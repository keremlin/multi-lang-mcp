"""
Leave / unsubscribe from a Telegram channel or group.

Accepts @username, t.me/username, or t.me/+HASH invite links.
Requires TELEGRAM_WRITE_ENABLED=true.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.telegram_config import get_client

_PRIVATE_RE = re.compile(r"(?:t\.me/\+|t\.me/joinchat/)([A-Za-z0-9_\-]+)")
_PUBLIC_RE = re.compile(r"t\.me/([A-Za-z0-9_]+)")


def _resolve_channel_arg(raw: str) -> str:
    """Return the best identifier to pass to get_entity / get_client."""
    raw = raw.strip()
    if raw.startswith("@") or raw.lstrip("-").isdigit():
        return raw
    m = _PUBLIC_RE.search(raw)
    if m:
        return "@" + m.group(1)
    # For private links we pass the full URL; Telethon can resolve from session cache
    m = _PRIVATE_RE.search(raw)
    if m:
        return raw  # pass the full invite link
    return raw


async def _leave(channel: str) -> dict:
    channel_arg = _resolve_channel_arg(channel)
    client, err = get_client(channel_arg, need_write=True)
    if client is None:
        return {"success": False, "error": err}

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"success": False, "error": "Session expired — re-run the session setup"}

    try:
        entity = await client.get_entity(channel_arg)

        from telethon.tl.types import Channel, Chat
        if isinstance(entity, Channel):
            from telethon.tl.functions.channels import LeaveChannelRequest
            await client(LeaveChannelRequest(channel=entity))
        elif isinstance(entity, Chat):
            from telethon.tl.functions.messages import DeleteChatUserRequest
            me = await client.get_me()
            await client(DeleteChatUserRequest(chat_id=entity.id, user_id=me.id))
        else:
            return {"success": False, "error": f"Cannot leave entity type: {type(entity).__name__}"}

        return {
            "success": True,
            "data": {
                "left": True,
                "channel_id": getattr(entity, "id", None),
                "channel_title": getattr(entity, "title", None),
                "channel_username": getattr(entity, "username", None),
            },
        }

    except Exception as exc:
        return {"success": False, "error": str(exc)}
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
        channel = params.get("channel", "").strip()
        if not channel:
            result = {"success": False, "error": "channel is required"}
        else:
            result = asyncio.run(_leave(channel))
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    print(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
