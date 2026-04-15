#!/usr/bin/env python3
"""Commissioner Mode — interactive season-by-season league management."""

import os
import random
from collections import Counter

from config import Config
from franchises import ALL_FRANCHISES, Franchise
from game import GameResult, _p_score, _sim_possession, _game_pace, _HOME_PATTERNS
from league import League
from player import (Player, GUARD, WING, BIG, POSITIONS, ZONES,
                    MOT_WINNING, MOT_MARKET, MOT_LOYALTY,
                    TIER_ELITE, TIER_HIGH, TIER_MID, TIER_LOW,
                    happiness_emoji, popularity_tier)
from season import Season, PlayoffSeries, _games_per_pair, _playoff_count, _round_labels
from team import Team

# ── ANSI colors ───────────────────────────────────────────────────────────────
GOLD   = "\033[93m"
GREEN  = "\033[92m"
RED    = "\033[91m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
MUTED  = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

W = 58  # display width

# ── Terminal helpers ──────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def header(title: str, subtitle: str = ""):
    print(f"\n{BOLD}{'═' * W}{RESET}")
    print(f"  {BOLD}{title}{RESET}")
    if subtitle:
        print(f"  {MUTED}{subtitle}{RESET}")
    print(f"{BOLD}{'═' * W}{RESET}")

def divider():
    print(f"{MUTED}{'─' * W}{RESET}")

def pop_bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    bar = "█" * filled + "░" * (width - filled)
    color = GREEN if value >= 0.55 else (RED if value < 0.42 else CYAN)
    return f"{color}{bar}{RESET} {value:.0%}"

def trend(old: float, new: float) -> str:
    if new > old + 0.005: return f"{GREEN}▲{RESET}"
    if new < old - 0.005: return f"{RED}▼{RESET}"
    return f"{MUTED}—{RESET}"

def era_label(meta: float) -> str:
    """Plain-text era description (no ANSI codes)."""
    if meta > 0.10:  return "High-scoring era"
    if meta > 0.05:  return "Slight offensive lean"
    if meta < -0.10: return "Grind-it-out era"
    if meta < -0.05: return "Slight defensive lean"
    return "Balanced era"

def era_desc(meta: float) -> str:
    """Colored era label. GREEN = offensive lean, RED = defensive lean."""
    label = era_label(meta)
    if meta > 0.05:
        color = GREEN
    elif meta < -0.05:
        color = RED
    else:
        color = MUTED
    return f"{color}{label}{RESET}"


def _wl(w: int, l: int) -> str:
    """Inline W–L (pct%) string."""
    total = w + l
    pct = w / total if total else 0
    return f"{w}–{l} ({pct:.0%})"

def _fmr_tag(team) -> str:
    """Returns ' (fmr. City)' if team has relocated, else ''."""
    if len(team.franchise_history) <= 1:
        return ""
    founding = team.franchise_history[0][1]
    return f" {MUTED}(fmr. {founding.city}){RESET}"

def _avg_ratings(teams) -> tuple[float, float]:
    """Live average ORtg and DRtg across a collection of teams."""
    if not teams:
        return 110.0, 110.0
    return (sum(t.ortg for t in teams) / len(teams),
            sum(t.drtg for t in teams) / len(teams))

def _season_avg_ratings(season) -> tuple[float, float]:
    """Average ORtg and DRtg at season start (from snapshot ratings)."""
    vals = [season._start_ratings.get(t, (t.ortg, t.drtg, t.pace, t.style_3pt))
            for t in season.teams]
    return (sum(v[0] for v in vals) / len(vals),
            sum(v[1] for v in vals) / len(vals))

def _rel_net(ortg: float, drtg: float, avg_ortg: float, avg_drtg: float) -> float:
    """Net rating relative to league average. Positive = above average."""
    return (ortg - avg_ortg) - (drtg - avg_drtg)

def _fan_base(team) -> float:
    """Current fan base in millions: market engagement intensity × market size."""
    return team.market_engagement * team.franchise.effective_metro

def _fan_base_bar(fb: float, max_fb: float, width: int = 14) -> str:
    """Filled bar scaled to max_fb, with absolute value in millions."""
    frac = fb / max_fb if max_fb > 0 else 0
    filled = round(frac * width)
    bar = "█" * filled + "░" * (width - filled)
    color = GREEN if frac >= 0.55 else (RED if frac < 0.25 else CYAN)
    return f"{color}{bar}{RESET} {fb:.1f}M"

def _show_risk_reward(cost: str, risk: str, reward: str, note: str = "") -> None:
    """Print a compact cost/risk/reward panel at the top of a decision screen."""
    def _c(level: str, invert: bool) -> str:
        hi = GREEN if invert else RED
        lo = RED if invert else GREEN
        if level == "High":             return hi
        if level in ("Medium","Varies"):return GOLD
        if level in ("Low","Free"):     return lo
        return MUTED
    cost_c = _c(cost, invert=False)
    risk_c = _c(risk, invert=False)
    rew_c  = _c(reward, invert=True)
    print(f"  {MUTED}Cost:{RESET} {cost_c}{cost:<8}{RESET}  "
          f"{MUTED}Risk:{RESET} {risk_c}{risk:<8}{RESET}  "
          f"{MUTED}Reward:{RESET} {rew_c}{reward}{RESET}")
    if note:
        print(f"  {MUTED}{note}{RESET}")
    print()

def prompt(msg: str) -> str:
    return input(f"\n  {CYAN}▶ {msg}{RESET} ").strip()

def press_enter(msg: str = "Press Enter to continue..."):
    input(f"\n  {MUTED}{msg}{RESET}")

def choose(options: list[str], title: str = "Choose an option", default: int = -1) -> int:
    """Present numbered options, return 0-based index.
    If default >= 0, pressing Enter selects that option."""
    print(f"\n  {title}")
    for i, opt in enumerate(options, 1):
        dflt_tag = f"  {GOLD}← default{RESET}" if i - 1 == default else ""
        print(f"    {CYAN}[{i}]{RESET} {opt}{dflt_tag}")
    while True:
        hint = (f"Enter 1–{len(options)} or Enter for [{default + 1}]:"
                if default >= 0 else f"Enter 1–{len(options)}:")
        raw = prompt(hint)
        if raw == "" and default >= 0:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"  {RED}Invalid choice.{RESET}")


# ── Commissioner game ─────────────────────────────────────────────────────────

class CommissionerGame:

    def __init__(self):
        self.league_name = "Basketball League"
        self.league: League | None = None
        self.season_num = 0
        self._prev_league_pop = 0.0
        self._rule_changes_made: int = 0  # cumulative rule changes (drives cost escalation)
        self._last_pop_signals: dict = {}  # signal breakdown from most recent season
        self._treasury: float = 0.0       # accumulated commissioner funds (carry-over)
        self._last_revenue: float = 0.0   # revenue earned most recent season
        self._retiring_this_season: list = []
        self._new_fas_this_season: list  = []

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _show_wip_status(self):
        clear()
        header("FAKE BASKETBALL", "Commissioner Mode  ·  v0.0  ·  Work in Progress")
        print(f"""
  You are the Commissioner of a fictional basketball league.
  The simulation runs — players age, teams rise and fall, stars
  chase rings or chase markets. Your job is to intervene at the
  right moments: steer franchises to better cities, shape the
  rules to keep the game interesting, decide when the league is
  ready to grow, and pull strings when a star hits free agency.
  You won't control outcomes. You'll influence them.

  {BOLD}This is an early build.{RESET} Some systems are fully realized;
  others are placeholders for what's coming.
""")
        print(f"  {BOLD}{GREEN}✓  IMPLEMENTED & SOLID{RESET}")
        solids = [
            "Season simulation  (schedule, standings, pace, shot style)",
            "Playoffs  (bracket, series, home court, interactive round-by-round)",
            "Player model  (Star / Co-Star / Starter, career arcs, positions, zones)",
            "Player happiness & popularity  (emoji scale, re-sign probability)",
            "Chemistry  (positional fit, zone diversity, continuity bonus)",
            "Awards  (MVP, OPOY, DPOY, Finals MVP — all distinct)",
            "Draft  (annual class, lottery influence, Invest in Talent)",
            "Free agency  (contracts, expirations, star FA event w/ nudge / rig)",
            "Market system  (effective metro, draw factor, fan base)",
            "Meta / era  (rule change tool, escalating costs, fan weariness)",
            "Reports  (league history, team history per franchise, rosters, rivalries…)",
        ]
        for s in solids:
            print(f"    {GREEN}•{RESET}  {s}")

        print(f"\n  {BOLD}{GOLD}~  WORKS BUT NEEDS REFINEMENT{RESET}")
        roughs = [
            "Relocation  (functional, but criteria and consequences need rework)",
            "Expansion  (triggers correctly, destination logic is thin)",
            "Happiness / popularity calibration  (formulas in place, tuning TBD)",
            "Showcase event  (present, stakes feel low)",
        ]
        for r in roughs:
            print(f"    {GOLD}•{RESET}  {r}")

        print(f"\n  {BOLD}{MUTED}○  NOT YET BUILT{RESET}")
        todos = [
            "Team owners  (personalities, goals, pressure on commissioner)",
            "Labor negotiations / CBA  (player union, salary cap, lockout risk)",
            "League sponsorships  (TV deals, naming rights, revenue system)",
            "Revamped relocation  (owner threats, stadium demands, city politics)",
            "Revamped expansion  (bidding, franchise fees, market research)",
        ]
        for t in todos:
            print(f"    {MUTED}•  {t}{RESET}")

        print()
        input("\n  Press Enter to start a new league...")

    def _setup(self):
        self._show_wip_status()
        clear()
        header("COMMISSIONER MODE", "Build and manage your basketball league")
        # League name
        name = prompt("Name your league (Enter for 'Fake Basketball Association'):")
        self.league_name = name if name else "Fake Basketball Association"

        # Seed
        seed_raw = prompt("Random seed (Enter for random):")
        seed = int(seed_raw) if seed_raw.isdigit() else random.randint(1, 9999)
        random.seed(seed)
        print(f"  {MUTED}Seed: {seed}{RESET}")
        press_enter()

        # Team selection
        selected = self._setup_markets()

        # Optional name customization
        self._setup_names(selected)

        # Schedule settings
        games_per_pair = self._setup_schedule(len(selected))

        # Playoff settings
        playoff_teams, series_length = self._setup_playoffs(len(selected))

        # Competitive variance
        variance_cfg = self._setup_variance()

        # Founding talent spread
        quality_mode = self._setup_quality_spread()

        # Build league
        cfg = Config(
            num_seasons=999,
            initial_teams=len(selected),
            games_per_pair=games_per_pair,
            playoff_teams_override=playoff_teams,
            series_length=series_length,
            initial_rating_mode=quality_mode,
            **variance_cfg,
        )
        self.league = League(cfg, selected_franchises=selected)
        self._prev_league_pop = self.league.league_popularity

        press_enter("\nPress Enter to meet your founding franchises...")
        self._show_founding_teams()
        press_enter("Press Enter to tip off Season 1...")

    def _setup_markets(self) -> list[Franchise]:
        """Let player pick founding franchises — primaries and optionally co-tenants."""
        all_primaries  = sorted([f for f in ALL_FRANCHISES if not f.secondary],
                                key=lambda f: -f.effective_metro)
        all_secondaries = {f.city: f for f in ALL_FRANCHISES if f.secondary}

        while True:
            clear()
            header("FOUNDING FRANCHISES", "Select your starting markets")
            print(f"""
  The league begins with franchises you choose. Larger markets
  provide more fan stability; smaller markets are harder to grow
  but create more dramatic underdog stories.

  You may also add a {GOLD}co-tenant{RESET} (second team in a city) from day one —
  a high-variance bet on intracity rivalry generating early buzz,
  at the cost of both teams starting with split market popularity.

  {MUTED}Market = relative metro size · Draw = climate/entertainment/marketability · ★ = co-tenant{RESET}
""")
            print(f"  {'#':>2}  {'Team':<28} {'Market':>6}  {'Draw':>4}")
            divider()
            for i, f in enumerate(all_primaries, 1):
                metro = f.effective_metro
                cotenant_tag = f"  {GOLD}★{RESET}" if f.city in all_secondaries else ""
                print(f"  {i:>2}. {f.name:<28} {metro:>6.1f}  {f.draw_factor:>4.2f}{cotenant_tag}")

            print()
            raw = prompt("Enter team numbers separated by spaces (min 6, max 16), or Enter for default (top 8):")
            if not raw.strip():
                selected = all_primaries[:8]
                print(f"  {MUTED}Using default: top 8 markets.{RESET}")
                break
            parts = raw.split()
            try:
                indices = [int(p) - 1 for p in parts]
                if not all(0 <= idx < len(all_primaries) for idx in indices):
                    raise ValueError
                if len(indices) != len(set(indices)):
                    print(f"  {RED}Duplicate selections.{RESET}")
                    press_enter()
                    continue
                if not (6 <= len(indices) <= 16):
                    print(f"  {RED}Please select between 6 and 16 teams.{RESET}")
                    press_enter()
                    continue
                selected = [all_primaries[i] for i in indices]
                break
            except (ValueError, IndexError):
                print(f"  {RED}Invalid input. Enter numbers from the list above.{RESET}")
                press_enter()

        # Offer co-tenancy for any selected city that has a secondary franchise
        cotenant_eligible = [f for f in selected if f.city in all_secondaries]
        if cotenant_eligible:
            print(f"\n  {GOLD}Co-tenancy available{RESET} in the following markets:\n")
            print(f"  {'Primary':<26} {'+ Co-tenant':<24} {'Mkt pull ea.':>12}")
            divider()
            for i, f in enumerate(cotenant_eligible, 1):
                sec = all_secondaries[f.city]
                pull = f.effective_metro * 0.5
                print(f"  {CYAN}[{i}]{RESET} {f.name:<24} {sec.name:<24} {MUTED}~{pull:.1f}M{RESET}")
            print(f"""
  {MUTED}Trade-off: both teams launch with split popularity. The primary
  keeps 80% of its starting pop; the secondary gets 20%. Market
  pull targets are 70%/50% of baseline. A city championship or
  Finals run steals 25% of that boost from the co-tenant.{RESET}
""")
            raw = prompt("Add co-tenants by number (e.g. 1 3), or Enter to skip:")
            parts = raw.split()
            added = []
            for p in parts:
                if p.isdigit():
                    idx = int(p) - 1
                    if 0 <= idx < len(cotenant_eligible) and len(selected) < 16:
                        primary = cotenant_eligible[idx]
                        sec = all_secondaries[primary.city]
                        if sec not in selected:
                            selected.append(sec)
                            added.append(sec.name)
            if added:
                print(f"  {GREEN}✓ Added: {', '.join(added)}{RESET}")

        print(f"\n  {GREEN}Selected {len(selected)} founding franchises:{RESET}")
        for f in selected:
            tag = f"  {GOLD}(co-tenant){RESET}" if f.secondary else ""
            print(f"  • {f.name}  {MUTED}(market {f.effective_metro:.1f}){RESET}{tag}")
        press_enter()
        return selected

    def _setup_names(self, franchises: list[Franchise]) -> None:
        """Optionally let player rename team nicknames."""
        clear()
        header("TEAM NAMES", "Customize your franchises (optional)")
        print(f"\n  Current teams:\n")
        for f in franchises:
            tag = f"  {GOLD}co-tenant{RESET}" if f.secondary else ""
            print(f"  • {f.name}{tag}")

        raw = prompt("\nCustomize any team nicknames? (Y to proceed, Enter to skip):")
        if raw.strip().lower() != "y":
            return

        print(f"\n  {MUTED}City stays fixed. Press Enter on any team to keep its name.{RESET}\n")
        for f in franchises:
            new_nick = prompt(f"{f.city} [{f.nickname}] →")
            if new_nick.strip():
                f.nickname = new_nick.strip()
                print(f"  {GREEN}✓ {f.name}{RESET}")

    def _setup_variance(self) -> dict:
        """Let player choose competitive balance preset. Returns Config keyword overrides."""
        clear()
        header("COMPETITIVE VARIANCE", "How wide is the gap between best and worst?")

        # Preset definitions: (label, description, ortg/drtg range, sigma)
        PRESETS = [
            (
                "Tight Parity",
                "Any team can compete. Dynasties are rare; upsets are common.",
                103.0, 117.0, 1.5,
            ),
            (
                "Balanced",
                "Elite teams pull away, but underdogs still make noise.",
                100.0, 120.0, 2.0,
            ),
            (
                "Wide Open",
                "Clear pecking order. Dynasties form; rebuilds take years.",
                95.0, 125.0, 3.0,
            ),
        ]

        print(f"""
  The variance range controls how different the best and worst teams
  are. Ratings use pts/100 possessions — the same scale as modern
  analytics. League average is 110 for both offense and defense.

  A wider range means bigger blowouts, clearer dynasties, and
  longer rebuilds for struggling franchises.
""")
        divider()
        for name, desc, lo, hi, sigma in PRESETS:
            spread = hi - lo
            color  = CYAN if spread < 18 else (GOLD if spread < 25 else RED)
            bar    = "█" * round(spread / 2)
            print(f"  {name:<18} {color}ORtg/DRtg {lo:.0f}–{hi:.0f}{RESET}  "
                  f"[{MUTED}{bar:<16}{RESET}]  {MUTED}{desc}{RESET}")
        print()

        options = [f"{name}  {MUTED}(ORtg/DRtg range {lo:.0f}–{hi:.0f}){RESET}"
                   for name, _, lo, hi, sigma in PRESETS]
        choice = choose(options, "Select a variance preset:", default=1)

        name, desc, lo, hi, sigma = PRESETS[choice]

        print(f"\n  {GREEN}Set:{RESET} {name}  ORtg/DRtg range {lo:.0f}–{hi:.0f}")
        press_enter()

        return dict(
            ortg_min=lo, ortg_max=hi,
            drtg_min=lo, drtg_max=hi,
            ortg_sigma=sigma, drtg_sigma=sigma,
        )

    def _setup_quality_spread(self) -> str:
        """Let player choose how founding-team ratings are distributed. Returns mode string."""
        clear()
        header("FOUNDING RATING DISTRIBUTION", "How is talent spread across your starting teams?")
        print(f"""
  This controls whether your founding teams start on equal footing
  or whether some arrive as powerhouses while others are rebuilding
  from day one.
""")
        MODES = [
            ("uniform",       "Equal footing",
             "All teams start at league-average ratings. Pure parity from tip-off."),
            ("moderate",      "Natural spread",
             "Random ratings across the range. Some lucky rosters, some thin ones."),
            ("haves_havenots","Haves & Have-nots",
             "Half the league starts strong, half starts weak — randomly assigned."),
        ]
        for key, name, desc in MODES:
            print(f"  {BOLD}{name}{RESET}  {MUTED}{desc}{RESET}")
        print()
        options = [f"{name}  {MUTED}— {desc}{RESET}" for _, name, desc in MODES]
        choice = choose(options, "Select talent distribution:", default=1)
        key, name, _ = MODES[choice]
        print(f"\n  {GREEN}Set:{RESET} {name}")
        press_enter()
        return key

    def _setup_schedule(self, n_teams: int) -> int:
        """Let player choose how many times each pair of teams plays."""
        clear()
        header("SCHEDULE FORMAT", "How many times does each matchup occur?")
        auto = _games_per_pair(n_teams)
        options = []
        for gpp in [2, 4, 6, 8, 10]:
            total = gpp * (n_teams - 1)
            label = f"{gpp}× per matchup  {MUTED}({total}-game season){RESET}"
            if gpp == auto:
                label += f"  {GOLD}← recommended for {n_teams} teams{RESET}"
            options.append((gpp, label))
        print(f"""
  More games = more meaningful standings, less variance.
  Fewer games = more upsets and surprise playoff runs.
""")
        default_idx = next(i for i, (gpp, _) in enumerate(options) if gpp == auto)
        choice = choose([label for _, label in options], "Select schedule format:", default=default_idx)
        gpp = options[choice][0]
        print(f"\n  {GREEN}Set:{RESET} {gpp}× per matchup · {gpp * (n_teams - 1)}-game regular season.")
        press_enter()
        return gpp

    def _setup_playoffs(self, n_teams: int):
        """Let player choose playoff bracket size and series length."""
        clear()
        header("PLAYOFF FORMAT", "Design your postseason")

        # Bracket size — must be power of 2 and <= n_teams
        bracket_options = [n for n in [4, 8, 16] if n <= n_teams]
        auto_bracket = _playoff_count(n_teams)
        print(f"\n  {BOLD}How many teams qualify for the playoffs?{RESET}\n")
        labels = []
        for n in bracket_options:
            pct = n / n_teams * 100
            rounds = {4: "2 rounds", 8: "3 rounds", 16: "4 rounds"}.get(n, f"? rounds")
            labels.append(f"{n} teams  {MUTED}(top {pct:.0f}% of league · {rounds}){RESET}")
        bracket_default = next(
            (i for i, n in enumerate(bracket_options) if n == auto_bracket),
            len(bracket_options) - 1,
        )
        pt_choice = choose(labels, default=bracket_default)
        playoff_teams = bracket_options[pt_choice]

        # Series length — default Best-of-7
        print(f"\n  {BOLD}How long is each playoff series?{RESET}\n")
        series_opts = [
            (5, f"Best-of-5  {MUTED}(first to 3 wins){RESET}"),
            (7, f"Best-of-7  {MUTED}(first to 4 wins · NBA standard){RESET}"),
        ]
        s_choice = choose([label for _, label in series_opts], default=1)
        series_length = series_opts[s_choice][0]

        print(f"\n  {GREEN}Set:{RESET} {playoff_teams}-team bracket · best-of-{series_length} series.")
        press_enter()
        return playoff_teams, series_length

    def _show_founding_teams(self):
        league = self.league
        cfg    = league.cfg
        teams  = sorted(league.teams, key=lambda t: -(t.ortg - t.drtg))
        max_fb = max(_fan_base(t) for t in teams)

        tier_colors = {TIER_ELITE: GOLD, TIER_HIGH: CYAN, TIER_MID: "", TIER_LOW: MUTED}
        PAGE  = 4
        total = len(teams)
        page  = 0
        avg_o, avg_d = _avg_ratings(league.teams)

        while True:
            clear()
            header(self.league_name, f"Founding Franchises  ·  {total} teams")
            chunk = teams[page: page + PAGE]

            for t in chunk:
                fb     = _fan_base(t)
                net    = _rel_net(t.ortg, t.drtg, avg_o, avg_d)
                net_c  = GREEN if net > 0 else (RED if net < 0 else MUTED)
                chem   = t.compute_chemistry(cfg)
                chem_c = GREEN if chem >= 1.05 else (RED if chem < 0.90 else CYAN)
                fb_str = _fan_base_bar(fb, max_fb, 12)

                print(f"\n  {BOLD}{t.name}{RESET}")
                print(f"  {MUTED}ORtg {t.ortg:.1f}  DRtg {t.drtg:.1f}  "
                      f"Net {net_c}{net:+.1f}{RESET}  "
                      f"Pace {t.pace:.0f}  3pt {t.style_3pt:.0%}  "
                      f"Fan Base {fb_str}  "
                      f"Chem {chem_c}{chem:.2f}{RESET}")
                print(f"  {MUTED}{'─' * 80}{RESET}")
                print(f"  {'Slot':<9} {'Name':<22} {'Pos':<5} {'Age':>3}  "
                      f"{'ORtg':>5}  {'DRtg':>5}  {'Zone':<6}  {'Ceiling':<7}  {'Mood':<4}  Motivation")

                for idx, player in enumerate(t.roster):
                    slot_lbl = t.slot_label(idx)
                    if player is None:
                        print(f"  {MUTED}{slot_lbl:<9} — empty{RESET}")
                    else:
                        tc    = tier_colors.get(player.ceiling_tier, "")
                        mot_c = (GREEN if player.motivation == MOT_WINNING
                                 else GOLD if player.motivation == MOT_MARKET else CYAN)
                        print(f"  {MUTED}{slot_lbl:<9}{RESET}"
                              f"{tc}{player.name:<22}{RESET}"
                              f" {player.position:<5} {player.age:>3}"
                              f"  {player.ortg_contrib:>+5.1f}  {player.drtg_contrib:>+5.1f}"
                              f"  {player.preferred_zone:<6}"
                              f"  {tc}{player.ceiling_tier:<7}{RESET}"
                              f"  {happiness_emoji(player.happiness):<4}"
                              f"  {mot_c}{player.motivation}{RESET}")

            print()
            divider()
            has_next = page + PAGE < total
            nav = []
            if page > 0:  nav.append("p=prev")
            if has_next:  nav.append("Enter=next")
            else:         nav.append("Enter=done")
            raw = prompt(f"  [{', '.join(nav)}]: ").strip().lower()
            if raw == "p" and page > 0:
                page -= PAGE
            elif has_next and raw in ("", "n"):
                page += PAGE
            else:
                break

    # ── Core season loop ──────────────────────────────────────────────────────

    def run(self):
        self._setup()
        while True:
            self.season_num += 1
            season = self._run_one_season()
            self._show_summary(season)
            self._post_season(season)
            while True:
                idx = choose(
                    ["Next season", "View reports", "Quit"],
                    title="What next?", default=0,
                )
                if idx == 1:
                    self._show_reports(season)
                else:
                    break
            if idx == 2:
                self._show_farewell()
                break

    def _run_one_season(self) -> Season:
        """Run one season through all engine steps, with interactive relocations."""
        league = self.league
        sn = self.season_num
        season = Season(sn, list(league.teams), league.cfg, league.league_meta)
        season.play_regular_season()
        self._play_playoffs_interactive(season)
        league.seasons.append(season)
        # Phase 1: advance players, surface retirements/FA for interactive handling
        self._retiring_this_season, self._new_fas_this_season = (
            league.offseason_phase1(season)
        )
        self._handle_relocations(season)
        league._decay_grudges()
        league._evolve_popularity(season)
        league._evolve_market_engagements(season)
        self._last_pop_signals = league._evolve_league_popularity(season)
        league._evolve_meta()
        season._popularity        = {t: t.popularity for t in league.teams}
        season._market_engagement = {t: t.market_engagement for t in league.teams}
        season._league_popularity = league.league_popularity
        return season

    # ── Interactive playoffs ───────────────────────────────────────────────────

    def _play_playoffs_interactive(self, season: Season) -> None:
        """Regular season recap → round-by-round playoffs with series interventions."""
        self._show_regular_season_recap(season)

        cfg = season.cfg
        bracket = season.regular_season_standings[:season.playoff_teams]
        # Total rounds = log2(playoff_teams)
        import math as _math
        total_rounds = int(_math.log2(season.playoff_teams))
        labels = _round_labels(total_rounds)

        interventions_this_season = 0
        round_idx = 0

        while len(bracket) > 1:
            matchups = [
                (bracket[i], bracket[len(bracket) - 1 - i])
                for i in range(len(bracket) // 2)
            ]
            rname = labels[round_idx] if round_idx < len(labels) else f"Round {round_idx+1}"

            # Offer interventions for this round
            bonuses, interventions_this_season = self._offer_round_interventions(
                matchups, season, rname, interventions_this_season
            )

            # Play every series in the round
            round_series: list[PlayoffSeries] = []
            next_bracket: list[Team] = []
            for s1, s2 in matchups:
                favored, bonus_val = bonuses.get((s1, s2), (None, 0.0))
                winner, games = self._play_series_with_bonus(s1, s2, season, favored, bonus_val)
                for g in games:
                    season._record(g)
                round_series.append(PlayoffSeries(s1, s2, winner, games))
                next_bracket.append(winner)

            season.playoff_rounds.append(round_series)
            self._show_round_results(round_series, season, rname)
            bracket = next_bracket
            round_idx += 1

        season.champion = bracket[0]
        season.champion.championships += 1

    def _show_regular_season_recap(self, season: Season) -> None:
        """Show final regular season standings before the playoff bracket locks."""
        clear()
        league = self.league
        sn = season.number
        standings = season.regular_season_standings
        n_playoff = season.playoff_teams
        n_teams = len(standings)

        header(self.league_name, f"Season {sn}  —  Regular Season Final")

        # Notable callouts
        leader = standings[0]
        last   = standings[-1]
        lw = season.reg_wins(leader);  ll = season.reg_losses(leader)
        bw = season.reg_wins(last);    bl = season.reg_losses(last)
        print(f"\n  {GREEN}Best record :{RESET}  {leader.franchise_at(sn).name}  {_wl(lw, ll)}")
        print(f"  {RED}Worst record:{RESET}  {last.franchise_at(sn).name}  {_wl(bw, bl)}")

        # Scoring / defensive leaders
        ppg_leader  = max(standings, key=lambda t: season.team_ppg(t))
        def_leader  = min(standings, key=lambda t: season.team_papg(t))
        diff_leader = max(standings, key=lambda t: season.team_ppg(t) - season.team_papg(t))
        print(f"  {GREEN}Top offense :{RESET}  {ppg_leader.franchise_at(sn).name:<28}  "
              f"{season.team_ppg(ppg_leader):.1f} PS/G")
        print(f"  {RED}Top defense :{RESET}  {def_leader.franchise_at(sn).name:<28}  "
              f"{season.team_papg(def_leader):.1f} PA/G")
        best_diff = season.team_ppg(diff_leader) - season.team_papg(diff_leader)
        print(f"  {CYAN}Best margin :{RESET}  {diff_leader.franchise_at(sn).name:<28}  "
              f"{best_diff:+.1f} per game")

        # Regular season awards
        if season.mvp or season.dpoy:
            print()
            if season.mvp:
                mvp_team = season.mvp_team.franchise_at(sn).nickname if season.mvp_team else "—"
                tc = GOLD if season.mvp.peak_overall >= 14 else CYAN
                print(f"  {GOLD}MVP  :{RESET}  {happiness_emoji(season.mvp.happiness)} {tc}{season.mvp.name:<22}{RESET}  "
                      f"{MUTED}{season.mvp.position} · {mvp_team}{RESET}  "
                      f"ORtg {season.mvp.ortg_contrib:>+5.1f}  DRtg {season.mvp.drtg_contrib:>+5.1f}  "
                      f"{season.mvp.trend}")
            if season.opoy:
                opoy_team = season.opoy_team.franchise_at(sn).nickname if season.opoy_team else "—"
                tc = GOLD if season.opoy.peak_overall >= 14 else CYAN
                print(f"  {GOLD}OPOY :{RESET}  {happiness_emoji(season.opoy.happiness)} {tc}{season.opoy.name:<22}{RESET}  "
                      f"{MUTED}{season.opoy.position} · {opoy_team}{RESET}  "
                      f"ORtg {season.opoy.ortg_contrib:>+5.1f}  DRtg {season.opoy.drtg_contrib:>+5.1f}  "
                      f"{season.opoy.trend}")
            if season.dpoy:
                dpoy_team = season.dpoy_team.franchise_at(sn).nickname if season.dpoy_team else "—"
                tc = GOLD if season.dpoy.peak_overall >= 14 else CYAN
                print(f"  {CYAN}DPOY :{RESET}  {happiness_emoji(season.dpoy.happiness)} {tc}{season.dpoy.name:<22}{RESET}  "
                      f"{MUTED}{season.dpoy.position} · {dpoy_team}{RESET}  "
                      f"ORtg {season.dpoy.ortg_contrib:>+5.1f}  DRtg {season.dpoy.drtg_contrib:>+5.1f}  "
                      f"{season.dpoy.trend}")

        cfg = season.cfg
        print(f"\n  {BOLD}{'#':>2}  {'Team':<28} {'Record':<13} {'ORtg':>4}  {'DRtg':>4}  {'Pace':>4}  "
              f"{'PS/G':>5}  {'PA/G':>5}  {'Diff':>5}{RESET}")
        divider()
        for i, team in enumerate(standings):
            rank = i + 1
            rw, rl = season.reg_wins(team), season.reg_losses(team)
            fname = team.franchise_at(sn).name
            ortg, drtg, pace, _ = season._start_ratings.get(team, (team.ortg, team.drtg, team.pace, team.style_3pt))
            record   = _wl(rw, rl)
            padded   = f"{fname:<28}"
            if rank <= n_playoff:
                seed_tag = f"{CYAN}({rank}){RESET}"
                name_str = f"{BOLD}{padded}{RESET}"
            else:
                seed_tag = f"{MUTED}    {RESET}"
                name_str = f"{MUTED}{padded}{RESET}"
            ppg  = season.team_ppg(team)
            papg = season.team_papg(team)
            diff = ppg - papg
            diff_c = GREEN if diff > 0 else (RED if diff < 0 else MUTED)
            print(f"  {rank:>2}. {name_str} {record:<13} {ortg:>4.0f}  {drtg:>4.0f}  {pace:>4.0f}  "
                  f"{seed_tag} {ppg:>5.1f}  {papg:>5.1f}  {diff_c}{diff:>+5.1f}{RESET}")

        divider()
        print(f"\n  Top {n_playoff} of {n_teams} teams advance to the playoffs.")
        press_enter("Press Enter to begin the playoffs...")

    def _offer_round_interventions(
        self,
        matchups: list[tuple[Team, Team]],
        season: Season,
        rname: str,
        n_done: int,
    ) -> tuple[dict, int]:
        """Show round matchups and let the commissioner intervene in any series.

        Returns (bonuses dict, updated intervention count).
        bonuses maps (s1, s2) → (favored_team, quality_bonus).
        """
        # Nudge / rig parameters
        NUDGE_BONUS  = 0.06
        RIG_BONUS    = 0.18
        NUDGE_BASE   = 0.03   # legitimacy cost
        RIG_BASE     = 0.10

        bonuses: dict = {}
        league = self.league
        cfg = season.cfg
        sn = season.number
        avg_o, avg_d = _season_avg_ratings(season)

        while True:
            clear()
            header(f"PLAYOFFS  —  {rname}", f"Season {sn}")
            legit = league.legitimacy
            legit_color = GREEN if legit >= 0.8 else (GOLD if legit >= 0.5 else RED)
            print(f"\n  Legitimacy: {legit_color}{legit:.0%}{RESET}"
                  + (f"  {MUTED}({n_done} intervention{'s' if n_done!=1 else ''} this season){RESET}"
                     if n_done > 0 else ""))

            # Show matchups
            print()
            for i, (s1, s2) in enumerate(matchups, 1):
                o1, d1, _, _ = season._start_ratings.get(s1, (s1.ortg, s1.drtg, s1.pace, s1.style_3pt))
                o2, d2, _, _ = season._start_ratings.get(s2, (s2.ortg, s2.drtg, s2.pace, s2.style_3pt))
                net1 = _rel_net(o1, d1, avg_o, avg_d)
                net2 = _rel_net(o2, d2, avg_o, avg_d)
                s1n = s1.franchise_at(sn).name[:24]
                s2n = s2.franchise_at(sn).name[:24]
                net1_c = GREEN if net1 > net2 else (RED if net1 < net2 else MUTED)
                net2_c = GREEN if net2 > net1 else (RED if net2 < net1 else MUTED)
                seed1_idx = season.regular_season_standings.index(s1) + 1
                seed2_idx = season.regular_season_standings.index(s2) + 1
                if (s1, s2) in bonuses:
                    fav, bv = bonuses[(s1, s2)]
                    btype  = "RIG" if bv >= RIG_BONUS else "nudge"
                    b_col  = RED if btype == "RIG" else GOLD
                    status = f"  {b_col}★ {btype} → {fav.franchise_at(sn).name[:14]}{RESET}"
                else:
                    status = ""
                # Star players
                def _star_tag(t: Team) -> str:
                    star = t.roster[0] if t.roster else None
                    if star is None:
                        return MUTED + "—" + RESET
                    tc = GOLD if star.ceiling_tier == TIER_ELITE else (CYAN if star.ceiling_tier == TIER_HIGH else MUTED)
                    return f"{happiness_emoji(star.happiness)} {tc}{star.name} ({star.ceiling_tier[0]}){RESET}"
                champ_tag1 = f"  {GOLD}🏆×{s1.championships}{RESET}" if s1.championships else ""
                champ_tag2 = f"  {GOLD}🏆×{s2.championships}{RESET}" if s2.championships else ""
                divider()
                print(f"  {CYAN}{i}.{RESET} "
                      f"({seed1_idx}) {BOLD}{s1n:<24}{RESET}  vs  "
                      f"({seed2_idx}) {BOLD}{s2n:<24}{RESET}"
                      f"  Net {net1_c}{net1:>+.0f}{RESET} v {net2_c}{net2:<+.0f}{RESET}"
                      f"{status}")
                print(f"      ★ {_star_tag(s1)}{champ_tag1:<20}      "
                      f"★ {_star_tag(s2)}{champ_tag2}")
            divider()

            print()
            raw = prompt("Intervene in a series? Enter series # (or Enter to play):")
            if raw == "":
                break
            if not raw.isdigit() or not (1 <= int(raw) <= len(matchups)):
                continue

            idx = int(raw) - 1
            s1, s2 = matchups[idx]

            # Pick favored team — full scouting card
            import math as _math
            clear()
            header(f"SERIES SCOUT  —  {rname}", f"Season {sn}")
            o1, d1, p1, _  = season._start_ratings.get(s1, (s1.ortg, s1.drtg, s1.pace, s1.style_3pt))
            o2, d2, p2, _  = season._start_ratings.get(s2, (s2.ortg, s2.drtg, s2.pace, s2.style_3pt))
            net1 = _rel_net(o1, d1, avg_o, avg_d)
            net2 = _rel_net(o2, d2, avg_o, avg_d)
            fb1 = _fan_base(s1);  fb2 = _fan_base(s2)

            # Seed indices
            seed1_idx = season.regular_season_standings.index(s1) + 1
            seed2_idx = season.regular_season_standings.index(s2) + 1
            rw1, rl1  = season.reg_wins(s1), season.reg_losses(s1)
            rw2, rl2  = season.reg_wins(s2), season.reg_losses(s2)

            # H2H regular season record
            h2h_s1 = sum(
                1 for g in season.regular_season_games
                if g.winner is s1 and (g.home is s2 or g.away is s2)
            )
            h2h_s2 = sum(
                1 for g in season.regular_season_games
                if g.winner is s2 and (g.home is s1 or g.away is s1)
            )

            # Series win probability (logistic on net rating diff)
            diff = net1 - net2 + cfg.playoff_seed_pscore_bonus * 50  # seed advantage tweak
            prob1 = round(100 / (1 + _math.exp(-diff / 4)))
            prob2 = 100 - prob1

            # Narrative tags
            def _tags(t: Team) -> str:
                tags = []
                prev_champs = [s.champion for s in league.seasons if s.champion is not None]
                if prev_champs and prev_champs[-1] is t:
                    tags.append(f"{GOLD}Defending champion{RESET}")
                if t.championships == 0:
                    tags.append(f"{CYAN}No titles yet{RESET}")
                elif t.championships >= 3:
                    tags.append(f"{GOLD}Dynasty ({t.championships}×){RESET}")
                return "  ·  ".join(tags) if tags else ""

            tier_colors = {TIER_ELITE: GOLD, TIER_HIGH: CYAN, TIER_MID: "", TIER_LOW: MUTED}

            def _team_card(label: str, t: Team, seed_idx: int, rw: int, rl: int,
                           net: float, fb: float, prob: int) -> None:
                tname = t.franchise_at(sn).name
                champ_str = f"  {GOLD}🏆 ×{t.championships}{RESET}" if t.championships else ""
                net_c = GREEN if net > 0 else (RED if net < 0 else MUTED)
                tags  = _tags(t)
                print(f"\n  {CYAN}{label}{RESET}  {BOLD}{tname}{RESET}{champ_str}")
                print(f"       Seed {seed_idx}  ·  Record {rw}–{rl}"
                      f"  ·  Net {net_c}{net:>+.1f}{RESET}"
                      f"  ·  ORtg {o1 if t is s1 else o2:.0f}"
                      f"  DRtg {d1 if t is s1 else d2:.0f}"
                      f"  Pace {p1 if t is s1 else p2:.0f}")
                print(f"       Fan Base {fb:.1f}M"
                      f"  ·  Market {t.franchise.effective_metro:.1f}M")
                if tags:
                    print(f"       {tags}")
                # Roster (Star + Co-Star)
                for slot_idx in range(2):
                    player = t.roster[slot_idx] if slot_idx < len(t.roster) else None
                    lbl    = t.slot_label(slot_idx)
                    if player:
                        tc    = tier_colors.get(player.ceiling_tier, "")
                        mot_c = (GREEN if player.motivation == MOT_WINNING
                                 else GOLD if player.motivation == MOT_MARKET else CYAN)
                        print(f"       {MUTED}{lbl:<9}{RESET}"
                              f"{happiness_emoji(player.happiness)} {tc}{player.name:<22}{RESET}"
                              f"  {player.position:<5} {player.age:>2}"
                              f"  ORtg {player.ortg_contrib:>+5.1f}"
                              f"  DRtg {player.drtg_contrib:>+5.1f}"
                              f"  {tc}{player.ceiling_tier}{RESET}"
                              f"  {mot_c}{player.motivation}{RESET}"
                              f"  {player.trend}")
                    else:
                        print(f"       {MUTED}{lbl:<9} — empty{RESET}")
                print(f"       Series win probability: {GREEN if prob >= 55 else (RED if prob <= 45 else MUTED)}{prob}%{RESET}")

            _team_card("[1]", s1, seed1_idx, rw1, rl1, net1, fb1, prob1)
            _team_card("[2]", s2, seed2_idx, rw2, rl2, net2, fb2, prob2)

            # H2H
            print(f"\n  {MUTED}Head-to-head this season:  "
                  f"{s1.franchise_at(sn).nickname} {h2h_s1}–{h2h_s2} "
                  f"{s2.franchise_at(sn).nickname}{RESET}")
            print()

            # Compounding cost display
            mult   = 1.0 + 0.5 * n_done
            n_cost = NUDGE_BASE * mult
            r_cost = RIG_BASE   * mult
            legit_after_n = max(0.0, legit - n_cost)
            legit_after_r = max(0.0, legit - r_cost)
            print(f"  {MUTED}Intervention #{n_done+1} this season  —  cost multiplier {mult:.1f}×{RESET}")
            print(f"  {GOLD}Nudge{RESET}  small edge (+{NUDGE_BONUS:.0%} p_score/poss)  "
                  f"{RED}−{n_cost:.0%} legitimacy{RESET}  → {legit_after_n:.0%}")
            print(f"  {RED}Rig  {RESET}  strong edge (+{RIG_BONUS:.0%} p_score/poss)  "
                  f"{RED}−{r_cost:.0%} legitimacy{RESET}  → {legit_after_r:.0%}")
            if legit < 0.4:
                print(f"\n  {RED}⚠  Legitimacy is dangerously low — further interventions risk a scandal.{RESET}")
            print()

            fav_choice = choose(
                [f"Favor {s1.franchise_at(sn).name}",
                 f"Favor {s2.franchise_at(sn).name}",
                 f"{MUTED}Cancel{RESET}"],
                "Which team?", default=2,
            )
            if fav_choice == 2:
                continue

            favored = s1 if fav_choice == 0 else s2
            type_choice = choose(
                [f"{GOLD}Nudge{RESET}  +{NUDGE_BONUS:.0%} p_score  {RED}−{n_cost:.0%} legit{RESET}",
                 f"{RED}Rig  {RESET}  +{RIG_BONUS:.0%} p_score  {RED}−{r_cost:.0%} legit{RESET}",
                 f"{MUTED}Cancel{RESET}"],
                "Intervention level?", default=0,
            )
            if type_choice == 2:
                continue

            bonus_val  = NUDGE_BONUS if type_choice == 0 else RIG_BONUS
            legit_cost = n_cost       if type_choice == 0 else r_cost
            league.legitimacy = max(0.0, legit - legit_cost)
            bonuses[(s1, s2)] = (favored, bonus_val)
            n_done += 1

        return bonuses, n_done

    def _play_series_with_bonus(
        self,
        seed1: Team, seed2: Team,
        season: Season,
        favored,
        bonus_val: float,
    ) -> tuple[Team, list[GameResult]]:
        """Play a full series, applying a p_score bonus to favored team every game."""
        cfg = season.cfg
        league = self.league
        wins_needed = cfg.series_length // 2 + 1
        pattern = _HOME_PATTERNS.get(
            cfg.series_length,
            [i % 2 == 0 for i in range(cfg.series_length)],
        )
        wins: dict[Team, int] = {seed1: 0, seed2: 0}
        games: list[GameResult] = []

        for game_num in range(cfg.series_length):
            if wins[seed1] >= wins_needed or wins[seed2] >= wins_needed:
                break

            seed1_is_home = pattern[game_num]
            home, away = (seed1, seed2) if seed1_is_home else (seed2, seed1)
            ha = cfg.playoff_home_pscore_bonus
            home_bonus = ha + cfg.playoff_seed_pscore_bonus * (1 if home is seed1 else 0)
            away_bonus = cfg.playoff_seed_pscore_bonus * (1 if away is seed1 else 0)
            if favored is not None:
                if home is favored:
                    home_bonus += bonus_val
                else:
                    away_bonus += bonus_val

            ph = _p_score(home, away, cfg, bonus=home_bonus, league_meta=league.league_meta)
            pa = _p_score(away, home, cfg, bonus=away_bonus, league_meta=league.league_meta)
            poss = _game_pace(home, away, cfg, league.league_meta)

            home_score = sum(_sim_possession(ph, home.style_3pt) for _ in range(poss))
            away_score = sum(_sim_possession(pa, away.style_3pt) for _ in range(poss))
            while home_score == away_score:
                home_score += _sim_possession(ph, home.style_3pt)
                away_score += _sim_possession(pa, away.style_3pt)

            result = GameResult(home, away, home_score, away_score)
            games.append(result)
            wins[result.winner] += 1

        winner = seed1 if wins[seed1] >= wins_needed else seed2
        return winner, games

    def _show_round_results(
        self,
        round_series: list[PlayoffSeries],
        season: Season,
        rname: str,
    ) -> None:
        """Display results for one completed playoff round."""
        clear()
        sn = season.number
        n_playoff = season.playoff_teams
        wins_needed = season.cfg.series_length // 2 + 1

        header(f"PLAYOFFS  —  {rname}  RESULTS", f"Season {sn}")
        print()

        for sr in round_series:
            winner = sr.winner
            loser  = sr.seed2 if sr.winner is sr.seed1 else sr.seed1
            w_wins = sr.seed1_wins if sr.winner is sr.seed1 else sr.seed2_wins
            l_wins = sr.seed2_wins if sr.winner is sr.seed1 else sr.seed1_wins
            n_games = len(sr.games)
            wname  = winner.franchise_at(sn).name
            lname  = loser.franchise_at(sn).name

            # Sweep / full series tag
            min_games = season.cfg.series_length // 2 + 1
            if n_games == min_games:
                drama_tag = f"  {MUTED}sweep{RESET}"
            elif n_games == season.cfg.series_length:
                drama_tag = f"  {GOLD}went to {season.cfg.series_length}!{RESET}"
            else:
                drama_tag = f"  {MUTED}in {n_games}{RESET}"

            # Upset flag: loser was higher seed
            upset = loser is sr.seed1
            upset_tag = f"  {RED}UPSET{RESET}" if upset else ""

            print(f"  {BOLD}{wname:<28}{RESET} def. {lname:<28} "
                  f"{GOLD}{w_wins}–{l_wins}{RESET}{drama_tag}{upset_tag}")

        # If this is the Finals, crown the champion
        if len(round_series) == 1 and round_series[0].winner is not None:
            champ = round_series[0].winner
            repeat = (len(self.league.seasons) >= 1
                      and self.league.seasons
                      and champ is getattr(self.league.seasons[-1], 'champion', None))
            print(f"\n  {GOLD}{BOLD}🏆  {champ.franchise_at(sn).name} are champions!{RESET}", end="")
            if repeat:
                print(f"  {GOLD}★ REPEAT{RESET}", end="")
            print()

        press_enter()

    # ── Season summary ────────────────────────────────────────────────────────

    def _show_summary(self, season: Season):
        clear()
        league = self.league
        sn = season.number
        n_teams = len(season.teams)
        lp = league.league_popularity
        lp_prev = self._prev_league_pop

        header(
            self.league_name,
            f"Season {sn}  ·  {n_teams} teams  ·  League Popularity: {lp:.0%} {trend(lp_prev, lp)}"
        )

        # Champion
        champ = season.champion
        champ_seed = season.regular_season_standings.index(champ) + 1
        finals = season.playoff_rounds[-1][0]
        runner_up = finals.seed2 if finals.winner is finals.seed1 else finals.seed1
        ru_w = sum(1 for g in finals.games if g.winner is champ)
        ru_l = len(finals.games) - ru_w
        repeat = len(league.seasons) >= 2 and champ is league.seasons[-2].champion

        print(f"\n  {GOLD}{BOLD}🏆  CHAMPION: {champ.franchise_at(sn).name}{RESET}", end="")
        if repeat: print(f"  {GOLD}★ REPEAT{RESET}", end="")
        print()
        print(f"     {MUTED}Seed {champ_seed} · defeated {runner_up.franchise_at(sn).name} {ru_w}–{ru_l} in the Finals{RESET}")

        # Awards
        if season.mvp or season.opoy or season.dpoy or season.finals_mvp:
            print(f"\n  {BOLD}Season Awards{RESET}")
            divider()
            for lbl, p, t in [
                ("MVP",        season.mvp,        season.mvp_team),
                ("OPOY",       season.opoy,       season.opoy_team),
                ("DPOY",       season.dpoy,       season.dpoy_team),
                ("Finals MVP", season.finals_mvp, season.champion),
            ]:
                if p is None:
                    continue
                tname = t.franchise_at(sn).nickname if t else "—"
                tc = GOLD if p.peak_overall >= 14 else CYAN
                print(f"  {GOLD}{lbl:<12}{RESET} {happiness_emoji(p.happiness)} {tc}{p.name:<22}{RESET}"
                      f"  {MUTED}{p.position} · {tname:<18}{RESET}"
                      f"  ORtg {p.ortg_contrib:>+5.1f}  DRtg {p.drtg_contrib:>+5.1f}"
                      f"  {p.trend}")

        # Standings
        print(f"\n  {'TEAM':<30} {'RECORD':<14} {'ORtg':>4}  {'DRtg':>4}  {'Pace':>4}  PLAYOFF")
        divider()
        standings = season.regular_season_standings
        n_playoff = season.playoff_teams
        playoff_result = self._playoff_results(season)
        cfg = season.cfg

        for i, team in enumerate(standings):
            rank = i + 1
            rw, rl = season.reg_wins(team), season.reg_losses(team)
            fname = team.franchise_at(sn).name
            result = playoff_result.get(team, "")
            ortg, drtg, pace, _ = season._start_ratings.get(team, (team.ortg, team.drtg, team.pace, team.style_3pt))
            record   = _wl(rw, rl)

            # Pad the raw name first, then wrap with color — avoids ANSI width issues
            padded = f"{fname:<28}"
            if team is champ:
                name_str   = f"{GOLD}{BOLD}{padded}{RESET}"
                result_str = f"{GOLD}★ Champion{RESET}"
            elif result == "Finals":
                name_str   = padded
                result_str = f"{GOLD}Finals{RESET}"
            elif result.startswith("Lost"):
                name_str   = padded
                result_str = f"{MUTED}{result}{RESET}"
            elif rank <= n_playoff:
                name_str   = padded
                result_str = f"{MUTED}Playoffs{RESET}"
            else:
                name_str   = f"{MUTED}{padded}{RESET}"
                result_str = f"{MUTED}—{RESET}"

            seed_str = f"{CYAN}({rank}){RESET}" if rank <= n_playoff else "    "
            print(f"  {rank:>2}. {name_str}  {record:<14} {ortg:>4.0f}  {drtg:>4.0f}  {pace:>4.0f}  {seed_str} {result_str}")

        # Points scored / allowed
        print()
        print(f"  {'TEAM':<30} {'PS/G':>5}  {'PA/G':>5}  Diff")
        divider()
        for i, team in enumerate(standings):
            fname = team.franchise_at(sn).name
            padded = f"{fname:<28}"
            ppg  = season.team_ppg(team)
            papg = season.team_papg(team)
            diff = ppg - papg
            diff_c = GREEN if diff > 0 else (RED if diff < 0 else MUTED)
            print(f"  {i+1:>2}. {padded}  {ppg:>5.1f}  {papg:>5.1f}  {diff_c}{diff:+.1f}{RESET}")

        # Playoff bracket recap
        if season.playoff_rounds:
            n_rounds = len(season.playoff_rounds)
            labels = _round_labels(n_rounds)
            print(f"\n  {BOLD}Playoff Recap{RESET}")
            divider()
            for rnd_idx, rnd in enumerate(season.playoff_rounds):
                rname = labels[rnd_idx]
                print(f"  {MUTED}{rname}{RESET}")
                for sr in rnd:
                    winner = sr.winner
                    loser  = sr.seed2 if sr.winner is sr.seed1 else sr.seed1
                    w_wins = sr.seed1_wins if sr.winner is sr.seed1 else sr.seed2_wins
                    l_wins = sr.seed2_wins if sr.winner is sr.seed1 else sr.seed1_wins
                    wname  = winner.franchise_at(sn).name
                    lname  = loser.franchise_at(sn).name
                    clinch = sr.games[-1]
                    w_score = clinch.home_score if clinch.home is winner else clinch.away_score
                    l_score = clinch.away_score if clinch.home is winner else clinch.home_score
                    print(f"    {wname:<26} def. {lname:<26} {w_wins}–{l_wins}  "
                          f"{MUTED}clinch {w_score}–{l_score}{RESET}")

        # League health
        print()
        divider()
        avg_ppg = season.league_avg_ppg()
        total_fb  = sum(_fan_base(t) for t in league.teams)
        print(f"\n  {BOLD}League Health{RESET}")
        print(f"  Popularity  {pop_bar(lp)}  {trend(lp_prev, lp)}")
        print(f"  Fan Base    {CYAN}{total_fb:.1f}M{RESET}  {MUTED}total engaged fans (engagement × market){RESET}")
        if self._last_pop_signals:
            annotations = self._pop_signal_annotations(season)
            for sig_name, sig_delta in self._last_pop_signals.items():
                if abs(sig_delta) >= 0.0005:
                    color = GREEN if sig_delta > 0 else RED
                    sign = "+" if sig_delta >= 0 else ""
                    note = annotations.get(sig_name, "")
                    note_str = f"  {MUTED}{note}{RESET}" if note else ""
                    print(f"    {MUTED}{sig_name:<20}{RESET} {color}{sign}{sig_delta:.1%}{RESET}{note_str}")
        print(f"  Era         {era_desc(league.league_meta)}")
        print(f"  Avg scoring {avg_ppg:.1f} pts/game")
        if season.meta_shock:
            print(f"  {RED}{BOLD}⚡ Rule change shock fired this season!{RESET}")

        # Notable events
        events = self._collect_events(season)
        if events:
            print(f"\n  {BOLD}Events{RESET}")
            for e in events:
                print(f"  • {e}")

        self._prev_league_pop = lp
        press_enter()

    def _playoff_results(self, season: Season) -> dict:
        num_rounds = len(season.playoff_rounds)
        result = {}
        for round_idx, rnd in enumerate(season.playoff_rounds):
            rounds_from_finals = num_rounds - 1 - round_idx
            for series in rnd:
                loser = series.seed2 if series.winner is series.seed1 else series.seed1
                if rounds_from_finals == 0:
                    result[loser] = "Finals"
                elif rounds_from_finals == 1:
                    result[loser] = "Lost Semifinals"
                elif rounds_from_finals == 2:
                    result[loser] = "Lost Quarterfinals"
                else:
                    result[loser] = f"Lost Round {round_idx + 1}"
        if season.champion:
            result[season.champion] = "Champion"
        return result

    def _collect_events(self, season: Season) -> list[str]:
        events = []
        sn = season.number
        for log_sn, old, new, ls, b2, pop in self.league.relocation_log:
            if log_sn == sn:
                events.append(f"{CYAN}{old}{RESET} relocated to {CYAN}{new}{RESET} "
                               f"{MUTED}({ls} losing seasons, pop {pop:.0%}){RESET}")
        for log_sn, fname, is_sec in self.league.expansion_log:
            if log_sn == sn:
                tag = " (second franchise in market)" if is_sec else ""
                events.append(f"{GREEN}Expansion:{RESET} {fname} joins next season{tag}")
        for log_sn, fname, is_sec in self.league.merger_log:
            if log_sn == sn:
                events.append(f"{BLUE}Merger:{RESET} {fname} absorbed from rival league")
        return events

    def _pop_signal_annotations(self, season: Season) -> dict:
        """Return a short context string for each popularity signal."""
        league = self.league
        cfg = league.cfg
        sn = season.number
        n_seasons = len(league.seasons)
        annotations = {}

        # ── Market engagement ─────────────────────────────────────────────────
        # Show which cities are most disengaged (pulling signal negative)
        # or most engaged (pulling signal positive).
        sorted_teams = sorted(league.teams, key=lambda t: t.market_engagement)
        low = [t for t in sorted_teams if t.market_engagement < 0.15][:2]
        high = [t for t in reversed(sorted_teams) if t.market_engagement > 0.40][:2]
        sig = self._last_pop_signals.get("Market engagement", 0.0)
        if sig < -0.002 and low:
            cities = ", ".join(t.franchise.city for t in low)
            annotations["Market engagement"] = f"{cities} disengaged"
        elif sig > 0.002 and high:
            cities = ", ".join(t.franchise.city for t in high)
            annotations["Market engagement"] = f"{cities} driving interest"
        else:
            annotations["Market engagement"] = ""

        # ── Drama ─────────────────────────────────────────────────────────────
        all_series = [sr for rnd in season.playoff_rounds for sr in rnd]
        if all_series:
            min_games = (cfg.series_length + 1) // 2
            sweeps = sum(1 for sr in all_series if len(sr.games) == min_games)
            long = sum(1 for sr in all_series if len(sr.games) >= cfg.series_length - 1)
            n = len(all_series)
            if sweeps == n:
                annotations["Drama"] = "all sweeps"
            elif long == 0:
                annotations["Drama"] = f"no series went {cfg.series_length - 1}+ games"
            elif long == n:
                annotations["Drama"] = f"all {n} series went {cfg.series_length - 1}+ games"
            else:
                annotations["Drama"] = f"{long} of {n} series went {cfg.series_length - 1}+ games"
        else:
            annotations["Drama"] = ""

        # ── Dynasty ───────────────────────────────────────────────────────────
        champ = season.champion
        consecutive = 0
        for past in reversed(league.seasons[:-1]):
            if past.champion is champ:
                consecutive += 1
            else:
                break
        champ_city = champ.franchise_at(sn).city
        if consecutive == 0:
            annotations["Dynasty"] = "new champion"
        elif consecutive == 1:
            annotations["Dynasty"] = f"first repeat — {champ_city}"
        elif consecutive == 2:
            annotations["Dynasty"] = f"two-peat — {champ_city}"
        elif consecutive == 3:
            annotations["Dynasty"] = f"three-peat — fatigue building"
        else:
            annotations["Dynasty"] = f"{consecutive + 1}-peat — fans checking out"

        # ── Entertainment ─────────────────────────────────────────────────────
        meta = league.league_meta
        if meta > 0.10:
            annotations["Entertainment"] = "extreme offense — fans restless"
        elif meta > 0.05:
            annotations["Entertainment"] = "slight offensive lean"
        elif meta > -0.05:
            annotations["Entertainment"] = "balanced era"
        elif meta > -0.10:
            annotations["Entertainment"] = "slight defensive lean"
        else:
            annotations["Entertainment"] = "extreme defense — fans restless"

        # ── Balance ───────────────────────────────────────────────────────────
        window = min(cfg.league_pop_balance_window, n_seasons)
        if window >= 3:
            recent = list(zip(league.seasons[-window:],
                              [s.champion for s in league.seasons[-window:]]))
            unique = len({c for _, c in recent})
            counts = Counter(c.franchise_at(s.number).city for s, c in recent)
            top_city, top_n = counts.most_common(1)[0]
            if top_n >= max(3, window // 2):
                annotations["Balance"] = f"{top_city} won {top_n} of last {window}"
            else:
                annotations["Balance"] = f"{unique} different champs in last {window}"
        else:
            annotations["Balance"] = ""

        # ── Rivalries ─────────────────────────────────────────────────────────
        rivalry_window = min(8, n_seasons)
        if n_seasons >= 4:
            pair_counts: dict = {}
            pair_cities: dict = {}
            for past in league.seasons[-rivalry_window:]:
                for rnd in past.playoff_rounds:
                    for sr in rnd:
                        key = tuple(sorted([sr.seed1.team_id, sr.seed2.team_id]))
                        pair_counts[key] = pair_counts.get(key, 0) + 1
                        if key not in pair_cities:
                            c1 = sr.seed1.franchise_at(past.number).city
                            c2 = sr.seed2.franchise_at(past.number).city
                            pair_cities[key] = f"{c1}–{c2}"
            established = sorted(
                [(k, cnt) for k, cnt in pair_counts.items() if cnt >= 3],
                key=lambda x: -x[1],
            )
            if established:
                top = pair_cities[established[0][0]]
                extra = len(established) - 1
                annotations["Rivalries"] = top + (f" +{extra} more" if extra else "")
            else:
                annotations["Rivalries"] = "none established yet"
        else:
            annotations["Rivalries"] = ""

        # ── Geography ─────────────────────────────────────────────────────────
        playoff_set = {t for rnd in season.playoff_rounds for sr in rnd
                       for t in (sr.seed1, sr.seed2)}
        playoff_set.add(season.champion)
        geo_teams = [t for t in playoff_set if t.franchise.lat != 0.0]
        if len(geo_teams) >= 3:
            lons = [t.franchise.lon for t in geo_teams]
            lats = [t.franchise.lat for t in geo_teams]
            lon_range = max(lons) - min(lons)
            avg_lon = sum(lons) / len(lons)
            avg_lat = sum(lats) / len(lats)
            if lon_range < 18:
                if avg_lon < -100:
                    annotations["Geography"] = "clustered in West"
                elif avg_lon > -82:
                    annotations["Geography"] = "clustered in East"
                else:
                    annotations["Geography"] = "clustered in Midwest"
            elif lon_range < 30 and avg_lat < 35:
                annotations["Geography"] = "clustered in South"
            else:
                annotations["Geography"] = "coast-to-coast playoffs"
        else:
            annotations["Geography"] = ""

        # ── Finals buzz ───────────────────────────────────────────────────────
        if season.playoff_rounds:
            finals = season.playoff_rounds[-1][0]
            c1 = finals.seed1.franchise_at(sn).city
            c2 = finals.seed2.franchise_at(sn).city
            annotations["Finals buzz"] = f"{c1} vs. {c2}"
        else:
            annotations["Finals buzz"] = ""

        # ── Legacy matchup ────────────────────────────────────────────────────
        # Find the single highest-legacy-product series and name it.
        best_series = None
        best_product = 0.0
        for rnd in season.playoff_rounds:
            for sr in rnd:
                product = sr.seed1.legacy * sr.seed2.legacy
                if product > best_product:
                    best_product = product
                    best_series = sr
        if best_series is None or best_product < 0.0002:
            annotations["Legacy matchup"] = "franchises still building legacy"
        else:
            c1 = best_series.seed1.franchise_at(sn).city
            c2 = best_series.seed2.franchise_at(sn).city
            # Is the marquee series the Finals, or an earlier round?
            finals_series = season.playoff_rounds[-1][0]
            if best_series is finals_series:
                annotations["Legacy matchup"] = f"{c1}–{c2} Finals"
            else:
                annotations["Legacy matchup"] = f"{c1}–{c2} marquee matchup"

        # ── Grudge markets ────────────────────────────────────────────────────
        if league.market_grudges:
            top_grudge = sorted(league.market_grudges.items(), key=lambda x: -x[1])[:2]
            parts = [f"{city} ({score:.0%})" for city, score in top_grudge]
            annotations["Grudge markets"] = ", ".join(parts)
        else:
            annotations["Grudge markets"] = "none"

        return annotations

    # ── Reports sub-menu ──────────────────────────────────────────────────────

    def _show_reports(self, season: Season):
        while True:
            clear()
            header("REPORTS", f"After Season {season.number}")
            idx = choose([
                f"League History   {MUTED}season-by-season champions, pace & popularity{RESET}",
                f"Team History     {MUTED}full record for any team{RESET}",
                f"Rosters          {MUTED}current players, ratings & chemistry by team{RESET}",
                f"Market Map       {MUTED}engagement, popularity & grudges by city{RESET}",
                f"Event Log        {MUTED}expansions, mergers & relocations{RESET}",
                f"All-Time Records {MUTED}championships, streaks, best & worst seasons{RESET}",
                f"Rivalries        {MUTED}head-to-head matchup history{RESET}",
                f"Playoff Analysis {MUTED}seed advantage & series length trends{RESET}",
                f"{MUTED}Back{RESET}",
            ], default=8)
            if   idx == 0: self._show_league_history(season)
            elif idx == 1: self._show_team_history(season)
            elif idx == 2: self._show_rosters(season)
            elif idx == 3: self._show_market_map(season)
            elif idx == 4: self._show_event_log(season)
            elif idx == 5: self._show_alltime_records(season)
            elif idx == 6: self._show_rivalries(season)
            elif idx == 7: self._show_playoff_analysis(season)
            else: break

    # ── Report: League History ────────────────────────────────────────────────

    def _show_league_history(self, season: Season):
        league  = self.league
        seasons = league.seasons
        if not seasons:
            press_enter("No seasons played yet.")
            return

        # Pre-build event tags per season
        ev: dict[int, list[str]] = {}
        for sn, name, _ in league.expansion_log:
            ev.setdefault(sn, []).append(f"{GREEN}+{name.split()[-1]}{RESET}")
        for sn, name, _ in league.merger_log:
            ev.setdefault(sn, []).append(f"{CYAN}M:{name.split()[-1]}{RESET}")
        for sn, old, new, *_ in league.relocation_log:
            ev.setdefault(sn, []).append(f"{GOLD}→{new.split()[-1]}{RESET}")

        PAGE = 20
        page = max(0, len(seasons) - PAGE)  # start at most recent page

        while True:
            clear()
            header("LEAGUE HISTORY", self.league_name)
            chunk = seasons[page: page + PAGE]

            print(f"\n  {'S':>3}  {'Champion':<20} {'Record':<13} {'Runner-up':<16} "
                  f"{'RS Leader':<16} {'N':>3}  {'Pop':>4}  {'Bal':>4}")
            divider()

            for s in chunk:
                if s.champion:
                    champ_name = s.champion.franchise_at(s.number).name[:19]
                    w  = s.reg_wins(s.champion)
                    lo = s.reg_losses(s.champion)
                    record = _wl(w, lo)
                    # Runner-up: finalist who lost
                    if s.playoff_rounds:
                        finals = s.playoff_rounds[-1][0]
                        ru = finals.seed2 if finals.winner is finals.seed1 else finals.seed1
                        ru_name = ru.franchise_at(s.number).nickname[:15]
                        # Star if champion also led regular season
                        rs_leader = s.regular_season_standings[0] if s.regular_season_standings else None
                        rs_name = rs_leader.franchise_at(s.number).nickname[:15] if rs_leader else "—"
                        rs_tag = f"{GOLD}★{RESET}" if rs_leader is s.champion else " "
                    else:
                        ru_name, rs_name, rs_tag = "—", "—", " "
                else:
                    champ_name, record, ru_name, rs_name, rs_tag = "—", "—", "—", "—", " "

                n_teams = len(s.teams)
                lp = getattr(s, '_league_popularity', 0.0)
                lp_str = f"{lp:.0%}" if lp else "  —"
                shock_tag = f"{RED}⚡{RESET}" if s.meta_shock else ""
                tags = " ".join(ev.get(s.number, []))
                tags_str = f"  {shock_tag}{tags}" if (shock_tag or tags) else ""

                # Parity: std dev of win%
                win_pcts = [s.reg_win_pct(t) for t in s.teams
                            if s.reg_wins(t) + s.reg_losses(t) > 0]
                if len(win_pcts) >= 2:
                    mean = sum(win_pcts) / len(win_pcts)
                    sd = (sum((x - mean) ** 2 for x in win_pcts) / len(win_pcts)) ** 0.5
                    bal_c = GREEN if sd < 0.14 else (RED if sd > 0.20 else MUTED)
                    bal_str = f"{bal_c}{sd:.2f}{RESET}"
                else:
                    bal_str = "  —"

                print(f"  {s.number:>3}  {rs_tag}{champ_name:<20} {record:<13} "
                      f"{ru_name:<16} {rs_name:<16} {n_teams:>3}  {lp_str:>4}  {bal_str}{tags_str}")

                award_parts = []
                if s.mvp:
                    award_parts.append(f"MVP {s.mvp.name}")
                if s.opoy:
                    award_parts.append(f"OPOY {s.opoy.name}")
                if s.dpoy:
                    award_parts.append(f"DPOY {s.dpoy.name}")
                if s.finals_mvp:
                    award_parts.append(f"FMVP {s.finals_mvp.name}")
                if award_parts:
                    print(f"       {MUTED}{('  ·  ').join(award_parts)}{RESET}")

            divider()
            total = len(seasons)
            showing = f"Seasons {page+1}–{min(page+PAGE, total)} of {total}"
            nav = []
            if page > 0:             nav.append(f"{CYAN}[P]{RESET}rev")
            if page + PAGE < total:  nav.append(f"{CYAN}[N]{RESET}ext")
            nav.append(f"{CYAN}[Q]{RESET}uit")
            print(f"\n  {showing}    {' · '.join(nav)}")
            raw = prompt("").lower()
            if raw == "p" and page > 0:
                page = max(0, page - PAGE)
            elif raw == "n" and page + PAGE < total:
                page += PAGE
            else:
                break

    # ── Report: Team History ──────────────────────────────────────────────────

    def _playoff_result_label(self, team: Team, s: Season) -> str:
        """Short string describing a team's playoff fate in a given season."""
        playoff_set = {t for rnd in s.playoff_rounds for sr in rnd
                       for t in (sr.seed1, sr.seed2)}
        if team not in playoff_set:
            return "Missed"
        if team is s.champion:
            return f"{GOLD}Champion{RESET}"
        finalist = (s.playoff_rounds[-1][0].seed2
                    if s.playoff_rounds[-1][0].winner is s.playoff_rounds[-1][0].seed1
                    else s.playoff_rounds[-1][0].seed1)
        if team is finalist:
            return f"{CYAN}Finals{RESET}"
        n_rounds = len(s.playoff_rounds)
        labels = _round_labels(n_rounds)
        for rnd_idx, rnd in enumerate(s.playoff_rounds):
            for sr in rnd:
                if sr.winner is not team and (sr.seed1 is team or sr.seed2 is team):
                    return f"Lost {labels[rnd_idx]}"
        return "Playoff"

    def _show_team_history(self, season: Season):
        """Franchise-identity history selector — one entry per name, never mixed."""
        league  = self.league
        seasons = league.seasons

        # Collect every team object that ever appeared in a season
        all_teams: set = set()
        for s in seasons:
            all_teams.update(s.teams)
        all_teams.update(league.teams)

        team_seasons: dict = {t: [s for s in seasons if t in s.teams] for t in all_teams}
        active_set = set(league.teams)

        # Build one entry per franchise identity:
        # (franchise, team, seasons_under_this_name, is_current_franchise)
        ident_entries = []
        for t in all_teams:
            played = team_seasons[t]
            hist = t.franchise_history  # [(start_season_num, franchise), ...]
            for idx, (start_sn, fran) in enumerate(hist):
                if idx + 1 < len(hist):
                    end_sn = hist[idx + 1][0]
                    fran_seasons = [s for s in played if start_sn <= s.number < end_sn]
                else:
                    fran_seasons = [s for s in played if s.number >= start_sn]
                is_current = (idx == len(hist) - 1) and (t in active_set)
                ident_entries.append((fran, t, fran_seasons, is_current))

        active_idents  = [(f, t, ss) for f, t, ss, ic in ident_entries if ic]
        defunct_idents = [(f, t, ss) for f, t, ss, ic in ident_entries if not ic]

        active_idents  = sorted(active_idents,  key=lambda e: -_fan_base(e[1]))
        defunct_idents = sorted(defunct_idents, key=lambda e: -(e[2][-1].number if e[2] else 0))
        all_idents = active_idents + defunct_idents

        while True:
            clear()
            header("TEAM HISTORY",
                   f"Select a franchise  ·  {len(active_idents)} active  ·  {len(defunct_idents)} defunct")
            print(f"\n  {'#':>3}  {'Franchise':<28} {'Seasons':>7}  {'Titles':>6}  {'Span':>11}")
            divider()

            if active_idents:
                print(f"  {BOLD}  — Active —{RESET}")
            for i, (fran, t, ss) in enumerate(active_idents, 1):
                titles = sum(1 for s in ss if s.champion is t)
                title_str = f"{GOLD}{titles}★{RESET}" if titles else f"{MUTED}—{RESET}"
                span = f"S{ss[0].number}–now" if ss else "no seasons"
                print(f"  {i:>3}. {fran.name:<28} {len(ss):>7}  {title_str:>6}  {MUTED}{span:>11}{RESET}")

            if defunct_idents:
                print(f"\n  {MUTED}  — Defunct —{RESET}")
            for j, (fran, t, ss) in enumerate(defunct_idents, len(active_idents) + 1):
                titles = sum(1 for s in ss if s.champion is t)
                title_str = f"{GOLD}{titles}★{RESET}" if titles else f"{MUTED}—{RESET}"
                span = (f"S{ss[0].number}–S{ss[-1].number}" if ss else "no seasons")
                print(f"  {j:>3}. {MUTED}{fran.name:<28}{RESET} {len(ss):>7}  {title_str:>6}  "
                      f"{MUTED}{span:>11}{RESET}")

            print(f"\n  {CYAN}[0]{RESET} {MUTED}Back{RESET}")
            raw = prompt("Franchise number (Enter to go back):").strip()
            if raw in ("", "0"):
                break
            if not raw.isdigit():
                continue
            val = int(raw)
            if 1 <= val <= len(all_idents):
                fran, t, ss = all_idents[val - 1]
                self._show_team_detail(fran, t, ss)

    def _show_team_detail(self, franchise, team, entries: list):
        """Season-by-season history for one franchise identity."""
        PAGE = 20
        page = max(0, len(entries) - PAGE)

        while True:
            clear()
            champ_count = sum(1 for s in entries if s.champion is team)
            champ_str = f"  {GOLD}{champ_count} title{'s' if champ_count != 1 else ''}{RESET}" if champ_count else ""
            header("TEAM HISTORY", f"{franchise.name}{champ_str}")

            # Show org context if part of a relocated franchise chain
            if len(team.franchise_history) > 1:
                parts = [f"{MUTED}S{sn}{RESET} {f.name}" for sn, f in team.franchise_history]
                print(f"\n  {MUTED}Org history: {' → '.join(parts)}{RESET}")

            print(f"\n  {'S':>3}  {'Record':<14} {'Pos':>4}  "
                  f"{'Result':<18}  {'PS/G':>5}  {'PA/G':>5}  {'Diff':>5}  {'Fan Base':>8}")
            divider()

            chunk = entries[page: page + PAGE]
            for s in chunk:
                w    = s.reg_wins(team)
                lo   = s.reg_losses(team)
                pos  = s.regular_season_standings.index(team) + 1
                n    = len(s.teams)
                pos_str = f"{pos}/{n}"
                result  = self._playoff_result_label(team, s)
                eng  = (s._market_engagement.get(team, team.market_engagement)
                        if hasattr(s, '_market_engagement') else team.market_engagement)
                fb   = eng * franchise.effective_metro
                ppg  = s.team_ppg(team)
                papg = s.team_papg(team)
                diff = ppg - papg
                diff_c = GREEN if diff > 0 else (RED if diff < 0 else MUTED)
                record = _wl(w, lo)
                print(f"  {s.number:>3}  {record:<14} {pos_str:>4}  "
                      f"{result:<18}  {ppg:>5.1f}  {papg:>5.1f}  "
                      f"{diff_c}{diff:>+5.1f}{RESET}  {fb:>6.1f}M")

            divider()
            total = len(entries)
            showing = f"Seasons {page+1}–{min(page+PAGE, total)} of {total}"
            nav = []
            if page > 0:            nav.append(f"{CYAN}[P]{RESET}rev")
            if page + PAGE < total: nav.append(f"{CYAN}[N]{RESET}ext")
            nav.append(f"{CYAN}[Q]{RESET}uit")
            print(f"\n  {showing}    {' · '.join(nav)}")
            raw = prompt("").lower()
            if raw == "p" and page > 0:
                page = max(0, page - PAGE)
            elif raw == "n" and page + PAGE < total:
                page += PAGE
            else:
                break

    # ── Report: Rosters ───────────────────────────────────────────────────────

    def _show_rosters(self, season: Season):
        """All teams' current rosters with player ratings, contract, trend, chemistry."""
        league = self.league
        sn     = season.number
        cfg    = league.cfg
        teams  = sorted(league.teams, key=lambda t: -t.net_rating())
        avg_o, avg_d = _avg_ratings(league.teams)

        PAGE = 6  # teams per page
        page = 0
        total = len(teams)

        tier_colors = {TIER_ELITE: GOLD, TIER_HIGH: CYAN, TIER_MID: "", TIER_LOW: MUTED}

        while True:
            clear()
            header("ROSTERS", f"Season {sn}  ·  {total} teams")
            chunk = teams[page: page + PAGE]

            for team in chunk:
                chem   = team.compute_chemistry(cfg)
                net    = _rel_net(team.ortg, team.drtg, avg_o, avg_d)
                chem_c = GREEN if chem >= 1.05 else (RED if chem < 0.90 else CYAN)
                print(f"\n  {BOLD}{team.franchise_at(sn).name}{RESET}"
                      f"  {MUTED}Net {net:+.1f}  ORtg {team.ortg:.1f}  DRtg {team.drtg:.1f}"
                      f"  Pace {team.pace:.0f}{RESET}"
                      f"  Chem {chem_c}{chem:.2f}{RESET}")
                print(f"  {'Slot':<8} {'Name':<22} {'Pos':<5} {'Age':>3}  "
                      f"{'ORtg':>5}  {'DRtg':>5}  {'Zone':<6}  "
                      f"{'Yrs':>3}  {'Tr':>2}  {'Mood':<4}  {'Popularity':<9}  Motivation")
                print(f"  {MUTED}{'─' * 84}{RESET}")
                for idx, player in enumerate(team.roster):
                    slot_lbl = team.slot_label(idx)
                    if player is None:
                        print(f"  {MUTED}{slot_lbl:<8} — empty{RESET}")
                    else:
                        mot_c = (GREEN if player.motivation == MOT_WINNING
                                 else GOLD if player.motivation == MOT_MARKET else CYAN)
                        trend_s = player.trend
                        tc = tier_colors.get(player.ceiling_tier, "")
                        pop_t = popularity_tier(player.popularity)
                        pop_c = GOLD if player.popularity >= 0.65 else (CYAN if player.popularity >= 0.40 else MUTED)
                        print(f"  {MUTED}{slot_lbl:<8}{RESET}"
                              f" {tc}{player.name:<22}{RESET}"
                              f" {player.position:<5} {player.age:>3}"
                              f"  {player.ortg_contrib:>+5.1f}  {player.drtg_contrib:>+5.1f}"
                              f"  {player.preferred_zone:<6}"
                              f"  {player.contract_years_remaining:>3}"
                              f"  {trend_s:>2}"
                              f"  {happiness_emoji(player.happiness):<4}"
                              f"  {pop_c}{pop_t:<9}{RESET}"
                              f"  {mot_c}{player.motivation}{RESET}")

            print()
            divider()
            nav = []
            if page > 0:           nav.append("p=prev")
            if page + PAGE < total: nav.append("n=next")
            nav.append("Enter=back")
            raw = prompt(f"  [{', '.join(nav)}]: ").strip().lower()
            if raw == "p" and page > 0:
                page -= PAGE
            elif raw == "n" and page + PAGE < total:
                page += PAGE
            else:
                break

    # ── Report: Market Map ────────────────────────────────────────────────────

    def _show_market_map(self, season: Season):
        league = self.league

        # Group current teams by city
        city_teams: dict[str, list] = {}
        for t in league.teams:
            city_teams.setdefault(t.franchise.city, []).append(t)

        # All cities with content: active + grudge
        active_cities = sorted(
            city_teams.items(),
            key=lambda x: -max(t.franchise.effective_metro for t in x[1]),
        )
        grudge_cities = sorted(
            [(c, s) for c, s in league.market_grudges.items() if c not in city_teams],
            key=lambda x: -x[1],
        )

        # Re-sort active cities by fan base (engagement × metro) descending
        active_cities = sorted(
            city_teams.items(),
            key=lambda x: -sum(_fan_base(t) for t in x[1]),
        )
        max_fb = max(
            (_fan_base(t) for teams in city_teams.values() for t in teams),
            default=1.0,
        )

        clear()
        header("MARKET MAP", f"After Season {season.number}")

        # Active markets
        print(f"\n  {BOLD}Active markets{RESET}  "
              f"{MUTED}Fan Base = engagement × market size  ·  sorted by fan base{RESET}\n")
        print(f"  {'City':<18} {'Team':<22} {'Fan Base':<22}  {'Eng':>5}  Metro")
        divider()
        for city, teams in active_cities:
            metro = max(t.franchise.effective_metro for t in teams)
            for i, t in enumerate(sorted(teams, key=lambda x: x.franchise.secondary)):
                fb      = _fan_base(t)
                fb_str  = _fan_base_bar(fb, max_fb, 12)
                eng_pct = f"{t.market_engagement:.0%}"
                grudge_tag = (f"  {RED}grudge{RESET}"
                              if t.franchise.city in league.market_grudges else "")
                if i == 0:
                    print(f"  {city:<18} {t.franchise.nickname:<22} {fb_str:<22}  "
                          f"{MUTED}{eng_pct:>5}{RESET}  {MUTED}{metro:.1f}M{RESET}{grudge_tag}")
                else:
                    print(f"  {'':18} {t.franchise.nickname:<22} {fb_str:<22}  "
                          f"{MUTED}{eng_pct:>5}{RESET}")

        # Grudge markets
        if grudge_cities:
            print(f"\n  {BOLD}{RED}Grudge markets{RESET}  "
                  f"{MUTED}(vacated — fans still bitter){RESET}\n")
            print(f"  {'City':<18} {'Grudge':>8}  {'Metro':>7}  Decays to floor at 5%")
            divider()
            for city, score in grudge_cities:
                metro = league._grudge_metro.get(city, 0.0)
                g_color = RED if score > 0.5 else (GOLD if score > 0.2 else MUTED)
                print(f"  {city:<18} {g_color}{score:.0%}{RESET}       "
                      f"{MUTED}{metro:.1f}M{RESET}")

        press_enter()

    # ── Report: Event Log ─────────────────────────────────────────────────────

    def _show_event_log(self, season: Season):
        league = self.league

        # Gather all events
        events: list[tuple[int, str]] = []
        for sn, name, is_sec in league.expansion_log:
            tag = " (co-tenant)" if is_sec else ""
            events.append((sn, f"{GREEN}EXPANSION{RESET}   {name}{tag} joined S{sn+1}"))
        for sn, name, is_sec in league.merger_log:
            tag = " (co-tenant)" if is_sec else ""
            events.append((sn, f"{CYAN}MERGER{RESET}      {name}{tag} joined S{sn+1}"))
        for sn, old, new, losing, bot2, pop in league.relocation_log:
            events.append((sn, f"{GOLD}RELOCATION{RESET}  {old} → {new}  "
                              f"{MUTED}({losing} losing seasons, pop {pop:.0%}){RESET}"))

        events.sort(key=lambda x: x[0])

        # Also note rule-change shocks from seasons
        for s in league.seasons:
            if s.meta_shock:
                events.append((s.number, f"{RED}RULE SHOCK{RESET}  Era reset after S{s.number}  "
                                         f"{MUTED}(meta → ~0){RESET}"))
        events.sort(key=lambda x: x[0])

        if not events:
            clear()
            header("EVENT LOG", self.league_name)
            print(f"\n  {MUTED}No notable events yet.{RESET}")
            press_enter()
            return

        PAGE = 22
        page = 0

        while True:
            clear()
            header("EVENT LOG", self.league_name)
            chunk = events[page: page + PAGE]
            print(f"\n  {'S':>3}  {'Event'}")
            divider()
            for sn, desc in chunk:
                print(f"  {sn:>3}  {desc}")
            divider()
            total = len(events)
            showing = f"Events {page+1}–{min(page+PAGE, total)} of {total}"
            nav = []
            if page > 0:            nav.append(f"{CYAN}[P]{RESET}rev")
            if page + PAGE < total: nav.append(f"{CYAN}[N]{RESET}ext")
            nav.append(f"{CYAN}[Q]{RESET}uit")
            print(f"\n  {showing}    {' · '.join(nav)}")
            raw = prompt("").lower()
            if raw == "p" and page > 0:
                page = max(0, page - PAGE)
            elif raw == "n" and page + PAGE < total:
                page += PAGE
            else:
                break

    # ── Report: All-Time Records ──────────────────────────────────────────────

    def _show_alltime_records(self, _season: Season):
        while True:
            clear()
            header("ALL-TIME RECORDS", self.league_name)
            n = len(self.league.seasons)
            print(f"\n  {n} seasons · {len(self.league.teams)} current teams\n")
            idx = choose([
                f"Championships & Finals  {MUTED}titles, finals apps, RS crowns{RESET}",
                f"Streaks & Droughts      {MUTED}dynasty runs, playoff streaks, droughts{RESET}",
                f"Best & Worst Seasons    {MUTED}top and bottom single-season records{RESET}",
                f"{MUTED}Back{RESET}",
            ], default=3)
            if   idx == 0: self._show_championships_table()
            elif idx == 1: self._show_streaks_droughts()
            elif idx == 2: self._show_best_worst()
            else: break

    def _show_championships_table(self):
        league  = self.league
        seasons = league.seasons
        from collections import defaultdict

        titles       = defaultdict(int)
        finals_wins  = defaultdict(int)
        finals_apps  = defaultdict(int)
        rs_firsts    = defaultdict(int)
        po_seasons_s = defaultdict(set)   # team -> set of season numbers with playoff app
        seasons_in   = defaultdict(int)

        for s in seasons:
            for t in s.teams:
                seasons_in[t] += 1
            if s.champion:
                titles[s.champion]      += 1
                finals_wins[s.champion] += 1
                finals_apps[s.champion] += 1
            if s.playoff_rounds:
                final = s.playoff_rounds[-1][0]
                ru = final.seed2 if final.winner is final.seed1 else final.seed1
                finals_apps[ru] += 1
            if s.regular_season_standings:
                rs_firsts[s.regular_season_standings[0]] += 1
            for rnd in s.playoff_rounds:
                for sr in rnd:
                    po_seasons_s[sr.seed1].add(s.number)
                    po_seasons_s[sr.seed2].add(s.number)

        all_teams = sorted(
            league.teams,
            key=lambda t: (-titles[t], -finals_apps[t], -len(po_seasons_s[t])),
        )

        clear()
        header("CHAMPIONSHIPS & FINALS", self.league_name)
        print(f"\n  {'#':>2}  {'Team':<26}  {'Ttls':>5}  {'Finals':>6}  "
              f"{'Win%':>5}  {'RS#1':>5}  {'PO':>4}  {'Szns':>5}")
        divider()
        for rank, t in enumerate(all_teams, 1):
            name   = t.franchise.name[:26]
            fmr    = _fmr_tag(t)
            ttls   = titles[t]
            fa     = finals_apps[t]
            wpct   = f"{ttls/fa:.0%}" if fa else "  —  "
            rs1    = rs_firsts[t]
            po     = len(po_seasons_s[t])
            sp     = seasons_in[t]
            star   = f"{GOLD}★{RESET}" if ttls else " "
            ttl_c  = GOLD if ttls else RESET
            print(f"  {rank:>2}. {name:<26}  {star}{ttl_c}{ttls:>4}{RESET}  "
                  f"{fa:>6}  {wpct:>5}  {rs1:>5}  {po:>4}  {sp:>5}{fmr}")
        press_enter()

    def _show_streaks_droughts(self):
        league  = self.league
        seasons = league.seasons
        if not seasons:
            press_enter("No seasons yet.")
            return

        played_sn = {}
        won_sn    = {}
        po_sn     = {}
        for t in league.teams:
            # Only count seasons under the team's current franchise identity
            franchise_start = t.franchise_history[-1][0]
            played_sn[t] = sorted(s.number for s in seasons
                                  if t in s.teams and s.number >= franchise_start)
            won_sn[t]    = {s.number for s in seasons
                            if s.champion is t and s.number >= franchise_start}
            po_sn[t]     = {s.number for s in seasons
                            if s.number >= franchise_start
                            for rnd in s.playoff_rounds for sr in rnd
                            if sr.seed1 is t or sr.seed2 is t}

        def best_streak(sn_list, good):
            best = (0, None, None)
            cur = 0; start = None
            for sn in sn_list:
                if sn in good:
                    if cur == 0: start = sn
                    cur += 1
                    if cur > best[0]: best = (cur, start, sn)
                else:
                    cur = 0
            return best

        def best_drought(sn_list, good):
            """Longest run of seasons NOT in `good`."""
            bad  = set(sn_list) - good
            return best_streak(sn_list, bad)

        # Compute each leaderboard
        dynasty   = sorted([(t, *best_streak (played_sn[t], won_sn[t]))
                             for t in league.teams if won_sn[t]],    key=lambda x: -x[1])
        droughts  = sorted([(t, *best_drought(played_sn[t], won_sn[t]))
                             for t in league.teams if won_sn[t]],    key=lambda x: -x[1])
        po_streak = sorted([(t, *best_streak (played_sn[t], po_sn[t]))
                             for t in league.teams if po_sn[t]],     key=lambda x: -x[1])
        po_dry    = sorted([(t, *best_drought(played_sn[t], po_sn[t]))
                             for t in league.teams if played_sn[t]], key=lambda x: -x[1])

        def show_block(title, color, rows, n=8):
            print(f"\n  {BOLD}{title}{RESET}\n")
            print(f"  {'Team':<26}  {'Len':>5}  Seasons")
            divider()
            for t, length, start, end in rows[:n]:
                if length == 0:
                    continue
                name   = t.franchise.name[:26]
                fmr    = _fmr_tag(t)
                window = (f"S{start}–S{end}" if start != end else f"S{start}") if start else "—"
                print(f"  {name:<26}  {color}{length:>5}{RESET}  {MUTED}{window}{RESET}{fmr}")

        clear()
        header("STREAKS & DROUGHTS", self.league_name)
        show_block("Championship Dynasties",       GOLD,  dynasty)
        show_block("Championship Droughts",        RED,   droughts)
        show_block("Longest Playoff Streaks",      GREEN, po_streak)
        show_block("Longest Playoff Droughts",     RED,   po_dry)
        press_enter()

    def _show_best_worst(self):
        league  = self.league
        seasons = league.seasons
        records = []
        for s in seasons:
            for t in s.teams:
                w  = s.reg_wins(t)
                lo = s.reg_losses(t)
                if w + lo == 0: continue
                ppg  = s.team_ppg(t)
                papg = s.team_papg(t)
                records.append((s, t, w, lo, w / (w + lo), ppg, papg))
        if not records:
            press_enter("Not enough data yet.")
            return

        best  = sorted(records, key=lambda x: (-x[4], -x[2]))[:12]
        worst = sorted(records, key=lambda x: (x[4],  x[2]))[:12]

        def show_block(title, rows):
            print(f"\n  {BOLD}{title}{RESET}\n")
            print(f"  {'S':>3}  {'Franchise':<24}  {'Record':<14}  {'PS/G':>5}  {'PA/G':>5}  {'Diff':>5}")
            divider()
            for s, t, w, lo, pct, ppg, papg in rows:
                fname    = t.franchise_at(s.number).name[:24]
                fmr      = _fmr_tag(t)
                champ_t  = f" {GOLD}★{RESET}" if t is s.champion else ""
                record   = _wl(w, lo)
                diff     = ppg - papg
                diff_c   = GREEN if diff > 0 else (RED if diff < 0 else MUTED)
                pct_c    = GREEN if pct >= 0.70 else (RED if pct <= 0.35 else RESET)
                print(f"  {s.number:>3}  {fname:<24}  "
                      f"{pct_c}{record:<14}{RESET}  {ppg:>5.1f}  {papg:>5.1f}  "
                      f"{diff_c}{diff:>+5.1f}{RESET}{champ_t}{fmr}")

        clear()
        header("BEST & WORST SEASONS", self.league_name)
        show_block("Best Single Seasons",  best)
        show_block("Worst Single Seasons", worst)
        press_enter()

    # ── Report: Rivalries ─────────────────────────────────────────────────────

    def _show_rivalries(self, _season: Season):
        league  = self.league
        seasons = league.seasons
        if not seasons:
            clear(); header("RIVALRIES", self.league_name)
            press_enter("No seasons played yet."); return

        from collections import defaultdict
        team_by_id = {t.team_id: t for t in league.teams}

        # ── Regular-season head-to-head ──────────────────────────────────────
        rs_wins: dict = defaultdict(lambda: defaultdict(int))
        for s in seasons:
            for g in s.regular_season_games:
                rs_wins[g.winner.team_id][g.loser.team_id] += 1

        rs_pairs: dict = {}
        all_ids = set(rs_wins) | {lid for d in rs_wins.values() for lid in d}
        for aid in all_ids:
            for bid in all_ids:
                if aid >= bid: continue
                wa = rs_wins[aid][bid]
                wb = rs_wins[bid][aid]
                if wa + wb:
                    rs_pairs[(aid, bid)] = (wa, wb)
        rs_sorted = sorted(rs_pairs.items(), key=lambda x: -(x[1][0]+x[1][1]))[:15]

        # ── Playoff series ───────────────────────────────────────────────────
        po_wins: dict = defaultdict(lambda: defaultdict(int))
        for s in seasons:
            for rnd in s.playoff_rounds:
                for sr in rnd:
                    key = tuple(sorted([sr.seed1.team_id, sr.seed2.team_id]))
                    po_wins[key][sr.winner.team_id] += 1
        po_sorted = sorted(po_wins.items(), key=lambda x: -sum(x[1].values()))[:15]

        # ── Finals ───────────────────────────────────────────────────────────
        finals_wins: dict = defaultdict(lambda: defaultdict(int))
        for s in seasons:
            if s.playoff_rounds:
                final = s.playoff_rounds[-1][0]
                key   = tuple(sorted([final.seed1.team_id, final.seed2.team_id]))
                finals_wins[key][final.winner.team_id] += 1
        finals_sorted = sorted(finals_wins.items(), key=lambda x: -sum(x[1].values()))

        PAGES = 3
        page  = 0

        def team_name(tid):
            t = team_by_id.get(tid)
            return t.franchise.name[:24] if t else f"(id {tid})"

        while True:
            clear()
            if page == 0:
                header("RIVALRIES — Regular Season", self.league_name)
                print(f"\n  Head-to-head records (all regular-season games)\n")
                print(f"  {'#':>2}  {'Team A':<25} {'Wins':>5}  {'Team B':<25} {'Wins':>5}  Games")
                divider()
                for i, ((aid, bid), (wa, wb)) in enumerate(rs_sorted, 1):
                    na, nb = team_name(aid), team_name(bid)
                    lead_a = GREEN if wa > wb else (RED if wa < wb else MUTED)
                    lead_b = GREEN if wb > wa else (RED if wb < wa else MUTED)
                    print(f"  {i:>2}. {na:<25} {lead_a}{wa:>5}{RESET}  "
                          f"{nb:<25} {lead_b}{wb:>5}{RESET}  {wa+wb:>5}")

            elif page == 1:
                header("RIVALRIES — Playoff Series", self.league_name)
                print(f"\n  All-time series record between each pair\n")
                print(f"  {'#':>2}  {'Team A':<25} {'W':>3}  {'Team B':<25} {'W':>3}  Series")
                divider()
                for i, (key, wins) in enumerate(po_sorted, 1):
                    aid, bid = key
                    na, nb   = team_name(aid), team_name(bid)
                    wa, wb   = wins.get(aid, 0), wins.get(bid, 0)
                    total    = wa + wb
                    lead_a   = GOLD if wa > wb else (MUTED if wa == wb else RED)
                    lead_b   = GOLD if wb > wa else (MUTED if wa == wb else RED)
                    print(f"  {i:>2}. {na:<25} {lead_a}{wa:>3}{RESET}  "
                          f"{nb:<25} {lead_b}{wb:>3}{RESET}  {total:>5}")

            elif page == 2:
                header("RIVALRIES — Finals Matchups", self.league_name)
                print(f"\n  Teams that have met in the Finals\n")
                if not finals_sorted:
                    print(f"  {MUTED}No Finals data yet.{RESET}")
                else:
                    print(f"  {'Team A':<25} {'W':>3}  {'Team B':<25} {'W':>3}  Finals")
                    divider()
                    for (aid, bid), wins in finals_sorted:
                        na, nb = team_name(aid), team_name(bid)
                        wa, wb = wins.get(aid, 0), wins.get(bid, 0)
                        lead_a = GOLD if wa > wb else (MUTED if wa == wb else RED)
                        lead_b = GOLD if wb > wa else (MUTED if wa == wb else RED)
                        print(f"  {na:<25} {lead_a}{wa:>3}{RESET}  "
                              f"{nb:<25} {lead_b}{wb:>3}{RESET}  {wa+wb:>5}")

            divider()
            nav = []
            if page > 0:          nav.append(f"{CYAN}[P]{RESET}rev")
            if page < PAGES - 1:  nav.append(f"{CYAN}[N]{RESET}ext")
            nav.append(f"{CYAN}[Q]{RESET}uit")
            print(f"\n  Page {page+1}/{PAGES}    {' · '.join(nav)}")
            raw = prompt("").lower()
            if   raw == "p" and page > 0:         page -= 1
            elif raw == "n" and page < PAGES - 1: page += 1
            else: break

    # ── Report: Playoff Analysis ──────────────────────────────────────────────

    def _show_playoff_analysis(self, _season: Season):
        league  = self.league
        seasons = league.seasons
        po_seasons = [s for s in seasons if s.playoff_rounds]
        if not po_seasons:
            clear(); header("PLAYOFF ANALYSIS", self.league_name)
            press_enter("No playoff data yet."); return

        from collections import defaultdict

        round_hs_wins = defaultdict(int)
        round_total   = defaultdict(int)
        round_lengths = defaultdict(lambda: defaultdict(int))

        for s in po_seasons:
            n_rounds = len(s.playoff_rounds)
            labels   = _round_labels(n_rounds)
            for rnd_idx, rnd in enumerate(s.playoff_rounds):
                rname = labels[rnd_idx]
                for sr in rnd:
                    round_total[rname]   += 1
                    round_lengths[rname][len(sr.games)] += 1
                    if sr.winner is sr.seed1:
                        round_hs_wins[rname] += 1

        # Ordered from earliest round to Finals — use abbreviated labels from _round_labels
        order = ["R16", "QF", "SF", "Finals"]
        present = [r for r in order if r in round_total]
        for r in round_total:
            if r not in present:
                present.insert(0, r)

        all_lengths = sorted({n for d in round_lengths.values() for n in d})
        series_max  = league.cfg.series_length
        series_min  = (series_max + 1) // 2

        def len_label(n):
            if n == series_min: return "Sweep"
            if n == series_max: return "Full"
            return f"{n}G"

        clear()
        header("PLAYOFF ANALYSIS", self.league_name)
        n_s = len(po_seasons)
        n_sr = sum(round_total.values())
        print(f"\n  {n_s} seasons · {n_sr} total series · best-of-{series_max}\n")

        # ── Higher-seed advantage ─────────────────────────────────────────────
        print(f"  {BOLD}Higher-seed win%  by round{RESET}\n")
        print(f"  {'Round':<16} {'Series':>7}  {'HS Wins':>8}  {'HS Win%':>8}")
        divider()
        for rname in present:
            tot  = round_total[rname]
            wins = round_hs_wins[rname]
            pct  = wins / tot if tot else 0
            pc   = GREEN if pct >= 0.60 else (RED if pct < 0.45 else MUTED)
            print(f"  {rname:<16} {tot:>7}  {wins:>8}  {pc}{pct:.0%}{RESET}")
        tot_all  = sum(round_total.values())
        wins_all = sum(round_hs_wins.values())
        if tot_all:
            pct = wins_all / tot_all
            pc  = GREEN if pct >= 0.60 else (RED if pct < 0.45 else MUTED)
            divider()
            print(f"  {'All rounds':<16} {tot_all:>7}  {wins_all:>8}  {pc}{pct:.0%}{RESET}")

        # ── Series length distribution ────────────────────────────────────────
        print(f"\n  {BOLD}Series length distribution  by round{RESET}\n")
        hdr = f"  {'Round':<16}"
        for n in all_lengths:
            hdr += f"  {len_label(n):>7}"
        print(hdr)
        divider()
        for rname in present:
            tot = round_total[rname]
            row = f"  {rname:<16}"
            for n in all_lengths:
                cnt = round_lengths[rname].get(n, 0)
                pct = cnt / tot if tot else 0
                row += f"  {pct:.0%}({cnt:>2})"
            print(row)

        press_enter()

    # ── Post-season decisions ─────────────────────────────────────────────────

    def _post_season(self, season: Season):
        # Revenue: fan_base summed across all teams × revenue rate
        revenue = sum(_fan_base(t) for t in self.league.teams) * self.league.cfg.revenue_per_fan_million
        self._treasury += revenue
        self._last_revenue = revenue
        self._handle_player_offseason(season)
        self._commissioner_desk(season)
        self._handle_force_relocation(season)
        self._handle_expansion_decision(season)
        self._handle_merger_decision(season)

    # ── Player offseason ──────────────────────────────────────────────────────

    def _handle_player_offseason(self, season: Season) -> None:
        """Retirement news → star FA events → draft → FA pool display."""
        retiring = self._retiring_this_season
        new_fas  = self._new_fas_this_season
        league   = self.league
        sn       = season.number

        # ── Retirements ───────────────────────────────────────────────────────
        if retiring:
            clear()
            header("PLAYER NEWS", f"After Season {sn}")
            print(f"\n  {GOLD}Retirements{RESET}\n")
            for p in retiring:
                team_name = next(
                    (t.franchise_at(sn).name for t in league.teams
                     if p in t.roster),
                    "Free Agent"
                )
                tier_c = GOLD if p.peak_overall >= 14 else (CYAN if p.peak_overall >= 8 else MUTED)
                print(f"  {happiness_emoji(p.happiness)} {tier_c}{p.name}{RESET}  {MUTED}{p.position} · Age {p.age} · "
                      f"{team_name}{RESET}")
                print(f"     Career: {p.seasons_played} seasons  "
                      f"Peak ORtg {p.peak_ortg:+.1f}  DRtg {p.peak_drtg:+.1f}")
            press_enter()

        # ── Contract expirations ──────────────────────────────────────────────
        if new_fas:
            clear()
            header("CONTRACT NEWS", f"After Season {sn}")
            print(f"\n  {CYAN}Players entering free agency{RESET}\n")
            for p in new_fas:
                old_team = next(
                    (t.franchise_at(sn).name for t in league.teams
                     if any(r is p for r in t.roster)),
                    "—"
                )
                mot_c = GREEN if p.motivation == MOT_WINNING else (GOLD if p.motivation == MOT_MARKET else CYAN)
                print(f"  {p.name:<22} {MUTED}{p.position} · Age {p.age}{RESET}  "
                      f"ORtg {p.ortg_contrib:+.1f}  DRtg {p.drtg_contrib:+.1f}  "
                      f"{happiness_emoji(p.happiness)}  "
                      f"{mot_c}{p.motivation}{RESET}  {MUTED}(was: {old_team}){RESET}")
            press_enter()

        # ── Star FA events ────────────────────────────────────────────────────
        star_fas = [p for p in league.free_agent_pool
                    if p.peak_overall >= league.cfg.star_fa_threshold]
        for star in star_fas:
            self._handle_star_fa_event(star, season)

        # ── Draft ─────────────────────────────────────────────────────────────
        self._handle_draft(season)

        # ── Phase 2: auto-fill remaining empties, recompute ratings ──────────
        league.offseason_phase2()

        # ── FA pool summary ───────────────────────────────────────────────────
        self._show_fa_summary(season)

    def _handle_star_fa_event(self, player: Player, season: Season) -> None:
        """Commissioner can nudge or rig where a star free agent signs."""
        league = self.league
        sn     = season.number
        cfg    = league.cfg
        RIG_COST   = 25.0
        NUDGE_COST = 10.0
        RIG_LEG    = 0.08
        NUDGE_LEG  = 0.02

        # Build candidate destinations (teams with empty slots, excluding current team)
        candidates = [t for t in league.teams
                      if None in t.roster and t.team_id != player.team_id]
        if not candidates:
            return

        fa_avg_o, fa_avg_d = _avg_ratings(league.teams)

        # Score each destination by player motivation
        def dest_score(team: Team) -> float:
            win_score    = _rel_net(team.ortg, team.drtg, fa_avg_o, fa_avg_d)  # relative contention proxy
            market_score = team.franchise.draw_factor * team.franchise.effective_metro
            if player.motivation == MOT_WINNING:
                return 0.80 * win_score + 0.20 * market_score
            elif player.motivation == MOT_MARKET:
                return 0.20 * win_score + 0.80 * market_score
            else:  # loyalty — won't reach here normally, but handle gracefully
                return win_score + market_score

        scores = {t: max(0.01, dest_score(t)) for t in candidates}
        total  = sum(scores.values())
        probs  = {t: scores[t] / total for t in candidates}

        clear()
        header("STAR FREE AGENT", f"After Season {sn}")
        mot_c = GREEN if player.motivation == MOT_WINNING else (GOLD if player.motivation == MOT_MARKET else CYAN)
        tier_c = GOLD if player.peak_overall >= 18 else CYAN
        print(f"\n  {happiness_emoji(player.happiness)} {tier_c}{BOLD}{player.name}{RESET}  "
              f"{MUTED}{player.position} · Age {player.age} · "
              f"Ceiling {player.ceiling_tier}{RESET}\n"
              f"  ORtg {player.ortg_contrib:+.1f}  DRtg {player.drtg_contrib:+.1f}  "
              f"{player.trend}  Motivation: {mot_c}{player.motivation}{RESET}\n")

        print(f"  {'Destination':<28}  {'Market':>6}  {'Net':>5}  {'Odds':>5}  Notes")
        divider()
        dest_list = sorted(candidates, key=lambda t: -probs[t])
        for i, t in enumerate(dest_list, 1):
            pct  = probs[t] * 100
            net  = _rel_net(t.ortg, t.drtg, fa_avg_o, fa_avg_d)
            slot = next(i for i, s in enumerate(t.roster) if s is None)
            print(f"  {CYAN}[{i}]{RESET} {t.franchise_at(sn).name:<28}  "
                  f"{t.franchise.effective_metro:>6.1f}  {net:>+5.1f}  {pct:>4.0f}%  "
                  f"{MUTED}{league.teams[0].slot_label(slot)} slot open{RESET}")

        print(f"\n  {MUTED}Treasury: ${self._treasury:.0f}M  ·  "
              f"Legitimacy: {league.legitimacy:.0%}{RESET}\n")

        can_nudge = self._treasury >= NUDGE_COST
        can_rig   = self._treasury >= RIG_COST and league.legitimacy >= RIG_LEG + 0.01
        options  = []
        handlers = []
        for i, t in enumerate(dest_list[:3], 1):
            if can_nudge:
                options.append(f"Nudge → {t.franchise_at(sn).name:<24}  "
                                f"{MUTED}Cost: ${NUDGE_COST:.0f}M  Leg: -{NUDGE_LEG:.0%}{RESET}")
                handlers.append(("nudge", t))
            if can_rig:
                options.append(f"{RED}Rig{RESET}   → {t.franchise_at(sn).name:<24}  "
                                f"{MUTED}Cost: ${RIG_COST:.0f}M  Leg: -{RIG_LEG:.0%}{RESET}")
                handlers.append(("rig", t))
        options.append(f"{MUTED}No intervention — let it play out{RESET}")
        handlers.append(("none", None))

        choice   = choose(options, "Commissioner Action:", default=len(options) - 1)
        action, forced_team = handlers[choice]

        if action in ("nudge", "rig"):
            cost = NUDGE_COST if action == "nudge" else RIG_COST
            leg  = NUDGE_LEG  if action == "nudge" else RIG_LEG
            boost = 0.5 if action == "nudge" else 2.0
            self._treasury        -= cost
            league.legitimacy      = max(0.0, league.legitimacy - leg)
            scores[forced_team]   *= (1 + boost)
            total = sum(scores.values())
            probs = {t: scores[t] / total for t in candidates}

        # Sign the player
        dest = random.choices(list(probs.keys()), weights=list(probs.values()))[0]
        slot_idx = next(i for i, s in enumerate(dest.roster) if s is None)
        cl = league._new_contract_length(player.age)
        player.contract_length          = cl
        player.contract_years_remaining = cl
        player.team_id                  = dest.team_id
        player.seasons_with_team        = 0
        dest.roster[slot_idx]           = player
        if player in league.free_agent_pool:
            league.free_agent_pool.remove(player)

        dest_name = dest.franchise_at(sn).name
        if action == "none":
            print(f"\n  {GOLD}★{RESET} {happiness_emoji(player.happiness)} {player.name} signs with {BOLD}{dest_name}{RESET}  "
                  f"({cl}-year deal)")
        elif dest is forced_team:
            print(f"\n  {GREEN}✓ Intervention successful.{RESET} "
                  f"{happiness_emoji(player.happiness)} {player.name} signs with {BOLD}{dest_name}{RESET}  ({cl}-year deal)")
        else:
            print(f"\n  {RED}Intervention failed.{RESET} "
                  f"{happiness_emoji(player.happiness)} {player.name} signs with {BOLD}{dest_name}{RESET} anyway  ({cl}-year deal)")
        press_enter()

    def _handle_draft(self, season: Season) -> None:
        """Show draft prospects and let commissioner influence lottery order."""
        league = self.league
        sn     = season.number
        cfg    = league.cfg

        if not league.draft_pool:
            return

        # Default draft order: worst record first
        if league.seasons:
            standings = league.seasons[-1].regular_season_standings
            draft_order = list(reversed(standings))
            in_standings = set(standings)
            draft_order += [t for t in league.teams if t not in in_standings]
        else:
            draft_order = list(league.teams)

        # Only teams with empty slots actually pick
        picking_teams = [t for t in draft_order if None in t.roster]

        if not picking_teams:
            league.free_agent_pool.extend(league.draft_pool)
            league.draft_pool = []
            return

        clear()
        header("DRAFT", f"After Season {sn}")
        print(f"\n  {len(league.draft_pool)} prospects  ·  "
              f"{len(picking_teams)} team(s) with open slots\n")

        # Show prospects
        tier_colors = {TIER_ELITE: GOLD, TIER_HIGH: CYAN, TIER_MID: "", TIER_LOW: MUTED}
        print(f"  {'#':>2}  {'Name':<22} {'Pos':<6} {'Age':>3}  {'Ceiling':<7}  "
              f"{'ORtg':>5}  {'DRtg':>5}  {'Zone':<6}  Motivation")
        divider()
        for i, p in enumerate(league.draft_pool, 1):
            tc = tier_colors.get(p.ceiling_tier, "")
            print(f"  {i:>2}. {tc}{p.name:<22}{RESET} {p.position:<6} {p.age:>3}  "
                  f"{tc}{p.ceiling_tier:<7}{RESET}  "
                  f"{p.ortg_contrib:>+5.1f}  {p.drtg_contrib:>+5.1f}  "
                  f"{p.preferred_zone:<6}  {p.motivation}")

        # Show draft order
        print(f"\n  Draft order (worst record first):\n")
        for i, t in enumerate(picking_teams, 1):
            empty_slots = [t.slot_label(j) for j, s in enumerate(t.roster) if s is None]
            print(f"  {i:>2}. {t.franchise_at(sn).name:<28}  "
                  f"{MUTED}open: {', '.join(empty_slots)}{RESET}")

        # Lottery influence option
        print()
        if self._treasury >= 10.0:
            raw = prompt("Influence lottery? Enter team # to bump up (Enter to skip):")
            if raw.isdigit():
                val = int(raw) - 1
                if 0 <= val < len(picking_teams) and val > 0:
                    cost = 10.0
                    self._treasury -= cost
                    league.legitimacy = max(0.0, league.legitimacy - 0.02)
                    # Move team to front of draft order
                    bumped = picking_teams.pop(val)
                    picking_teams.insert(0, bumped)
                    print(f"  {GREEN}✓ {bumped.franchise_at(sn).name} moved to pick #1.  "
                          f"(-${cost:.0f}M, legitimacy -2%){RESET}")
        else:
            print(f"  {MUTED}(Need $10M to influence lottery){RESET}")

        press_enter("Press Enter to run the draft...")

        # Run draft picks
        print()
        prospects = list(league.draft_pool)
        signed: list[Player] = []
        for team in picking_teams:
            if not prospects:
                break
            for slot_idx, slot in enumerate(team.roster):
                if slot is None and prospects:
                    # Pick best available (by overall)
                    pick = max(prospects, key=lambda p: p.overall)
                    prospects.remove(pick)
                    cl = league._new_contract_length(pick.age)
                    pick.contract_length          = cl
                    pick.contract_years_remaining = cl
                    pick.team_id                  = team.team_id
                    team.roster[slot_idx]         = pick
                    signed.append(pick)
                    tc = tier_colors.get(pick.ceiling_tier, "")
                    print(f"  {team.franchise_at(sn).name:<28}  selects  "
                          f"{tc}{pick.name}{RESET}  "
                          f"{MUTED}({pick.position} · {pick.ceiling_tier} ceiling){RESET}")
                    break

        # Undrafted go to FA pool
        league.free_agent_pool.extend(prospects)
        league.draft_pool = []
        press_enter()

    def _show_fa_summary(self, season: Season) -> None:
        """Show available free agents after draft and auto-signing."""
        league = self.league
        sn     = season.number
        pool   = league.free_agent_pool
        if not pool:
            return

        clear()
        header("FREE AGENT POOL", f"After Season {sn}")
        print(f"\n  {len(pool)} players available\n")
        print(f"  {'Name':<22} {'Pos':<6} {'Age':>3}  {'ORtg':>5}  {'DRtg':>5}  "
              f"{'Zone':<6}  {'Mood':<4}  {'Popularity':<9}  Motivation")
        divider()
        for p in sorted(pool, key=lambda p: -p.overall):
            mot_c = (GREEN if p.motivation == MOT_WINNING
                     else GOLD if p.motivation == MOT_MARKET else CYAN)
            pop_c = GOLD if p.popularity >= 0.65 else (CYAN if p.popularity >= 0.40 else MUTED)
            print(f"  {p.name:<22} {p.position:<6} {p.age:>3}  "
                  f"{p.ortg_contrib:>+5.1f}  {p.drtg_contrib:>+5.1f}  "
                  f"{p.preferred_zone:<6}  {happiness_emoji(p.happiness):<4}"
                  f"  {pop_c}{popularity_tier(p.popularity):<9}{RESET}"
                  f"  {mot_c}{p.motivation}{RESET}")
        press_enter()

    # ── Commissioner's Desk (always-available proactive actions) ──────────────

    def _commissioner_desk(self, season: Season):
        """Always shown — proactive tools the commissioner can use each season."""
        rule_change_used = False
        showcase_used    = False
        invest_used      = False

        while True:
            league = self.league
            meta = league.league_meta
            lp   = league.league_popularity
            clear()
            header("COMMISSIONER'S DESK", f"After Season {season.number}")

            # Status bar
            treas_color = GREEN if self._treasury >= 75.0 else (GOLD if self._treasury >= 25.0 else RED)
            legit = league.legitimacy
            legit_color = GREEN if legit >= 0.8 else (GOLD if legit >= 0.5 else RED)
            print(f"\n  Popularity  {pop_bar(lp)}  ·  "
                  f"Era: {era_label(meta)}  ({meta:+.3f})")
            print(f"  Treasury    {treas_color}${self._treasury:.0f}M{RESET}  "
                  f"{MUTED}(+${self._last_revenue:.0f}M revenue this season){RESET}")
            print(f"  Legitimacy  {legit_color}{legit:.0%}{RESET}"
                  f"{MUTED}  — rises +2%/season, costs 8% per G7 intervention{RESET}")
            if league._talent_boost_seasons_left > 0:
                print(f"  Talent      {GREEN}investment active "
                      f"· {league._talent_boost_seasons_left} seasons left{RESET}")
            print()

            options  = []
            handlers = []

            if not rule_change_used:
                n_prev   = self._rule_changes_made
                leg_cost = 0.02 + 0.01 * min(6, n_prev)
                risk_c   = GREEN if n_prev < 3 else (GOLD if n_prev < 6 else RED)
                risk_lbl = "Low" if n_prev < 3 else ("Medium" if n_prev < 6 else "High")
                options.append(
                    f"Rule change      "
                    f"{MUTED}Leg:{RESET} {risk_c}-{leg_cost:.0%}    {RESET}"
                    f"{MUTED}Risk:{RESET} {risk_c}{risk_lbl:<7}{RESET}"
                    f"{MUTED}Reward:{RESET} {GOLD}Medium{RESET}"
                    + (f"  {MUTED}({n_prev} prior changes){RESET}" if n_prev > 0 else "")
                )
                handlers.append("rule_change")

            if not showcase_used:
                can_showcase = self._treasury >= 25.0
                budget_tag = "" if can_showcase else f"  {RED}(need $25M){RESET}"
                options.append(
                    f"Showcase event   "
                    f"{MUTED}Cost:{RESET} {RED}$25M     {RESET}"
                    f"{MUTED}Risk:{RESET} {GREEN}Low      {RESET}"
                    f"{MUTED}Reward:{RESET} {GOLD}Medium{RESET}"
                    f"{budget_tag}"
                )
                handlers.append("showcase" if can_showcase else None)

            if not invest_used and league._talent_boost_seasons_left == 0:
                can_invest = self._treasury >= 75.0
                budget_tag = "" if can_invest else f"  {RED}(need $75M){RESET}"
                options.append(
                    f"Invest in talent "
                    f"{MUTED}Cost:{RESET} {RED}$75M     {RESET}"
                    f"{MUTED}Risk:{RESET} {GREEN}Low      {RESET}"
                    f"{MUTED}Reward:{RESET} {GREEN}High{RESET}"
                    f"{budget_tag}"
                )
                handlers.append("invest" if can_invest else None)

            options.append(
                f"Format review    "
                f"{MUTED}Cost:{RESET} {GREEN}Free     {RESET}"
                f"{MUTED}Risk:{RESET} {GREEN}Low      {RESET}"
                f"{MUTED}Reward:{RESET} {MUTED}Varies{RESET}"
            )
            handlers.append("format")

            options.append(f"{MUTED}Continue{RESET}")
            handlers.append(None)

            idx = choose(options, default=len(options) - 1)
            action = handlers[idx]
            if action is None:
                # Either "Continue" or a budget-locked option was chosen — skip
                if idx == len(options) - 1:
                    break
                print(f"  {RED}Not enough budget for that action.{RESET}")
                press_enter()
            elif action == "rule_change":
                self._do_rule_change(season)
                rule_change_used = True
            elif action == "showcase":
                self._do_showcase_event(season)
                showcase_used = True
            elif action == "invest":
                self._do_invest_in_talent(season)
                invest_used = True
            elif action == "format":
                self._do_format_review(season)

    def _do_rule_change(self, season: Season):
        """Unified rule change — offered every season, cost scales with overuse."""
        league   = self.league
        cfg      = league.cfg
        sn       = season.number
        meta     = league.league_meta
        n_prev   = self._rule_changes_made
        champ    = season.champion

        # Cost scaling
        leg_cost   = 0.02 + 0.01 * min(6, n_prev)
        extreme    = abs(meta) > 0.10   # near the edge already

        # Fan pop effect: novelty early, weariness late
        if n_prev < 2:
            pop_effect = +0.008
            pop_label  = f"{GREEN}+pop (novelty){RESET}"
        elif n_prev < 6:
            pop_effect = 0.0
            pop_label  = f"{MUTED}neutral{RESET}"
        else:
            pop_effect = -0.006
            pop_label  = f"{RED}-pop (wary){RESET}"

        extreme_tag = (f"  {RED}⚠ extremes surcharge -2% leg{RESET}") if extreme else ""

        clear()
        header("RULE CHANGE", f"After Season {sn}")
        print(f"\n  Era: {era_desc(meta)}  ({meta:+.3f})")
        era_seasons = getattr(league, '_meta_extreme_seasons', 0)
        if era_seasons >= 3:
            print(f"  {MUTED}Prolonged era — {era_seasons} consecutive seasons{RESET}")
        print(f"\n  Legitimacy cost: {RED}-{leg_cost:.0%}{RESET}{extreme_tag}")
        print(f"  Fan reaction:    {pop_label}")
        if n_prev > 0:
            print(f"  {MUTED}({n_prev} rule change{'s' if n_prev!=1 else ''} already made — costs escalate){RESET}")
        print()

        PUSH = 0.03
        COUNTER_PUSH = 0.04

        def _projected(delta: float) -> str:
            new = max(-cfg.meta_max, min(cfg.meta_max, meta + delta))
            return f"{new:+.3f}  {era_label(new)}"

        options = [
            (f"{GREEN}Push offense{RESET}        "
             f"{MUTED}→ {_projected(+PUSH)}{RESET}",
             +PUSH),
            (f"{RED}Push defense{RESET}        "
             f"{MUTED}→ {_projected(-PUSH)}{RESET}",
             -PUSH),
            (f"{CYAN}Reset toward balance{RESET} "
             f"{MUTED}→ ~{_projected(-meta * 0.6)}{RESET}",
             None),   # special: partial reversion
        ]
        if champ:
            champ_style = "3pt-heavy" if champ.style_3pt > 0.25 else "interior"
            counter_sign = -1 if champ.style_3pt > 0.25 else +1
            options.append((
                f"{GOLD}Counter champion{RESET}    "
                f"{MUTED}→ {_projected(counter_sign * COUNTER_PUSH)}  "
                f"(push against {champ_style}){RESET}",
                counter_sign * COUNTER_PUSH,
            ))
        options.append((f"{MUTED}No change{RESET}", "skip"))

        choice = choose([o[0] for o in options], default=len(options) - 1)
        action = options[choice][1]

        if action == "skip":
            return

        old_meta = meta
        if action is None:
            # Reset toward balance
            league.league_meta = meta * 0.4 + random.gauss(0, cfg.meta_shock_spread)
        else:
            league.league_meta = max(-cfg.meta_max, min(cfg.meta_max, meta + action))

        # Apply costs
        total_leg = leg_cost + (0.02 if extreme else 0.0)
        league.legitimacy = max(0.0, league.legitimacy - total_leg)
        league.league_popularity = max(0.0, min(1.0,
                                        league.league_popularity + pop_effect))

        # Track and reset era counter
        self._rule_changes_made += 1
        league._meta_extreme_seasons = 0
        season.meta_shock = True

        print(f"\n  {GREEN}Rule change applied.{RESET}  "
              f"Meta: {old_meta:+.3f} → {league.league_meta:+.3f}  "
              f"{era_desc(league.league_meta)}")
        print(f"  Legitimacy: -{total_leg:.0%}  ·  "
              f"Fan reaction: {pop_label}")
        press_enter()

    def _do_showcase_event(self, season: Season):
        league = self.league
        sn = season.number
        clear()
        header("SHOWCASE EVENT", f"After Season {sn}")
        _show_risk_reward("High", "Low", "Medium",
                          "Host a marquee event to revitalise a market. Once per season.")

        # Build de-duplicated city list, sorted lowest engagement first
        city_map: dict = {}
        for team in league.teams:
            city_map.setdefault(team.franchise.city, []).append(team)
        cities = sorted(city_map.items(),
                        key=lambda x: sum(t.market_engagement for t in x[1]) / len(x[1]))

        print(f"  Markets ranked by need (lowest engagement first):\n")
        print(f"  {'#':>2}  {'City':<20} {'Teams':<26} Engagement")
        divider()
        for i, (city, teams) in enumerate(cities, 1):
            avg_eng   = sum(t.market_engagement for t in teams) / len(teams)
            nicknames = " & ".join(t.franchise.nickname for t in teams)
            grudge_tag = f"  {RED}grudge{RESET}" if city in league.market_grudges else ""
            print(f"  {i:>2}. {city:<20} {nicknames:<26} {pop_bar(avg_eng, 10)}{grudge_tag}")

        print()
        raw = prompt("Choose a market by number, or Enter to cancel:")
        if not raw.strip() or not raw.isdigit():
            print(f"  {MUTED}Showcase cancelled.{RESET}")
            press_enter()
            return
        idx = int(raw) - 1
        if not (0 <= idx < len(cities)):
            print(f"  {RED}Invalid choice.{RESET}")
            press_enter()
            return

        chosen_city, chosen_teams = cities[idx]
        for team in chosen_teams:
            team.market_engagement = min(1.0, team.market_engagement + 0.05)
        league.league_popularity = min(1.0, league.league_popularity + 0.01)
        self._treasury -= 25.0

        names = " & ".join(t.franchise_at(sn).name for t in chosen_teams)
        print(f"\n  {GREEN}Showcase hosted in {chosen_city}.{RESET}  {MUTED}{names}{RESET}")
        print(f"  Market engagement +5%  ·  League popularity +1%  ·  "
              f"Treasury: {GREEN}${self._treasury:.0f}M{RESET}")
        press_enter()

    def _do_invest_in_talent(self, season: Season):
        league = self.league
        sn = season.number
        cfg = league.cfg
        clear()
        header("INVEST IN TALENT", f"After Season {sn}")
        _show_risk_reward("High", "Low", "High",
                          "Fund scouting and development league-wide for 10 seasons.")

        boost = 1.0   # full quality shift for draft weights

        print(f"  Effect: draft class quality improves for 10 seasons.\n"
              f"          Elite prospects: ~3% → ~13%  ·  High: ~15% → ~27%\n"
              f"          Mid/Low picks become noticeably rarer.\n")
        print(f"  Cost: {RED}$75M{RESET}  ·  Treasury after: "
              f"{(GREEN if self._treasury-75 >= 0 else RED)}${self._treasury-75:.0f}M{RESET}\n")

        choice = choose([
            f"Approve the investment  {RED}($75M){RESET}",
            f"{MUTED}Skip{RESET}",
        ], default=1)

        if choice == 0:
            self._treasury -= 75.0
            league.start_talent_investment(boost, 10)
            print(f"\n  {GREEN}Investment approved.{RESET}  Elite/High prospects will rise for 10 seasons.")
            print(f"  Treasury: {GREEN}${self._treasury:.0f}M{RESET}")
            press_enter()

    def _do_format_review(self, season: Season):
        """Show current format health and let the commissioner adjust it (free action)."""
        league = self.league
        cfg    = league.cfg
        sn     = season.number
        n      = len(league.teams)

        while True:
            clear()
            header("FORMAT REVIEW", f"After Season {sn}  ·  {n} teams")
            _show_risk_reward("Free", "Low", "Varies",
                              "Adjust schedule, playoff bracket, or series length. Changes apply next season.")

            # Current format stats
            gpp  = cfg.games_per_pair if cfg.games_per_pair > 0 else _games_per_pair(n)
            gs   = gpp * (n - 1)
            po   = cfg.playoff_teams_override if cfg.playoff_teams_override > 0 else _playoff_count(n)
            sl   = cfg.series_length
            po_pct = po / n * 100

            print(f"  {BOLD}Current format{RESET}\n")
            print(f"  Games per matchup     {CYAN}{gpp}×{RESET}  →  {gs}-game regular season")
            print(f"  Playoff bracket       {CYAN}{po} teams{RESET}  ({po_pct:.0f}% qualify)")
            print(f"  Series length         {CYAN}Best-of-{sl}{RESET}")
            print()

            # Health signals
            if po_pct > 60:
                print(f"  {RED}⚠ {po_pct:.0f}% playoff rate is high — regular season wins feel cheap{RESET}")
            elif po_pct < 30:
                print(f"  {GREEN}✓ {po_pct:.0f}% playoff rate — regular season games matter{RESET}")
            else:
                print(f"  {MUTED}Playoff rate {po_pct:.0f}% — reasonable{RESET}")

            if gs < 20:
                print(f"  {RED}⚠ Only {gs} games — high variance, standings may not reflect quality{RESET}")
            elif gs > 70:
                print(f"  {MUTED}{gs} games — long season, lower per-game drama{RESET}")
            else:
                print(f"  {GREEN}✓ {gs}-game season — solid sample size{RESET}")
            print()

            idx = choose([
                f"Change games per matchup   {MUTED}(now {gpp}×){RESET}",
                f"Change playoff bracket     {MUTED}(now {po} teams){RESET}",
                f"Change series length       {MUTED}(now best-of-{sl}){RESET}",
                f"{MUTED}Done{RESET}",
            ], default=3)

            if idx == 3:
                break

            elif idx == 0:
                print(f"\n  Select new games-per-matchup  {MUTED}(auto for {n} teams = {_games_per_pair(n)}×){RESET}")
                opts = []
                for gval in [2, 4, 6, 8, 10]:
                    total = gval * (n - 1)
                    auto_tag = f"  {GOLD}← auto{RESET}" if gval == _games_per_pair(n) else ""
                    opts.append(f"{gval}×  {MUTED}({total}-game season){RESET}{auto_tag}")
                cur_idx = next((i for i, gv in enumerate([2, 4, 6, 8, 10]) if gv == gpp), 1)
                pick = choose(opts, default=cur_idx)
                cfg.games_per_pair = [2, 4, 6, 8, 10][pick]
                print(f"\n  {GREEN}Set:{RESET} {cfg.games_per_pair}× per matchup from next season.")
                press_enter()

            elif idx == 1:
                bracket_opts = [n2 for n2 in [4, 8, 16] if n2 <= n]
                if not bracket_opts:
                    print(f"  {RED}No valid bracket sizes for {n} teams.{RESET}")
                    press_enter()
                    continue
                auto_b = _playoff_count(n)
                labels = []
                for b in bracket_opts:
                    pct2 = b / n * 100
                    auto_tag = f"  {GOLD}← auto{RESET}" if b == auto_b else ""
                    labels.append(f"{b} teams  {MUTED}({pct2:.0f}% qualify){RESET}{auto_tag}")
                cur_idx = next((i for i, b in enumerate(bracket_opts) if b == po), 0)
                pick = choose(labels, default=cur_idx)
                cfg.playoff_teams_override = bracket_opts[pick]
                print(f"\n  {GREEN}Set:{RESET} {cfg.playoff_teams_override}-team playoff from next season.")
                press_enter()

            elif idx == 2:
                series_opts = [(5, "Best-of-5"), (7, "Best-of-7")]
                cur_idx = next((i for i, (sv, _) in enumerate(series_opts) if sv == sl), 1)
                labels = [f"{label}  {MUTED}(first to {(sv+1)//2} wins){RESET}" for sv, label in series_opts]
                pick = choose(labels, default=cur_idx)
                cfg.series_length = series_opts[pick][0]
                print(f"\n  {GREEN}Set:{RESET} {series_opts[pick][1]} from next season.")
                press_enter()

    def _handle_expansion_format_prompt(self, season: Season):
        """Offer a format review after an expansion wave fires."""
        league = self.league
        n = len(league.teams)
        clear()
        header("EXPANSION FORMAT CHECK", f"After Season {season.number}")
        print(f"""
  The league has grown to {BOLD}{n} teams{RESET}. Your current schedule and
  playoff format may need adjusting to stay balanced.

  {MUTED}Auto-recommended for {n} teams:{RESET}
    Games per matchup   {_games_per_pair(n)}×  →  {_games_per_pair(n) * (n-1)}-game season
    Playoff bracket     {_playoff_count(n)} teams  ({_playoff_count(n)/n*100:.0f}% qualify)
""")
        idx = choose([
            "Review & adjust format now",
            f"{MUTED}Keep current format{RESET}",
        ], default=1)
        if idx == 0:
            self._do_format_review(season)

    # ── Force relocation (pre-threshold intervention) ─────────────────────────

    def _handle_force_relocation(self, season: Season):
        """Offer early relocation for teams 5+ losing seasons, below natural threshold."""
        league = self.league
        sn     = season.number
        cfg    = league.cfg

        at_risk = [
            t for t in league.teams
            if t._consecutive_losing_seasons >= 5
            and t._consecutive_losing_seasons < cfg.relocation_threshold
            and sn >= t._protected_until
        ]
        if not at_risk:
            return

        clear()
        header("STRUGGLING FRANCHISES", f"After Season {sn}")
        _show_risk_reward("Medium", "High", "Medium",
                          "Force early relocation. Larger fan backlash; market holds a grudge.")
        print(f"  These franchises haven't hit the natural {cfg.relocation_threshold}-season "
              f"threshold yet,\n  but you can push the move now.\n")
        for t in at_risk:
            print(f"  {RED}{t.franchise_at(sn).name:<30}{RESET}  "
                  f"{MUTED}{t._consecutive_losing_seasons} losing seasons  "
                  f"pop {t.popularity:.0%}{RESET}")

        if self._treasury < 20.0:
            print(f"\n  {RED}Insufficient treasury ($20M per move, ${self._treasury:.0f}M available).{RESET}")
            press_enter()
            return

        choice = choose([
            "Review force-relocation options",
            f"{MUTED}Leave them alone{RESET}",
        ], default=1)
        if choice == 0:
            for team in at_risk:
                self._force_relocation_prompt(team, season)

    def _force_relocation_prompt(self, team, season: Season):
        league = self.league
        sn     = season.number
        cfg    = league.cfg
        fname  = team.franchise_at(sn).name

        city_count = Counter(t.franchise.city for t in league.teams)
        eligible   = sorted(
            [f for f in league.reserve_pool
             if not f.secondary
             and city_count.get(f.city, 0) == 0
             and sn >= league._relocation_cooldowns.get(f.city, 0)],
            key=lambda f: -f.effective_metro,
        )
        if not eligible:
            print(f"  {MUTED}No destinations available for {fname}.{RESET}")
            press_enter()
            return

        clear()
        header("FORCE RELOCATION", fname)
        budget_color = GREEN if self._treasury >= 20.0 else RED

        avg_o, avg_d = _avg_ratings(league.teams)
        net = _rel_net(team.ortg, team.drtg, avg_o, avg_d)
        net_c = GREEN if net > 0 else (RED if net < 0 else MUTED)

        print(f"""
  {RED}{BOLD}{fname}{RESET} has {team._consecutive_losing_seasons} consecutive losing seasons.
  Moving them before the natural threshold carries extra consequences.

  {RED}⚠  Popularity retained:{RESET} 40%  (vs 60% for a natural move)
  {RED}⚠  Market grudge:{RESET} {team.franchise.city} fans won't forgive easily
  {MUTED}Grudge decays ~8%/season, floors at 5% until a new team arrives.{RESET}
  Net rating: {net_c}{net:>+5.1f}{RESET} vs league avg  ·  Market: {team.franchise.city} ({team.franchise.effective_metro:.1f}  draw {team.franchise.draw_factor:.2f})
  Cost: {RED}$20M{RESET}  ·  Treasury after: {budget_color}${self._treasury-20:.0f}M{RESET}
""")

        # Roster context
        tier_colors = {TIER_ELITE: GOLD, TIER_HIGH: CYAN, TIER_MID: "", TIER_LOW: MUTED}
        players = [p for p in team.roster if p is not None]
        if players:
            print(f"  {'Slot':<9} {'Player':<22} {'Pos':<5} {'ORtg':>5}  {'DRtg':>5}  Mood")
            for idx, p in enumerate(team.roster):
                lbl = team.slot_label(idx)
                if p:
                    tc = tier_colors.get(p.ceiling_tier, "")
                    print(f"  {MUTED}{lbl:<9}{RESET}{happiness_emoji(p.happiness)} "
                          f"{tc}{p.name:<22}{RESET} {p.position:<5} "
                          f"{p.ortg_contrib:>+5.1f}  {p.drtg_contrib:>+5.1f}")
                else:
                    print(f"  {MUTED}{lbl:<9} — empty{RESET}")
        print()

        top = eligible[:8]
        dest_opts = []
        for f in top:
            if f.effective_metro < team.franchise.effective_metro * 0.5:
                size_note = f"  {RED}⚠ much smaller market{RESET}"
            elif f.effective_metro > team.franchise.effective_metro * 1.2:
                size_note = f"  {GREEN}↑ larger market{RESET}"
            else:
                size_note = ""
            grudge = league.market_grudges.get(f.city, 0.0)
            grudge_note = (f"  {RED}⚠ grudge {grudge:.0%} — fans still bitter{RESET}"
                           if grudge > 0 else "")
            dest_opts.append(
                f"{f.name:<28} {MUTED}mkt {f.effective_metro:.1f}  draw {f.draw_factor:.2f}{RESET}"
                f"{size_note}{grudge_note}"
            )
        dest_opts.append(f"{MUTED}Do not relocate {fname}{RESET}")

        rand_dest = random.randrange(len(top))
        print(f"\n  {MUTED}(Enter picks a random destination){RESET}")
        choice = choose(dest_opts, f"Force relocation destination for {fname}:", default=rand_dest)
        if choice >= len(top):
            print(f"  {MUTED}{fname} stays put.{RESET}")
            press_enter()
            return

        if self._treasury < 20.0:
            print(f"  {RED}Insufficient treasury ($20M required, ${self._treasury:.0f}M available).{RESET}")
            press_enter()
            return

        new_franchise  = top[choice]
        old_city       = team.franchise.city
        old_metro      = team.franchise.effective_metro
        league.reserve_pool.remove(new_franchise)
        old_franchise  = team.relocate(new_franchise, sn + 1)
        team.popularity *= (0.4 / 0.6)          # extra haircut: 40% total retention
        league.reserve_pool.append(old_franchise)
        league.relocation_log.append((
            sn, old_franchise.name, new_franchise.name,
            team._consecutive_losing_seasons, team._bottom2_in_streak, team.popularity,
        ))
        league.market_grudges[old_city]         = 1.0
        league._grudge_metro[old_city]          = old_metro
        league._relocation_cooldowns[old_city]  = sn + 4  # blocked for 3 seasons
        self._treasury -= 20.0

        print(f"\n  {GREEN}Relocation approved.{RESET} "
              f"{old_franchise.name} → {new_franchise.name} from Season {sn + 1}.")
        print(f"  {RED}{old_city} fans are furious.{RESET} Grudge score: 100%  ·  "
              f"Treasury: {GREEN}${self._treasury:.0f}M{RESET}")
        print(f"  {MUTED}No relocated team may enter {old_city} until Season {sn + 4}.{RESET}")
        press_enter()

    # ── Relocation (interactive) ──────────────────────────────────────────────

    def _handle_relocations(self, season: Season):
        """Replace automatic relocation roll with commissioner approval."""
        league = self.league
        league._grant_protections(season)
        standings = season.regular_season_standings
        bottom2 = set(standings[-2:])

        for team in list(league.teams):
            if season.reg_win_pct(team) < 0.5:
                team._consecutive_losing_seasons += 1
                if team in bottom2:
                    team._bottom2_in_streak += 1
            else:
                team._consecutive_losing_seasons = 0
                team._bottom2_in_streak = 0

            if team._consecutive_losing_seasons < league.cfg.relocation_threshold:
                continue
            if team._bottom2_in_streak < league.cfg.relocation_bottom2_required:
                continue
            if season.number < team._protected_until:
                continue

            city_count = Counter(t.franchise.city for t in league.teams)
            eligible = [
                f for f in league.reserve_pool
                if not f.secondary
                and city_count.get(f.city, 0) == 0
                and season.number >= league._relocation_cooldowns.get(f.city, 0)
            ]
            if not eligible:
                continue

            self._relocation_prompt(team, season, eligible)

    def _relocation_prompt(self, team, season, eligible):
        league = self.league
        sn     = season.number
        fname  = team.franchise_at(sn).name

        clear()
        header("RELOCATION REQUEST", f"Season {sn}")
        _show_risk_reward("Low", "Medium", "Medium",
                          "Natural relocation: 60% popularity retained. Market will hold a grudge.")

        avg_o, avg_d = _avg_ratings(league.teams)
        net = _rel_net(team.ortg, team.drtg, avg_o, avg_d)
        net_c = GREEN if net > 0 else (RED if net < 0 else MUTED)

        print(f"  {RED}{BOLD}{fname}{RESET} is struggling and has requested permission to relocate.\n"
              f"\n"
              f"  Consecutive losing seasons : {RED}{team._consecutive_losing_seasons}{RESET}\n"
              f"  Bottom-2 finishes in streak: {RED}{team._bottom2_in_streak}{RESET}\n"
              f"  Current popularity         : {pop_bar(team.popularity, 12)}\n"
              f"  Market                     : {team.franchise.city} "
              f"(market {team.franchise.effective_metro:.1f}  draw {team.franchise.draw_factor:.2f})\n"
              f"  Net rating                 : {net_c}{net:>+5.1f}{RESET}  vs league avg\n")

        # Roster context
        tier_colors = {TIER_ELITE: GOLD, TIER_HIGH: CYAN, TIER_MID: "", TIER_LOW: MUTED}
        players = [p for p in team.roster if p is not None]
        if players:
            print(f"  {'Slot':<9} {'Player':<22} {'Pos':<5} {'ORtg':>5}  {'DRtg':>5}  Mood")
            for idx, p in enumerate(team.roster):
                lbl = team.slot_label(idx)
                if p:
                    tc = tier_colors.get(p.ceiling_tier, "")
                    print(f"  {MUTED}{lbl:<9}{RESET}{happiness_emoji(p.happiness)} "
                          f"{tc}{p.name:<22}{RESET} {p.position:<5} "
                          f"{p.ortg_contrib:>+5.1f}  {p.drtg_contrib:>+5.1f}")
                else:
                    print(f"  {MUTED}{lbl:<9} — empty{RESET}")
        print()

        # No metro floor — any empty city is a valid destination
        dest_list = sorted(eligible, key=lambda f: -f.effective_metro)[:8]
        dest_opts = []
        for f in dest_list:
            if f.effective_metro < team.franchise.effective_metro * 0.5:
                size_note = f"  {RED}⚠ much smaller market{RESET}"
            elif f.effective_metro > team.franchise.effective_metro * 1.2:
                size_note = f"  {GREEN}↑ larger market{RESET}"
            else:
                size_note = ""
            grudge = league.market_grudges.get(f.city, 0.0)
            grudge_note = (f"  {RED}⚠ grudge {grudge:.0%} — fans still bitter{RESET}"
                           if grudge > 0 else "")
            dest_opts.append(
                f"{f.name:<28} {MUTED}mkt {f.effective_metro:.1f}  draw {f.draw_factor:.2f}{RESET}"
                f"{size_note}{grudge_note}"
            )
        # Surface any cities on relocation cooldown so commissioner knows why they're absent
        cooled = [
            f for f in league.reserve_pool
            if not f.secondary
            and Counter(t.franchise.city for t in league.teams).get(f.city, 0) == 0
            and sn < league._relocation_cooldowns.get(f.city, 0)
        ]
        if cooled:
            print(f"\n  {MUTED}On cooldown (recently vacated — not available for relocation):{RESET}")
            for f in sorted(cooled, key=lambda x: league._relocation_cooldowns[x.city]):
                avail = league._relocation_cooldowns[f.city]
                print(f"    {f.city:<18} available Season {avail}")

        rand_dest = random.randrange(len(dest_list))
        options = dest_opts + [
            f"{MUTED}Block relocation this season{RESET}",
            f"{MUTED}Grant 3-season protection{RESET}",
        ]
        print(f"\n  {MUTED}(Enter picks a random destination){RESET}")
        choice = choose(options, "Commissioner Decision:", default=rand_dest)

        if choice < len(dest_list):
            new_franchise  = dest_list[choice]
            old_city       = team.franchise.city
            old_metro      = team.franchise.effective_metro
            league.reserve_pool.remove(new_franchise)
            old_franchise  = team.relocate(new_franchise, sn + 1)
            league.reserve_pool.append(old_franchise)
            league.relocation_log.append((
                sn, old_franchise.name, new_franchise.name,
                team._consecutive_losing_seasons, team._bottom2_in_streak, team.popularity,
            ))
            league.market_grudges[old_city]         = 1.0
            league._grudge_metro[old_city]          = old_metro
            league._relocation_cooldowns[old_city]  = sn + 4  # blocked for 3 seasons
            print(f"\n  {GREEN}Approved.{RESET} {fname} → {new_franchise.name} from Season {sn+1}.")
            print(f"  {RED}{old_city} will hold a grudge.{RESET}  "
                  f"{MUTED}No relocated team may enter {old_city} until Season {sn+4}.{RESET}")
        elif choice == len(dest_list):
            print(f"\n  {MUTED}Relocation blocked for this season.{RESET}")
        else:
            team._protected_until = max(team._protected_until, sn + 3)
            print(f"\n  {CYAN}Protection granted.{RESET} {fname} safe until Season {sn+4}.")

        press_enter()

    # ── Expansion ─────────────────────────────────────────────────────────────

    def _handle_expansion_decision(self, season: Season):
        league = self.league
        sn = season.number
        cfg = league.cfg

        if len(league.teams) >= cfg.max_teams:
            return
        if sn - league._last_expansion_season < cfg.expansion_min_seasons:
            return
        if league.league_popularity >= cfg.expansion_trigger_popularity:
            league._expansion_eligible_seasons += 1
        else:
            league._expansion_eligible_seasons = 0
            return
        if league._expansion_eligible_seasons < cfg.expansion_consecutive_seasons:
            return

        candidates = league._expansion_candidates(sn)
        if not candidates:
            return

        boom = league.league_popularity >= cfg.expansion_boom_popularity
        max_wave = cfg.expansion_boom_teams if boom else cfg.expansion_teams_per_wave
        max_add = min(max_wave, cfg.max_teams - len(league.teams), len(candidates))

        clear()
        header("EXPANSION OPPORTUNITY", f"After Season {sn}")
        boom_str = f"  {GOLD}{BOLD}⚡ BOOM CONDITIONS — league is thriving!{RESET}\n" if boom else ""
        print(f"""
{boom_str}  League popularity is {GREEN}{league.league_popularity:.0%}{RESET} — strong enough to support expansion.
  You can add up to {BOLD}{max_add}{RESET} franchise(s) now, or wait until next season.

  Available markets  {MUTED}Market = relative size · Draw = climate/entertainment/marketability{RESET}
""")
        top_candidates = candidates[:8]
        print(f"  {'#':>4}  {'Franchise':<28} {'Market':>6}  {'Draw':>4}")
        divider()
        for i, f in enumerate(top_candidates, 1):
            metro = f.effective_metro

            if f.secondary:
                # Find incumbent and estimate post-split popularity
                incumbent = next((t for t in league.teams if t.franchise.city == f.city), None)
                inc_pop = incumbent.popularity if incumbent else 0.0
                new_pop  = inc_pop * 0.20
                kept_pop = inc_pop * 0.80
                split_note = (
                    f"  {RED}⚠ splits {f.city} market{RESET}  "
                    f"{MUTED}{incumbent.franchise_at(sn).name} {inc_pop:.0%}→{kept_pop:.0%} · "
                    f"new team starts ~{new_pop:.0%}{RESET}"
                )
                print(f"  {CYAN}[{i:2}]{RESET} {f.name:<28} {metro:>5.1f}  {f.draw_factor:>4.2f}{split_note}")
            else:
                print(f"  {CYAN}[{i:2}]{RESET} {f.name:<28} {metro:>5.1f}  {f.draw_factor:>4.2f}")

        print(f"\n  {CYAN}[ 0]{RESET} {MUTED}Skip expansion this season{RESET}")
        print(f"  {MUTED}Enter = auto-select {max_add} random market(s){RESET}")
        n_add  = 0
        chosen = []   # list of franchises

        while n_add < max_add:
            raw = prompt(f"Add a franchise? Enter number or 0 to stop [{n_add}/{max_add} selected]:")
            if raw == "":
                picks = random.sample([f for f in top_candidates if f not in chosen],
                                      min(max_add - n_add, len(top_candidates) - n_add))
                for pick in picks:
                    chosen.append(pick)
                    n_add += 1
                    print(f"  {GREEN}✓ {pick.name} added.{RESET}")
                break
            if not raw.isdigit():
                continue
            val = int(raw)
            if val == 0:
                break
            if 1 <= val <= len(top_candidates):
                pick = top_candidates[val - 1]
                if any(c is pick for c in chosen):
                    print(f"  {RED}Already selected.{RESET}")
                    continue
                chosen.append(pick)
                n_add += 1
                print(f"  {GREEN}✓ {pick.name} added.{RESET}")
            else:
                print(f"  {RED}Invalid.{RESET}")

        if chosen:
            joined = sn + 1
            for franchise in chosen:
                league._add_expansion_team(franchise, joined)
                league.expansion_log.append((sn, franchise.name, franchise.secondary))
            league.league_popularity = min(1.0, league.league_popularity + cfg.league_pop_expansion_boost)
            league._last_expansion_season = sn
            league._expansion_eligible_seasons = 0
            names = ", ".join(f.name for f in chosen)
            print(f"\n  {GREEN}Expansion approved!{RESET} {names} will join Season {joined}.")
            print(f"  League grows to {BOLD}{len(league.teams)}{RESET} teams.")
            press_enter()
            self._handle_expansion_format_prompt(season)
            return
        else:
            print(f"\n  {MUTED}Expansion deferred.{RESET}")

        press_enter()

    # ── Merger ────────────────────────────────────────────────────────────────

    def _handle_merger_decision(self, season: Season):
        league = self.league
        sn = season.number
        cfg = league.cfg

        if len(league.teams) >= cfg.max_teams: return
        if len(league.teams) < cfg.merger_min_teams: return
        if len(league.teams) >= cfg.merger_max_teams: return
        if sn < cfg.merger_min_season: return
        if sn - league._last_merger_season < cfg.merger_cooldown_seasons: return

        if league.league_popularity < cfg.merger_trigger_popularity:
            league._merger_eligible_seasons += 1
        else:
            league._merger_eligible_seasons = 0
            return
        if league._merger_eligible_seasons < cfg.merger_consecutive_seasons:
            return

        candidates = league._merger_candidates()
        if not candidates:
            return

        max_add = min(cfg.merger_size_max, cfg.max_teams - len(league.teams), len(candidates))
        suggested = random.randint(cfg.merger_size_min, max_add)

        clear()
        header("RIVAL LEAGUE MERGER OFFER", f"After Season {sn}")
        print(f"""
  {RED}League popularity has fallen to {league.league_popularity:.0%} — a rival league
  has approached about a merger to consolidate the sport.{RESET}

  Absorbing their teams would immediately boost popularity
  and inject competitive balance into the league.

  {BOLD}Proposed absorption: {suggested} franchises{RESET}
  Top candidates:
""")
        top = candidates[:suggested]
        for f in top:
            sec = f"  {MUTED}(shares {f.city}){RESET}" if f.secondary else ""
            print(f"  • {f.name:<28} {MUTED}{f.city}, {f.effective_metro:.0f}{RESET}{sec}")

        choice = choose([
            f"Accept merger ({suggested} teams absorbed)",
            "Reject merger offer",
        ], "Commissioner Decision:")

        if choice == 0:
            joined = sn + 1
            for franchise in top:
                league._add_merger_team(franchise, joined)
                league.merger_log.append((sn, franchise.name, franchise.secondary))
            league.league_popularity = min(1.0, league.league_popularity + cfg.merger_league_pop_boost)
            league._last_merger_season = sn
            league._merger_eligible_seasons = 0
            print(f"\n  {GREEN}Merger accepted.{RESET} {suggested} franchises join Season {joined}.")
            print(f"  League grows to {BOLD}{len(league.teams)}{RESET} teams.")
        else:
            print(f"\n  {MUTED}Merger rejected.{RESET}")

        press_enter()


    # ── Farewell ──────────────────────────────────────────────────────────────

    def _show_farewell(self):
        clear()
        league = self.league
        header(self.league_name, f"Commissioner tenure: {self.season_num} seasons")
        if league.seasons:
            champs = Counter(s.champion.franchise_at(s.number).name for s in league.seasons)
            top_champ, top_wins = champs.most_common(1)[0]
            print(f"""
  Final league size  : {len(league.teams)} teams
  League popularity  : {pop_bar(league.league_popularity)}
  Total relocations  : {len(league.relocation_log)}
  Expansion waves    : {len({sn for sn, *_ in league.expansion_log})}
  Merger waves       : {len({sn for sn, *_ in league.merger_log})}
  Most championships : {GOLD}{top_champ}{RESET}  ({top_wins})
""")
        print(f"  {MUTED}Thanks for playing.{RESET}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    CommissionerGame().run()
