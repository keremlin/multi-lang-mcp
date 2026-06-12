"""
WC_schedule — fetch World Cup fixtures/results for a given date from soccerdata.

Tries sources in order: FBref → ESPN → Sofascore.
Returns all matches on the requested date with score (if finished) and status.

Input (stdin JSON):
  date      str   "YYYY-MM-DD" or "today" (default "today")
  league    str   soccerdata league string (default "INT-World Cup")
  season    str   Season year (default "2026")
  source    str   "fbref" | "espn" | "sofascore" | "auto" (default "auto")
  all       bool  Return ALL matches in the season, not just one date (default false)

Output:
  {
    "success": true,
    "data": {
      "date": "2026-06-12",
      "source": "FBref",
      "total": 3,
      "finished": 1,
      "upcoming": 2,
      "matches": [
        {
          "kickoff": "02:00",
          "home": "South Korea",
          "away": "Czech Republic",
          "score": "2-1",
          "status": "finished",
          "venue": "Estadio Akron",
          "group": "Group A"
        },
        ...
      ]
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


def _col(cols, *keywords):
    """Return first column name whose lowercase contains ALL keywords."""
    for col in cols:
        cl = col.lower()
        if all(k in cl for k in keywords):
            return col
    return None


def _parse_target_date(date_str: str) -> str:
    """Return a normalised YYYY-MM-DD string."""
    if not date_str or date_str.lower() == "today":
        return date.today().isoformat()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return date.today().isoformat()


def _build_match_record(row, home_col, away_col, hs_col, as_col,
                        date_col, time_col, venue_col, group_col, target_date):
    """Turn a schedule DataFrame row into a clean match dict."""
    home = str(row.get(home_col, ""))
    away = str(row.get(away_col, ""))

    # Score / status
    try:
        hs = int(float(row[hs_col])) if hs_col else None
        as_ = int(float(row[as_col])) if as_col else None
        finished = hs is not None and as_ is not None
    except (ValueError, TypeError, KeyError):
        hs = as_ = None
        finished = False

    rec = {
        "home": home,
        "away": away,
        "status": "finished" if finished else "upcoming",
    }
    if finished:
        rec["score"] = f"{hs}-{as_}"
        rec["home_goals"] = hs
        rec["away_goals"] = as_

    if date_col:
        rec["date"] = str(row.get(date_col, ""))
    if time_col:
        rec["kickoff"] = str(row.get(time_col, ""))
    if venue_col:
        rec["venue"] = str(row.get(venue_col, ""))
    if group_col:
        rec["group"] = str(row.get(group_col, ""))

    return rec


def _fetch_fbref(league, season, target_date, return_all):
    import soccerdata as sd

    fbref = sd.FBref(leagues=[league], seasons=[season])
    schedule = fbref.read_schedule()
    df = schedule.reset_index()

    home_col   = _col(df.columns, "home", "team")
    away_col   = _col(df.columns, "away", "team")
    hs_col     = _col(df.columns, "home", "score") or _col(df.columns, "home", "goal")
    as_col     = _col(df.columns, "away", "score") or _col(df.columns, "away", "goal")
    date_col   = _col(df.columns, "date")
    time_col   = _col(df.columns, "time")
    venue_col  = _col(df.columns, "venue") or _col(df.columns, "stadium") or _col(df.columns, "ground")
    group_col  = _col(df.columns, "round") or _col(df.columns, "group") or _col(df.columns, "stage")

    if not home_col or not away_col:
        return None, f"Unexpected FBref columns: {list(df.columns)}"

    if not return_all and date_col:
        # Normalise date column to YYYY-MM-DD strings for comparison
        try:
            import pandas as pd
            df["_norm_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date.astype(str)
            df = df[df["_norm_date"] == target_date]
        except Exception:
            # Fallback: string match
            df = df[df[date_col].astype(str).str.startswith(target_date)]

    if df.empty:
        return [], None  # no matches on this date (not an error)

    matches = []
    for _, row in df.iterrows():
        matches.append(_build_match_record(
            row, home_col, away_col, hs_col, as_col,
            date_col, time_col, venue_col, group_col, target_date
        ))

    return matches, None


def _fetch_espn(league, season, target_date, return_all):
    import soccerdata as sd

    espn = sd.ESPN(leagues=[league], seasons=[season])
    schedule = espn.read_schedule()
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
        return None, f"Unexpected ESPN columns: {list(df.columns)}"

    if not return_all and date_col:
        try:
            import pandas as pd
            df["_norm_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date.astype(str)
            df = df[df["_norm_date"] == target_date]
        except Exception:
            df = df[df[date_col].astype(str).str.startswith(target_date)]

    if df.empty:
        return [], None

    matches = []
    for _, row in df.iterrows():
        matches.append(_build_match_record(
            row, home_col, away_col, hs_col, as_col,
            date_col, time_col, venue_col, group_col, target_date
        ))

    return matches, None


def _fetch_sofascore(league, season, target_date, return_all):
    import soccerdata as sd

    ss = sd.Sofascore(leagues=[league], seasons=[season])
    schedule = ss.read_schedule()
    df = schedule.reset_index()

    home_col  = _col(df.columns, "home", "team")
    away_col  = _col(df.columns, "away", "team")
    hs_col    = _col(df.columns, "home", "score") or _col(df.columns, "home", "goal")
    as_col    = _col(df.columns, "away", "score") or _col(df.columns, "away", "goal")
    date_col  = _col(df.columns, "date")
    time_col  = _col(df.columns, "time")
    venue_col = _col(df.columns, "venue")
    group_col = _col(df.columns, "round") or _col(df.columns, "group")

    if not home_col or not away_col:
        return None, f"Unexpected Sofascore columns: {list(df.columns)}"

    if not return_all and date_col:
        try:
            import pandas as pd
            df["_norm_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date.astype(str)
            df = df[df["_norm_date"] == target_date]
        except Exception:
            df = df[df[date_col].astype(str).str.startswith(target_date)]

    if df.empty:
        return [], None

    matches = []
    for _, row in df.iterrows():
        matches.append(_build_match_record(
            row, home_col, away_col, hs_col, as_col,
            date_col, time_col, venue_col, group_col, target_date
        ))

    return matches, None


_SOURCE_MAP = {
    "fbref":     ("FBref",     _fetch_fbref),
    "espn":      ("ESPN",      _fetch_espn),
    "sofascore": ("Sofascore", _fetch_sofascore),
}


def fetch_schedule(
    date_str: str = "today",
    league: str = _DEFAULT_LEAGUE,
    season: str = _DEFAULT_SEASON,
    source: str = "auto",
    return_all: bool = False,
) -> dict:
    target_date = _parse_target_date(date_str)

    # Determine source order
    if source == "auto":
        order = ["fbref", "espn", "sofascore"]
    elif source in _SOURCE_MAP:
        order = [source]
    else:
        return {"success": False, "error": f"Unknown source '{source}'. Use: fbref, espn, sofascore, auto"}

    last_error = None
    for src_key in order:
        label, fetch_fn = _SOURCE_MAP[src_key]
        try:
            matches, err = fetch_fn(league, season, target_date, return_all)
            if err:
                last_error = f"{label}: {err}"
                continue
            if matches is None:
                last_error = f"{label}: returned no data"
                continue

            finished = sum(1 for m in matches if m.get("status") == "finished")
            upcoming = len(matches) - finished

            return {
                "success": True,
                "data": {
                    "date": target_date if not return_all else "all",
                    "league": league,
                    "season": season,
                    "source": label,
                    "total": len(matches),
                    "finished": finished,
                    "upcoming": upcoming,
                    "matches": matches,
                },
            }
        except Exception as exc:
            last_error = f"{label}: {exc}"
            logger.debug("Schedule fetch failed for %s: %s", label, exc)
            continue

    return {
        "success": False,
        "error": f"All sources failed. Last error: {last_error}",
        "tried": order,
        "hint": (
            "soccerdata may not have data for this league/season yet, "
            "or the website is temporarily unavailable. "
            f"League tried: '{league}', Season: '{season}'. "
            "Try source='espn' or source='sofascore' explicitly."
        ),
    }


def main():
    raw = sys.stdin.read().strip()
    params = {}
    if raw:
        try:
            params = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
            sys.exit(1)

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
