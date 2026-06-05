#!/usr/bin/env python3
"""
Download Manager UI — auto-launched by YouTube / Telegram download MCP tools.
Polls data/downloads_progress.json every 500 ms and shows live progress cards.
Single-instance enforced via a local socket on port 37842.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from shared import download_progress as _dp
    _DP_OK = True
except Exception:
    _DP_OK = False

_PROGRESS_FILE = _ROOT / "data" / "downloads_progress.json"
_TOOL_PATH = _ROOT / "tools" / "python" / "video_converter_lg.py"
_UI_PORT = 37842
_POLL_MS = 500
_AUTO_CLOSE_SECS = 30

# ── Colour palette ────────────────────────────────────────────────────────────
C_BG      = "#1e1e2e"
C_SURFACE = "#2a2a3e"
C_BORDER  = "#45475a"
C_TEXT    = "#cdd6f4"
C_MUTED   = "#a6adc8"
C_YT      = "#f38ba8"
C_TG      = "#89b4fa"
C_CVT     = "#cba6f7"
C_OK      = "#a6e3a1"
C_ERR     = "#f38ba8"
C_BAR_TG  = "#89b4fa"
C_BAR_YT  = "#fab387"
C_BAR_CVT = "#cba6f7"
C_BAR_BG  = "#313244"
C_BTN     = "#313244"
C_BTN_ACT = "#45475a"

_NO_WIN = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_PRESETS = ["ultrafast", "veryfast", "faster", "fast", "medium", "slow", "slower"]


def _kill_pid(pid: int):
    """Kill a process tree by PID (Windows + Unix)."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
            )
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


class DownloadManagerApp:

    def __init__(self):
        self._srv = self._bind_single_instance()
        self._cards: dict = {}
        self._procs: dict = {}          # dl_id → Popen for convert jobs
        self._all_done_since: float | None = None
        self._conv_file: str = ""       # currently selected file for convert

        self.root = tk.Tk()
        self.root.title("Download Manager")
        self.root.configure(bg=C_BG)
        self.root.geometry("600x340")
        self.root.minsize(440, 280)
        self.root.resizable(True, True)
        self.root.attributes("-topmost", True)
        self.root.after(2500, lambda: self.root.attributes("-topmost", False))

        self._setup_styles()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(_POLL_MS, self._poll)
        self.root.mainloop()

    # ── Single-instance ───────────────────────────────────────────────────────

    def _bind_single_instance(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", _UI_PORT))
            srv.listen(5)
            threading.Thread(
                target=self._accept_focus_requests, args=(srv,), daemon=True
            ).start()
            return srv
        except OSError:
            sys.exit(0)

    def _accept_focus_requests(self, srv):
        while True:
            try:
                conn, _ = srv.accept()
                conn.close()
                self.root.after(0, self._bring_to_front)
            except Exception:
                return

    def _bring_to_front(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    # ── Styles ────────────────────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        for name, fg in [
            ("TG.Horizontal.TProgressbar",  C_BAR_TG),
            ("YT.Horizontal.TProgressbar",  C_BAR_YT),
            ("CV.Horizontal.TProgressbar",  C_BAR_CVT),
            ("OK.Horizontal.TProgressbar",  C_OK),
            ("ERR.Horizontal.TProgressbar", C_ERR),
        ]:
            s.configure(
                name,
                troughcolor=C_BAR_BG, background=fg,
                bordercolor=C_BG, lightcolor=fg, darkcolor=fg, relief="flat",
            )
        s.configure("Dark.TCombobox",
                    fieldbackground=C_BTN, background=C_BTN,
                    foreground=C_TEXT, arrowcolor=C_MUTED)
        s.configure("Dark.TSpinbox",
                    fieldbackground=C_BTN, background=C_BTN,
                    foreground=C_TEXT, arrowcolor=C_MUTED)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=C_BG, pady=10, padx=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="↓  Download Manager", bg=C_BG, fg=C_TEXT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        self._hdr_status = tk.Label(hdr, text="", bg=C_BG, fg=C_MUTED,
                                     font=("Segoe UI", 9))
        self._hdr_status.pack(side="right")
        tk.Frame(self.root, bg=C_BORDER, height=1).pack(fill="x")

        # ── Scrollable cards ─────────────────────────────────────────────────
        outer = tk.Frame(self.root, bg=C_BG)
        outer.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(outer, bg=C_BG, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=C_BG)
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=vsb.set)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._canvas.bind_all("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # ── Convert panel ─────────────────────────────────────────────────────
        tk.Frame(self.root, bg=C_BORDER, height=1).pack(fill="x")
        self._convert_frame = tk.Frame(self.root, bg=C_BG, padx=14, pady=8)
        self._convert_frame.pack(fill="x")
        self._build_convert_panel()

    def _on_inner_configure(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_resize(self, e):
        self._canvas.itemconfig(self._win_id, width=e.width)

    # ── Convert panel ─────────────────────────────────────────────────────────

    def _build_convert_panel(self):
        f = self._convert_frame

        tk.Label(f, text="↪  Convert Video", bg=C_BG, fg=C_CVT,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w",
                                                      columnspan=6, pady=(0, 4))

        # Row 1 controls
        self._browse_btn = tk.Button(
            f, text="📁 Browse", bg=C_BTN, fg=C_TEXT, activebackground=C_BTN_ACT,
            activeforeground=C_TEXT, relief="flat", font=("Segoe UI", 9),
            cursor="hand2", command=self._pick_file,
        )
        self._browse_btn.grid(row=1, column=0, padx=(0, 6))

        self._file_lbl = tk.Label(f, text="no file selected", bg=C_BG, fg=C_MUTED,
                                   font=("Segoe UI", 9), anchor="w")
        self._file_lbl.grid(row=1, column=1, sticky="ew", padx=(0, 10))

        tk.Label(f, text="Preset", bg=C_BG, fg=C_MUTED,
                 font=("Segoe UI", 8)).grid(row=1, column=2, padx=(0, 3))
        self._preset_var = tk.StringVar(value="fast")
        preset_cb = ttk.Combobox(f, textvariable=self._preset_var, values=_PRESETS,
                                  state="readonly", width=10, style="Dark.TCombobox")
        preset_cb.grid(row=1, column=3, padx=(0, 10))

        tk.Label(f, text="CRF", bg=C_BG, fg=C_MUTED,
                 font=("Segoe UI", 8)).grid(row=1, column=4, padx=(0, 3))
        self._crf_var = tk.StringVar(value="23")
        crf_spin = ttk.Spinbox(f, from_=0, to=51, textvariable=self._crf_var,
                                width=4, style="Dark.TSpinbox")
        crf_spin.grid(row=1, column=5, padx=(0, 10))

        self._conv_btn = tk.Button(
            f, text="▶  Convert", bg=C_CVT, fg=C_BG,
            activebackground="#b48ead", activeforeground=C_BG,
            relief="flat", font=("Segoe UI", 9, "bold"),
            cursor="hand2", padx=10,
            command=self._start_conversion,
        )
        self._conv_btn.grid(row=1, column=6, padx=(0, 0))

        f.columnconfigure(1, weight=1)

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.ts *.m4v"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._conv_file = path
            self._file_lbl.config(text=Path(path).name, fg=C_TEXT)

    def _start_conversion(self):
        if not self._conv_file:
            self._file_lbl.config(text="⚠ pick a file first", fg=C_ERR)
            return

        dl_id = _dp.new_download("convert", Path(self._conv_file).name) if _DP_OK else ""

        params = {
            "input_path": self._conv_file,
            "preset": self._preset_var.get(),
            "crf": int(self._crf_var.get()),
            "dl_id": dl_id,
        }

        pythonw = Path(sys.executable).with_name("pythonw.exe")
        python = str(pythonw) if pythonw.exists() else sys.executable

        proc = subprocess.Popen(
            [python, str(_TOOL_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WIN,
        )
        proc.stdin.write(json.dumps(params).encode("utf-8"))
        proc.stdin.close()

        if dl_id:
            self._procs[dl_id] = proc

        # Reset convert panel
        self._conv_file = ""
        self._file_lbl.config(text="no file selected", fg=C_MUTED)

    # ── Kill ──────────────────────────────────────────────────────────────────

    def _kill_download(self, dl_id: str):
        if dl_id in self._procs:
            try:
                _kill_pid(self._procs[dl_id].pid)
            except Exception:
                pass
            del self._procs[dl_id]
        else:
            data = self._load_data()
            pid = data.get(dl_id, {}).get("pid")
            if pid:
                _kill_pid(int(pid))

        if _DP_OK:
            try:
                _dp.update(dl_id, status="cancelled", error="Cancelled by user")
            except Exception:
                pass

    # ── Poll loop ─────────────────────────────────────────────────────────────

    def _poll(self):
        data = self._load_data()
        self._sync_cards(data)
        self._check_auto_close(data)
        self.root.after(_POLL_MS, self._poll)

    def _load_data(self) -> dict:
        try:
            if _PROGRESS_FILE.exists():
                return json.loads(_PROGRESS_FILE.read_text("utf-8"))
        except Exception:
            pass
        return {}

    def _sync_cards(self, data: dict):
        for dl_id, info in data.items():
            if dl_id not in self._cards:
                self._create_card(dl_id, info)
            else:
                self._refresh_card(dl_id, info)

        active = sum(1 for v in data.values()
                     if v.get("status") not in ("completed", "error", "cancelled"))
        total = len(data)
        self._hdr_status.config(
            text=f"{active} active  /  {total} total" if total else ""
        )

    # ── Card helpers ──────────────────────────────────────────────────────────

    def _tag(self, tool: str) -> str:
        t = tool.lower()
        if "youtube" in t or "yt_" in t:
            return "YT"
        if "telegram" in t:
            return "TG"
        if "convert" in t:
            return "CV"
        return "DL"

    def _tag_color(self, tool: str) -> str:
        t = self._tag(tool)
        return C_YT if t == "YT" else C_CVT if t == "CV" else C_TG

    def _bar_style(self, tool: str, status: str) -> str:
        if status == "completed":
            return "OK.Horizontal.TProgressbar"
        if status in ("error", "cancelled"):
            return "ERR.Horizontal.TProgressbar"
        t = self._tag(tool)
        return {"YT": "YT.Horizontal.TProgressbar",
                "CV": "CV.Horizontal.TProgressbar"}.get(t, "TG.Horizontal.TProgressbar")

    _ACTIVE = {"starting", "downloading", "converting"}

    # ── Card creation / refresh ───────────────────────────────────────────────

    def _create_card(self, dl_id: str, info: dict):
        tool = info.get("tool", "")
        card = tk.Frame(self._inner, bg=C_SURFACE, padx=14, pady=10)
        card.pack(fill="x", padx=10, pady=(4, 0))

        row1 = tk.Frame(card, bg=C_SURFACE)
        row1.pack(fill="x")

        # Kill button — always present, fg toggled for visibility
        kill_btn = tk.Button(
            row1, text="✕",
            bg=C_SURFACE, fg=C_SURFACE,            # invisible by default
            activebackground=C_SURFACE, activeforeground=C_ERR,
            font=("Segoe UI", 10, "bold"), relief="flat",
            cursor="hand2", bd=0, padx=2,
            command=lambda: self._kill_download(dl_id),
        )
        kill_btn.pack(side="right", padx=(4, 0))

        status_lbl = tk.Label(row1, text="", bg=C_SURFACE, fg=C_MUTED,
                               font=("Segoe UI", 9))
        status_lbl.pack(side="right", padx=(0, 4))

        tk.Label(row1, text=f" [{self._tag(tool)}] ",
                 bg=C_SURFACE, fg=self._tag_color(tool),
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        name_lbl = tk.Label(row1, text="", bg=C_SURFACE, fg=C_TEXT,
                             font=("Segoe UI", 10), anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True)

        bar = ttk.Progressbar(card, style=self._bar_style(tool, "starting"),
                               length=500, mode="determinate", maximum=100)
        bar.pack(fill="x", pady=(6, 2))

        info_lbl = tk.Label(card, text="", bg=C_SURFACE, fg=C_MUTED,
                             font=("Segoe UI", 9))
        info_lbl.pack(anchor="w")

        path_lbl = tk.Label(card, text="", bg=C_SURFACE, fg=C_OK,
                             font=("Segoe UI", 8), anchor="w", wraplength=530)
        path_lbl.pack(anchor="w")

        self._cards[dl_id] = {
            "tool": tool, "name_lbl": name_lbl, "status_lbl": status_lbl,
            "bar": bar, "info_lbl": info_lbl, "path_lbl": path_lbl,
            "kill_btn": kill_btn,
        }
        self._refresh_card(dl_id, info)

    def _refresh_card(self, dl_id: str, info: dict):
        w = self._cards[dl_id]
        tool   = info.get("tool", w["tool"])
        status = info.get("status", "starting")
        pct    = float(info.get("pct", 0))

        name = (info.get("name") or info.get("title") or "").strip() or "Loading…"
        w["name_lbl"].config(text=name)

        # Kill button: visible only while active
        if status in self._ACTIVE:
            w["kill_btn"].config(fg=C_ERR, cursor="hand2")
        else:
            w["kill_btn"].config(fg=C_SURFACE, cursor="")

        # Status badge
        badges = {
            "completed": ("Done ✓",     C_OK),
            "error":     ("Failed ✗",   C_ERR),
            "cancelled": ("Cancelled",  C_MUTED),
            "starting":  ("Starting…",  C_MUTED),
            "converting":("Converting", self._tag_color(tool)),
        }
        badge_text, badge_color = badges.get(
            status, ("Active", self._tag_color(tool))
        )
        w["status_lbl"].config(text=badge_text, fg=badge_color)

        w["bar"].config(value=pct, style=self._bar_style(tool, status))

        # Info / path lines
        if status in ("error", "cancelled"):
            msg = info.get("error", "Unknown error") if status == "error" else "Cancelled by user"
            w["info_lbl"].config(text=msg, fg=C_ERR)
            w["path_lbl"].config(text="")
        elif status == "completed":
            w["info_lbl"].config(text="", fg=C_MUTED)
            if info.get("saved_to"):
                w["path_lbl"].config(text=f"Saved to: {info['saved_to']}")
            elif info.get("output_dir"):
                n = info.get("downloaded_count", "")
                w["path_lbl"].config(text=f"Saved {n} file(s)  →  {info['output_dir']}")
            else:
                w["path_lbl"].config(text="")
        else:
            parts = []
            if info.get("speed_mbps"):
                parts.append(f"{float(info['speed_mbps']):.1f} MB/s")
            if info.get("eta_s"):
                eta = int(info["eta_s"])
                parts.append(f"ETA {eta // 60}m {eta % 60}s" if eta >= 60 else f"ETA {eta}s")
            if info.get("downloaded_mb") and info.get("total_mb"):
                parts.append(f"{float(info['downloaded_mb']):.0f} / {float(info['total_mb']):.0f} MB")
            elif info.get("size_mb"):
                parts.append(f"{float(info['size_mb']):.1f} MB")
            if info.get("files_done") is not None and info.get("files_total"):
                parts.append(f"file {info['files_done']} / {info['files_total']}")
            if info.get("current_file"):
                parts.append(info["current_file"])
            if pct and status == "downloading":
                parts.append(f"{pct:.0f}%")
            w["info_lbl"].config(
                text="  ·  ".join(parts) if parts else (
                    "Converting…" if status == "converting" else "Downloading…"
                ),
                fg=C_MUTED,
            )
            w["path_lbl"].config(text="")

    # ── Auto-close ────────────────────────────────────────────────────────────

    def _check_auto_close(self, data: dict):
        if not data:
            return
        terminal = {"completed", "error", "cancelled"}
        if all(v.get("status") in terminal for v in data.values()):
            if self._all_done_since is None:
                self._all_done_since = time.time()
            else:
                remaining = int(_AUTO_CLOSE_SECS - (time.time() - self._all_done_since))
                if remaining <= 0:
                    self._on_close()
                    return
                self._hdr_status.config(text=f"All done  —  closing in {remaining}s")
        else:
            self._all_done_since = None

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        try:
            self._srv.close()
        except Exception:
            pass
        try:
            data = self._load_data()
            cutoff = time.time() - 3600
            cleaned = {
                k: v for k, v in data.items()
                if v.get("updated_at", 0) > cutoff
                or v.get("status") not in ("completed", "error", "cancelled")
            }
            _PROGRESS_FILE.write_text(json.dumps(cleaned, indent=2), "utf-8")
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    DownloadManagerApp()
