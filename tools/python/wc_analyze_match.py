"""
WC_analyze_match — full World Cup match analysis orchestrator.

Reads team data from Supabase (wc_team_stats, wc_head_to_head) — fast, no scraping.
Falls back to the built-in Elo table if a team is not in the DB.

Steps:
  1. Read team_a + team_b stats from Supabase wc_team_stats
  2. Read H2H record from wc_head_to_head
  3. Predict win/draw/loss (Elo + form + goals blend, H2H-adjusted)
  4. Predict score distribution (Poisson + Dixon-Coles)
  5. Return full betting summary

Input (stdin JSON):
  team_a          str    Team A name (e.g. "United States")
  team_b          str    Team B name (e.g. "Paraguay")
  elo_a           float  Override Elo for team A (optional)
  elo_b           float  Override Elo for team B (optional)
  home_advantage  float  Elo bonus for team A if home advantage (default 0)
  league          str    Unused — kept for API compatibility
  season          str    Unused — kept for API compatibility

Output:
  {
    "success": true,
    "data": {
      "match": "...",
      "team_a_stats": {elo, fifa_ranking, form_last5, form_last10, avg_goals_scored, ...},
      "team_b_stats": {...},
      "head_to_head": {played, team_a_wins, draws, team_b_wins, goals_a, goals_b, last_match},
      "prediction": {
        "outcome_probs": {...},
        "expected_goals": {...},
        "score_distribution": [...],
        "markets": {...},
        "h2h_adjustment_pct": N
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

from tools.python.wc_predict_outcome import predict_outcome
from tools.python.wc_predict_score import predict_score
from shared.wc_models import compute_lambda

logger = logging.getLogger(__name__)

# Elo fallback when team is not in DB
_ELO_FALLBACK = {
    "argentina": 2141, "france": 2086, "england": 2065, "spain": 2047,
    "brazil": 2026, "portugal": 1985, "netherlands": 1984, "germany": 1978,
    "belgium": 1966, "croatia": 1956, "uruguay": 1954, "colombia": 1935,
    "switzerland": 1895, "mexico": 1901, "united states": 1891, "senegal": 1884,
    "morocco": 1882, "sweden": 1893, "japan": 1878, "austria": 1879,
    "south korea": 1862, "iran": 1860, "norway": 1852, "australia": 1845,
    "ecuador": 1851, "turkey": 1868, "canada": 1866, "scotland": 1831,
    "paraguay": 1832, "czechia": 1828, "algeria": 1820, "ivory coast": 1798,
    "egypt": 1791, "bosnia-herzegovina": 1771, "ghana": 1839,
    "tunisia": 1748, "saudi arabia": 1748, "qatar": 1744, "south africa": 1652,
    "cape verde islands": 1718, "jordan": 1711, "iraq": 1712,
    "congo dr": 1698, "panama": 1699, "uzbekistan": 1681,
    "curaçao": 1581, "haiti": 1602, "new zealand": 1601,
}

_TEAM_ALIASES = {
    "usa": "united states", "us": "united states", "usmnt": "united states",
    "drc": "congo dr",
    "côte d'ivoire": "ivory coast",
    "czech republic": "czechia",
    "korea republic": "south korea",
    "bosnia": "bosnia-herzegovina",
}


def _get_team_from_db(team_name: str) -> dict | None:
    try:
        from shared.supabase_client import SupabaseClient
        rows = SupabaseClient().select("wc_team_stats", filters={"name": team_name})
        return rows[0] if rows else None
    except Exception as exc:
        logger.debug("DB team lookup failed for %s: %s", team_name, exc)
        return None


def _get_h2h(team_a: str, team_b: str) -> dict | None:
    """Fetch H2H record from wc_head_to_head (canonical alphabetical order in DB)."""
    try:
        from shared.supabase_client import SupabaseClient
        db_a, db_b = sorted([team_a, team_b])
        rows = SupabaseClient().select("wc_head_to_head",
                                       filters={"team_a": db_a, "team_b": db_b})
        if not rows:
            return None
        r = rows[0]
        # Return stats from team_a's perspective
        if db_a == team_a:
            return {
                "played":      r["played"],
                "team_a_wins": r["team_a_wins"],
                "draws":       r["draws"],
                "team_b_wins": r["team_b_wins"],
                "goals_a":     r["goals_a"],
                "goals_b":     r["goals_b"],
                "last_match":  r.get("last_match_date"),
            }
        else:
            return {
                "played":      r["played"],
                "team_a_wins": r["team_b_wins"],
                "draws":       r["draws"],
                "team_b_wins": r["team_a_wins"],
                "goals_a":     r["goals_b"],
                "goals_b":     r["goals_a"],
                "last_match":  r.get("last_match_date"),
            }
    except Exception as exc:
        logger.debug("H2H lookup failed %s vs %s: %s", team_a, team_b, exc)
        return None


def _resolve_elo(team_name: str, db_row: dict | None, override: float) -> tuple[float, str]:
    if override and override > 0:
        return float(override), "manual override"
    if db_row and db_row.get("elo"):
        return float(db_row["elo"]), "supabase"
    key = team_name.lower().strip()
    canonical = _TEAM_ALIASES.get(key, key)
    fallback = _ELO_FALLBACK.get(canonical)
    if fallback:
        return float(fallback), "fallback table"
    return None, "unavailable"


def _apply_h2h_adjustment(
    pw: float, pd: float, pl: float, h2h: dict | None
) -> tuple[float, float, float, float]:
    """
    Blend Elo-based outcome probs with historical H2H win rates.
    Weight scales from 0 (< 5 games) to max 15% (≥ 50 games).
    Returns (pw, pd, pl, h2h_weight_pct).
    """
    if not h2h or h2h["played"] < 5:
        return pw, pd, pl, 0.0

    played = h2h["played"]
    h2h_weight = min(0.15, played / 100 * 0.15 / 0.5)  # 0→15% over 0→50 games, capped at 15%
    h2h_weight = round(min(0.15, played / 333), 4)      # simpler: 15% at 50+ games

    h_pw = (h2h["team_a_wins"] / played) * 100
    h_pd = (h2h["draws"]       / played) * 100
    h_pl = (h2h["team_b_wins"] / played) * 100

    blended_w = pw * (1 - h2h_weight) + h_pw * h2h_weight
    blended_d = pd * (1 - h2h_weight) + h_pd * h2h_weight
    blended_l = pl * (1 - h2h_weight) + h_pl * h2h_weight

    # Renormalise
    total = blended_w + blended_d + blended_l
    blended_w, blended_d, blended_l = (
        round(blended_w / total * 100, 1),
        round(blended_d / total * 100, 1),
        round(blended_l / total * 100, 1),
    )
    return blended_w, blended_d, blended_l, round(h2h_weight * 100, 1)


def _betting_summary(
    team_a: str, team_b: str,
    pw: float, pd: float, pl: float,
    lambda_a: float, lambda_b: float,
    top: list, markets: dict, elo_diff: float,
    h2h: dict | None,
    ranking_a: int | None, ranking_b: int | None,
) -> str:
    lines = [f"=== {team_a} vs {team_b} — Betting Summary ==="]

    if ranking_a and ranking_b:
        lines.append(f"\nFIFA World Ranking:  {team_a} #{ranking_a}  |  {team_b} #{ranking_b}")

    lines.append(f"\nOutcome probabilities:")
    lines.append(f"  {team_a} win : {pw}%")
    lines.append(f"  Draw        : {pd}%")
    lines.append(f"  {team_b} win : {pl}%")

    if abs(elo_diff) > 120:
        fav = team_a if elo_diff > 0 else team_b
        lines.append(f"\nClear favourite: {fav} (Elo gap {abs(elo_diff):.0f})")
    elif abs(elo_diff) < 40:
        lines.append(f"\nVery even match — draw or small-margin win most likely")

    lines.append(f"\nExpected goals: {team_a} {lambda_a:.2f}  |  {team_b} {lambda_b:.2f}")

    if h2h and h2h["played"] >= 3:
        lines.append(f"\nHead-to-Head ({h2h['played']} matches):")
        lines.append(f"  {team_a} wins : {h2h['team_a_wins']}")
        lines.append(f"  Draws        : {h2h['draws']}")
        lines.append(f"  {team_b} wins : {h2h['team_b_wins']}")
        if h2h.get("last_match"):
            lines.append(f"  Last played  : {h2h['last_match']}")

    lines.append(f"\nTop-5 most probable scores:")
    for s in top[:5]:
        lines.append(f"  {s['score']:>5}  {s['probability_pct']:.1f}%")

    lines.append(f"\nKey markets:")
    lines.append(f"  Over 1.5 goals  : {markets.get('over_1_5_pct', '?')}%")
    lines.append(f"  Over 2.5 goals  : {markets.get('over_2_5_pct', '?')}%")
    lines.append(f"  Both score BTTS : {markets.get('btts_pct', '?')}%")
    lines.append(f"  Under 2.5 goals : {markets.get('under_2_5_pct', '?')}%")
    lines.append("\nThese are model probabilities, not guarantees.")
    return "\n".join(lines)


def analyze_match(
    team_a: str,
    team_b: str,
    elo_a_override: float = 0.0,
    elo_b_override: float = 0.0,
    home_adv: float = 0.0,
) -> dict:
    # 1 & 2 — Team stats + H2H from Supabase
    row_a = _get_team_from_db(team_a)
    row_b = _get_team_from_db(team_b)
    h2h   = _get_h2h(team_a, team_b)

    def _stat(row, key, default=None):
        return row.get(key) if row else default

    elo_a, source_a = _resolve_elo(team_a, row_a, elo_a_override)
    elo_b, source_b = _resolve_elo(team_b, row_b, elo_b_override)

    if elo_a is None or elo_b is None:
        missing = team_a if elo_a is None else team_b
        return {"success": False,
                "error": f"Elo unavailable for '{missing}'. Provide elo_a/elo_b manually."}

    form_a   = _stat(row_a, "form_last5", "")
    form_b   = _stat(row_b, "form_last5", "")
    avg_gf_a = _stat(row_a, "avg_goals_scored")
    avg_ga_a = _stat(row_a, "avg_goals_conceded")
    avg_gf_b = _stat(row_b, "avg_goals_scored")
    avg_ga_b = _stat(row_b, "avg_goals_conceded")

    rank_a = _stat(row_a, "fifa_ranking")
    rank_b = _stat(row_b, "fifa_ranking")

    team_a_info = {
        "team":               team_a,
        "elo":                elo_a,
        "elo_source":         source_a,
        "fifa_ranking":       rank_a,
        "group":              _stat(row_a, "group_name"),
        "form_last5":         form_a,
        "form_last10":        _stat(row_a, "form_last10", ""),
        "avg_goals_scored":   avg_gf_a,
        "avg_goals_conceded": avg_ga_a,
        "matches_analyzed":   _stat(row_a, "matches_analyzed", 0),
    }
    team_b_info = {
        "team":               team_b,
        "elo":                elo_b,
        "elo_source":         source_b,
        "fifa_ranking":       rank_b,
        "group":              _stat(row_b, "group_name"),
        "form_last5":         form_b,
        "form_last10":        _stat(row_b, "form_last10", ""),
        "avg_goals_scored":   avg_gf_b,
        "avg_goals_conceded": avg_ga_b,
        "matches_analyzed":   _stat(row_b, "matches_analyzed", 0),
    }

    # 3 — Outcome prediction (Elo + form + goals)
    outcome = predict_outcome(
        team_a=team_a, team_b=team_b,
        elo_a=elo_a, elo_b=elo_b,
        form_a=form_a or "", form_b=form_b or "",
        avg_gf_a=float(avg_gf_a) if avg_gf_a else None,
        avg_ga_a=float(avg_ga_a) if avg_ga_a else None,
        avg_gf_b=float(avg_gf_b) if avg_gf_b else None,
        avg_ga_b=float(avg_ga_b) if avg_ga_b else None,
        home_adv=home_adv,
    )
    final = (outcome.get("data") or {}).get("final_probs", {})
    pw  = final.get(f"{team_a}_win", 0)
    pd_ = final.get("draw", 0)
    pl  = final.get(f"{team_b}_win", 0)

    # Apply H2H adjustment (up to 15% weight when ≥ 50 games)
    pw, pd_, pl, h2h_adj = _apply_h2h_adjustment(pw, pd_, pl, h2h)
    adjusted_probs = {f"{team_a}_win": pw, "draw": pd_, f"{team_b}_win": pl}

    # 4 — Score distribution
    has_goals = all(v is not None for v in [avg_gf_a, avg_ga_a, avg_gf_b, avg_ga_b])
    if has_goals:
        la = compute_lambda(float(avg_gf_a), float(avg_ga_b))
        lb = compute_lambda(float(avg_gf_b), float(avg_ga_a))
    else:
        elo_ratio = 10 ** ((elo_a - elo_b) / 400)
        la = round(1.3 * elo_ratio / (1 + elo_ratio), 2)
        lb = round(1.3 / (1 + elo_ratio), 2)

    score_dist = predict_score(lambda_a=la, lambda_b=lb, team_a=team_a, team_b=team_b)
    markets = (score_dist.get("data") or {}).get("markets", {})
    top     = (score_dist.get("data") or {}).get("top_scores", [])

    return {
        "success": True,
        "data": {
            "match":       f"{team_a} vs {team_b}",
            "team_a_stats": team_a_info,
            "team_b_stats": team_b_info,
            "head_to_head": h2h,
            "prediction": {
                "outcome_probs":        adjusted_probs,
                "expected_goals":       {"lambda_a": la, "lambda_b": lb},
                "score_distribution":   top,
                "markets":              markets,
                "h2h_adjustment_pct":   h2h_adj,
                "full_outcome_detail":  outcome.get("data"),
            },
            "betting_summary": _betting_summary(
                team_a, team_b, pw, pd_, pl, la, lb, top, markets,
                elo_a - elo_b, h2h, rank_a, rank_b,
            ),
        },
    }


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
            elo_a_override=float(p.get("elo_a", 0) or 0),
            elo_b_override=float(p.get("elo_b", 0) or 0),
            home_adv=float(p.get("home_advantage", 0) or 0),
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
