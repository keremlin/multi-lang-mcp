#!/usr/bin/env python3
"""
Download specific messages (audio, video, documents) from a Telegram channel by message ID.
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
import os
import sys
import json
import asyncio
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.telegram_config import get_client

try:
    from shared import download_progress as _dp
    _DP_OK = True
except Exception:
    _DP_OK = False


def _safe_filename(name: str, fallback: str) -> str:
    safe = "".join(c if c.isalnum() or c in " .-_()" else "_" for c in name).strip()
    return safe if safe else fallback


async def _download(channel: str, message_ids: list[int], output_dir: Path, dl_id: str = "") -> dict:
    from telethon.tl.types import (
        MessageMediaDocument,
        DocumentAttributeAudio,
        DocumentAttributeVideo,
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
    files_done = 0
    files_total = len(message_ids)

    try:
        entity = await client.get_entity(channel)
        channel_title = getattr(entity, "title", None) or getattr(entity, "username", channel)
        print(f"[telegram_download_by_ids] Channel: {channel_title}, fetching {len(message_ids)} messages", file=sys.stderr)

        if dl_id and _DP_OK:
            try:
                _dp.update(dl_id, name=channel_title, files_total=files_total)
            except Exception:
                pass

        # Fetch all requested messages in one round-trip
        messages = await client.get_messages(entity, ids=message_ids)

        for msg in messages:
            if msg is None:
                continue
            if not msg.media or not isinstance(msg.media, MessageMediaDocument):
                print(f"[telegram_download_by_ids] msg {msg.id}: no document media, skipping", file=sys.stderr)
                skipped += 1
                continue

            doc = msg.media.document
            mime = getattr(doc, "mime_type", "") or ""
            ext = mime.split("/")[-1] if "/" in mime else "bin"
            if mime == "audio/mpeg":
                ext = "mp3"
            elif mime == "video/mp4":
                ext = "mp4"

            # Try to get filename from attributes
            filename = None
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

            if not filename:
                if mime.startswith("audio/"):
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
                else:
                    filename = f"msg_{msg.id}.{ext}"

            safe_name = _safe_filename(filename, f"msg_{msg.id}.{ext}")
            save_path = output_dir / safe_name

            if save_path.exists():
                print(f"[telegram_download_by_ids] Skip (exists): {safe_name}", file=sys.stderr)
                skipped += 1
                continue

            print(f"[telegram_download_by_ids] Downloading: {safe_name}", file=sys.stderr)
            if dl_id and _DP_OK:
                try:
                    _dp.update(dl_id, status="downloading", current_file=safe_name,
                               files_done=files_done, files_total=files_total,
                               pct=round(files_done / files_total * 100, 1) if files_total else 0)
                except Exception:
                    pass

            def _make_progress_cb(name, did, done, total_files):
                def _cb(current, total):
                    if did and _DP_OK and total:
                        try:
                            file_pct = current / total
                            overall_pct = (done + file_pct) / total_files * 100 if total_files else 0
                            _dp.update(did, status="downloading", current_file=name,
                                       files_done=done, files_total=total_files,
                                       pct=round(overall_pct, 1),
                                       downloaded_mb=round(current / (1024 * 1024), 1),
                                       total_mb=round(total / (1024 * 1024), 1))
                        except Exception:
                            pass
                return _cb

            try:
                await client.download_media(
                    msg, file=str(save_path),
                    progress_callback=_make_progress_cb(safe_name, dl_id, files_done, files_total),
                )
                size = save_path.stat().st_size if save_path.exists() else 0
                files_done += 1
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

    result = {
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
    if dl_id and _DP_OK:
        try:
            _dp.complete(
                dl_id,
                name=channel_title,
                output_dir=str(output_dir.resolve()),
                downloaded_count=len(downloaded),
            )
        except Exception:
            pass
    return result


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

    dl_id = _dp.new_download("telegram", channel) if _DP_OK else ""
    if dl_id and _DP_OK:
        try:
            _dp.update(dl_id, pid=os.getpid())
        except Exception:
            pass
    try:
        result = asyncio.run(_download(channel, [int(i) for i in message_ids], output_dir, dl_id))
    except Exception as exc:
        if dl_id and _DP_OK:
            try:
                _dp.fail(dl_id, str(exc))
            except Exception:
                pass
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()