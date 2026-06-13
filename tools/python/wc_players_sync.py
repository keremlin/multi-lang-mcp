"""
WC_players_sync — sync WC 2026 squad rosters into wc_players.

Data source: football-data.org
  GET /v4/competitions/WC/teams?season=2026  → squad per team
  GET /v4/persons/{id}                       → player's current club (rate-limited)

Input (stdin JSON):
  mode   str   "squads" | "clubs" | "all"  (default "all")
  team   str   Filter to one team name (default "" = all)

Output:
  {"success": true, "data": {"players_upserted": N, "clubs_updated": N, "warnings": [...]}}
"""
import sys
import json
import time
import os
import logging
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import requests
from shared.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

_FD_BASE = "https://api.football-data.org/v4"

# Map football-data.org team name → our canonical DB name
_FD_NAME_MAP = {
    "United States": "United States",
    "USA":           "United States",
    "Republic of Ireland": "Republic of Ireland",
    "Korea Republic": "South Korea",
    "DR Congo":      "Congo DR",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Cape Verde":    "Cape Verde Islands",
    "Ivory Coast":   "Ivory Coast",
    "Curaçao":       "Curaçao",
}

# football-data.org position codes → readable labels
_POSITION_LABEL = {
    "Goalkeeper":  "GK",
    "Defence":     "DEF",
    "Midfield":    "MID",
    "Offence":     "FWD",
    "Coach":       None,
}


def _canonical(name: str) -> str:
    return _FD_NAME_MAP.get(name, name)


def _headers(api_key: str) -> dict:
    return {"X-Auth-Token": api_key}


def sync_squads(db: SupabaseClient, api_key: str, team_filter: str) -> tuple[int, list]:
    """Fetch all WC teams + squads, upsert into wc_players."""
    url = f"{_FD_BASE}/competitions/WC/teams?season=2026"
    try:
        r = requests.get(url, headers=_headers(api_key), timeout=20)
        r.raise_for_status()
        teams = r.json().get("teams", [])
    except Exception as exc:
        return 0, [f"Failed to fetch teams: {exc}"]

    upserted, warnings = 0, []
    for team_obj in teams:
        raw_name = team_obj.get("name", "")
        canonical = _canonical(raw_name)
        if team_filter and canonical.lower() != team_filter.lower():
            continue

        squad = team_obj.get("squad", [])
        if not squad:
            warnings.append(f"{canonical}: empty squad")
            continue

        rows = []
        for p in squad:
            pos_raw = p.get("position", "")
            pos = _POSITION_LABEL.get(pos_raw)
            if pos is None:
                continue  # skip coaches
            rows.append({
                "team":          canonical,
                "fd_player_id":  p.get("id"),
                "name":          p.get("name", ""),
                "position":      pos,
                "shirt_number":  p.get("shirtNumber"),
                "date_of_birth": p.get("dateOfBirth"),
                "nationality":   p.get("nationality"),
            })

        if rows:
            db.upsert("wc_players", rows, on_conflict="team,name")
            upserted += len(rows)

    return upserted, warnings


def sync_clubs(db: SupabaseClient, api_key: str, team_filter: str) -> tuple[int, list]:
    """
    Enrich each player with current club + league by calling /v4/persons/{id}.
    Free tier: 10 req/min — sleep 6 s between calls.
    """
    filters = {}
    if team_filter:
        filters["team"] = team_filter

    players = db.select("wc_players", filters=filters if filters else None) \
        if filters else db.select("wc_players")

    updated, warnings = 0, []
    for i, player in enumerate(players):
        pid = player.get("fd_player_id")
        if not pid:
            continue
        if player.get("club"):  # already have club — skip unless refreshing
            continue
        if i > 0:
            time.sleep(6)  # stay inside free-tier rate limit
        try:
            r = requests.get(f"{_FD_BASE}/persons/{pid}",
                             headers=_headers(api_key), timeout=15)
            r.raise_for_status()
            data = r.json()
            current = data.get("currentTeam") or {}
            club       = current.get("name", "")
            area       = current.get("area", {}).get("name", "")
            # competition is nested under runningCompetitions
            running    = current.get("runningCompetitions", [])
            league     = running[0].get("name", "") if running else ""
            db.upsert("wc_players", [{
                "team":         player["team"],
                "name":         player["name"],
                "club":         club,
                "club_country": area,
                "club_league":  league,
            }], on_conflict="team,name")
            updated += 1
        except Exception as exc:
            warnings.append(f"{player['name']}: {exc}")

    return updated, warnings


_TSDB_SEARCH = "https://www.thesportsdb.com/api/v1/json/3/searchplayers.php"


def sync_photos(db: SupabaseClient, team_filter: str) -> tuple[int, list]:
    """
    Fetch player headshot URLs from TheSportsDB by name search.
    Stores the thumbnail URL in wc_players.photo_url. Skips players
    that already have a photo. Sleeps 0.3 s between requests.
    """
    filters = {"team": team_filter} if team_filter else None
    players = db.select("wc_players", filters=filters) if filters \
        else db.select("wc_players")

    updated, warnings = 0, []
    for i, player in enumerate(players):
        if player.get("photo_url"):
            continue
        name = player["name"]
        if i > 0:
            time.sleep(1.2)
        try:
            r = requests.get(_TSDB_SEARCH,
                             params={"p": name},
                             headers={"User-Agent": "Mozilla/5.0"},
                             timeout=10)
            r.raise_for_status()
            results = r.json().get("player") or []
            if not results:
                continue
            thumb = results[0].get("strThumb") or ""
            if not thumb:
                continue
            db.upsert("wc_players", [{
                "team":      player["team"],
                "name":      name,
                "photo_url": thumb,
            }], on_conflict="team,name")
            updated += 1
        except Exception as exc:
            warnings.append(f"{name}: {exc}")

    return updated, warnings


def run_sync(mode: str = "all", team: str = "") -> dict:
    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not api_key and mode in ("all", "squads", "clubs"):
        return {"success": False, "error": "FOOTBALL_DATA_API_KEY not set in .env"}

    db = SupabaseClient()
    result: dict = {"players_upserted": 0, "clubs_updated": 0,
                    "photos_updated": 0, "warnings": []}

    if mode in ("all", "squads"):
        n, w = sync_squads(db, api_key, team)
        result["players_upserted"] = n
        result["warnings"].extend(w)

    if mode in ("all", "clubs"):
        n, w = sync_clubs(db, api_key, team)
        result["clubs_updated"] = n
        result["warnings"].extend(w)

    if mode in ("all", "photos"):
        n, w = sync_photos(db, team)
        result["photos_updated"] = n
        result["warnings"].extend(w)

    return {"success": True, "data": result}


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    try:
        out = run_sync(
            mode=params.get("mode", "all"),
            team=params.get("team", ""),
        )
    except Exception as exc:
        out = {"success": False, "error": str(exc)}
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
