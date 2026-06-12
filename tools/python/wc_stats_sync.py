"""
WC_stats_sync — enrich wc_team_stats and populate wc_head_to_head.

Data sources (all free, no auth):
  - World ranking + live Elo : eloratings.net/World.tsv
  - Recent form + goals      : eloratings.net/{TeamName}.tsv  (per-team history)
  - Head-to-head             : same per-team TSVs, cross-referenced

Input (stdin JSON):
  mode   str   "all" | "rankings" | "form" | "h2h"  (default "all")
  team   str   Single team name to update (default "" = all 48 teams)

Output:
  {"success": true, "data": {"rankings_updated": N, "form_updated": N, "h2h_pairs": N}}
"""
import sys
import json
import time
import logging
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import requests
from shared.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

ELO_BASE = "https://www.eloratings.net"
_HDR = {"User-Agent": "Mozilla/5.0 (WC-Stats-Sync/1.0)"}

# eloratings.net 2-letter code → our canonical DB name
_ELO_CODE_TO_NAME = {
    "AR": "Argentina",        "AU": "Australia",         "AT": "Austria",
    "BE": "Belgium",          "BA": "Bosnia-Herzegovina", "BR": "Brazil",
    "CA": "Canada",           "CV": "Cape Verde Islands", "CI": "Ivory Coast",
    "CD": "Congo DR",         "HR": "Croatia",            "CZ": "Czechia",
    "CU": "Curaçao",          "EC": "Ecuador",            "EG": "Egypt",
    "EN": "England",          "FR": "France",             "DE": "Germany",
    "GH": "Ghana",            "HT": "Haiti",              "IR": "Iran",
    "IQ": "Iraq",             "JP": "Japan",              "JO": "Jordan",
    "MX": "Mexico",           "MA": "Morocco",            "NL": "Netherlands",
    "NZ": "New Zealand",      "NO": "Norway",             "PA": "Panama",
    "PY": "Paraguay",         "PT": "Portugal",           "QA": "Qatar",
    "SA": "Saudi Arabia",     "SN": "Senegal",            "ZA": "South Africa",
    "KR": "South Korea",      "ES": "Spain",              "CH": "Switzerland",
    "TN": "Tunisia",          "TR": "Turkey",             "US": "United States",
    "UY": "Uruguay",          "UZ": "Uzbekistan",
    "CO": "Colombia",         "DZ": "Algeria",            "SE": "Sweden",
    "SQ": "Scotland",
}
_NAME_TO_CODE = {v: k for k, v in _ELO_CODE_TO_NAME.items()}

# Our canonical DB name → eloratings.net URL slug (only non-obvious ones)
_ELO_URL_SLUG = {
    "United States":       "United_States",
    "South Korea":         "South_Korea",
    "Bosnia-Herzegovina":  "Bosnia_and_Herzegovina",
    "Cape Verde Islands":  "Cape_Verde",
    "Congo DR":            "DR_Congo",
    "Ivory Coast":         "Ivory_Coast",
    "Saudi Arabia":        "Saudi_Arabia",
    "New Zealand":         "New_Zealand",
    "South Africa":        "South_Africa",
    "Curaçao":             "Curacao",
}


def _elo_url(team_name: str) -> str:
    slug = _ELO_URL_SLUG.get(team_name, team_name.replace(" ", "_"))
    return f"{ELO_BASE}/{slug}.tsv"


# ── World Rankings + live Elo ─────────────────────────────────────────────────

def fetch_world_rankings() -> dict[str, dict]:
    """
    Parse eloratings.net/World.tsv.
    TSV cols: rank, prev_rank, code, elo, ...
    Returns {canonical_name: {"rank": int, "elo": int}}.
    """
    result: dict[str, dict] = {}
    try:
        resp = requests.get(f"{ELO_BASE}/World.tsv", headers=_HDR, timeout=15)
        resp.raise_for_status()
        for line in resp.text.splitlines():
            parts = line.strip().split("\t")
            if len(parts) < 4:
                continue
            try:
                rank = int(parts[0])
                code = parts[2].strip()
                elo  = int(parts[3])
            except (ValueError, IndexError):
                continue
            name = _ELO_CODE_TO_NAME.get(code)
            if name:
                result[name] = {"rank": rank, "elo": elo}
    except Exception as exc:
        logger.warning("eloratings World.tsv failed: %s", exc)
    return result


# ── Per-team TSV: form + H2H ──────────────────────────────────────────────────

def _fetch_team_tsv(team_name: str) -> list[list[str]]:
    """
    Fetch team-specific TSV from eloratings.net.
    TSV cols: year, month, day, home_code, away_code, home_score, away_score,
              match_type, tournament, elo_change, home_elo_after, away_elo_after, ...
    Returns list of parsed rows (oldest → newest).
    """
    url = _elo_url(team_name)
    try:
        resp = requests.get(url, headers=_HDR, timeout=15)
        resp.raise_for_status()
        rows = []
        for line in resp.text.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7:
                rows.append(parts)
        return rows
    except Exception as exc:
        logger.debug("TSV fetch failed for %s (%s): %s", team_name, url, exc)
        return []


def _parse_form_from_tsv(rows: list[list[str]], team_code: str, n: int = 10) -> dict:
    """Compute form string and goal averages from last n matches."""
    results, gf_list, ga_list = [], [], []
    for parts in rows:
        home_code, away_code = parts[3], parts[4]
        if home_code != team_code and away_code != team_code:
            continue
        try:
            hs, as_ = int(parts[5]), int(parts[6])
        except (ValueError, IndexError):
            continue
        is_home = home_code == team_code
        gf = hs if is_home else as_
        ga = as_ if is_home else hs
        results.append("W" if gf > ga else ("D" if gf == ga else "L"))
        gf_list.append(gf)
        ga_list.append(ga)

    if not results:
        return {}
    tail = results[-n:]
    n_used = len(tail)
    gf_tail = gf_list[-n:]
    ga_tail = ga_list[-n:]
    return {
        "form_last5":          "".join(tail[-5:]),
        "form_last10":         "".join(tail),
        "avg_goals_scored":    round(sum(gf_tail) / n_used, 2),
        "avg_goals_conceded":  round(sum(ga_tail) / n_used, 2),
        "matches_analyzed":    n_used,
        "data_source":         "eloratings.net",
    }


def _extract_h2h_from_tsv(rows: list[list[str]], team_name: str,
                           team_code: str, wc_codes: set[str]) -> dict[str, dict]:
    """
    Extract H2H records vs all other WC teams from a team's TSV.
    Returns {canonical_pair_key: h2h_row} with alphabetical a/b ordering.
    """
    pairs: dict[str, dict] = {}
    for parts in rows:
        home_code, away_code = parts[3], parts[4]
        if home_code != team_code and away_code != team_code:
            continue
        opp_code = away_code if home_code == team_code else home_code
        if opp_code not in wc_codes:
            continue
        opp_name = _ELO_CODE_TO_NAME.get(opp_code)
        if not opp_name:
            continue
        try:
            hs, as_ = int(parts[5]), int(parts[6])
        except (ValueError, IndexError):
            continue

        is_home = home_code == team_code
        gf = hs if is_home else as_
        ga = as_ if is_home else hs

        a, b = sorted([team_name, opp_name])
        key = f"{a}|||{b}"
        if key not in pairs:
            pairs[key] = {"team_a": a, "team_b": b, "played": 0,
                          "team_a_wins": 0, "draws": 0, "team_b_wins": 0,
                          "goals_a": 0, "goals_b": 0, "last_match_date": None}
        p = pairs[key]
        p["played"] += 1

        a_is_team = (a == team_name)
        if a_is_team:
            p["goals_a"] += gf; p["goals_b"] += ga
            if gf > ga:    p["team_a_wins"] += 1
            elif gf == ga: p["draws"] += 1
            else:          p["team_b_wins"] += 1
        else:
            p["goals_a"] += ga; p["goals_b"] += gf
            if gf > ga:    p["team_b_wins"] += 1
            elif gf == ga: p["draws"] += 1
            else:          p["team_a_wins"] += 1

        try:
            match_date = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        except (ValueError, IndexError):
            match_date = None
        if match_date and (not p["last_match_date"] or match_date > p["last_match_date"]):
            p["last_match_date"] = match_date

    return pairs


# ── Main sync logic ────────────────────────────────────────────────────────────

def sync_rankings(db: SupabaseClient, team_filter: str) -> int:
    world = fetch_world_rankings()
    if not world:
        return 0
    rows = db.select("wc_team_stats", order="name") if not team_filter else \
           db.select("wc_team_stats", filters={"name": team_filter})
    updated = 0
    for row in rows:
        info = world.get(row["name"])
        if info:
            db.upsert("wc_team_stats", [{
                "name": row["name"],
                "fifa_ranking": info["rank"],
                "elo": info["elo"],
            }], on_conflict="name")
            updated += 1
    return updated


def sync_form(db: SupabaseClient, team_filter: str) -> tuple[int, list]:
    rows = db.select("wc_team_stats", order="name") if not team_filter else \
           db.select("wc_team_stats", filters={"name": team_filter})
    updated, failed = 0, []
    for i, row in enumerate(rows):
        name = row["name"]
        code = _NAME_TO_CODE.get(name)
        if not code:
            failed.append(f"{name}: no eloratings code")
            continue
        if i > 0:
            time.sleep(0.5)
        tsv_rows = _fetch_team_tsv(name)
        if not tsv_rows:
            failed.append(f"{name}: TSV fetch failed")
            continue
        form = _parse_form_from_tsv(tsv_rows, code)
        if not form:
            failed.append(f"{name}: no parseable matches")
            continue
        db.upsert("wc_team_stats", [{"name": name, **form}], on_conflict="name")
        updated += 1
    return updated, failed


def sync_h2h(db: SupabaseClient, team_filter: str) -> tuple[int, list]:
    all_rows = db.select("wc_team_stats", order="name")
    wc_codes = {_NAME_TO_CODE[r["name"]] for r in all_rows if r["name"] in _NAME_TO_CODE}

    target_rows = all_rows if not team_filter else \
                  [r for r in all_rows if r["name"] == team_filter]

    all_h2h: dict[str, dict] = {}
    failed = []

    for i, row in enumerate(target_rows):
        name = row["name"]
        code = _NAME_TO_CODE.get(name)
        if not code:
            failed.append(f"{name}: no eloratings code")
            continue
        if i > 0:
            time.sleep(0.5)
        tsv_rows = _fetch_team_tsv(name)
        if not tsv_rows:
            failed.append(f"{name}: TSV fetch failed")
            continue
        pairs = _extract_h2h_from_tsv(tsv_rows, name, code, wc_codes)
        for key, pair in pairs.items():
            if key not in all_h2h or pair["played"] > all_h2h[key]["played"]:
                all_h2h[key] = pair

    if not all_h2h:
        return 0, failed

    pairs_list = list(all_h2h.values())
    db.upsert("wc_head_to_head", pairs_list, on_conflict="team_a,team_b")
    return len(pairs_list), failed


def run_sync(mode: str = "all", team: str = "") -> dict:
    db = SupabaseClient()
    result: dict = {"rankings_updated": 0, "form_updated": 0, "h2h_pairs": 0,
                    "warnings": []}

    if mode in ("all", "rankings"):
        result["rankings_updated"] = sync_rankings(db, team)

    if mode in ("all", "form"):
        n, failed = sync_form(db, team)
        result["form_updated"] = n
        result["warnings"].extend(failed)

    if mode in ("all", "h2h"):
        n, failed = sync_h2h(db, team)
        result["h2h_pairs"] = n
        result["warnings"].extend(failed)

    return {"success": True, "data": result}


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    try:
        result = run_sync(
            mode=params.get("mode", "all"),
            team=params.get("team", ""),
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
