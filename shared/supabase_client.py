"""
Supabase REST API client — thin wrapper using requests (no extra SDK needed).

Usage:
    from shared.supabase_client import SupabaseClient
    db = SupabaseClient()
    rows = db.select("wc_matches", filters={"match_date": "2026-06-12"})
    db.upsert("wc_matches", records, on_conflict="match_date,home_team,away_team")
"""
import os
import logging
from pathlib import Path

_ROOT = Path(__file__).parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_ANON_KEY", "")
        if not self.url or not self.key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env"
            )

    def _headers(self, prefer: str = None) -> dict:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def select(self, table: str, filters: dict = None, columns: str = "*",
               order: str = None, limit: int = None) -> list:
        import requests
        params = {"select": columns}
        if filters:
            for col, val in filters.items():
                params[col] = f"eq.{val}"
        if order:
            params["order"] = order
        if limit:
            params["limit"] = limit

        r = requests.get(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers(),
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def upsert(self, table: str, records: list, on_conflict: str) -> int:
        import requests
        if not records:
            return 0
        r = requests.post(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers(
                prefer=f"resolution=merge-duplicates,return=minimal"
            ),
            params={"on_conflict": on_conflict},
            json=records,
            timeout=30,
        )
        r.raise_for_status()
        return len(records)

    def insert(self, table: str, records: list) -> int:
        import requests
        if not records:
            return 0
        r = requests.post(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers(prefer="return=minimal"),
            json=records,
            timeout=30,
        )
        r.raise_for_status()
        return len(records)
