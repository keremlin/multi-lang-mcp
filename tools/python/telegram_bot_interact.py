"""
Telegram bot interaction — send a text message or click an inline button.

Bot-only: rejects channels and groups at the Telethon entity level.
Requires TELEGRAM_WRITE_ENABLED=true.
"""
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.telegram_config import get_client

_DEFAULT_OUTPUT = Path.home() / "Downloads" / "telegram"


async def _interact(
    bot_username: str,
    text: str,
    click_button_index: int,
    output_dir: str,
    wait_seconds: int,
) -> dict:
    client, err = get_client(bot_username, need_write=True)
    if client is None:
        return {"success": False, "error": err}

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"success": False, "error": "Session expired — re-run the session setup"}

    try:
        entity = await client.get_entity(bot_username)

        # Bot-only enforcement: reject channels, groups, and regular users
        if not getattr(entity, "bot", False):
            return {
                "success": False,
                "error": (
                    f"'{bot_username}' is not a bot. "
                    "telegram_bot_interact only works with bots — not channels or groups."
                ),
            }

        me = await client.get_me()

        if click_button_index >= 0:
            # Find the most recent bot message that has inline buttons
            msgs = await client.get_messages(entity, limit=20)
            target_msg = None
            for m in msgs:
                if m.sender_id != me.id and m.buttons:
                    target_msg = m
                    break
            if target_msg is None:
                return {"success": False, "error": "No recent bot message with inline buttons found"}
            flat = [btn for row in target_msg.buttons for btn in row]
            if click_button_index >= len(flat):
                return {
                    "success": False,
                    "error": f"Button index {click_button_index} out of range (0–{len(flat) - 1})",
                }
            await flat[click_button_index].click()

        elif text:
            try:
                await client.send_message(entity, text)
            except Exception as exc:
                if "blocked" in str(exc).lower():
                    from telethon.tl.functions.contacts import UnblockRequest
                    await client(UnblockRequest(entity))
                    await client.send_message(entity, text)
                else:
                    raise
        else:
            return {"success": False, "error": "Provide either 'text' or 'click_button_index'"}

        # Wait for the bot to respond
        await asyncio.sleep(wait_seconds)

        # Fetch recent conversation messages — never download media here.
        # Use telegram_forward_message + telegram_download_by_ids for large files.
        msgs = await client.get_messages(entity, limit=20)

        responses = []
        for msg in msgs:
            if msg.sender_id == me.id:
                continue  # skip our own messages

            item = {
                "message_id": msg.id,
                "text": msg.text or "",
                "date": msg.date.isoformat(),
                "has_media": msg.media is not None,
                "media_type": None,
                "buttons": [],
            }

            if msg.media:
                from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
                if isinstance(msg.media, MessageMediaDocument):
                    item["media_type"] = getattr(msg.media.document, "mime_type", "document")
                elif isinstance(msg.media, MessageMediaPhoto):
                    item["media_type"] = "photo"
                else:
                    item["media_type"] = type(msg.media).__name__

            # Extract inline keyboard buttons
            if msg.buttons:
                for row_idx, row in enumerate(msg.buttons):
                    flat_offset = sum(len(msg.buttons[r]) for r in range(row_idx))
                    item["buttons"].append([
                        {
                            "index": flat_offset + i,
                            "text": btn.text,
                            "url": getattr(btn, "url", None),
                            "has_callback": bool(getattr(btn, "data", None)),
                        }
                        for i, btn in enumerate(row)
                    ])

            responses.append(item)

        return {
            "success": True,
            "data": {
                "bot": bot_username,
                "action": (
                    f"clicked button {click_button_index}"
                    if click_button_index >= 0
                    else f"sent: {text!r}"
                ),
                "responses": responses,
            },
        }

    finally:
        await client.disconnect()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
        bot_username = params.get("bot_username", "")
        text = params.get("text", "")
        click_button_index = int(params.get("click_button_index", -1))
        output_dir = params.get("output_dir", "")
        wait_seconds = int(params.get("wait_seconds", 8))

        if not bot_username:
            result = {"success": False, "error": "bot_username is required"}
        else:
            result = asyncio.run(
                _interact(bot_username, text, click_button_index, output_dir, wait_seconds)
            )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    # ensure_ascii=True guarantees pure ASCII output — safe regardless of the
    # parent process's stdout encoding (cp1252 on Windows without UTF-8 mode).
    print(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
