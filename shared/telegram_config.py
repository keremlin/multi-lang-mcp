"""
Telegram connection factory — the single gatekeeper for all Telegram tools.

Tool scripts MUST NOT import credentials or load .env directly.
They call get_client(channel) and receive either a ready TelegramClient
or an error string. All security checks live here and nowhere else.

Private (not for import by tools):
  _API_ID, _API_HASH, _SESSION_PATH, _TelegramClient, _ReadOnlyClient

Public:
  get_client(channel, need_write) -> (TelegramClient | None, error_str)
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

# ── Telethon client classes (lazy-imported once at module load) ───────────────

try:
    from telethon import TelegramClient as _TelegramClient

    class _ReadOnlyClient(_TelegramClient):
        """TelegramClient that raises PermissionError on any write-method access.

        Returned by get_client() when TELEGRAM_WRITE_ENABLED is false or
        need_write=False. Acts as a Telethon-level enforcement layer on top
        of the need_write gate in get_client() — even if a tool forgets to
        declare need_write=True, it cannot accidentally send messages.
        """

        _WRITE_METHODS: frozenset = frozenset({
            # Messaging
            "send_message",
            "send_file",
            "send_voice",
            "send_video_note",
            "send_reaction",
            # Editing / deletion
            "edit_message",
            "delete_messages",
            # Forwarding
            "forward_messages",
            # Pin / unpin
            "pin_message",
            "unpin_message",
            # Admin / moderation
            "kick_participant",
            "edit_admin",
            "edit_permissions",
            "edit_ban",
            # Channel / group management
            "create_channel",
            "delete_channel",
        })

        def __getattribute__(self, name: str):
            blocked = object.__getattribute__(type(self), "_WRITE_METHODS")
            if name in blocked:
                raise PermissionError(
                    f"Write operation '{name}' is blocked — "
                    "set TELEGRAM_WRITE_ENABLED=true in .env to enable."
                )
            return super().__getattribute__(name)

    _TELETHON_AVAILABLE = True

except ImportError:
    _TelegramClient = None  # type: ignore[assignment,misc]
    _ReadOnlyClient = None  # type: ignore[assignment,misc]
    _TELETHON_AVAILABLE = False


# ── Public gate ───────────────────────────────────────────────────────────────

def get_client(channel: str = "", need_write: bool = False):
    """Single gate for all Telegram tool access.

    Checks in order:
      1. TELEGRAM_TOOLS_ENABLED env var  (read at call time — no restart needed)
      2. Channel ACL from config/telegram_channels.json  (re-read from disk each call)
      3. Credentials present (API_ID, API_HASH)
      4. Write permission — only when need_write=True:
         TELEGRAM_WRITE_ENABLED must be "true" / "1" / "yes", default is "false".
         Tools that only read must NOT pass need_write=True.
      5. telethon package installed

    Returns (client, "") on success:
      - need_write=False or TELEGRAM_WRITE_ENABLED=false → _ReadOnlyClient
        (write methods raise PermissionError at the Telethon level)
      - need_write=True and TELEGRAM_WRITE_ENABLED=true  → TelegramClient

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

    # 4. Write permission (only enforced when the tool explicitly requests write access)
    write_enabled = (
        os.environ.get("TELEGRAM_WRITE_ENABLED", "false").strip().lower()
        in ("true", "1", "yes")
    )
    if need_write and not write_enabled:
        return None, (
            "Telegram write operations are disabled "
            "(set TELEGRAM_WRITE_ENABLED=true in .env to enable)."
        )

    # 5. telethon
    if not _TELETHON_AVAILABLE:
        return None, "telethon not installed — run: pip install telethon"

    # Return read-only client unless the tool explicitly requested write access
    # AND the admin has enabled writes globally.
    cls = _TelegramClient if (need_write and write_enabled) else _ReadOnlyClient
    return cls(_SESSION_PATH, _API_ID, _API_HASH), ""
