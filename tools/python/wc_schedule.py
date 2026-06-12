"""
WC_schedule — fetch World Cup fixtures/results for a given date.

Primary source: Supabase DB (wc_matches table) — fast, no scraping.
Fallback: soccerdata scraping (WhoScored → FBref) if DB is empty.

Input (stdin JSON):
  date      str   "YYYY-MM-DD" or "today" (default "today")
  league    str   soccerdata league string used for fallback (default "INT-World Cup")
  season    str   Season year (default "2026")
  source    str   "db" | "scrape" | "auto" (default "auto" — DB first)
  all       bool  Return ALL matches in the season (default false)

Output:
  {
    "success": true,
    "data": {
      "date": "2026-06-12",
      "source": "supabase",
      "total": 3,
      "finished": 1,
      "upcoming": 2,
      "matches": [...]
    }
  }
"""
import sys
import json
import logging
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)

_DEFAULT_LEAGUE = "INT-World Cup"
_DEFAULT_SEASON = "2026"


def _parse_target_date(date_str: str) -> str:
    if not date_str or date_str.lower() == "today":
        return date.today().isoformat()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return date.today().isoformat()


def _from_supabase(target_date: str, return_all: bool):
    """Query wc_matches from Supabase. Returns (matches, error)."""
    try:
        from shared.supabase_client import SupabaseClient
        db = SupabaseClient()

        if return_all:
            rows = db.select("wc_matches", order="match_date,kickoff_time")
        else:
            rows = db.select(
                "wc_matches",
                filters={"match_date": target_date},
                order="kickoff_time",
            )

        matches = []
        for row in rows:
            m = {
                "home": row.get("home_team", ""),
                "away": row.get("away_team", ""),
                "status": row.get("status", "upcoming"),
                "date": row.get("match_date", ""),
            }
            if row.get("kickoff_time"):
                m["kickoff"] = row["kickoff_time"]
            if row.get("venue"):
                m["venue"] = row["venue"]
            if row.get("group_name"):
                m["group"] = row["group_name"]
            if row.get("stage"):
                m["stage"] = row["stage"]
            if row.get("status") == "finished":
                hg = row.get("home_goals")
                ag = row.get("away_goals")
                if hg is not None and ag is not None:
                    m["score"] = f"{hg}-{ag}"
                    m["home_goals"] = hg
                    m["away_goals"] = ag
            matches.append(m)

        return matches, None
    except Exception as exc:
        return None, str(exc)


def _col(cols, *keywords):
    for col in cols:
        cl = col.lower()
        if all(k in cl for k in keywords):
            return col
    return None


def _fetch_scrape(league: str, season: str, target_date: str, return_all: bool):
    """Fallback: scrape from soccerdata WhoScored → FBref."""
    import soccerdata as sd
    import pandas as pd

    sources = [
        ("WhoScored", lambda: sd.WhoScored(leagues=[league], seasons=[season])),
        ("FBref",     lambda: sd.FBref(leagues=[league], seasons=[season])),
    ]
    for label, factory in sources:
        try:
            src = factory()
            schedule = src.read_schedule()
            df = schedule.reset_index()

            home_col  = _col(df.columns, "home", "team")
            away_col  = _col(df.columns, "away", "team")
            hs_col    = _col(df.columns, "home", "score") or _col(df.columns, "home", "goal")
            as_col    = _col(df.columns, "away", "score") or _col(df.columns, "away", "goal")
            date_col  = _col(df.columns, "date")
            time_col  = _col(df.columns, "time")
            venue_col = _col(df.columns, "venue") or _col(df.columns, "stadium")
            group_col = _col(df.columns, "round") or _col(df.columns, "group")

            if not home_col or not away_col:
                continue

            if not return_all and date_col:
                df["_nd"] = pd.to_datetime(df[date_col], errors="coerce").dt.date.astype(str)
                df = df[df["_nd"] == target_date]

            matches = []
            for _, row in df.iterrows():
                try:
                    hs = int(float(row[hs_col])) if hs_col else None
                    as_ = int(float(row[as_col])) if as_col else None
                    finished = hs is not None and as_ is not None
                except Exception:
                    hs = as_ = None
                    finished = False

                m = {
                    "home": str(row.get(home_col, "")),
                    "away": str(row.get(away_col, "")),
                    "status": "finished" if finished else "upcoming",
                }
                if finished:
                    m["score"] = f"{hs}-{as_}"
                    m["home_goals"] = hs
                    m["away_goals"] = as_
                if date_col:
                    m["date"] = str(row.get(date_col, ""))
                if time_col:
                    m["kickoff"] = str(row.get(time_col, ""))
                if venue_col:
                    m["venue"] = str(row.get(venue_col, ""))
                if group_col:
                    m["group"] = str(row.get(group_col, ""))
                matches.append(m)

            return matches, None
        except Exception as exc:
            logger.debug("%s scrape failed: %s", label, exc)
            continue

    return None, "All scrape sources failed"


def fetch_schedule(
    date_str: str = "today",
    league: str = _DEFAULT_LEAGUE,
    season: str = _DEFAULT_SEASON,
    source: str = "auto",
    return_all: bool = False,
) -> dict:
    target_date = _parse_target_date(date_str)

    matches = None
    used_source = None
    last_error = None

    # --- Try Supabase DB first ---
    if source in ("auto", "db"):
        rows, err = _from_supabase(target_date, return_all)
        if rows is not None:
            matches = rows
            used_source = "supabase"
        else:
            last_error = f"Supabase: {err}"

    # --- Fallback to scraping ---
    if matches is None and source in ("auto", "scrape"):
        rows, err = _fetch_scrape(league, season, target_date, return_all)
        if rows is not None:
            matches = rows
            used_source = "scrape (WhoScored/FBref)"
        else:
            last_error = err

    if matches is None:
        return {
            "success": False,
            "error": f"No data available. {last_error}",
            "hint": "Run WC_db_sync first to populate the database.",
        }

    finished = sum(1 for m in matches if m.get("status") == "finished")
    upcoming = len(matches) - finished

    return {
        "success": True,
        "data": {
            "date": target_date if not return_all else "all",
            "league": league,
            "season": season,
            "source": used_source,
            "total": len(matches),
            "finished": finished,
            "upcoming": upcoming,
            "matches": matches,
        },
    }


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    result = fetch_schedule(
        date_str=str(params.get("date", "today")),
        league=params.get("league", _DEFAULT_LEAGUE),
        season=str(params.get("season", _DEFAULT_SEASON)),
        source=params.get("source", "auto"),
        return_all=bool(params.get("all", False)),
    )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
