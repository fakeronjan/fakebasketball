#!/usr/bin/env python3
"""Commissioner Mode — interactive season-by-season league management."""

import os
import random
from collections import Counter

from config import Config
from franchises import ALL_FRANCHISES, Franchise
from game import GameResult, _eff, _sim_possession, _possessions, _HOME_PATTERNS
from league import League
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

# Absolute quality anchors for the 0–100 strength scale.
# These match the Wide Open preset's floor/ceiling so all presets
# display on the same consistent scale during both setup and gameplay.
_STR_QUALITY_MIN = 2.50
_STR_QUALITY_MAX = 3.70


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

def _team_strength(q: float, cfg=None) -> int:
    """Map quality onto a fixed 0–100 scale (anchored to Wide Open preset bounds).

    Using absolute anchors means a strength-67 team in Tight Parity is genuinely
    below a strength-80 team in Wide Open — the number means the same everywhere.
    """
    r = _STR_QUALITY_MAX - _STR_QUALITY_MIN
    return max(0, min(100, round((q - _STR_QUALITY_MIN) / r * 100)))

def _lean_label(identity: float) -> str:
    """Colored qualitative lean indicator. GREEN = offensive, RED = defensive."""
    if identity > 0.6:
        return f"{GREEN}▲ OFF{RESET}"
    if identity < 0.4:
        return f"{RED}▼ DEF{RESET}"
    return f"{MUTED}= BAL{RESET}"

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
        self._rule_change_cooldown = 0   # seasons remaining before next manual shock allowed
        self._last_pop_signals: dict = {}  # signal breakdown from most recent season
        self._treasury: float = 0.0       # accumulated commissioner funds (carry-over)
        self._last_revenue: float = 0.0   # revenue earned most recent season

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup(self):
        clear()
        header("COMMISSIONER MODE", "Build and manage your basketball league")
        print(f"""
  You are the Commissioner. You decide when the league expands,
  whether struggling franchises can relocate, and when to shake
  up the rules. Your goal: grow the league, keep the fans happy,
  and avoid dynasties that kill interest.
""")
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
            initial_quality_mode=quality_mode,
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

  {MUTED}Market = relative metro size · Growth = talent pull direction{RESET}
  {MUTED}★ = co-tenant available in this market{RESET}
""")
            print(f"  {'#':>2}  {'Team':<28} {'Market':>6}  Growth")
            divider()
            for i, f in enumerate(all_primaries, 1):
                metro = f.effective_metro
                if metro >= 10:   growth = f"{GREEN}Strong ▲{RESET}"
                elif metro >= 5:  growth = f"{CYAN}Moderate{RESET}"
                elif metro >= 3:  growth = f"{MUTED}Modest{RESET}"
                else:             growth = f"{RED}Weak ▼{RESET}"
                cotenant_tag = f"  {GOLD}★{RESET}" if f.city in all_secondaries else ""
                print(f"  {i:>2}. {f.name:<28} {metro:>6.1f}  {growth}{cotenant_tag}")

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

        # Preset definitions: (label, description, min_q, max_q)
        PRESETS = [
            (
                "Tight Parity",
                "Any team can compete. Dynasties are rare; upsets are common.",
                2.85, 3.30,
            ),
            (
                "Balanced",
                "Elite teams pull away, but underdogs still make noise.",
                2.70, 3.50,
            ),
            (
                "Wide Open",
                "Clear pecking order. Dynasties form; rebuilds take years.",
                2.50, 3.70,
            ),
        ]

        print(f"""
  The variance range controls how different the best and worst
  teams are. A wider range means bigger blowouts, clearer
  dynasties, and longer rebuilds for struggling franchises.

  Teams are displayed on a 0–100 strength scale during play.
  This shows what range your league will occupy on that scale.
""")
        divider()
        for name, desc, lo, hi in PRESETS:
            lo_s = _team_strength(lo)
            hi_s = _team_strength(hi)
            span = hi_s - lo_s
            color = CYAN if span < 45 else (GOLD if span < 75 else RED)
            bar_start = lo_s // 5
            bar_span  = round(span / 5)
            bar = " " * bar_start + "█" * bar_span
            print(f"  {name:<18} {color}{lo_s:>3}–{hi_s:<3}{RESET}  "
                  f"[{MUTED}{bar:<20}{RESET}]  {MUTED}{desc}{RESET}")
        print()

        options = [f"{name}  {MUTED}(strength {_team_strength(lo)}–{_team_strength(hi)}){RESET}"
                   for name, _, lo, hi in PRESETS]
        choice = choose(options, "Select a variance preset:", default=1)

        name, desc, min_q, max_q = PRESETS[choice]
        q_range = max_q - min_q

        # Derived values that all scale with the range
        sigma       = round(0.233 * q_range, 3)   # ~23% of range
        q_delta     = round(0.100 * q_range, 3)   # 10% of range per win/loss
        merger_lo   = round(min_q + 0.333 * q_range, 3)
        merger_hi   = round(min_q + 0.833 * q_range, 3)

        print(f"\n  {GREEN}Set:{RESET} {name}  "
              f"team strength range {_team_strength(min_q)}–{_team_strength(max_q)}")
        press_enter()

        return dict(
            min_quality=min_q,
            max_quality=max_q,
            offseason_sigma=sigma,
            quality_delta=q_delta,
            merger_quality_min=merger_lo,
            merger_quality_max=merger_hi,
        )

    def _setup_quality_spread(self) -> str:
        """Let player choose how founding-team talent is distributed. Returns mode string."""
        clear()
        header("FOUNDING TALENT DISTRIBUTION", "How is talent spread across your starting teams?")
        print(f"""
  This controls whether your founding teams start on equal footing
  or whether some arrive as powerhouses while others are rebuilding
  from day one.
""")
        MODES = [
            ("uniform",       "Equal footing",
             "All teams start at the same quality. Pure parity from tip-off."),
            ("moderate",      "Natural spread",
             "Random talent across the range. Some lucky rosters, some thin ones."),
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
        clear()
        header(self.league_name, "Founding Franchises")
        print(f"""
  {BOLD}Column key:{RESET}
    {CYAN}Fan Base{RESET}  Market engagement × city size (millions of engaged fans)
    {CYAN}STR{RESET}       Team strength 0–100 at tip-off
    {CYAN}LEAN{RESET}      Play style  {GREEN}▲ OFF{RESET} = offensive  {RED}▼ DEF{RESET} = defensive  {MUTED}= BAL{RESET} = balanced
""")
        teams = self.league.teams
        max_fb = max(_fan_base(t) for t in teams)
        teams_sorted = sorted(teams, key=lambda t: -_fan_base(t))
        print(f"  {'Team':<30}  {'Fan Base':<22}  STR  LEAN")
        divider()
        for t in teams_sorted:
            fb      = _fan_base(t)
            fb_str  = _fan_base_bar(fb, max_fb, 12)
            str_val = _team_strength(t.quality)
            lean    = _lean_label(t.identity)
            name_padded = f"{t.name:<30}"
            print(f"  {BOLD}{name_padded}{RESET}  {fb_str}  {str_val:>3}  {lean}")

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
        league._offseason_adjustments(season)
        self._handle_relocations(season)
        league._decay_grudges()
        league._evolve_popularity(season)
        league._evolve_market_engagements(season)
        self._last_pop_signals = league._evolve_league_popularity(season)
        league._evolve_meta()
        season._popularity        = {t: t.popularity for t in league.teams}
        season._market_engagement = {t: t.market_engagement for t in league.teams}
        season._league_popularity = league.league_popularity
        if self._rule_change_cooldown > 0:
            self._rule_change_cooldown -= 1
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

        print(f"\n  {BOLD}{'#':>2}  {'Team':<28} {'Record':<13} {'STR':>3}  LEAN   "
              f"{'PS/G':>5}  {'PA/G':>5}  {'Diff':>5}{RESET}")
        divider()
        for i, team in enumerate(standings):
            rank = i + 1
            rw, rl = season.reg_wins(team), season.reg_losses(team)
            fname = team.franchise_at(sn).name
            q, ident = season._start_ratings.get(team, (team.quality, team.identity))
            str_val  = _team_strength(q)
            lean_str = _lean_label(ident)
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
            print(f"  {rank:>2}. {name_str} {record:<13} {str_val:>3}  {lean_str}  "
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

        while True:
            clear()
            header(f"PLAYOFFS  —  {rname}", f"Season {sn}")
            legit = league.legitimacy
            legit_color = GREEN if legit >= 0.8 else (GOLD if legit >= 0.5 else RED)
            print(f"\n  Legitimacy: {legit_color}{legit:.0%}{RESET}"
                  + (f"  {MUTED}({n_done} intervention{'s' if n_done!=1 else ''} this season){RESET}"
                     if n_done > 0 else ""))

            # Show matchups
            print(f"\n  {'#':>2}  {'Seed 1':<26}  {'Seed 2':<26}  {'STR':>3}v{'':<3}  Status")
            divider()
            for i, (s1, s2) in enumerate(matchups, 1):
                q1 = season._start_ratings.get(s1, (s1.quality, s1.identity))[0]
                q2 = season._start_ratings.get(s2, (s2.quality, s2.identity))[0]
                s1n = s1.franchise_at(sn).name[:24]
                s2n = s2.franchise_at(sn).name[:24]
                str_tag = f"{_team_strength(q1):>3}v{_team_strength(q2):<3}"
                if (s1, s2) in bonuses:
                    fav, _ = bonuses[(s1, s2)]
                    btype  = "RIG" if _ >= RIG_BONUS else "nudge"
                    b_col  = RED if btype == "RIG" else GOLD
                    status = f"{b_col}★ {btype} → {fav.franchise_at(sn).name[:16]}{RESET}"
                else:
                    status = f"{MUTED}—{RESET}"
                print(f"  {i:>2}. {s1n:<26}  {s2n:<26}  {str_tag}  {status}")

            print()
            raw = prompt("Intervene in a series? Enter series # (or Enter to play):")
            if raw == "":
                break
            if not raw.isdigit() or not (1 <= int(raw) <= len(matchups)):
                continue

            idx = int(raw) - 1
            s1, s2 = matchups[idx]

            # Pick favored team
            clear()
            header(f"INTERVENE  —  {rname}", f"Season {sn}")
            q1, id1 = season._start_ratings.get(s1, (s1.quality, s1.identity))
            q2, id2 = season._start_ratings.get(s2, (s2.quality, s2.identity))
            fb1 = _fan_base(s1);  fb2 = _fan_base(s2)

            print(f"\n  {'':4}  {'Team':<28}  {'STR':>4}  {'LEAN':<5}  {'Fan Base':>9}")
            divider()
            print(f"  {CYAN}[1]{RESET}  {s1.franchise_at(sn).name:<28}  {_team_strength(q1):>4}"
                  f"  {_lean_label(id1)}  {fb1:>7.1f}M")
            print(f"  {CYAN}[2]{RESET}  {s2.franchise_at(sn).name:<28}  {_team_strength(q2):>4}"
                  f"  {_lean_label(id2)}  {fb2:>7.1f}M")
            print()

            # Compounding cost display
            mult   = 1.0 + 0.5 * n_done
            n_cost = NUDGE_BASE * mult
            r_cost = RIG_BASE   * mult
            legit_after_n = max(0.0, legit - n_cost)
            legit_after_r = max(0.0, legit - r_cost)
            print(f"  {MUTED}Intervention #{n_done+1} this season  —  cost multiplier {mult:.1f}×{RESET}")
            print(f"  {GOLD}Nudge{RESET}  small edge (+{NUDGE_BONUS:.0%} quality)  "
                  f"{RED}−{n_cost:.0%} legitimacy{RESET}  → {legit_after_n:.0%}")
            print(f"  {RED}Rig  {RESET}  strong edge (+{RIG_BONUS:.0%} quality)  "
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
                [f"{GOLD}Nudge{RESET}  +{NUDGE_BONUS:.0%} quality  {RED}−{n_cost:.0%} legit{RESET}",
                 f"{RED}Rig  {RESET}  +{RIG_BONUS:.0%} quality  {RED}−{r_cost:.0%} legit{RESET}",
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
        """Play a full series, applying a quality bonus to favored team every game."""
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
            ha = cfg.playoff_home_advantage
            home_bonus = ha + cfg.playoff_seed_bonus * (1 if home is seed1 else 0)
            away_bonus = cfg.playoff_seed_bonus * (1 if away is seed1 else 0)
            if favored is not None:
                if home is favored:
                    home_bonus += bonus_val
                else:
                    away_bonus += bonus_val

            eff_home = _eff(home, away, cfg, bonus=home_bonus)
            eff_away = _eff(away, home, cfg, bonus=away_bonus)
            poss = _possessions(cfg, league.league_meta)

            home_score = sum(_sim_possession(eff_home) for _ in range(poss))
            away_score = sum(_sim_possession(eff_away) for _ in range(poss))
            while home_score == away_score:
                home_score += _sim_possession(eff_home)
                away_score += _sim_possession(eff_away)

            result = GameResult(home, away, home_score, away_score)
            result.winner.quality = min(result.winner.quality + cfg.quality_delta, cfg.max_quality)
            result.loser.quality  = max(result.loser.quality  - cfg.quality_delta, cfg.min_quality)
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

        # Standings
        print(f"\n  {'TEAM':<30} {'RECORD':<14} {'STR':>3}  LEAN   PLAYOFF")
        divider()
        standings = season.regular_season_standings
        n_playoff = season.playoff_teams
        playoff_result = self._playoff_results(season)

        for i, team in enumerate(standings):
            rank = i + 1
            rw, rl = season.reg_wins(team), season.reg_losses(team)
            fname = team.franchise_at(sn).name
            result = playoff_result.get(team, "")
            q, ident = season._start_ratings.get(team, (team.quality, team.identity))
            str_val  = _team_strength(q)
            lean_str = _lean_label(ident)
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
            print(f"  {rank:>2}. {name_str}  {record:<14} {str_val:>3}  {lean_str}  {seed_str} {result_str}")

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
                f"Team History     {MUTED}full record for any franchise{RESET}",
                f"Market Map       {MUTED}engagement, popularity & grudges by city{RESET}",
                f"Event Log        {MUTED}expansions, mergers & relocations{RESET}",
                f"All-Time Records {MUTED}championships, streaks, best & worst seasons{RESET}",
                f"Rivalries        {MUTED}head-to-head matchup history{RESET}",
                f"Playoff Analysis {MUTED}seed advantage & series length trends{RESET}",
                f"{MUTED}Back{RESET}",
            ], default=7)
            if   idx == 0: self._show_league_history(season)
            elif idx == 1: self._show_team_history(season)
            elif idx == 2: self._show_market_map(season)
            elif idx == 3: self._show_event_log(season)
            elif idx == 4: self._show_alltime_records(season)
            elif idx == 5: self._show_rivalries(season)
            elif idx == 6: self._show_playoff_analysis(season)
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

    def _build_city_history(self) -> dict:
        """Build city_data: {city: [(season, team), ...]} keyed by city name.

        History belongs to the city, not the team object. If a team moves from
        Chicago to Boston, Chicago retains its history; Boston gets a new entry
        only from the season the team arrives. Expansion back to Chicago starts
        a fresh Chicago chapter.
        """
        city_data: dict = {}   # city → list of (season, team)
        for s in self.league.seasons:
            for team in s.teams:
                city = team.franchise_at(s.number).city
                city_data.setdefault(city, []).append((s, team))
        return city_data

    def _show_team_history(self, season: Season):
        """City-level history selector."""
        league = self.league
        city_data = self._build_city_history()

        # Sort cities: active first (by fan base), then inactive alphabetically
        active_cities = {t.franchise.city for t in league.teams}
        active = sorted(
            [c for c in city_data if c in active_cities],
            key=lambda c: -sum(
                _fan_base(t) for t in league.teams if t.franchise.city == c
            ),
        )
        inactive = sorted(c for c in city_data if c not in active_cities)
        city_list = active + inactive

        while True:
            clear()
            header("CITY HISTORY", "Select a city")
            print(f"\n  {'#':>3}  {'City':<22} {'Seasons':>8}  Status")
            divider()
            for i, city in enumerate(city_list, 1):
                entries = city_data[city]
                n_seasons = len(entries)
                if city in active_cities:
                    cur_teams = [t for t in league.teams if t.franchise.city == city]
                    names = " / ".join(t.franchise.nickname for t in cur_teams)
                    status = f"{GREEN}{names}{RESET}"
                else:
                    status = f"{MUTED}relocated / disbanded{RESET}"
                print(f"  {i:>3}. {city:<22} {n_seasons:>8}  {status}")
            print(f"\n  {CYAN}[0]{RESET} {MUTED}Back{RESET}")

            raw = prompt("City number (Enter to go back):")
            if raw == "":
                break
            if not raw.isdigit():
                continue
            val = int(raw)
            if val == 0:
                break
            if 1 <= val <= len(city_list):
                self._show_city_detail(city_list[val - 1], city_data[city_list[val - 1]])

    def _show_city_detail(self, city: str, entries: list):
        """Season-by-season history for one city."""
        PAGE = 20
        page = max(0, len(entries) - PAGE)

        while True:
            clear()
            # Championships for this city
            champ_count = sum(
                1 for s, t in entries if s.champion is t
            )
            champ_str = f"  {GOLD}{champ_count} title{'s' if champ_count != 1 else ''}{RESET}" if champ_count else ""
            header("CITY HISTORY", f"{city}{champ_str}")

            # Show any franchise transitions for this city
            name_changes = []
            prev_name = None
            for s, t in entries:
                fname = t.franchise_at(s.number).name
                if fname != prev_name:
                    name_changes.append(f"{MUTED}S{s.number}{RESET} {fname}")
                    prev_name = fname
            if len(name_changes) > 1:
                print(f"\n  Franchise history: {' → '.join(name_changes)}")

            print(f"\n  {'S':>3}  {'Franchise':<22} {'Record':<14} {'Pos':>4}  "
                  f"{'Result':<18}  {'PS/G':>5}  {'PA/G':>5}  {'Diff':>5}  {'Fan Base':>8}")
            divider()

            chunk = entries[page: page + PAGE]
            for s, team in chunk:
                fname = team.franchise_at(s.number).name[:21]
                w    = s.reg_wins(team)
                lo   = s.reg_losses(team)
                pos  = s.regular_season_standings.index(team) + 1
                n    = len(s.teams)
                pos_str = f"{pos}/{n}"
                result  = self._playoff_result_label(team, s)
                eng  = (s._market_engagement.get(team, team.market_engagement)
                        if hasattr(s, '_market_engagement') else team.market_engagement)
                metro = team.franchise_at(s.number).effective_metro
                fb   = eng * metro
                ppg  = s.team_ppg(team)
                papg = s.team_papg(team)
                diff = ppg - papg
                diff_c = GREEN if diff > 0 else (RED if diff < 0 else MUTED)
                record = _wl(w, lo)
                result_padded = f"{result:<18}"
                print(f"  {s.number:>3}  {fname:<22} {record:<14} {pos_str:>4}  "
                      f"{result_padded}  {ppg:>5.1f}  {papg:>5.1f}  "
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
            played_sn[t] = sorted(s.number for s in seasons if t in s.teams)
            won_sn[t]    = {s.number for s in seasons if s.champion is t}
            po_sn[t]     = {s.number for s in seasons
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
        self._commissioner_desk(season)
        self._handle_force_relocation(season)
        self._handle_expansion_decision(season)
        self._handle_merger_decision(season)
        self._handle_rule_change_offer(season)

    # ── Commissioner's Desk (always-available proactive actions) ──────────────

    def _commissioner_desk(self, season: Season):
        """Always shown — proactive tools the commissioner can use each season."""
        nudge_used      = False
        showcase_used   = False
        invest_used     = False

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

            if not nudge_used:
                options.append(
                    f"Meta nudge       "
                    f"{MUTED}Cost:{RESET} {GREEN}Free     {RESET}"
                    f"{MUTED}Risk:{RESET} {GREEN}Low      {RESET}"
                    f"{MUTED}Reward:{RESET} {MUTED}Low{RESET}"
                )
                handlers.append("nudge")

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
            elif action == "nudge":
                self._do_meta_nudge(season)
                nudge_used = True
            elif action == "showcase":
                self._do_showcase_event(season)
                showcase_used = True
            elif action == "invest":
                self._do_invest_in_talent(season)
                invest_used = True
            elif action == "format":
                self._do_format_review(season)

    def _do_meta_nudge(self, season: Season):
        league = self.league
        meta = league.league_meta
        clear()
        header("META NUDGE", f"After Season {season.number}")
        _show_risk_reward("Free", "Low", "Low",
                          "Issue an officiating memo that nudges play style. Once per season.")
        print(f"  Current meta: {meta:+.3f}  {era_desc(meta)}\n")
        opts = [
            f"{GREEN}Push toward more offense{RESET}  {MUTED}→ {min(league.cfg.meta_max, meta+0.02):+.3f}{RESET}",
            f"{RED}Push toward more defense{RESET}  {MUTED}→ {max(-league.cfg.meta_max, meta-0.02):+.3f}{RESET}",
            f"{MUTED}Skip{RESET}",
        ]
        choice = choose(opts, default=2)
        if choice == 0:
            league.league_meta = min(league.cfg.meta_max, meta + 0.02)
            print(f"\n  {GREEN}Nudge applied.{RESET}  {meta:+.3f} → {league.league_meta:+.3f}")
            press_enter()
        elif choice == 1:
            league.league_meta = max(-league.cfg.meta_max, meta - 0.02)
            print(f"\n  {GREEN}Nudge applied.{RESET}  {meta:+.3f} → {league.league_meta:+.3f}")
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

        q_range = cfg.max_quality - cfg.min_quality
        boost   = round(0.04 * q_range, 3)

        print(f"  Effect: non-playoff teams gain a +{boost:.3f} quality mean bonus each")
        print(f"          offseason for 10 seasons — raising the league's talent floor.\n")
        print(f"  Cost: {RED}$75M{RESET}  ·  Treasury after: "
              f"{(GREEN if self._treasury-75 >= 0 else RED)}${self._treasury-75:.0f}M{RESET}\n")

        choice = choose([
            f"Approve the investment  {RED}($75M){RESET}",
            f"{MUTED}Skip{RESET}",
        ], default=1)

        if choice == 0:
            self._treasury -= 75.0
            league.start_talent_investment(boost, 10)
            print(f"\n  {GREEN}Investment approved.{RESET}  Talent floor rising for 10 seasons.")
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
        print(f"""
  {RED}{BOLD}{fname}{RESET} has {team._consecutive_losing_seasons} consecutive losing seasons.
  Moving them before the natural threshold carries extra consequences.

  {RED}⚠  Popularity retained:{RESET} 40%  (vs 60% for a natural move)
  {RED}⚠  Market grudge:{RESET} {team.franchise.city} fans won't forgive easily
  {MUTED}Grudge decays ~8%/season, floors at 5% until a new team arrives.{RESET}
  Cost: {RED}$20M{RESET}  ·  Treasury after: {budget_color}${self._treasury-20:.0f}M{RESET}
""")
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
                f"{f.name:<28} {MUTED}market {f.effective_metro:.1f}{RESET}{size_note}{grudge_note}"
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
        print(f"  {RED}{BOLD}{fname}{RESET} is struggling and has requested permission to relocate.\n"
              f"\n"
              f"  Consecutive losing seasons : {RED}{team._consecutive_losing_seasons}{RESET}\n"
              f"  Bottom-2 finishes in streak: {RED}{team._bottom2_in_streak}{RESET}\n"
              f"  Current popularity         : {pop_bar(team.popularity, 12)}\n"
              f"  Market                     : {team.franchise.city} "
              f"(market {team.franchise.effective_metro:.1f})\n")

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
                f"{f.name:<28} {MUTED}market {f.effective_metro:.1f}{RESET}{size_note}{grudge_note}"
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

  Available markets  {MUTED}Market = relative size · Growth = talent pull{RESET}
""")
        top_candidates = candidates[:8]
        for i, f in enumerate(top_candidates, 1):
            metro = f.effective_metro
            if metro >= 10:   growth = f"{GREEN}Strong ▲{RESET}"
            elif metro >= 5:  growth = f"{CYAN}Moderate{RESET}"
            elif metro >= 3:  growth = f"{MUTED}Modest{RESET}"
            else:             growth = f"{RED}Weak ▼{RESET}"

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
                print(f"  {CYAN}[{i:2}]{RESET} {f.name:<28} {metro:>5.1f}  {growth}{split_note}")
            else:
                print(f"  {CYAN}[{i:2}]{RESET} {f.name:<28} {metro:>5.1f}  {growth}")

        print(f"\n  {CYAN}[ 0]{RESET} {MUTED}Skip expansion this season{RESET}")
        n_add  = 0
        chosen = []   # list of (franchise, starting_quality)

        while n_add < max_add:
            raw = prompt(f"Add a franchise? Enter number or 0 to stop [{n_add}/{max_add} selected]:")
            if not raw.isdigit():
                continue
            val = int(raw)
            if val == 0:
                break
            if 1 <= val <= len(top_candidates):
                pick = top_candidates[val - 1]
                if any(c[0] is pick for c in chosen):
                    print(f"  {RED}Already selected.{RESET}")
                    continue
                # Quality tier choice — strong entry scales with configured range
                q_range = cfg.max_quality - cfg.min_quality
                strong_q = cfg.min_quality + round(0.333 * q_range, 2)
                tier = choose([
                    f"Standard      {MUTED}quality {cfg.min_quality:.2f}  ·  "
                    f"will struggle for years{RESET}",
                    f"Strong entry  {MUTED}quality {strong_q:.2f}  ·  "
                    f"{RED}costs existing teams −0.01 quality each{RESET}",
                ], f"Entry quality for {pick.name}:", default=0)
                sq = strong_q if tier == 1 else cfg.min_quality
                chosen.append((pick, sq))
                n_add += 1
                tier_label = f"{RED}strong entry{RESET}" if tier == 1 else "standard"
                print(f"  {GREEN}✓ {pick.name} added  ({tier_label}).{RESET}")
            else:
                print(f"  {RED}Invalid.{RESET}")

        if chosen:
            joined = sn + 1
            existing_teams = list(league.teams)   # snapshot before adding anyone
            for franchise, sq in chosen:
                league._add_expansion_team(franchise, joined, starting_quality=sq)
                league.expansion_log.append((sn, franchise.name, franchise.secondary))
                if sq > cfg.min_quality:
                    for t in existing_teams:
                        t.quality = max(cfg.min_quality, t.quality - 0.01)
            league.league_popularity = min(1.0, league.league_popularity + cfg.league_pop_expansion_boost)
            league._last_expansion_season = sn
            league._expansion_eligible_seasons = 0
            names = ", ".join(f.name for f, _ in chosen)
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

    # ── Rule change ───────────────────────────────────────────────────────────

    def _handle_rule_change_offer(self, season: Season):
        league = self.league
        sn     = season.number
        cfg    = league.cfg

        if self._rule_change_cooldown > 0:
            return
        if league._meta_extreme_seasons < cfg.meta_shock_min_seasons:
            return

        direction = "offensive" if league.league_meta > 0 else "defensive"
        champ     = season.champion
        champ_style = "offensive" if champ.identity > 0.5 else "defensive"

        clear()
        header("RULE CHANGE AVAILABLE", f"After Season {sn}")
        print(f"  The league has been in a prolonged {RED}{direction}{RESET} era "
              f"for {RED}{league._meta_extreme_seasons}{RESET} consecutive seasons.\n"
              f"\n"
              f"  Avg scoring : {season.league_avg_ppg():.1f} pts/game\n"
              f"  Meta value  : {league.league_meta:+.3f}\n"
              f"  Champion    : {champ.franchise_at(sn).name} "
              f"({MUTED}{champ_style} identity{RESET})\n"
              f"  {MUTED}10-season cooldown after any rule change.{RESET}\n")

        options = [
            (
                f"Favor current style    "
                f"{MUTED}Cost:{RESET} {GOLD}Medium  {RESET}"
                f"{MUTED}Risk:{RESET} {GOLD}Medium  {RESET}"
                f"{MUTED}Reward:{RESET} {GOLD}Medium{RESET}  "
                f"{MUTED}(amplify the {direction} era){RESET}",
                "favor",
            ),
            (
                f"Level the field        "
                f"{MUTED}Cost:{RESET} {GREEN}Low     {RESET}"
                f"{MUTED}Risk:{RESET} {GREEN}Low     {RESET}"
                f"{MUTED}Reward:{RESET} {GOLD}Medium{RESET}  "
                f"{MUTED}(reset toward neutral){RESET}",
                "neutral",
            ),
            (
                f"Counter the champion   "
                f"{MUTED}Cost:{RESET} {GOLD}Medium  {RESET}"
                f"{MUTED}Risk:{RESET} {GOLD}Medium  {RESET}"
                f"{MUTED}Reward:{RESET} {GOLD}Medium{RESET}  "
                f"{MUTED}(push against {champ_style} play){RESET}",
                "counter",
            ),
            (
                f"{MUTED}No rule change{RESET}",
                "none",
            ),
        ]

        choice = choose([o[0] for o in options], "Commissioner Decision:", default=3)
        action = options[choice][1]
        old_meta = league.league_meta

        if action == "favor":
            sign = 1 if league.league_meta > 0 else -1
            league.league_meta = max(-cfg.meta_max,
                                     min(cfg.meta_max, league.league_meta + sign * 0.04))
            league._meta_velocity *= 0.5
            league._meta_extreme_seasons = 0
            season.meta_shock = True
            self._rule_change_cooldown = 10
            print(f"\n  {GREEN}Rules tilted to favor {direction} play.{RESET}")
            print(f"  Meta: {old_meta:+.3f} → {league.league_meta:+.3f}")

        elif action == "neutral":
            league.league_meta = random.gauss(0, cfg.meta_shock_spread)
            league._meta_velocity = 0.0
            league._meta_extreme_seasons = 0
            season.meta_shock = True
            self._rule_change_cooldown = 10
            new_dir = "offensive" if league.league_meta > 0 else "defensive"
            print(f"\n  {GREEN}Rules reset toward balanced play.{RESET}")
            print(f"  Meta: {old_meta:+.3f} → {league.league_meta:+.3f}  ({new_dir} lean)")

        elif action == "counter":
            sign = -1 if champ.identity > 0.5 else 1   # oppose champ's style
            league.league_meta = max(-cfg.meta_max,
                                     min(cfg.meta_max, league.league_meta + sign * 0.06))
            league._meta_velocity = 0.0
            league._meta_extreme_seasons = 0
            season.meta_shock = True
            self._rule_change_cooldown = 10
            counter_dir = "defensive" if champ.identity > 0.5 else "offensive"
            print(f"\n  {GREEN}Rules adjusted to counter {champ.franchise_at(sn).name}.{RESET}")
            print(f"  Pushed toward {counter_dir}. Meta: {old_meta:+.3f} → {league.league_meta:+.3f}")

        else:
            print(f"\n  {MUTED}No rule change. The {direction} era continues.{RESET}")

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
