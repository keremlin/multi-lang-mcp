"""
Delete specific messages from a Telegram chat.

You must be the sender of the messages or an admin of the chat.
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


async def _delete(chat: str, message_ids: list) -> dict:
    client, err = get_client(chat, need_write=True)
    if client is None:
        return {"success": False, "error": err}

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"success": False, "error": "Session expired — re-run the session setup"}

    try:
        entity = await client.get_entity(chat)
        await client.delete_messages(entity, message_ids)
        return {
            "success": True,
            "data": {
                "chat": chat,
                "deleted_message_ids": message_ids,
                "deleted_count": len(message_ids),
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
        chat = params.get("chat", "").strip()
        message_ids = params.get("message_ids", [])
        if not chat:
            result = {"success": False, "error": "chat is required"}
        elif not message_ids:
            result = {"success": False, "error": "message_ids must be a non-empty list"}
        else:
            result = asyncio.run(_delete(chat, [int(i) for i in message_ids]))
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    print(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
