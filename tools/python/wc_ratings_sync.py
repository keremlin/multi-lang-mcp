"""
WC_ratings_sync — derive FIFA-style player ratings from Transfermarkt market values.

Transfermarkt is the gold standard for player valuation in football analytics.
Market value captures current form, age trajectory, and league quality —
making it a better prediction signal than static FIFA card ratings.

Rating scale (log formula):  overall = clip(60 + 13 * log10(value_M), 45, 99)
  €200m → 90   €100m → 86   €40m → 81   €10m → 73   €1m → 60   <€500k → 45

The tool also stores the raw market_value_eur for transparency.

Input (stdin JSON):
  team   str   Single team name to update (default "" = all 48 teams)
  force  bool  Re-fetch even if rating already exists (default false)

Output:
  {"success": true, "data": {"players_updated": N, "not_found": N, "warnings": [...]}}
"""
import sys
import json
import time
import re
import math
import logging
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import requests
from bs4 import BeautifulSoup
from shared.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

_BASE = "https://www.transfermarkt.com"
_SEARCH_URL = f"{_BASE}/schnellsuche/ergebnis/schnellsuche"
_HDR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.transfermarkt.com/",
}

# DB team name → Transfermarkt nationality text (only where they differ)
_NAT_MAP: dict[str, list[str]] = {
    "United States":      ["United States", "USA"],
    "South Korea":        ["South Korea", "Korea, South"],
    "Congo DR":           ["Congo DR", "Congo, DR"],
    "Bosnia-Herzegovina": ["Bosnia-Herzegovina", "Bosnia & Herzegovina"],
    "Ivory Coast":        ["Ivory Coast", "Côte d'Ivoire"],
    "Cape Verde Islands": ["Cape Verde Islands", "Cape Verde"],
    "England":            ["England", "Great Britain"],
    "Scotland":           ["Scotland", "Great Britain"],
}


def _parse_value(raw: str) -> float | None:
    """Parse Transfermarkt market value string → float (millions €)."""
    raw = raw.strip().replace("\xa0", "").replace(",", ".")
    # Remove currency symbols and whitespace
    raw = re.sub(r"[€$£¥]", "", raw).strip()
    if not raw or raw == "-":
        return None
    m_bn = re.match(r"([\d.]+)\s*bn", raw, re.I)
    if m_bn:
        return float(m_bn.group(1)) * 1000
    m_m = re.match(r"([\d.]+)\s*m", raw, re.I)
    if m_m:
        return float(m_m.group(1))
    m_k = re.match(r"([\d.]+)\s*k", raw, re.I)
    if m_k:
        return float(m_k.group(1)) / 1000
    try:
        return float(raw) / 1_000_000
    except ValueError:
        return None


def _value_to_rating(value_m: float) -> int:
    """Convert market value (€M) to 45–99 overall rating."""
    if value_m <= 0:
        return 50
    rating = 60 + 13 * math.log10(max(0.01, value_m))
    return int(max(45, min(99, round(rating))))


def _nat_matches(tm_nat: str, db_team: str) -> bool:
    """Check if Transfermarkt nationality text matches our team name."""
    low_tm  = tm_nat.lower()
    low_db  = db_team.lower()
    if low_tm == low_db:
        return True
    aliases = _NAT_MAP.get(db_team, [])
    return any(low_tm == a.lower() for a in aliases)


def _name_sim(a: str, b: str) -> float:
    ta = set(re.sub(r"[^a-z ]", "", a.lower()).split())
    tb = set(re.sub(r"[^a-z ]", "", b.lower()).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def search_player(name: str, team: str) -> dict | None:
    """
    Search Transfermarkt for a player by name, match by team nationality.
    Returns {"overall_rating": int, "market_value_eur": int} or None.
    """
    try:
        resp = requests.get(
            _SEARCH_URL,
            params={"query": name, "Spieler_page": "0"},
            headers=_HDR,
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.debug("TM request failed for %s: %s", name, exc)
        return None

    soup  = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="items")
    if not table:
        return None

    best: dict | None = None
    best_score = 0.0

    for row in table.find_all("tr", class_=re.compile(r"(odd|even)")):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        # Column layout: player info | position | club | age | nat flag | value | ...
        # Extract player name (first <a> with player path)
        name_tag = row.find("a", href=re.compile(r"/profil/spieler/\d+"))
        row_name = name_tag.get_text(strip=True) if name_tag else ""

        # Nationality from flag img alt text
        nat_img = row.find("img", class_=re.compile(r"flagge"))
        row_nat = nat_img.get("title", "") if nat_img else ""
        if not row_nat:
            nat_img = row.find("img", src=re.compile(r"flagge|flag"))
            row_nat = nat_img.get("title", nat_img.get("alt", "")) if nat_img else ""

        # Market value — last meaningful td with € sign or text
        value_raw = ""
        for td in reversed(cells):
            txt = td.get_text(strip=True)
            if any(c in txt for c in ["m", "k", "bn", "€", "$", "£"]):
                value_raw = txt
                break

        if row_nat and not _nat_matches(row_nat, team):
            continue

        score = _name_sim(name, row_name)
        if score > best_score:
            value_m = _parse_value(value_raw)
            if value_m is not None:
                best_score = score
                best = {
                    "overall_rating":   _value_to_rating(value_m),
                    "market_value_eur": int(value_m * 1_000_000),
                }

    if best and best_score >= 0.3:
        return best
    return None


def sync_ratings(db: SupabaseClient, team_filter: str, force: bool) -> tuple[int, int, list]:
    filters = {"team": team_filter} if team_filter else None
    players = db.select("wc_players", filters=filters) if filters \
        else db.select("wc_players")

    updated, not_found, warnings = 0, 0, []

    for i, player in enumerate(players):
        if not force and player.get("overall_rating"):
            continue
        name = player["name"]
        team = player["team"]
        if i > 0:
            time.sleep(1.5)

        result = search_player(name, team)
        if not result:
            not_found += 1
            logger.debug("No rating: %s (%s)", name, team)
            continue

        db.upsert("wc_players", [{
            "team": team,
            "name": name,
            **result,
        }], on_conflict="team,name")
        updated += 1

    return updated, not_found, warnings


def run_sync(team: str = "", force: bool = False) -> dict:
    db = SupabaseClient()
    updated, not_found, warnings = sync_ratings(db, team, force)
    return {"success": True, "data": {
        "players_updated": updated,
        "not_found":       not_found,
        "warnings":        warnings,
    }}


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    try:
        out = run_sync(
            team=params.get("team", ""),
            force=bool(params.get("force", False)),
        )
    except Exception as exc:
        out = {"success": False, "error": str(exc)}
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
