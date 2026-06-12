"""
WC_analyze_match — full World Cup match analysis orchestrator.

Internally calls all WC sub-tools and synthesises a complete betting analysis:
  1. Fetch form & goals for team_a  (FBref via wc_team_stats)
  2. Fetch form & goals for team_b  (FBref via wc_team_stats)
  3. Fetch national Elo for both    (eloratings.net via wc_elo_rating)
  4. Fetch H2H history              (FBref via wc_head_to_head)
  5. Predict win/draw/loss          (wc_predict_outcome)
  6. Predict score distribution     (wc_predict_score)

Input (stdin JSON):
  team_a          str    Team A name (e.g. "Argentina")
  team_b          str    Team B name (e.g. "Germany")
  league          str    FBref league string (default "INT-World Cup")
  season          str    Season year (default "2026")
  elo_a           float  Override Elo for team A (optional — fetched if omitted)
  elo_b           float  Override Elo for team B (optional — fetched if omitted)
  n_recent        int    Recent matches for form analysis (default 10)
  home_advantage  float  Elo bonus for team A if home advantage applies (default 0)

Output:
  {
    "success": true,
    "data": {
      "match": "Argentina vs Germany",
      "team_a_stats": {...},
      "team_b_stats": {...},
      "elo": {...},
      "head_to_head": {...},
      "prediction": {
        "outcome_probs": {...},
        "score_distribution": {...},
        "markets": {...}
      },
      "betting_summary": "..."
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

from tools.python.wc_team_stats import fetch_team_stats
from tools.python.wc_elo_rating import fetch_elo_ratings
from tools.python.wc_head_to_head import fetch_head_to_head
from tools.python.wc_predict_outcome import predict_outcome
from tools.python.wc_predict_score import predict_score
from shared.wc_models import compute_lambda

logger = logging.getLogger(__name__)

_DEFAULT_LEAGUE = "INT-World Cup"
_DEFAULT_SEASON = "2026"

# Approximate Elo fallbacks for major 2026 WC teams (used when scraping fails)
_ELO_FALLBACK = {
    "argentina": 2141, "france": 2086, "england": 2065, "spain": 2047,
    "brazil": 2026, "portugal": 1985, "netherlands": 1984, "germany": 1978,
    "belgium": 1966, "italy": 1963, "croatia": 1956, "uruguay": 1954,
    "colombia": 1935, "mexico": 1901, "usa": 1891, "senegal": 1884,
    "morocco": 1882, "japan": 1878, "south korea": 1862, "australia": 1845,
    "poland": 1858, "switzerland": 1895, "denmark": 1910, "austria": 1879,
    "turkey": 1868, "iran": 1860, "nigeria": 1855, "ecuador": 1851,
    "chile": 1871, "canada": 1866, "peru": 1848, "ghana": 1839,
}


def _lookup_elo_fallback(team: str) -> float | None:
    return _ELO_FALLBACK.get(team.lower().strip())


def _extract_elo_from_result(result: dict, team: str) -> float | None:
    """Try to pull a numeric Elo rating from a wc_elo_rating response."""
    if not result.get("success"):
        return None
    data = result.get("data", {})
    matches = data.get("matches", [])
    for entry in matches:
        if isinstance(entry, dict):
            for key in ("elo", "rating", "Elo", "Rating"):
                val = entry.get(key)
                if val is not None:
                    try:
                        return float(str(val).replace(",", ""))
                    except ValueError:
                        pass
            # Try parsing raw text entries
            for v in entry.values():
                try:
                    f = float(str(v).replace(",", ""))
                    if 1500 < f < 2500:  # plausible Elo range
                        return f
                except ValueError:
                    pass
    return None


def _betting_summary(
    team_a: str, team_b: str,
    pw: float, pd: float, pl: float,
    lambda_a: float, lambda_b: float,
    top: list,
    markets: dict,
    elo_diff: float,
) -> str:
    lines = [f"=== {team_a} vs {team_b} — Betting Summary ==="]

    lines.append(f"\nOutcome probabilities:")
    lines.append(f"  {team_a} win : {pw}%")
    lines.append(f"  Draw        : {pd}%")
    lines.append(f"  {team_b} win : {pl}%")

    if abs(elo_diff) > 120:
        fav = team_a if elo_diff > 0 else team_b
        lines.append(f"\n⚡ Clear favourite: {fav} (Elo gap {abs(elo_diff):.0f})")
    elif abs(elo_diff) < 40:
        lines.append(f"\n⚖  Very even match — draw or small-margin win most likely")

    lines.append(f"\nExpected goals: {team_a} {lambda_a:.2f}  |  {team_b} {lambda_b:.2f}")
    lines.append(f"\nTop-5 most probable scores:")
    for s in top[:5]:
        lines.append(f"  {s['score']:>5}  {s['probability_pct']:.1f}%")

    lines.append(f"\nKey markets:")
    lines.append(f"  Over 1.5 goals : {markets.get('over_1_5_pct', '?')}%")
    lines.append(f"  Over 2.5 goals : {markets.get('over_2_5_pct', '?')}%")
    lines.append(f"  Both teams score (BTTS): {markets.get('btts_pct', '?')}%")
    lines.append(f"  Under 2.5 goals: {markets.get('under_2_5_pct', '?')}%")

    lines.append(
        "\n⚠  These are model probabilities, not guarantees. "
        "Compare to bookmaker odds to find value bets."
    )
    return "\n".join(lines)


def analyze_match(
    team_a: str,
    team_b: str,
    league: str = _DEFAULT_LEAGUE,
    season: str = _DEFAULT_SEASON,
    elo_a_override: float | None = None,
    elo_b_override: float | None = None,
    n_recent: int = 10,
    home_adv: float = 0.0,
) -> dict:
    report = {}

    # --- Step 1 & 2: Team stats ---
    stats_a = fetch_team_stats(team_a, league, season, n_recent)
    stats_b = fetch_team_stats(team_b, league, season, n_recent)
    report["team_a_stats"] = stats_a.get("data") if stats_a.get("success") else {"error": stats_a.get("error")}
    report["team_b_stats"] = stats_b.get("data") if stats_b.get("success") else {"error": stats_b.get("error")}

    # Extract form strings
    form_a = (stats_a.get("data") or {}).get("form_last5", "")
    form_b = (stats_b.get("data") or {}).get("form_last5", "")

    # Extract goal averages
    data_a = stats_a.get("data") or {}
    data_b = stats_b.get("data") or {}
    avg_gf_a = data_a.get("avg_goals_scored")
    avg_ga_a = data_a.get("avg_goals_conceded")
    avg_gf_b = data_b.get("avg_goals_scored")
    avg_ga_b = data_b.get("avg_goals_conceded")

    # --- Step 3: Elo ratings ---
    elo_info = {}
    if elo_a_override is not None:
        elo_a = elo_a_override
        elo_info["team_a_elo"] = elo_a
        elo_info["team_a_source"] = "manual override"
    else:
        elo_res_a = fetch_elo_ratings(team=team_a)
        elo_a = _extract_elo_from_result(elo_res_a, team_a)
        if elo_a is None:
            elo_a = _lookup_elo_fallback(team_a)
            elo_info["team_a_elo"] = elo_a
            elo_info["team_a_source"] = "fallback table" if elo_a else "unavailable"
        else:
            elo_info["team_a_elo"] = elo_a
            elo_info["team_a_source"] = "eloratings.net"

    if elo_b_override is not None:
        elo_b = elo_b_override
        elo_info["team_b_elo"] = elo_b
        elo_info["team_b_source"] = "manual override"
    else:
        elo_res_b = fetch_elo_ratings(team=team_b)
        elo_b = _extract_elo_from_result(elo_res_b, team_b)
        if elo_b is None:
            elo_b = _lookup_elo_fallback(team_b)
            elo_info["team_b_elo"] = elo_b
            elo_info["team_b_source"] = "fallback table" if elo_b else "unavailable"
        else:
            elo_info["team_b_elo"] = elo_b
            elo_info["team_b_source"] = "eloratings.net"

    report["elo"] = elo_info

    if elo_a is None or elo_b is None:
        return {
            "success": False,
            "error": (
                f"Elo rating unavailable for "
                f"{'team_a' if elo_a is None else 'team_b'}. "
                "Provide elo_a / elo_b manually in the request."
            ),
            "partial_report": report,
        }

    # --- Step 4: Head-to-head ---
    h2h = fetch_head_to_head(team_a, team_b, league, season, n_matches=20)
    report["head_to_head"] = h2h.get("data") if h2h.get("success") else {"error": h2h.get("error")}

    # --- Step 5: Predict outcome ---
    outcome = predict_outcome(
        team_a=team_a, team_b=team_b,
        elo_a=elo_a, elo_b=elo_b,
        form_a=form_a, form_b=form_b,
        avg_gf_a=avg_gf_a, avg_ga_a=avg_ga_a,
        avg_gf_b=avg_gf_b, avg_ga_b=avg_ga_b,
        home_adv=home_adv,
    )

    # --- Step 6: Predict score ---
    has_goals = all(v is not None for v in [avg_gf_a, avg_ga_a, avg_gf_b, avg_ga_b])
    if has_goals:
        la = compute_lambda(avg_gf_a, avg_ga_b)
        lb = compute_lambda(avg_gf_b, avg_ga_a)
    else:
        # Estimate lambdas from Elo (rough heuristic: avg WC is ~1.3 gpg)
        elo_ratio = 10 ** ((elo_a - elo_b) / 400)
        la = round(1.3 * elo_ratio / (1 + elo_ratio), 2)
        lb = round(1.3 / (1 + elo_ratio), 2)

    score_dist = predict_score(
        lambda_a=la, lambda_b=lb,
        team_a=team_a, team_b=team_b,
    )

    final = (outcome.get("data") or {}).get("final_probs", {})
    pw = final.get(f"{team_a}_win", 0)
    pd = final.get("draw", 0)
    pl = final.get(f"{team_b}_win", 0)
    markets = (score_dist.get("data") or {}).get("markets", {})
    top = (score_dist.get("data") or {}).get("top_scores", [])

    report["prediction"] = {
        "outcome_probs": final,
        "expected_goals": {"lambda_a": la, "lambda_b": lb},
        "score_distribution": top,
        "markets": markets,
        "full_outcome_detail": outcome.get("data"),
    }
    report["betting_summary"] = _betting_summary(
        team_a, team_b, pw, pd, pl, la, lb, top, markets, elo_a - elo_b
    )
    report["match"] = f"{team_a} vs {team_b}"
    report["league"] = league
    report["season"] = season

    return {"success": True, "data": report}


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No JSON input. Required: {team_a, team_b}"}))
        sys.exit(1)
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    team_a = p.get("team_a", "").strip()
    team_b = p.get("team_b", "").strip()
    if not team_a or not team_b:
        print(json.dumps({"success": False, "error": "'team_a' and 'team_b' are required"}))
        sys.exit(1)

    try:
        result = analyze_match(
            team_a=team_a,
            team_b=team_b,
            league=p.get("league", _DEFAULT_LEAGUE),
            season=str(p.get("season", _DEFAULT_SEASON)),
            elo_a_override=float(p["elo_a"]) if "elo_a" in p else None,
            elo_b_override=float(p["elo_b"]) if "elo_b" in p else None,
            n_recent=int(p.get("n_recent", 10)),
            home_adv=float(p.get("home_advantage", 0.0)),
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
