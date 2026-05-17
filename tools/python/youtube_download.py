import sys
import json
from pathlib import Path

DOWNLOADS_DIR = Path.home() / "Downloads"


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: youtube_download.py <url> [retries=3] [timeout=30] [format=bestvideo+bestaudio/best]",
        }))
        sys.exit(1)

    url = sys.argv[1]

    try:
        retries = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        socket_timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    except ValueError as exc:
        print(json.dumps({"success": False, "error": f"Invalid argument: {exc}"}))
        sys.exit(1)

    video_format = sys.argv[4] if len(sys.argv) > 4 else "bestvideo+bestaudio/best"

    try:
        import yt_dlp
    except ImportError:
        print(json.dumps({"success": False, "error": "yt-dlp not installed — run: pip install yt-dlp"}))
        sys.exit(1)

    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    download_state = {"filepath": None}

    def progress_hook(d):
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                pct = downloaded / total * 100
                print(f"[youtube_download] {pct:.1f}% ({downloaded}/{total} bytes)", file=sys.stderr)
            else:
                print(f"[youtube_download] {downloaded} bytes downloaded", file=sys.stderr)
        elif status == "finished":
            download_state["filepath"] = d.get("filename")
            print(f"[youtube_download] stream finished: {d.get('filename')}", file=sys.stderr)

    ydl_opts = {
        "outtmpl": str(DOWNLOADS_DIR / "%(title)s.%(ext)s"),
        "format": video_format,
        "retries": retries,
        "socket_timeout": socket_timeout,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename_fallback = ydl.prepare_filename(info)

        # requested_downloads is the authoritative post-merge filepath
        if info.get("requested_downloads"):
            filepath = Path(info["requested_downloads"][0].get("filepath", filename_fallback))
        elif download_state["filepath"]:
            filepath = Path(download_state["filepath"])
        else:
            filepath = Path(filename_fallback)

        file_size = filepath.stat().st_size if filepath.exists() else 0

        print(json.dumps({
            "success": True,
            "data": {
                "title": info.get("title", ""),
                "url": url,
                "saved_to": str(filepath.resolve()),
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "status": "completed",
                "duration_seconds": info.get("duration"),
                "uploader": info.get("uploader", ""),
                "format": info.get("format", ""),
            },
        }))

    except yt_dlp.utils.DownloadError as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
