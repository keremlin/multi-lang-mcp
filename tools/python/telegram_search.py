#!/usr/bin/env python3
"""
Search for audio or video files across Telegram (globally or within a specific channel).
Uses Telegram's server-side search — same engine as the Telegram app's search bar.
Does NOT download — returns metadata and message IDs for use with telegram_download_by_ids.

Input (stdin JSON):
  {
    "query": "Maximum Pleasure Guaranteed",
    "channel": "",           # optional — empty means global search across all Telegram
    "media_type": "any",     # "audio" | "video" | "any"
    "limit": 50
  }

Output:
  {"success": true, "data": {"scope": "global", "match_count": N, "matches": [...]}}
"""
import sys
import json
import asyncio
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.telegram_config import get_client

DEFAULT_LIMIT = 50


async def _search(channel: str, query: str, media_type: str, limit: int) -> dict:
    from telethon.tl.types import (
        MessageMediaDocument,
        DocumentAttributeAudio,
        DocumentAttributeFilename,
        DocumentAttributeVideo,
        InputMessagesFilterVideo,
        InputMessagesFilterMusic,
        InputMessagesFilterDocument,
    )

    client, err = get_client(channel)
    if client is None:
        return {"success": False, "error": err}

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"success": False, "error": "Telegram session expired — re-run auth to refresh tele_session.session"}

    # entity=None → Telegram global search; otherwise search within a specific channel
    entity = None
    scope = "global"
    if channel.strip():
        try:
            entity = await client.get_entity(channel.strip())
            scope = getattr(entity, "title", None) or getattr(entity, "username", channel.strip())
        except Exception as e:
            await client.disconnect()
            return {"success": False, "error": f"Could not resolve channel '{channel}': {e}"}

    # Map media_type to Telegram API filters.
    # For "any" we run both filtered passes (video + music + document) AND an
    # unfiltered pass so announcement/text posts about the content are also captured.
    if media_type == "video":
        filter_passes = [InputMessagesFilterVideo(), None]
    elif media_type == "audio":
        filter_passes = [InputMessagesFilterMusic(), None]
    else:
        filter_passes = [InputMessagesFilterVideo(), InputMessagesFilterMusic(), InputMessagesFilterDocument(), None]

    print(
        f"[telegram_search] scope={scope!r} | query={query!r} | type={media_type} | limit={limit}",
        file=sys.stderr,
    )

    matches = []
    announcements = []
    seen_ids: set = set()
    total_scanned = 0

    try:
        for msg_filter in filter_passes:
            async for message in client.iter_messages(
                entity, search=query, filter=msg_filter, limit=limit
            ):
                total_scanned += 1

                if message.id in seen_ids:
                    continue
                seen_ids.add(message.id)

                chat = message.chat
                chat_name = (
                    getattr(chat, "title", None)
                    or getattr(chat, "username", None)
                    or str(message.chat_id)
                )
                chat_username = getattr(chat, "username", None) or ""

                # Handle actual downloadable document/file
                if message.media and isinstance(message.media, MessageMediaDocument):
                    doc = message.media.document
                    mime = (getattr(doc, "mime_type", "") or "").lower()

                    title = performer = filename = ""
                    duration = width = height = None

                    for attr in doc.attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            filename = attr.file_name or ""
                        elif isinstance(attr, DocumentAttributeAudio):
                            title = getattr(attr, "title", "") or ""
                            performer = getattr(attr, "performer", "") or ""
                            duration = getattr(attr, "duration", None)
                        elif isinstance(attr, DocumentAttributeVideo):
                            duration = getattr(attr, "duration", None)
                            width = getattr(attr, "w", None)
                            height = getattr(attr, "h", None)

                    size = getattr(doc, "size", 0) or 0
                    entry = {
                        "message_id": message.id,
                        "result_type": "file",
                        "chat_name": chat_name,
                        "chat_username": f"@{chat_username}" if chat_username else "",
                        "chat_id": message.chat_id,
                        "filename": filename,
                        "title": title,
                        "performer": performer,
                        "mime_type": mime,
                        "size_bytes": size,
                        "size_mb": round(size / (1024 * 1024), 2),
                        "date": message.date.isoformat() if message.date else None,
                    }
                    if duration is not None:
                        entry["duration_seconds"] = duration
                    if width is not None and height is not None:
                        entry["resolution"] = f"{width}x{height}"

                    matches.append(entry)
                    print(
                        f"[telegram_search] File match: msg_id={message.id} | chat={chat_name!r} | {filename or title or '(unnamed)'}",
                        file=sys.stderr,
                    )

                else:
                    # Text/announcement post mentioning the content
                    snippet = (message.message or "").strip()[:200]

                    # Extract all links: inline keyboard buttons + text entity URLs
                    inline_buttons = []
                    markup = getattr(message, "reply_markup", None)
                    if markup:
                        from telethon.tl.types import (
                            ReplyInlineMarkup,
                            KeyboardButtonUrl,
                            KeyboardButtonCallback,
                        )
                        if isinstance(markup, ReplyInlineMarkup):
                            for row in markup.rows:
                                for btn in row.buttons:
                                    if isinstance(btn, KeyboardButtonUrl):
                                        inline_buttons.append({
                                            "text": btn.text,
                                            "url": btn.url,
                                            "type": "url",
                                        })
                                    elif isinstance(btn, KeyboardButtonCallback):
                                        inline_buttons.append({
                                            "text": btn.text,
                                            "data": btn.data.decode("utf-8", errors="replace") if btn.data else "",
                                            "type": "callback",
                                        })

                    # Also extract text entity URLs (hyperlinks embedded in message text)
                    raw_text = message.message or ""
                    for ent in (message.entities or []):
                        from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
                        if isinstance(ent, MessageEntityTextUrl):
                            label = raw_text[ent.offset: ent.offset + ent.length]
                            inline_buttons.append({
                                "text": label,
                                "url": ent.url,
                                "type": "text_url",
                            })
                        elif isinstance(ent, MessageEntityUrl):
                            url_text = raw_text[ent.offset: ent.offset + ent.length]
                            inline_buttons.append({
                                "text": url_text,
                                "url": url_text,
                                "type": "plain_url",
                            })

                    announcements.append({
                        "message_id": message.id,
                        "result_type": "announcement",
                        "chat_name": chat_name,
                        "chat_username": f"@{chat_username}" if chat_username else "",
                        "chat_id": message.chat_id,
                        "text_snippet": snippet,
                        "date": message.date.isoformat() if message.date else None,
                        "inline_buttons": inline_buttons,
                    })
                    print(
                        f"[telegram_search] Announcement: msg_id={message.id} | chat={chat_name!r}",
                        file=sys.stderr,
                    )

    finally:
        await client.disconnect()

    return {
        "success": True,
        "data": {
            "scope": scope,
            "query": query,
            "media_type": media_type,
            "total_scanned": total_scanned,
            "file_count": len(matches),
            "announcement_count": len(announcements),
            "files": matches,
            "announcements": announcements,
        },
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    raw = sys.stdin.read().strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    query = params.get("query", "").strip()
    if not query:
        print(json.dumps({"success": False, "error": "Missing required field: query"}))
        sys.exit(1)

    channel = params.get("channel", "").strip()
    media_type = params.get("media_type", "any").strip().lower()
    if media_type not in ("audio", "video", "any"):
        print(json.dumps({"success": False, "error": "media_type must be 'audio', 'video', or 'any'"}))
        sys.exit(1)

    limit = int(params.get("limit", DEFAULT_LIMIT))

    result = asyncio.run(_search(channel, query, media_type, limit))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
