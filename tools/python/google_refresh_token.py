import sys
import os
import json
from pathlib import Path

# .env lives at the project root (two levels up from this script)
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


def _update_env_file(new_token: str) -> bool:
    """Replace GOOGLE_ACCESS_TOKEN line in .env, or append if missing."""
    if not _ENV_FILE.exists():
        return False

    lines = _ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("GOOGLE_ACCESS_TOKEN="):
            lines[i] = f"GOOGLE_ACCESS_TOKEN={new_token}\n"
            updated = True
            break

    if not updated:
        lines.append(f"GOOGLE_ACCESS_TOKEN={new_token}\n")

    _ENV_FILE.write_text("".join(lines), encoding="utf-8")
    return True


def main():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")

    missing = [k for k, v in {
        "GOOGLE_CLIENT_ID": client_id,
        "GOOGLE_CLIENT_SECRET": client_secret,
        "GOOGLE_REFRESH_TOKEN": refresh_token,
    }.items() if not v]
    if missing:
        print(json.dumps({"success": False, "error": f"Missing required env vars: {', '.join(missing)}"}))
        sys.exit(1)

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        print(json.dumps({"success": False, "error": "google-auth not installed — run: pip install google-auth"}))
        sys.exit(1)

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        creds.refresh(Request())
        new_token = creds.token
        expiry = creds.expiry.isoformat() if creds.expiry else None

        env_updated = _update_env_file(new_token)

        print(json.dumps({
            "success": True,
            "data": {
                "access_token": new_token,
                "expires_at": expiry,
                "env_file_updated": env_updated,
            },
        }))

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
