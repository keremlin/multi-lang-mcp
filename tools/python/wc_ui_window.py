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

# ── Theme ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":          "#0d1117",
    "card":        "#161b22",
    "card_a":      "#0d2137",
    "card_b":      "#1a0d15",
    "border":      "#30363d",
    "team_a":      "#388bfd",
    "team_b":      "#f85149",
    "gold":        "#e3b341",
    "green":       "#3fb950",
    "yellow":      "#d29922",
    "text":        "#e6edf3",
    "muted":       "#8b949e",
    "win_bar":     "#238636",
    "draw_bar":    "#9e6a03",
    "loss_bar":    "#8b1a1a",
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
    "Tunisia": "🇹🇳", "Algeria": "🇩🇿", "Senegal": "🇸🇳",
    "Saudi Arabia": "🇸🇦", "Qatar": "🇶🇦", "Iraq": "🇮🇶",
    "Jordan": "🇯🇴", "South Africa": "🇿🇦", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Czechia": "🇨🇿", "Slovakia": "🇸🇰", "Bosnia-Herzegovina": "🇧🇦",
    "Serbia": "🇷🇸", "Croatia": "🇭🇷", "Panama": "🇵🇦",
    "New Zealand": "🇳🇿", "Haiti": "🇭🇹", "Ivory Coast": "🇨🇮",
    "Uzbekistan": "🇺🇿", "Congo DR": "🇨🇩", "Cape Verde Islands": "🇨🇻",
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

        d         = data.get("data", data)
        self.d    = d
        ta        = d.get("team_a_stats", {})
        tb        = d.get("team_b_stats", {})
        pred      = d.get("prediction", {})
        probs     = pred.get("outcome_probs", {})
        markets   = pred.get("markets", {})
        scores    = pred.get("score_distribution", [])
        eg        = pred.get("expected_goals", {})
        detail    = pred.get("full_outcome_detail", {}) or {}

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
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="🏆  FIFA WORLD CUP 2026",
            font=ctk.CTkFont("Arial", 22, "bold"),
            text_color=C["gold"],
        ).grid(row=0, column=0, pady=(14, 2))

        group_a = ta.get("group", "")
        group_b = tb.get("group", "")
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
                        eg.get("lambda_a"), col=0, anchor="e")
        self._center_panel(main, name_a, name_b, probs, eg, detail, col=1)
        self._team_card(main, tb, name_b, C["team_b"], C["card_b"],
                        eg.get("lambda_b"), col=2, anchor="w")

        # ── FOOTER ────────────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=1)

        self._scores_panel(footer, name_a, name_b, scores, col=0)
        self._markets_panel(footer, markets, col=1)

    # ── Team card ─────────────────────────────────────────────────────────
    def _team_card(self, parent, stats, name, accent, bg, lam, col, anchor):
        card = ctk.CTkFrame(parent, fg_color=bg, corner_radius=16)
        card.grid(row=0, column=col, sticky="nsew", padx=12, pady=8)
        card.grid_columnconfigure(0, weight=1)

        # Flag + name
        ctk.CTkLabel(
            card, text=flag(name),
            font=ctk.CTkFont("Segoe UI Emoji", 52),
        ).grid(row=0, column=0, pady=(28, 4))

        ctk.CTkLabel(
            card, text=name,
            font=ctk.CTkFont("Arial", 26, "bold"),
            text_color=accent,
            wraplength=280,
        ).grid(row=1, column=0, padx=20, pady=(0, 18))

        # Divider
        ctk.CTkFrame(card, height=2, fg_color=accent).grid(
            row=2, column=0, sticky="ew", padx=30, pady=(0, 16)
        )

        # Stats rows
        def stat_row(r, label, value, vc=C["text"]):
            f = ctk.CTkFrame(card, fg_color="transparent")
            f.grid(row=r, column=0, sticky="ew", padx=32, pady=3)
            f.grid_columnconfigure(0, weight=1)
            f.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont("Arial", 13),
                         text_color=C["muted"], anchor="w").grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(f, text=str(value), font=ctk.CTkFont("Arial", 13, "bold"),
                         text_color=vc, anchor="e").grid(row=0, column=1, sticky="e")

        elo = stats.get("elo", "—")
        stat_row(3, "Elo Rating", f"{int(elo):,}" if elo else "—", accent)
        stat_row(4, "Group", stats.get("group", "—").replace("GROUP_", "Group "))
        stat_row(5, "Expected Goals (λ)", f"{lam:.2f}" if lam else "—")

        avg_gf = stats.get("avg_goals_scored")
        avg_ga = stats.get("avg_goals_conceded")
        stat_row(6, "Avg Goals Scored", f"{avg_gf:.2f}" if avg_gf else "—")
        stat_row(7, "Avg Goals Conceded", f"{avg_ga:.2f}" if avg_ga else "—")

        # Form
        form = stats.get("form_last5", "") or ""
        if form:
            ctk.CTkLabel(card, text="Recent Form",
                         font=ctk.CTkFont("Arial", 12),
                         text_color=C["muted"]).grid(row=8, column=0, pady=(12, 2))
            form_frame = ctk.CTkFrame(card, fg_color="transparent")
            form_frame.grid(row=9, column=0, pady=(0, 20))
            for i, ch in enumerate(form):
                sym, col = form_dot(ch)
                ctk.CTkLabel(form_frame, text=sym,
                             font=ctk.CTkFont("Arial", 22),
                             text_color=col).grid(row=0, column=i, padx=3)
        else:
            ctk.CTkLabel(card, text="No form data yet",
                         font=ctk.CTkFont("Arial", 11),
                         text_color=C["muted"]).grid(row=8, column=0, pady=(14, 20))

    # ── Center prediction panel ────────────────────────────────────────────
    def _center_panel(self, parent, name_a, name_b, probs, eg, detail, col):
        panel = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=16)
        panel.grid(row=0, column=col, sticky="nsew", padx=8, pady=8)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel, text="PREDICTION",
            font=ctk.CTkFont("Arial", 16, "bold"),
            text_color=C["gold"],
        ).grid(row=0, column=0, pady=(22, 4))

        ctk.CTkLabel(
            panel, text="Win Probability",
            font=ctk.CTkFont("Arial", 12),
            text_color=C["muted"],
        ).grid(row=1, column=0, pady=(0, 14))

        # VS badge
        ctk.CTkLabel(
            panel, text="VS",
            font=ctk.CTkFont("Arial", 38, "bold"),
            text_color=C["muted"],
        ).grid(row=2, column=0, pady=(0, 18))

        pw  = probs.get(f"{name_a}_win", 0)
        pd_ = probs.get("draw", 0)
        pl  = probs.get(f"{name_b}_win", 0)

        def prob_row(r, label, pct, bar_color):
            ctk.CTkLabel(panel, text=label,
                         font=ctk.CTkFont("Arial", 12),
                         text_color=C["muted"]).grid(row=r, column=0, padx=30, sticky="w")
            bar_frame = ctk.CTkFrame(panel, fg_color="transparent")
            bar_frame.grid(row=r+1, column=0, padx=30, sticky="ew", pady=(2, 10))
            bar_frame.grid_columnconfigure(0, weight=1)
            bar = ctk.CTkProgressBar(bar_frame, height=18, corner_radius=8,
                                     progress_color=bar_color, fg_color=C["border"])
            bar.grid(row=0, column=0, sticky="ew")
            bar.set(pct / 100)
            ctk.CTkLabel(bar_frame, text=f"{pct}%",
                         font=ctk.CTkFont("Arial", 13, "bold"),
                         text_color=C["text"]).grid(row=0, column=1, padx=(8, 0))

        prob_row(3,  name_a, pw,  C["team_a"])
        prob_row(5,  "Draw",  pd_, C["draw_bar"])
        prob_row(7,  name_b, pl,  C["team_b"])

        # Expected goals
        la = eg.get("lambda_a", 0)
        lb = eg.get("lambda_b", 0)
        ctk.CTkFrame(panel, height=1, fg_color=C["border"]).grid(
            row=9, column=0, sticky="ew", padx=20, pady=(8, 12)
        )
        ctk.CTkLabel(panel, text="Expected Goals",
                     font=ctk.CTkFont("Arial", 12),
                     text_color=C["muted"]).grid(row=10, column=0)

        eg_frame = ctk.CTkFrame(panel, fg_color="transparent")
        eg_frame.grid(row=11, column=0, pady=(4, 8))
        ctk.CTkLabel(eg_frame, text=f"{la:.2f}",
                     font=ctk.CTkFont("Arial", 28, "bold"),
                     text_color=C["team_a"]).grid(row=0, column=0, padx=16)
        ctk.CTkLabel(eg_frame, text="–",
                     font=ctk.CTkFont("Arial", 20),
                     text_color=C["muted"]).grid(row=0, column=1)
        ctk.CTkLabel(eg_frame, text=f"{lb:.2f}",
                     font=ctk.CTkFont("Arial", 28, "bold"),
                     text_color=C["team_b"]).grid(row=0, column=2, padx=16)

        # Verdict
        verdict = detail.get("verdict", "")
        if verdict:
            ctk.CTkLabel(panel, text=verdict,
                         font=ctk.CTkFont("Arial", 12, slant="italic"),
                         text_color=C["gold"],
                         wraplength=260).grid(row=12, column=0, padx=20, pady=(4, 20))

    # ── Top scores ────────────────────────────────────────────────────────
    def _scores_panel(self, parent, name_a, name_b, scores, col):
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid(row=0, column=col, sticky="nsew", padx=20, pady=12)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(panel, text="⚽  Top Probable Scores",
                     font=ctk.CTkFont("Arial", 14, "bold"),
                     text_color=C["gold"]).grid(row=0, column=0, sticky="w", pady=(0, 8))

        header_f = ctk.CTkFrame(panel, fg_color="transparent")
        header_f.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(header_f, text=f"{name_a[:12]}",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=C["team_a"], width=80, anchor="center").grid(row=0, column=0)
        ctk.CTkLabel(header_f, text="  –  ",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=C["muted"]).grid(row=0, column=1)
        ctk.CTkLabel(header_f, text=f"{name_b[:12]}",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=C["team_b"], width=80, anchor="center").grid(row=0, column=2)
        ctk.CTkLabel(header_f, text="Probability",
                     font=ctk.CTkFont("Arial", 11),
                     text_color=C["muted"], width=80, anchor="center").grid(row=0, column=3)

        for i, s in enumerate(scores[:6]):
            sc = s.get("score", "")
            pct = s.get("probability_pct", 0)
            parts = sc.split("-") if "-" in sc else ["?", "?"]
            fg = "transparent"
            row_frame = ctk.CTkFrame(panel, fg_color=fg)
            row_frame.grid(row=i+2, column=0, sticky="ew", pady=1)
            ctk.CTkLabel(row_frame, text=parts[0],
                         font=ctk.CTkFont("Arial", 15, "bold"),
                         text_color=C["team_a"], width=80, anchor="center").grid(row=0, column=0)
            ctk.CTkLabel(row_frame, text=" – ",
                         font=ctk.CTkFont("Arial", 13),
                         text_color=C["muted"]).grid(row=0, column=1)
            ctk.CTkLabel(row_frame, text=parts[1] if len(parts) > 1 else "?",
                         font=ctk.CTkFont("Arial", 15, "bold"),
                         text_color=C["team_b"], width=80, anchor="center").grid(row=0, column=2)
            ctk.CTkLabel(row_frame, text=f"{pct:.1f}%",
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
            ("Over 1.5 Goals",  markets.get("over_1_5_pct", 0)),
            ("Over 2.5 Goals",  markets.get("over_2_5_pct", 0)),
            ("Both Teams Score", markets.get("btts_pct", 0)),
            ("Under 2.5 Goals", markets.get("under_2_5_pct", 0)),
        ]
        for i, (label, pct) in enumerate(market_data):
            row_f = ctk.CTkFrame(panel, fg_color="transparent")
            row_f.grid(row=i+1, column=0, sticky="ew", pady=4)
            row_f.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row_f, text=label,
                         font=ctk.CTkFont("Arial", 13),
                         text_color=C["muted"], anchor="w").grid(row=0, column=0, sticky="w")
            pct_color = C["green"] if pct >= 60 else (C["yellow"] if pct >= 40 else C["team_b"])
            ctk.CTkLabel(row_f, text=f"{pct:.1f}%",
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
