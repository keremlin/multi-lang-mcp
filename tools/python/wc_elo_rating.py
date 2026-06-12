"""
WC_elo_rating — fetch national team Elo ratings.

Sources tried in order:
  1. eloratings.net JSON API  (primary – national team Elo)
  2. eloratings.net HTML table (fallback scrape)
  3. clubelo.com via soccerdata ClubElo (club teams; useful for squad quality)

Input (stdin JSON):
  team      str   Team name to look up, e.g. "Argentina" (empty = return top list)
  top_n     int   Return top N teams when team is empty (default 30)
  source    str   "elo" (default) | "clubelo"
  timeout   int   HTTP timeout seconds (default 20)

Output:
  {"success": true, "data": {"team": ..., "elo": ..., "rank": ..., "source": ...}}
"""
import sys
import json
import logging
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}


def _try_eloratings_json(team: str, top_n: int, timeout: int) -> dict | None:
    """Try eloratings.net JSON endpoints."""
    import requests

    # Known endpoint pattern — returns JSON array of {rank, team, elo, ...}
    urls = [
        "https://eloratings.net/en.json",
        "https://www.eloratings.net/en.json",
        "https://eloratings.net/api/ratings",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=timeout)
            if r.status_code == 200 and r.text.strip().startswith("["):
                data = r.json()
                if isinstance(data, list) and data:
                    return data
        except Exception:
            continue
    return None


def _try_eloratings_html(team: str, top_n: int, timeout: int) -> dict | None:
    """Scrape eloratings.net main page for embedded data or HTML table."""
    import requests
    from bs4 import BeautifulSoup

    try:
        r = requests.get("https://www.eloratings.net/", headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Strategy A: JSON array embedded in a <script> tag
        for script in soup.find_all("script"):
            text = script.string or ""
            if '"elo"' in text or '"rating"' in text.lower():
                match = re.search(r'(\[\s*\{[^;]+\}\s*\])', text, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass

        # Strategy B: plain HTML table
        table = soup.find("table")
        if table:
            headers_row = table.find("tr")
            headers = [th.get_text(strip=True).lower() for th in (headers_row.find_all("th") if headers_row else [])]
            rows = []
            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cells and len(cells) >= 2:
                    rows.append(dict(zip(headers, cells)) if headers else {"raw": cells})
            if rows:
                return rows
    except Exception as exc:
        logger.debug("eloratings HTML scrape failed: %s", exc)
    return None


def _try_clubelo(team: str, top_n: int, timeout: int) -> dict:
    """Use soccerdata ClubElo for club-level Elo ratings."""
    try:
        import soccerdata as sd
        from datetime import date

        celo = sd.ClubElo()
        if team:
            hist = celo.read_team_history(team)
            df = hist.reset_index()
            latest = df.sort_values("date").iloc[-1] if not df.empty else None
            if latest is None:
                return {"success": False, "error": f"No ClubElo history for '{team}'"}
            return {
                "success": True,
                "data": {
                    "team": team,
                    "elo": float(latest.get("elo", 0)),
                    "rank": int(latest.get("rank", 0)) if "rank" in latest.index else None,
                    "source": "clubelo.com (CLUB Elo — not national team)",
                    "note": "ClubElo tracks CLUB teams. For national teams use source='elo'.",
                },
            }
        else:
            today = date.today().isoformat()
            df = celo.read_by_date(today).reset_index()
            records = df.head(top_n).to_dict(orient="records")
            return {
                "success": True,
                "data": {
                    "rankings": records,
                    "total": len(df),
                    "source": "clubelo.com (CLUB Elo — not national teams)",
                },
            }
    except Exception as exc:
        return {"success": False, "error": f"ClubElo failed: {exc}"}


def fetch_elo_ratings(
    team: str = "",
    top_n: int = 30,
    source: str = "elo",
    timeout: int = 20,
) -> dict:
    if source == "clubelo":
        return _try_clubelo(team, top_n, timeout)

    # --- eloratings.net path ---
    data = _try_eloratings_json(team, top_n, timeout)
    if data is None:
        data = _try_eloratings_html(team, top_n, timeout)

    if data is None:
        return {
            "success": False,
            "error": (
                "Could not fetch data from eloratings.net. "
                "The site may be JavaScript-rendered. "
                "Try source='clubelo' for club teams, or provide elo values manually "
                "to WC_predict_outcome."
            ),
        }

    # Normalise list of dicts
    if isinstance(data, list):
        if team:
            team_lc = team.lower()
            matches = [
                row for row in data
                if team_lc in str(row).lower()
            ]
            if not matches:
                return {
                    "success": False,
                    "error": f"Team '{team}' not found in eloratings.net data",
                    "sample_teams": [str(r) for r in data[:5]],
                }
            return {
                "success": True,
                "data": {
                    "team": team,
                    "matches": matches,
                    "source": "eloratings.net",
                },
            }
        return {
            "success": True,
            "data": {
                "rankings": data[:top_n],
                "total": len(data),
                "source": "eloratings.net",
            },
        }

    return {"success": False, "error": "Unexpected data format from eloratings.net"}


def main():
    raw = sys.stdin.read().strip()
    params = {}
    if raw:
        try:
            params = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
            sys.exit(1)

    result = fetch_elo_ratings(
        team=params.get("team", ""),
        top_n=int(params.get("top_n", 30)),
        source=params.get("source", "elo"),
        timeout=int(params.get("timeout", 20)),
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
