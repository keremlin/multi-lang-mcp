"""
WC Match Info UI — standalone CustomTkinter window.

Launched as a detached subprocess by wc_match_info_ui.py.
Reads match + prediction data from a JSON file passed as --data <path>.

Usage:
    python wc_ui_window.py --data C:/temp/wc_match_data.json
"""
import sys
import json
import argparse
import io
import urllib.request
from pathlib import Path

import customtkinter as ctk
from PIL import Image

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":       "#0d1117",
    "card":     "#161b22",
    "card_a":   "#0d2137",
    "card_b":   "#1a0d15",
    "h2h_bg":   "#111820",
    "border":   "#30363d",
    "team_a":   "#388bfd",
    "team_b":   "#f85149",
    "gold":     "#e3b341",
    "green":    "#3fb950",
    "yellow":   "#d29922",
    "text":     "#e6edf3",
    "muted":    "#8b949e",
    "win_bar":  "#238636",
    "draw_bar": "#9e6a03",
    "loss_bar": "#8b1a1a",
}

# 2-letter badge code for each team (shown as styled jersey badge)
TEAM_CODE = {
    "Argentina": "AR", "Australia": "AU", "Austria": "AT",
    "Belgium": "BE", "Bosnia-Herzegovina": "BA", "Brazil": "BR",
    "Canada": "CA", "Cape Verde Islands": "CV", "Ivory Coast": "CI",
    "Colombia": "CO", "Congo DR": "CD", "Croatia": "HR",
    "Czechia": "CZ", "Curaçao": "CW", "Ecuador": "EC",
    "Egypt": "EG", "England": "EN", "France": "FR",
    "Germany": "DE", "Ghana": "GH", "Haiti": "HT",
    "Iran": "IR", "Iraq": "IQ", "Japan": "JP",
    "Jordan": "JO", "Mexico": "MX", "Morocco": "MA",
    "Netherlands": "NL", "New Zealand": "NZ", "Norway": "NO",
    "Panama": "PA", "Paraguay": "PY", "Portugal": "PT",
    "Qatar": "QA", "Saudi Arabia": "SA", "Scotland": "SC",
    "Senegal": "SN", "South Africa": "ZA", "South Korea": "KR",
    "Spain": "ES", "Sweden": "SE", "Switzerland": "CH",
    "Tunisia": "TN", "Turkey": "TR", "United States": "US",
    "Uruguay": "UY", "Uzbekistan": "UZ", "Algeria": "DZ",
    "USA": "US",
}


_FLAGS_DIR = Path(__file__).parent.parent.parent / "flags_cache"
_FLAG_CACHE: dict[str, object] = {}

# flagcdn.com codes that differ from ISO / TEAM_CODE
_FLAG_OVERRIDE = {
    "England":  "gb-eng",
    "Scotland": "gb-sct",
}


def team_code(name: str) -> str:
    return TEAM_CODE.get(name, name[:2].upper())


def _flag_code(name: str) -> str:
    if name in _FLAG_OVERRIDE:
        return _FLAG_OVERRIDE[name]
    return TEAM_CODE.get(name, name[:2]).lower()


_PLAYER_CACHE: dict[str, object] = {}


def get_flag_image(name: str, width: int = 120, height: int = 80):
    """Download flag from flagcdn.com (w320 format), cache to disk, return CTkImage or None."""
    cache_key = f"{name}_{width}x{height}"
    if cache_key in _FLAG_CACHE:
        return _FLAG_CACHE[cache_key]
    code = _flag_code(name)
    _FLAGS_DIR.mkdir(exist_ok=True)
    cache_file = _FLAGS_DIR / f"{code}_{width}x{height}.png"
    try:
        if not cache_file.exists():
            # flagcdn.com uses /w{pixels}/{code}.png — not /WxH/
            url = f"https://flagcdn.com/w320/{code}.png"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                raw = resp.read()
            # Resize to requested display size and save
            img_raw = Image.open(io.BytesIO(raw)).convert("RGBA")
            img_raw = img_raw.resize((width, height), Image.LANCZOS)
            cache_file.write_bytes(raw)   # cache original; resize happens at load
        img = Image.open(cache_file).convert("RGBA").resize((width, height), Image.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(width, height))
        _FLAG_CACHE[cache_key] = ctk_img
        return ctk_img
    except Exception:
        _FLAG_CACHE[cache_key] = None
        return None


def get_player_image(photo_url: str, size: int = 48):
    """Load a player headshot from disk cache or download; return circular CTkImage or None."""
    if not photo_url:
        return None
    if photo_url in _PLAYER_CACHE:
        return _PLAYER_CACHE[photo_url]
    _FLAGS_DIR.mkdir(exist_ok=True)
    slug = photo_url.split("/")[-1]
    cache_file = _FLAGS_DIR / f"player_{slug}"
    try:
        if not cache_file.exists():
            req = urllib.request.Request(photo_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                cache_file.write_bytes(resp.read())
        raw = Image.open(cache_file).convert("RGBA")
        # Crop to square from center, then resize
        w, h = raw.size
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        raw = raw.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
        # Circular mask
        from PIL import ImageDraw
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(raw, mask=mask)
        ctk_img = ctk.CTkImage(light_image=result, dark_image=result, size=(size, size))
        _PLAYER_CACHE[photo_url] = ctk_img
        return ctk_img
    except Exception:
        _PLAYER_CACHE[photo_url] = None
        return None


def form_dot(ch: str) -> tuple[str, str]:
    if ch == "W":
        return "●", C["green"]
    if ch == "D":
        return "●", C["yellow"]
    return "●", C["team_b"]


class MatchApp(ctk.CTk):
    def __init__(self, data: dict):
        super().__init__()

        d      = data.get("data", data)
        ta     = d.get("team_a_stats", {})
        tb     = d.get("team_b_stats", {})
        pred   = d.get("prediction", {})
        h2h    = d.get("head_to_head") or {}
        probs  = pred.get("outcome_probs", {})
        markets = pred.get("markets", {})
        scores = pred.get("score_distribution", [])
        eg     = pred.get("expected_goals", {})
        detail = pred.get("full_outcome_detail", {}) or {}
        h2h_adj = pred.get("h2h_adjustment_pct", 0)

        name_a = ta.get("team", "Team A")
        name_b = tb.get("team", "Team B")

        self.title(f"⚽ WC 2026 — {name_a}  vs  {name_b}")
        self.configure(bg_color=C["bg"], fg_color=C["bg"])
        self.after(0, lambda: self.state("zoomed"))

        # ── ROOT GRID ─────────────────────────────────────────────────────
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=3)  # main
        self.grid_rowconfigure(2, weight=1)  # footer
        self.grid_rowconfigure(3, weight=1)  # news
        self.grid_rowconfigure(4, weight=2)  # squad

        # ── HEADER ────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="🏆  FIFA WORLD CUP 2026",
            font=ctk.CTkFont("Arial", 22, "bold"),
            text_color=C["gold"],
        ).grid(row=0, column=0, pady=(14, 2))

        group_a = ta.get("group", "")
        group_str = f"GROUP {group_a.replace('GROUP_', '')}" if group_a else ""
        ctk.CTkLabel(
            header, text=group_str,
            font=ctk.CTkFont("Arial", 13),
            text_color=C["muted"],
        ).grid(row=1, column=0, pady=(0, 12))

        # ── MAIN ──────────────────────────────────────────────────────────
        main = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        main.grid(row=1, column=0, sticky="nsew", padx=20, pady=(10, 5))
        main.grid_columnconfigure(0, weight=2)
        main.grid_columnconfigure(1, weight=3)
        main.grid_columnconfigure(2, weight=2)
        main.grid_rowconfigure(0, weight=1)

        self._team_card(main, ta, name_a, C["team_a"], C["card_a"],
                        eg.get("lambda_a"), col=0)
        self._center_panel(main, name_a, name_b, probs, eg, detail, h2h, h2h_adj, col=1)
        self._team_card(main, tb, name_b, C["team_b"], C["card_b"],
                        eg.get("lambda_b"), col=2)

        # ── FOOTER ────────────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=1)

        self._scores_panel(footer, name_a, name_b, scores, col=0)
        self._markets_panel(footer, markets, col=1)

        # ── NEWS SECTION ──────────────────────────────────────────────────
        news_frame = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        news_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 4))
        news_frame.grid_columnconfigure(0, weight=1)
        news_frame.grid_columnconfigure(1, weight=1)
        self._news_panel(news_frame, name_a, C["team_a"], col=0)
        self._news_panel(news_frame, name_b, C["team_b"], col=1)

        # ── SQUAD SECTION ─────────────────────────────────────────────────
        squad_frame = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        squad_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 12))
        squad_frame.grid_columnconfigure(0, weight=1)
        squad_frame.grid_columnconfigure(1, weight=1)
        self._squad_panel(squad_frame, name_a, C["team_a"], col=0)
        self._squad_panel(squad_frame, name_b, C["team_b"], col=1)

    # ── Team card ─────────────────────────────────────────────────────────
    def _team_card(self, parent, stats, name, accent, bg, lam, col):
        card = ctk.CTkFrame(parent, fg_color=bg, corner_radius=16)
        card.grid(row=0, column=col, sticky="nsew", padx=12, pady=8)
        card.grid_columnconfigure(0, weight=1)

        # Flag image (downloaded from flagcdn.com, falls back to letter badge)
        flag_img = get_flag_image(name, 120, 80)
        if flag_img:
            ctk.CTkLabel(card, image=flag_img, text="").grid(
                row=0, column=0, pady=(24, 6))
        else:
            badge_frame = ctk.CTkFrame(card, fg_color=accent, corner_radius=14,
                                       width=90, height=90)
            badge_frame.grid(row=0, column=0, pady=(24, 6))
            badge_frame.grid_propagate(False)
            badge_frame.grid_columnconfigure(0, weight=1)
            badge_frame.grid_rowconfigure(0, weight=1)
            ctk.CTkLabel(badge_frame, text=team_code(name),
                         font=ctk.CTkFont("Arial", 34, "bold"),
                         text_color="#ffffff",
                         ).grid(row=0, column=0)

        ctk.CTkLabel(card, text=name,
                     font=ctk.CTkFont("Arial", 24, "bold"),
                     text_color=accent, wraplength=280,
                     ).grid(row=1, column=0, padx=20, pady=(0, 6))

        # FIFA ranking badge
        ranking = stats.get("fifa_ranking")
        if ranking:
            ctk.CTkLabel(card, text=f"World Ranking  #{ranking}",
                         font=ctk.CTkFont("Arial", 13),
                         text_color=C["gold"],
                         ).grid(row=2, column=0, pady=(0, 10))

        # Divider
        ctk.CTkFrame(card, height=2, fg_color=accent).grid(
            row=3, column=0, sticky="ew", padx=30, pady=(0, 14))

        def stat_row(r, label, value, vc=C["text"]):
            f = ctk.CTkFrame(card, fg_color="transparent")
            f.grid(row=r, column=0, sticky="ew", padx=32, pady=2)
            f.grid_columnconfigure(0, weight=1)
            f.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont("Arial", 12),
                         text_color=C["muted"], anchor="w").grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(f, text=str(value), font=ctk.CTkFont("Arial", 12, "bold"),
                         text_color=vc, anchor="e").grid(row=0, column=1, sticky="e")

        elo = stats.get("elo", "—")
        stat_row(4, "Elo Rating", f"{int(elo):,}" if elo else "—", accent)
        stat_row(5, "Group", stats.get("group", "—").replace("GROUP_", "Group "))
        stat_row(6, "Expected Goals (λ)", f"{lam:.2f}" if lam else "—")

        avg_gf = stats.get("avg_goals_scored")
        avg_ga = stats.get("avg_goals_conceded")
        stat_row(7, "Avg Scored (L10)", f"{float(avg_gf):.2f}" if avg_gf else "—")
        stat_row(8, "Avg Conceded (L10)", f"{float(avg_ga):.2f}" if avg_ga else "—")

        # Form last 10 (dots)
        form10 = stats.get("form_last10", "") or stats.get("form_last5", "") or ""
        if form10:
            ctk.CTkLabel(card, text="Form (last 10)",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["muted"]).grid(row=9, column=0, pady=(12, 2))
            form_frame = ctk.CTkFrame(card, fg_color="transparent")
            form_frame.grid(row=10, column=0, pady=(0, 8))
            for i, ch in enumerate(form10[-10:]):
                sym, col_c = form_dot(ch)
                ctk.CTkLabel(form_frame, text=sym,
                             font=ctk.CTkFont("Arial", 18),
                             text_color=col_c).grid(row=0, column=i, padx=2)

            # W/D/L counts below dots
            w = form10.count("W")
            d = form10.count("D")
            l = form10.count("L")
            ctk.CTkLabel(card, text=f"W{w}  D{d}  L{l}",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["muted"]).grid(row=11, column=0, pady=(0, 16))
        else:
            ctk.CTkLabel(card, text="No form data",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["muted"]).grid(row=9, column=0, pady=(14, 20))

    # ── Center prediction panel ────────────────────────────────────────────
    def _center_panel(self, parent, name_a, name_b, probs, eg, detail,
                      h2h, h2h_adj, col):
        panel = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=16)
        panel.grid(row=0, column=col, sticky="nsew", padx=8, pady=8)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(panel, text="PREDICTION",
                     font=ctk.CTkFont("Arial", 16, "bold"),
                     text_color=C["gold"],
                     ).grid(row=0, column=0, pady=(20, 4))

        ctk.CTkLabel(panel, text="Win Probability",
                     font=ctk.CTkFont("Arial", 12),
                     text_color=C["muted"],
                     ).grid(row=1, column=0, pady=(0, 10))

        ctk.CTkLabel(panel, text="VS",
                     font=ctk.CTkFont("Arial", 34, "bold"),
                     text_color=C["muted"],
                     ).grid(row=2, column=0, pady=(0, 12))

        pw  = probs.get(f"{name_a}_win", 0)
        pd_ = probs.get("draw", 0)
        pl  = probs.get(f"{name_b}_win", 0)

        def prob_row(r, label, pct, bar_color):
            ctk.CTkLabel(panel, text=label,
                         font=ctk.CTkFont("Arial", 12),
                         text_color=C["muted"]).grid(row=r, column=0, padx=30, sticky="w")
            bf = ctk.CTkFrame(panel, fg_color="transparent")
            bf.grid(row=r+1, column=0, padx=30, sticky="ew", pady=(2, 8))
            bf.grid_columnconfigure(0, weight=1)
            bar = ctk.CTkProgressBar(bf, height=16, corner_radius=8,
                                     progress_color=bar_color, fg_color=C["border"])
            bar.grid(row=0, column=0, sticky="ew")
            bar.set(max(0.0, min(1.0, pct / 100)))
            ctk.CTkLabel(bf, text=f"{pct}%",
                         font=ctk.CTkFont("Arial", 13, "bold"),
                         text_color=C["text"]).grid(row=0, column=1, padx=(8, 0))

        prob_row(3,  name_a, pw,  C["team_a"])
        prob_row(5,  "Draw",  pd_, C["draw_bar"])
        prob_row(7,  name_b, pl,  C["team_b"])

        # H2H adjustment note — below all bars, right-aligned small caption
        if h2h_adj and h2h_adj > 0:
            ctk.CTkLabel(panel,
                         text=f"Probabilities include {h2h_adj}% H2H historical weight",
                         font=ctk.CTkFont("Arial", 10),
                         text_color=C["muted"],
                         ).grid(row=9, column=0, pady=(0, 6))

        # Divider
        ctk.CTkFrame(panel, height=1, fg_color=C["border"]).grid(
            row=10, column=0, sticky="ew", padx=20, pady=(2, 10))

        # Expected goals
        la = eg.get("lambda_a", 0)
        lb = eg.get("lambda_b", 0)
        ctk.CTkLabel(panel, text="Expected Goals",
                     font=ctk.CTkFont("Arial", 12),
                     text_color=C["muted"]).grid(row=11, column=0)

        eg_frame = ctk.CTkFrame(panel, fg_color="transparent")
        eg_frame.grid(row=12, column=0, pady=(4, 6))
        ctk.CTkLabel(eg_frame, text=f"{la:.2f}",
                     font=ctk.CTkFont("Arial", 26, "bold"),
                     text_color=C["team_a"]).grid(row=0, column=0, padx=16)
        ctk.CTkLabel(eg_frame, text="–",
                     font=ctk.CTkFont("Arial", 18),
                     text_color=C["muted"]).grid(row=0, column=1)
        ctk.CTkLabel(eg_frame, text=f"{lb:.2f}",
                     font=ctk.CTkFont("Arial", 26, "bold"),
                     text_color=C["team_b"]).grid(row=0, column=2, padx=16)

        # Verdict
        verdict = detail.get("verdict", "")
        if verdict:
            ctk.CTkLabel(panel, text=verdict,
                         font=ctk.CTkFont("Arial", 11, slant="italic"),
                         text_color=C["gold"],
                         wraplength=250).grid(row=13, column=0, padx=20, pady=(4, 8))

        # ── H2H Section ───────────────────────────────────────────────────
        if h2h and h2h.get("played", 0) >= 1:
            ctk.CTkFrame(panel, height=1, fg_color=C["border"]).grid(
                row=14, column=0, sticky="ew", padx=20, pady=(6, 8))

            ctk.CTkLabel(panel, text="HEAD-TO-HEAD",
                         font=ctk.CTkFont("Arial", 13, "bold"),
                         text_color=C["gold"],
                         ).grid(row=15, column=0, pady=(0, 4))

            played = h2h["played"]
            wa = h2h.get("team_a_wins", 0)
            dr = h2h.get("draws", 0)
            wb = h2h.get("team_b_wins", 0)

            ctk.CTkLabel(panel, text=f"{played} matches played",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["muted"]).grid(row=16, column=0, pady=(0, 6))

            # H2H bar
            h2h_bar = ctk.CTkFrame(panel, fg_color="transparent")
            h2h_bar.grid(row=17, column=0, padx=24, sticky="ew", pady=(0, 4))
            h2h_bar.grid_columnconfigure(0, weight=wa if wa else 0)
            h2h_bar.grid_columnconfigure(1, weight=dr if dr else 0)
            h2h_bar.grid_columnconfigure(2, weight=wb if wb else 0)

            if wa:
                ctk.CTkFrame(h2h_bar, height=10, fg_color=C["team_a"],
                             corner_radius=4).grid(row=0, column=0, sticky="ew", padx=1)
            if dr:
                ctk.CTkFrame(h2h_bar, height=10, fg_color=C["draw_bar"],
                             corner_radius=0).grid(row=0, column=1, sticky="ew", padx=1)
            if wb:
                ctk.CTkFrame(h2h_bar, height=10, fg_color=C["team_b"],
                             corner_radius=4).grid(row=0, column=2, sticky="ew", padx=1)

            # W/D/L labels
            wdl_frame = ctk.CTkFrame(panel, fg_color="transparent")
            wdl_frame.grid(row=18, column=0, pady=(4, 2))
            ctk.CTkLabel(wdl_frame, text=f"{wa}W",
                         font=ctk.CTkFont("Arial", 14, "bold"),
                         text_color=C["team_a"]).grid(row=0, column=0, padx=12)
            ctk.CTkLabel(wdl_frame, text=f"{dr}D",
                         font=ctk.CTkFont("Arial", 14, "bold"),
                         text_color=C["yellow"]).grid(row=0, column=1, padx=12)
            ctk.CTkLabel(wdl_frame, text=f"{wb}W",
                         font=ctk.CTkFont("Arial", 14, "bold"),
                         text_color=C["team_b"]).grid(row=0, column=2, padx=12)

            # Goals
            ga = h2h.get("goals_a", 0)
            gb = h2h.get("goals_b", 0)
            ctk.CTkLabel(panel, text=f"Goals  {ga} – {gb}",
                         font=ctk.CTkFont("Arial", 12),
                         text_color=C["muted"]).grid(row=19, column=0, pady=(2, 2))

            last = h2h.get("last_match")
            if last:
                ctk.CTkLabel(panel, text=f"Last played: {last}",
                             font=ctk.CTkFont("Arial", 10),
                             text_color=C["muted"]).grid(row=20, column=0, pady=(0, 14))

    # ── Top scores ────────────────────────────────────────────────────────
    def _scores_panel(self, parent, name_a, name_b, scores, col):
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid(row=0, column=col, sticky="nsew", padx=20, pady=12)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(panel, text="⚽  Top Probable Scores",
                     font=ctk.CTkFont("Arial", 14, "bold"),
                     text_color=C["gold"]).grid(row=0, column=0, sticky="w", pady=(0, 8))

        hf = ctk.CTkFrame(panel, fg_color="transparent")
        hf.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(hf, text=f"{name_a[:12]}",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=C["team_a"], width=80, anchor="center").grid(row=0, column=0)
        ctk.CTkLabel(hf, text="  –  ",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=C["muted"]).grid(row=0, column=1)
        ctk.CTkLabel(hf, text=f"{name_b[:12]}",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=C["team_b"], width=80, anchor="center").grid(row=0, column=2)
        ctk.CTkLabel(hf, text="Probability",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=C["muted"], width=80, anchor="center").grid(row=0, column=3)

        for i, s in enumerate(scores[:6]):
            sc = s.get("score", "")
            pct = s.get("probability_pct", 0)
            parts = sc.split("-") if "-" in sc else ["?", "?"]
            rf = ctk.CTkFrame(panel, fg_color="transparent")
            rf.grid(row=i+2, column=0, sticky="ew", pady=1)
            ctk.CTkLabel(rf, text=parts[0],
                         font=ctk.CTkFont("Arial", 15, "bold"),
                         text_color=C["team_a"], width=80, anchor="center").grid(row=0, column=0)
            ctk.CTkLabel(rf, text=" – ",
                         font=ctk.CTkFont("Arial", 13),
                         text_color=C["muted"]).grid(row=0, column=1)
            ctk.CTkLabel(rf, text=parts[1] if len(parts) > 1 else "?",
                         font=ctk.CTkFont("Arial", 15, "bold"),
                         text_color=C["team_b"], width=80, anchor="center").grid(row=0, column=2)
            ctk.CTkLabel(rf, text=f"{pct:.1f}%",
                         font=ctk.CTkFont("Arial", 13),
                         text_color=C["green"], width=80, anchor="center").grid(row=0, column=3)

    # ── Markets ───────────────────────────────────────────────────────────
    def _markets_panel(self, parent, markets, col):
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid(row=0, column=col, sticky="nsew", padx=20, pady=12)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(panel, text="📊  Betting Markets",
                     font=ctk.CTkFont("Arial", 14, "bold"),
                     text_color=C["gold"]).grid(row=0, column=0, sticky="w", pady=(0, 8))

        market_data = [
            ("Over 1.5 Goals",   markets.get("over_1_5_pct", 0)),
            ("Over 2.5 Goals",   markets.get("over_2_5_pct", 0)),
            ("Both Teams Score", markets.get("btts_pct", 0)),
            ("Under 2.5 Goals",  markets.get("under_2_5_pct", 0)),
        ]
        for i, (label, pct) in enumerate(market_data):
            rf = ctk.CTkFrame(panel, fg_color="transparent")
            rf.grid(row=i+1, column=0, sticky="ew", pady=4)
            rf.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(rf, text=label,
                         font=ctk.CTkFont("Arial", 13),
                         text_color=C["muted"], anchor="w").grid(row=0, column=0, sticky="w")
            pct_color = (C["green"] if pct >= 60 else
                         C["yellow"] if pct >= 40 else C["team_b"])
            ctk.CTkLabel(rf, text=f"{pct:.1f}%",
                         font=ctk.CTkFont("Arial", 16, "bold"),
                         text_color=pct_color).grid(row=0, column=1, padx=(16, 0))


    # ── News panel ────────────────────────────────────────────────────────
    def _news_panel(self, parent, team_name: str, accent: str, col: int):
        """Show last 5 news headlines for this team from wc_team_news."""
        try:
            _ROOT = Path(__file__).parent.parent.parent
            if str(_ROOT) not in sys.path:
                sys.path.insert(0, str(_ROOT))
            from shared.supabase_client import SupabaseClient
            db = SupabaseClient()
            rows = db.select("wc_team_news", filters={"team": team_name})
            rows.sort(key=lambda r: r.get("published_at") or "", reverse=True)
            news = rows[:5]
        except Exception:
            news = []

        outer = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12)
        outer.grid(row=0, column=col, sticky="nsew", padx=8, pady=4)
        outer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(outer, text=f"  {team_name}  LATEST NEWS",
                     font=ctk.CTkFont("Arial", 12, "bold"),
                     text_color=accent).grid(row=0, column=0, sticky="w",
                                             padx=16, pady=(10, 4))

        if not news:
            ctk.CTkLabel(outer, text="No news — run WC_news_sync",
                         font=ctk.CTkFont("Arial", 10),
                         text_color=C["muted"]).grid(row=1, column=0,
                                                     padx=16, pady=(0, 8))
            return

        for i, item in enumerate(news):
            nf = ctk.CTkFrame(outer, fg_color="transparent")
            nf.grid(row=i + 1, column=0, sticky="ew", padx=12, pady=2)
            nf.grid_columnconfigure(0, weight=1)

            src   = item.get("source", "")
            pub   = (item.get("published_at") or "")[:10]
            label = f"[{src}  {pub}]" if src else pub
            ctk.CTkLabel(nf, text=label,
                         font=ctk.CTkFont("Arial", 9),
                         text_color=C["muted"], anchor="w").grid(
                             row=0, column=0, sticky="w")
            ctk.CTkLabel(nf, text=item.get("headline", ""),
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["text"], anchor="w",
                         wraplength=380).grid(row=1, column=0, sticky="w")

        outer.grid_rowconfigure(len(news) + 1, weight=1)

    # ── Squad panel ───────────────────────────────────────────────────────
    def _squad_panel(self, parent, team_name: str, accent: str, col: int):
        """Fetch players for this team from Supabase and render them."""
        try:
            _ROOT = Path(__file__).parent.parent.parent
            if str(_ROOT) not in sys.path:
                sys.path.insert(0, str(_ROOT))
            from shared.supabase_client import SupabaseClient
            db = SupabaseClient()
            players = db.select("wc_players", filters={"team": team_name})
        except Exception:
            players = []

        outer = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12)
        outer.grid(row=0, column=col, sticky="nsew", padx=8, pady=4)
        outer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(outer, text=f"  {team_name}  SQUAD",
                     font=ctk.CTkFont("Arial", 13, "bold"),
                     text_color=accent).grid(row=0, column=0, sticky="w",
                                             padx=16, pady=(12, 6))

        if not players:
            ctk.CTkLabel(outer, text="No squad data — run WC_players_sync",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["muted"]).grid(row=1, column=0,
                                                     padx=16, pady=(0, 12))
            return

        pos_order = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
        players_sorted = sorted(players,
                                key=lambda p: (pos_order.get(p.get("position", "FWD"), 4),
                                               p.get("shirt_number") or 99))

        _POS_COLOR = {"GK": "#e3b341", "DEF": "#388bfd", "MID": "#3fb950", "FWD": "#f85149"}

        scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent", height=200)
        scroll.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        scroll.grid_columnconfigure(0, weight=0)  # #
        scroll.grid_columnconfigure(1, weight=0)  # pos pill
        scroll.grid_columnconfigure(2, weight=1)  # name
        scroll.grid_columnconfigure(3, weight=1)  # club

        # column headers
        for c_idx, hdr in enumerate(["#", "Pos", "Player", "Club / League"]):
            ctk.CTkLabel(scroll, text=hdr,
                         font=ctk.CTkFont("Arial", 10),
                         text_color=C["muted"]).grid(row=0, column=c_idx,
                                                     sticky="w", padx=(4, 8), pady=(0, 4))

        for i, p in enumerate(players_sorted):
            r = i + 1
            shirt      = p.get("shirt_number") or ""
            pos        = p.get("position", "")
            name       = p.get("name", "")
            club       = p.get("club") or "—"
            league     = p.get("club_league") or ""
            club_label = f"{club}  ·  {league}" if league else club
            injured    = p.get("injured", False)
            photo_url  = p.get("photo_url") or ""
            rating     = p.get("overall_rating")
            mv_eur     = p.get("market_value_eur")
            mv_label   = (f"€{mv_eur/1e6:.0f}M" if mv_eur and mv_eur >= 1_000_000
                          else f"€{mv_eur/1000:.0f}K" if mv_eur else "")

            row_bg = "#1a2030" if i % 2 == 0 else "transparent"
            rf = ctk.CTkFrame(scroll, fg_color=row_bg, corner_radius=4)
            rf.grid(row=r, column=0, columnspan=6, sticky="ew", pady=1)
            rf.grid_columnconfigure(0, weight=0)  # photo / initials
            rf.grid_columnconfigure(1, weight=0)  # pos pill
            rf.grid_columnconfigure(2, weight=1)  # name
            rf.grid_columnconfigure(3, weight=1)  # club
            rf.grid_columnconfigure(4, weight=0)  # rating badge
            rf.grid_columnconfigure(5, weight=0)  # market value

            # Player photo (circular) or initials fallback
            photo_img = get_player_image(photo_url, size=44)
            if photo_img:
                ctk.CTkLabel(rf, image=photo_img, text="").grid(
                    row=0, column=0, padx=(6, 6), pady=2)
            else:
                pos_col = _POS_COLOR.get(pos, C["muted"])
                initials = "".join(w[0] for w in name.split()[:2]).upper()
                init_frame = ctk.CTkFrame(rf, fg_color=pos_col, corner_radius=22,
                                          width=44, height=44)
                init_frame.grid(row=0, column=0, padx=(6, 6), pady=2)
                init_frame.grid_propagate(False)
                init_frame.grid_columnconfigure(0, weight=1)
                init_frame.grid_rowconfigure(0, weight=1)
                ctk.CTkLabel(init_frame, text=initials,
                             font=ctk.CTkFont("Arial", 13, "bold"),
                             text_color="#ffffff").grid(row=0, column=0)

            pos_col = _POS_COLOR.get(pos, C["muted"])
            pos_pill = ctk.CTkFrame(rf, fg_color=pos_col, corner_radius=4,
                                    width=36, height=20)
            pos_pill.grid(row=0, column=1, padx=(0, 8))
            pos_pill.grid_propagate(False)
            pos_pill.grid_columnconfigure(0, weight=1)
            pos_pill.grid_rowconfigure(0, weight=1)
            ctk.CTkLabel(pos_pill, text=pos,
                         font=ctk.CTkFont("Arial", 9, "bold"),
                         text_color="#ffffff").grid(row=0, column=0)

            name_text = f"🚑 {name}" if injured else name
            name_color = "#f85149" if injured else C["text"]
            ctk.CTkLabel(rf, text=name_text,
                         font=ctk.CTkFont("Arial", 12),
                         text_color=name_color, anchor="w").grid(
                             row=0, column=2, sticky="w", padx=(0, 8))

            ctk.CTkLabel(rf, text=club_label,
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["muted"], anchor="w").grid(
                             row=0, column=3, sticky="w", padx=(0, 4))

            # Overall rating badge (color-coded: ≥85 gold, ≥75 green, else muted)
            if rating:
                rat_color = (C["gold"] if rating >= 85 else
                             C["green"] if rating >= 75 else C["muted"])
                rat_frame = ctk.CTkFrame(rf, fg_color=rat_color, corner_radius=6,
                                         width=34, height=22)
                rat_frame.grid(row=0, column=4, padx=(0, 4), pady=2)
                rat_frame.grid_propagate(False)
                rat_frame.grid_columnconfigure(0, weight=1)
                rat_frame.grid_rowconfigure(0, weight=1)
                ctk.CTkLabel(rat_frame, text=str(rating),
                             font=ctk.CTkFont("Arial", 10, "bold"),
                             text_color="#ffffff").grid(row=0, column=0)

            if mv_label:
                ctk.CTkLabel(rf, text=mv_label,
                             font=ctk.CTkFont("Arial", 10),
                             text_color=C["muted"], anchor="e", width=52).grid(
                                 row=0, column=5, padx=(0, 6))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to JSON data file")
    args = parser.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)

    app = MatchApp(data)
    app.mainloop()


if __name__ == "__main__":
    main()
