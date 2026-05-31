#!/usr/bin/env python3
"""
Download audio files from a Telegram channel using Telethon (MTProto).
Input: JSON on stdin  { "channel": "@name_or_id", "output_dir": "...", "limit": 50, "min_id": 0 }
Output: JSON on stdout
"""
import sys
import json
import asyncio
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.telegram_config import get_client

# ── Config ─────────────────────────────────────────────────────────────────
RATE_LIMIT_PER_SEC = 10
BURST_LIMIT = 20
REQUEST_DELAY = 0.2
MAX_RETRIES = 5
BASE_BACKOFF = 2.0
MAX_BACKOFF = 60.0
DEFAULT_LIMIT = 50

# ── Inline rate limiter (from tele project) ───────────────────────────────
class _RateLimiter:
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.capacity = burst
        self.tokens = float(burst)
        self.last = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0
            else:
                self.tokens -= 1
            self.last = time.monotonic()


# ── Inline retry logic (from tele project) ────────────────────────────────
async def _with_retry(fn, max_retries: int, base_backoff: float, max_backoff: float):
    from telethon.errors import FloodWaitError
    for attempt in range(max_retries):
        try:
            return await fn()
        except FloodWaitError as e:
            print(f"[telegram_download] FloodWait: sleeping {e.seconds}s (attempt {attempt + 1})", file=sys.stderr)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            delay = min(base_backoff ** attempt, max_backoff)
            print(f"[telegram_download] Error: {e} — retry in {delay:.1f}s (attempt {attempt + 1})", file=sys.stderr)
            await asyncio.sleep(delay)
    raise RuntimeError(f"Max retries ({max_retries}) exceeded")


def _safe_filename(name: str, fallback: str) -> str:
    """Keep only filesystem-safe characters; fall back if result is empty."""
    safe = "".join(c if c.isalnum() or c in " .-_()" else "_" for c in name).strip()
    return safe if safe else fallback


async def _download(channel: str, output_dir: Path, limit: int, min_id: int, max_id: int = 0) -> dict:
    from telethon.tl.types import (
        MessageMediaDocument,
        DocumentAttributeAudio,
        DocumentAttributeFilename,
    )

    client, err = get_client(channel)
    if client is None:
        return {"success": False, "error": err}

    output_dir.mkdir(parents=True, exist_ok=True)
    limiter = _RateLimiter(RATE_LIMIT_PER_SEC, BURST_LIMIT)

    async def safe_call(fn):
        await limiter.acquire()
        async def wrapped():
            await asyncio.sleep(REQUEST_DELAY)
            return await fn()
        return await _with_retry(wrapped, MAX_RETRIES, BASE_BACKOFF, MAX_BACKOFF)

    downloaded = []
    skipped = 0

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"success": False, "error": "Telegram session expired — re-run auth.py in the tele project to refresh tele_session.session"}

    try:
        entity = await safe_call(lambda: client.get_entity(channel))
        channel_title = getattr(entity, "title", None) or getattr(entity, "username", channel)
        print(f"[telegram_download] Channel: {channel_title}", file=sys.stderr)

        async for message in client.iter_messages(entity, limit=limit, min_id=min_id, max_id=max_id):
            if not message.media or not isinstance(message.media, MessageMediaDocument):
                continue

            doc = message.media.document
            mime = getattr(doc, "mime_type", "") or ""
            if not mime.startswith("audio/"):
                continue

            # Determine extension and base name
            ext = "mp3" if mime == "audio/mpeg" else mime.split("/")[-1]
            filename = None

            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

            if not filename:
                title = ""
                performer = ""
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
                    filename = f"msg_{message.id}.{ext}"

            safe_name = _safe_filename(filename, f"msg_{message.id}.{ext}")
            save_path = output_dir / safe_name

            if save_path.exists():
                print(f"[telegram_download] Skip (exists): {safe_name}", file=sys.stderr)
                skipped += 1
                continue

            print(f"[telegram_download] Downloading: {safe_name}", file=sys.stderr)
            try:
                await client.download_media(message, file=str(save_path))
                size = save_path.stat().st_size if save_path.exists() else 0
                downloaded.append({
                    "message_id": message.id,
                    "filename": safe_name,
                    "path": str(save_path.resolve()),
                    "mime_type": mime,
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "date": message.date.isoformat() if message.date else None,
                })
                print(f"[telegram_download] Saved: {safe_name} ({round(size / 1024, 1)} KB)", file=sys.stderr)
            except Exception as e:
                print(f"[telegram_download] Failed {safe_name}: {e}", file=sys.stderr)

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
            "files": downloaded,
        },
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    channel = params.get("channel", "").strip()
    if not channel:
        print(json.dumps({"success": False, "error": "Missing required field: channel"}))
        sys.exit(1)

    raw_dir = params.get("output_dir", "").strip()
    output_dir = Path(raw_dir) if raw_dir else Path.home() / "Downloads" / "telegram"

    limit = int(params.get("limit", DEFAULT_LIMIT))
    min_id = int(params.get("min_id", 0))
    max_id = int(params.get("max_id", 0))

    result = asyncio.run(_download(channel, output_dir, limit, min_id, max_id))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
