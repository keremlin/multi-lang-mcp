"""
Telegram channel ACL (whitelist / blacklist).

Config file: config/telegram_channels.json
  {
    "mode": "off" | "whitelist" | "blacklist",
    "channels": ["@channelname", "-1001234567890", ...]
  }

The file is re-read on every call so edits take effect without a server restart.
MCP users have no parameter to influence this — it is server-side only.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_ACL_PATH = Path(__file__).parent.parent / "config" / "telegram_channels.json"


def _normalize(channel: str) -> str:
    """Lowercase and strip leading @ so '@MyChannel' and 'mychannel' compare equal."""
    s = channel.strip().lower()
    return s.lstrip("@")


def check_channel(channel: str) -> tuple[bool, str]:
    """Return (allowed, error_message).

    channel="" means global search (no specific channel).
    Returns (True, "") when access is granted.
    Returns (False, "<reason>") when access is denied.
    """
    try:
        acl = json.loads(_ACL_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True, ""
    except Exception as exc:
        logger.error("telegram_channels.json parse error: %s", exc)
        return False, f"telegram_channels.json parse error: {exc}"

    mode = acl.get("mode", "off").strip().lower()

    if mode == "off":
        return True, ""

    listed = {_normalize(c) for c in acl.get("channels", []) if c.strip()}
    norm = _normalize(channel)

    if mode == "whitelist":
        if not norm:
            return False, "Global Telegram search is not permitted while whitelist mode is active."
        if norm not in listed:
            return False, f"Channel '{channel}' is not on the whitelist."
        return True, ""

    if mode == "blacklist":
        if norm and norm in listed:
            return False, f"Channel '{channel}' is blocked."
        return True, ""

    return False, f"Unknown ACL mode '{mode}' in telegram_channels.json — expected 'off', 'whitelist', or 'blacklist'."
