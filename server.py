import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from mcp.server.fastmcp import FastMCP

from shared.logging_config import setup_logging
from shared.powershell_runner import run_powershell
from shared.python_runner import run_python
from shared.node_runner import run_node
from shared.java_runner import run_java

setup_logging()
logger = logging.getLogger(__name__)

mcp = FastMCP("multi-lang-mcp")


@mcp.tool()
def windows_services(filter_name: str = "") -> dict:
    """List Windows services, optionally filtered by name."""
    args = [filter_name] if filter_name else []
    return run_powershell("tools/powershell/services.ps1", args)


@mcp.tool()
def read_file(path: str) -> dict:
    """Read a file from disk and return its contents."""
    return run_python("tools/python/read_file.py", [path])


@mcp.tool()
def npm_package_info(package_name: str) -> dict:
    """Fetch metadata about an npm package."""
    return run_node("tools/node/npm_info.js", [package_name])


@mcp.tool()
def java_tool(input_json: str = "{}") -> dict:
    """Run the Java ToolRunner with optional JSON input."""
    return run_java("tools/java/build/ToolRunner.jar", stdin_data=input_json)


@mcp.tool()
def download_file(url: str, save_path: str) -> dict:
    """Download a file from a URL and save it to disk. Returns progress milestones and final percentage."""
    return run_python("tools/python/download_file.py", [url, save_path], timeout=300)


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web using DuckDuckGo and return the top results.

    Args:
        query: The search query string.
        max_results: Number of results to return, between 1 and 20 (default 5).
    """
    return run_python("tools/python/web_search.py", [query, str(max_results)], timeout=60)


@mcp.tool()
def youtube_download(url: str, retries: int = 3, timeout: int = 30, video_format: str = "bestvideo+bestaudio/best", audio_format: str = "") -> dict:
    """Download a YouTube video (or audio-only) to the user's Downloads folder.

    Args:
        url: Full YouTube video URL (watch?v=... or playlist link).
        retries: Number of download retries on transient errors (default 3).
        timeout: Socket timeout in seconds for each network operation (default 30).
        video_format: yt-dlp format string, e.g. 'best[ext=mp4]' or 'bestvideo+bestaudio/best' (default).
        audio_format: When set, downloads audio only and converts to this format (e.g. 'mp3', 'm4a', 'opus'). Requires ffmpeg.
    """
    return run_python(
        "tools/python/youtube_download.py",
        [url, str(retries), str(timeout), video_format, audio_format],
        timeout=600,
    )


@mcp.tool()
def get_clean_webpage(url: str, timeout: int = 15, max_chars: int = 10000) -> dict:
    """Fetch a webpage and return its content as cleaned plain text with all HTML, JS, and boilerplate removed.

    Args:
        url: The full URL of the webpage to fetch.
        timeout: HTTP request timeout in seconds, between 1 and 120 (default 15).
        max_chars: Maximum characters to return; 0 means unlimited (default 10000).
    """
    return run_python(
        "tools/python/get_clean_webpage.py",
        [url, str(timeout), str(max_chars)],
        timeout=timeout + 5,
    )


@mcp.tool()
def google_tts(
    text: str,
    output_path: str,
    voice: str = "en-US-Neural2-A",
    language_code: str = "en-US",
    audio_encoding: str = "MP3",
) -> dict:
    """Convert text (or SSML) to speech using Google Cloud TTS and save it to a file.

    Args:
        text: Plain text or SSML (wrap in <speak>...</speak>) to synthesize.
        output_path: Absolute or relative path where the audio file will be saved.
        voice: Google Cloud TTS voice name, e.g. 'en-US-Neural2-A' or 'de-DE-Neural2-F'.
        language_code: BCP-47 language code, e.g. 'en-US' or 'de-DE'.
        audio_encoding: Output audio format — one of MP3, LINEAR16, OGG_OPUS, MULAW, ALAW (default MP3).

    Requires env vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN.
    """
    import json as _json
    stdin = _json.dumps({
        "text": text,
        "output_path": output_path,
        "voice": voice,
        "language_code": language_code,
        "audio_encoding": audio_encoding,
    })
    return run_python("tools/python/google_tts.py", stdin_data=stdin, timeout=60)


@mcp.tool()
def groq_stt(
    audio_path: str,
    language_code: str = "en",
    model: str = "whisper-large-v3-turbo",
) -> dict:
    """Transcribe a local audio file to text using Groq's Whisper API.

    Args:
        audio_path: Absolute or relative path to the audio file (MP3, MP4, WAV, WEBM, OGG, FLAC, M4A). Max 25 MB.
        language_code: ISO-639-1 language code of the spoken language, e.g. 'en' or 'de' (default en).
        model: Groq Whisper model — 'whisper-large-v3-turbo' (default, fastest) or 'whisper-large-v3'.

    Requires env var: GROQ_API_KEY.
    """
    return run_python("tools/python/groq_stt.py", [audio_path, language_code, model], timeout=120)


@mcp.tool()
def record_audio(output_path: str, duration: int = 5) -> dict:
    """Record audio from the default microphone and save it as a WAV file.
    Blocks for the full duration, then returns the saved file path.

    Args:
        output_path: Absolute or relative path where the WAV file will be saved.
        duration: Recording length in seconds, 1–120 (default 5).

    The file is saved at 16 kHz mono PCM — the native format for Groq STT (groq_stt tool).
    """
    return run_python("tools/python/record_audio.py", [output_path, str(duration)], timeout=duration + 15)


@mcp.tool()
def play_audio(audio_path: str) -> dict:
    """Play an audio file (MP3, WAV, OGG, FLAC) through the system speakers without opening a media player window.
    Blocks until playback is complete, then returns.

    Args:
        audio_path: Absolute or relative path to the audio file to play.
    """
    return run_python("tools/python/play_audio.py", [audio_path], timeout=600)


@mcp.tool()
def google_refresh_token() -> dict:
    """Refresh the Google OAuth2 access token using the stored refresh token.

    Calls Google's token endpoint with GOOGLE_REFRESH_TOKEN and writes the new
    GOOGLE_ACCESS_TOKEN back into the .env file automatically.
    No arguments needed — reads all credentials from the environment.

    Requires env vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN.
    """
    return run_python("tools/python/google_refresh_token.py", timeout=30)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-language MCP server")
    p.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport type (default: stdio; use sse/streamable-http for service mode)",
    )
    p.add_argument("--host", default="127.0.0.1", help="Bind host for SSE/HTTP (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8080, help="Bind port for SSE/HTTP (default: 8080)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    logger.info("MCP server starting (transport=%s, host=%s, port=%s)", args.transport, args.host, args.port)
    mcp.run(transport=args.transport)
