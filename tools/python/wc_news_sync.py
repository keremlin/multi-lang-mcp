"""
WC_news_sync — fetch recent news about WC 2026 teams.

Sources (both free, no API key):
  1. ESPN FIFA World Cup API  — structured JSON, team categories
  2. BBC Sport Football RSS   — broad football news, keyword-matched

Articles are assigned to teams by category label or headline/description match.
Safe to re-run — upserts by URL.

Input (stdin JSON):
  team   str  Filter to one team (default "" = store all)
  days   int  How many days back to include (default 10)

Output:
  {"success": true, "data": {"articles_saved": N, "warnings": [...]}}
"""
import sys
import json
import re
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import requests
from shared.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

_HDR = {"User-Agent": "Mozilla/5.0 (WC-News-Sync/1.0)"}

_ESPN_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer"
    "/fifa.world/news?limit=100"
)
_BBC_URL = "https://feeds.bbci.co.uk/sport/football/rss.xml"

WC_TEAMS = [
    "Argentina", "Australia", "Austria", "Belgium", "Bosnia-Herzegovina",
    "Brazil", "Canada", "Cape Verde Islands", "Colombia", "Congo DR",
    "Croatia", "Czechia", "Curaçao", "Ecuador", "Egypt", "England",
    "France", "Germany", "Ghana", "Haiti", "Iran", "Iraq", "Japan",
    "Jordan", "Mexico", "Morocco", "Netherlands", "New Zealand", "Norway",
    "Panama", "Paraguay", "Portugal", "Qatar", "Saudi Arabia", "Scotland",
    "Senegal", "South Africa", "South Korea", "Spain", "Sweden",
    "Switzerland", "Tunisia", "Turkey", "United States", "Uruguay",
    "Uzbekistan", "Algeria", "Ivory Coast",
]

# ESPN category label → canonical DB team name (only where they differ)
_ESPN_CAT_MAP = {
    "USA":                  "United States",
    "Korea Republic":       "South Korea",
    "DR Congo":             "Congo DR",
    "Bosnia-Herzegovina":   "Bosnia-Herzegovina",
    "Cape Verde":           "Cape Verde Islands",
    "Ivory Coast":          "Ivory Coast",
    "Côte d'Ivoire":        "Ivory Coast",
}

# Keywords to match in headline/description → canonical team name
_KEYWORDS: dict[str, list[str]] = {
    t: [t.lower()] for t in WC_TEAMS
}
_KEYWORDS["United States"] += ["usmnt", "u.s. men", "usa soccer", "american"]
_KEYWORDS["South Korea"]   += ["south korea", "korea republic", "taeguk"]
_KEYWORDS["Congo DR"]      += ["dr congo", "democratic republic"]
_KEYWORDS["Bosnia-Herzegovina"] += ["bosnia"]
_KEYWORDS["Ivory Coast"]   += ["ivory coast", "côte d'ivoire", "cote d'ivoire"]
_KEYWORDS["Cape Verde Islands"] += ["cape verde"]
_KEYWORDS["Netherlands"]   += ["dutch", "oranje"]
_KEYWORDS["England"]       += ["three lions"]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_rss_date(s: str) -> datetime | None:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            return datetime.strptime(s.strip(), fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _teams_for_text(text: str) -> list[str]:
    """Return all WC team names that appear in the given text."""
    low = text.lower()
    found = []
    for team, kws in _KEYWORDS.items():
        if any(kw in low for kw in kws):
            found.append(team)
    return found


# ── ESPN ──────────────────────────────────────────────────────────────────────

def fetch_espn(cutoff: datetime) -> list[dict]:
    try:
        r = requests.get(_ESPN_URL, headers=_HDR, timeout=15)
        r.raise_for_status()
        articles = r.json().get("articles", [])
    except Exception as exc:
        logger.warning("ESPN fetch failed: %s", exc)
        return []

    rows = []
    for a in articles:
        pub = _parse_iso(a.get("published"))
        if pub and pub < cutoff:
            continue

        headline = _strip_html(a.get("headline", ""))
        desc     = _strip_html(a.get("description", ""))
        url      = (a.get("links") or {}).get("web", {}).get("href", "")
        if not url:
            # fallback: build from id
            url = f"https://www.espn.com/soccer/story/_/id/{a.get('id', '')}"

        # Determine which teams this article belongs to
        cats     = [c.get("description", "") for c in a.get("categories", [])]
        teams_from_cats = []
        for cat in cats:
            mapped = _ESPN_CAT_MAP.get(cat)
            if mapped:
                teams_from_cats.append(mapped)
            elif cat in WC_TEAMS:
                teams_from_cats.append(cat)

        teams = teams_from_cats or _teams_for_text(f"{headline} {desc}")
        if not teams:
            teams = ["General"]  # keep it anyway under General

        for team in set(teams):
            rows.append({
                "team":        team,
                "headline":    headline[:500],
                "summary":     desc[:1000] or None,
                "url":         url[:1000],
                "source":      "ESPN",
                "published_at": pub.isoformat() if pub else None,
            })
    return rows


# ── BBC ───────────────────────────────────────────────────────────────────────

def fetch_bbc(cutoff: datetime) -> list[dict]:
    try:
        r = requests.get(_BBC_URL, headers=_HDR, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
    except Exception as exc:
        logger.warning("BBC fetch failed: %s", exc)
        return []

    rows = []
    for item in items:
        title   = _strip_html(item.findtext("title", ""))
        desc    = _strip_html(item.findtext("description", ""))
        url     = item.findtext("link", "").strip()
        pub_raw = item.findtext("pubDate", "")
        pub     = _parse_rss_date(pub_raw)

        if pub and pub < cutoff:
            continue
        if not title or not url:
            continue

        teams = _teams_for_text(f"{title} {desc}")
        if not teams:
            continue  # skip BBC articles not related to any WC team

        for team in set(teams):
            rows.append({
                "team":        team,
                "headline":    title[:500],
                "summary":     desc[:1000] or None,
                "url":         url[:1000],
                "source":      "BBC Sport",
                "published_at": pub.isoformat() if pub else None,
            })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def run_sync(team: str = "", days: int = 10) -> dict:
    db = SupabaseClient()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    rows = fetch_espn(cutoff) + fetch_bbc(cutoff)

    if team:
        rows = [r for r in rows if r["team"].lower() == team.lower()]

    saved, warnings = 0, []
    for row in rows:
        try:
            db.upsert("wc_team_news", [row], on_conflict="url")
            saved += 1
        except Exception as exc:
            warnings.append(str(exc)[:200])

    return {"success": True, "data": {
        "articles_saved": saved,
        "sources": ["ESPN", "BBC Sport"],
        "warnings": warnings[:20],
    }}


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    try:
        out = run_sync(
            team=params.get("team", ""),
            days=int(params.get("days", 10)),
        )
    except Exception as exc:
        out = {"success": False, "error": str(exc)}
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
