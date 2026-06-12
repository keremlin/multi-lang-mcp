"""
WC_predict_outcome — win / draw / loss probability model.

Combines three signals:
  1. Elo gap          (primary signal)
  2. Recent form      (WWDLW strings, weighted exponentially)
  3. Goals model      (attack/defense strength → Poisson lambda → outcome probs)

All three are blended with configurable weights.

Input (stdin JSON):
  team_a          str    Team A name (label only)
  team_b          str    Team B name (label only)
  elo_a           float  Team A Elo rating (e.g. 2050)
  elo_b           float  Team B Elo rating (e.g. 1980)
  form_a          str    Recent form string for A (e.g. "WWDWL"), newest last
  form_b          str    Recent form string for B (e.g. "WLWDW"), newest last
  avg_gf_a        float  Team A avg goals scored (optional, enables goals model)
  avg_ga_a        float  Team A avg goals conceded (optional)
  avg_gf_b        float  Team B avg goals scored (optional)
  avg_ga_b        float  Team B avg goals conceded (optional)
  home_advantage  float  Extra Elo points for team A if playing at home (default 0 for WC neutral)
  draw_base       float  Base draw probability (default 0.28)
  form_weight     float  How much form adjusts Elo probs (default 0.15)
  goals_blend     float  Weight of goal-based probs vs Elo probs (0–1, default 0.3)

Output:
  {
    "success": true,
    "data": {
      "team_a": ..., "team_b": ...,
      "elo_diff": ...,
      "elo_probs":   { "team_a_win": %, "draw": %, "team_b_win": % },
      "form_probs":  { ... },   // after form adjustment
      "goals_probs": { ... },   // Poisson model (if goal data provided)
      "final_probs": { ... },   // blended recommendation
      "lambda_a": ..., "lambda_b": ...,   // expected goals
      "verdict": "Team A favoured / Even match / ..."
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

from shared.wc_models import (
    elo_to_probabilities,
    form_adjusted_probs,
    compute_lambda,
    compute_score_matrix,
    score_matrix_to_outcomes,
)

logger = logging.getLogger(__name__)


def _pct(v: float) -> float:
    return round(v * 100, 1)


def predict_outcome(
    team_a: str,
    team_b: str,
    elo_a: float,
    elo_b: float,
    form_a: str = "",
    form_b: str = "",
    avg_gf_a: float | None = None,
    avg_ga_a: float | None = None,
    avg_gf_b: float | None = None,
    avg_ga_b: float | None = None,
    home_adv: float = 0.0,
    draw_base: float = 0.28,
    form_weight: float = 0.15,
    goals_blend: float = 0.30,
) -> dict:
    # 1) Elo probabilities
    pw_elo, pd_elo, pl_elo = elo_to_probabilities(elo_a, elo_b, home_adv, draw_base)

    # 2) Form-adjusted probabilities
    if form_a or form_b:
        pw_form, pd_form, pl_form = form_adjusted_probs(
            pw_elo, pd_elo, pl_elo, form_a, form_b, form_weight
        )
    else:
        pw_form, pd_form, pl_form = pw_elo, pd_elo, pl_elo

    # 3) Goals-based Poisson probabilities
    has_goal_data = all(v is not None for v in [avg_gf_a, avg_ga_a, avg_gf_b, avg_ga_b])
    lambda_a = lambda_b = None
    if has_goal_data:
        lambda_a = compute_lambda(avg_gf_a, avg_ga_b)
        lambda_b = compute_lambda(avg_gf_b, avg_ga_a)
        matrix = compute_score_matrix(lambda_a, lambda_b)
        pw_goals, pd_goals, pl_goals = score_matrix_to_outcomes(matrix)
    else:
        pw_goals, pd_goals, pl_goals = pw_form, pd_form, pl_form
        goals_blend = 0.0

    # 4) Blend form-adjusted and goals-based
    blend = goals_blend if has_goal_data else 0.0
    pw_final = (1 - blend) * pw_form + blend * pw_goals
    pd_final = (1 - blend) * pd_form + blend * pd_goals
    pl_final = (1 - blend) * pl_form + blend * pl_goals
    total = pw_final + pd_final + pl_final
    pw_final, pd_final, pl_final = pw_final / total, pd_final / total, pl_final / total

    # 5) Verdict
    diff = elo_a - elo_b
    if diff > 150:
        verdict = f"{team_a} strongly favoured (Elo +{diff:.0f})"
    elif diff > 60:
        verdict = f"{team_a} moderately favoured (Elo +{diff:.0f})"
    elif diff > -60:
        verdict = "Even match — small edge depends on form"
    elif diff > -150:
        verdict = f"{team_b} moderately favoured (Elo {diff:.0f})"
    else:
        verdict = f"{team_b} strongly favoured (Elo {diff:.0f})"

    result = {
        "team_a": team_a,
        "team_b": team_b,
        "elo_a": elo_a,
        "elo_b": elo_b,
        "elo_diff": round(elo_a - elo_b, 1),
        "elo_probs": {
            f"{team_a}_win": _pct(pw_elo),
            "draw": _pct(pd_elo),
            f"{team_b}_win": _pct(pl_elo),
        },
        "form_probs": {
            f"{team_a}_win": _pct(pw_form),
            "draw": _pct(pd_form),
            f"{team_b}_win": _pct(pl_form),
        },
        "final_probs": {
            f"{team_a}_win": _pct(pw_final),
            "draw": _pct(pd_final),
            f"{team_b}_win": _pct(pl_final),
        },
        "verdict": verdict,
    }

    if has_goal_data:
        result["lambda_a"] = round(lambda_a, 3)
        result["lambda_b"] = round(lambda_b, 3)
        result["goals_probs"] = {
            f"{team_a}_win": _pct(pw_goals),
            "draw": _pct(pd_goals),
            f"{team_b}_win": _pct(pl_goals),
        }
        result["goals_blend_used"] = round(blend, 2)

    if form_a:
        result["form_a"] = form_a
    if form_b:
        result["form_b"] = form_b

    return {"success": True, "data": result}


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No JSON input. Required: {team_a, team_b, elo_a, elo_b}"}))
        sys.exit(1)
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    required = ["team_a", "team_b", "elo_a", "elo_b"]
    missing = [k for k in required if k not in p]
    if missing:
        print(json.dumps({"success": False, "error": f"Missing fields: {missing}"}))
        sys.exit(1)

    try:
        result = predict_outcome(
            team_a=str(p["team_a"]),
            team_b=str(p["team_b"]),
            elo_a=float(p["elo_a"]),
            elo_b=float(p["elo_b"]),
            form_a=str(p.get("form_a", "")),
            form_b=str(p.get("form_b", "")),
            avg_gf_a=float(p["avg_gf_a"]) if "avg_gf_a" in p else None,
            avg_ga_a=float(p["avg_ga_a"]) if "avg_ga_a" in p else None,
            avg_gf_b=float(p["avg_gf_b"]) if "avg_gf_b" in p else None,
            avg_ga_b=float(p["avg_ga_b"]) if "avg_ga_b" in p else None,
            home_adv=float(p.get("home_advantage", 0.0)),
            draw_base=float(p.get("draw_base", 0.28)),
            form_weight=float(p.get("form_weight", 0.15)),
            goals_blend=float(p.get("goals_blend", 0.30)),
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
