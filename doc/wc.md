# World Cup 2026 Match Prediction — Architecture & Tools

## Overview

A data-science prediction system for FIFA World Cup 2026 match outcomes. Implemented as a set of MCP tools that Claude can call to fetch live football data, compute Elo-based win probabilities, model exact scores via Poisson regression, and synthesise a betting-oriented match analysis.

All tools follow the project's standard contract: accept JSON on stdin, return `{"success": bool, ...}` JSON to stdout, and are registered in `config/tools.json`.

---

## Prediction Process (Phases)

The system is designed in phases. Phases 1–4 are implemented. Phase 5 (LLM-powered injury intelligence) and Phase 6 (LightGBM) are planned.

### Phase 1 — Baseline Elo Model

Elo ratings are the primary signal. The world football Elo system assigns every national team a numeric rating (typically 1500–2200). The probability that team A beats team B is:

```
P(A wins) = 1 / (1 + 10^((elo_B - elo_A) / 400))
```

Draw probability peaks when teams are equal and decays exponentially as the Elo gap widens:

```
P(draw) = draw_base × exp(-|Elo_gap| / 240)
```

`draw_base` defaults to 0.28, matching the empirical draw rate in international football.

### Phase 2 — Data Gathering

Three data sources are used:

| Source | Tool | Data |
|---|---|---|
| FBref (via soccerdata) | `WC_team_stats`, `WC_head_to_head`, `WC_schedule` | Match schedule, scores, form |
| eloratings.net | `WC_elo_rating` | National team Elo ratings |
| WhoScored (via soccerdata) | `WC_schedule` | Match schedule fallback |

FBref is the primary source. It is sometimes blocked by Cloudflare; WhoScored is the schedule fallback. eloratings.net is JavaScript-rendered and not always scrapeable; a built-in fallback table of 32 WC 2026 nations covers the common case.

### Phase 3 — Win / Draw / Loss Prediction

Three signals are blended:

1. **Elo signal** — pure mathematical probability from rating gap
2. **Form adjustment** — recent match results (WWDLW strings) shift win/loss probabilities by up to 15%; draw probability is held constant
3. **Goals model** — attack/defense strength coefficients feed into Poisson lambdas, which generate an independent win/draw/loss distribution

The form string encodes results newest-last: `"LWDWW"` means the most recent match was a win. Each character is exponentially weighted so the most recent match contributes the most.

Blending formula (default 70/30 Elo+form vs goals model):

```
P_final = 0.70 × P_form_adjusted + 0.30 × P_goals_model
```

### Phase 4 — Poisson Score Distribution (Dixon-Coles)

Given expected goals λ_A and λ_B for each team, the probability of a specific scoreline A=i, B=j is:

```
P(i-j) = Poisson(i, λ_A) × Poisson(j, λ_B) × dc_correction(i, j)
```

The Dixon-Coles correction adjusts the four low-score outcomes (0-0, 1-0, 0-1, 1-1) that pure Poisson underestimates. With ρ = −0.10:

| Score | Correction |
|---|---|
| 0-0 | 1 − λ_A × λ_B × ρ |
| 1-0 | 1 + λ_B × ρ |
| 0-1 | 1 + λ_A × ρ |
| 1-1 | 1 − ρ |

Expected goals λ are computed from attack/defense strength:

```
λ_A = (avg_goals_A / league_avg) × (avg_conceded_B / league_avg) × league_avg
```

League average defaults to 1.3 goals/game for international football.

### Phase 5 — Player Intelligence (Implemented — data layer)

Player data is now stored in `wc_players` (roster, club, league, rating, market value, injury flag) and `wc_team_news` (recent news articles). Both are displayed in the match UI window.

**Implemented:**
- `WC_players_sync` — squad rosters, club/league enrichment, headshot photos
- `WC_ratings_sync` — FIFA-style overall ratings derived from Transfermarkt market values
- `WC_news_sync` — ESPN + BBC Sport RSS news articles per team (last 10 days)

**Remaining (planned):** LLM-powered injury impact analysis — feed recent news + player absences to Claude, get qualitative probability adjustment on top of the quantitative model.

### Phase 6 — LightGBM (Planned)

Once enough historical match data is stored (matches + predictions + actual results), a gradient-boosted classifier will be trained on features: Elo gap, form score, λ_A, λ_B, H2H win rate, home/neutral flag. This replaces the hand-tuned blend weights with learned weights.

---

## File Layout

```
tools/python/
├── wc_schedule.py          # Fixture fetcher — date → match list
├── wc_db_sync.py           # Seed/refresh wc_matches from football-data.org
├── wc_team_stats.py        # Form & goal stats from FBref
├── wc_elo_rating.py        # National Elo from eloratings.net
├── wc_head_to_head.py      # H2H history between two teams
├── wc_predict_outcome.py   # Win/draw/loss probability model
├── wc_predict_score.py     # Poisson + Dixon-Coles score distribution
├── wc_analyze_match.py     # Full orchestrator — calls all of the above
├── wc_match_info_ui.py     # Desktop match window (CustomTkinter)
├── wc_ui_window.py         # UI window implementation (flags, squad, news)
├── wc_players_sync.py      # Sync squad rosters + club/league/photos
├── wc_news_sync.py         # Fetch team news from ESPN + BBC Sport RSS
└── wc_ratings_sync.py      # Derive player ratings from Transfermarkt values

shared/
└── wc_models.py            # Pure math library — no network calls

flags_cache/                # Auto-created — flag PNGs cached from flagcdn.com (gitignored)
```

---

## Shared Math Library — `shared/wc_models.py`

All prediction math lives here. No HTTP calls, no I/O. Every prediction tool imports from this module rather than reimplementing formulas.

| Function | Signature | Description |
|---|---|---|
| `elo_win_prob` | `(elo_a, elo_b, home_adv=0) → float` | Raw P(A wins) from Elo formula |
| `elo_to_probabilities` | `(elo_a, elo_b, home_adv, draw_base=0.28) → (pw, pd, pl)` | Full three-way split |
| `form_score` | `(form_str) → float 0–1` | Exponentially weighted form rating |
| `form_adjusted_probs` | `(pw, pd, pl, form_a, form_b, weight=0.15) → (pw, pd, pl)` | Nudge win/loss by form; draw fixed |
| `compute_lambda` | `(avg_gf, avg_ga_opp, league_avg=1.3) → float` | Expected goals via attack×defense strength |
| `compute_score_matrix` | `(λ_a, λ_b, max_goals=8, dixon_coles=True) → 2D list` | Normalised P(i-j) matrix |
| `score_matrix_to_outcomes` | `(matrix) → (pw, pd, pl)` | Sum rows/diagonal/cols of score matrix |
| `top_scores` | `(matrix, n=10) → list[{score, probability_pct}]` | Top-N scorelines sorted by probability |

---

## Tools Reference

### WC_schedule

Fetches World Cup fixtures and results for a specific date (or the full season).

**Source order:** FBref → WhoScored → Sofascore

ESPN was evaluated and excluded because it does not carry the `INT-World Cup` league.

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `date` | string | `"today"` | `"YYYY-MM-DD"` or `"today"` |
| `league` | string | `"INT-World Cup"` | soccerdata league identifier |
| `season` | string | `"2026"` | Season year |
| `source` | string | `"auto"` | `"fbref"` / `"whoscored"` / `"sofascore"` / `"auto"` |
| `all` | bool | `false` | Return entire season instead of one date |

**Output:**

```json
{
  "success": true,
  "data": {
    "date": "2026-06-12",
    "league": "INT-World Cup",
    "season": "2026",
    "source": "FBref",
    "total": 3,
    "finished": 1,
    "upcoming": 2,
    "matches": [
      {
        "home": "Argentina",
        "away": "Canada",
        "status": "upcoming",
        "kickoff": "18:00",
        "venue": "MetLife Stadium",
        "group": "Group A"
      }
    ]
  }
}
```

**File:** [tools/python/wc_schedule.py](../tools/python/wc_schedule.py) | Timeout: 120 s

---

### WC_team_stats

Fetches a team's recent form string and goal statistics from FBref.

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `team` | string | required | Team name as spelled in FBref (e.g. `"Argentina"`) |
| `league` | string | `"INT-World Cup"` | soccerdata league string |
| `season` | string | `"2026"` | Season year |
| `n_recent` | int | `10` | Number of most recent completed matches to include |

**Output:**

```json
{
  "success": true,
  "data": {
    "team": "Argentina",
    "matches_analyzed": 10,
    "form_last5": "WWDWW",
    "form_full": "WDWLWWDWWW",
    "wins": 7, "draws": 2, "losses": 1,
    "win_rate": 0.7, "draw_rate": 0.2, "loss_rate": 0.1,
    "avg_goals_scored": 2.1,
    "avg_goals_conceded": 0.8,
    "goal_diff_avg": 1.3,
    "points_per_game": 2.3,
    "clean_sheets": 5,
    "failed_to_score": 0,
    "recent_results": [
      {"opponent": "Brazil", "score": "2-0", "result": "W", "venue": "H"}
    ]
  }
}
```

**Limitation:** FBref is sometimes blocked by Cloudflare. When scraping fails, this tool returns an error; use the Elo fallback table in `WC_analyze_match` instead.

**File:** [tools/python/wc_team_stats.py](../tools/python/wc_team_stats.py) | Timeout: 120 s

---

### WC_elo_rating

Fetches national team Elo ratings from eloratings.net, with ClubElo as an alternative for club teams.

**Source order (for national teams):** eloratings.net JSON API → eloratings.net HTML scrape

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `team` | string | `""` | Team name; empty returns top-N list |
| `top_n` | int | `30` | Rankings to return when no team specified |
| `source` | string | `"elo"` | `"elo"` (national) or `"clubelo"` (club) |
| `timeout` | int | `20` | HTTP timeout in seconds |

**Output (single team):**

```json
{
  "success": true,
  "data": {
    "team": "Argentina",
    "matches": [{"rank": 1, "team": "Argentina", "elo": 2141}],
    "source": "eloratings.net"
  }
}
```

**Limitation:** eloratings.net is JavaScript-rendered. When the JSON API endpoint returns no data and HTML scraping is also blocked, the tool returns an error. `WC_analyze_match` handles this by falling back to a built-in static table of 32 WC 2026 nations.

**File:** [tools/python/wc_elo_rating.py](../tools/python/wc_elo_rating.py) | Timeout: 30 s

---

### WC_head_to_head

Fetches historical head-to-head results between two teams from FBref.

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `team_a` | string | required | First team |
| `team_b` | string | required | Second team |
| `league` | string | `"INT-World Cup"` | soccerdata league string |
| `season` | string | `"2026"` | Season year |
| `n_matches` | int | `20` | Maximum H2H matches to return |

**Output:**

```json
{
  "success": true,
  "data": {
    "team_a": "Argentina",
    "team_b": "Brazil",
    "matches_found": 5,
    "team_a_wins": 2,
    "draws": 2,
    "team_b_wins": 1,
    "avg_goals_team_a": 1.4,
    "avg_goals_team_b": 1.0,
    "records": [
      {"home": "Argentina", "away": "Brazil", "score": "2-0", "result_for_a": "W"}
    ]
  }
}
```

**File:** [tools/python/wc_head_to_head.py](../tools/python/wc_head_to_head.py) | Timeout: 120 s

---

### WC_predict_outcome

Computes win/draw/loss probabilities by blending three signals: Elo gap, recent form, and goal-based Poisson model.

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `team_a` | string | required | Team A label |
| `team_b` | string | required | Team B label |
| `elo_a` | float | required | Team A Elo rating |
| `elo_b` | float | required | Team B Elo rating |
| `form_a` | string | `""` | Recent form, newest last (e.g. `"WWDLW"`) |
| `form_b` | string | `""` | Recent form for team B |
| `avg_gf_a` | float | optional | Team A average goals scored |
| `avg_ga_a` | float | optional | Team A average goals conceded |
| `avg_gf_b` | float | optional | Team B average goals scored |
| `avg_ga_b` | float | optional | Team B average goals conceded |
| `home_advantage` | float | `0` | Elo bonus for team A if playing at home |
| `draw_base` | float | `0.28` | Empirical base draw rate |
| `form_weight` | float | `0.15` | How much form shifts win/loss probs |
| `goals_blend` | float | `0.30` | Weight of goal-based probs in final blend |

**Output:**

```json
{
  "success": true,
  "data": {
    "team_a": "Argentina", "team_b": "Canada",
    "elo_a": 2141, "elo_b": 1866, "elo_diff": 275,
    "elo_probs":   {"Argentina_win": 71.2, "draw": 17.4, "Canada_win": 11.4},
    "form_probs":  {"Argentina_win": 73.1, "draw": 17.4, "Canada_win": 9.5},
    "goals_probs": {"Argentina_win": 68.0, "draw": 19.0, "Canada_win": 13.0},
    "final_probs": {"Argentina_win": 71.8, "draw": 17.9, "Canada_win": 10.3},
    "lambda_a": 1.94, "lambda_b": 0.85,
    "verdict": "Argentina strongly favoured (Elo +275)"
  }
}
```

**File:** [tools/python/wc_predict_outcome.py](../tools/python/wc_predict_outcome.py) | Timeout: 15 s

---

### WC_predict_score

Builds the full Poisson + Dixon-Coles score probability matrix and returns the top most-likely scorelines plus betting market probabilities.

**Input (option 1 — direct lambdas):**

| Field | Type | Default | Description |
|---|---|---|---|
| `lambda_a` | float | required | Expected goals for team A |
| `lambda_b` | float | required | Expected goals for team B |
| `team_a` | string | `"Team A"` | Label |
| `team_b` | string | `"Team B"` | Label |
| `max_goals` | int | `8` | Maximum goals per team in the matrix |
| `top_n` | int | `12` | Number of scorelines to return |
| `dixon_coles` | bool | `true` | Apply Dixon-Coles low-score correction |

**Input (option 2 — goal averages, lambdas computed internally):**

`avg_gf_a`, `avg_ga_a`, `avg_gf_b`, `avg_ga_b`, optionally `league_avg` (default 1.3)

**Output:**

```json
{
  "success": true,
  "data": {
    "lambda_a": 1.94, "lambda_b": 0.85,
    "Argentina_win_pct": 63.2,
    "draw_pct": 22.1,
    "Canada_win_pct": 14.7,
    "top_scores": [
      {"score": "1-0", "probability_pct": 14.2},
      {"score": "2-0", "probability_pct": 13.8},
      {"score": "2-1", "probability_pct": 11.1}
    ],
    "markets": {
      "over_1_5_pct": 71.3,
      "over_2_5_pct": 52.8,
      "btts_pct": 36.4,
      "under_2_5_pct": 47.2
    }
  }
}
```

**File:** [tools/python/wc_predict_score.py](../tools/python/wc_predict_score.py) | Timeout: 15 s

---

### WC_analyze_match

Full orchestrator. Calls all of the above tools internally and synthesises a complete match report with a plain-language betting summary.

**Call sequence:**
1. `WC_team_stats(team_a)` — form & goal stats
2. `WC_team_stats(team_b)` — form & goal stats
3. `WC_elo_rating(team_a)` → fallback table if scraping fails
4. `WC_elo_rating(team_b)` → fallback table if scraping fails
5. `WC_head_to_head(team_a, team_b)` — historical H2H
6. `WC_predict_outcome(...)` — blended probabilities
7. `WC_predict_score(...)` — score distribution & markets

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `team_a` | string | required | First team (e.g. `"Argentina"`) |
| `team_b` | string | required | Second team (e.g. `"Canada"`) |
| `league` | string | `"INT-World Cup"` | FBref league string |
| `season` | string | `"2026"` | Season year |
| `elo_a` | float | optional | Override Elo — skips scraping |
| `elo_b` | float | optional | Override Elo — skips scraping |
| `n_recent` | int | `10` | Recent matches for form analysis |
| `home_advantage` | float | `0` | Elo bonus for team A |

**Output:**

```json
{
  "success": true,
  "data": {
    "match": "Argentina vs Canada",
    "team_a_stats": { ... },
    "team_b_stats": { ... },
    "elo": {
      "team_a_elo": 2141, "team_a_source": "fallback table",
      "team_b_elo": 1866, "team_b_source": "fallback table"
    },
    "head_to_head": { ... },
    "prediction": {
      "outcome_probs": { "Argentina_win": 71.8, "draw": 17.9, "Canada_win": 10.3 },
      "expected_goals": { "lambda_a": 1.94, "lambda_b": 0.85 },
      "score_distribution": [ {"score": "1-0", "probability_pct": 14.2}, ... ],
      "markets": { "over_1_5_pct": 71.3, ... }
    },
    "betting_summary": "=== Argentina vs Canada — Betting Summary ===\n..."
  }
}
```

**Elo fallback table** built into the tool (used when eloratings.net is unreachable):

| Team | Elo | Team | Elo |
|---|---|---|---|
| Argentina | 2141 | France | 2086 |
| Spain | 2047 | England | 2065 |
| Brazil | 2026 | Portugal | 1985 |
| Netherlands | 1984 | Germany | 1978 |
| Croatia | 1956 | Uruguay | 1954 |
| USA | 1891 | Mexico | 1901 |
| Canada | 1866 | Morocco | 1882 |
| Japan | 1878 | South Korea | 1862 |
| ... | ... | (32 nations total) | |

**File:** [tools/python/wc_analyze_match.py](../tools/python/wc_analyze_match.py) | Timeout: 300 s

---

## Prediction Logic & Orchestration

### How `WC_analyze_match` orchestrates the pipeline

```
Input: team_a, team_b (+ optional overrides)
        │
        ├──► Step 1 & 2: Fetch stats for both teams (FBref)
        │         FBref.read_schedule() ──filter by team name──►
        │         Completed matches only (has score) ──tail(n_recent)──►
        │         Outputs: form_last5 (str), avg_goals_scored, avg_goals_conceded
        │         On failure: stats entry = {"error": "..."}, form = "", goals = None
        │
        ├──► Step 3: Resolve Elo for both teams
        │         if elo_override provided ──────────────────────────────► use it
        │         else try eloratings.net JSON API
        │              └─ fail ──► try eloratings.net HTML scrape
        │                         └─ fail ──► lookup internal fallback table (32 nations)
        │                                    └─ not found ──► return error (Elo required)
        │
        ├──► Step 4: Head-to-Head (FBref)
        │         Filter schedule for rows where BOTH teams appear
        │         On failure: h2h = {"error": "..."}  (non-blocking)
        │
        ├──► Step 5: predict_outcome()
        │         See blending logic below
        │
        └──► Step 6: predict_score()
                  if goal stats available ──► compute_lambda() for each team
                  else (no stats) ──► estimate lambdas from Elo ratio:
                       elo_ratio = 10^((elo_A - elo_B) / 400)
                       λ_A = 1.3 × elo_ratio / (1 + elo_ratio)
                       λ_B = 1.3 / (1 + elo_ratio)
                  ──► compute_score_matrix(λ_A, λ_B) → 9×9 matrix
                  ──► top_scores(), markets
```

### Blending logic inside `predict_outcome()`

The three signals are computed independently, then merged:

```
Step A — Elo signal
  elo_gap = |elo_A - elo_B|
  P_draw_elo  = 0.28 × exp(−elo_gap / 240)
  P_raw_win   = 1 / (1 + 10^((elo_B − elo_A − home_adv) / 400))
  P_win_elo   = P_raw_win × (1 − P_draw_elo)
  P_loss_elo  = (1 − P_raw_win) × (1 − P_draw_elo)

Step B — Form adjustment (applied on top of Elo probs)
  form_score(A) = exponentially weighted W=1, D=0.5, L=0 (newest has highest weight)
  diff = form_score(A) − form_score(B)          # −1 to +1
  adj  = diff × form_weight (default 0.15)
  P_win_form  = clamp(P_win_elo  + adj, 0.02, 0.96)
  P_loss_form = clamp(P_loss_elo − adj, 0.02, 0.96)
  P_draw stays unchanged; all three renormalised to sum to 1

Step C — Goals model (only if avg_gf/ga available for both teams)
  λ_A = (avg_gf_A / 1.3) × (avg_ga_B / 1.3) × 1.3
  λ_B = (avg_gf_B / 1.3) × (avg_ga_A / 1.3) × 1.3
  score_matrix = Poisson × Dixon-Coles correction
  (P_win_goals, P_draw_goals, P_loss_goals) = sum over matrix cells

  if goal data missing:
    goals_blend forced to 0.0 (Elo+form only)

Step D — Final blend
  P_win_final  = (1 − blend) × P_win_form  + blend × P_win_goals
  P_draw_final = (1 − blend) × P_draw_form + blend × P_draw_goals
  P_loss_final = (1 − blend) × P_loss_form + blend × P_loss_goals
  renormalise to 1.0
  (default blend = 0.30 → 70% form-Elo, 30% goals)
```

### Score matrix construction

```
For goals 0..max_goals (default 8), build a 9×9 grid:

  raw[i][j] = Poisson(i, λ_A) × Poisson(j, λ_B)

Apply Dixon-Coles low-score correction (ρ = −0.10):
  (0,0) → raw × (1 − λ_A × λ_B × ρ)    # reduces overcount of 0-0
  (1,0) → raw × (1 + λ_B × ρ)           # adjusts 1-0
  (0,1) → raw × (1 + λ_A × ρ)           # adjusts 0-1
  (1,1) → raw × (1 − ρ)                 # adjusts 1-1

Normalise matrix so all 81 cells sum to 1.

Outcome extraction:
  P_win  = Σ matrix[i][j]  where i > j   (team A scores more)
  P_draw = Σ matrix[i][j]  where i = j   (diagonal)
  P_loss = Σ matrix[i][j]  where i < j

Market derivation:
  Over 1.5 = Σ where i+j > 1
  Over 2.5 = Σ where i+j > 2
  BTTS     = Σ where i ≥ 1 AND j ≥ 1
  Under 2.5 = 1 − Over 2.5
```

### Verdict thresholds

```
elo_diff = elo_A − elo_B

> +150  → "Team A strongly favoured"
> +60   → "Team A moderately favoured"
−60 to +60 → "Even match — small edge depends on form"
< −60   → "Team B moderately favoured"
< −150  → "Team B strongly favoured"
```

### Fallback decision tree (Elo resolution)

```
WC_analyze_match needs elo_A, elo_B to proceed.

elo_a param provided by caller?
  YES → use it directly (source = "manual override")
  NO  → try eloratings.net JSON API
          → success? extract team's row, parse numeric Elo
          → fail? try eloratings.net HTML scrape (BeautifulSoup)
              → success? extract row
              → fail? look up _ELO_FALLBACK dict (32 nations, keyed by lowercase name)
                  → found? use it (source = "fallback table")
                  → not found? return error — caller must provide elo_A manually
```

---

## Typical Workflow

### Quick single-match prediction (fast, no scraping)

```
WC_predict_outcome({
  "team_a": "Spain", "team_b": "Morocco",
  "elo_a": 2047, "elo_b": 1882,
  "form_a": "WWWDW", "form_b": "WLWWW"
})
```

### Full data-driven analysis

```
WC_analyze_match({
  "team_a": "Argentina",
  "team_b": "France",
  "elo_a": 2141,
  "elo_b": 2086
})
```

### Get today's fixtures then analyse each

```
1. WC_schedule({"date": "today"})
2. For each match → WC_analyze_match(team_a, team_b)
```

### Score distribution only

```
WC_predict_score({
  "lambda_a": 1.6, "lambda_b": 1.1,
  "team_a": "Brazil", "team_b": "Colombia"
})
```

---

## Known Limitations

| Limitation | Impact | Workaround |
|---|---|---|
| FBref Cloudflare blocking | `WC_team_stats`, `WC_head_to_head` may fail | Manual elo/form inputs for predictions; schedule comes from DB |
| eloratings.net JS-rendered | `WC_elo_rating` JSON API and HTML scrape may return nothing | Built-in 32-team Elo fallback table in `WC_analyze_match` |
| WC 2026 season data sparse | FBref may have incomplete schedule | Schedule now served from Supabase — not scraped |
| No real-time injury data | Model doesn't know about late squad changes | Phase 5 (LLM injury analyst) planned |

---

### WC_db_sync

Seeds or refreshes the Supabase `wc_matches` table from a football data API. Run once before using `WC_schedule`. Re-run daily to update scores as matches finish.

**Source priority:**
1. `football-data.org` — if `FOOTBALL_DATA_API_KEY` is set in `.env` (free key at football-data.org)
2. `TheSportsDB` — free, no key needed (fallback)

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `source` | string | `"auto"` | `"auto"` / `"football-data"` / `"thesportsdb"` |
| `force` | bool | `false` | Re-sync even if data already exists |

**Output:**

```json
{
  "success": true,
  "data": {
    "source": "football-data.org",
    "total_fetched": 104,
    "upserted": 72,
    "sample": [...]
  }
}
```

**Note:** Matches with unknown teams (e.g. TBD knockout-stage slots) are skipped — only confirmed group stage fixtures are inserted.

**File:** [tools/python/wc_db_sync.py](../tools/python/wc_db_sync.py) | Timeout: 60 s

---

### WC_match_info_ui

Opens a maximised desktop window showing a full match prediction dashboard for two teams.

The window is built with **CustomTkinter** and displays:
- Country flag images (flagcdn.com, cached to `flags_cache/`)
- Win/draw/loss probability bars (from `WC_analyze_match`)
- Score distribution grid (top-12 scorelines)
- Recent news panel — 5 most recent headlines from `wc_team_news`
- Squad panel — scrollable list with player photo, position pill, club/league, rating badge, market value, and injury indicator

When the window opens it also spawns a **background subprocess** that runs `WC_players_sync` in `"clubs"` mode for both teams, enriching club/league data without blocking the UI.

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `team_a` | string | required | First team (e.g. `"Brazil"`) |
| `team_b` | string | required | Second team (e.g. `"Argentina"`) |

**Output:**

```json
{"success": true, "data": {"message": "UI window opened for Brazil vs Argentina"}}
```

**File:** [tools/python/wc_match_info_ui.py](../tools/python/wc_match_info_ui.py) | Timeout: 30 s

---

### WC_players_sync

Syncs WC 2026 squad rosters from **football-data.org** and enriches them with club/league data and player photos.

**Modes:**

| Mode | Action | Sleep between requests |
|---|---|---|
| `"squads"` | Fetch all 48 squad rosters (name, position, nationality) | 6 s (rate limit) |
| `"clubs"` | Enrich with current club and league via `/v4/persons/{id}` | 6 s |
| `"photos"` | Fetch headshot URL from TheSportsDB | 1.2 s |
| `"all"` | Runs squads → clubs → photos in sequence | — |

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `mode` | string | `"squads"` | Which sync step to run |
| `team` | string | `""` | Limit to one team (empty = all 48) |

**Output:**

```json
{
  "success": true,
  "data": {
    "mode": "clubs",
    "team_filter": "Brazil",
    "players_synced": 26,
    "clubs_enriched": 24,
    "warnings": []
  }
}
```

**Requires:** `FOOTBALL_DATA_API_KEY` in `.env` (free key from football-data.org)

**File:** [tools/python/wc_players_sync.py](../tools/python/wc_players_sync.py) | Timeout: 900 s

---

### WC_news_sync

Fetches recent news articles about WC 2026 teams and stores them in `wc_team_news`. Safe to re-run (upserts by URL).

**Sources:**
1. **ESPN FIFA World Cup API** — structured JSON, team categories, one HTTP call for ~100 articles
2. **BBC Sport Football RSS** — 88 items, keyword-matched to teams

Articles are assigned to teams by category label (ESPN) or keyword matching (BBC). Each article can map to multiple teams.

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `team` | string | `""` | Filter to one team; empty = store all |
| `days` | int | `10` | How many days back to include |

**Output:**

```json
{
  "success": true,
  "data": {
    "articles_saved": 146,
    "sources": ["ESPN", "BBC Sport"],
    "warnings": []
  }
}
```

**File:** [tools/python/wc_news_sync.py](../tools/python/wc_news_sync.py) | Timeout: 300 s

---

### WC_ratings_sync

Derives FIFA-style player ratings from **Transfermarkt market values** and stores them in `wc_players`.

**Why Transfermarkt:** sofifa.com (Cloudflare-blocked) and pesdb.net (only major licensed clubs) are inaccessible. Transfermarkt is the gold-standard for player valuation and covers 80–90% of WC squad players.

**Rating formula:**

```
overall = clip(60 + 13 × log10(market_value_M), 45, 99)
```

| Market value | Rating |
|---|---|
| €200 M | 90 |
| €100 M | 86 |
| €40 M | 81 |
| €10 M | 73 |
| €1 M | 60 |
| < €500 k | 45 |

**Matching strategy:** Searches Transfermarkt by player name, filters rows by nationality flag (title attribute), scores name similarity using token overlap ≥ 0.3 threshold.

**Input:**

| Field | Type | Default | Description |
|---|---|---|---|
| `team` | string | `""` | Limit to one team; empty = all 48 |
| `force` | bool | `false` | Re-fetch even if rating already exists |

**Output:**

```json
{
  "success": true,
  "data": {
    "players_updated": 23,
    "not_found": 3,
    "warnings": []
  }
}
```

**Note:** Sleep is 1.5 s between requests. Full 48-team run takes ~45 minutes. Players at non-Transfermarkt-listed clubs (common for Qatar, smaller nations) will have no rating.

**File:** [tools/python/wc_ratings_sync.py](../tools/python/wc_ratings_sync.py) | Timeout: 1800 s

---

## Data Layer — Supabase

The project uses the **DeepLearn** Supabase project (`iehfahiljhkpprgzejzo`, region `us-east-1`) as its persistent data store. The following tables live in the `public` schema:

| Table | Purpose |
|---|---|
| `wc_matches` | Full WC 2026 schedule + live scores |
| `wc_teams` | Team reference data (Elo, group) |
| `wc_predictions` | Stored model predictions per match |
| `wc_players` | Squad rosters — name, position, club, league, photo URL, rating, market value |
| `wc_team_news` | Recent news articles per team (ESPN + BBC Sport) |

**`wc_players` columns:** `team`, `name`, `position` (GK/DEF/MID/FWD), `date_of_birth`, `nationality`, `shirt_number`, `club`, `league`, `photo_url`, `overall_rating`, `market_value_eur`, `is_injured`

**`wc_team_news` columns:** `team`, `headline`, `summary`, `url` (unique key), `source`, `published_at`

**Access:** anon key (read + write) — server-side only. RLS is enabled but allows full anon access since all requests originate from the MCP server, not a public browser.

**Connection details** (in `.env`):
```
SUPABASE_URL=https://iehfahiljhkpprgzejzo.supabase.co
SUPABASE_ANON_KEY=<jwt>
FOOTBALL_DATA_API_KEY=<key>   # free from football-data.org
```

**`shared/supabase_client.py`** — thin REST wrapper over `requests` (no extra SDK):
- `db.select(table, filters, order, limit)` — GET query
- `db.upsert(table, records, on_conflict)` — POST with merge-duplicates
- `db.insert(table, records)` — plain POST

---

## Configuration

All tools are registered in [config/tools.json](../config/tools.json):

```json
{"name": "WC_schedule",        "script": "tools/python/wc_schedule.py",        "timeout": 30},
{"name": "WC_db_sync",         "script": "tools/python/wc_db_sync.py",          "timeout": 60},
{"name": "WC_team_stats",      "script": "tools/python/wc_team_stats.py",       "timeout": 120},
{"name": "WC_elo_rating",      "script": "tools/python/wc_elo_rating.py",       "timeout": 30},
{"name": "WC_head_to_head",    "script": "tools/python/wc_head_to_head.py",     "timeout": 120},
{"name": "WC_predict_outcome", "script": "tools/python/wc_predict_outcome.py",  "timeout": 15},
{"name": "WC_predict_score",   "script": "tools/python/wc_predict_score.py",    "timeout": 15},
{"name": "WC_analyze_match",   "script": "tools/python/wc_analyze_match.py",    "timeout": 300},
{"name": "WC_match_info_ui",   "script": "tools/python/wc_match_info_ui.py",    "timeout": 30},
{"name": "WC_players_sync",    "script": "tools/python/wc_players_sync.py",     "timeout": 900},
{"name": "WC_news_sync",       "script": "tools/python/wc_news_sync.py",        "timeout": 300},
{"name": "WC_ratings_sync",    "script": "tools/python/wc_ratings_sync.py",     "timeout": 1800}
```

Dependencies (in `requirements.txt`):
- `soccerdata>=1.9.0` — data scraping (FBref, WhoScored, ClubElo) — used by team stats / H2H tools
- `psycopg2-binary>=2.9.0` — installed (not used directly; Supabase access via REST API)
- `Pillow>=10.0.0` — image processing for flag images and circular player photos in the UI
- `beautifulsoup4>=4.12.0` — HTML parsing for Transfermarkt scraping in `WC_ratings_sync`
- `requests>=2.31.0` — HTTP client used by news sync, ratings sync, and player photo sync

Data backend: **Supabase** — 72 group stage matches seeded from football-data.org. `WC_schedule` reads from DB in ~200ms (no scraping).

---

## AI Instructions — How to Update Data and Show UI

This section tells Claude (or any AI using these tools) exactly which tools to call and in what order for common tasks.

### Show a match prediction UI

To open the match window for a specific pair of teams:

```
WC_match_info_ui({"team_a": "Brazil", "team_b": "Argentina"})
```

The window opens immediately; club data enrichment runs in the background.

### Show today's or tomorrow's matches then open UI

```
1. WC_schedule({"date": "today"})          # or "YYYY-MM-DD" for tomorrow
2. For each match in the result:
   WC_match_info_ui({"team_a": ..., "team_b": ...})
```

### Refresh squad rosters for all 48 teams

Run once before the tournament, or after a squad change:

```
WC_players_sync({"mode": "squads"})         # ~15 min (6s/team × 48 teams)
WC_players_sync({"mode": "clubs"})          # ~15 min (enriches club/league)
WC_players_sync({"mode": "photos"})         # ~1 min (TheSportsDB headshots)
```

Or in one call (slower but unattended):

```
WC_players_sync({"mode": "all"})
```

### Refresh squad for specific teams only

```
WC_players_sync({"mode": "clubs", "team": "France"})
WC_players_sync({"mode": "photos", "team": "France"})
```

### Refresh player ratings

Run after squad sync. Skips players already rated unless `force=true`:

```
WC_ratings_sync({})                              # all 48 teams (~45 min)
WC_ratings_sync({"team": "Brazil"})              # single team (~2 min)
WC_ratings_sync({"team": "Brazil", "force": true})  # re-fetch all
```

### Refresh team news

```
WC_news_sync({})                          # all teams, last 10 days
WC_news_sync({"team": "France", "days": 7})  # one team, custom window
```

### Full data refresh (before tournament day)

Recommended order:

```
1. WC_db_sync({})                         # refresh match schedule
2. WC_news_sync({})                       # fetch latest news
3. WC_players_sync({"mode": "squads"})   # update rosters
4. WC_ratings_sync({})                   # update ratings (long — run overnight)
```

### When the UI shows no players or news

The `wc_players` and `wc_team_news` tables may be empty for newly added teams. Run:

```
WC_players_sync({"mode": "all", "team": "<team_name>"})
WC_news_sync({"team": "<team_name>"})
WC_ratings_sync({"team": "<team_name>"})
```

Then re-open the UI window.

### When flag images are missing

Flag images are cached under `flags_cache/` using ISO 3166-1 alpha-2 codes. They download automatically when the UI opens. If a flag fails to load (network issue or wrong country code), the UI shows a grey placeholder. The `_FLAG_OVERRIDE` dict in `wc_ui_window.py` maps special cases (`England → gb-eng`, `Scotland → gb-sct`).

### Tool timeout guide

| Task | Tool | Expected duration |
|---|---|---|
| Open match window | `WC_match_info_ui` | < 5 s |
| Refresh match schedule | `WC_db_sync` | < 60 s |
| Refresh news (all teams) | `WC_news_sync` | < 60 s |
| Sync squads (48 teams) | `WC_players_sync mode=squads` | ~15 min |
| Sync clubs (48 teams) | `WC_players_sync mode=clubs` | ~15 min |
| Sync photos (one team) | `WC_players_sync mode=photos` | < 1 min |
| Ratings (one team) | `WC_ratings_sync` + team filter | ~2 min |
| Ratings (all 48 teams) | `WC_ratings_sync` no filter | ~45 min |
