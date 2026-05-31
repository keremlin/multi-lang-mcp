#!/usr/bin/env python3
"""
Download specific audio messages from a Telegram channel by message ID.
Uses Telethon's get_messages(ids=[...]) — fetches only the listed messages,
no history scan needed.

Input (stdin JSON):
  {
    "channel": "@myyazdmusic_com",
    "message_ids": [25301, 25440, 26012],
    "output_dir": ""          # optional, defaults to ~/Downloads/telegram
  }

Output:
  {"success": true, "data": {"downloaded_count": N, "skipped_count": N, "files": [...]}}
"""
import sys
import json
import asyncio
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.telegram_config import get_client


def _safe_filename(name: str, fallback: str) -> str:
    safe = "".join(c if c.isalnum() or c in " .-_()" else "_" for c in name).strip()
    return safe if safe else fallback


async def _download(channel: str, message_ids: list[int], output_dir: Path) -> dict:
    from telethon.tl.types import (
        MessageMediaDocument,
        DocumentAttributeAudio,
        DocumentAttributeFilename,
    )

    client, err = get_client(channel)
    if client is None:
        return {"success": False, "error": err}

    output_dir.mkdir(parents=True, exist_ok=True)

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"success": False, "error": "Telegram session expired — re-run auth to refresh tele_session.session"}

    downloaded = []
    skipped = 0
    failed = []

    try:
        entity = await client.get_entity(channel)
        channel_title = getattr(entity, "title", None) or getattr(entity, "username", channel)
        print(f"[telegram_download_by_ids] Channel: {channel_title}, fetching {len(message_ids)} messages", file=sys.stderr)

        # Fetch all requested messages in one round-trip
        messages = await client.get_messages(entity, ids=message_ids)

        for msg in messages:
            if msg is None:
                continue
            if not msg.media or not isinstance(msg.media, MessageMediaDocument):
                print(f"[telegram_download_by_ids] msg {msg.id}: no audio, skipping", file=sys.stderr)
                skipped += 1
                continue

            doc = msg.media.document
            mime = getattr(doc, "mime_type", "") or ""
            if not mime.startswith("audio/"):
                skipped += 1
                continue

            ext = "mp3" if mime == "audio/mpeg" else mime.split("/")[-1]
            filename = None

            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

            if not filename:
                title = performer = ""
                for attr in doc.attributes:
                    if isinstance(attr, DocumentAttributeAudio):
                        title = getattr(attr, "title", "") or ""
                        performer = getattr(attr, "performer", "") or ""
                        break
                if title and performer:
                    filename = f"{performer} - {title}.{ext}"
                elif title:
                    filename = f"{title}.{ext}"
                else:
                    filename = f"msg_{msg.id}.{ext}"

            safe_name = _safe_filename(filename, f"msg_{msg.id}.{ext}")
            save_path = output_dir / safe_name

            if save_path.exists():
                print(f"[telegram_download_by_ids] Skip (exists): {safe_name}", file=sys.stderr)
                skipped += 1
                continue

            print(f"[telegram_download_by_ids] Downloading: {safe_name}", file=sys.stderr)
            try:
                await client.download_media(msg, file=str(save_path))
                size = save_path.stat().st_size if save_path.exists() else 0
                downloaded.append({
                    "message_id": msg.id,
                    "filename": safe_name,
                    "path": str(save_path.resolve()),
                    "mime_type": mime,
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "date": msg.date.isoformat() if msg.date else None,
                })
                print(f"[telegram_download_by_ids] Saved: {safe_name} ({round(size / 1024, 1)} KB)", file=sys.stderr)
            except Exception as e:
                print(f"[telegram_download_by_ids] Failed {safe_name}: {e}", file=sys.stderr)
                failed.append({"message_id": msg.id, "error": str(e)})

    finally:
        await client.disconnect()

    return {
        "success": True,
        "data": {
            "channel": channel,
            "channel_title": channel_title,
            "output_dir": str(output_dir.resolve()),
            "downloaded_count": len(downloaded),
            "skipped_count": skipped,
            "failed_count": len(failed),
            "files": downloaded,
            "failed": failed,
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

    channel = params.get("channel", "").strip()
    if not channel:
        print(json.dumps({"success": False, "error": "Missing required field: channel"}))
        sys.exit(1)

    message_ids = params.get("message_ids", [])
    if not message_ids or not isinstance(message_ids, list):
        print(json.dumps({"success": False, "error": "message_ids must be a non-empty list of integers"}))
        sys.exit(1)

    raw_dir = params.get("output_dir", "").strip()
    output_dir = Path(raw_dir) if raw_dir else Path.home() / "Downloads" / "telegram"

    result = asyncio.run(_download(channel, [int(i) for i in message_ids], output_dir))
    print(json.dumps(result))


if __name__ == "__main__":
    main()