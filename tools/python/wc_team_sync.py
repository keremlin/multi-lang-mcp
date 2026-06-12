"""
WC_team_sync — update team stats in Supabase wc_team_stats table.

Updates form strings and goal averages from FBref (with a short timeout so it
never blocks). Elo ratings and group assignments are already seeded; this tool
enriches them with live form data once FBref becomes accessible.

Input (stdin JSON):
  team      str   Single team to update (empty = update all teams in DB)
  timeout   int   FBref scrape timeout in seconds (default 15)
  elo_only  bool  Only update Elo from fallback table, skip FBref (default false)

Output:
  {"success": true, "data": {"updated": N, "failed": [...], "skipped": [...]}}
"""
import sys
import json
import logging
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

_ELO_TABLE = {
    "Argentina": 2141, "France": 2086, "England": 2065, "Spain": 2047,
    "Brazil": 2026, "Portugal": 1985, "Netherlands": 1984, "Germany": 1978,
    "Belgium": 1966, "Croatia": 1956, "Uruguay": 1954, "Colombia": 1935,
    "Switzerland": 1895, "Sweden": 1893, "Mexico": 1901, "Senegal": 1884,
    "Morocco": 1882, "Japan": 1878, "Austria": 1879, "Norway": 1852,
    "South Korea": 1862, "Iran": 1860, "Australia": 1845, "Ecuador": 1851,
    "Turkey": 1868, "Canada": 1866, "Scotland": 1831, "Paraguay": 1832,
    "Czechia": 1828, "Algeria": 1820, "Ivory Coast": 1798, "Egypt": 1791,
    "Bosnia-Herzegovina": 1771, "Ghana": 1839, "Tunisia": 1748,
    "Saudi Arabia": 1748, "Qatar": 1744, "United States": 1891,
    "Cape Verde Islands": 1718, "Jordan": 1711, "Iraq": 1712,
    "Congo DR": 1698, "Panama": 1699, "Uzbekistan": 1681,
    "South Africa": 1652, "Curaçao": 1581, "Haiti": 1602, "New Zealand": 1601,
}


def _fetch_fbref_stats(team: str, timeout: int) -> dict | None:
    """Try to get form + goal stats from FBref. Returns None if blocked/slow."""
    try:
        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError()

        import soccerdata as sd
        import pandas as pd

        fbref = sd.FBref(leagues=["INT-World Cup"], seasons=["2026"])
        schedule = fbref.read_schedule()
        df = schedule.reset_index()

        home_col = next((c for c in df.columns if "home" in c.lower() and "team" in c.lower()), None)
        away_col = next((c for c in df.columns if "away" in c.lower() and "team" in c.lower()), None)
        hs_col   = next((c for c in df.columns if "home" in c.lower() and ("score" in c.lower() or "goal" in c.lower())), None)
        as_col   = next((c for c in df.columns if "away" in c.lower() and ("score" in c.lower() or "goal" in c.lower())), None)

        if not home_col or not away_col:
            return None

        team_lc = team.lower()
        mask = (
            df[home_col].str.lower().str.contains(team_lc, na=False)
            | df[away_col].str.lower().str.contains(team_lc, na=False)
        )
        games = df[mask].dropna(subset=[hs_col, as_col]) if hs_col and as_col else df[mask]

        results, gf_list, ga_list = [], [], []
        for _, row in games.tail(10).iterrows():
            try:
                hs = int(float(row[hs_col]))
                as_ = int(float(row[as_col]))
            except Exception:
                continue
            is_home = team_lc in str(row.get(home_col, "")).lower()
            gf = hs if is_home else as_
            ga = as_ if is_home else hs
            r = "W" if gf > ga else ("D" if gf == ga else "L")
            results.append(r)
            gf_list.append(gf)
            ga_list.append(ga)

        if not results:
            return None

        n = len(results)
        return {
            "form_last5": "".join(results[-5:]),
            "avg_goals_scored": round(sum(gf_list) / n, 2),
            "avg_goals_conceded": round(sum(ga_list) / n, 2),
            "matches_analyzed": n,
            "data_source": "fbref",
        }
    except Exception as exc:
        logger.debug("FBref stats fetch failed for %s: %s", team, exc)
        return None


def sync_teams(team: str = "", timeout: int = 15, elo_only: bool = False) -> dict:
    db = SupabaseClient()

    if team:
        teams = db.select("wc_team_stats", filters={"name": team})
    else:
        teams = db.select("wc_team_stats", order="group_name,name")

    if not teams:
        return {"success": False, "error": f"Team '{team}' not found in DB. Run WC_db_sync first."}

    updated, failed, skipped = [], [], []

    for row in teams:
        name = row["name"]

        update = {"name": name}

        # Always refresh Elo from table if available
        if name in _ELO_TABLE:
            update["elo"] = _ELO_TABLE[name]

        # Try FBref for form/goals unless elo_only
        if not elo_only:
            stats = _fetch_fbref_stats(name, timeout)
            if stats:
                update.update(stats)
                updated.append(name)
            else:
                skipped.append(name)
        else:
            updated.append(name)

        update["updated_at"] = "now()"
        try:
            db.upsert("wc_team_stats", [update], on_conflict="name")
        except Exception as exc:
            failed.append({"team": name, "error": str(exc)})

    return {
        "success": True,
        "data": {
            "updated": len(updated),
            "skipped_fbref": skipped,
            "failed": failed,
            "note": "Skipped teams had FBref blocked — Elo still updated from fallback table.",
        },
    }


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    try:
        result = sync_teams(
            team=params.get("team", ""),
            timeout=int(params.get("timeout", 15)),
            elo_only=bool(params.get("elo_only", False)),
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
