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
def youtube_download(url: str, retries: int = 3, timeout: int = 30, video_format: str = "bestvideo+bestaudio/best", audio_format: str = "", merge_format: str = "") -> dict:
    """Download a YouTube video (or audio-only) to the user's Downloads folder.

    Args:
        url: Full YouTube video URL (watch?v=... or playlist link).
        retries: Number of download retries on transient errors (default 3).
        timeout: Socket timeout in seconds for each network operation (default 30).
        video_format: yt-dlp format string, e.g. 'best[ext=mp4]' or 'bestvideo+bestaudio/best' (default).
        audio_format: When set, downloads audio only and converts to this format (e.g. 'mp3', 'm4a', 'opus'). Requires ffmpeg.
        merge_format: Output container format for remuxing, e.g. 'mkv', 'avi', 'mp4'. Requires ffmpeg. Overrides the container of the merged output.
    """
    return run_python(
        "tools/python/youtube_download.py",
        [url, str(retries), str(timeout), video_format, audio_format, merge_format],
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
def record_audio(
    output_path: str,
    max_seconds: float = 15.0,
    silence_duration: float = 1.5,
) -> dict:
    """Record audio from the default microphone, stopping automatically when silence is detected.

    Args:
        output_path: Absolute or relative path where the WAV file will be saved.
        max_seconds: Hard safety limit in seconds, 1–120 (default 15). Recording always stops by this time.
        silence_duration: Consecutive seconds of quiet after speech that triggers stop (default 1.5).
                          Thresholds are auto-calibrated from ambient noise — no manual tuning needed.

    The file is saved at 16 kHz mono PCM — the native format for Groq STT (groq_stt tool).
    """
    return run_python(
        "tools/python/record_audio.py",
        [output_path, str(max_seconds), str(silence_duration)],
        timeout=int(max_seconds) + 15,
    )


@mcp.tool()
def play_audio(audio_path: str) -> dict:
    """Play an audio file (MP3, WAV, OGG, FLAC) through the system speakers without opening a media player window.
    Blocks until playback is complete, then returns.

    Args:
        audio_path: Absolute or relative path to the audio file to play.
    """
    return run_python("tools/python/play_audio.py", [audio_path], timeout=600)


@mcp.tool()
def telegram_download(
    channel: str,
    output_dir: str = "",
    limit: int = 50,
    min_id: int = 0,
    max_id: int = 0,
) -> dict:
    """Download audio files (MP3, OGG, voice messages) from a Telegram channel.

    Args:
        channel: Channel username (e.g. '@mychannel') or numeric channel ID.
        output_dir: Directory to save files. Defaults to ~/Downloads/telegram.
        limit: Maximum number of messages to scan (default 50). Increase to fetch deeper history.
        min_id: Only fetch messages with ID greater than this (use for incremental runs).
        max_id: Only fetch messages with ID less than this (caps upper bound; use to target a year range).

    Requires a valid Telethon session at tools/python/tele_session.session.
    """
    import json as _json
    stdin = _json.dumps({
        "channel": channel,
        "output_dir": output_dir,
        "limit": limit,
        "min_id": min_id,
        "max_id": max_id,
    })
    return run_python("tools/python/telegram_download.py", stdin_data=stdin, timeout=300)


@mcp.tool()
def telegram_download_by_ids(
    channel: str,
    message_ids: list,
    output_dir: str = "",
) -> dict:
    """Download specific audio messages from a Telegram channel by message ID.

    Fetches only the listed messages in a single round-trip using Telethon's
    get_messages(ids=[...]) — no history scan required.

    Args:
        channel: Channel username (e.g. '@mychannel') or numeric channel ID.
        message_ids: List of Telegram message IDs to download (integers).
        output_dir: Directory to save files. Defaults to ~/Downloads/telegram.

    Requires a valid Telethon session at tools/python/tele_session.session.
    """
    import json as _json
    stdin = _json.dumps({
        "channel": channel,
        "message_ids": message_ids,
        "output_dir": output_dir,
    })
    return run_python("tools/python/telegram_download_by_ids.py", stdin_data=stdin, timeout=7200)


@mcp.tool()
def telegram_search(
    query: str,
    channel: str = "",
    media_type: str = "any",
    limit: int = 50,
) -> dict:
    """Search for audio or video files across Telegram using Telegram's own search engine.

    Works globally (like the Telegram app's search bar) or within a specific channel.
    Returns metadata + message IDs for each match. Does NOT download files — use
    telegram_download_by_ids with the returned message_ids to get the actual files.

    Args:
        query: Search string matched by Telegram's server-side engine (filenames, titles, artists).
        channel: Channel username (e.g. '@mychannel') or numeric ID. Leave empty for global search.
        media_type: Filter to 'audio', 'video', or 'any' (default). Use 'video' for films.
        limit: Maximum results per media-type pass (default 50).

    Requires a valid Telethon session at tools/python/tele_session.session.
    """
    import json as _json
    stdin = _json.dumps({
        "query": query,
        "channel": channel,
        "media_type": media_type,
        "limit": limit,
    })
    return run_python("tools/python/telegram_search.py", stdin_data=stdin, timeout=300)


def telegram_bot_interact(
    bot_username: str,
    text: str = "",
    click_button_index: int = -1,
    output_dir: str = "",
    wait_seconds: int = 8,
) -> dict:
    """Send a text message or click an inline button on a Telegram bot, then return its response.

    Bot-only — rejects channels and groups at the Telethon entity level.
    Any file the bot sends is downloaded automatically to output_dir.
    Requires TELEGRAM_WRITE_ENABLED=true in .env.

    Args:
        bot_username: Bot @username (e.g. '@FlintFilesBot').
        text: Message text to send (e.g. '/start TOKEN'). Use this OR click_button_index.
        click_button_index: Flat index (0-based, row-major) of the inline button to click
                            in the bot's most recent reply. Use -1 (default) to send text instead.
        output_dir: Directory to save any files the bot replies with. Defaults to ~/Downloads/telegram.
        wait_seconds: Seconds to wait for the bot to reply after sending (default 8).

    Requires a valid Telethon session at tools/python/tele_session.session.
    """
    import json as _json
    stdin = _json.dumps({
        "bot_username": bot_username,
        "text": text,
        "click_button_index": click_button_index,
        "output_dir": output_dir,
        "wait_seconds": wait_seconds,
    })
    return run_python("tools/python/telegram_bot_interact.py", stdin_data=stdin, timeout=120)

@mcp.tool()
def telegram_join_channel(invite_link: str) -> dict:
    """Join a Telegram channel or group via @username or a private invite link.

    Accepts:
      @username               — public channel / group
      https://t.me/+HASH      — private invite link
      https://t.me/joinchat/HASH — private invite link (legacy format)

    Requires TELEGRAM_WRITE_ENABLED=true in .env.

    Args:
        invite_link: Channel @username or full t.me invite URL.

    Requires a valid Telethon session at tools/python/tele_session.session.
    """
    import json as _json
    stdin = _json.dumps({"invite_link": invite_link})
    return run_python("tools/python/telegram_join_channel.py", stdin_data=stdin, timeout=60)


@mcp.tool()
def telegram_forward_message(from_chat: str, message_ids: list, to_chat: str) -> dict:
    """Forward specific messages from one Telegram chat to another.

    Use this to preserve bot files before the bot auto-deletes them.

    Args:
        from_chat: Source chat @username, numeric ID, or bot @username.
        message_ids: List of message IDs to forward (integers).
        to_chat: Destination chat @username or numeric ID.

    Requires TELEGRAM_WRITE_ENABLED=true.
    Requires a valid Telethon session at tools/python/tele_session.session.
    """
    import json as _json
    stdin = _json.dumps({"from_chat": from_chat, "message_ids": message_ids, "to_chat": to_chat})
    return run_python("tools/python/telegram_forward_message.py", stdin_data=stdin, timeout=60)


@mcp.tool()
def telegram_leave_channel(channel: str) -> dict:
    """Leave / unsubscribe from a Telegram channel or group.

    Accepts @username, t.me/username, or t.me/+HASH private invite links.

    Args:
        channel: Channel @username, full t.me URL, or private invite link to leave.

    Requires TELEGRAM_WRITE_ENABLED=true.
    Requires a valid Telethon session at tools/python/tele_session.session.
    """
    import json as _json
    stdin = _json.dumps({"channel": channel})
    return run_python("tools/python/telegram_leave_channel.py", stdin_data=stdin, timeout=60)


@mcp.tool()
def telegram_delete_messages(chat: str, message_ids: list) -> dict:
    """Delete specific messages from a Telegram chat.

    You must be the sender of the messages or an admin of the chat.

    Args:
        chat: Chat @username or numeric ID where the messages live.
        message_ids: List of message IDs to delete (integers).

    Requires TELEGRAM_WRITE_ENABLED=true.
    Requires a valid Telethon session at tools/python/tele_session.session.
    """
    import json as _json
    stdin = _json.dumps({"chat": chat, "message_ids": message_ids})
    return run_python("tools/python/telegram_delete_messages.py", stdin_data=stdin, timeout=30)



@mcp.tool()
def chroma_list_collections() -> dict:
    """List all collections in the ChromaDB instance.

    Requires env vars: CHROMA_HOST (default 127.0.0.1), CHROMA_PORT (default 8001).
    """
    return run_python("tools/python/chroma_list_collections.py", timeout=15)


@mcp.tool()
def chroma_query(
    collection: str,
    query_text: str,
    n_results: int = 5,
    where: str = "",
) -> dict:
    """Semantic search in a ChromaDB collection using local sentence-transformers embeddings.

    Args:
        collection: Name of the ChromaDB collection to search.
        query_text: Natural-language query string to embed and search.
        n_results: Number of nearest neighbours to return (default 5).
        where: Optional JSON object string with ChromaDB metadata filter, e.g. '{"category": "news"}'.

    Requires env vars: CHROMA_HOST, CHROMA_PORT, CHROMA_EMBEDDING_MODEL (default all-MiniLM-L6-v2).
    """
    import json as _json
    payload = {"collection": collection, "query_text": query_text, "n_results": n_results}
    if where:
        try:
            payload["where"] = _json.loads(where)
        except _json.JSONDecodeError:
            return {"success": False, "error": "where must be valid JSON"}
    return run_python("tools/python/chroma_query.py", stdin_data=_json.dumps(payload), timeout=60)


@mcp.tool()
def chroma_add_document(
    collection: str,
    documents: str,
    ids: str,
    metadatas: str = "",
    create_if_missing: bool = True,
) -> dict:
    """Upsert one or more documents into a ChromaDB collection.

    Args:
        collection: Name of the ChromaDB collection.
        documents: JSON array of document strings, e.g. '["text one", "text two"]'.
        ids: JSON array of unique IDs matching documents, e.g. '["id1", "id2"]'.
        metadatas: Optional JSON array of metadata dicts, e.g. '[{"source": "web"}]'.
        create_if_missing: Create the collection if it does not exist (default true).

    Requires env vars: CHROMA_HOST, CHROMA_PORT, CHROMA_EMBEDDING_MODEL.
    """
    import json as _json
    try:
        docs = _json.loads(documents)
        doc_ids = _json.loads(ids)
    except _json.JSONDecodeError as exc:
        return {"success": False, "error": f"Invalid JSON in documents or ids: {exc}"}

    payload = {
        "collection": collection,
        "documents": docs,
        "ids": doc_ids,
        "create_if_missing": create_if_missing,
    }
    if metadatas:
        try:
            payload["metadatas"] = _json.loads(metadatas)
        except _json.JSONDecodeError:
            return {"success": False, "error": "metadatas must be a valid JSON array"}

    return run_python("tools/python/chroma_add_document.py", stdin_data=_json.dumps(payload), timeout=60)


@mcp.tool()
def chroma_get_document(collection: str, ids: str) -> dict:
    """Fetch documents from a ChromaDB collection by their IDs.

    Args:
        collection: Name of the ChromaDB collection.
        ids: JSON array of document IDs to retrieve, e.g. '["id1", "id2"]'.

    Requires env vars: CHROMA_HOST, CHROMA_PORT.
    """
    import json as _json
    try:
        doc_ids = _json.loads(ids)
    except _json.JSONDecodeError as exc:
        return {"success": False, "error": f"Invalid JSON in ids: {exc}"}

    payload = {"collection": collection, "ids": doc_ids}
    return run_python("tools/python/chroma_get_document.py", stdin_data=_json.dumps(payload), timeout=30)


@mcp.tool()
def bluetooth_enable(state: str) -> dict:
    """Enable or disable the system Bluetooth radio.

    Args:
        state: 'enable' to turn Bluetooth on, 'disable' to turn it off.
    """
    return run_powershell("tools/powershell/bluetooth_enable.ps1", [state], timeout=15)


@mcp.tool()
def bluetooth_scan(timeout_seconds: int = 10) -> dict:
    """Scan for nearby and paired Bluetooth devices (Classic and BLE).

    Args:
        timeout_seconds: How long to scan in seconds, 3–60 (default 10).
    """
    return run_powershell("tools/powershell/bluetooth_scan.ps1", [str(timeout_seconds)], timeout=timeout_seconds + 15)


@mcp.tool()
def bluetooth_connect(name: str) -> dict:
    """Connect to a paired Bluetooth device by name (full or partial match).

    Uses Win32 BluetoothSetServiceState to enable Bluetooth services on the
    device, triggering a persistent connection. The device must already be
    paired with this PC and within Bluetooth range.

    Args:
        name: Full or partial device name, e.g. 'WH-1000XM4' or 'AirPods'.
    """
    return run_powershell("tools/powershell/bluetooth_connect.ps1", [name], timeout=30)


@mcp.tool()
def bluetooth_disconnect(name: str) -> dict:
    """Disconnect a Bluetooth device by name (full or partial match).

    Uses Win32 BluetoothSetServiceState to disable Bluetooth services on the
    device, dropping the connection cleanly without leaving driver errors.

    Args:
        name: Full or partial device name, e.g. 'WH-1000XM4' or 'AirPods'.
    """
    return run_powershell("tools/powershell/bluetooth_disconnect.ps1", [name], timeout=15)


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
