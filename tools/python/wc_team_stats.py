"""
WC_team_stats — fetch a team's recent form and goal statistics from FBref.

Input (stdin JSON):
  team        str   Team name as it appears in FBref (e.g. "Argentina")
  league      str   soccerdata league string (default "INT-World Cup")
  season      str   Season year string (default "2026")
  n_recent    int   How many recent completed matches to analyse (default 10)

Output (stdout JSON):
  {"success": true, "data": { form, wins, draws, losses, avg_goals_scored, ... }}
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


def _col(df_cols, *keywords) -> str | None:
    """Return first column whose lowercase name contains ALL keywords."""
    for col in df_cols:
        cl = col.lower()
        if all(k in cl for k in keywords):
            return col
    return None


def fetch_team_stats(
    team: str,
    league: str = _DEFAULT_LEAGUE,
    season: str = _DEFAULT_SEASON,
    n_recent: int = 10,
) -> dict:
    try:
        import soccerdata as sd
        import pandas as pd
    except ImportError as e:
        return {"success": False, "error": f"soccerdata not installed: {e}. Run: pip install soccerdata"}

    try:
        fbref = sd.FBref(leagues=[league], seasons=[season])
        schedule = fbref.read_schedule()
        df = schedule.reset_index()

        home_col = _col(df.columns, "home", "team")
        away_col = _col(df.columns, "away", "team")
        home_score_col = _col(df.columns, "home", "score") or _col(df.columns, "home", "goal")
        away_score_col = _col(df.columns, "away", "score") or _col(df.columns, "away", "goal")

        if not home_col or not away_col:
            return {
                "success": False,
                "error": "Unexpected FBref column layout",
                "available_columns": list(df.columns),
            }

        team_lc = team.lower()
        mask = (
            df[home_col].str.lower().str.contains(team_lc, na=False)
            | df[away_col].str.lower().str.contains(team_lc, na=False)
        )
        games = df[mask].copy()

        if games.empty:
            all_teams = sorted(
                set(df[home_col].dropna().tolist()) | set(df[away_col].dropna().tolist())
            )
            similar = [t for t in all_teams if team_lc[:4] in t.lower()][:8]
            return {
                "success": False,
                "error": f"No matches found for '{team}' in {league} {season}",
                "similar_teams": similar,
                "hint": "Try available_leagues() on FBref or check the team name spelling",
            }

        # Keep only completed matches (have scores)
        if home_score_col and away_score_col:
            games = games.dropna(subset=[home_score_col, away_score_col])

        recent = games.tail(n_recent)

        results, gf_list, ga_list, detail = [], [], [], []
        for _, row in recent.iterrows():
            ht = str(row.get(home_col, ""))
            at = str(row.get(away_col, ""))
            try:
                hs = int(float(row[home_score_col])) if home_score_col else 0
                as_ = int(float(row[away_score_col])) if away_score_col else 0
            except (ValueError, TypeError, KeyError):
                continue

            is_home = team_lc in ht.lower()
            gf = hs if is_home else as_
            ga = as_ if is_home else hs
            opp = at if is_home else ht
            r = "W" if gf > ga else ("D" if gf == ga else "L")
            results.append(r)
            gf_list.append(gf)
            ga_list.append(ga)
            detail.append({
                "opponent": opp,
                "score": f"{gf}-{ga}",
                "result": r,
                "venue": "H" if is_home else "A",
            })

        n = len(results)
        if n == 0:
            return {"success": False, "error": f"No completed matches found for '{team}'"}

        w, d, l = results.count("W"), results.count("D"), results.count("L")
        avg_gf = round(sum(gf_list) / n, 2)
        avg_ga = round(sum(ga_list) / n, 2)

        return {
            "success": True,
            "data": {
                "team": team,
                "league": league,
                "season": season,
                "matches_analyzed": n,
                "form_last5": "".join(results[-5:]),
                "form_full": "".join(results),
                "wins": w,
                "draws": d,
                "losses": l,
                "win_rate": round(w / n, 3),
                "draw_rate": round(d / n, 3),
                "loss_rate": round(l / n, 3),
                "avg_goals_scored": avg_gf,
                "avg_goals_conceded": avg_ga,
                "goal_diff_avg": round(avg_gf - avg_ga, 2),
                "points_per_game": round((w * 3 + d) / n, 2),
                "clean_sheets": sum(1 for g in ga_list if g == 0),
                "failed_to_score": sum(1 for g in gf_list if g == 0),
                "recent_results": detail,
            },
        }

    except Exception as exc:
        return {"success": False, "error": str(exc)}


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No JSON input. Required: {team}"}))
        sys.exit(1)
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    team = params.get("team", "").strip()
    if not team:
        print(json.dumps({"success": False, "error": "'team' is required"}))
        sys.exit(1)

    result = fetch_team_stats(
        team=team,
        league=params.get("league", _DEFAULT_LEAGUE),
        season=str(params.get("season", _DEFAULT_SEASON)),
        n_recent=int(params.get("n_recent", 10)),
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
