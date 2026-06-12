"""
World Cup prediction models — pure Python, no network calls.

Provides:
  elo_to_probabilities()      win/draw/loss from Elo ratings
  form_adjusted_probs()       adjust by recent form string
  compute_lambda()            expected goals via attack/defense strength
  compute_score_matrix()      Poisson score probability matrix (+ Dixon-Coles)
  score_matrix_to_outcomes()  extract win/draw/loss from matrix
  top_scores()                top-N most probable score lines
"""
import math
from typing import Optional

# ---------- Elo probability ----------

def elo_win_prob(elo_a: float, elo_b: float, home_adv: float = 0.0) -> float:
    """P(A wins) from Elo ratings; home_adv adds virtual Elo points to A."""
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a - home_adv) / 400.0))


def elo_to_probabilities(
    elo_a: float,
    elo_b: float,
    home_adv: float = 0.0,
    draw_base: float = 0.28,
) -> tuple:
    """
    Map Elo ratings to (p_win_A, p_draw, p_win_B) for a single match.

    draw_base: empirical base draw rate in international football (~0.28).
    Draw probability peaks when teams are equal, decays as gap widens.
    """
    elo_gap = abs(elo_a + home_adv - elo_b)
    p_draw = draw_base * math.exp(-elo_gap / 240.0)
    p_raw = elo_win_prob(elo_a, elo_b, home_adv)
    remainder = 1.0 - p_draw
    p_win = p_raw * remainder
    p_loss = (1.0 - p_raw) * remainder
    return (round(p_win, 4), round(p_draw, 4), round(p_loss, 4))


# ---------- Form ----------

def form_score(form_str: str) -> float:
    """Convert e.g. 'WWDLW' to a 0–1 score; recent matches weighted more."""
    mapping = {"W": 1.0, "D": 0.5, "L": 0.0}
    values = [mapping[c] for c in form_str.upper() if c in mapping]
    if not values:
        return 0.5
    # Most-recent match has highest weight (index -1)
    weights = [2 ** i for i in range(len(values))]
    total_w = sum(weights)
    weighted = sum(v * w for v, w in zip(reversed(values), weights))
    return weighted / total_w


def form_adjusted_probs(
    p_win: float,
    p_draw: float,
    p_loss: float,
    form_a: str,
    form_b: str,
    weight: float = 0.15,
) -> tuple:
    """Nudge win/loss by form differential; draw unchanged."""
    diff = form_score(form_a) - form_score(form_b)
    adj = diff * weight
    pw = max(0.02, min(0.96, p_win + adj))
    pl = max(0.02, min(0.96, p_loss - adj))
    total = pw + p_draw + pl
    return (round(pw / total, 4), round(p_draw / total, 4), round(pl / total, 4))


# ---------- Expected goals ----------

def compute_lambda(
    avg_gf: float,
    avg_ga_opp: float,
    league_avg: float = 1.3,
) -> float:
    """
    Expected goals for a team given:
      avg_gf       – team's average goals scored per game
      avg_ga_opp   – opponent's average goals conceded per game
      league_avg   – overall league average goals per game
    """
    attack = avg_gf / max(league_avg, 0.01)
    defense_weakness = avg_ga_opp / max(league_avg, 0.01)
    return max(0.2, round(attack * defense_weakness * league_avg, 3))


# ---------- Poisson / Dixon-Coles ----------

def _poisson(k: int, lam: float) -> float:
    if k < 0 or lam <= 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _dc_correction(i: int, j: int, la: float, lb: float, rho: float = -0.10) -> float:
    """Dixon-Coles low-score correction (2×2 corner of the matrix)."""
    if i == 0 and j == 0:
        return 1.0 - la * lb * rho
    if i == 1 and j == 0:
        return 1.0 + lb * rho
    if i == 0 and j == 1:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def compute_score_matrix(
    lambda_a: float,
    lambda_b: float,
    max_goals: int = 8,
    dixon_coles: bool = True,
) -> list:
    """
    Return (max_goals+1) × (max_goals+1) normalized probability matrix.
    matrix[i][j] = P(team_A scores i, team_B scores j).
    """
    matrix = []
    for i in range(max_goals + 1):
        row = []
        for j in range(max_goals + 1):
            p = _poisson(i, lambda_a) * _poisson(j, lambda_b)
            if dixon_coles:
                p *= _dc_correction(i, j, lambda_a, lambda_b)
            row.append(max(0.0, p))
        matrix.append(row)

    total = sum(p for row in matrix for p in row)
    if total > 0:
        matrix = [[p / total for p in row] for row in matrix]
    return matrix


def score_matrix_to_outcomes(matrix: list) -> tuple:
    """Extract (p_win_A, p_draw, p_win_B) from score matrix."""
    p_win, p_draw, p_loss = 0.0, 0.0, 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if i > j:
                p_win += p
            elif i == j:
                p_draw += p
            else:
                p_loss += p
    return (round(p_win, 4), round(p_draw, 4), round(p_loss, 4))


def top_scores(matrix: list, n: int = 10) -> list:
    """Return top-N most probable scores as list of dicts."""
    scores = []
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            scores.append({"score": f"{i}-{j}", "probability_pct": round(p * 100, 2)})
    scores.sort(key=lambda x: x["probability_pct"], reverse=True)
    return scores[:n]
