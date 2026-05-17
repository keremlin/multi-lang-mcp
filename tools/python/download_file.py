import sys
import json
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: download_file.py <url> <save_path>"}))
        sys.exit(1)

    url = sys.argv[1]
    save_path = sys.argv[2]

    if not url.startswith(("http://", "https://")):
        print(json.dumps({"success": False, "error": "URL must use http:// or https://"}))
        sys.exit(1)

    try:
        import requests
    except ImportError:
        print(json.dumps({"success": False, "error": "requests library not installed — run: pip install requests"}))
        sys.exit(1)

    dest = Path(save_path)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(json.dumps({"success": False, "error": f"Cannot create directory: {exc}"}))
        sys.exit(1)

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; download_file-tool/1.0)"}
        with requests.get(url, stream=True, timeout=(10, 270), headers=headers) as response:
            response.raise_for_status()

            total = int(response.headers.get("content-length", 0)) or None
            downloaded = 0
            milestones_hit = []
            next_milestone = 25

            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total:
                            pct = downloaded / total * 100
                            while next_milestone <= pct and next_milestone <= 100:
                                milestones_hit.append(next_milestone)
                                print(
                                    f"[download_file] {next_milestone}% ({downloaded}/{total} bytes)",
                                    file=sys.stderr,
                                )
                                next_milestone += 25

        if total:
            progress_percent = round(downloaded / total * 100, 1)
            if downloaded >= total and 100 not in milestones_hit:
                milestones_hit.append(100)
        else:
            # No Content-Length header — report 100% on completion
            progress_percent = 100.0
            milestones_hit = [100]

        print(json.dumps({
            "success": True,
            "data": {
                "url": url,
                "saved_to": str(dest.resolve()),
                "bytes_downloaded": downloaded,
                "total_bytes": total,
                "progress_percent": progress_percent,
                "progress_milestones": milestones_hit,
            },
        }))

    except requests.exceptions.HTTPError as exc:
        print(json.dumps({"success": False, "error": f"HTTP {exc.response.status_code}: {exc.response.reason}"}))
        sys.exit(1)
    except requests.exceptions.ConnectionError as exc:
        print(json.dumps({"success": False, "error": f"Connection failed: {exc}"}))
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(json.dumps({"success": False, "error": "Request timed out"}))
        sys.exit(1)
    except OSError as exc:
        print(json.dumps({"success": False, "error": f"File write error: {exc}"}))
        sys.exit(1)
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
