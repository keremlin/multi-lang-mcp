"""Minimal yt_dlp stub for offline testing of youtube_download.py."""
from pathlib import Path


class YoutubeDL:
    def __init__(self, opts):
        self._opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def extract_info(self, url, download=True):
        outtmpl = self._opts.get("outtmpl", "%(title)s.%(ext)s")
        title = "Fake Test Video"
        ext = "mp4"
        filepath = outtmpl.replace("%(title)s", title).replace("%(ext)s", ext)
        dest = Path(filepath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"0" * 1_048_576)  # 1 MB placeholder

        for hook in self._opts.get("progress_hooks", []):
            hook({"status": "downloading", "downloaded_bytes": 524288, "total_bytes": 1_048_576})
            hook({"status": "downloading", "downloaded_bytes": 1_048_576, "total_bytes": 1_048_576})
            hook({"status": "finished", "filename": filepath})

        return {
            "title": title,
            "uploader": "Fake Channel",
            "duration": 120,
            "format": "mp4",
            "requested_downloads": [{"filepath": filepath}],
        }

    def prepare_filename(self, info):
        outtmpl = self._opts.get("outtmpl", "%(title)s.%(ext)s")
        return outtmpl.replace("%(title)s", info["title"]).replace("%(ext)s", "mp4")


class utils:
    class DownloadError(Exception):
        pass
