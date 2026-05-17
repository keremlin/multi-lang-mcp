import sys
import json
import re


def fetch_and_clean(url: str, timeout: int = 15, max_chars: int = 10000) -> dict:
    try:
        import requests
    except ImportError:
        return {"success": False, "error": "requests not installed"}

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {"success": False, "error": "beautifulsoup4 not installed — run: pip install beautifulsoup4"}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Request timed out after {timeout}s"}
    except requests.exceptions.ConnectionError as exc:
        return {"success": False, "error": f"Connection error: {exc}"}
    except requests.exceptions.HTTPError as exc:
        return {"success": False, "error": f"HTTP {response.status_code}: {exc}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    soup = BeautifulSoup(response.text, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    for tag in soup(["head", "script", "style", "nav", "footer", "header",
                     "aside", "noscript", "iframe", "form", "button", "input"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = text.strip()

    truncated = False
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return {
        "success": True,
        "data": {
            "url": url,
            "title": title,
            "char_count": len(text),
            "truncated": truncated,
            "text": text,
        },
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: get_clean_webpage.py <url> [timeout=15] [max_chars=10000]",
        }))
        sys.exit(1)

    url = sys.argv[1]

    try:
        timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        if timeout < 1 or timeout > 120:
            raise ValueError("timeout must be between 1 and 120")
    except ValueError as exc:
        print(json.dumps({"success": False, "error": f"Invalid timeout: {exc}"}))
        sys.exit(1)

    try:
        max_chars = int(sys.argv[3]) if len(sys.argv) > 3 else 10000
        if max_chars < 0:
            raise ValueError("max_chars must be >= 0")
    except ValueError as exc:
        print(json.dumps({"success": False, "error": f"Invalid max_chars: {exc}"}))
        sys.exit(1)

    result = fetch_and_clean(url, timeout=timeout, max_chars=max_chars)
    print(json.dumps(result))
    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
