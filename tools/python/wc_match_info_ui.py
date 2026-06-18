"""
WC_match_info_ui — fetch match + prediction data and open the UI window.

Spawns wc_ui_window.py as a detached Windows process so the MCP call
returns immediately while the window stays open.

Input (stdin JSON):
  team_a  str  e.g. "Brazil"
  team_b  str  e.g. "United States"

Output (returned instantly):
  {"success": true, "data": {"message": "UI opened", ...prediction summary...}}
"""
import sys
import json
import subprocess
import tempfile
import os
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.python.wc_analyze_match import analyze_match


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

    team_a    = p.get("team_a", "").strip()
    team_b    = p.get("team_b", "").strip()
    summary_a = p.get("summary_a", "").strip()
    summary_b = p.get("summary_b", "").strip()
    if not team_a or not team_b:
        print(json.dumps({"success": False, "error": "'team_a' and 'team_b' are required"}))
        sys.exit(1)

    # Fetch prediction data
    result = analyze_match(
        team_a=team_a,
        team_b=team_b,
        elo_a_override=float(p.get("elo_a", 0) or 0),
        elo_b_override=float(p.get("elo_b", 0) or 0),
        home_adv=float(p.get("home_advantage", 0) or 0),
    )

    if not result.get("success"):
        print(json.dumps(result))
        sys.exit(1)

    # Inject AI-generated summaries if provided
    if summary_a or summary_b:
        result.setdefault("data", {})["summaries"] = {
            "team_a": summary_a,
            "team_b": summary_b,
        }

    # Write data to a temp file that the UI window will read
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False,
        prefix="wc_match_", encoding="utf-8"
    )
    json.dump(result, tmp, ensure_ascii=False)
    tmp.close()

    python_exe = sys.executable
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    # Spawn UI window as detached process (returns instantly)
    ui_script = str(_ROOT / "tools" / "python" / "wc_ui_window.py")
    subprocess.Popen(
        [python_exe, ui_script, "--data", tmp.name],
        creationflags=flags, close_fds=True, cwd=str(_ROOT),
    )

    # Background: enrich club data for both teams (skips players that already have it)
    root_str = str(_ROOT).replace("\\", "\\\\")
    for team in (team_a, team_b):
        team_escaped = team.replace("'", "\\'")
        subprocess.Popen(
            [python_exe, "-c",
             f"import sys; sys.path.insert(0, r'{root_str}'); "
             f"from dotenv import load_dotenv; from pathlib import Path; "
             f"load_dotenv(Path(r'{root_str}') / '.env'); "
             f"from tools.python.wc_players_sync import run_sync; "
             f"run_sync('clubs', '{team_escaped}')"],
            creationflags=flags, close_fds=True, cwd=str(_ROOT),
        )

    # Return summary immediately
    d = result.get("data", {})
    pred = d.get("prediction", {})
    probs = pred.get("outcome_probs", {})
    eg    = pred.get("expected_goals", {})

    print(json.dumps({
        "success": True,
        "data": {
            "message": f"UI opened — {team_a} vs {team_b}",
            "outcome_probs": probs,
            "expected_goals": eg,
            "top_scores": pred.get("score_distribution", [])[:5],
            "markets": pred.get("markets", {}),
            "verdict": (pred.get("full_outcome_detail") or {}).get("verdict", ""),
        },
    }))


if __name__ == "__main__":
    main()
