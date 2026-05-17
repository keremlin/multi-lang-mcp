import sys
import json
import time
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
    audio_format = sys.argv[5] if len(sys.argv) > 5 else ""

    try:
        import yt_dlp
    except ImportError:
        print(json.dumps({"success": False, "error": "yt-dlp not installed — run: pip install yt-dlp"}))
        sys.exit(1)

    try:
        from tqdm import tqdm
        _tqdm_available = True
    except ImportError:
        _tqdm_available = False

    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    download_state = {"filepath": None}
    progress_log = []   # [{pct, speed_mbps, elapsed}]
    speed_samples = []
    start_time = time.monotonic()
    bar = None

    def progress_hook(d):
        nonlocal bar
        status = d.get("status")

        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0          # bytes/s
            speed_mbps = round(speed / (1024 * 1024), 2) if speed else 0
            elapsed = round(time.monotonic() - start_time, 1)

            if speed_mbps:
                speed_samples.append(speed_mbps)

            if total:
                pct = round(downloaded / total * 100, 1)

                # tqdm bar on stderr
                if _tqdm_available:
                    if bar is None:
                        bar = tqdm(
                            total=total,
                            unit="B",
                            unit_scale=True,
                            unit_divisor=1024,
                            desc="Downloading",
                            file=sys.stderr,
                            dynamic_ncols=True,
                        )
                    bar.n = downloaded
                    bar.refresh()
                else:
                    filled = int(pct / 5)
                    bar_str = "█" * filled + "░" * (20 - filled)
                    eta = d.get("eta") or 0
                    print(
                        f"\r[{bar_str}] {pct:5.1f}%  {speed_mbps:.2f} MB/s  ETA {eta}s   ",
                        end="",
                        file=sys.stderr,
                        flush=True,
                    )

                # record milestone every 10 %
                last_pct = progress_log[-1]["pct"] if progress_log else -1
                if pct - last_pct >= 10:
                    progress_log.append({"pct": pct, "speed_mbps": speed_mbps, "elapsed_s": elapsed})
            else:
                print(f"[youtube_download] {downloaded} bytes downloaded", file=sys.stderr)

        elif status == "finished":
            if bar is not None:
                bar.close()
                bar = None
            else:
                print(file=sys.stderr)   # newline after \r bar
            download_state["filepath"] = d.get("filename")
            print(f"[youtube_download] stream finished: {d.get('filename')}", file=sys.stderr)

    ydl_opts = {
        "outtmpl": str(DOWNLOADS_DIR / "%(title)s.%(ext)s"),
        "format": "bestaudio/best" if audio_format else video_format,
        "retries": retries,
        "socket_timeout": socket_timeout,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if audio_format:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_format,
            "preferredquality": "192",
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename_fallback = ydl.prepare_filename(info)

        if info.get("requested_downloads"):
            filepath = Path(info["requested_downloads"][0].get("filepath", filename_fallback))
        elif download_state["filepath"]:
            filepath = Path(download_state["filepath"])
        else:
            filepath = Path(filename_fallback)

        file_size = filepath.stat().st_size if filepath.exists() else 0
        elapsed_total = round(time.monotonic() - start_time, 1)
        avg_speed = round(sum(speed_samples) / len(speed_samples), 2) if speed_samples else 0
        peak_speed = round(max(speed_samples), 2) if speed_samples else 0

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
                "download_stats": {
                    "elapsed_seconds": elapsed_total,
                    "avg_speed_mbps": avg_speed,
                    "peak_speed_mbps": peak_speed,
                    "progress_log": progress_log,
                },
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
