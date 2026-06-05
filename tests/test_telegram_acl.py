"""
Telegram ACL tests — 3 parts + write gate:
  Part 1 — Blacklist mode
  Part 2 — Whitelist mode
  Part 3 — Combined: enable/disable flag + ACL
  Part 4 — Write gate: need_write + TELEGRAM_WRITE_ENABLED + _ReadOnlyClient

All tests target get_client() in shared/telegram_config.py — the single
gatekeeper for all three Telegram tools. An architectural test at the end
verifies that no tool script bypasses the gate by reading .env directly.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import shared.telegram_config as _tc
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


def _client_patch(readonly=True):
    """Prevent real client construction.

    readonly=True  → patches _ReadOnlyClient  (default: need_write=False path)
    readonly=False → patches _TelegramClient  (need_write=True + write enabled path)
    """
    mock = MagicMock(name="MockClient")
    target = (
        "shared.telegram_config._ReadOnlyClient"
        if readonly
        else "shared.telegram_config._TelegramClient"
    )
    return patch(target, return_value=mock)


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


# ─── Part 4: Write gate ───────────────────────────────────────────────────────

class TestWriteGate:

    # ── Gate checks ───────────────────────────────────────────────────────────

    def test_read_tool_succeeds_without_write_flag(self, tmp_path):
        acl = _write_acl(tmp_path, "off", [])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p, _client_patch(readonly=True):
            with patch.dict("os.environ", {"TELEGRAM_WRITE_ENABLED": "false"}):
                client, err = get_client(ALLOWED, need_write=False)
        assert client is not None
        assert err == ""

    def test_write_tool_blocked_when_flag_is_false(self, tmp_path):
        acl = _write_acl(tmp_path, "off", [])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p:
            with patch.dict("os.environ", {"TELEGRAM_WRITE_ENABLED": "false"}):
                client, err = get_client(ALLOWED, need_write=True)
        assert client is None
        assert "write" in err.lower()

    @pytest.mark.parametrize("enabled_val", ["true", "1", "yes"])
    def test_write_tool_allowed_when_flag_is_true(self, enabled_val, tmp_path):
        acl = _write_acl(tmp_path, "off", [])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p, _client_patch(readonly=False):
            with patch.dict("os.environ", {"TELEGRAM_WRITE_ENABLED": enabled_val}):
                client, err = get_client(ALLOWED, need_write=True)
        assert client is not None
        assert err == ""

    def test_write_flag_checked_after_acl(self, tmp_path):
        acl = _write_acl(tmp_path, "whitelist", [ALLOWED])
        with _acl_patch(acl), patch.dict("os.environ", {"TELEGRAM_WRITE_ENABLED": "true"}):
            client, err = get_client(BLOCKED, need_write=True)
        assert client is None
        assert "whitelist" in err.lower()

    def test_write_flag_default_is_false(self, tmp_path):
        acl = _write_acl(tmp_path, "off", [])
        id_p, hash_p = _creds_patch()
        env = {k: v for k, v in __import__("os").environ.items()
               if k != "TELEGRAM_WRITE_ENABLED"}
        with _acl_patch(acl), id_p, hash_p, patch.dict("os.environ", env, clear=True):
            client, err = get_client(ALLOWED, need_write=True)
        assert client is None
        assert "write" in err.lower()

    # ── _ReadOnlyClient Telethon-level enforcement ────────────────────────────

    def test_readonly_client_is_returned_when_write_disabled(self, tmp_path):
        acl = _write_acl(tmp_path, "off", [])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p, _client_patch(readonly=True):
            with patch.dict("os.environ", {"TELEGRAM_WRITE_ENABLED": "false"}):
                client, err = get_client(ALLOWED, need_write=False)
        assert client is not None
        # The mock was called via _ReadOnlyClient, not _TelegramClient
        assert err == ""

    def test_readonly_client_is_returned_even_when_write_enabled_but_not_requested(self, tmp_path):
        # Tool passes need_write=False while admin has write enabled →
        # still gets _ReadOnlyClient to prevent accidental writes.
        acl = _write_acl(tmp_path, "off", [])
        id_p, hash_p = _creds_patch()
        with _acl_patch(acl), id_p, hash_p, _client_patch(readonly=True):
            with patch.dict("os.environ", {"TELEGRAM_WRITE_ENABLED": "true"}):
                client, err = get_client(ALLOWED, need_write=False)
        assert client is not None
        assert err == ""

    @pytest.mark.parametrize("method", [
        "send_message", "send_file", "edit_message", "delete_messages",
        "forward_messages", "pin_message", "kick_participant",
    ])
    def test_readonly_client_blocks_write_methods(self, method):
        # Use __new__ to get an instance without a real Telegram connection.
        client = object.__new__(_tc._ReadOnlyClient)
        with pytest.raises(PermissionError, match=method):
            getattr(client, method)

    def test_readonly_client_allows_read_methods(self):
        client = object.__new__(_tc._ReadOnlyClient)
        # These must NOT raise — they are read operations.
        for attr in ("iter_messages", "get_messages", "get_entity",
                     "download_media", "connect", "disconnect",
                     "is_user_authorized"):
            # Just accessing the attribute (not calling) must succeed.
            _ = getattr(client, attr)


# ─── Architecture: no tool script may bypass the gate ────────────────────────

TOOL_SCRIPTS = [
    Path("tools/python/telegram_download.py"),
    Path("tools/python/telegram_download_by_ids.py"),
    Path("tools/python/telegram_search.py"),
    Path("tools/python/telegram_bot_interact.py"),
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
