"""
Interactive script to get fresh Google OAuth2 tokens with Cloud Platform scope.
Run once to populate GOOGLE_ACCESS_TOKEN and GOOGLE_REFRESH_TOKEN in .env.

Usage:
    .venv\\Scripts\\python setup_google_oauth.py
"""
from pathlib import Path
from dotenv import load_dotenv

_ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(_ENV_FILE)

import os
import sys


def update_env(access_token: str, refresh_token: str | None) -> None:
    if not _ENV_FILE.exists():
        print("[setup] .env not found — tokens not saved to file.")
        return

    lines = _ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    found_access = found_refresh = False

    for i, line in enumerate(lines):
        if line.startswith("GOOGLE_ACCESS_TOKEN="):
            lines[i] = f"GOOGLE_ACCESS_TOKEN={access_token}\n"
            found_access = True
        if refresh_token and line.startswith("GOOGLE_REFRESH_TOKEN="):
            lines[i] = f"GOOGLE_REFRESH_TOKEN={refresh_token}\n"
            found_refresh = True

    if not found_access:
        lines.append(f"GOOGLE_ACCESS_TOKEN={access_token}\n")
    if refresh_token and not found_refresh:
        lines.append(f"GOOGLE_REFRESH_TOKEN={refresh_token}\n")

    _ENV_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"[setup] .env updated at {_ENV_FILE}")


def main():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback")

    if not client_id or not client_secret:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import Flow
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        print("ERROR: Run: pip install google-auth-oauthlib")
        sys.exit(1)

    scopes = ["https://www.googleapis.com/auth/cloud-platform"]

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=scopes,
        redirect_uri=redirect_uri,
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )

    print("\nGoogle OAuth2 Setup")
    print("=" * 50)
    print("\nStep 1 — Open this URL in your browser:\n")
    print(f"  {auth_url}\n")
    print("Step 2 — After authorizing, you will be redirected to:")
    print(f"  {redirect_uri}?code=...")
    print("\nCopy the full redirect URL or just the 'code' value and paste it below.\n")

    raw = input("Paste the authorization code (or full redirect URL): ").strip()

    # Support pasting the full redirect URL
    if "code=" in raw:
        from urllib.parse import urlparse, parse_qs
        code = parse_qs(urlparse(raw).query).get("code", [raw])[0]
    else:
        code = raw

    print("\nExchanging code for tokens...")

    try:
        flow.fetch_token(code=code)
        creds = flow.credentials

        access_token = creds.token
        refresh_token = creds.refresh_token
        expiry = creds.expiry.isoformat() if creds.expiry else "unknown"

        print(f"\nAccess token:  {access_token[:40]}...")
        print(f"Refresh token: {'(received)' if refresh_token else '(NOT received — revoke app access in Google and retry)'}")
        print(f"Expires at:    {expiry}")

        update_env(access_token, refresh_token)

        print("\nDone! Restart the MCP server to pick up the new tokens.")

    except Exception as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
