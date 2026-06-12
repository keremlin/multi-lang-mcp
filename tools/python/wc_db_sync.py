"""
WC_db_sync — fetch WC 2026 fixtures from a football API and upsert into Supabase.

Sources tried in order:
  1. football-data.org  (free key required — set FOOTBALL_DATA_API_KEY in .env)
  2. TheSportsDB        (no key needed — free tier, searches for FIFA World Cup)

Run this tool once to seed the DB, then again periodically to update scores.

Input (stdin JSON):
  source        str   "auto" | "football-data" | "thesportsdb" (default "auto")
  force         bool  Re-sync even if matches already exist (default false)

Output:
  {"success": true, "data": {"upserted": N, "source": "...", "matches": [...]}}
"""
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

_FD_BASE = "https://api.football-data.org/v4"
_TSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"


def _fetch_football_data(api_key: str) -> list:
    """Fetch all WC 2026 matches from football-data.org."""
    import requests
    headers = {"X-Auth-Token": api_key}
    r = requests.get(f"{_FD_BASE}/competitions/WC/matches", headers=headers, timeout=20)
    r.raise_for_status()
    raw = r.json().get("matches", [])
    matches = []
    for m in raw:
        utc = m.get("utcDate", "")
        try:
            dt = datetime.fromisoformat(utc.replace("Z", "+00:00"))
            match_date = dt.date().isoformat()
            kickoff = dt.strftime("%H:%M")
        except Exception:
            match_date = utc[:10] if utc else None
            kickoff = None

        home = m.get("homeTeam", {}).get("name", "")
        away = m.get("awayTeam", {}).get("name", "")
        score = m.get("score", {})
        full = score.get("fullTime", {})
        home_goals = full.get("home")
        away_goals = full.get("away")
        status_raw = m.get("status", "SCHEDULED")
        status = "finished" if status_raw == "FINISHED" else "upcoming"

        matches.append({
            "match_date": match_date,
            "kickoff_time": kickoff,
            "home_team": home,
            "away_team": away,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "status": status,
            "venue": m.get("venue"),
            "group_name": m.get("group"),
            "stage": m.get("stage", "GROUP_STAGE").replace("_", " ").title(),
            "source": "football-data.org",
        })
    return matches


def _find_wc_league_id() -> str | None:
    """Search TheSportsDB for the FIFA World Cup league ID."""
    import requests
    try:
        r = requests.get(
            f"{_TSDB_BASE}/search_all_leagues.php",
            params={"s": "Soccer", "c": "International"},
            timeout=15,
        )
        leagues = r.json().get("countrys") or []
        for lg in leagues:
            name = (lg.get("strLeague") or "").lower()
            if "world cup" in name and "fifa" in name:
                return lg.get("idLeague")
        # Fallback: known ID
        return "4779"
    except Exception:
        return "4779"


def _fetch_thesportsdb() -> list:
    """Fetch WC 2026 matches from TheSportsDB (no API key needed)."""
    import requests

    league_id = _find_wc_league_id()
    # TheSportsDB uses season format "2026-2027" for summer tournaments
    for season in ["2026-2027", "2026"]:
        try:
            r = requests.get(
                f"{_TSDB_BASE}/eventsseason.php",
                params={"id": league_id, "s": season},
                timeout=20,
            )
            events = r.json().get("events") or []
            if events:
                break
        except Exception:
            events = []

    matches = []
    for ev in events:
        date_str = ev.get("dateEvent", "")
        time_str = (ev.get("strTime") or "")[:5]
        home_score = ev.get("intHomeScore")
        away_score = ev.get("intAwayScore")
        try:
            hg = int(home_score) if home_score is not None else None
            ag = int(away_score) if away_score is not None else None
        except (ValueError, TypeError):
            hg = ag = None

        status = "finished" if (hg is not None and ag is not None) else "upcoming"

        matches.append({
            "match_date": date_str or None,
            "kickoff_time": time_str or None,
            "home_team": ev.get("strHomeTeam", ""),
            "away_team": ev.get("strAwayTeam", ""),
            "home_goals": hg,
            "away_goals": ag,
            "status": status,
            "venue": ev.get("strVenue"),
            "group_name": ev.get("strRound"),
            "stage": ev.get("strRound", "Group Stage"),
            "source": "thesportsdb",
        })
    return matches


def sync(source: str = "auto", force: bool = False) -> dict:
    import os
    db = SupabaseClient()

    if not force:
        existing = db.select("wc_matches", limit=1)
        if existing:
            total = db.select("wc_matches", columns="id")
            return {
                "success": True,
                "data": {
                    "skipped": True,
                    "reason": f"DB already has {len(total)} matches. Use force=true to re-sync.",
                    "total_in_db": len(total),
                },
            }

    matches = []
    used_source = None
    last_error = None

    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()

    if source in ("auto", "football-data") and api_key:
        try:
            matches = _fetch_football_data(api_key)
            used_source = "football-data.org"
        except Exception as e:
            last_error = f"football-data.org: {e}"

    if not matches and source in ("auto", "thesportsdb"):
        try:
            matches = _fetch_thesportsdb()
            used_source = "thesportsdb"
        except Exception as e:
            last_error = f"thesportsdb: {e}"

    if not matches:
        return {
            "success": False,
            "error": f"No matches fetched. Last error: {last_error}",
            "hint": (
                "Get a free API key at https://www.football-data.org/client/register "
                "and set FOOTBALL_DATA_API_KEY in .env for reliable data."
            ),
        }

    # Filter out rows missing required fields (e.g. TBD knockout teams)
    valid = [
        m for m in matches
        if m.get("match_date") and m.get("home_team") and m.get("away_team")
    ]

    # Upsert in batches of 20 to avoid payload limits
    upserted = 0
    for i in range(0, len(valid), 20):
        upserted += db.upsert("wc_matches", valid[i:i+20], on_conflict="match_date,home_team,away_team")

    return {
        "success": True,
        "data": {
            "source": used_source,
            "total_fetched": len(matches),
            "upserted": upserted,
            "sample": valid[:3],
        },
    }


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    try:
        result = sync(
            source=params.get("source", "auto"),
            force=bool(params.get("force", False)),
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
