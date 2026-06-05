"""
Forward specific messages from one Telegram chat to another.

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


async def _forward(from_chat: str, message_ids: list, to_chat: str) -> dict:
    client, err = get_client(from_chat, need_write=True)
    if client is None:
        return {"success": False, "error": err}

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"success": False, "error": "Session expired — re-run the session setup"}

    try:
        from_entity = await client.get_entity(from_chat)
        to_entity = await client.get_entity(to_chat)

        result = await client.forward_messages(
            entity=to_entity,
            messages=message_ids,
            from_peer=from_entity,
        )

        forwarded = []
        for msg in (result if isinstance(result, list) else [result]):
            forwarded.append({
                "new_message_id": getattr(msg, "id", None),
                "date": msg.date.isoformat() if getattr(msg, "date", None) else None,
            })

        return {
            "success": True,
            "data": {
                "from_chat": from_chat,
                "to_chat": to_chat,
                "forwarded_count": len(forwarded),
                "messages": forwarded,
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
        from_chat = params.get("from_chat", "").strip()
        to_chat = params.get("to_chat", "").strip()
        message_ids = params.get("message_ids", [])

        if not from_chat or not to_chat:
            result = {"success": False, "error": "from_chat and to_chat are required"}
        elif not message_ids:
            result = {"success": False, "error": "message_ids must be a non-empty list"}
        else:
            result = asyncio.run(_forward(from_chat, [int(i) for i in message_ids], to_chat))
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    print(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
