import argparse
import functools
import inspect
import logging
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from mcp.server.fastmcp import FastMCP

from shared.logging_config import setup_logging
from shared.activity_log import log_call, log_done
from shared.powershell_runner import run_powershell
from shared.python_runner import run_python
from shared.node_runner import run_node
from shared.java_runner import run_java

setup_logging()
logger = logging.getLogger(__name__)

mcp = FastMCP("multi-lang-mcp")


def mcp_tool():
    """Drop-in for @mcp.tool() that also writes to logs/activity.log."""
    def outer(func):
        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            inputs = dict(bound.arguments)
            log_call(func.__name__, inputs)
            start = time.perf_counter()
            result = func(*args, **kwargs)
            log_done(func.__name__, result, time.perf_counter() - start)
            return result

        wrapper.__signature__ = sig
        return mcp.tool()(wrapper)
    return outer


@mcp_tool()
def windows_services(filter_name: str = "") -> dict:
    """List Windows services, optionally filtered by name."""
    args = [filter_name] if filter_name else []
    return run_powershell("tools/powershell/services.ps1", args)


@mcp_tool()
def read_file(path: str) -> dict:
    """Read a file from disk and return its contents."""
    return run_python("tools/python/read_file.py", [path])


@mcp_tool()
def npm_package_info(package_name: str) -> dict:
    """Fetch metadata about an npm package."""
    return run_node("tools/node/npm_info.js", [package_name])


@mcp_tool()
def java_tool(input_json: str = "{}") -> dict:
    """Run the Java ToolRunner with optional JSON input."""
    return run_java("tools/java/build/ToolRunner.jar", stdin_data=input_json)


@mcp_tool()
def download_file(url: str, save_path: str) -> dict:
    """Download a file from a URL and save it to disk. Returns progress milestones and final percentage."""
    return run_python("tools/python/download_file.py", [url, save_path], timeout=300)


@mcp_tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web using DuckDuckGo and return the top results.

    Args:
        query: The search query string.
        max_results: Number of results to return, between 1 and 20 (default 5).
    """
    return run_python("tools/python/web_search.py", [query, str(max_results)], timeout=60)


@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
def play_audio(audio_path: str) -> dict:
    """Play an audio file (MP3, WAV, OGG, FLAC) through the system speakers without opening a media player window.
    Blocks until playback is complete, then returns.

    Args:
        audio_path: Absolute or relative path to the audio file to play.
    """
    return run_python("tools/python/play_audio.py", [audio_path], timeout=600)


@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
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

@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
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



@mcp_tool()
def chroma_list_collections() -> dict:
    """List all collections in the ChromaDB instance.

    Requires env vars: CHROMA_HOST (default 127.0.0.1), CHROMA_PORT (default 8001).
    """
    return run_python("tools/python/chroma_list_collections.py", timeout=15)


@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
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


@mcp_tool()
def bluetooth_enable(state: str) -> dict:
    """Enable or disable the system Bluetooth radio.

    Args:
        state: 'enable' to turn Bluetooth on, 'disable' to turn it off.
    """
    return run_powershell("tools/powershell/bluetooth_enable.ps1", [state], timeout=15)


@mcp_tool()
def bluetooth_scan(timeout_seconds: int = 10) -> dict:
    """Scan for nearby and paired Bluetooth devices (Classic and BLE).

    Args:
        timeout_seconds: How long to scan in seconds, 3–60 (default 10).
    """
    return run_powershell("tools/powershell/bluetooth_scan.ps1", [str(timeout_seconds)], timeout=timeout_seconds + 15)


@mcp_tool()
def bluetooth_connect(name: str) -> dict:
    """Connect to a paired Bluetooth device by name (full or partial match).

    Uses Win32 BluetoothSetServiceState to enable Bluetooth services on the
    device, triggering a persistent connection. The device must already be
    paired with this PC and within Bluetooth range.

    Args:
        name: Full or partial device name, e.g. 'WH-1000XM4' or 'AirPods'.
    """
    return run_powershell("tools/powershell/bluetooth_connect.ps1", [name], timeout=30)


@mcp_tool()
def bluetooth_disconnect(name: str) -> dict:
    """Disconnect a Bluetooth device by name (full or partial match).

    Uses Win32 BluetoothSetServiceState to disable Bluetooth services on the
    device, dropping the connection cleanly without leaving driver errors.

    Args:
        name: Full or partial device name, e.g. 'WH-1000XM4' or 'AirPods'.
    """
    return run_powershell("tools/powershell/bluetooth_disconnect.ps1", [name], timeout=15)


@mcp_tool()
def youtube_downloader_lg(
    url: str,
    crf: int = 23,
    preset: str = "medium",
    retries: int = 3,
    timeout: int = 30,
) -> dict:
    """Download a YouTube video and encode it directly to LG TV-compatible MP4 in one step.

    Uses yt-dlp's native FFmpegVideoConvertor post-processor — no separate conversion needed.
    Output: H.264 video, AAC audio, MP4 container, max 1920×1080, movflags +faststart.

    Args:
        url: Full YouTube video URL (watch?v=... or playlist link).
        crf: H.264 quality — 0=lossless, 51=worst, 23=default. Lower = better quality, larger file.
        preset: x264 speed/compression preset (ultrafast … veryslow). Default: medium.
        retries: Download retries on transient errors (default 3).
        timeout: Socket timeout in seconds per network operation (default 30).

    Requires: yt-dlp, ffmpeg binary in PATH.
    """
    import json as _json
    stdin = _json.dumps({
        "url": url,
        "crf": crf,
        "preset": preset,
        "retries": retries,
        "timeout": timeout,
    })
    return run_python("tools/python/youtube_downloader_lg.py", stdin_data=stdin, timeout=7200)


@mcp_tool()
def video_converter_lg(
    input_path: str,
    output_path: str = "",
    crf: int = 23,
    preset: str = "medium",
) -> dict:
    """Convert a video file to LG TV-compatible format (H.264 MP4, AAC audio, max 1920×1080 @ 30 fps).

    Optimised for LG 43LH5410 and similar 2015 LG Full HD TVs.
    Scales down to 1920×1080 if the source is larger; preserves original resolution otherwise.
    Frame rate is capped at 30 fps only when the source exceeds it.

    Args:
        input_path: Absolute path to the source video file (MKV, AVI, MOV, WEBM, etc.).
        output_path: Destination MP4 path. Defaults to <input_stem>_lg.mp4 in the same folder.
        crf: H.264 quality — 0=lossless, 51=worst, 23=default. Lower means better quality and larger file.
        preset: x264 speed/compression preset: ultrafast, superfast, veryfast, faster, fast,
                medium (default), slow, slower, veryslow. Slower = smaller file.

    Requires: ffmpeg-python (pip install ffmpeg-python) and ffmpeg binary in PATH.
    """
    import json as _json
    stdin = _json.dumps({
        "input_path": input_path,
        "output_path": output_path,
        "crf": crf,
        "preset": preset,
    })
    return run_python("tools/python/video_converter_lg.py", stdin_data=stdin, timeout=3600)


@mcp_tool()
def google_refresh_token() -> dict:
    """Refresh the Google OAuth2 access token using the stored refresh token.

    Calls Google's token endpoint with GOOGLE_REFRESH_TOKEN and writes the new
    GOOGLE_ACCESS_TOKEN back into the .env file automatically.
    No arguments needed — reads all credentials from the environment.

    Requires env vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN.
    """
    return run_python("tools/python/google_refresh_token.py", timeout=30)


@mcp_tool()
def activity_log_query(
    date: str = "",
    tool: str = "",
    status: str = "",
    search: str = "",
    tail: int = 0,
    summary: bool = False,
) -> dict:
    """Query the MCP activity log — who called what, when, and with what result.

    All parameters are optional and combinable.

    Args:
        date: Date filter — "today", "yesterday", "YYYY-MM-DD", or a range
              "YYYY-MM-DD/YYYY-MM-DD". Leave empty for all dates.
        tool: Partial tool name filter, case-insensitive (e.g. "telegram" matches
              telegram_download, telegram_search, etc.).
        status: "ok" for successful calls, "fail" for errors, "incomplete" for
                calls with no matching DONE line. Leave empty for all.
        search: Free-text substring searched in inputs and output (case-insensitive).
        tail: Return only the last N entries after all other filters (0 = unlimited).
        summary: When true, return per-tool counts (total/ok/fail/avg_duration_ms)
                 instead of individual entries — useful for a quick usage overview.
    """
    import json as _json
    stdin = _json.dumps({
        "date": date,
        "tool": tool,
        "status": status,
        "search": search,
        "tail": tail,
        "summary": summary,
    })
    return run_python("tools/python/activity_log_query.py", stdin_data=stdin, timeout=15)


@mcp_tool()
def WC_team_stats(
    team: str,
    league: str = "INT-World Cup",
    season: str = "2026",
    n_recent: int = 10,
) -> dict:
    """Fetch a national team's recent form, goal stats, and match results from FBref.

    Args:
        team: Team name as it appears in FBref (e.g. 'Argentina', 'Germany').
        league: soccerdata league string (default 'INT-World Cup').
        season: Season year string (default '2026').
        n_recent: Number of recent completed matches to analyse (default 10).

    Returns win rate, form string, avg goals scored/conceded, clean sheets, recent results.
    """
    import json as _json
    stdin = _json.dumps({"team": team, "league": league, "season": season, "n_recent": n_recent})
    return run_python("tools/python/wc_team_stats.py", stdin_data=stdin, timeout=120)


@mcp_tool()
def WC_elo_rating(
    team: str = "",
    top_n: int = 30,
    source: str = "elo",
    timeout: int = 20,
) -> dict:
    """Fetch national team Elo ratings from eloratings.net or club Elo from clubelo.com.

    Args:
        team: Team name to look up (e.g. 'Argentina'). Leave empty to get the top-N list.
        top_n: Number of top teams to return when team is empty (default 30).
        source: 'elo' (default, national team eloratings.net) or 'clubelo' (club teams via soccerdata).
        timeout: HTTP request timeout in seconds (default 20).

    Returns Elo rating, rank, and source information.
    """
    import json as _json
    stdin = _json.dumps({"team": team, "top_n": top_n, "source": source, "timeout": timeout})
    return run_python("tools/python/wc_elo_rating.py", stdin_data=stdin, timeout=30)


@mcp_tool()
def WC_head_to_head(
    team_a: str,
    team_b: str,
    league: str = "INT-World Cup",
    season: str = "2026",
    n_matches: int = 20,
) -> dict:
    """Fetch historical head-to-head match records between two teams from FBref.

    Args:
        team_a: First team name (e.g. 'Argentina').
        team_b: Second team name (e.g. 'Germany').
        league: FBref league string (default 'INT-World Cup').
        season: Season year string; leave empty for all seasons.
        n_matches: Maximum number of recent H2H matches to return (default 20).

    Returns win/draw/loss counts, avg goals, and per-match details.
    """
    import json as _json
    stdin = _json.dumps({"team_a": team_a, "team_b": team_b, "league": league, "season": season, "n_matches": n_matches})
    return run_python("tools/python/wc_head_to_head.py", stdin_data=stdin, timeout=120)


@mcp_tool()
def WC_predict_outcome(
    team_a: str,
    team_b: str,
    elo_a: float,
    elo_b: float,
    form_a: str = "",
    form_b: str = "",
    avg_gf_a: float = 0.0,
    avg_ga_a: float = 0.0,
    avg_gf_b: float = 0.0,
    avg_ga_b: float = 0.0,
    home_advantage: float = 0.0,
) -> dict:
    """Predict win/draw/loss probabilities using Elo ratings, recent form, and goals model.

    Args:
        team_a: Team A label.
        team_b: Team B label.
        elo_a: Team A Elo rating (e.g. 2050).
        elo_b: Team B Elo rating (e.g. 1980).
        form_a: Recent form string for A, newest last (e.g. 'WWDWL').
        form_b: Recent form string for B, newest last (e.g. 'WLWDW').
        avg_gf_a: Team A average goals scored per game (enables goals model).
        avg_ga_a: Team A average goals conceded per game.
        avg_gf_b: Team B average goals scored per game.
        avg_ga_b: Team B average goals conceded per game.
        home_advantage: Extra Elo points for team A if playing at home (default 0 = neutral).

    Returns Elo, form-adjusted, and final blended win/draw/loss percentages.
    """
    import json as _json
    payload = {
        "team_a": team_a, "team_b": team_b,
        "elo_a": elo_a, "elo_b": elo_b,
        "form_a": form_a, "form_b": form_b,
        "home_advantage": home_advantage,
    }
    if avg_gf_a > 0:
        payload.update({"avg_gf_a": avg_gf_a, "avg_ga_a": avg_ga_a, "avg_gf_b": avg_gf_b, "avg_ga_b": avg_ga_b})
    return run_python("tools/python/wc_predict_outcome.py", stdin_data=_json.dumps(payload), timeout=15)


@mcp_tool()
def WC_predict_score(
    lambda_a: float,
    lambda_b: float,
    team_a: str = "Team A",
    team_b: str = "Team B",
    max_goals: int = 8,
    top_n: int = 12,
) -> dict:
    """Predict exact-score probabilities using Poisson regression with Dixon-Coles correction.

    Args:
        lambda_a: Expected goals for team A (e.g. 1.8). Use WC_predict_outcome to derive these.
        lambda_b: Expected goals for team B (e.g. 1.2).
        team_a: Label for team A.
        team_b: Label for team B.
        max_goals: Maximum goals per team to model (default 8).
        top_n: Number of top score lines to return (default 12).

    Returns top-N most likely scores, over/under 2.5, BTTS, and outcome percentages.
    """
    import json as _json
    stdin = _json.dumps({
        "lambda_a": lambda_a, "lambda_b": lambda_b,
        "team_a": team_a, "team_b": team_b,
        "max_goals": max_goals, "top_n": top_n,
    })
    return run_python("tools/python/wc_predict_score.py", stdin_data=stdin, timeout=15)


@mcp_tool()
def WC_schedule(
    date: str = "today",
    league: str = "INT-World Cup",
    season: str = "2026",
    source: str = "auto",
    all_matches: bool = False,
) -> dict:
    """Fetch World Cup fixtures and results for a given date.

    Reads from Supabase DB (fast, <1s). Falls back to soccerdata scraping if DB is empty.
    Run WC_db_sync first to populate the DB.

    Args:
        date: "today" (default), "YYYY-MM-DD", or any date string.
        league: soccerdata league string used for scrape fallback (default 'INT-World Cup').
        season: Season year (default '2026').
        source: 'auto' (default, DB first), 'db' (DB only), or 'scrape' (force scraping).
        all_matches: Return the full season schedule instead of a single date (default false).

    Returns each match with home/away teams, kickoff time, venue, group,
    and score + status (finished/upcoming) for completed games.
    """
    import json as _json
    stdin = _json.dumps({
        "date": date,
        "league": league,
        "season": season,
        "source": source,
        "all": all_matches,
    })
    return run_python("tools/python/wc_schedule.py", stdin_data=stdin, timeout=30)


@mcp_tool()
def WC_db_sync(
    source: str = "auto",
    force: bool = False,
) -> dict:
    """Seed or refresh the Supabase wc_matches table from a football data API.

    Run this once before using WC_schedule to populate the DB with all WC 2026 fixtures.
    Subsequent WC_schedule calls will be instant (reads from DB, no scraping).

    Args:
        source: 'auto' (default), 'football-data' (needs FOOTBALL_DATA_API_KEY in .env),
                or 'thesportsdb' (free, no key needed).
        force: Re-sync even if data already exists in the DB (default false).
    """
    import json as _json
    stdin = _json.dumps({"source": source, "force": force})
    return run_python("tools/python/wc_db_sync.py", stdin_data=stdin, timeout=60)


@mcp_tool()
def WC_match_info_ui(
    team_a: str,
    team_b: str,
    elo_a: float = 0,
    elo_b: float = 0,
    home_advantage: float = 0,
) -> dict:
    """Open a maximized match prediction window for two World Cup teams.

    Fetches team data from Supabase, runs prediction models, then launches
    a full-screen dark-theme UI showing team stats, win probabilities,
    expected goals, top scores, and betting markets. Returns instantly.

    Args:
        team_a: First team (e.g. 'Brazil'). Use exact name from WC_schedule.
        team_b: Second team (e.g. 'United States').
        elo_a: Override Elo for team A (0 = use DB value).
        elo_b: Override Elo for team B (0 = use DB value).
        home_advantage: Elo bonus for team A if playing at home (default 0).
    """
    import json as _json
    stdin = _json.dumps({
        "team_a": team_a, "team_b": team_b,
        "elo_a": elo_a, "elo_b": elo_b,
        "home_advantage": home_advantage,
    })
    return run_python("tools/python/wc_match_info_ui.py", stdin_data=stdin, timeout=30)


@mcp_tool()
def WC_team_sync(
    team: str = "",
    elo_only: bool = False,
) -> dict:
    """Update team Elo and form stats in Supabase wc_team_stats.

    Args:
        team: Team name to update (empty = update all 48 teams).
        elo_only: Only refresh Elo from built-in table, skip FBref scraping (default false).
    """
    import json as _json
    stdin = _json.dumps({"team": team, "elo_only": elo_only})
    return run_python("tools/python/wc_team_sync.py", stdin_data=stdin, timeout=120)


@mcp_tool()
def WC_stats_sync(
    mode: str = "all",
    team: str = "",
) -> dict:
    """Enrich team stats and head-to-head data from live sources.

    Pulls FIFA rankings from api.fifa.com and recent form + goals from
    football-data.org, then stores everything in Supabase.

    Args:
        mode: What to sync — "all" | "rankings" | "form" | "h2h"
        team: Single team name to update (empty = all 48 teams)
    """
    import json as _json
    stdin = _json.dumps({"mode": mode, "team": team})
    return run_python("tools/python/wc_stats_sync.py", stdin_data=stdin, timeout=600)


@mcp_tool()
def WC_analyze_match(
    team_a: str,
    team_b: str,
    league: str = "INT-World Cup",
    season: str = "2026",
    elo_a: float = 0.0,
    elo_b: float = 0.0,
    n_recent: int = 10,
    home_advantage: float = 0.0,
) -> dict:
    """Full World Cup match analysis — fetches data and runs all prediction models in one call.

    Internally calls WC_team_stats (×2), WC_elo_rating (×2), WC_head_to_head,
    WC_predict_outcome, and WC_predict_score, then synthesises a betting summary.

    Args:
        team_a: Team A name (e.g. 'Argentina').
        team_b: Team B name (e.g. 'Germany').
        league: FBref league string (default 'INT-World Cup').
        season: Season year string (default '2026').
        elo_a: Override Elo for team A (0 = auto-fetch from eloratings.net).
        elo_b: Override Elo for team B (0 = auto-fetch).
        n_recent: Recent matches for form analysis (default 10).
        home_advantage: Elo bonus for team A if playing at home (default 0 = neutral).

    Returns team stats, Elo info, H2H history, outcome probabilities,
    score distribution, and a plain-language betting summary.
    """
    import json as _json
    payload = {
        "team_a": team_a, "team_b": team_b,
        "league": league, "season": season,
        "n_recent": n_recent, "home_advantage": home_advantage,
    }
    if elo_a > 0:
        payload["elo_a"] = elo_a
    if elo_b > 0:
        payload["elo_b"] = elo_b
    return run_python("tools/python/wc_analyze_match.py", stdin_data=_json.dumps(payload), timeout=300)


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
