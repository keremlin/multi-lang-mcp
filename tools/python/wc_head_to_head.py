"""
WC_head_to_head — historical head-to-head record between two teams from FBref.

Input (stdin JSON):
  team_a      str   First team name (e.g. "Argentina")
  team_b      str   Second team name (e.g. "Germany")
  league      str   FBref league string (default "INT-World Cup")
  season      str   Season year string (default "2026"); leave empty for all seasons
  n_matches   int   Max recent H2H matches to return (default 20)

Output:
  {
    "success": true,
    "data": {
      "team_a": ..., "team_b": ...,
      "matches_found": N,
      "team_a_wins": W, "draws": D, "team_b_wins": L,
      "avg_goals_a": X, "avg_goals_b": Y,
      "matches": [...]
    }
  }
"""
import sys
import json
import logging
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)

_DEFAULT_LEAGUE = "INT-World Cup"
_DEFAULT_SEASON = "2026"


def _col(cols, *keywords) -> str | None:
    for col in cols:
        cl = col.lower()
        if all(k in cl for k in keywords):
            return col
    return None


def fetch_head_to_head(
    team_a: str,
    team_b: str,
    league: str = _DEFAULT_LEAGUE,
    season: str = _DEFAULT_SEASON,
    n_matches: int = 20,
) -> dict:
    try:
        import soccerdata as sd
    except ImportError as e:
        return {"success": False, "error": f"soccerdata not installed: {e}"}

    try:
        seasons_arg = [season] if season else None
        fbref = sd.FBref(leagues=[league], seasons=seasons_arg)
        df = fbref.read_schedule().reset_index()

        home_col = _col(df.columns, "home", "team")
        away_col = _col(df.columns, "away", "team")
        hs_col = _col(df.columns, "home", "score") or _col(df.columns, "home", "goal")
        as_col = _col(df.columns, "away", "score") or _col(df.columns, "away", "goal")
        date_col = _col(df.columns, "date") or next(
            (c for c in df.columns if "date" in c.lower()), None
        )

        if not home_col or not away_col:
            return {"success": False, "error": f"Unexpected columns: {list(df.columns)}"}

        a_lc, b_lc = team_a.lower(), team_b.lower()

        mask = (
            (
                df[home_col].str.lower().str.contains(a_lc, na=False)
                & df[away_col].str.lower().str.contains(b_lc, na=False)
            )
            | (
                df[home_col].str.lower().str.contains(b_lc, na=False)
                & df[away_col].str.lower().str.contains(a_lc, na=False)
            )
        )
        h2h = df[mask].copy()

        if h2h.empty:
            return {
                "success": False,
                "error": f"No H2H matches found between '{team_a}' and '{team_b}' in {league}",
                "hint": "Try a broader league or an empty season to search all seasons",
            }

        # Keep only completed
        if hs_col and as_col:
            h2h = h2h.dropna(subset=[hs_col, as_col])

        h2h = h2h.tail(n_matches)

        wins_a, draws, wins_b = 0, 0, 0
        gf_a_list, gf_b_list, records = [], [], []

        for _, row in h2h.iterrows():
            ht = str(row.get(home_col, ""))
            at = str(row.get(away_col, ""))
            try:
                hs = int(float(row[hs_col])) if hs_col else 0
                as_ = int(float(row[as_col])) if as_col else 0
            except (ValueError, TypeError, KeyError):
                continue

            a_is_home = a_lc in ht.lower()
            ga = hs if a_is_home else as_
            gb = as_ if a_is_home else hs
            gf_a_list.append(ga)
            gf_b_list.append(gb)

            if ga > gb:
                wins_a += 1
                result = f"{team_a} win"
            elif ga == gb:
                draws += 1
                result = "Draw"
            else:
                wins_b += 1
                result = f"{team_b} win"

            rec = {
                "home": ht,
                "away": at,
                "score": f"{hs}-{as_}",
                f"{team_a}_goals": ga,
                f"{team_b}_goals": gb,
                "result": result,
            }
            if date_col:
                rec["date"] = str(row.get(date_col, ""))
            records.append(rec)

        n = len(records)
        if n == 0:
            return {"success": False, "error": "No completed H2H matches found"}

        return {
            "success": True,
            "data": {
                "team_a": team_a,
                "team_b": team_b,
                "league": league,
                "season": season or "all",
                "matches_found": n,
                f"{team_a}_wins": wins_a,
                "draws": draws,
                f"{team_b}_wins": wins_b,
                f"avg_goals_{team_a}": round(sum(gf_a_list) / n, 2),
                f"avg_goals_{team_b}": round(sum(gf_b_list) / n, 2),
                "avg_total_goals": round((sum(gf_a_list) + sum(gf_b_list)) / n, 2),
                "matches": records,
            },
        }

    except Exception as exc:
        return {"success": False, "error": str(exc)}


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No JSON input. Required: {team_a, team_b}"}))
        sys.exit(1)
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    team_a = params.get("team_a", "").strip()
    team_b = params.get("team_b", "").strip()
    if not team_a or not team_b:
        print(json.dumps({"success": False, "error": "'team_a' and 'team_b' are required"}))
        sys.exit(1)

    result = fetch_head_to_head(
        team_a=team_a,
        team_b=team_b,
        league=params.get("league", _DEFAULT_LEAGUE),
        season=str(params.get("season", _DEFAULT_SEASON)),
        n_matches=int(params.get("n_matches", 20)),
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
