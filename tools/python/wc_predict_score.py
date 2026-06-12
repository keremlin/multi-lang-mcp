"""
WC_predict_score — exact-score probability distribution using Poisson + Dixon-Coles.

Given expected goals (lambdas) for each team, computes P(score = i-j) for all
score combinations up to max_goals, applies the Dixon-Coles low-score correction,
and returns the top-N most likely scores plus overall outcome probabilities.

Input (stdin JSON):
  lambda_a        float  Expected goals for team A (e.g. 1.8)
  lambda_b        float  Expected goals for team B (e.g. 1.2)
  team_a          str    Label for team A (default "Team A")
  team_b          str    Label for team B (default "Team B")
  max_goals       int    Maximum goals per team to model (default 8)
  top_n           int    Number of top scores to return (default 12)
  dixon_coles     bool   Apply Dixon-Coles correction (default true)

  Alternative: provide goal stats instead of lambdas —
  avg_gf_a, avg_ga_a, avg_gf_b, avg_ga_b  (floats)
  league_avg      float  League average goals (default 1.3)

Output:
  {
    "success": true,
    "data": {
      "lambda_a": 1.8, "lambda_b": 1.2,
      "team_a_win_pct": 49.0,
      "draw_pct": 27.0,
      "team_b_win_pct": 24.0,
      "top_scores": [{"score": "1-0", "probability_pct": 11.2}, ...],
      "over_1_5_pct": 72.0,
      "over_2_5_pct": 51.0,
      "btts_pct": 43.0
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
    compute_lambda,
    compute_score_matrix,
    score_matrix_to_outcomes,
    top_scores,
)

logger = logging.getLogger(__name__)


def predict_score(
    lambda_a: float,
    lambda_b: float,
    team_a: str = "Team A",
    team_b: str = "Team B",
    max_goals: int = 8,
    top_n: int = 12,
    dixon_coles: bool = True,
) -> dict:
    if lambda_a <= 0 or lambda_b <= 0:
        return {"success": False, "error": "lambda_a and lambda_b must be positive"}

    matrix = compute_score_matrix(lambda_a, lambda_b, max_goals, dixon_coles)
    pw, pd, pl = score_matrix_to_outcomes(matrix)
    best = top_scores(matrix, top_n)

    # Derived market probabilities
    over_1_5 = sum(
        matrix[i][j]
        for i in range(len(matrix))
        for j in range(len(matrix[i]))
        if i + j > 1
    )
    over_2_5 = sum(
        matrix[i][j]
        for i in range(len(matrix))
        for j in range(len(matrix[i]))
        if i + j > 2
    )
    btts = sum(
        matrix[i][j]
        for i in range(1, len(matrix))
        for j in range(1, len(matrix[i]))
    )

    return {
        "success": True,
        "data": {
            "team_a": team_a,
            "team_b": team_b,
            "lambda_a": round(lambda_a, 3),
            "lambda_b": round(lambda_b, 3),
            "dixon_coles": dixon_coles,
            f"{team_a}_win_pct": round(pw * 100, 1),
            "draw_pct": round(pd * 100, 1),
            f"{team_b}_win_pct": round(pl * 100, 1),
            "top_scores": best,
            "markets": {
                "over_1_5_pct": round(over_1_5 * 100, 1),
                "over_2_5_pct": round(over_2_5 * 100, 1),
                "btts_pct": round(btts * 100, 1),
                "under_2_5_pct": round((1 - over_2_5) * 100, 1),
            },
        },
    }


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No JSON input. Required: {lambda_a, lambda_b} or {avg_gf_a, avg_ga_a, avg_gf_b, avg_ga_b}"}))
        sys.exit(1)
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    # Support either direct lambdas or raw goal averages
    if "lambda_a" in p and "lambda_b" in p:
        la = float(p["lambda_a"])
        lb = float(p["lambda_b"])
    elif all(k in p for k in ["avg_gf_a", "avg_ga_a", "avg_gf_b", "avg_ga_b"]):
        league_avg = float(p.get("league_avg", 1.3))
        la = compute_lambda(float(p["avg_gf_a"]), float(p["avg_ga_b"]), league_avg)
        lb = compute_lambda(float(p["avg_gf_b"]), float(p["avg_ga_a"]), league_avg)
    else:
        print(json.dumps({
            "success": False,
            "error": "Provide either {lambda_a, lambda_b} or {avg_gf_a, avg_ga_a, avg_gf_b, avg_ga_b}",
        }))
        sys.exit(1)

    try:
        result = predict_score(
            lambda_a=la,
            lambda_b=lb,
            team_a=str(p.get("team_a", "Team A")),
            team_b=str(p.get("team_b", "Team B")),
            max_goals=int(p.get("max_goals", 8)),
            top_n=int(p.get("top_n", 12)),
            dixon_coles=bool(p.get("dixon_coles", True)),
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
