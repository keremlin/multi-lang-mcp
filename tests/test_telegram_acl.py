"""
Telegram ACL tests — 3 parts:
  Part 1 — Blacklist mode
  Part 2 — Whitelist mode
  Part 3 — Combined: enable/disable flag + ACL

All tests target get_client() in shared/telegram_config.py — the single
gatekeeper for all three Telegram tools. An architectural test at the end
verifies that no tool script bypasses the gate by reading .env directly.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.telegram_config import get_client

BLOCKED = "@blockedchan"
ALLOWED = "@allowedchan"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _write_acl(tmp_path, mode, channels):
    acl = tmp_path / "telegram_channels.json"
    acl.write_text(json.dumps({"mode": mode, "channels": channels}))
    return acl


def _acl_patch(acl_file):
    return patch("shared.telegram_acl._ACL_PATH", acl_file)


def _creds_patch():
    """Provide valid-looking credentials so the credential check passes."""
    return (
        patch("shared.telegram_config._API_ID", 12345),
        patch("shared.telegram_config._API_HASH", "abc123"),
    )


def _client_patch():
    """Prevent a real TelegramClient from being constructed."""
    mock = MagicMock(name="TelegramClient")
    return patch("telethon.TelegramClient", return_value=mock)


# ─── Part 1: Blacklist ────────────────────────────────────────────────────────

class TestBlacklist:

    def test_listed_channel_returns_none_and_blocked_error(self, tmp_path):
        acl = _write_acl(tmp_path, "blacklist", [BLOCKED])
        with _acl_patch(acl):
            client, err = get_client(BLOCKED)
        assert client is None
        assert "blocked" in err.lower()

    def test_unlisted_channel_passes_acl_reaches_credential_check(self, tmp_path):
        acl = _write_acl(tmp_path, "blacklist", [BLOCKED])
        # Force credentials to 0 so we can see the ACL passed and hit cred check
        with _acl_patch(acl), patch("shared.telegram_config._API_ID", 0):
            client, err = get_client(ALLOWED)
        assert client is None
        assert "credentials" in err.lower()

    def test_unlisted_channel_returns_client_when_all_checks_pass(self, tmp_path):
        acl = _write_acl(tmp_path, "blacklist", [BLOCKED])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p, _client_patch():
            client, err = get_client(ALLOWED)
        assert client is not None
        assert err == ""

    def test_global_search_passes_blacklist_mode(self, tmp_path):
        acl = _write_acl(tmp_path, "blacklist", [BLOCKED])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p, _client_patch():
            client, err = get_client("")
        assert client is not None
        assert err == ""

    def test_channel_match_is_case_insensitive(self, tmp_path):
        acl = _write_acl(tmp_path, "blacklist", ["BlockedChan"])
        with _acl_patch(acl):
            client, err = get_client("@blockedchan")
        assert client is None
        assert "blocked" in err.lower()

    def test_at_prefix_stripped_before_comparison(self, tmp_path):
        acl = _write_acl(tmp_path, "blacklist", ["@blockedchan"])
        with _acl_patch(acl):
            client, err = get_client("blockedchan")
        assert client is None
        assert "blocked" in err.lower()


# ─── Part 2: Whitelist ────────────────────────────────────────────────────────

class TestWhitelist:

    def test_listed_channel_returns_client(self, tmp_path):
        acl = _write_acl(tmp_path, "whitelist", [ALLOWED])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p, _client_patch():
            client, err = get_client(ALLOWED)
        assert client is not None
        assert err == ""

    def test_unlisted_channel_returns_none_and_whitelist_error(self, tmp_path):
        acl = _write_acl(tmp_path, "whitelist", [ALLOWED])
        with _acl_patch(acl):
            client, err = get_client(BLOCKED)
        assert client is None
        assert "whitelist" in err.lower()

    def test_global_search_blocked_in_whitelist_mode(self, tmp_path):
        acl = _write_acl(tmp_path, "whitelist", [ALLOWED])
        with _acl_patch(acl):
            client, err = get_client("")
        assert client is None
        assert "whitelist" in err.lower()

    def test_off_mode_allows_any_channel(self, tmp_path):
        acl = _write_acl(tmp_path, "off", [])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p, _client_patch():
            client, err = get_client(BLOCKED)
        assert client is not None
        assert err == ""

    def test_missing_acl_file_defaults_to_allow(self, tmp_path):
        nonexistent = tmp_path / "no_such_file.json"
        id_p, hash_p = _creds_patch()
        with _acl_patch(nonexistent), id_p, hash_p, _client_patch():
            client, err = get_client(BLOCKED)
        assert client is not None
        assert err == ""


# ─── Part 3: Combined (enable flag + ACL) ────────────────────────────────────

class TestCombined:

    @pytest.mark.parametrize("disabled_val", ["false", "0", "no"])
    def test_disabled_flag_blocks_regardless_of_acl(self, disabled_val, tmp_path):
        acl = _write_acl(tmp_path, "off", [])
        with _acl_patch(acl), patch.dict("os.environ", {"TELEGRAM_TOOLS_ENABLED": disabled_val}):
            client, err = get_client(ALLOWED)
        assert client is None
        assert "disabled" in err.lower()

    def test_disabled_overrides_whitelist(self, tmp_path):
        acl = _write_acl(tmp_path, "whitelist", [ALLOWED])
        with _acl_patch(acl), patch.dict("os.environ", {"TELEGRAM_TOOLS_ENABLED": "false"}):
            client, err = get_client(ALLOWED)
        assert client is None
        assert "disabled" in err.lower()

    def test_enabled_with_blacklisted_channel_blocked(self, tmp_path):
        acl = _write_acl(tmp_path, "blacklist", [BLOCKED])
        with _acl_patch(acl), patch.dict("os.environ", {"TELEGRAM_TOOLS_ENABLED": "true"}):
            client, err = get_client(BLOCKED)
        assert client is None
        assert "blocked" in err.lower()

    def test_enabled_with_whitelisted_channel_returns_client(self, tmp_path):
        acl = _write_acl(tmp_path, "whitelist", [ALLOWED])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), patch.dict("os.environ", {"TELEGRAM_TOOLS_ENABLED": "true"}):
            with id_p, hash_p, _client_patch():
                client, err = get_client(ALLOWED)
        assert client is not None
        assert err == ""

    def test_missing_credentials_blocked_after_acl_passes(self, tmp_path):
        acl = _write_acl(tmp_path, "off", [])
        with _acl_patch(acl), \
             patch("shared.telegram_config._API_ID", 0), \
             patch("shared.telegram_config._API_HASH", ""):
            client, err = get_client(ALLOWED)
        assert client is None
        assert "credentials" in err.lower()

    def test_enable_flag_checked_before_acl(self, tmp_path):
        # Even if the channel would be on the whitelist, disabled fires first.
        acl = _write_acl(tmp_path, "whitelist", [BLOCKED])
        with _acl_patch(acl), patch.dict("os.environ", {"TELEGRAM_TOOLS_ENABLED": "false"}):
            client, err = get_client(BLOCKED)
        assert client is None
        assert "disabled" in err.lower()


# ─── Architecture: no tool script may bypass the gate ────────────────────────

TOOL_SCRIPTS = [
    Path("tools/python/telegram_download.py"),
    Path("tools/python/telegram_download_by_ids.py"),
    Path("tools/python/telegram_search.py"),
]

FORBIDDEN = ["API_ID", "API_HASH", "SESSION_PATH", "load_dotenv", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"]


@pytest.mark.parametrize("script", TOOL_SCRIPTS, ids=[s.name for s in TOOL_SCRIPTS])
def test_tool_uses_get_client_not_direct_env(script):
    content = script.read_text(encoding="utf-8")
    assert "get_client" in content, f"{script.name} does not call get_client()"
    for forbidden in FORBIDDEN:
        assert forbidden not in content, (
            f"{script.name} directly accesses '{forbidden}' — "
            "all credential and security checks must go through get_client()"
        )
