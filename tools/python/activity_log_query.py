#!/usr/bin/env python3
"""Query logs/activity.log with flexible filters.

Reads args from stdin (JSON):
  date    – "today" | "yesterday" | "YYYY-MM-DD" | "YYYY-MM-DD/YYYY-MM-DD"
  tool    – partial tool name match, case-insensitive (e.g. "telegram")
  status  – "ok" | "fail" | "incomplete"  (omit or "" for all)
  search  – free-text substring matched against inputs + output
  tail    – integer; keep only the last N entries after all other filters (0 = all)
  summary – bool; return per-tool counts instead of individual entries
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_LOG  = _ROOT / "logs" / "activity.log"

_CALL_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[CALL\] (\w+) \| (.*)$"
)
_DONE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[DONE\] (\w+) \| (OK|FAIL) \| (\d+)ms \| (.*)$"
)


def _log_files_oldest_first(base: Path) -> list[Path]:
    """Return rotated + current log files in chronological order (oldest → newest)."""
    backups = []
    for f in base.parent.glob(base.name + ".*"):
        try:
            backups.append((int(f.suffix.lstrip(".")), f))
        except ValueError:
            pass
    # Higher number = older backup (.5 oldest, .1 most-recent backup)
    backups.sort(key=lambda x: x[0], reverse=True)
    ordered = [f for _, f in backups]
    if base.exists():
        ordered.append(base)
    return ordered


def _parse_entries(lines: list[str]) -> list[dict]:
    """Pair CALL/DONE lines into structured entries; unpaired CALLs → INCOMPLETE."""
    pending: dict[str, list[dict]] = defaultdict(list)
    entries: list[dict] = []

    for line in lines:
        line = line.strip()

        m = _CALL_RE.match(line)
        if m:
            ts, tool, inputs = m.groups()
            pending[tool].append({"timestamp": ts, "inputs": inputs})
            continue

        m = _DONE_RE.match(line)
        if m:
            ts, tool, status, duration_ms, output_raw = m.groups()
            call = pending[tool].pop(0) if pending[tool] else {}
            try:
                output = json.loads(output_raw)
            except json.JSONDecodeError:
                output = output_raw
            entries.append({
                "timestamp": call.get("timestamp", ts),
                "tool": tool,
                "status": status,
                "duration_ms": int(duration_ms),
                "inputs": call.get("inputs", ""),
                "output": output,
            })

    # Orphaned CALL lines (server crash or log rotation mid-call)
    for tool, calls in pending.items():
        for call in calls:
            entries.append({
                "timestamp": call["timestamp"],
                "tool": tool,
                "status": "INCOMPLETE",
                "duration_ms": None,
                "inputs": call["inputs"],
                "output": None,
            })

    entries.sort(key=lambda e: e["timestamp"])
    return entries


def _parse_date_range(s: str) -> tuple[date, date]:
    today = date.today()
    s = s.strip().lower()
    if s == "today":
        return today, today
    if s == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if "/" in s:
        a, b = s.split("/", 1)
        return date.fromisoformat(a.strip()), date.fromisoformat(b.strip())
    d = date.fromisoformat(s)
    return d, d


def main() -> None:
    raw = sys.stdin.read().strip()
    args = json.loads(raw) if raw else {}

    date_str     = str(args.get("date",   ""))
    tool_filter  = str(args.get("tool",   "")).lower()
    status_filter = str(args.get("status","")).upper()
    search_text  = str(args.get("search", "")).lower()
    tail         = int(args.get("tail",    0))
    summary_mode = bool(args.get("summary", False))

    if not _LOG.exists() and not list(_LOG.parent.glob(_LOG.name + ".*")):
        print(json.dumps({"success": True, "total": 0, "entries": [],
                          "message": "No activity log found yet — make a tool call first."}))
        return

    date_range = None
    if date_str:
        try:
            date_range = _parse_date_range(date_str)
        except ValueError as exc:
            print(json.dumps({
                "success": False,
                "error": (f"Invalid date '{date_str}': {exc}. "
                          "Use: today / yesterday / YYYY-MM-DD / YYYY-MM-DD/YYYY-MM-DD")
            }))
            return

    # Read all log files in chronological order
    all_lines: list[str] = []
    for lf in _log_files_oldest_first(_LOG):
        all_lines.extend(lf.read_text(encoding="utf-8", errors="replace").splitlines())

    entries = _parse_entries(all_lines)

    # ── Filters ──────────────────────────────────────────────────────────────
    filtered: list[dict] = []
    for e in entries:
        if date_range:
            try:
                entry_date = datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S").date()
            except ValueError:
                continue
            if not (date_range[0] <= entry_date <= date_range[1]):
                continue

        if tool_filter and tool_filter not in e["tool"].lower():
            continue

        if status_filter and e["status"] != status_filter:
            continue

        if search_text:
            haystack = (e["inputs"] + " " + json.dumps(e["output"] or "")).lower()
            if search_text not in haystack:
                continue

        filtered.append(e)

    if tail > 0:
        filtered = filtered[-tail:]

    # ── Output ───────────────────────────────────────────────────────────────
    if summary_mode:
        counts: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "ok": 0, "fail": 0, "incomplete": 0, "total_ms": 0}
        )
        for e in filtered:
            c = counts[e["tool"]]
            c["total"] += 1
            key = e["status"].lower()
            if key in c:
                c[key] += 1
            if e["duration_ms"] is not None:
                c["total_ms"] += e["duration_ms"]

        rows = []
        for tool, c in sorted(counts.items()):
            completed = c["ok"] + c["fail"]
            rows.append({
                "tool": tool,
                "total": c["total"],
                "ok": c["ok"],
                "fail": c["fail"],
                "incomplete": c["incomplete"],
                "avg_duration_ms": round(c["total_ms"] / completed) if completed else None,
            })
        print(json.dumps({"success": True, "total": len(rows), "summary": rows},
                         ensure_ascii=False))
    else:
        print(json.dumps({"success": True, "total": len(filtered), "entries": filtered},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
