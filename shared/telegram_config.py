"""
Telegram connection factory — the single gatekeeper for all Telegram tools.

Tool scripts MUST NOT import credentials or load .env directly.
They call get_client(channel) and receive either a ready TelegramClient
or an error string. All security checks live here and nowhere else.

Private (not for import by tools):
  _API_ID, _API_HASH, _SESSION_PATH

Public:
  get_client(channel) -> (TelegramClient | None, error_str)
"""
import os
import logging
from pathlib import Path

from dotenv import load_dotenv

from shared.telegram_acl import check_channel as _acl_check

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

_API_ID: int = int(os.environ.get("TELEGRAM_API_ID", "0") or "0")
_API_HASH: str = os.environ.get("TELEGRAM_API_HASH", "")
_SESSION_PATH: str = str(
    Path(__file__).parent.parent / "tools" / "python" / "tele_session"
)


def get_client(channel: str = ""):
    """Single gate for all Telegram tool access.

    Checks in order:
      1. TELEGRAM_TOOLS_ENABLED env var  (read at call time — no restart needed)
      2. Channel ACL from config/telegram_channels.json  (re-read from disk each call)
      3. Credentials present (API_ID, API_HASH)
      4. telethon package installed

    Returns (TelegramClient, "") on success.
    The client is NOT yet connected — caller must: await client.connect(),
    verify is_user_authorized(), do work, then await client.disconnect().

    Returns (None, error_message) if any check fails.
    Tool scripts must treat None as a hard stop and print the error to stdout.
    """
    # 1. Enable flag
    if (
        os.environ.get("TELEGRAM_TOOLS_ENABLED", "true").strip().lower()
        in ("false", "0", "no")
    ):
        return None, "Telegram tools are currently disabled by the server administrator."

    # 2. ACL
    allowed, err = _acl_check(channel)
    if not allowed:
        return None, err

    # 3. Credentials
    if not _API_ID or not _API_HASH:
        return None, "Missing credentials: add TELEGRAM_API_ID and TELEGRAM_API_HASH to .env"

    # 4. telethon
    try:
        from telethon import TelegramClient  # noqa: PLC0415
    except ImportError:
        return None, "telethon not installed — run: pip install telethon"

    return TelegramClient(_SESSION_PATH, _API_ID, _API_HASH), ""
