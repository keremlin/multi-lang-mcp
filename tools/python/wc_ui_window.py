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
from pathlib import Path

import customtkinter as ctk

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

FLAGS = {
    "United States": "🇺🇸", "USA": "🇺🇸",
    "Brazil": "🇧🇷", "Argentina": "🇦🇷", "France": "🇫🇷",
    "Germany": "🇩🇪", "Spain": "🇪🇸", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Portugal": "🇵🇹", "Netherlands": "🇳🇱", "Belgium": "🇧🇪",
    "Croatia": "🇭🇷", "Uruguay": "🇺🇾", "Colombia": "🇨🇴",
    "Mexico": "🇲🇽", "Canada": "🇨🇦", "Japan": "🇯🇵",
    "South Korea": "🇰🇷", "Morocco": "🇲🇦", "Senegal": "🇸🇳",
    "Switzerland": "🇨🇭", "Austria": "🇦🇹", "Norway": "🇳🇴",
    "Sweden": "🇸🇪", "Denmark": "🇩🇰", "Poland": "🇵🇱",
    "Australia": "🇦🇺", "Iran": "🇮🇷", "Turkey": "🇹🇷",
    "Ecuador": "🇪🇨", "Paraguay": "🇵🇾", "Chile": "🇨🇱",
    "Ghana": "🇬🇭", "Nigeria": "🇳🇬", "Egypt": "🇪🇬",
    "Tunisia": "🇹🇳", "Algeria": "🇩🇿",
    "Saudi Arabia": "🇸🇦", "Qatar": "🇶🇦", "Iraq": "🇮🇶",
    "Jordan": "🇯🇴", "South Africa": "🇿🇦", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Czechia": "🇨🇿", "Bosnia-Herzegovina": "🇧🇦",
    "Panama": "🇵🇦", "New Zealand": "🇳🇿", "Haiti": "🇭🇹",
    "Ivory Coast": "🇨🇮", "Uzbekistan": "🇺🇿",
    "Congo DR": "🇨🇩", "Cape Verde Islands": "🇨🇻", "Curaçao": "🇨🇼",
}


def flag(team: str) -> str:
    return FLAGS.get(team, "⚽")


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

    # ── Team card ─────────────────────────────────────────────────────────
    def _team_card(self, parent, stats, name, accent, bg, lam, col):
        card = ctk.CTkFrame(parent, fg_color=bg, corner_radius=16)
        card.grid(row=0, column=col, sticky="nsew", padx=12, pady=8)
        card.grid_columnconfigure(0, weight=1)

        # Flag + name
        ctk.CTkLabel(card, text=flag(name),
                     font=ctk.CTkFont("Segoe UI Emoji", 52),
                     ).grid(row=0, column=0, pady=(24, 4))

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

        # H2H adjustment note
        if h2h_adj and h2h_adj > 0:
            ctk.CTkLabel(panel, text=f"↳ {h2h_adj}% weight from H2H history",
                         font=ctk.CTkFont("Arial", 10),
                         text_color=C["muted"],
                         ).grid(row=8, column=0, pady=(0, 4))

        # Divider
        ctk.CTkFrame(panel, height=1, fg_color=C["border"]).grid(
            row=9, column=0, sticky="ew", padx=20, pady=(6, 10))

        # Expected goals
        la = eg.get("lambda_a", 0)
        lb = eg.get("lambda_b", 0)
        ctk.CTkLabel(panel, text="Expected Goals",
                     font=ctk.CTkFont("Arial", 12),
                     text_color=C["muted"]).grid(row=10, column=0)

        eg_frame = ctk.CTkFrame(panel, fg_color="transparent")
        eg_frame.grid(row=11, column=0, pady=(4, 6))
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
                         wraplength=250).grid(row=12, column=0, padx=20, pady=(4, 8))

        # ── H2H Section ───────────────────────────────────────────────────
        if h2h and h2h.get("played", 0) >= 1:
            ctk.CTkFrame(panel, height=1, fg_color=C["border"]).grid(
                row=13, column=0, sticky="ew", padx=20, pady=(6, 8))

            ctk.CTkLabel(panel, text="HEAD-TO-HEAD",
                         font=ctk.CTkFont("Arial", 13, "bold"),
                         text_color=C["gold"],
                         ).grid(row=14, column=0, pady=(0, 4))

            played = h2h["played"]
            wa = h2h.get("team_a_wins", 0)
            dr = h2h.get("draws", 0)
            wb = h2h.get("team_b_wins", 0)

            ctk.CTkLabel(panel, text=f"{played} matches played",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["muted"]).grid(row=15, column=0, pady=(0, 6))

            # H2H bar
            h2h_bar = ctk.CTkFrame(panel, fg_color="transparent")
            h2h_bar.grid(row=16, column=0, padx=24, sticky="ew", pady=(0, 4))
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
            wdl_frame.grid(row=17, column=0, pady=(4, 2))
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
                         text_color=C["muted"]).grid(row=18, column=0, pady=(2, 2))

            last = h2h.get("last_match")
            if last:
                ctk.CTkLabel(panel, text=f"Last played: {last}",
                             font=ctk.CTkFont("Arial", 10),
                             text_color=C["muted"]).grid(row=19, column=0, pady=(0, 14))

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
