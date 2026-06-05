"""
Telegram channel join tool — join a public channel or a private invite link.

Requires TELEGRAM_WRITE_ENABLED=true (write gate via get_client).

Accepted formats for invite_link:
  @username               public channel
  t.me/username           public channel
  https://t.me/+HASH      private invite link
  https://t.me/joinchat/HASH  private invite link (legacy format)
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
_PUBLIC_RE = re.compile(r"(?:t\.me/)([A-Za-z0-9_]+)")


def _parse_invite(raw: str):
    """Return ('private', hash) or ('public', username) or (None, error)."""
    raw = raw.strip()
    m = _PRIVATE_RE.search(raw)
    if m:
        return "private", m.group(1)
    if raw.startswith("@"):
        return "public", raw
    m = _PUBLIC_RE.search(raw)
    if m:
        return "public", "@" + m.group(1)
    # Assume it's a bare username
    if re.fullmatch(r"[A-Za-z0-9_]{5,}", raw):
        return "public", "@" + raw
    return None, f"Cannot parse invite link or username: {raw!r}"


async def _join(invite_link: str) -> dict:
    kind, value = _parse_invite(invite_link)
    if kind is None:
        return {"success": False, "error": value}

    # Pass the channel/link through the gate (need_write=True enforces the flag)
    channel_arg = invite_link if kind == "private" else value
    client, err = get_client(channel_arg, need_write=True)
    if client is None:
        return {"success": False, "error": err}

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"success": False, "error": "Session expired — re-run the session setup"}

    try:
        if kind == "private":
            from telethon.tl.functions.messages import ImportChatInviteRequest
            result = await client(ImportChatInviteRequest(value))
            # result.chats[0] is the channel we just joined
            chat = result.chats[0] if result.chats else None
            return {
                "success": True,
                "data": {
                    "joined": True,
                    "type": "private_invite",
                    "hash": value,
                    "channel_id": getattr(chat, "id", None),
                    "channel_title": getattr(chat, "title", None),
                    "channel_username": getattr(chat, "username", None),
                },
            }
        else:
            from telethon.tl.functions.channels import JoinChannelRequest
            entity = await client.get_entity(value)
            await client(JoinChannelRequest(entity))
            return {
                "success": True,
                "data": {
                    "joined": True,
                    "type": "public",
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
        invite_link = params.get("invite_link", "").strip()
        if not invite_link:
            result = {"success": False, "error": "invite_link is required"}
        else:
            result = asyncio.run(_join(invite_link))
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    print(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
