import sys
import json
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from shared import download_progress as _dp
    _DP_OK = True
except Exception:
    _DP_OK = False

DOWNLOADS_DIR = Path.home() / "Downloads"

# ffmpeg vf filter: scale down to max 1920x1080, keep aspect ratio, ensure even dimensions
_LG_VF = (
    "scale=w=min(iw\\,1920):h=min(ih\\,1080)"
    ":force_original_aspect_ratio=decrease,"
    "pad=ceil(iw/2)*2:ceil(ih/2)*2"
)


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No input provided — pass JSON on stdin"}))
        sys.exit(1)

    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {exc}"}))
        sys.exit(1)

    url = params.get("url", "").strip()
    if not url:
        print(json.dumps({"success": False, "error": "url is required"}))
        sys.exit(1)

    crf = params.get("crf", 23)
    preset = params.get("preset", "medium")
    retries = params.get("retries", 3)
    socket_timeout = params.get("timeout", 30)

    valid_presets = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
    if preset not in valid_presets:
        print(json.dumps({"success": False, "error": f"Invalid preset '{preset}'. Choose from: {', '.join(sorted(valid_presets))}"}))
        sys.exit(1)

    try:
        crf = int(crf)
        if not (0 <= crf <= 51):
            raise ValueError
    except (TypeError, ValueError):
        print(json.dumps({"success": False, "error": "crf must be an integer between 0 and 51"}))
        sys.exit(1)

    try:
        import yt_dlp
    except ImportError:
        print(json.dumps({"success": False, "error": "yt-dlp not installed — run: pip install yt-dlp"}))
        sys.exit(1)

    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    # Register in progress UI
    dl_id = None
    if _DP_OK:
        try:
            dl_id = _dp.new_download("youtube_downloader_lg", name=url)
        except Exception:
            pass

    download_state = {"filepath": None}
    start_time = time.monotonic()

    def progress_hook(d):
        status = d.get("status")
        if status == "downloading" and dl_id and _DP_OK:
            try:
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("speed") or 0
                if total:
                    pct = min(round(downloaded / total * 100, 1), 99)
                    speed_mbps = round(speed / (1024 * 1024), 2) if speed else 0
                    _dp.update(dl_id, status="downloading", pct=pct, speed_mbps=speed_mbps)
            except Exception:
                pass
        elif status == "finished":
            download_state["filepath"] = d.get("filename")

    def pp_hook(d):
        if not dl_id or not _DP_OK:
            return
        try:
            if d.get("status") == "started":
                _dp.update(dl_id, status="encoding", pct=99)
        except Exception:
            pass

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": str(DOWNLOADS_DIR / "%(title)s.%(ext)s"),
        # Force merge to MKV so FFmpegVideoConvertor always triggers (skipped if already .mp4)
        "merge_output_format": "mkv",
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
        "postprocessor_args": {
            "videoconvertor": [
                "-vcodec", "libx264",
                "-acodec", "aac",
                "-crf", str(crf),
                "-preset", preset,
                "-vf", _LG_VF,
                "-movflags", "+faststart",
            ]
        },
        "retries": retries,
        "socket_timeout": socket_timeout,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [pp_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename_fallback = ydl.prepare_filename(info)

        # Resolve final filepath — VideoConvertor renames extension to .mp4
        if info.get("requested_downloads"):
            raw_path = info["requested_downloads"][0].get("filepath", filename_fallback)
        elif download_state["filepath"]:
            raw_path = download_state["filepath"]
        else:
            raw_path = filename_fallback

        filepath = Path(raw_path)
        mp4_path = filepath.with_suffix(".mp4")
        if mp4_path.exists():
            filepath = mp4_path

        file_size = filepath.stat().st_size if filepath.exists() else 0
        elapsed = round(time.monotonic() - start_time, 1)

        if dl_id and _DP_OK:
            try:
                _dp.complete(
                    dl_id,
                    name=info.get("title", filepath.name),
                    saved_to=str(filepath.resolve()),
                    size_mb=round(file_size / (1024 * 1024), 2),
                )
            except Exception:
                pass

        print(json.dumps({
            "success": True,
            "data": {
                "title": info.get("title", ""),
                "url": url,
                "saved_to": str(filepath.resolve()),
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "output_format": {
                    "container": "mp4",
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "max_resolution": "1920x1080",
                    "crf": crf,
                    "preset": preset,
                },
                "duration_seconds": info.get("duration"),
                "uploader": info.get("uploader", ""),
                "elapsed_seconds": elapsed,
            },
        }))

    except yt_dlp.utils.DownloadError as exc:
        if dl_id and _DP_OK:
            try:
                _dp.fail(dl_id, str(exc))
            except Exception:
                pass
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)
    except Exception as exc:
        if dl_id and _DP_OK:
            try:
                _dp.fail(dl_id, str(exc))
            except Exception:
                pass
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
