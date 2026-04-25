#!/usr/bin/env python3
"""Commissioner Mode — interactive season-by-season league management."""

import os
import pickle
import random
from collections import Counter

from config import Config
from franchises import ALL_FRANCHISES, Franchise
from game import GameResult, _BENCH_ID
from league import League
from rival import (RivalLeague, strength_label as rival_strength_label,
                   funding_label as rival_funding_label)
from owner import (Owner, generate_buyers,
                   MOT_MONEY, MOT_WINNING as OWNER_MOT_WINNING, MOT_LOCAL_HERO,
                   THREAT_QUIET, THREAT_LEAN, THREAT_DEMAND,
                   PERS_RENEGADE, LOY_LOW,
                   happiness_label as owner_happiness_label)
from player import (Player, GUARD, WING, BIG, POSITIONS, ZONES,
                    MOT_WINNING, MOT_MARKET, MOT_LOYALTY,
                    TIER_ELITE, TIER_HIGH, TIER_MID, TIER_LOW,
                    happiness_emoji, popularity_tier, durability_label)
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
    has_reports = (
        _game_ref is not None
        and _game_ref.league is not None
        and bool(_game_ref.league.seasons)
    )
    hint = "[q] save & quit  ·  [r] reports" if has_reports else "[q] quit"
    print(f"  {MUTED}{hint}{RESET}")

def divider():
    print(f"{MUTED}{'─' * W}{RESET}")

def _pillar_grade(score: float) -> str:
    """Convert [0,1] pillar score to letter grade (2-char, right-padded)."""
    if score >= 0.93: return "A+"
    if score >= 0.88: return "A "
    if score >= 0.85: return "A-"
    if score >= 0.80: return "B+"
    if score >= 0.75: return "B "
    if score >= 0.70: return "B-"
    if score >= 0.65: return "C+"
    if score >= 0.60: return "C "
    if score >= 0.55: return "C-"
    if score >= 0.50: return "D+"
    if score >= 0.45: return "D "
    if score >= 0.40: return "D-"
    return "F "

def _grade_color(grade: str) -> str:
    """ANSI color for a pillar grade string."""
    g = grade.strip()
    if g.startswith("A"): return GREEN
    if g.startswith("B"): return CYAN
    if g.startswith("C"): return GOLD
    return RED

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

def _fans_millions(team) -> float:
    """Fan count in millions: popularity × market size."""
    return team.popularity * team.franchise.effective_metro

def _pop_fan_display(team, width: int = 12) -> str:
    """Popularity bar (0–1, market-agnostic) + absolute fan count.

    The bar reflects how beloved the team is regardless of market size.
    The fan count shows the absolute scale (popularity × metro).
    """
    pop   = team.popularity
    fans  = pop * team.franchise.effective_metro
    filled = round(pop * width)
    bar    = "█" * filled + "░" * (width - filled)
    color  = GREEN if pop >= 0.55 else (RED if pop < 0.30 else CYAN)
    return f"{color}{bar}{RESET} {pop:.0%}  {MUTED}{fans:.1f}M{RESET}"

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


def _owner_breaking_point_prob(owner: "Owner", denial_count: int) -> float:
    """Probability of a breaking point after denial_count total denials.

    The first denial (count=1) is always safe — the owner is furious but not yet
    at breaking point. From the 2nd denial onward, risk scales with personality
    and loyalty. Renegade + low-loyalty owners can snap on the 2nd denial (50%);
    steady + loyal owners have much more patience but risk keeps climbing.
    """
    if denial_count <= 1:
        return 0.0
    renegade = owner.personality == PERS_RENEGADE
    disloyal  = owner.loyalty    == LOY_LOW
    if renegade and disloyal:
        base, scale = 0.50, 0.25   # 50% / 75% / 100% on 2nd / 3rd / 4th denial
    elif renegade:
        base, scale = 0.30, 0.20   # 30% / 50% / 70%
    elif disloyal:
        base, scale = 0.25, 0.20   # 25% / 45% / 65%
    else:
        base, scale = 0.15, 0.15   # 15% / 30% / 45%
    return min(1.0, base + (denial_count - 2) * scale)

# ── Global quit / reports ─────────────────────────────────────────────────────
# Typing "quit" or "q" at any prompt saves and exits.
# Typing "reports" or "r" at any prompt opens the reports menu mid-flow.

class _QuitSignal(Exception):
    """Raised anywhere inside the game to trigger a save-and-exit."""

_game_ref: "CommissionerGame | None" = None  # set in CommissionerGame.run()


def prompt(msg: str) -> str:
    """Input helper. Intercepts 'quit'/'q' and 'reports'/'r' globally."""
    while True:
        raw = input(f"\n  {CYAN}▶ {msg}{RESET} ").strip()
        low = raw.lower()
        if low in ("quit", "q"):
            raise _QuitSignal()
        if low in ("reports", "r") and _game_ref is not None:
            # Use the in-progress season if available (e.g. during playoffs),
            # otherwise fall back to the last completed season.
            season = _game_ref._current_season
            if season is None and _game_ref.league:
                seasons = _game_ref.league.seasons
                season  = seasons[-1] if seasons else None
            if season is not None:
                _game_ref._show_reports(season)
            # After returning from reports, re-prompt in context.
            continue
        return raw


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


# ── Save / load ───────────────────────────────────────────────────────────────

_SAVE_FILE = os.path.join(os.path.dirname(__file__), "save.pkl")

def _save_exists() -> bool:
    return os.path.isfile(_SAVE_FILE)

def _do_save(game: "CommissionerGame") -> None:
    """Pickle the full game state, including player module globals."""
    import player as _player_mod
    import owner as _owner_mod
    payload = {
        "game":               game,
        "next_id":            _player_mod._next_id,
        "used_names":         _player_mod._used_names,
        "owner_names":        _owner_mod._used_owner_names,
        "owner_firsts":       _owner_mod._used_owner_firsts,
    }
    tmp = _SAVE_FILE + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, _SAVE_FILE)   # atomic on POSIX; best-effort on Windows

def _do_load() -> "CommissionerGame":
    """Restore game state from disk. Raises on version mismatch or corruption."""
    import player as _player_mod
    import owner as _owner_mod
    with open(_SAVE_FILE, "rb") as f:
        payload = pickle.load(f)
    game                          = payload["game"]
    _player_mod._next_id          = payload["next_id"]
    _player_mod._used_names       = payload["used_names"]
    _owner_mod._used_owner_names  = payload.get("owner_names",  set())
    _owner_mod._used_owner_firsts = payload.get("owner_firsts", set())
    return game


# ── Commissioner game ─────────────────────────────────────────────────────────

class CommissionerGame:

    def __init__(self):
        self.league_name = "Basketball League"
        self.league: League | None = None
        self.season_num = 0
        self._prev_league_pop = 0.0
        self._rule_changes_made: int = 0  # cumulative rule changes (drives cost escalation)
        self._last_pop_signals: dict = {}   # signal breakdown from most recent season
        self._last_pillar_scores: dict = {}  # four-pillar health scores from most recent season
        self._treasury: float = 0.0       # accumulated commissioner funds (carry-over)
        self._last_revenue: float = 0.0   # revenue earned most recent season
        self._retiring_this_season: list = []
        self._new_fas_this_season: list  = []
        self._owner_actions: dict = {}    # {team_id: action_dict} — generated each offseason
        self._walkout_just_formed: bool = False   # set by CBA handler when Type C forms
        self._defection_warning_shown: set = set()  # season numbers where warning was shown
        self._current_season: "Season | None" = None  # set during _run_one_season for mid-season reports

    def _load_game(self) -> None:
        """Load saved state into self, handling corruption or version mismatch."""
        try:
            loaded = _do_load()
            self.__dict__.update(loaded.__dict__)
            clear()
            sn = self.season_num
            lname = self.league_name
            n_teams = len(self.league.teams) if self.league else 0
            print(f"\n  {GREEN}Save loaded.{RESET}  "
                  f"{lname}  ·  After Season {sn}  ·  {n_teams} teams\n")
            press_enter()
        except Exception as e:
            clear()
            print(f"\n  {RED}Could not load save file:{RESET} {e}\n")
            print(f"  The save may be from an incompatible version of the game.")
            idx = choose(["Start a new league", "Quit"], default=0)
            if idx == 1:
                raise _QuitSignal()
            self._setup()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _show_wip_status(self):
        clear()
        header("FAKE BASKETBALL", "Commissioner Mode")
        print(f"""
  {BOLD}You are the Commissioner of a fictional basketball league.{RESET}
  Players develop, age, and retire. Owners push back. Rivals
  emerge. You won't control outcomes — you'll influence them.
""")
        cols = [
            ("Season & playoff simulation",    "Owner system & CBA"),
            ("Player arcs, injuries & fatigue", "Rival leagues  (3 types)"),
            ("Chemistry, awards & draft",       "Expansion & relocation"),
            ("Free agency & star FA events",    "Revenue, era & reports"),
        ]
        for left, right in cols:
            print(f"  {GREEN}✓{RESET}  {left:<36}  {GREEN}✓{RESET}  {right}")
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
            print(f"\n  Larger markets give more fan stability; smaller markets are harder")
            print(f"  to grow but create more dramatic underdog stories.  {GOLD}★{RESET} = co-tenant available\n")

            # Two-column layout
            half = (len(all_primaries) + 1) // 2
            left_col  = list(enumerate(all_primaries[:half],        1))
            right_col = list(enumerate(all_primaries[half:], half + 1))
            col_w = 26
            for (li, lf), rc in zip(left_col, right_col + [(None, None)]):
                lm  = f"{lf.effective_metro:>4.0f}M"
                lst = f"{GOLD}★{RESET}" if lf.city in all_secondaries else " "
                left  = f"  {li:>2}. {lf.city:<{col_w}} {lm} {lst}"
                if rc[0] is not None:
                    ri, rf = rc
                    rm  = f"{rf.effective_metro:>4.0f}M"
                    rst = f"{GOLD}★{RESET}" if rf.city in all_secondaries else " "
                    right = f"   {ri:>2}. {rf.city:<{col_w}} {rm} {rst}"
                else:
                    right = ""
                print(left + right)

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
            print(f"  {'#':>2}  {'Market':<28} {'Mkt pull ea.':>12}")
            divider()
            for i, f in enumerate(cotenant_eligible, 1):
                pull = f.effective_metro * 0.5
                print(f"  {CYAN}[{i}]{RESET} {f.city:<28} {MUTED}~{pull:.1f}M{RESET}")
            print(f"""
  {MUTED}Trade-off: both teams launch with split popularity — 50/50,
  since neither has history in this league yet. Market pull targets
  are 70%/50% of baseline. A city championship or Finals run steals
  25% of that boost from the co-tenant.{RESET}
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

        print(f"\n  {GREEN}Selected {len(selected)} founding markets:{RESET}")
        for f in selected:
            tag = f"  {GOLD}(co-tenant){RESET}" if f.secondary else ""
            print(f"  • {f.city}  {MUTED}(market {f.effective_metro:.1f}){RESET}{tag}")
        press_enter()
        return selected

    def _setup_names(self, franchises: list[Franchise]) -> None:
        """Randomly assign nicknames, then let the player rename any they want."""
        # Save options before touching anything (league.py needs them cleared later)
        options_map: dict[int, list[str]] = {
            id(f): f.nickname_options[:] for f in franchises
        }

        # Pre-assign a random nickname to every franchise
        for f in franchises:
            opts = options_map[id(f)]
            if opts:
                f.nickname = random.choice(opts)

        # Show the full list; let the player drill into any team to rename it
        while True:
            clear()
            header("TEAM NAMES", "Randomly assigned — enter a number to rename")
            print()
            for i, f in enumerate(franchises, 1):
                tag = f"  {GOLD}co-tenant{RESET}" if f.secondary else ""
                print(f"  {CYAN}[{i}]{RESET} {f.name}{tag}")
            print()
            raw = prompt("Enter a number to rename, or Enter to accept all:").strip()

            if not raw:
                break

            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(franchises):
                    f = franchises[idx]
                    opts = options_map[id(f)]
                    clear()
                    tag = f"  {GOLD}co-tenant{RESET}" if f.secondary else ""
                    header("RENAME", f"{f.city}{tag}")
                    print(f"\n  Current: {BOLD}{f.name}{RESET}\n")
                    if opts:
                        for i, opt in enumerate(opts, 1):
                            cur_tag = f"  {GOLD}← current{RESET}" if opt == f.nickname else ""
                            print(f"    {CYAN}[{i}]{RESET} {f.city} {opt}{cur_tag}")
                        print(f"    {MUTED}[c]{RESET} Enter a custom name")
                        print()
                        pick = prompt(f"Pick 1–{len(opts)}, [c] for custom, or Enter to keep:").strip().lower()
                        if pick == "c":
                            custom = prompt(f"{f.city} nickname:").strip()
                            if custom:
                                f.nickname = custom
                        elif pick.isdigit() and 1 <= int(pick) <= len(opts):
                            f.nickname = opts[int(pick) - 1]
                    else:
                        custom = prompt(f"{f.city} nickname (Enter to keep):").strip()
                        if custom:
                            f.nickname = custom

        # Mark all options resolved so league.py won't re-randomize
        for f in franchises:
            f.nickname_options = []

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
        max_fb = max(_fans_millions(t) for t in teams)

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
                net    = _rel_net(t.ortg, t.drtg, avg_o, avg_d)
                net_c  = GREEN if net > 0 else (RED if net < 0 else MUTED)
                chem   = t.compute_chemistry(cfg)
                chem_c = GREEN if chem >= 1.05 else (RED if chem < 0.90 else CYAN)
                pd_str = _pop_fan_display(t, 12)

                print(f"\n  {BOLD}{t.name}{RESET}")
                print(f"  {MUTED}ORtg {t.ortg:.1f}  DRtg {t.drtg:.1f}  "
                      f"Net {net_c}{net:+.1f}{RESET}  "
                      f"Pace {t.pace:.0f}  3pt {t.style_3pt:.0%}  "
                      f"Popularity {pd_str}  "
                      f"Chem {chem_c}{chem:.2f}{RESET}")

                if t.owner:
                    o = t.owner
                    pers_c = GOLD if o.personality == "renegade" else MUTED
                    loy_c  = CYAN if o.loyalty == "loyal" else RED
                    mot_c  = (GREEN if o.motivation == OWNER_MOT_WINNING
                              else GOLD if o.motivation == MOT_MONEY else CYAN)
                    print(f"  {MUTED}Owner:{RESET} {o.name}  "
                          f"{mot_c}{o.motivation_label()}{RESET}  "
                          f"{pers_c}{o.personality}{RESET}  "
                          f"{loy_c}{o.loyalty.replace('_', ' ')}{RESET}  "
                          f"{MUTED}competence {o.competence:.0%}{RESET}")

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
        global _game_ref
        _game_ref = self
        try:
            self._start_menu()
            while True:
                self.season_num += 1
                season = self._run_one_season()
                self._show_summary(season)
                self._post_season(season)
                _do_save(self)   # autosave after every completed season
                while True:
                    idx = choose(
                        ["Next season", "View reports", "Save & quit", "Quit without saving"],
                        title="What next?", default=0,
                    )
                    if idx == 1:
                        self._show_reports(season)
                    else:
                        break
                if idx == 2:
                    _do_save(self)
                    clear()
                    print(f"\n  {GREEN}Game saved.{RESET}  See you next season, Commissioner.\n")
                    break
                if idx == 3:
                    self._show_farewell()
                    break
        except _QuitSignal:
            if self.league is not None and self.league.seasons:
                _do_save(self)
                clear()
                print(f"\n  {GREEN}Game saved.{RESET}  See you next season, Commissioner.\n")
            # else: quit from start menu — no game to save, just exit cleanly

    def _start_menu(self) -> None:
        """Startup menu — new game or continue a saved one."""
        clear()
        header("FAKE BASKETBALL", "Commissioner Mode")
        if _save_exists():
            print(f"\n  {GREEN}Save file found.{RESET}\n")
            idx = choose(
                ["Continue saved game", "New league", "Quit"],
                title="What would you like to do?", default=0,
            )
            if idx == 0:
                self._load_game()
                return
            elif idx == 2:
                raise _QuitSignal()
        self._setup()

    def _run_one_season(self) -> Season:
        """Run one season through all engine steps, with interactive relocations."""
        league = self.league
        sn = self.season_num
        season = Season(sn, list(league.teams), league.cfg, league.league_meta)
        self._current_season = season   # expose early so 'r' works during playoffs
        season.play_regular_season()
        self._play_playoffs_interactive(season)
        league.seasons.append(season)
        # Phase 1: advance players, surface retirements/FA for interactive handling
        self._retiring_this_season, self._new_fas_this_season = (
            league.offseason_phase1(season)
        )
        league._update_losing_streaks(season)
        league._decay_grudges()
        league._evolve_popularity(season)
        league._evolve_market_engagements(season)
        self._last_pop_signals = league._evolve_league_popularity(season)
        league._evolve_meta()
        self._last_pillar_scores = league.compute_pillar_scores(season)
        season._popularity        = {t: t.popularity for t in league.teams}
        season._market_engagement = {t: t.market_engagement for t in league.teams}
        season._league_popularity = league.league_popularity
        season._meta              = league.league_meta   # snapshot for history display
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
                tc  = GOLD if season.mvp.peak_overall >= 14 else CYAN
                ms  = season.player_stats.get(season.mvp.player_id)
                stat_str = (f"{ms.ppg:>5.1f} PPG  {ms.fg_pct:.1%} FG  {ms.fg3_pct:.1%} 3P"
                            if ms else f"ORtg {season.mvp.ortg_contrib:>+5.1f}")
                print(f"  {GOLD}MVP  :{RESET}  {happiness_emoji(season.mvp.happiness)} {tc}{season.mvp.name:<22}{RESET}  "
                      f"{MUTED}{season.mvp.position} · {mvp_team}{RESET}  {stat_str}")
            if season.opoy:
                opoy_team = season.opoy_team.franchise_at(sn).nickname if season.opoy_team else "—"
                tc  = GOLD if season.opoy.peak_overall >= 14 else CYAN
                os  = season.player_stats.get(season.opoy.player_id)
                stat_str = (f"{os.ppg:>5.1f} PPG  {os.fg_pct:.1%} FG  {os.fg3_pct:.1%} 3P"
                            if os else f"ORtg {season.opoy.ortg_contrib:>+5.1f}")
                print(f"  {GOLD}OPOY :{RESET}  {happiness_emoji(season.opoy.happiness)} {tc}{season.opoy.name:<22}{RESET}  "
                      f"{MUTED}{season.opoy.position} · {opoy_team}{RESET}  {stat_str}")
            if season.dpoy:
                dpoy_team = season.dpoy_team.franchise_at(sn).nickname if season.dpoy_team else "—"
                tc  = GOLD if season.dpoy.peak_overall >= 14 else CYAN
                ds  = season.player_stats.get(season.dpoy.player_id)
                stat_str = (f"Def Rtg {ds.def_rtg:>5.1f}  {ds.pts_allowed}/{ds.poss_defended} poss"
                            if ds and ds.poss_defended else f"DRtg {season.dpoy.drtg_contrib:>+5.1f}")
                print(f"  {CYAN}DPOY :{RESET}  {happiness_emoji(season.dpoy.happiness)} {tc}{season.dpoy.name:<22}{RESET}  "
                      f"{MUTED}{season.dpoy.position} · {dpoy_team}{RESET}  {stat_str}")

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

        # ── Season stat leaderboard ───────────────────────────────────────────
        all_players = [(p, t) for t in season.teams for p in t.roster if p is not None]
        scored = [(p, t, season.player_stats[p.player_id])
                  for p, t in all_players
                  if p.player_id in season.player_stats
                  and p.player_id != _BENCH_ID]
        if scored:
            print()
            print(f"  {BOLD}{'SCORING LEADERS':^60}{RESET}")
            print(f"  {MUTED}{'Player':<22} {'Team':<20} {'PPG':>5} {'FG%':>6} {'3P%':>6} {'FT%':>6}{RESET}")
            top_scorers = sorted(scored, key=lambda x: x[2].ppg, reverse=True)[:5]
            for p, t, s in top_scorers:
                tname = t.franchise_at(sn).nickname[:18]
                tc = GOLD if p is season.mvp else (CYAN if p.peak_overall >= 14 else "")
                print(f"  {tc}{p.name:<22}{RESET} {MUTED}{tname:<20}{RESET}"
                      f" {s.ppg:>5.1f} {s.fg_pct:>6.1%} {s.fg3_pct:>6.1%} {s.ft_pct:>6.1%}")

            print()
            print(f"  {BOLD}{'DEFENSIVE LEADERS':^60}{RESET}")
            print(f"  {MUTED}{'Player':<22} {'Team':<20} {'Def Rtg':>7} {'Poss':>5}{RESET}")
            def_candidates = [(p, t, s) for p, t, s in scored if s.poss_defended > 0]
            top_defenders = sorted(def_candidates, key=lambda x: x[2].def_rtg)[:5]
            for p, t, s in top_defenders:
                tname = t.franchise_at(sn).nickname[:18]
                tc = CYAN if p is season.dpoy else ""
                print(f"  {tc}{p.name:<22}{RESET} {MUTED}{tname:<20}{RESET}"
                      f" {s.def_rtg:>7.1f} {s.poss_defended:>5}")

        press_enter("Press Enter to see injury report...")

        # ── Injury report screen ──────────────────────────────────────────────
        clear()
        header(self.league_name, f"Season {sn}  —  Injury Report")

        injured = [
            (p, t, season.player_stats[p.player_id].games_missed)
            for t in season.teams
            for p in t.roster
            if p is not None
            and p.player_id in season.player_stats
            and season.player_stats[p.player_id].games_missed >= 5
        ]
        if injured:
            print()
            print(f"  {BOLD}{'NOTABLE INJURIES':^60}{RESET}")
            print(f"  {MUTED}{'Player':<22} {'Team':<20} {'Slot':<8} {'Missed':>6}  {'Dur':<7}  🔋{RESET}")
            divider()
            for p, t, gm in sorted(injured, key=lambda x: -x[2]):
                tname = t.franchise_at(sn).nickname[:18]
                dur_c = (GREEN if p.durability >= 0.88 else
                         CYAN  if p.durability >= 0.75 else
                         MUTED if p.durability >= 0.62 else RED)
                nrg = (1 - p.fatigue) * 100
                fat_c = RED if nrg < 60 else (GOLD if nrg < 80 else MUTED)
                slot_lbl = t.slot_label(t.roster.index(p)) if p in t.roster else "—"
                print(f"  {p.name:<22} {MUTED}{tname:<20}{RESET}"
                      f" {MUTED}{slot_lbl:<8}{RESET}"
                      f" {RED}{gm:>5} gms{RESET}"
                      f"  {dur_c}{durability_label(p.durability):<7}{RESET}"
                      f"  {fat_c}🔋{nrg:.0f}%{RESET}")
        else:
            print(f"\n  {GREEN}No significant injuries this season.{RESET}")

        # ── Fatigue summary for playoff-bound teams ───────────────────────────
        playoff_set = set(season.regular_season_standings[:season.playoff_teams])
        fatigue_rows = []
        for t in season.regular_season_standings[:season.playoff_teams]:
            for p in t.roster:
                if p is not None:
                    fatigue_rows.append((p, t, p.fatigue))
        fatigue_rows.sort(key=lambda x: -x[2])
        if fatigue_rows:
            print()
            print(f"  {BOLD}{'PLAYOFF-BOUND FATIGUE LOADS':^60}{RESET}")
            print(f"  {MUTED}{'Player':<22} {'Team':<20} {'Slot':<8}  🔋  {'Dur':<7}{RESET}")
            divider()
            for p, t, fat in fatigue_rows:
                tname = t.franchise_at(sn).nickname[:18]
                slot_lbl = t.slot_label(t.roster.index(p)) if p in t.roster else "—"
                nrg = (1 - fat) * 100
                fat_c = RED if nrg < 60 else (GOLD if nrg < 80 else MUTED)
                dur_c = (GREEN if p.durability >= 0.88 else
                         CYAN  if p.durability >= 0.75 else
                         MUTED if p.durability >= 0.62 else RED)
                print(f"  {p.name:<22} {MUTED}{tname:<20}{RESET}"
                      f" {MUTED}{slot_lbl:<8}{RESET}"
                      f"  {fat_c}🔋{nrg:.0f}%{RESET}"
                      f"  {dur_c}{durability_label(p.durability):<7}{RESET}")

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
                # Per-team roster row: star + co-star with fatigue + games missed
                def _fat_str(player) -> str:
                    nrg = (1 - player.fatigue) * 100
                    fat_c = RED if nrg < 60 else (GOLD if nrg < 80 else MUTED)
                    ps = season.player_stats.get(player.player_id)
                    gm = ps.games_missed if ps else 0
                    gm_str = f" {RED}({gm}out){RESET}" if gm >= 5 else ""
                    return f"{fat_c}🔋{nrg:.0f}%{RESET}{gm_str}"

                def _roster_row(t: Team) -> str:
                    star   = t.roster[0] if len(t.roster) > 0 else None
                    costar = t.roster[1] if len(t.roster) > 1 else None
                    parts = []
                    for lbl, p in [("★", star), ("·", costar)]:
                        if p is None:
                            continue
                        tc = GOLD if p.ceiling_tier == TIER_ELITE else (CYAN if p.ceiling_tier == TIER_HIGH else "")
                        parts.append(
                            f"{lbl} {happiness_emoji(p.happiness)}"
                            f"{tc}{p.name} ({p.ceiling_tier[0]}){RESET}"
                            f" {_fat_str(p)}"
                        )
                    return "   ".join(parts)

                champ_tag1 = f"  {GOLD}🏆×{s1.championships}{RESET}" if s1.championships else ""
                champ_tag2 = f"  {GOLD}🏆×{s2.championships}{RESET}" if s2.championships else ""
                divider()
                print(f"  {CYAN}{i}.{RESET} "
                      f"({seed1_idx}) {BOLD}{s1n:<24}{RESET}  vs  "
                      f"({seed2_idx}) {BOLD}{s2n:<24}{RESET}"
                      f"  Net {net1_c}{net1:>+.0f}{RESET} v {net2_c}{net2:<+.0f}{RESET}"
                      f"{status}")
                print(f"      {CYAN}({seed1_idx}){RESET}  {_roster_row(s1)}{champ_tag1}")
                print(f"      {CYAN}({seed2_idx}){RESET}  {_roster_row(s2)}{champ_tag2}")
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
            fb1 = _fans_millions(s1);  fb2 = _fans_millions(s2)

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
                print(f"       Popularity {t.popularity:.0%}"
                      f"  ·  Fans {fb:.1f}M"
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
                        ps = season.player_stats.get(player.player_id)
                        if ps and ps.games > 0:
                            stat_str = (f"  {ps.ppg:>5.1f} PPG"
                                        f"  {ps.fg_pct:.1%} FG"
                                        f"  {ps.fg3_pct:.1%} 3P")
                        else:
                            stat_str = (f"  ORtg {player.ortg_contrib:>+5.1f}"
                                        f"  DRtg {player.drtg_contrib:>+5.1f}")
                        gm = ps.games_missed if ps else 0
                        gm_str = (f"  {RED}{gm} missed{RESET}" if gm >= 5
                                  else f"  {MUTED}{gm} missed{RESET}" if gm > 0
                                  else "")
                        _nrg = (1 - player.fatigue) * 100
                        fat_c = RED if _nrg < 60 else (GOLD if _nrg < 80 else MUTED)
                        fat_str = f"  {fat_c}🔋{_nrg:.0f}%{RESET}"
                        print(f"       {MUTED}{lbl:<9}{RESET}"
                              f"{happiness_emoji(player.happiness)} {tc}{player.name:<22}{RESET}"
                              f"  {player.position:<5} {player.age:>2}"
                              f"{stat_str}"
                              f"{gm_str}"
                              f"{fat_str}"
                              f"  {tc}{player.ceiling_tier}{RESET}"
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
        """Play a full series, applying a prob bonus to the favored team every game."""
        from game import play_game as _play_game, _HOME_PATTERNS as _PAT
        cfg = season.cfg
        league = self.league
        wins_needed = cfg.series_length // 2 + 1
        pattern = _PAT.get(
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
            ha = cfg.home_pscore_bonus_base + cfg.home_pscore_bonus_pop_scale * home.popularity
            home_adv = ha + cfg.playoff_seed_pscore_bonus * (1 if home is seed1 else 0)
            away_adv = cfg.playoff_seed_pscore_bonus * (1 if away is seed1 else 0)
            if favored is not None:
                if home is favored:
                    home_adv += bonus_val
                else:
                    away_adv += bonus_val

            result = _play_game(home, away, cfg,
                                home_advantage=home_adv,
                                away_advantage=away_adv,
                                league_meta=league.league_meta)
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
                ps = season.player_stats.get(p.player_id)
                if ps and lbl == "DPOY":
                    stat_str = (f"Def Rtg {ps.def_rtg:.1f}  {ps.poss_defended} poss defended"
                                if ps.poss_defended else f"DRtg {p.drtg_contrib:>+.1f}")
                elif ps and ps.games > 0:
                    stat_str = f"{ps.ppg:.1f} PPG  {ps.fg_pct:.1%} FG  {ps.fg3_pct:.1%} 3P  {ps.ft_pct:.1%} FT"
                else:
                    stat_str = f"ORtg {p.ortg_contrib:>+.1f}  DRtg {p.drtg_contrib:>+.1f}"
                print(f"  {GOLD}{lbl:<12}{RESET} {happiness_emoji(p.happiness)} {tc}{p.name:<22}{RESET}"
                      f"  {MUTED}{p.position} · {tname:<18}{RESET}"
                      f"  {stat_str}  {p.trend}")

        # Standings (single table: record + scoring + playoff result)
        print(f"\n  {'TEAM':<30} {'RECORD':<13} {'PS/G':>5}  {'PA/G':>5}  {'Diff':>5}  PLAYOFF")
        divider()
        standings = season.regular_season_standings
        n_playoff = season.playoff_teams
        playoff_result = self._playoff_results(season)

        for i, team in enumerate(standings):
            rank = i + 1
            rw, rl = season.reg_wins(team), season.reg_losses(team)
            fname  = team.franchise_at(sn).name
            result = playoff_result.get(team, "")
            record = _wl(rw, rl)
            ppg    = season.team_ppg(team)
            papg   = season.team_papg(team)
            diff   = ppg - papg
            diff_c = GREEN if diff > 0 else (RED if diff < 0 else MUTED)

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
            print(f"  {rank:>2}. {name_str}  {record:<13} {ppg:>5.1f}  {papg:>5.1f}  {diff_c}{diff:>+5.1f}{RESET}  {seed_str} {result_str}")

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
        total_fans = sum(_fans_millions(t) for t in league.teams)
        print(f"\n  {BOLD}League Health{RESET}")
        print(f"  Popularity  {pop_bar(lp)}  {trend(lp_prev, lp)}")
        print(f"  Fan Base    {CYAN}{total_fans:.1f}M{RESET}  "
              f"{MUTED}total fans · Era: {era_label(league.league_meta)} · "
              f"Avg {avg_ppg:.1f} pts/game{RESET}")
        if season.meta_shock:
            print(f"  {RED}{BOLD}⚡ Rule change shock fired this season!{RESET}")

        # Four-pillar display
        pillar_data = self._last_pillar_scores
        if pillar_data:
            print()
            pillar_defs = [
                ("Integrity",     "integrity"),
                ("Parity",        "parity"),
                ("Drama",         "drama"),
                ("Entertainment", "entertainment"),
            ]
            history = league.pillar_history
            for label, key in pillar_defs:
                data   = pillar_data.get(key, {})
                score  = data.get("score", 0.0)
                grade  = _pillar_grade(score)
                gc     = _grade_color(grade)
                # Trend vs prior season
                prev_sn = sn - 1
                prev_score = history.get(prev_sn, {}).get(key)
                tr = trend(prev_score, score) if prev_score is not None else f"{MUTED}—{RESET}"
                print(f"  {label:<14} {gc}{BOLD}{grade}{RESET}  "
                      f"{MUTED}{score:.2f}{RESET}  {tr}")
                drivers = data.get("drivers", [])
                for dir_ch, dlabel, _ in drivers[:3]:
                    dc = GREEN if dir_ch == "↑" else RED
                    print(f"    {dc}{dir_ch}{RESET}  {MUTED}{dlabel}{RESET}")
            print(f"\n  {MUTED}[H] Full health breakdown{RESET}")

        # Notable events
        events = self._collect_events(season)
        if events:
            print(f"\n  {BOLD}Events{RESET}")
            for e in events:
                print(f"  • {e}")

        self._prev_league_pop = lp
        while True:
            raw = prompt("Enter to continue, [H] for full health breakdown:").strip().lower()
            if raw == "h" and self._last_pillar_scores:
                self._show_league_health_detail(season)
            else:
                break

    def _show_league_health_detail(self, season: Season) -> None:
        """Full drill-down screen for all four pillar scores and their components."""
        league = self.league
        sn = season.number
        pillar_data = self._last_pillar_scores
        if not pillar_data:
            press_enter("No pillar data available.")
            return

        clear()
        header("LEAGUE HEALTH BREAKDOWN", f"Season {sn}")

        pillar_defs = [
            ("INTEGRITY",     "integrity",     "Trustworthiness & governance"),
            ("PARITY",        "parity",        "Competitive balance & access"),
            ("DRAMA",         "drama",         "Narrative & story arcs"),
            ("ENTERTAINMENT", "entertainment", "Product quality & star power"),
        ]

        for label, key, subtitle in pillar_defs:
            data  = pillar_data.get(key, {})
            score = data.get("score", 0.0)
            grade = _pillar_grade(score)
            gc    = _grade_color(grade)
            history = league.pillar_history
            prev_score = history.get(sn - 1, {}).get(key)
            tr = trend(prev_score, score) if prev_score is not None else f"{MUTED}—{RESET}"

            print(f"\n  {gc}{BOLD}{label}{RESET}  {gc}{grade}{RESET}  "
                  f"{MUTED}{score:.2f}{RESET}  {tr}  {MUTED}{subtitle}{RESET}")
            divider()

            components = data.get("components", [])
            for w, s, clabel in components:
                bar_w = 12
                filled = round(s * bar_w)
                bar = "█" * filled + "░" * (bar_w - filled)
                sc = GREEN if s >= 0.70 else (RED if s < 0.45 else GOLD)
                contribution = w * s
                print(f"  {sc}{bar}{RESET}  {MUTED}w={w:.2f}{RESET}  {clabel}")

        # Show raw popularity signals at bottom for reference
        if self._last_pop_signals:
            print(f"\n  {BOLD}Popularity signals this season{RESET}  {MUTED}(underlying drivers){RESET}")
            divider()
            annotations = self._pop_signal_annotations(season)
            for sig_name, sig_delta in self._last_pop_signals.items():
                if abs(sig_delta) >= 0.0005:
                    color = GREEN if sig_delta > 0 else RED
                    sign  = "+" if sig_delta >= 0 else ""
                    note  = annotations.get(sig_name, "")
                    note_str = f"  {MUTED}{note}{RESET}" if note else ""
                    print(f"    {MUTED}{sig_name:<22}{RESET} {color}{sign}{sig_delta:.1%}{RESET}{note_str}")

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
        sig = self._last_pop_signals.get("Fan composite", 0.0)
        if sig < -0.002 and low:
            cities = ", ".join(t.franchise.city for t in low)
            annotations["Fan composite"] = f"{cities} disengaged"
        elif sig > 0.002 and high:
            cities = ", ".join(t.franchise.city for t in high)
            annotations["Fan composite"] = f"{cities} driving interest"
        else:
            annotations["Fan composite"] = ""

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

        # ── Work stoppage hangover ────────────────────────────────────────────
        # Counter is decremented during evolution, so h reflects seasons still remaining
        h = league._stoppage_hangover
        if h == 5:
            annotations["Work stoppage hangover"] = "catastrophic — season cancelled, fans furious"
        elif h == 4:
            annotations["Work stoppage hangover"] = "severe — trust not rebuilt"
        elif h == 3:
            annotations["Work stoppage hangover"] = "moderate — scars still visible"
        elif h == 2:
            annotations["Work stoppage hangover"] = "lingering fan resentment"
        elif h == 1:
            annotations["Work stoppage hangover"] = "trace — needs something special to fully heal"
        elif h == 0 and "Work stoppage hangover" in self._last_pop_signals:
            annotations["Work stoppage hangover"] = "recovered — fans have moved on"

        return annotations

    # ── Reports sub-menu ──────────────────────────────────────────────────────

    def _show_reports(self, season: Season):
        while True:
            clear()
            header("REPORTS", f"After Season {season.number}")
            has_rival = (self.league.rival_league is not None
                         or bool(self.league.rival_league_history))
            rival_label = (
                f"Rival League     {RED}⚔ ACTIVE{RESET}" if (self.league.rival_league and self.league.rival_league.active)
                else f"Rival League     {MUTED}standings, champions & history{RESET}" if has_rival
                else f"{MUTED}Rival League     no rival league yet{RESET}"
            )
            idx = choose([
                f"League History   {MUTED}season-by-season champions, scorer, era & parity{RESET}",
                f"Team History     {MUTED}full record for any team with top player each year{RESET}",
                f"Player Stats     {MUTED}season leaders · best single seasons · career leaders{RESET}",
                f"Rosters          {MUTED}current players with last season's stats{RESET}",
                f"Owner Dashboard  {MUTED}happiness, P&L, competence & threat level by team{RESET}",
                f"Market Map       {MUTED}engagement, popularity & grudges by city{RESET}",
                f"Event Log        {MUTED}expansions, mergers & relocations{RESET}",
                f"All-Time Records {MUTED}championships, streaks, best & worst seasons{RESET}",
                f"Rivalries        {MUTED}head-to-head matchup history{RESET}",
                f"Playoff Analysis {MUTED}seed advantage, series length & home court trends{RESET}",
                f"League Health    {MUTED}pillar scores trend — Integrity · Parity · Drama · Entertainment{RESET}",
                rival_label,
                f"{MUTED}Back{RESET}",
            ], default=12)
            if   idx == 0:  self._show_league_history(season)
            elif idx == 1:  self._show_team_history(season)
            elif idx == 2:  self._show_player_stats(season)
            elif idx == 3:  self._show_rosters(season)
            elif idx == 4:  self._show_owner_dashboard(season)
            elif idx == 5:  self._show_market_map(season)
            elif idx == 6:  self._show_event_log(season)
            elif idx == 7:  self._show_alltime_records(season)
            elif idx == 8:  self._show_rivalries(season)
            elif idx == 9:  self._show_playoff_analysis(season)
            elif idx == 10: self._show_league_health_report(season)
            elif idx == 11: self._show_rival_league_report(season)
            else: break

    # ── Report: League Health Trend ───────────────────────────────────────────

    def _show_league_health_report(self, season: Season):
        league  = self.league
        history = league.pillar_history
        if not history:
            press_enter("No pillar history available yet — play at least one season.")
            return

        PAGE = 20
        seasons = league.seasons
        page = max(0, len(seasons) - PAGE)

        while True:
            clear()
            header("LEAGUE HEALTH HISTORY", self.league_name)
            chunk = seasons[page: page + PAGE]

            print(f"\n  {'S':>3}  {'Integrity':<12} {'Parity':<12} "
                  f"{'Drama':<12} {'Entertainment':<14} {'Pop':>4}")
            divider()

            for s in chunk:
                sn = s.number
                ph = history.get(sn, {})
                lp = getattr(s, '_league_popularity', None)
                lp_str = f"{lp:.0%}" if lp is not None else "  —"

                def _grade_cell(key: str) -> str:
                    sc = ph.get(key)
                    if sc is None:
                        return f"{'—':<12}"
                    g  = _pillar_grade(sc)
                    gc = _grade_color(g)
                    return f"{gc}{BOLD}{g}{RESET} {MUTED}{sc:.2f}{RESET}  "

                print(f"  {sn:>3}  "
                      f"{_grade_cell('integrity')}"
                      f"{_grade_cell('parity')}"
                      f"{_grade_cell('drama')}"
                      f"{_grade_cell('entertainment')}"
                      f"  {MUTED}{lp_str}{RESET}")

            print()
            divider()
            has_next = page + PAGE < len(seasons)
            nav = []
            if page > 0:  nav.append("p=prev")
            if has_next:  nav.append("Enter=next")
            else:         nav.append("Enter=done")
            raw = prompt(f"  [{', '.join(nav)}]:").strip().lower()
            if raw == "p" and page > 0:
                page -= PAGE
            elif has_next and raw in ("", "n"):
                page += PAGE
            else:
                break

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

            print(f"\n  {'S':>3}  {'Champion':<20} {'Record':<13} {'Runner-up':<14} "
                  f"{'N':>3}  {'Pop':>4}  {'Bal':>4}  {'Era':>4}  Top Scorer")
            divider()

            for s in chunk:
                if s.champion:
                    champ_name = s.champion.franchise_at(s.number).name[:19]
                    w  = s.reg_wins(s.champion)
                    lo = s.reg_losses(s.champion)
                    record = _wl(w, lo)
                    if s.playoff_rounds:
                        finals = s.playoff_rounds[-1][0]
                        ru = finals.seed2 if finals.winner is finals.seed1 else finals.seed1
                        ru_name = ru.franchise_at(s.number).nickname[:13]
                        rs_leader = s.regular_season_standings[0] if s.regular_season_standings else None
                        rs_tag = f"{GOLD}★{RESET}" if rs_leader is s.champion else " "
                    else:
                        ru_name, rs_tag = "—", " "
                else:
                    champ_name, record, ru_name, rs_tag = "—", "—", "—", " "

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

                # Era tag (3pt meta)
                meta_val = s._league_popularity  # use stored league_pop as proxy; real meta in _meta
                # Use actual meta if stored (we snapshot it from league.league_meta)
                stored_meta = getattr(s, '_meta', None)
                if stored_meta is not None:
                    if stored_meta > 0.07:   era_s = f"{GREEN}OFF{RESET}"
                    elif stored_meta < -0.07: era_s = f"{RED}DEF{RESET}"
                    else:                     era_s = f"{MUTED}BAL{RESET}"
                else:
                    era_s = f"{MUTED} — {RESET}"

                # Top scorer
                top_scorer_str = ""
                if s.player_stats:
                    qualified = [(pid, st) for pid, st in s.player_stats.items()
                                 if pid != _BENCH_ID and st.games >= 5]
                    if qualified:
                        top_pid, top_st = max(qualified, key=lambda x: x[1].ppg)
                        # Find player name
                        top_name = next(
                            (p.name for t in s.teams for p in t.roster
                             if p is not None and p.player_id == top_pid),
                            f"P{top_pid}"
                        )
                        top_scorer_str = f"{top_name[:14]} {top_st.ppg:.1f}"

                print(f"  {s.number:>3}  {rs_tag}{champ_name:<20} {record:<13} "
                      f"{ru_name:<14} {n_teams:>3}  {lp_str:>4}  {bal_str}  {era_s}  "
                      f"{MUTED}{top_scorer_str}{RESET}{tags_str}")

                award_parts = []
                if s.mvp:
                    ms = s.player_stats.get(s.mvp.player_id)
                    ppg_s = f" {ms.ppg:.1f}ppg" if ms else ""
                    award_parts.append(f"MVP {s.mvp.name}{ppg_s}")
                if s.opoy:
                    award_parts.append(f"OPOY {s.opoy.name}")
                if s.dpoy:
                    ds = s.player_stats.get(s.dpoy.player_id)
                    drtg_s = f" {ds.def_rtg:.1f}drtg" if (ds and ds.poss_defended) else ""
                    award_parts.append(f"DPOY {s.dpoy.name}{drtg_s}")
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

        active_idents  = sorted(active_idents,  key=lambda e: -_fans_millions(e[1]))
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
                  f"{'Result':<18}  {'PS/G':>5}  {'PA/G':>5}  {'Diff':>5}  {'Fans':>6}  Top Player")
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
                # Top player by PPG on this team this season
                team_players = [p for p in team.roster if p is not None]
                top_player_str = ""
                if team_players and s.player_stats:
                    scored = [(p, s.player_stats[p.player_id])
                              for p in team_players
                              if p.player_id in s.player_stats
                              and p.player_id != _BENCH_ID
                              and s.player_stats[p.player_id].games >= 5]
                    if scored:
                        best_p, best_s = max(scored, key=lambda x: x[1].ppg)
                        mvp_tag = f"{GOLD}★{RESET}" if best_p is s.mvp else ""
                        top_player_str = f"{best_p.name[:14]} {best_s.ppg:.1f}{mvp_tag}"
                print(f"  {s.number:>3}  {record:<14} {pos_str:>4}  "
                      f"{result:<18}  {ppg:>5.1f}  {papg:>5.1f}  "
                      f"{diff_c}{diff:>+5.1f}{RESET}  {fb:>6.1f}M  {MUTED}{top_player_str}{RESET}")

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
                # Find this season's stats for each player
                last_season = league.seasons[-1] if league.seasons else None
                last_stats = last_season.player_stats if last_season else {}

                print(f"  {'Slot':<8} {'Name':<22} {'Pos':<5} {'Age':>3}  "
                      f"{'ORtg':>5}  {'DRtg':>5}  {'Zone':<6}  "
                      f"{'Yrs':>3}  {'Tr':>2}  {'Mood':<4}  {'PPG':>5}  {'FG%':>5}  {'DRtg':>7}  "
                      f"{'Gms':>3}  {'Dur':<6}  {'🔋':>5}  Mot")
                print(f"  {MUTED}{'─' * 110}{RESET}")
                for idx, player in enumerate(team.roster):
                    slot_lbl = team.slot_label(idx)
                    if player is None:
                        print(f"  {MUTED}{slot_lbl:<8} — empty{RESET}")
                    else:
                        mot_c = (GREEN if player.motivation == MOT_WINNING
                                 else GOLD if player.motivation == MOT_MARKET else CYAN)
                        trend_s = player.trend
                        tc = tier_colors.get(player.ceiling_tier, "")
                        ps = last_stats.get(player.player_id)
                        ppg_str   = f"{ps.ppg:>5.1f}" if (ps and ps.games > 0) else f"{MUTED}  —  {RESET}"
                        fg_str    = f"{ps.fg_pct:>5.1%}" if (ps and ps.fga > 0) else f"{MUTED}  —  {RESET}"
                        drtg_str  = f"{ps.def_rtg:>7.1f}" if (ps and ps.poss_defended > 0) else f"{MUTED}    —  {RESET}"
                        gms_str   = f"{ps.games_missed:>3}" if (ps and ps.games_missed > 0) else f"{MUTED}  0{RESET}"
                        dur_lbl   = durability_label(player.durability)
                        dur_c     = GREEN if player.durability >= 0.88 else (CYAN if player.durability >= 0.75 else (MUTED if player.durability >= 0.62 else RED))
                        _nrg2     = (1 - player.fatigue) * 100
                        fat_c     = RED if _nrg2 < 60 else (GOLD if _nrg2 < 80 else MUTED)
                        print(f"  {MUTED}{slot_lbl:<8}{RESET}"
                              f" {tc}{player.name:<22}{RESET}"
                              f" {player.position:<5} {player.age:>3}"
                              f"  {player.ortg_contrib:>+5.1f}  {player.drtg_contrib:>+5.1f}"
                              f"  {player.preferred_zone:<6}"
                              f"  {player.contract_years_remaining:>3}"
                              f"  {trend_s:>2}"
                              f"  {happiness_emoji(player.happiness):<4}"
                              f"  {ppg_str}  {fg_str}  {drtg_str}"
                              f"  {gms_str}  {dur_c}{dur_lbl:<6}{RESET}  {fat_c}🔋{_nrg2:>3.0f}%{RESET}"
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

        # Re-sort active cities by fan count (popularity × metro) descending
        active_cities = sorted(
            city_teams.items(),
            key=lambda x: -sum(_fans_millions(t) for t in x[1]),
        )

        clear()
        header("MARKET MAP", f"After Season {season.number}")

        # Active markets
        print(f"\n  {BOLD}Active markets{RESET}  "
              f"{MUTED}Bar = popularity (market-agnostic)  ·  sorted by fan count{RESET}\n")
        print(f"  {'City':<18} {'Team':<22} {'Popularity / Fans':<26}  {'Eng':>5}  Metro")
        divider()
        for city, teams in active_cities:
            metro = max(t.franchise.effective_metro for t in teams)
            for i, t in enumerate(sorted(teams, key=lambda x: x.franchise.secondary)):
                pd_str  = _pop_fan_display(t, 12)
                eng_pct = f"{t.market_engagement:.0%}"
                grudge_tag = (f"  {RED}grudge{RESET}"
                              if t.franchise.city in league.market_grudges else "")
                if i == 0:
                    print(f"  {city:<18} {t.franchise.nickname:<22} {pd_str}  "
                          f"{MUTED}{eng_pct:>5}{RESET}  {MUTED}{metro:.1f}M{RESET}{grudge_tag}")
                else:
                    print(f"  {'':18} {t.franchise.nickname:<22} {pd_str}  "
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
                             for t in league.teams if played_sn[t]], key=lambda x: -x[1])
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
            print(f"  {'S':>3}  {'Franchise':<24}  {'Record':<14}  {'PS/G':>5}  {'PA/G':>5}  {'Diff':>5}  Top Scorer")
            divider()
            for s, t, w, lo, pct, ppg, papg in rows:
                fname    = t.franchise_at(s.number).name[:24]
                fmr      = _fmr_tag(t)
                champ_t  = f" {GOLD}★{RESET}" if t is s.champion else ""
                record   = _wl(w, lo)
                diff     = ppg - papg
                diff_c   = GREEN if diff > 0 else (RED if diff < 0 else MUTED)
                pct_c    = GREEN if pct >= 0.70 else (RED if pct <= 0.35 else RESET)
                # Top scorer for this team this season
                team_pids = [p.player_id for p in t.roster if p is not None]
                top_str = ""
                if s.player_stats and team_pids:
                    scored = [(s.player_stats[pid], pid)
                              for pid in team_pids
                              if pid in s.player_stats and pid != _BENCH_ID
                              and s.player_stats[pid].games >= 5]
                    if scored:
                        best_st, best_pid = max(scored, key=lambda x: x[0].ppg)
                        pname = next((p.name[:14] for p in t.roster
                                      if p is not None and p.player_id == best_pid), "")
                        top_str = f"{MUTED}{pname} {best_st.ppg:.1f}{RESET}"
                print(f"  {s.number:>3}  {fname:<24}  "
                      f"{pct_c}{record:<14}{RESET}  {ppg:>5.1f}  {papg:>5.1f}  "
                      f"{diff_c}{diff:>+5.1f}{RESET}{champ_t}{fmr}  {top_str}")

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

        # ── Home court win% — regular season, by team ─────────────────────────
        print(f"\n  {BOLD}Home court advantage  (regular season){RESET}\n")

        team_hw: dict = {}   # team_id → (home_wins, home_games)
        pop_hw   = [0, 0, 0]   # wins by pop bucket
        pop_hg   = [0, 0, 0]   # games by pop bucket
        for s in seasons:
            for g in s.regular_season_games:
                home_pop = getattr(s, '_popularity', {}).get(g.home, g.home.popularity)
                bucket = 0 if home_pop < 0.33 else (1 if home_pop < 0.60 else 2)
                is_win = 1 if g.home_score > g.away_score else 0
                pop_hw[bucket]  += is_win
                pop_hg[bucket]  += 1
                tid = g.home.team_id
                hw, hg = team_hw.get(tid, (0, 0))
                team_hw[tid] = (hw + is_win, hg + 1)

        # League-wide home win rate
        all_hw = sum(w for w, _ in team_hw.values())
        all_hg = sum(g for _, g in team_hw.values())
        lw_pct = all_hw / all_hg if all_hg else 0
        pc = GREEN if lw_pct >= 0.55 else (RED if lw_pct < 0.50 else MUTED)
        print(f"  League overall home win%:  {pc}{lw_pct:.1%}{RESET}  ({all_hw}/{all_hg} games)")

        # By popularity bucket
        print(f"\n  By team popularity tier:")
        print(f"  {'Tier':<22} {'HW%':>5}  Games")
        divider()
        pop_labels = ["Low  (pop < 0.33)", "Mid  (0.33–0.60)", "High (pop > 0.60)"]
        for i, lbl in enumerate(pop_labels):
            if pop_hg[i]:
                r = pop_hw[i] / pop_hg[i]
                rc = GREEN if r >= 0.57 else (RED if r < 0.50 else MUTED)
                print(f"  {lbl:<22} {rc}{r:.1%}{RESET}  {pop_hg[i]:,}")

        # By team — top/bottom movers (min 20 home games)
        team_by_id = {t.team_id: t for t in league.teams}
        team_rates = [
            (tid, hw / hg, hw, hg)
            for tid, (hw, hg) in team_hw.items()
            if hg >= 20
        ]
        if team_rates:
            team_rates.sort(key=lambda x: -x[1])
            print(f"\n  Best home records (min 20 games):")
            print(f"  {'Team':<26} {'HW%':>6}  W–G")
            divider()
            for tid, rate, hw, hg in team_rates[:5]:
                t = team_by_id.get(tid)
                name = t.franchise.name[:26] if t else f"Team {tid}"
                rc = GREEN if rate >= 0.58 else MUTED
                print(f"  {name:<26} {rc}{rate:.1%}{RESET}  {hw}–{hg}")
            if len(team_rates) > 5:
                print(f"  {MUTED}…{RESET}")
                worst = team_rates[-3:]
                for tid, rate, hw, hg in worst:
                    t = team_by_id.get(tid)
                    name = t.franchise.name[:26] if t else f"Team {tid}"
                    rc = RED if rate < 0.48 else MUTED
                    print(f"  {name:<26} {rc}{rate:.1%}{RESET}  {hw}–{hg}")

        press_enter()

    # ── Report: Player Stats ──────────────────────────────────────────────────

    def _show_player_stats(self, season: Season):
        """Player leaderboards: current season, all-time single season, career."""
        league  = self.league
        seasons = league.seasons
        sn      = season.number

        PAGES = 3
        page  = 0

        while True:
            clear()

            if page == 0:
                # ── Current season leaderboards ───────────────────────────────
                header("PLAYER STATS — This Season", f"Season {sn}")
                ps = season.player_stats
                all_players = [(p, t) for t in season.teams for p in t.roster
                               if p is not None]
                scored = [(p, t, ps[p.player_id])
                          for p, t in all_players
                          if p.player_id in ps and p.player_id != _BENCH_ID
                          and ps[p.player_id].games >= 5]

                if not scored:
                    print(f"\n  {MUTED}No player stats yet.{RESET}")
                else:
                    def _show_cat(title, rows, cols):
                        print(f"\n  {BOLD}{title}{RESET}")
                        hdr = f"  {'Player':<22} {'Team':<18}"
                        for c in cols: hdr += f"  {c[0]:>{c[2]}}"
                        print(hdr)
                        divider()
                        for p, t, s in rows[:8]:
                            tname = t.franchise_at(sn).nickname[:16]
                            tc = GOLD if p is season.mvp or p is season.opoy or p is season.dpoy else ""
                            row = f"  {tc}{p.name:<22}{RESET} {MUTED}{tname:<18}{RESET}"
                            for c in cols:
                                row += f"  {c[1](s):>{c[2]}}"
                            print(row)

                    _show_cat("Scoring Leaders",
                        sorted(scored, key=lambda x: -x[2].ppg),
                        [("PPG", lambda s: f"{s.ppg:.1f}", 5),
                         ("FG%", lambda s: f"{s.fg_pct:.1%}", 5),
                         ("3P%", lambda s: (f"{s.fg3_pct:.1%}" if s.fga_3 > 0 else "  —  "), 5),
                         ("FT%", lambda s: (f"{s.ft_pct:.1%}" if s.fta > 0 else "  —  "), 5),
                         ("GP",  lambda s: f"{s.games}", 3),
                         ("GM",  lambda s: f"{s.games_missed}" if s.games_missed > 0 else "—", 3)])

                    _show_cat("Defensive Leaders  (lower = better)",
                        sorted([(p, t, s) for p, t, s in scored if s.poss_defended >= 10],
                               key=lambda x: x[2].def_rtg),
                        [("Def Rtg", lambda s: f"{s.def_rtg:.1f}", 7),
                         ("Poss",    lambda s: f"{s.poss_defended}", 5),
                         ("Pts All", lambda s: f"{s.pts_allowed}", 7)])

                    _show_cat("Efficiency Leaders  (min 5 GP, 10 FGA)",
                        sorted([(p, t, s) for p, t, s in scored if s.fga >= 10],
                               key=lambda x: -(x[2].fgm * 2 + x[2].fgm_3) / max(x[2].fga, 1)),
                        [("PPG",  lambda s: f"{s.ppg:.1f}", 5),
                         ("FG%",  lambda s: f"{s.fg_pct:.1%}", 5),
                         ("3P%",  lambda s: (f"{s.fg3_pct:.1%}" if s.fga_3 > 0 else "  —  "), 5),
                         ("FT%",  lambda s: (f"{s.ft_pct:.1%}" if s.fta > 0 else "  —  "), 5)])

            elif page == 1:
                # ── Best single-season performances (all-time) ────────────────
                header("PLAYER STATS — Best Single Seasons", self.league_name)

                # Gather all qualified seasons — use season-start snapshots so
                # retired/released players still appear with correct names.
                all_records: list[tuple] = []   # (season_num, pname, tname, champ_team, stats)
                for s in seasons:
                    for pid, st in s.player_stats.items():
                        if pid == _BENCH_ID or st.games < 5:
                            continue
                        pname = s.player_names.get(pid)
                        tname = s.player_teams.get(pid)
                        if pname and tname:
                            all_records.append((s.number, pname, tname, s.champion, st))

                if not all_records:
                    print(f"\n  {MUTED}Not enough history yet.{RESET}")
                else:
                    def _show_alltime(title, records, key_fn, col_fn, col_hdr):
                        print(f"\n  {BOLD}{title}{RESET}")
                        print(f"  {'S':>3}  {'Player':<22} {'Team':<18}  {col_hdr}")
                        divider()
                        for snum, pname, tname, champ_team, st in sorted(records, key=key_fn)[:8]:
                            champ = f" {GOLD}★{RESET}" if champ_team is not None else ""
                            print(f"  {snum:>3}  {pname:<22} {MUTED}{tname:<18}{RESET}  "
                                  f"{col_fn(st)}{champ}")

                    _show_alltime("Best PPG Seasons",
                        all_records,
                        lambda x: -x[4].ppg,
                        lambda s: f"{s.ppg:.1f} PPG  {s.fg_pct:.1%} FG  {s.fg3_pct:.1%} 3P",
                        "PPG   FG%   3P%")

                    _show_alltime("Best Defensive Seasons  (min 20 poss defended)",
                        [r for r in all_records if r[4].poss_defended >= 20],
                        lambda x: x[4].def_rtg,
                        lambda s: f"{s.def_rtg:.1f} Def Rtg  {s.poss_defended} poss",
                        "Def Rtg  Poss")

            elif page == 2:
                # ── Career leaders (aggregated across all seasons) ─────────────
                header("PLAYER STATS — Career Leaders", self.league_name)

                # Aggregate per player_id across all seasons
                from collections import defaultdict
                career_pts:   dict[int, int]   = defaultdict(int)
                career_games: dict[int, int]   = defaultdict(int)
                career_fga:   dict[int, int]   = defaultdict(int)
                career_fgm:   dict[int, int]   = defaultdict(int)
                career_fga3:  dict[int, int]   = defaultdict(int)
                career_fgm3:  dict[int, int]   = defaultdict(int)
                career_poss:  dict[int, int]   = defaultdict(int)
                career_allow: dict[int, int]   = defaultdict(int)
                pid_to_name:  dict[int, str]   = {}
                pid_to_team:  dict[int, str]   = {}

                for s in seasons:
                    for pid, st in s.player_stats.items():
                        if pid == _BENCH_ID:
                            continue
                        career_pts[pid]   += st.points
                        career_games[pid] += st.games
                        career_fga[pid]   += st.fga
                        career_fgm[pid]   += st.fgm
                        career_fga3[pid]  += st.fga_3
                        career_fgm3[pid]  += st.fgm_3
                        career_poss[pid]  += st.poss_defended
                        career_allow[pid] += st.pts_allowed
                        # Use season-start snapshots — survive retirements/releases
                        # that mutate live rosters after the season ends.
                        if pid in s.player_names:
                            pid_to_name[pid] = s.player_names[pid]
                        if pid in s.player_teams:
                            pid_to_team[pid] = s.player_teams[pid]

                qualified = [(pid, career_games[pid]) for pid in career_games
                             if career_games[pid] >= 10]

                if not qualified:
                    print(f"\n  {MUTED}Not enough history yet.{RESET}")
                else:
                    def career_ppg(pid):
                        g = career_games[pid]
                        return career_pts[pid] / g if g else 0.0

                    def career_fg(pid):
                        return career_fgm[pid] / career_fga[pid] if career_fga[pid] else 0.0

                    def career_drtg(pid):
                        return career_allow[pid] / career_poss[pid] * 100 if career_poss[pid] else 999.0

                    print(f"\n  {BOLD}Career Scoring (min 10 games){RESET}")
                    print(f"  {'Player':<22} {'Team':<18}  {'PPG':>5}  {'FG%':>5}  {'3P%':>5}  GP")
                    divider()
                    top_scorers = sorted([p for p, _ in qualified], key=lambda p: -career_ppg(p))[:10]
                    for pid in top_scorers:
                        name  = pid_to_name.get(pid, f"P{pid}")
                        tname = pid_to_team.get(pid, "—")
                        gp    = career_games[pid]
                        fg3_str = (f"{career_fgm3[pid]/career_fga3[pid]:.1%}"
                                   if career_fga3[pid] else "  —  ")
                        print(f"  {name:<22} {MUTED}{tname:<18}{RESET}  "
                              f"{career_ppg(pid):>5.1f}  {career_fg(pid):>5.1%}  "
                              f"{fg3_str:>5}  {gp}")

                    print(f"\n  {BOLD}Career Defensive Rating (min 30 poss){RESET}")
                    print(f"  {'Player':<22} {'Team':<18}  {'Def Rtg':>7}  {'Poss':>5}")
                    divider()
                    def_qualified = [pid for pid, _ in qualified if career_poss[pid] >= 30]
                    top_defenders = sorted(def_qualified, key=lambda p: career_drtg(p))[:10]
                    for pid in top_defenders:
                        name  = pid_to_name.get(pid, f"P{pid}")
                        tname = pid_to_team.get(pid, "—")
                        print(f"  {name:<22} {MUTED}{tname:<18}{RESET}  "
                              f"{career_drtg(pid):>7.1f}  {career_poss[pid]:>5}")

            divider()
            nav = []
            if page > 0:          nav.append(f"{CYAN}[P]{RESET}rev")
            if page < PAGES - 1:  nav.append(f"{CYAN}[N]{RESET}ext")
            nav.append(f"{CYAN}[Q]{RESET}uit")
            pg_labels = ["Season Leaders", "Best Single Seasons", "Career Leaders"]
            print(f"\n  {pg_labels[page]}   page {page+1}/{PAGES}    {' · '.join(nav)}")
            raw = prompt("").lower()
            if   raw == "p" and page > 0:         page -= 1
            elif raw == "n" and page < PAGES - 1: page += 1
            else: break

    # ── Report: Owner Dashboard ───────────────────────────────────────────────

    def _show_owner_dashboard(self, season: Season):
        """Per-team owner health: happiness, competence, motivation, P&L, threat."""
        league = self.league
        sn     = season.number
        cfg    = league.cfg
        teams  = sorted(league.teams, key=lambda t: -(t.owner.happiness if t.owner else 0))

        clear()
        header("OWNER DASHBOARD", f"After Season {sn}  ·  {len(teams)} teams")

        print(f"\n  {'Team':<26} {'Owner':<22} {'Mot':<12} {'Happy':>6}  "
              f"{'Comp':>5}  {'P&L':>8}  {'Threat':<10}  Rev Eff")
        divider()

        for t in teams:
            owner = t.owner
            tname = t.franchise_at(sn).name[:24]
            if owner is None:
                print(f"  {MUTED}{tname:<26} — no owner{RESET}")
                continue

            # Motivation color
            mot_c = (GREEN if owner.motivation == MOT_WINNING
                     else GOLD if owner.motivation == MOT_MONEY else CYAN)
            mot_lbl = owner.motivation_label()[:10]

            # Happiness color
            h = owner.happiness
            h_c = GREEN if h >= 0.65 else (GOLD if h >= 0.40 else RED)
            h_lbl = f"{h_c}{h:.0%}{RESET}"

            # Competence (hidden, shown as bar)
            comp = owner.competence
            comp_bars = "█" * round(comp * 5) + "░" * (5 - round(comp * 5))
            comp_c = GREEN if comp >= 0.75 else (GOLD if comp >= 0.45 else RED)

            # Profit/loss
            profit = owner.last_net_profit
            p_c = GREEN if profit >= 0 else RED
            p_str = f"{p_c}{profit:>+7.1f}M{RESET}"

            # Threat level
            threat = owner.threat_level
            threat_lbl = {0: "Content", 1: "Watching", 2: "Demanding"}.get(threat, "")
            t_c = RED if threat == 2 else (GOLD if threat == 1 else MUTED)

            # Revenue efficiency
            rev_eff = owner.revenue_efficiency
            re_c = GREEN if rev_eff >= 0.85 else (GOLD if rev_eff >= 0.70 else RED)

            print(f"  {tname:<26} {owner.name:<22} {mot_c}{mot_lbl:<12}{RESET} "
                  f"{h_lbl:>6}  "
                  f"{comp_c}{comp_bars}{RESET}  "
                  f"{p_str}  "
                  f"{t_c}{threat_lbl:<10}{RESET}  "
                  f"{re_c}{rev_eff:.0%}{RESET}")

        # League-wide summary
        divider()
        owners = [t.owner for t in league.teams if t.owner]
        if owners:
            avg_h  = sum(o.happiness for o in owners) / len(owners)
            avg_c  = sum(o.competence for o in owners) / len(owners)
            total_profit = sum(o.last_net_profit for o in owners)
            demanding = sum(1 for o in owners if o.threat_level == 2)
            watching  = sum(1 for o in owners if o.threat_level == 1)
            h_c = GREEN if avg_h >= 0.60 else (GOLD if avg_h >= 0.40 else RED)
            p_c = GREEN if total_profit >= 0 else RED
            print(f"\n  Avg owner happiness:  {h_c}{avg_h:.0%}{RESET}   "
                  f"Avg competence: {avg_c:.0%}   "
                  f"League P&L: {p_c}{total_profit:+.1f}M{RESET}")
            if demanding or watching:
                print(f"  {RED}{demanding} demanding{RESET}  ·  {GOLD}{watching} watching{RESET}")

        press_enter()

    # ── Rival league ──────────────────────────────────────────────────────────

    def _handle_rival_league(self, season: Season) -> None:
        """Rival league offseason: Type A trigger + Type B ringleader + Type C walkout."""
        league = self.league
        sn     = season.number
        cfg    = league.cfg

        # Share league name so rival avoids duplicate names
        league._league_name = self.league_name

        # ── Type B: ringleader detection (runs even when no rival is active) ──
        if league.rival_league is None or not league.rival_league.active:
            warning_msg, defectors = league.check_rival_b_ringleader(sn)
            if warning_msg and sn not in self._defection_warning_shown:
                self._defection_warning_shown.add(sn)
                clear()
                header("OWNERSHIP ALERT", f"Season {sn} — Confidential")
                print(f"\n  {GOLD}⚠  {warning_msg}{RESET}\n")
                print(f"  You have one offseason to act. Keeping unhappy owners satisfied")
                print(f"  or forcing an ownership change may prevent the split.")
                press_enter()
            if defectors:
                clear()
                header("OWNER DEFECTION", f"Season {sn} — Breaking News")
                rival = league.rival_league
                print(f"\n  {RED}{BOLD}{len(defectors)} franchise(s) have defected.{RESET}\n")
                print(f"  Under {rival.ringleader_owner_name}, the following teams")
                print(f"  have broken away to form the {BOLD}{rival.name}{RESET}:\n")
                for t in defectors:
                    print(f"    {RED}·{RESET}  {t.franchise.name}")
                print(f"\n  Your league has lost {len(defectors)} franchise(s).")
                print(f"  {MUTED}Consider emergency expansion or negotiating their return.{RESET}")
                press_enter()

        # ── Type A: check if a new external rival forms ────────────────────────
        just_spawned_a = False
        if league.rival_league is None:
            just_spawned_a = league.check_rival_league_trigger(sn)

        # ── Type C: walkout just formed via CBA ────────────────────────────────
        just_spawned_c = getattr(self, '_walkout_just_formed', False)
        self._walkout_just_formed = False

        rival = league.rival_league
        if rival is None:
            return

        # 2. Advance the rival's season (simulate their records, apply base growth/decay)
        rival, intel = league.advance_rival_season(sn)

        # 3. Formation announcement
        if just_spawned_a:
            clear()
            header("RIVAL LEAGUE", f"Season {sn} — Offseason Alert")
            print(f"\n  {RED}{BOLD}A rival league has formed.{RESET}\n")
            print(f"  A group of investors has launched the {BOLD}{rival.name}{RESET} ({rival.short_name}).")
            print(f"  They have assembled {len(rival.teams)} franchise(s) across separate cities")
            print(f"  and are actively recruiting players and fans.")
            print(f"\n  {MUTED}Their financial backing is unknown. Watch this space.{RESET}")
            print(f"\n  {GOLD}Cities:{RESET}")
            for t in rival.teams:
                print(f"    {MUTED}·{RESET}  {t.name}")
            press_enter()

        if just_spawned_c:
            clear()
            header("PLAYER WALKOUT", f"Season {sn} — Crisis")
            print(f"\n  {RED}{BOLD}The work stoppage has escalated.{RESET}\n")
            print(f"  Striking players have organized a barnstorming circuit —")
            print(f"  the {BOLD}{rival.name}{RESET} ({rival.short_name}).")
            print(f"  They have {len(rival.teams)} loosely city-anchored teams.")
            print(f"\n  {GOLD}Your league will use replacement players this season{RESET}")
            print(f"  {MUTED}until you resolve the walkout.{RESET}")
            scab_events = league.install_replacement_rosters()
            if scab_events:
                print(f"\n  {GOLD}Scab signings:{RESET}")
                for ev in scab_events[:5]:
                    print(f"    {MUTED}·{RESET}  {ev}")
            press_enter()

        # 4. Intel event (if any)
        if intel:
            clear()
            header("RIVAL LEAGUE INTEL", f"Season {sn}")
            print(f"\n  {CYAN}Intelligence report — {rival.name}{RESET}\n")
            print(f"  {intel}")
            if rival.funding_revealed and rival.formation_type == "external":
                fl = rival_funding_label(rival.funding)
                fc = RED if rival.funding >= 0.65 else (GOLD if rival.funding >= 0.40 else MUTED)
                print(f"\n  {MUTED}Confirmed funding level:{RESET}  {fc}{fl}{RESET}")
            press_enter()

        # 5. Check for automatic resolution before offering decisions
        resolution = league.check_rival_resolution(sn)
        if resolution == "collapse":
            clear()
            header("RIVAL LEAGUE", f"Season {sn} — Breaking News")
            print(f"\n  {GREEN}{BOLD}The {rival.name} has ceased operations.{RESET}\n")
            print(f"  After {rival.seasons_active} season{'s' if rival.seasons_active != 1 else ''}, "
                  f"the {rival.short_name} has folded.")
            if rival.formation_type == "walkout":
                print(f"  Players return to their teams.")
                if league._walkout_replacement_rosters:
                    league.restore_regular_rosters(concession_level=0.0)
            else:
                print(f"  Players under rival contracts re-enter the free agent market next season.")
            print(f"\n  {GREEN}League popularity boost: +3%{RESET}")
            press_enter()
            return
        if resolution == "forced_merger":
            clear()
            header("RIVAL LEAGUE", f"Season {sn} — Crisis")
            print(f"\n  {RED}{BOLD}Forced merger — the {rival.name} negotiates from strength.{RESET}\n")
            print(f"  With your legitimacy critically low and the rival league dominant,")
            print(f"  you have no choice but to accept their terms.")
            cost = random.uniform(cfg.rival_brokered_merger_cost_min * 1.5,
                                  cfg.rival_brokered_merger_cost_max * 1.5)
            legit_hit = 0.10
            self._treasury    = max(0.0, self._treasury - cost)
            league.legitimacy = max(0.0, league.legitimacy - legit_hit)
            print(f"  Treasury: {RED}−${cost:.0f}M{RESET}   Legitimacy: {RED}−{legit_hit:.0%}{RESET}")
            press_enter()
            return

        # 6. Commissioner decision — branched by type
        rival = league.rival_league   # re-fetch (may have changed)
        if rival is None:
            return
        if rival.formation_type == "defection":
            self._handle_rival_b_decision(rival, sn)
        elif rival.formation_type == "walkout":
            self._handle_rival_c_decision(rival, sn)
        else:
            self._handle_rival_a_decision(rival, sn)

    def _handle_rival_a_decision(self, rival, sn: int) -> None:
        """Decision screen for Type A (external investors)."""
        league = self.league
        cfg    = league.cfg

        clear()
        header("RIVAL LEAGUE", f"Season {sn} — Commissioner Decision")

        strength_c = (RED  if rival.strength >= 0.70 else
                      GOLD if rival.strength >= 0.50 else
                      CYAN if rival.strength >= 0.30 else MUTED)
        sl = rival_strength_label(rival.strength)
        fl = rival_funding_label(rival.funding) if rival.funding_revealed else "Unknown"
        fc = (RED if rival.funding >= 0.65 else GOLD if rival.funding >= 0.40 else MUTED) if rival.funding_revealed else MUTED

        print(f"\n  {BOLD}{rival.name}  ({rival.short_name}){RESET}  {MUTED}External Investors{RESET}")
        print(f"  Active since season {rival.formed_season}  ·  "
              f"{rival.seasons_active} season{'s' if rival.seasons_active != 1 else ''} in operation")
        print(f"  Strength: {strength_c}{sl}  ({rival.strength:.0%}){RESET}")
        print(f"  Funding:  {fc}{fl}{RESET}")
        if rival.season_records:
            rec = rival.season_records[-1]
            print(f"\n  {MUTED}This season's {rival.short_name} champion:{RESET}  {rec.champion}")
            if rec.notable_players:
                top = rec.notable_players[0]
                print(f"  {MUTED}Scoring leader:{RESET}  {top[0]}  {MUTED}({top[1]}){RESET}  {top[2]:.1f} PPG")
        if rival.intel_events:
            _, last_intel = rival.intel_events[-1]
            print(f"\n  {MUTED}Latest intel:{RESET}  {last_intel[:80]}{'…' if len(last_intel) > 80 else ''}")

        divider()
        print(f"\n  {BOLD}How do you respond?{RESET}\n")

        options = [
            f"Monitor           {MUTED}do nothing · rival grows further{RESET}",
            f"Wage talent war   {MUTED}${cfg.rival_talent_war_cost_min:.0f}–${cfg.rival_talent_war_cost_max:.0f}M · weakens rival FA pull{RESET}",
            f"Legal & media     {MUTED}−{cfg.rival_legal_pressure_legit_cost:.0%} legitimacy · slows rival growth{RESET}",
        ]
        if rival.strength <= cfg.rival_merger_offer_max_strength:
            options.append(
                f"Broker merger     {MUTED}${cfg.rival_brokered_merger_cost_min:.0f}–${cfg.rival_brokered_merger_cost_max:.0f}M · dissolves rival, absorbs teams{RESET}"
            )
        options.append(f"{MUTED}Skip (monitor){RESET}")

        idx = choose(options, default=len(options) - 1)
        action_map = {0: "monitor", 1: "talent_war", 2: "legal",
                      3: ("merger" if rival.strength <= cfg.rival_merger_offer_max_strength else "monitor"),
                      4: "monitor"}
        action = action_map.get(idx, "monitor")

        cost, legit_cost, summary = league.apply_rival_commissioner_action(action, sn)
        if cost > 0:       self._treasury = max(0.0, self._treasury - cost)
        if legit_cost > 0: league.legitimacy = max(0.0, league.legitimacy - legit_cost)

        print(f"\n  {summary}")
        if cost > 0:       print(f"  {RED}Treasury: −${cost:.0f}M{RESET}")
        if legit_cost > 0: print(f"  {RED}Legitimacy: −{legit_cost:.0%}{RESET}")

        if league.rival_league and league.rival_league.active:
            pull_pct = league.rival_league.rival_fa_pull
            if pull_pct >= 0.10:
                print(f"\n  {GOLD}⚠ The {rival.short_name} is siphoning ~{pull_pct:.0%} of the free agent pool.{RESET}")
        press_enter()

    def _handle_rival_b_decision(self, rival, sn: int) -> None:
        """Decision screen for Type B (owner defection)."""
        league = self.league
        cfg    = league.cfg

        clear()
        header("OWNER DEFECTION", f"Season {sn} — Commissioner Decision")

        strength_c = (RED  if rival.strength >= 0.70 else
                      GOLD if rival.strength >= 0.50 else
                      CYAN if rival.strength >= 0.30 else MUTED)
        sl = rival_strength_label(rival.strength)

        print(f"\n  {BOLD}{rival.name}  ({rival.short_name}){RESET}  {MUTED}Owner Defection{RESET}")
        print(f"  Ringleader: {RED}{rival.ringleader_owner_name}{RESET}")
        print(f"  Defected franchises: {len(rival.teams)}")
        print(f"  Strength: {strength_c}{sl}  ({rival.strength:.0%}){RESET}")
        if rival.defected_team_names:
            print(f"  {MUTED}Teams out:{RESET}  " + ", ".join(rival.defected_team_names[:4]))
        if rival.season_records:
            rec = rival.season_records[-1]
            print(f"\n  {MUTED}{rival.short_name} this season — Champion:{RESET}  {rec.champion}")
        if rival.intel_events:
            _, last_intel = rival.intel_events[-1]
            print(f"  {MUTED}Latest:{RESET}  {last_intel[:80]}{'…' if len(last_intel) > 80 else ''}")

        divider()
        print(f"\n  {BOLD}How do you respond?{RESET}\n")

        options = [
            f"Monitor              {MUTED}wait and watch · rival grows{RESET}",
            f"Negotiate return     {MUTED}${cfg.rival_b_win_back_cost_min:.0f}–${cfg.rival_b_win_back_cost_max:.0f}M · −{cfg.rival_b_win_back_legit_cost:.0%} legitimacy · try to bring teams back{RESET}",
            f"Legal & media        {MUTED}−{cfg.rival_legal_pressure_legit_cost:.0%} legitimacy · weakens their operation{RESET}",
            f"Emergency expansion  {MUTED}fill gaps — use expansion tool after this screen{RESET}",
            f"{MUTED}Skip (monitor){RESET}",
        ]
        idx = choose(options, default=4)
        action_map = {0: "monitor", 1: "win_back", 2: "legal", 3: "expand", 4: "monitor"}
        action = action_map.get(idx, "monitor")

        cost, legit_cost, summary = league.apply_rival_b_commissioner_action(action, sn)
        if cost > 0:       self._treasury = max(0.0, self._treasury - cost)
        if legit_cost > 0: league.legitimacy = max(0.0, league.legitimacy - legit_cost)

        print(f"\n  {summary}")
        if cost > 0:       print(f"  {RED}Treasury: −${cost:.0f}M{RESET}")
        if legit_cost > 0: print(f"  {RED}Legitimacy: −{legit_cost:.0%}{RESET}")
        press_enter()

    def _handle_rival_c_decision(self, rival, sn: int) -> None:
        """Decision screen for Type C (player walkout)."""
        league = self.league
        cfg    = league.cfg

        clear()
        header("PLAYER WALKOUT", f"Season {sn} — Commissioner Decision")

        strength_c = (RED  if rival.strength >= 0.50 else
                      GOLD if rival.strength >= 0.30 else MUTED)
        sl = rival_strength_label(rival.strength)
        seasons_out = rival.seasons_active

        print(f"\n  {BOLD}{rival.name}  ({rival.short_name}){RESET}  {MUTED}Player Walkout{RESET}")
        print(f"  Circuit strength: {strength_c}{sl}  ({rival.strength:.0%}){RESET}  "
              f"{MUTED}(decays −{abs(cfg.rival_c_player_circuit_decay):.0%}/season){RESET}")
        print(f"  Season{'s' if seasons_out != 1 else ''} without regular players: {RED}{seasons_out}{RESET}")
        print(f"  {MUTED}Fan engagement −{abs(cfg.rival_c_fan_engagement_penalty):.0%} and legitimacy "
              f"−{abs(cfg.rival_c_legitimacy_penalty):.0%} per season of replacement ball.{RESET}")

        if rival.season_records:
            rec = rival.season_records[-1]
            print(f"\n  {MUTED}Player circuit this season — Champion:{RESET}  {rec.champion}")
            if rec.notable_players:
                top = rec.notable_players[0]
                print(f"  {MUTED}Top scorer:{RESET}  {top[0]}  {top[2]:.1f} PPG")
        if rival.intel_events:
            _, last_intel = rival.intel_events[-1]
            print(f"  {MUTED}Latest:{RESET}  {last_intel[:80]}{'…' if len(last_intel) > 80 else ''}")

        divider()
        print(f"\n  {BOLD}Negotiation options{RESET}\n")

        options = [
            f"Hold firm            {MUTED}another season of replacement ball · engagement & legitimacy keep falling{RESET}",
            f"Full concessions     {MUTED}−{cfg.rival_c_concession_legit_min:.0%}–{cfg.rival_c_concession_legit_max:.0%} legitimacy · players return happier · walkout ends{RESET}",
            f"Partial deal         {MUTED}−{cfg.rival_c_concession_legit_min:.0%} legitimacy · players return unhappy · walkout ends{RESET}",
        ]
        idx = choose(options, default=2)
        action_map = {0: "hold_firm", 1: "concede", 2: "partial"}
        action = action_map.get(idx, "partial")

        cost, legit_cost, summary = league.apply_rival_c_commissioner_action(action, sn)
        if cost > 0:       self._treasury = max(0.0, self._treasury - cost)
        if legit_cost > 0: league.legitimacy = max(0.0, league.legitimacy - legit_cost)

        print(f"\n  {summary}")
        if legit_cost > 0: print(f"  {RED}Legitimacy: −{legit_cost:.0%}{RESET}")
        if action == "hold_firm" and league.rival_league and league.rival_league.active:
            print(f"  {MUTED}Season {sn + 1} will run with replacement rosters.{RESET}")
        press_enter()

    # ── Rival league report ────────────────────────────────────────────────────

    def _show_rival_league_report(self, season: Season) -> None:
        """Three-page rival league report: overview / standings / history."""
        league = self.league
        rival  = league.rival_league
        history = league.rival_league_history

        if rival is None and not history:
            clear()
            header("RIVAL LEAGUE", self.league_name)
            print(f"\n  {MUTED}No rival league has formed yet.{RESET}")
            press_enter()
            return

        page = 0
        while True:
            clear()
            active_rival = rival if (rival and rival.active) else None

            if page == 0:
                # ── Overview ──────────────────────────────────────────────────
                header("RIVAL LEAGUE", "Overview")
                if active_rival:
                    r = active_rival
                    strength_c = (RED  if r.strength >= 0.70 else
                                  GOLD if r.strength >= 0.50 else
                                  CYAN if r.strength >= 0.30 else MUTED)
                    sl = rival_strength_label(r.strength)
                    fl = rival_funding_label(r.funding) if r.funding_revealed else "Unknown"
                    fc = (RED if r.funding >= 0.65 else GOLD if r.funding >= 0.40 else MUTED) if r.funding_revealed else MUTED

                    type_label = r.formation_label
                    print(f"\n  {BOLD}{r.name}  ({r.short_name}){RESET}  {GREEN}● ACTIVE{RESET}  {MUTED}{type_label}{RESET}")
                    print(f"  Formed season {r.formed_season}  ·  {r.seasons_active} season{'s' if r.seasons_active != 1 else ''} active")
                    if r.formation_type == "defection" and r.ringleader_owner_name:
                        print(f"  Ringleader: {RED}{r.ringleader_owner_name}{RESET}")
                    print()
                    # Strength bar
                    filled = round(r.strength * 20)
                    bar_c  = RED if r.strength >= 0.70 else (GOLD if r.strength >= 0.50 else CYAN)
                    bar    = f"{bar_c}{'█' * filled}{'░' * (20 - filled)}{RESET}"
                    decay_note = f"  {MUTED}(degrades naturally){RESET}" if r.formation_type == "walkout" else ""
                    print(f"  Strength  {bar}  {strength_c}{sl}  ({r.strength:.0%}){RESET}{decay_note}")
                    if r.formation_type != "walkout":
                        print(f"  Funding   {fc}{fl}{RESET}")
                    if r.rival_fa_pull > 0:
                        print(f"  FA pull   {MUTED}{r.rival_fa_pull:.0%} of free agent pool per offseason{RESET}")
                    print()
                    print(f"  {BOLD}Teams  ({len(r.teams)}){RESET}")
                    for t in r.teams:
                        tc = GOLD if t.strength >= 0.60 else (CYAN if t.strength >= 0.35 else MUTED)
                        print(f"    {tc}·{RESET}  {t.name:<28}  "
                              f"strength {tc}{t.strength:.0%}{RESET}")
                    if r.intel_events:
                        print(f"\n  {BOLD}Recent intel{RESET}")
                        for ev_sn, msg in r.intel_events[-3:]:
                            print(f"    {MUTED}S{ev_sn}:{RESET}  {msg[:72]}{'…' if len(msg) > 72 else ''}")
                else:
                    print(f"\n  {MUTED}No active rival league.{RESET}")

                if history:
                    print(f"\n  {BOLD}Former rival leagues  ({len(history)}){RESET}")
                    for r in history:
                        status = "Collapsed" if not r.active else "Merged"
                        print(f"    {MUTED}·{RESET}  {r.name}  {MUTED}S{r.formed_season}–S{r.formed_season + r.seasons_active}  ·  {r.formation_label}  ·  {status}{RESET}")

            elif page == 1:
                # ── Standings & champion ──────────────────────────────────────
                r = active_rival or (history[-1] if history else None)
                if r is None or not r.season_records:
                    print(f"\n  {MUTED}No season records yet.{RESET}")
                else:
                    header(f"{r.name}", "Standings & Champions")
                    latest = r.season_records[-1]
                    print(f"\n  {BOLD}Season {latest.season} — Standings{RESET}")
                    print(f"  {MUTED}{'Team':<30} {'W':>3}  {'L':>3}  {'Pct':>5}{RESET}")
                    divider()
                    for i, (tname, w, l) in enumerate(latest.standings):
                        total = w + l
                        pct   = w / total if total else 0.0
                        rank_c = GOLD if i == 0 else (CYAN if i < 4 else MUTED)
                        print(f"  {rank_c}{tname:<30}{RESET}  {w:>3}  {l:>3}  {pct:>5.1%}")
                    print(f"\n  {GOLD}Champion:{RESET}  {latest.champion}")
                    if latest.notable_players:
                        print(f"\n  {BOLD}Top scorers{RESET}")
                        print(f"  {MUTED}{'Player':<26} {'Team':<26} {'PPG':>5}{RESET}")
                        divider()
                        for pname, tname, ppg in latest.notable_players:
                            print(f"  {pname:<26} {MUTED}{tname:<26}{RESET}  {ppg:>5.1f}")

                    print(f"\n  {BOLD}All-time {r.short_name} champions{RESET}")
                    for rec in r.season_records:
                        print(f"  {MUTED}S{rec.season}:{RESET}  {rec.champion}")

            elif page == 2:
                # ── History & strength trend ──────────────────────────────────
                r = active_rival or (history[-1] if history else None)
                if r is None:
                    print(f"\n  {MUTED}No rival league history.{RESET}")
                else:
                    header(f"{r.name}", "Strength History")
                    if r.season_records:
                        print(f"\n  {MUTED}{'Season':<8} {'Strength':>10}  {'Delta':>8}  Status{RESET}")
                        divider()
                        for rec in r.season_records:
                            # Estimate strength at that season from cumulative deltas
                            sc = (RED  if rec.strength_delta > 0.05 else
                                  GREEN if rec.strength_delta < -0.05 else MUTED)
                            delta_str = f"{sc}{rec.strength_delta:>+.3f}{RESET}"
                            print(f"  S{rec.season:<6}  {'—':>10}  {delta_str:>8}")
                    if r.intel_events:
                        print(f"\n  {BOLD}All intel events{RESET}")
                        for ev_sn, msg in r.intel_events:
                            print(f"  {MUTED}S{ev_sn}:{RESET}  {msg[:70]}{'…' if len(msg) > 70 else ''}")

            divider()
            nav = choose(
                [f"Overview", f"Standings & Champions", f"History", f"{MUTED}Back{RESET}"],
                title="", default=3,
            )
            if   nav == 0: page = 0
            elif nav == 1: page = 1
            elif nav == 2: page = 2
            else: break

    # ── Post-season decisions ─────────────────────────────────────────────────

    def _post_season(self, season: Season):
        # Revenue: 20% to commissioner treasury, 80% to team owners (with competence penalty)
        commissioner_take = self.league.distribute_revenue()
        self._treasury += commissioner_take
        self._last_revenue = commissioner_take
        # Update owner happiness now that P&L is finalized
        self.league.update_all_owner_happiness(season)
        self._handle_player_offseason(season)
        self._owner_actions = self._generate_all_owner_actions(season)
        if season.number >= 5 and season.number % 5 == 0:
            self._handle_cba_negotiation(season)
        self._handle_rival_league(season)
        self._commissioner_desk(season)
        self._handle_players_meeting(season)
        self._handle_owner_meeting(season)
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
                # Aggregate career stats from all seasons
                career_pts = career_games = career_fga = career_fgm = 0
                career_poss = career_allow = 0
                for s in league.seasons:
                    st = s.player_stats.get(p.player_id)
                    if st:
                        career_pts   += st.points
                        career_games += st.games
                        career_fga   += st.fga
                        career_fgm   += st.fgm
                        career_poss  += st.poss_defended
                        career_allow += st.pts_allowed
                if career_games > 0:
                    c_ppg  = career_pts / career_games
                    c_fg   = career_fgm / career_fga if career_fga else 0.0
                    c_drtg = career_allow / career_poss * 100 if career_poss else 0.0
                    stat_line = f"  {c_ppg:.1f} PPG  {c_fg:.1%} FG"
                    if career_poss > 0: stat_line += f"  {c_drtg:.1f} Def Rtg"
                else:
                    stat_line = ""
                print(f"     Career: {p.seasons_played} seasons{stat_line}  "
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
                ps = season.player_stats.get(p.player_id)
                if ps and ps.games > 0:
                    stat_str = f"{ps.ppg:.1f} PPG  {ps.fg_pct:.1%} FG"
                else:
                    stat_str = f"ORtg {p.ortg_contrib:+.1f}  DRtg {p.drtg_contrib:+.1f}"
                print(f"  {p.name:<22} {MUTED}{p.position} · Age {p.age}{RESET}  "
                      f"{stat_str}  "
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

        # ── Rival FA pull — remove siphoned players before pool is shown ─────
        n_siphoned = league.apply_rival_passive_fa_pull()
        if n_siphoned > 0 and league.rival_league:
            self._rival_fa_notice = (league.rival_league.short_name, n_siphoned)
        else:
            self._rival_fa_notice = None

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

        legit = league.legitimacy
        legit_c = RED if legit < 0.50 else MUTED
        print(f"\n  {MUTED}Treasury: ${self._treasury:.0f}M  ·  "
              f"Legitimacy: {legit_c}{legit:.0%}{RESET}")
        if legit < 0.50:
            print(f"  {RED}⚠ Low legitimacy — rival leagues gain strength faster "
                  f"and fan trust erodes each season.{RESET}")
        print()

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

        # Pull last season's stats for each FA
        last_stats = season.player_stats  # already computed for this season

        clear()
        header("FREE AGENT POOL", f"After Season {sn}")
        notice = getattr(self, '_rival_fa_notice', None)
        if notice:
            short_name, n_gone = notice
            print(f"\n  {GOLD}⚠ The {short_name} signed {n_gone} player{'s' if n_gone != 1 else ''} "
                  f"before you got here.{RESET}")
        print(f"\n  {len(pool)} players available\n")
        print(f"  {'Name':<22} {'Pos':<6} {'Age':>3}  {'ORtg':>5}  {'DRtg':>5}  "
              f"{'Zone':<5}  {'PPG':>5}  {'FG%':>5}  {'Mood':<4}  Motivation")
        divider()
        for p in sorted(pool, key=lambda p: -p.overall):
            mot_c = (GREEN if p.motivation == MOT_WINNING
                     else GOLD if p.motivation == MOT_MARKET else CYAN)
            ps = last_stats.get(p.player_id)
            ppg_s = f"{ps.ppg:>5.1f}" if (ps and ps.games > 0) else f"{MUTED}  —  {RESET}"
            fg_s  = f"{ps.fg_pct:>5.1%}" if (ps and ps.fga > 0) else f"{MUTED}  —  {RESET}"
            print(f"  {p.name:<22} {p.position:<6} {p.age:>3}  "
                  f"{p.ortg_contrib:>+5.1f}  {p.drtg_contrib:>+5.1f}  "
                  f"{p.preferred_zone:<5}  {ppg_s}  {fg_s}  "
                  f"{happiness_emoji(p.happiness):<4}"
                  f"  {mot_c}{p.motivation}{RESET}")
        press_enter()

    # ── Commissioner's Desk (always-available proactive actions) ──────────────

    def _desk_flags(self, season: Season) -> list[str]:
        """Return a list of notable situation notices to surface on the commissioner's desk."""
        league = self.league
        flags  = []

        for team in league.teams:
            owner = team.owner
            if owner is None:
                continue

            # Owner has been Watching for 2+ seasons without escalating to Demand
            if owner.threat_level == THREAT_LEAN and owner._seasons_unhappy >= 2:
                flags.append(
                    f"{GOLD}▲{RESET}  {owner.name} ({team.name}) has been "
                    f"{GOLD}Watching{RESET} for {owner._seasons_unhappy} seasons"
                )

            # Franchise player in final year, unhappy, likely to leave
            star = team.roster[0] if team.roster else None
            if (star is not None
                    and star.contract_years_remaining == 1
                    and star.happiness < 0.55
                    and star.motivation != "loyalty"):
                flags.append(
                    f"{RED}⚠{RESET}  {team.name} franchise player is expiring "
                    f"and {RED}unhappy{RESET} — flight risk"
                )

            # Market engagement below starting baseline — slipping
            if team.market_engagement < 0.08:
                flags.append(
                    f"{MUTED}↘{RESET}  {team.franchise.city} engagement at "
                    f"{RED}{team.market_engagement:.0%}{RESET} — well below baseline"
                )

        # Fatigue alerts — playoff-bound teams with heavily loaded rosters
        n_playoff = (season.cfg.playoff_teams_override if season.cfg.playoff_teams_override > 0
                     else len(league.teams))  # post-season, all teams have finished
        playoff_teams = set(season.regular_season_standings[:season.playoff_teams]
                            if season.regular_season_standings else [])
        for team in league.teams:
            if team not in playoff_teams:
                continue
            fatigued = [p for p in team.roster
                        if p is not None and p.fatigue >= 0.35]
            if fatigued:
                names = ", ".join(p.name.split()[-1] for p in fatigued)
                max_fat = max(p.fatigue for p in fatigued)
                fat_c = RED if max_fat >= 0.50 else GOLD
                flags.append(
                    f"{fat_c}🔋{RESET}  {team.name} playoff-bound with "
                    f"{fat_c}high fatigue{RESET}: {names}"
                )

        # Rival league alerts
        rival = league.rival_league
        if rival and rival.active:
            strength_c = RED if rival.strength >= 0.70 else (GOLD if rival.strength >= 0.50 else CYAN)
            sl = rival_strength_label(rival.strength)
            flags.append(
                f"{strength_c}⚔{RESET}  Rival league active: {BOLD}{rival.name}{RESET}  "
                f"{strength_c}{sl}  ({rival.strength:.0%}){RESET}"
            )

        # Type B ringleader detection warning
        if (league._defection_warning_season is not None
                and league._defection_warning_season == season.number - 1
                and league.rival_league is None):
            rl_team = next(
                (t for t in league.teams if t.team_id == league._ringleader_team_id), None
            )
            if rl_team and rl_team.owner:
                flags.append(
                    f"{RED}⚠{RESET}  {RED}{BOLD}{rl_team.owner.name}{RESET} "
                    f"({rl_team.name}) is in contact with other ownership groups "
                    f"— {RED}defection risk{RESET}"
                )

        # Scandal alerts — surface before the owner meeting so you walk in informed
        _SCANDAL_LABELS = {
            "political_bribery": "bribery of city officials",
            "personal_misconduct": "personal misconduct",
            "financial_fraud": "financial fraud allegation",
        }
        for team in league.teams:
            action = self._owner_actions.get(team.team_id)
            if action and action["category"] == "scandal":
                label = _SCANDAL_LABELS.get(action["type"], "scandal")
                flags.append(
                    f"{RED}!{RESET}  {RED}{BOLD}{team.owner.name}{RESET} ({team.name}) — "
                    f"{RED}{label} — requires response in owner meeting{RESET}"
                )

        return flags

    def _commissioner_desk(self, season: Season):
        """Always shown — proactive tools the commissioner can use each season."""
        rule_change_used    = False
        showcase_used       = False
        invest_used         = False
        revenue_sharing_set = False

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

            # Contextual flags — notable situations worth attention
            flags = self._desk_flags(season)
            if flags:
                print()
                for f in flags:
                    print(f"  {f}")
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
                    f"{MUTED}Reward:{RESET} {GOLD}Strong{RESET}"
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

            if not revenue_sharing_set:
                options.append(
                    f"Revenue sharing  "
                    f"{MUTED}Cost:{RESET} {GOLD}Varies   {RESET}"
                    f"{MUTED}Risk:{RESET} {GREEN}Low      {RESET}"
                    f"{MUTED}Reward:{RESET} {CYAN}Owner mood{RESET}"
                )
                handlers.append("revenue_sharing")

            options.append(
                f"Schedule & format"
                f"{MUTED}Cost:{RESET} {GREEN}Free     {RESET}"
                f"{MUTED}Risk:{RESET} {GREEN}None     {RESET}"
                f"{MUTED}Reward:{RESET} {MUTED}Config{RESET}"
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
            elif action == "revenue_sharing":
                self._do_revenue_sharing(season)
                revenue_sharing_set = True
            elif action == "format":
                self._do_format_review(season)

    def _do_revenue_sharing(self, season: Season) -> None:
        """Redistribute a portion of the league treasury to loss-making teams.

        Levels:
          None  — no redistribution, treasury untouched
          Light — $5M pool split among loss-making teams proportional to deficit
          Heavy — $15M pool, same distribution

        Effect: each recipient team's owner gets a direct happiness boost
        proportional to the relief they receive. Small-market owners benefit most.
        """
        league = self.league
        sn = season.number
        clear()
        header("REVENUE SHARING", f"After Season {sn}")

        loss_teams = [
            (t, t.owner) for t in league.teams
            if t.owner is not None and t.owner.last_net_profit < 0
        ]

        if not loss_teams:
            print(f"\n  {GREEN}All teams ran a profit this season.{RESET}  "
                  f"No revenue sharing needed.\n")
            press_enter()
            return

        total_deficit = sum(-o.last_net_profit for _, o in loss_teams)

        print(f"\n  {len(loss_teams)} team(s) ran a loss this season "
              f"(total deficit: {RED}${total_deficit:.1f}M{RESET}):\n")
        print(f"  {'Team':<28} {'Owner':<24} {'P&L':>8}")
        divider()
        for team, owner in loss_teams:
            print(f"  {team.name:<28} {owner.name:<24} "
                  f"{RED}${owner.last_net_profit:+.1f}M{RESET}")

        print(f"\n  Treasury available: {GREEN}${self._treasury:.0f}M{RESET}\n")

        can_heavy = self._treasury >= 15.0
        can_light = self._treasury >= 5.0
        heavy_tag = "" if can_heavy else f"  {RED}(need $15M){RESET}"
        light_tag = "" if can_light else f"  {RED}(need $5M){RESET}"

        choice = choose([
            f"Heavy sharing  {RED}$15M{RESET} pool — meaningful relief, owner mood boost{heavy_tag}",
            f"Light sharing  {RED}$5M{RESET}  pool — gesture of support, modest boost{light_tag}",
            f"{MUTED}No sharing — treasury untouched{RESET}",
        ], "Revenue sharing level:", default=2)

        if choice == 2:
            print(f"\n  {MUTED}No revenue sharing this season.{RESET}")
            press_enter()
            return

        pool  = 15.0 if choice == 0 else 5.0
        label = "Heavy" if choice == 0 else "Light"

        if self._treasury < pool:
            print(f"\n  {RED}Insufficient treasury.{RESET}")
            press_enter()
            return

        self._treasury -= pool

        print(f"\n  {GREEN}{label} revenue sharing approved.{RESET}  "
              f"${pool:.0f}M distributed:\n")
        for team, owner in loss_teams:
            deficit   = -owner.last_net_profit
            share     = pool * (deficit / total_deficit)
            # Happiness boost: larger share = more relief, capped at +0.15
            hap_boost = min(0.15, share / max(pool, 1.0) * 0.20)
            owner.happiness = min(1.0, owner.happiness + hap_boost)
            # Soften threat level slightly if in LEAN
            if owner.threat_level == THREAT_LEAN and hap_boost >= 0.05:
                owner._seasons_unhappy = max(0, owner._seasons_unhappy - 1)
            print(f"  {team.name:<28} {MUTED}receives{RESET} "
                  f"{GREEN}+${share:.1f}M{RESET}  "
                  f"{MUTED}owner mood {'+' if hap_boost >= 0.005 else ''}"
                  f"{hap_boost:.0%}{RESET}")

        press_enter()

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

        PUSH = 0.08
        COUNTER_PUSH = 0.10

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
            # Full reset — meta snaps back near balance with a small noise component
            league.league_meta = random.gauss(0, cfg.meta_shock_spread)
            league._meta_velocity = 0.0
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
            tags = []
            if city in league.market_grudges:
                tags.append(f"{RED}grudge{RESET}")
            for t in teams:
                if t._consecutive_losing_seasons >= cfg.relocation_threshold - 3:
                    tags.append(f"{RED}relocation risk{RESET}")
                    break
            for t in teams:
                if t.owner and t.owner.threat_level == THREAT_DEMAND:
                    tags.append(f"{RED}owner demanding{RESET}")
                    break
                elif t.owner and t.owner.threat_level == THREAT_LEAN:
                    tags.append(f"{GOLD}owner watching{RESET}")
                    break
            tag_str = ("  " + "  ".join(tags)) if tags else ""
            print(f"  {i:>2}. {city:<20} {nicknames:<26} {pop_bar(avg_eng, 10)}{tag_str}")

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
            header("SCHEDULE & PLAYOFF FORMAT", f"After Season {sn}  ·  {n} teams")
            _show_risk_reward("Free", "None", "Config",
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

    # ── Owner meeting ─────────────────────────────────────────────────────────

    # ── Players' meeting ──────────────────────────────────────────────────────

    def _player_style_lean(self, player, team) -> str:
        """Return 'offensive', 'defensive', or 'balanced' for rule-change advocacy.

        Based on the ratio of the player's offensive contribution to their total
        contribution magnitude. High-ortg/low-drtg players want an offensive era;
        strong defenders with modest scoring want defense rewarded.
        """
        oc = player.ortg_contrib          # positive
        dc = abs(player.drtg_contrib)     # positive (drtg_contrib is negative)
        total = oc + dc
        if total < 1.0:
            return 'balanced'
        ratio = oc / total
        if ratio > 0.65:
            return 'offensive'
        if ratio < 0.38:
            return 'defensive'
        return 'balanced'

    def _player_feedback_text(self, player, team, season: Season) -> str:
        """Generate a player's meeting quote based on their situation."""
        league   = self.league
        owner    = team.owner
        expiring = player.contract_years_remaining <= 1
        is_champ = season.champion is team
        in_po    = any(team in (sr.seed1, sr.seed2)
                       for rnd in season.playoff_rounds for sr in rnd)
        relocation_threat = (owner is not None and
                             owner.threat_level in (THREAT_LEAN, THREAT_DEMAND))

        if player.motivation == MOT_WINNING:
            if is_champ:
                return ("We're champions. I'm exactly where I want to be. "
                        "Keep this core together and we'll do it again.")
            if in_po and player.happiness >= 0.60:
                return "We're building something real here. I'm committed to this team."
            if in_po and player.happiness < 0.60:
                return ("Making the playoffs isn't the ceiling. "
                        "I want to compete for a title, not just show up.")
            if expiring and player.happiness < 0.50:
                return ("My contract is up. I need to see this organization is serious "
                        "about winning before I commit.")
            if player.happiness < 0.45:
                return "I didn't come here to lose. Something has to change."
            return "I still believe in what we're building. But patience only goes so far."

        if player.motivation == MOT_MARKET:
            avg_metro = (sum(t.franchise.effective_metro for t in league.teams)
                         / len(league.teams)) if league.teams else 1.0
            big_market = team.franchise.effective_metro > avg_metro * 1.2
            if big_market and player.happiness >= 0.60:
                return "The spotlight here is everything. I'm exactly where I want to be."
            if big_market and expiring:
                return "I love this market. I'd like to stay — the right deal needs to be there."
            if not big_market and player.happiness < 0.50:
                return ("I've put in the work. I deserve a bigger stage. "
                        "My brand is being limited here.")
            if not big_market and expiring:
                return ("When my deal is up, I have to weigh my options. "
                        "Exposure matters for my career.")
            return "The market is decent. I'm making it work."

        # MOT_LOYALTY
        swt = player.seasons_with_team
        if relocation_threat:
            tenure = f"{swt} season{'s' if swt != 1 else ''}"
            return (f"I keep hearing rumors about this franchise moving. "
                    f"I've given {tenure} to this city. "
                    f"I need to know we're not going anywhere.")
        if swt >= 5:
            return "This is my home. Whatever comes next, I'm here."
        if swt >= 2:
            return "I'm starting to feel like this is really my city. I want to stay and build something."
        return "I'm still finding my footing here. So far, so good."

    def _player_audience(self, player, team, season: Season,
                         marketing_used: bool) -> bool:
        """Show a single player's feedback and offer limited commissioner actions.

        Returns True if the player's marketing slot was used.
        """
        league   = self.league
        sn       = season.number
        owner    = team.owner
        lean     = self._player_style_lean(player, team)
        meta     = league.league_meta

        clear()
        header("PLAYERS' MEETING", f"{player.name} — {team.name}")

        # Player card
        mood_c = (GREEN if player.happiness >= 0.60 else
                  GOLD  if player.happiness >= 0.40 else RED)
        ctr_tag = f"  {RED}(expiring){RESET}" if player.contract_years_remaining <= 1 else ""
        print(f"\n  {happiness_emoji(player.happiness)} {BOLD}{player.name}{RESET}  "
              f"{MUTED}{player.position} · Age {player.age} · "
              f"{player.motivation} · overall {player.overall:.1f}{RESET}")
        print(f"  {mood_c}{owner_happiness_label(player.happiness)}{RESET}  "
              f"{MUTED}Contract: {player.contract_years_remaining}yr remaining{RESET}"
              f"{ctr_tag}\n")

        # Quote
        quote = self._player_feedback_text(player, team, season)
        print(f"  \"{quote}\"\n")

        # Rule change ask
        if lean != 'balanced':
            direction  = "offensive" if lean == 'offensive' else "defensive"
            meta_dir   = "positive" if lean == 'offensive' else "negative"
            already    = ((lean == 'offensive' and meta > 0.03) or
                          (lean == 'defensive' and meta < -0.03))
            if already:
                print(f"  {MUTED}(Happy with the current {direction} lean of the era.){RESET}\n")
            else:
                ask_c = GOLD if lean == 'offensive' else CYAN
                print(f"  {ask_c}Also asking:{RESET} Push toward a more {direction} era  "
                      f"{MUTED}(meta now {meta:+.3f}){RESET}\n")

        # Options
        options = []
        actions = []

        can_market = not marketing_used and self._treasury >= 10.0
        market_tag = "" if can_market else (
            f"  {RED}(used){RESET}" if marketing_used else f"  {RED}(need $10M){RESET}"
        )
        options.append(
            f"Feature in league marketing  "
            f"{MUTED}$10M — popularity +12%, happiness +6%{RESET}{market_tag}"
        )
        actions.append("marketing" if can_market else None)

        # Rule change ask — only if they want a shift AND this season's change not yet used
        if lean != 'balanced' and not season.meta_shock:
            already = ((lean == 'offensive' and meta > 0.03) or
                       (lean == 'defensive' and meta < -0.03))
            if not already:
                n_prev   = self._rule_changes_made
                leg_cost = round((0.02 + 0.01 * min(6, n_prev)) * 0.70, 3)  # 30% discount
                direction = "offensive" if lean == 'offensive' else "defensive"
                options.append(
                    f"Honor rule change request  "
                    f"{MUTED}Push {direction} · leg -{leg_cost:.0%} (30% discount){RESET}"
                )
                actions.append("rule_change")

        # Stability pledge — if owner has a relocation threat
        reloc_threat = (owner is not None and
                        owner.threat_level in (THREAT_LEAN, THREAT_DEMAND))
        already_protected = (season.number < team._protected_until)
        if reloc_threat and not already_protected:
            options.append(
                f"Stability pledge  "
                f"{MUTED}Promise this team stays for 3 seasons — player happiness boost{RESET}"
            )
            actions.append("pledge")

        options.append(f"{MUTED}Continue{RESET}")
        actions.append(None)

        choice = choose(options, default=len(options) - 1)
        action = actions[choice]

        used_marketing = False

        if action == "marketing":
            self._treasury -= 10.0
            player.popularity = min(1.0, player.popularity + 0.12)
            player.happiness  = min(1.0, player.happiness  + 0.06)
            league.league_popularity = min(1.0, league.league_popularity + 0.005)
            print(f"\n  {GREEN}Done.{RESET} {player.name} featured in league marketing.  "
                  f"Popularity +12%  ·  Happiness +6%  ·  Treasury: ${self._treasury:.0f}M")
            used_marketing = True
            press_enter()

        elif action == "rule_change":
            push = 0.08 if lean == 'offensive' else -0.08
            league.league_meta = max(-league.cfg.meta_max,
                                     min(league.cfg.meta_max, meta + push))
            n_prev   = self._rule_changes_made
            leg_cost = round((0.02 + 0.01 * min(6, n_prev)) * 0.70, 3)
            league.legitimacy = max(0.0, league.legitimacy - leg_cost)
            self._rule_changes_made += 1
            league._meta_extreme_seasons = 0
            season.meta_shock = True
            player.happiness = min(1.0, player.happiness + 0.05)
            direction = "offensive" if lean == 'offensive' else "defensive"
            print(f"\n  {GREEN}Rule change approved.{RESET}  "
                  f"Meta: {meta:+.3f} → {league.league_meta:+.3f}  ({direction} push)")
            print(f"  Legitimacy: -{leg_cost:.0%}  ·  {player.name} approves.")
            press_enter()

        elif action == "pledge":
            team._protected_until = max(team._protected_until, sn + 3)
            player.happiness = min(1.0, player.happiness + 0.08)
            if owner is not None:
                # Constrains the owner's options — they know you've promised stability
                owner._relocation_cooldown_until = max(
                    owner._relocation_cooldown_until, sn + 3
                )
            print(f"\n  {GREEN}Stability pledged.{RESET}  "
                  f"{team.name} will not relocate for 3 seasons.")
            print(f"  {player.name} is relieved.  "
                  f"{MUTED}(Owner relocation demand blocked until Season {sn + 3}.){RESET}")
            press_enter()

        return used_marketing

    def _handle_players_meeting(self, season: Season) -> None:
        """Players' meeting: franchise star from each team gives their read.

        Always shown. Intelligence layer — surfaces mood, contract risk, and
        rule-change advocacy. Commissioner can feature a player in marketing
        (once per meeting), honor a rule-change request, or pledge team stability.
        """
        league = self.league
        sn     = season.number

        reps = [(t, t.roster[0]) for t in league.teams
                if t.roster and t.roster[0] is not None]
        if not reps:
            return

        marketing_used = False

        while True:
            clear()
            header("PLAYERS' MEETING", f"After Season {sn}")

            print(f"\n  {MUTED}{'':4}{'Player':<22} {'Team':<22} {'Mot':<4} "
                  f"{'Mood':<10} {'Ctr':>4}  Ask{RESET}\n")

            n_content = n_restless = n_unhappy = n_asks = 0
            for i, (team, player) in enumerate(reps, 1):
                mood_c = (GREEN if player.happiness >= 0.60 else
                          GOLD  if player.happiness >= 0.40 else RED)
                mood_str = owner_happiness_label(player.happiness)
                mot_str  = player.motivation[:3].title()
                ctr_str  = f"{player.contract_years_remaining}yr"
                exp_tag  = f"{RED}⚠{RESET}" if player.contract_years_remaining <= 1 else " "

                lean = self._player_style_lean(player, team)
                already = ((lean == 'offensive' and league.league_meta > 0.03) or
                           (lean == 'defensive' and league.league_meta < -0.03))
                if lean == 'offensive' and not already:
                    ask_str = f"{GOLD}+off{RESET}"
                    n_asks += 1
                elif lean == 'defensive' and not already:
                    ask_str = f"{CYAN}+def{RESET}"
                    n_asks += 1
                else:
                    ask_str = f"{MUTED}—{RESET}"

                if player.happiness >= 0.60:    n_content  += 1
                elif player.happiness >= 0.40:  n_restless += 1
                else:                           n_unhappy  += 1

                print(f"  {CYAN}[{i}]{RESET} {player.name:<22} {team.name:<22} "
                      f"{MUTED}{mot_str:<4}{RESET} "
                      f"{mood_c}{mood_str:<10}{RESET} "
                      f"{ctr_str} {exp_tag}  {ask_str}")

            # Summary
            print()
            parts = []
            if n_content:  parts.append(f"{GREEN}{n_content} content{RESET}")
            if n_restless: parts.append(f"{GOLD}{n_restless} restless{RESET}")
            if n_unhappy:  parts.append(f"{RED}{n_unhappy} unhappy{RESET}")
            if n_asks and not season.meta_shock:
                parts.append(f"{GOLD}{n_asks} requesting rule change{RESET}")
            print(f"  {' · '.join(parts)}")
            print()

            raw = prompt(
                "Enter a player number to hear their take, or Enter to continue:"
            ).strip()

            if not raw:
                break
            if not raw.isdigit():
                continue
            idx = int(raw) - 1
            if not (0 <= idx < len(reps)):
                continue

            team, player = reps[idx]
            used = self._player_audience(player, team, season, marketing_used)
            if used:
                marketing_used = True

    def _owner_outreach(self, team, owner, season: Season) -> None:
        """Proactive commissioner outreach to a single owner.

        Two options:
          Express confidence — small happiness boost, costs $5M
          Discuss concerns   — free; surfaces roster/market context the owner is thinking about
        """
        league = self.league
        sn = season.number
        clear()
        header("OWNER OUTREACH", f"Season {sn}")

        mood_c = (GREEN if owner.happiness >= 0.55 else
                  GOLD  if owner.happiness >= 0.35 else RED)
        print(f"\n  {BOLD}{owner.name}{RESET}  {MUTED}— {team.name} · {owner.motivation_label()}{RESET}")
        print(f"  Mood: {mood_c}{owner_happiness_label(owner.happiness)}{RESET}  "
              f"P&L: {(GREEN if owner.last_net_profit >= 0 else RED)}"
              f"${owner.last_net_profit:+.1f}M{RESET}  "
              f"Tenure left: {owner.tenure_left} seasons\n")

        choice = choose([
            f"Express confidence  {MUTED}($5M — small happiness boost, goodwill gesture){RESET}",
            f"Discuss concerns    {MUTED}(Free — roster & market context, no mechanical effect){RESET}",
            f"{MUTED}Cancel{RESET}",
        ], default=2)

        if choice == 0:
            if self._treasury >= 5.0:
                self._treasury -= 5.0
                owner.happiness = min(1.0, owner.happiness + 0.05)
                print(f"\n  {GREEN}Done.{RESET} {owner.name} appreciates the attention.  "
                      f"Mood +5%  ·  Treasury: ${self._treasury:.0f}M")
            else:
                print(f"\n  {RED}Insufficient treasury (need $5M).{RESET}")
            press_enter()

        elif choice == 1:
            # Surface the owner's private concerns using the roster/market signals
            clear()
            header("OWNER CONCERNS", f"{owner.name} — {team.name}")
            print()

            roster = [p for p in team.roster if p is not None]
            star   = team.roster[0] if team.roster else None

            # Roster signals
            concerns = []
            if star is not None and star.contract_years_remaining <= 1:
                flight_risk = star.happiness < 0.55 and star.motivation != "loyalty"
                tag = f"{RED}flight risk{RESET}" if flight_risk else f"{GOLD}expiring{RESET}"
                concerns.append(f"Franchise player contract: {tag}  "
                                 f"{MUTED}(happiness {star.happiness:.0%}, "
                                 f"{star.contract_years_remaining}yr left){RESET}")
            if star is not None and star.age >= 33:
                concerns.append(f"Franchise player age: {GOLD}{star.age}{RESET}  "
                                 f"{MUTED}(window is closing){RESET}")
            expiring = [p for p in roster if p.contract_years_remaining <= 1]
            if len(expiring) >= 2:
                concerns.append(f"{RED}{len(expiring)} players{RESET} expiring at season end")
            if roster and not any(p.overall >= 6 for p in roster):
                concerns.append(f"{RED}No player above replacement level{RESET} on this roster")

            # Market signals
            if team.market_engagement < 0.12:
                concerns.append(f"Market engagement: {RED}{team.market_engagement:.0%}{RESET}  "
                                 f"{MUTED}(below healthy baseline){RESET}")
            if team.popularity < 0.30:
                concerns.append(f"Popularity: {RED}{team.popularity:.0%}{RESET}  "
                                 f"{MUTED}(fan base is thin){RESET}")

            # P&L
            if owner.last_net_profit < 0:
                concerns.append(f"P&L: {RED}${owner.last_net_profit:+.1f}M loss this season{RESET}")

            if concerns:
                print(f"  {MUTED}What {owner.pronoun} is thinking about:{RESET}\n")
                for c in concerns:
                    print(f"  • {c}")
            else:
                print(f"  {GREEN}{owner.name} has no major concerns right now.{RESET}")
                print(f"  {MUTED}Roster is healthy, market is stable, financials are fine.{RESET}")

            if owner.grievance:
                print(f"\n  {GOLD}On record:{RESET} \"{owner.grievance}\"")

            print()
            press_enter()

    # ── Owner-initiated actions ───────────────────────────────────────────────

    def _generate_all_owner_actions(self, season: Season) -> dict:
        """Roll for owner-initiated actions this offseason. Returns {team_id: action}."""
        from owner import PERS_RENEGADE, MOT_MONEY, MOT_WINNING, MOT_LOCAL_HERO
        actions: dict = {}
        for team in self.league.teams:
            owner = team.owner
            if owner is None:
                continue
            if owner._action_cooldown > 0:
                owner._action_cooldown -= 1
                continue
            action = self._roll_owner_action(team, owner, season)
            if action is not None:
                actions[team.team_id] = action
                owner._action_cooldown = 2
        return actions

    def _roll_owner_action(self, team, owner, season: Season):
        from owner import PERS_RENEGADE, MOT_MONEY, MOT_WINNING, MOT_LOCAL_HERO
        prob = 0.28 + (0.15 if owner.personality == PERS_RENEGADE else 0.0)
        if random.random() > prob:
            return None

        pool: dict = {}
        def add(t, w): pool[t] = pool.get(t, 0) + w

        if owner.motivation == MOT_WINNING:
            add("talent_push", 4); add("fa_favor", 2)
        elif owner.motivation == MOT_MONEY:
            add("naming_rights", 4); add("gambling_sponsor", 3); add("shady_sponsor", 2)
        elif owner.motivation == MOT_LOCAL_HERO:
            add("marketing_push", 4); add("political_lobby", 2)

        if owner.personality == PERS_RENEGADE:
            add("gambling_sponsor", 2); add("political_bribery", 2)
            add("personal_misconduct", 2); add("financial_fraud", 1)

        if owner.happiness < 0.35:
            add("sell_interest", 5)

        if not pool:
            return None

        action_type = random.choices(list(pool), weights=list(pool.values()))[0]
        _SCANDAL  = {"political_bribery", "personal_misconduct", "financial_fraud"}
        _UNSAVORY = {"gambling_sponsor", "shady_sponsor", "political_lobby"}
        category = ("scandal"  if action_type in _SCANDAL  else
                    "unsavory" if action_type in _UNSAVORY else "proposal")
        return {"type": action_type, "category": category}

    def _handle_owner_action(self, team, owner, action: dict, season: Season) -> None:
        """Resolve a single owner-initiated action."""
        atype  = action["type"]
        sn     = season.number
        league = self.league
        fname  = team.franchise_at(sn).name

        # ── PROPOSALS ────────────────────────────────────────────────────────

        if atype == "talent_push":
            clear(); header("OWNER AGENDA — TALENT INVESTMENT", f"After Season {sn}")
            print(f"""
  {BOLD}{owner.name}{RESET}  {MUTED}{fname}{RESET}

  "{MUTED}We're close to something real. I want to make a serious investment
  in talent this offseason — my money, not the league's. But I need
  your public endorsement to make it official.{RESET}"

  {GREEN}[1] Endorse ($20M owner investment){RESET}  Talent boost next season. Owner {GREEN}+happy{RESET}.
  {GOLD}[2] Encourage without endorsing ($10M){RESET}  Smaller boost. Modest happiness.
  {RED}[3] Decline{RESET}                            Owner {GOLD}frustrated{RESET}.
""")
            while True:
                r = prompt("Decision [1/2/3]:").strip()
                if r in ("1","2","3"): break
            if r == "1":
                league._talent_boost_seasons_left = max(league._talent_boost_seasons_left, 1)
                league._talent_boost_delta = max(league._talent_boost_delta, 0.25)
                owner.happiness = min(1.0, owner.happiness + 0.12)
                print(f"  {GREEN}✓ Endorsed.{RESET} {owner.name}'s investment is confirmed.")
            elif r == "2":
                league._talent_boost_seasons_left = max(league._talent_boost_seasons_left, 1)
                league._talent_boost_delta = max(league._talent_boost_delta, 0.12)
                owner.happiness = min(1.0, owner.happiness + 0.06)
                print(f"  {GOLD}✓ Encouraged.{RESET} A smaller investment proceeds.")
            else:
                owner.happiness = max(0.0, owner.happiness - 0.06)
                print(f"  {RED}Declined.{RESET} {owner.name} is disappointed.")
            press_enter()

        elif atype == "fa_favor":
            clear(); header("OWNER AGENDA — QUIET FA ARRANGEMENT", f"After Season {sn}")
            print(f"""
  {BOLD}{owner.name}{RESET}  {MUTED}{fname}{RESET}

  "{MUTED}We're building something here. All I need is a little understanding
  when the next big name hits the market. A nudge in the right direction.
  Nothing that has to be on paper.{RESET}"

  {GREEN}[1] Agree quietly{RESET}  Owner {GREEN}+confidence{RESET}. Legitimacy {RED}−5%{RESET}.
  {RED}[2] Decline{RESET}        Owner {GOLD}mildly frustrated{RESET}. No cost.
""")
            while True:
                r = prompt("Decision [1/2]:").strip()
                if r in ("1","2"): break
            if r == "1":
                owner.happiness = min(1.0, owner.happiness + 0.10)
                league.legitimacy = max(0.0, league.legitimacy - 0.05)
                print(f"  {GOLD}Arrangement made.{RESET} {owner.name} believes you'll deliver.")
            else:
                owner.happiness = max(0.0, owner.happiness - 0.04)
                print(f"  {MUTED}Declined.{RESET} {owner.name} accepts it, for now.")
            press_enter()

        elif atype == "naming_rights":
            clear(); header("OWNER AGENDA — NAMING RIGHTS DEAL", f"After Season {sn}")
            companies = ["Apex Financial","QuickCash Credit","TurboFuel Energy",
                         "Pinnacle Lending","CoreBank Group","NovaTech Systems"]
            company = random.choice(companies)
            deal = random.randint(6, 14)
            print(f"""
  {BOLD}{owner.name}{RESET}  {MUTED}{fname}{RESET}

  "{MUTED}I've got a naming rights offer from {company} — ${deal}M per year.
  Strong money. I need your sign-off to finalize it.{RESET}"

  {GREEN}[1] Approve{RESET}  Owner revenue {GREEN}+${deal}M{RESET}. Arena renamed.
  {RED}[2] Decline{RESET}  Owner {GOLD}frustrated{RESET}.
""")
            while True:
                r = prompt("Decision [1/2]:").strip()
                if r in ("1","2"): break
            if r == "1":
                owner.last_net_profit  += deal
                owner.cumulative_profit += deal
                owner.happiness = min(1.0, owner.happiness + 0.08)
                print(f"  {GREEN}✓ Approved.{RESET} The {company} Arena is official.")
            else:
                owner.happiness = max(0.0, owner.happiness - 0.06)
                print(f"  {MUTED}Declined.{RESET} {owner.name} will find another way.")
            press_enter()

        elif atype == "marketing_push":
            clear(); header("OWNER AGENDA — COMMUNITY MARKETING PUSH", f"After Season {sn}")
            print(f"""
  {BOLD}{owner.name}{RESET}  {MUTED}{fname}{RESET}

  "{MUTED}Our community isn't fully behind us yet. A real promotional push —
  events, local media, outreach — could change that. I need you to fund it.{RESET}"

  {GREEN}[1] Fund it ($8M){RESET}   Popularity {GREEN}+6%{RESET} · Engagement {GREEN}+3%{RESET} · Owner {GREEN}happy{RESET}.
  {GOLD}[2] Half-fund ($4M){RESET}  Smaller boost.
  {RED}[3] Decline{RESET}          Owner {GOLD}disappointed{RESET}.
""")
            while True:
                r = prompt("Decision [1/2/3]:").strip()
                if r in ("1","2","3"): break
            if r == "1":
                if self._treasury >= 8.0:
                    self._treasury -= 8.0
                    team.popularity = min(1.0, team.popularity + 0.06)
                    team.market_engagement = min(1.0, team.market_engagement + 0.03)
                    owner.happiness = min(1.0, owner.happiness + 0.10)
                    print(f"  {GREEN}✓ Funded.{RESET} {team.franchise.city} is buzzing.")
                else:
                    print(f"  {RED}Insufficient treasury (${self._treasury:.0f}M).{RESET}")
                    owner.happiness = max(0.0, owner.happiness - 0.04)
            elif r == "2":
                if self._treasury >= 4.0:
                    self._treasury -= 4.0
                    team.popularity = min(1.0, team.popularity + 0.03)
                    team.market_engagement = min(1.0, team.market_engagement + 0.015)
                    owner.happiness = min(1.0, owner.happiness + 0.05)
                    print(f"  {GOLD}✓ Half-funded.{RESET} Modest boost to local interest.")
                else:
                    print(f"  {RED}Insufficient treasury.{RESET}")
            else:
                owner.happiness = max(0.0, owner.happiness - 0.07)
                print(f"  {MUTED}Declined.{RESET} {owner.name} is visibly disappointed.")
            press_enter()

        elif atype == "sell_interest":
            clear(); header("OWNER AGENDA — SALE INTEREST", f"After Season {sn}")
            print(f"""
  {BOLD}{owner.name}{RESET}  {MUTED}{fname}{RESET}

  "{MUTED}I've been thinking hard about my future here. This isn't working the
  way I hoped. I may be ready to step back and let someone else take over.{RESET}"

  {GREEN}[1] Begin sale process{RESET}         Ownership transition initiated.
  {GOLD}[2] Talk them out of it ($5M){RESET}   Show of confidence. Owner reconsiders.
  {RED}[3] Acknowledge, delay{RESET}           Noted. Revisit next season.
""")
            while True:
                r = prompt("Decision [1/2/3]:").strip()
                if r in ("1","2","3"): break
            if r == "1":
                owner.tenure_left = 0
                print(f"  {CYAN}Sale process initiated.{RESET} Buyers will be identified.")
            elif r == "2":
                if self._treasury >= 5.0:
                    self._treasury -= 5.0
                    owner.happiness = min(1.0, owner.happiness + 0.15)
                    owner._seasons_unhappy = max(0, owner._seasons_unhappy - 2)
                    print(f"  {GREEN}✓ Confidence shown.{RESET} {owner.name} agrees to stay.")
                else:
                    print(f"  {RED}Insufficient treasury.{RESET}")
            else:
                print(f"  {MUTED}Noted.{RESET} The conversation isn't over.")
            press_enter()

        # ── UNSAVORY PROPOSALS ────────────────────────────────────────────────

        elif atype == "gambling_sponsor":
            clear(); header("OWNER AGENDA — GAMBLING SPONSORSHIP", f"After Season {sn}")
            cos = ["BetMax Sports","Lucky Strike Wagering","Pinnacle Betting",
                   "GameDay Odds","WinLine Sports","PropBet Pro"]
            company = random.choice(cos)
            deal = random.randint(18, 28)
            print(f"""
  {BOLD}{owner.name}{RESET}  {MUTED}{fname}{RESET}

  "{MUTED}{company} is offering us a ${deal}M/year jersey patch and arena deal.
  It's real money. I need a decision from you.{RESET}"

  This is a gambling company. The money is significant. So is the exposure.

  {GREEN}[1] Approve publicly{RESET}   Revenue {GREEN}+${deal}M{RESET}. Legitimacy {RED}−10%{RESET}. Players & union notice.
  {GOLD}[2] Approve quietly{RESET}    Revenue {GOLD}+${deal//2}M{RESET}. Legitimacy {RED}−5%{RESET}. Lower visibility.
  {RED}[3] Reject{RESET}             Owner {RED}very unhappy{RESET}. League stays clean.
""")
            while True:
                r = prompt("Decision [1/2/3]:").strip()
                if r in ("1","2","3"): break
            if r == "1":
                owner.last_net_profit += deal; owner.cumulative_profit += deal
                owner.happiness = min(1.0, owner.happiness + 0.12)
                league.legitimacy = max(0.0, league.legitimacy - 0.10)
                league.cba_player_happiness_mod -= 0.02
                print(f"  {GOLD}Deal signed.{RESET} {company} patches go on the jersey. Eyebrows raised.")
            elif r == "2":
                amt = deal // 2
                owner.last_net_profit += amt; owner.cumulative_profit += amt
                owner.happiness = min(1.0, owner.happiness + 0.06)
                league.legitimacy = max(0.0, league.legitimacy - 0.05)
                print(f"  {MUTED}Quietly approved.{RESET} Deal structured to minimize attention.")
            else:
                owner.happiness = max(0.0, owner.happiness - 0.10)
                print(f"  {GREEN}Rejected.{RESET} {owner.name} is furious, but the league stays clean.")
            press_enter()

        elif atype == "shady_sponsor":
            clear(); header("OWNER AGENDA — SPONSORSHIP PROPOSAL", f"After Season {sn}")
            options = [
                ("payday loan company",        "EasyCash Now",    10, 0.06),
                ("cryptocurrency exchange",    "CoinVault",        9, 0.05),
                ("vape / tobacco alternative", "VapeLife",         8, 0.05),
                ("predatory lending service",  "FastFunds Direct", 11, 0.07),
            ]
            stype, sname, sdeal, shlegit = random.choice(options)
            print(f"""
  {BOLD}{owner.name}{RESET}  {MUTED}{fname}{RESET}

  "{MUTED}I've got a ${sdeal}M sponsorship offer from {sname}, a {stype}.
  The deal is ready to go. I want your sign-off.{RESET}"

  {GREEN}[1] Approve{RESET}  Revenue {GREEN}+${sdeal}M{RESET}. Legitimacy {RED}−{int(shlegit*100)}%{RESET}.
  {RED}[2] Reject{RESET}   Owner {GOLD}frustrated{RESET}.
""")
            while True:
                r = prompt("Decision [1/2]:").strip()
                if r in ("1","2"): break
            if r == "1":
                owner.last_net_profit += sdeal; owner.cumulative_profit += sdeal
                owner.happiness = min(1.0, owner.happiness + 0.07)
                league.legitimacy = max(0.0, league.legitimacy - shlegit)
                print(f"  {GOLD}Approved.{RESET} The {sname} deal is done.")
            else:
                owner.happiness = max(0.0, owner.happiness - 0.06)
                print(f"  {MUTED}Rejected.{RESET} {owner.name} is not pleased.")
            press_enter()

        elif atype == "political_lobby":
            clear(); header("OWNER AGENDA — POLITICAL LOBBYING", f"After Season {sn}")
            print(f"""
  {BOLD}{owner.name}{RESET}  {MUTED}{fname}{RESET}

  "{MUTED}We're working with city officials on a new arena financing deal —
  tax incentives, infrastructure support. Your public backing would
  close this. It's good for the city and good for the franchise.{RESET}"

  {GREEN}[1] Endorse publicly{RESET}   Treasury {GREEN}+$10M{RESET} (subsidy flows to league). Legitimacy {RED}−5%{RESET}.
  {GOLD}[2] Stay neutral{RESET}        No effect either way.
  {RED}[3] Distance yourself{RESET}   Owner {GOLD}frustrated{RESET}. Small legitimacy signal.
""")
            while True:
                r = prompt("Decision [1/2/3]:").strip()
                if r in ("1","2","3"): break
            if r == "1":
                self._treasury += 10.0
                owner.happiness = min(1.0, owner.happiness + 0.08)
                league.legitimacy = max(0.0, league.legitimacy - 0.05)
                print(f"  {GREEN}✓ Endorsed.{RESET} The arena financing deal moves forward.")
            elif r == "2":
                print(f"  {MUTED}You stay out of it.{RESET} {owner.name} understands.")
            else:
                owner.happiness = max(0.0, owner.happiness - 0.07)
                league.legitimacy = min(1.0, league.legitimacy + 0.02)
                print(f"  {MUTED}You distance yourself.{RESET} {owner.name} is annoyed.")
            press_enter()

        # ── SCANDALS ─────────────────────────────────────────────────────────

        elif atype == "political_bribery":
            clear(); header("SCANDAL — POLITICAL CORRUPTION", f"After Season {sn}")
            print(f"""
  {RED}{BOLD}BREAKING: {owner.name.upper()} PAID OFFICIALS FOR ARENA DEAL{RESET}

  Reports have emerged that {owner.name} ({fname}) made payments
  to city officials to secure arena permits and zoning approvals.
  The story is gaining traction. The league needs to respond.

  {RED}[1] Suspend & fine heavily{RESET}   Owner suspended 1 season. Legitimacy {GREEN}+8%{RESET}.
                               Owner {RED}furious{RESET}. Strong public message.
  {GOLD}[2] Fine only{RESET}               Public fine, no suspension.
                               Legitimacy {GREEN}+3%{RESET}. Owner {RED}unhappy{RESET}.
  {MUTED}[3] Ignore / bury it{RESET}        Legitimacy {RED}−12%{RESET}. League looks complicit.
""")
            while True:
                r = prompt("Decision [1/2/3]:").strip()
                if r in ("1","2","3"): break
            if r == "1":
                owner.happiness = max(0.0, owner.happiness - 0.20)
                owner._action_cooldown = 3
                league.legitimacy = min(1.0, league.legitimacy + 0.08)
                print(f"  {RED}Suspended.{RESET} {owner.name} faces a 1-season ban.")
            elif r == "2":
                owner.happiness = max(0.0, owner.happiness - 0.10)
                league.legitimacy = min(1.0, league.legitimacy + 0.03)
                print(f"  {GOLD}Fined.{RESET} {owner.name} pays. Questions linger.")
            else:
                league.legitimacy = max(0.0, league.legitimacy - 0.12)
                league.league_popularity = max(0.0, league.league_popularity - 0.03)
                print(f"  {MUTED}Buried.{RESET} For now.")
            press_enter()

        elif atype == "personal_misconduct":
            clear(); header("SCANDAL — OWNER MISCONDUCT", f"After Season {sn}")
            incidents = [
                (f"a recording has surfaced of {owner.name} making discriminatory remarks at a private event",
                 "The comments are circulating widely."),
                (f"{owner.name} was photographed in a compromising personal situation now running in the tabloids",
                 "Sponsors and players are watching how you respond."),
                (f"{owner.name} made inflammatory statements on social media that have gone viral",
                 "Players are talking. The union has issued a statement."),
                (f"{owner.name} has been accused of workplace misconduct by former staff",
                 "The allegation is credible. Your response defines the story."),
            ]
            incident, context = random.choice(incidents)
            print(f"""
  {RED}{BOLD}SCANDAL: {owner.name.upper()}{RESET}

  {incident.capitalize()}.
  {context}

  {RED}[1] Public sanction{RESET}     Required apology + remediation program.
                           Legitimacy {GREEN}+5%{RESET}. Players {GREEN}notice the response{RESET}. Owner {RED}unhappy{RESET}.
  {GOLD}[2] Private reprimand{RESET}   Handle behind closed doors. No immediate effect.
  {MUTED}[3] Ignore{RESET}             Legitimacy {RED}−8%{RESET}. Player morale {RED}−3%{RESET}. League looks complicit.
""")
            while True:
                r = prompt("Decision [1/2/3]:").strip()
                if r in ("1","2","3"): break
            if r == "1":
                owner.happiness = max(0.0, owner.happiness - 0.12)
                league.legitimacy = min(1.0, league.legitimacy + 0.05)
                league.cba_player_happiness_mod += 0.02
                print(f"  {GREEN}Sanctioned publicly.{RESET} Players respect the response.")
            elif r == "2":
                print(f"  {MUTED}Handled privately.{RESET} The story slows but doesn't die.")
            else:
                league.legitimacy = max(0.0, league.legitimacy - 0.08)
                league.cba_player_happiness_mod -= 0.03
                print(f"  {RED}Ignored.{RESET} The league's silence is its own statement.")
            press_enter()

        elif atype == "financial_fraud":
            clear(); header("SCANDAL — FINANCIAL FRAUD ALLEGATION", f"After Season {sn}")
            print(f"""
  {RED}{BOLD}ALLEGATION: {owner.name.upper()} — EMBEZZLEMENT{RESET}

  Auditors and league investigators have flagged serious irregularities
  in {owner.name}'s financial management of the {fname}.
  The allegation: embezzlement of franchise funds for personal use.

  {RED}[1] Force immediate sale{RESET}      Ownership transition now.
                               Legitimacy {GREEN}+10%{RESET}. Sends a clear message.
  {GOLD}[2] Suspend pending review{RESET}   Owner suspended during investigation.
                               Legitimacy {GREEN}+4%{RESET}. Outcome TBD.
  {MUTED}[3] Ignore{RESET}                  Legitimacy {RED}−15%{RESET}.
                               If fraud is later confirmed: catastrophic.
""")
            while True:
                r = prompt("Decision [1/2/3]:").strip()
                if r in ("1","2","3"): break
            if r == "1":
                league.legitimacy = min(1.0, league.legitimacy + 0.10)
                owner.tenure_left = 0
                print(f"  {RED}Sale forced.{RESET} {owner.name} is out.")
            elif r == "2":
                league.legitimacy = min(1.0, league.legitimacy + 0.04)
                owner._action_cooldown = 3
                owner.happiness = max(0.0, owner.happiness - 0.15)
                print(f"  {GOLD}Suspended pending review.{RESET} Investigation begins.")
            else:
                league.legitimacy = max(0.0, league.legitimacy - 0.15)
                print(f"  {RED}Ignored.{RESET} This will not stay buried.")
            press_enter()

    def _handle_owner_meeting(self, season: Season) -> None:
        """Owner meeting: always shown. Room read → optional outreach → agenda → transitions."""
        league = self.league
        sn = season.number

        owners_with_teams = [(t, t.owner) for t in league.teams if t.owner is not None]
        if not owners_with_teams:
            return

        demanding     = [(t, o) for t, o in owners_with_teams if o.threat_level == THREAT_DEMAND]
        watching      = [(t, o) for t, o in owners_with_teams if o.threat_level == THREAT_LEAN]
        transitioning = [(t, o) for t, o in owners_with_teams if o.tenure_left == 0]
        quiet         = [(t, o) for t, o in owners_with_teams
                         if o.threat_level not in (THREAT_DEMAND, THREAT_LEAN)]

        # ── Layer 1: Room Read — loop so user can meet multiple owners ──────────
        while True:
            clear()
            header("OWNER MEETING", f"After Season {sn}")
            print(f"\n  {MUTED}{'':4}{'Owner':<22} {'Team':<20} {'Motivation':<12} {'Mood':<10} {'P&L':>8}  Status{RESET}\n")

            for i, (team, owner) in enumerate(owners_with_teams, 1):
                mood_c  = (GREEN if owner.happiness >= 0.55 else
                           GOLD  if owner.happiness >= 0.35 else RED)
                pl_c    = GREEN if owner.last_net_profit >= 0 else RED
                pl_str  = f"{pl_c}${owner.last_net_profit:+.1f}M{RESET}"
                mot_str = owner.motivation_label()

                if owner.threat_level == THREAT_DEMAND:
                    status = f"{RED}Demanding ◀{RESET}"
                elif owner.threat_level == THREAT_LEAN:
                    status = f"{GOLD}Watching{RESET}"
                else:
                    status = f"{MUTED}—{RESET}"

                action = self._owner_actions.get(team.team_id)
                if action:
                    flag = (f"  {RED}[! scandal]{RESET}"   if action["category"] == "scandal"  else
                            f"  {GOLD}[→ unsavory]{RESET}"  if action["category"] == "unsavory" else
                            f"  {CYAN}[→ proposal]{RESET}")
                else:
                    flag = ""

                print(f"  {CYAN}[{i}]{RESET} {owner.name:<22} {MUTED}{team.name:<20} {mot_str:<12}{RESET} "
                      f"{mood_c}{owner_happiness_label(owner.happiness):<10}{RESET} "
                      f"{pl_str:>18}  {status}{flag}")

            print()
            parts = []
            if demanding:
                parts.append(f"{RED}{len(demanding)} demanding{RESET}")
            if watching:
                parts.append(f"{GOLD}{len(watching)} watching{RESET}")
            if quiet:
                parts.append(f"{MUTED}{len(quiet)} quiet{RESET}")
            if transitioning:
                parts.append(f"{CYAN}{len(transitioning)} transitioning{RESET}")
            print(f"  {' · '.join(parts)}")

            n_scandals  = sum(1 for t, _ in owners_with_teams
                              if self._owner_actions.get(t.team_id, {}).get("category") == "scandal")
            n_unsavory  = sum(1 for t, _ in owners_with_teams
                              if self._owner_actions.get(t.team_id, {}).get("category") == "unsavory")
            n_proposals = sum(1 for t, _ in owners_with_teams
                              if self._owner_actions.get(t.team_id, {}).get("category") == "proposal")
            action_parts = []
            if n_scandals:  action_parts.append(f"{RED}{n_scandals} scandal(s) requiring response{RESET}")
            if n_unsavory:  action_parts.append(f"{GOLD}{n_unsavory} unsavory proposal(s){RESET}")
            if n_proposals: action_parts.append(f"{CYAN}{n_proposals} proposal(s){RESET}")
            if action_parts:
                print(f"  {' · '.join(action_parts)}")

            lean_with_grievance = [(t, o) for t, o in watching if o.grievance]
            if lean_with_grievance:
                print(f"\n  {GOLD}Watching — grievances on record:{RESET}")
                for team, owner in lean_with_grievance:
                    print(f"  {MUTED}{owner.name} ({team.name}):{RESET}")
                    print(f"    {owner.grievance}")

            print()
            raw = prompt("Enter an owner number to meet, or Enter to continue:")
            if not raw:
                break   # proceed to agenda
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(owners_with_teams):
                    t, o = owners_with_teams[idx]
                    action = self._owner_actions.pop(t.team_id, None)
                    if action:
                        self._handle_owner_action(t, o, action, season)
                    if o.threat_level != THREAT_DEMAND:
                        self._owner_outreach(t, o, season)
            # loop back — redraws the list with updated flags

        # ── Layer 2: Agenda (DEMAND owners) ──────────────────────────────────
        for team, owner in demanding:
            self._handle_owner_demand(team, owner, season)

        # ── Layer 3: Ownership transitions ───────────────────────────────────
        for team, owner in list(owners_with_teams):
            if owner.tenure_left == 0:
                self._handle_ownership_transition(team, owner, season, forced=False)

    def _handle_owner_demand(self, team: Team, owner: Owner, season: Season) -> None:
        """Handle a DEMAND-level owner. Options depend on motivation and situation."""
        league = self.league
        sn = season.number
        fname = team.franchise_at(sn).name

        clear()
        header("OWNER DEMAND", f"After Season {sn}")

        mood_c = RED if owner.happiness < 0.35 else GOLD
        print(f"\n  {mood_c}{BOLD}{owner.name}{RESET}  {MUTED}— {fname} · {owner.motivation_label()}{RESET}\n")
        if owner.grievance:
            print(f"  \"{owner.grievance}\"\n")

        # Build options based on motivation
        options = []
        actions = []

        relocation_eligible_now = (sn >= owner._relocation_cooldown_until)

        if owner.motivation == MOT_MONEY:
            # Money owners want relocation to bigger market, or a subsidy
            if relocation_eligible_now:
                eligible = self._relocation_eligible(team, sn)
                if eligible and team.franchise.effective_metro < 5.0:
                    options.append(f"Approve relocation to a new market")
                    actions.append(("relocate", eligible))
            options.append(f"Grant league subsidy  {MUTED}($10M — buys patience){RESET}")
            actions.append(("subsidy", 10.0))

        elif owner.motivation == OWNER_MOT_WINNING:
            # Winning owners want talent investment, or relocation to attract FAs
            options.append(f"Invest in talent development  {MUTED}($15M — 3-season draft boost){RESET}")
            actions.append(("talent", 15.0))
            if relocation_eligible_now:
                eligible = self._relocation_eligible(team, sn)
                if eligible:
                    options.append(f"Approve relocation to a stronger market")
                    actions.append(("relocate", eligible))
            options.append(f"Grant league subsidy  {MUTED}($10M — buys patience){RESET}")
            actions.append(("subsidy", 10.0))

        else:  # local_hero
            options.append(f"Invest in community engagement  {MUTED}($10M — market engagement boost){RESET}")
            actions.append(("community", 10.0))
            options.append(f"Grant league subsidy  {MUTED}($10M — buys patience){RESET}")
            actions.append(("subsidy", 10.0))

        next_denial_count = owner.relocation_blocked + 1
        bp_prob = _owner_breaking_point_prob(owner, next_denial_count)
        if bp_prob == 0.0:
            deny_label = f"{MUTED}Deny — first denial, no immediate breaking point risk{RESET}"
        elif bp_prob >= 0.60:
            deny_label = f"{RED}Deny — {bp_prob:.0%} chance of breaking point{RESET}"
        elif bp_prob >= 0.30:
            deny_label = f"{GOLD}Deny — {bp_prob:.0%} chance of breaking point{RESET}"
        else:
            deny_label = f"{MUTED}Deny — {bp_prob:.0%} chance of breaking point{RESET}"
        options.append(deny_label)
        actions.append(("deny", 0.0))

        # Show franchise context
        avg_o, avg_d = _avg_ratings(league.teams)
        net = _rel_net(team.ortg, team.drtg, avg_o, avg_d)
        net_c = GREEN if net > 0 else (RED if net < 0 else MUTED)
        print(f"  Net rating: {net_c}{net:+.1f}{RESET}  "
              f"Popularity: {pop_bar(team.popularity, 12)}  "
              f"Losing streak: {RED if team._consecutive_losing_seasons >= 3 else MUTED}"
              f"{team._consecutive_losing_seasons}{RESET}")
        print(f"  Treasury: {GREEN if self._treasury >= 15 else RED}${self._treasury:.0f}M{RESET}\n")

        choice = choose(options, "Commissioner Decision:", default=len(options) - 1)
        action, cost = actions[choice]

        if action == "relocate":
            eligible = cost  # eligible is stored in cost slot here
            self._owner_relocation_prompt(team, owner, season, eligible)
        elif action == "talent":
            if self._treasury >= cost:
                self._treasury -= cost
                league.start_talent_investment(0.30, 3)
                owner.happiness = min(1.0, owner.happiness + 0.20)
                owner.threat_level = THREAT_LEAN
                owner._seasons_unhappy = 0
                print(f"\n  {GREEN}Approved.{RESET} 3-season talent boost funded. "
                      f"{owner.name} is encouraged.")
            else:
                print(f"\n  {RED}Insufficient treasury (need ${cost:.0f}M, have ${self._treasury:.0f}M).{RESET}")
                owner.relocation_blocked += 1
            press_enter()
        elif action in ("subsidy", "community"):
            if self._treasury >= cost:
                self._treasury -= cost
                owner.happiness = min(1.0, owner.happiness + 0.15)
                if action == "community":
                    team.market_engagement = min(1.0, team.market_engagement + 0.05)
                owner.threat_level = max(THREAT_LEAN, owner.threat_level - 1)
                owner._seasons_unhappy = max(0, owner._seasons_unhappy - 1)
                print(f"\n  {GREEN}Payment made.{RESET} {owner.name} accepts the gesture — for now.")
            else:
                print(f"\n  {RED}Insufficient treasury (need ${cost:.0f}M, have ${self._treasury:.0f}M).{RESET}")
                owner.relocation_blocked += 1
            press_enter()
        else:  # deny
            owner.relocation_blocked += 1
            print(f"\n  {RED}Request denied.{RESET} {owner.name} is not pleased.")
            bp_prob = _owner_breaking_point_prob(owner, owner.relocation_blocked)
            if bp_prob > 0 and random.random() < bp_prob:
                press_enter()
                self._handle_owner_breaking_point(team, owner, season)
                return
            press_enter()

    def _relocation_eligible(self, team: Team, sn: int) -> list:
        """Return list of eligible relocation destinations for a given team."""
        from collections import Counter
        league = self.league
        city_count = Counter(t.franchise.city for t in league.teams)
        return [
            f for f in league.reserve_pool
            if not f.secondary
            and city_count.get(f.city, 0) == 0
            and sn >= league._relocation_cooldowns.get(f.city, 0)
        ]

    def _owner_relocation_prompt(self, team: Team, owner: Owner, season: Season,
                                  eligible: list) -> None:
        """Owner-driven relocation picker — commissioner chooses the destination.

        All eligible markets are shown, sorted by the owner's motivation preference:
          money      → prefers larger effective_metro  (⭐ on top options)
          winning    → prefers high draw_factor         (⭐ on top options)
          local_hero → prefers similar-sized metro      (⭐ on closest matches)
        """
        from owner import MOT_MONEY, MOT_LOCAL_HERO
        league = self.league
        sn = season.number
        fname = team.franchise_at(sn).name
        cur_metro = team.franchise.effective_metro
        cur_draw  = team.franchise.draw_factor

        if not eligible:
            print(f"\n  {MUTED}No eligible destinations available right now.{RESET}")
            owner.relocation_blocked += 1
            bp_prob = _owner_breaking_point_prob(owner, owner.relocation_blocked)
            if bp_prob > 0 and random.random() < bp_prob:
                press_enter()
                self._handle_owner_breaking_point(team, owner, season)
            else:
                press_enter()
            return

        clear()
        header("RELOCATION — OWNER DEMAND", f"Season {sn}")

        # Sort by owner preference
        if owner.motivation == MOT_MONEY:
            dest_list = sorted(eligible, key=lambda f: -f.effective_metro)
            pref_label = f"{GOLD}prefers larger markets{RESET}"
            def _is_preferred(f) -> bool:
                return f.effective_metro >= cur_metro * 0.90
        elif owner.motivation == "winning":
            dest_list = sorted(eligible, key=lambda f: -f.draw_factor)
            pref_label = f"{GOLD}prefers high-draw markets{RESET}"
            def _is_preferred(f) -> bool:
                return f.draw_factor >= cur_draw * 0.95
        else:  # local_hero
            dest_list = sorted(eligible, key=lambda f: abs(f.effective_metro - cur_metro))
            pref_label = f"{GOLD}prefers similar-sized markets{RESET}"
            def _is_preferred(f) -> bool:
                return abs(f.effective_metro - cur_metro) / max(cur_metro, 0.1) <= 0.30

        mot_c = (GOLD if owner.motivation == MOT_MONEY else
                 GREEN if owner.motivation == "winning" else CYAN)
        print(f"\n  {owner.name} is demanding relocation.")
        print(f"  Motivation: {mot_c}{owner.motivation_label()}{RESET} — {pref_label}\n")

        dest_opts = []
        for f in dest_list:
            pref_star  = f" {GOLD}⭐{RESET}" if _is_preferred(f) else "   "
            grudge     = league.market_grudges.get(f.city, 0.0)
            grudge_note = (f"  {RED}⚠ grudge {grudge:.0%}{RESET}" if grudge > 0 else "")
            dest_opts.append(
                f"{pref_star} {f.name:<28} {MUTED}mkt {f.effective_metro:.1f}  draw {f.draw_factor:.2f}{RESET}"
                f"{grudge_note}"
            )

        dest_opts.append(f"{RED}Block relocation — grant 3-season protection (owner stays unhappy){RESET}")

        choice = choose(dest_opts, "Pick a destination (or block):", default=len(dest_opts) - 1)

        if choice < len(dest_list):
            new_franchise = dest_list[choice]
            old_city      = team.franchise.city
            old_metro     = team.franchise.effective_metro
            league.reserve_pool.remove(new_franchise)
            old_franchise = team.relocate(new_franchise, sn + 1)
            league.reserve_pool.append(old_franchise)
            league.relocation_log.append((
                sn, old_franchise.name, new_franchise.name,
                team._consecutive_losing_seasons, team._bottom2_in_streak, team.popularity,
            ))
            league.market_grudges[old_city]          = 1.0
            league._grudge_metro[old_city]           = old_metro
            league._relocation_cooldowns[old_city]   = sn + 4
            owner.happiness = min(1.0, owner.happiness + 0.30)
            owner.threat_level = THREAT_QUIET
            owner.grievance    = None
            owner._seasons_unhappy = 0
            owner.relocation_blocked = 0
            owner._relocation_cooldown_until = sn + 10
            print(f"\n  {GREEN}Approved.{RESET} {fname} → {new_franchise.name} from Season {sn+1}.")
            print(f"  {RED}{old_city} will hold a grudge.{RESET}  "
                  f"{MUTED}No relocated team may enter until Season {sn+4}.{RESET}")
            print(f"  {MUTED}{owner.name} will not be eligible to demand relocation again until Season {sn+10}.{RESET}")
        else:
            team._protected_until = max(team._protected_until, sn + 3)
            owner.relocation_blocked += 1
            print(f"\n  {MUTED}Relocation blocked. Protection granted through Season {sn+3}.{RESET}")
            bp_prob = _owner_breaking_point_prob(owner, owner.relocation_blocked)
            if bp_prob > 0 and random.random() < bp_prob:
                press_enter()
                self._handle_owner_breaking_point(team, owner, season)
                return

        press_enter()

    def _handle_owner_breaking_point(self, team: Team, owner: Owner, season: Season) -> None:
        """Owner has hit a breaking point after repeated denials.

        Two paths: facilitate an immediate sale (costs $20M, rolls for acceptance
        based on owner profile) or let it play out (free, but wires owner into
        Type B ringleader machinery — may sell quietly or recruit allies).
        """
        BUYOUT_COST = 20.0

        league = self.league
        sn     = season.number
        cfg    = league.cfg
        fname  = team.franchise_at(sn).name

        renegade = owner.personality == PERS_RENEGADE
        disloyal  = owner.loyalty    == LOY_LOW

        if renegade and disloyal:
            risk_c      = RED
            risk_label  = "HIGH"
            risk_note   = "Renegade + low loyalty — likely to recruit disgruntled owners."
            accept_prob = 0.65
        elif renegade or disloyal:
            risk_c      = GOLD
            risk_label  = "MEDIUM"
            risk_note   = ("Renegade personality — may look for allies."
                           if renegade else
                           "Low loyalty — may not go quietly.")
            accept_prob = 0.80
        else:
            risk_c      = MUTED
            risk_label  = "LOW"
            risk_note   = "Steady + loyal — more likely to sell and move on."
            accept_prob = 1.00   # always accepts a clean exit

        other_demand = sum(1 for t in league.teams
                           if t is not team and t.owner
                           and t.owner.threat_level == THREAT_DEMAND)
        other_lean   = sum(1 for t in league.teams
                           if t is not team and t.owner
                           and t.owner.threat_level == THREAT_LEAN)

        can_facilitate = self._treasury >= BUYOUT_COST

        clear()
        header("OWNER AT BREAKING POINT", f"After Season {sn}")
        print(f"\n  {RED}{BOLD}{owner.name}{RESET}  {MUTED}— {fname}{RESET}\n")
        print(f"  {owner.name} has been denied one too many times.")
        print(f"  The next move is theirs — but you can influence which path they take.\n")
        print(f"  Owner profile     {owner.personality}  ·  {owner.loyalty}")
        print(f"  Breakaway risk    {risk_c}{risk_label}{RESET}  —  {risk_note}")

        if other_demand or other_lean:
            print(f"\n  {GOLD}League climate:{RESET}  "
                  f"{other_demand} owner(s) demanding  ·  {other_lean} watching  "
                  f"— potential recruits exist.")
        else:
            print(f"\n  {MUTED}League climate: no other owners at crisis level — "
                  f"limited recruiting pool.{RESET}")

        print(f"\n  {BOLD}Two paths forward:{RESET}\n")

        # ── Option 1: Facilitate sale ─────────────────────────────────────────
        if can_facilitate:
            prob_str = f"{accept_prob:.0%} chance they accept" if accept_prob < 1.0 else "guaranteed acceptance"
            sale_label = (f"Facilitate an immediate sale  "
                          f"{MUTED}(${ BUYOUT_COST:.0f}M buyout incentive · {prob_str}){RESET}")
        else:
            sale_label = (f"{MUTED}Facilitate an immediate sale  "
                          f"(need ${BUYOUT_COST:.0f}M — insufficient treasury){RESET}")

        print(f"  {CYAN}[1]{RESET}  {sale_label}")
        if can_facilitate:
            print(f"       {MUTED}{owner.name} leaves. You choose the new ownership group.{RESET}")
        print()

        # ── Option 2: Let it play out ─────────────────────────────────────────
        print(f"  {CYAN}[2]{RESET}  Let it play out")
        print(f"       {MUTED}{owner.name} stays for now. Whether they sell or recruit")
        print(f"       depends on how many allies they can find in the ownership group.{RESET}")
        print(f"       {MUTED}Watch next season's owner meeting closely.{RESET}")

        opts = [sale_label if can_facilitate else f"{MUTED}Facilitate sale (insufficient funds){RESET}",
                "Let it play out"]
        choice = choose(opts, default=1 if not can_facilitate else 0)

        if choice == 0 and can_facilitate:
            self._treasury -= BUYOUT_COST
            if accept_prob >= 1.0 or random.random() < accept_prob:
                # Sale accepted
                print(f"\n  {GREEN}{owner.name} accepts the offer.{RESET}  "
                      f"Treasury: {GREEN}${self._treasury:.0f}M{RESET}")
                press_enter()
                self._handle_ownership_transition(team, owner, season, forced=True)
            else:
                # Sale rejected — money spent, falls through to ringleader path
                print(f"\n  {RED}{owner.name} rejected the offer — not interested in a quiet exit.{RESET}")
                print(f"  {MUTED}Treasury: ${self._treasury:.0f}M  (buyout cost still spent){RESET}")
                print(f"  {MUTED}They remain for now. Watch next season's owner meeting.{RESET}")
                press_enter()
                league._ringleader_team_id        = team.team_id
                league._ringleader_demand_seasons  = cfg.rival_b_ringleader_seasons
                league._defection_warning_season   = None
        else:
            # Let it play out — wire into Type B ringleader machinery
            league._ringleader_team_id        = team.team_id
            league._ringleader_demand_seasons  = cfg.rival_b_ringleader_seasons
            league._defection_warning_season   = None
            print(f"\n  {GOLD}Understood.{RESET} {owner.name} remains — for now.")
            print(f"  {MUTED}Keep an eye on the owner meeting next season.{RESET}")
            press_enter()

    def _handle_ownership_transition(self, team: Team, owner: Owner, season: Season,
                                      forced: bool = False) -> None:
        """Handle natural succession (tenure expired) or forced sale (walked out).

        forced=True → generate buyers and let commissioner pick the new owner.
        forced=False → heir inherits (70%) or sale (30%).
        """
        import random as _random
        from owner import generate_heir
        league = self.league
        sn = season.number
        fname = team.franchise_at(sn).name

        clear()
        if forced:
            header("OWNERSHIP TRANSITION", f"After Season {sn}")
            print(f"\n  {RED}{BOLD}{owner.name}{RESET} is selling {fname} and leaving the league.\n")
            print(f"  Three ownership groups have expressed interest.")
            print(f"  {MUTED}A change in ownership brings new priorities — review each group carefully.")
            print(f"  For {fname}, this could be a genuine fresh start.{RESET}\n")
        else:
            header("OWNERSHIP TRANSITION", f"After Season {sn}")
            print(f"\n  {owner.name}'s tenure with {fname} has run its course.\n")

        # Determine whether heir or sale
        use_sale = forced or _random.random() < 0.30

        if use_sale:
            buyers = generate_buyers(3)
            print(f"  {'Buyer':<26} {'Motivation':<12} {'Personality':<10} {'Loyalty':<10}  Notes")
            divider()
            for i, b in enumerate(buyers, 1):
                lok = f"{MUTED}loyal{RESET}" if b.loyalty == "loyal" else f"{RED}low loyalty{RESET}"
                pers = "steady" if b.personality == "steady" else f"{GOLD}renegade{RESET}"
                mot_c = (GREEN if b.motivation == OWNER_MOT_WINNING else
                         GOLD  if b.motivation == MOT_MONEY else CYAN)
                print(f"  {CYAN}[{i}]{RESET} {b.name:<26} {mot_c}{b.motivation_label():<12}{RESET} "
                      f"{pers:<20}  {lok}")

            choice = choose([f"Choose buyer {i+1}" for i in range(3)],
                            "Select new ownership group:", default=random.randint(0, 2))
            new_owner = buyers[choice]
        else:
            # Heir inherits
            new_owner = generate_heir(owner)
            print(f"  {owner.name}'s heir, {BOLD}{new_owner.name}{RESET}, takes over {fname}.\n"
                  f"  Motivation: {new_owner.motivation_label()}  "
                  f"Personality: {new_owner.personality}  "
                  f"Loyalty: {new_owner.loyalty}\n")
            press_enter()

        team.owner = new_owner
        if use_sale:
            print(f"\n  {GREEN}{new_owner.name}{RESET} now owns {fname}.")
            press_enter()

    def _handle_expansion_format_prompt(self, season: Season, n_added: int = 0):
        """Offer a format review after an expansion wave fires, showing before/after impact."""
        league  = self.league
        cfg     = league.cfg
        n       = len(league.teams)
        n_before = n - n_added

        # Effective gpp last season (before expansion teams join)
        gpp_before = cfg.games_per_pair if cfg.games_per_pair > 0 else _games_per_pair(max(n_before, 2))
        gs_before  = gpp_before * (n_before - 1) if n_before > 1 else 0

        # What auto-calc gives for new size
        gpp_auto = _games_per_pair(n)
        gs_auto  = gpp_auto * (n - 1)

        # Effective gpp next season (locked or auto)
        gpp_next = cfg.games_per_pair if cfg.games_per_pair > 0 else gpp_auto
        gs_next  = gpp_next * (n - 1)

        clear()
        header("EXPANSION FORMAT CHECK", f"After Season {season.number}")
        print(f"\n  The league grows from {BOLD}{n_before}{RESET} → {BOLD}{n} teams{RESET} next season.\n")

        # Before / after table
        print(f"  {'':28} {'This season':>12}  {'Next season':>12}")
        print(f"  {'Teams':<28} {n_before:>12}  {n:>12}")
        print(f"  {'Games per matchup':<28} {gpp_before:>10}×  {gpp_next:>10}×")
        print(f"  {'Regular season length':<28} {gs_before:>11}g  {gs_next:>11}g")

        # Flag if schedule shrinks
        if gs_next < gs_before:
            print(f"\n  {RED}⚠ Your season would shrink from {gs_before} to {gs_next} games.{RESET}")
            print(f"  {MUTED}With more teams, auto-calc reduces games per pair to stay near 40 games total.{RESET}")
            print(f"  {MUTED}You can lock a higher value in format review.{RESET}")
        elif gs_next > gs_before:
            print(f"\n  {GREEN}Season grows from {gs_before} to {gs_next} games with {n} teams.{RESET}")
        else:
            print(f"\n  {MUTED}Season length unchanged at {gs_next} games.{RESET}")

        po_auto = _playoff_count(n)
        print(f"\n  {MUTED}Playoff bracket auto-recommendation: {po_auto} teams ({po_auto/n*100:.0f}% qualify){RESET}\n")

        idx = choose([
            "Review & adjust format",
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
            self._handle_expansion_format_prompt(season, n_added=len(chosen))
            return
        else:
            print(f"\n  {MUTED}Expansion deferred.{RESET}")

        press_enter()

    # ── Collective bargaining ─────────────────────────────────────────────────

    def _handle_cba_negotiation(self, season: Season) -> None:
        """CBA fires every 5 seasons starting at season 5."""
        league = self.league
        sn = season.number

        # Reset all CBA terms — new deal replaces the old one completely
        league.cba_player_happiness_mod = 0.0
        league.cba_winning_happiness_mod = 0.0
        league.cba_market_happiness_mod = 0.0
        league.cba_loyalty_happiness_mod = 0.0
        league.cba_reloc_protection = False
        league.cba_veteran_protection = False
        league.cba_revenue_share_mod = 0.0
        league.work_stoppage_this_season = False

        # Player sentiment drives demand count and union tone
        all_players = [p for t in league.teams for p in t.roster if p is not None]
        avg_h = (sum(p.happiness for p in all_players) / len(all_players)
                 if all_players else 0.55)

        if avg_h < 0.38:
            n_demands, mood = 4, "furious"
        elif avg_h < 0.50:
            n_demands, mood = 3, "restless"
        elif avg_h < 0.62:
            n_demands, mood = 3, "watchful"
        else:
            n_demands, mood = 2, "content"

        if league._work_stoppages > 0:
            n_demands = min(5, n_demands + 1)  # union plays hardball after a prior stoppage

        pool = ["rev_share", "contract_sec", "fa_rights", "reloc_protect", "veteran_sec"]
        others = [d for d in pool if d != "rev_share"]
        selected = ["rev_share"] + random.sample(others, min(n_demands - 1, len(others)))
        random.shuffle(selected)

        DEMANDS = {
            "rev_share": {
                "title":     "REVENUE SHARING",
                "quote":     '"We fill these arenas. We deserve a greater share of what we generate."',
                "union_ask": "Increase player revenue share — commissioner treasury cut drops by 4%.",
                "accept":    (f"All player happiness {GREEN}+4%{RESET}/season."
                              f" Your revenue take {RED}−4%{RESET} of gross."),
                "counter":   f"All player happiness {GOLD}+2%{RESET}/season. No revenue impact.",
                "reject":    f"All player happiness {RED}−4%{RESET}/season. Stoppage risk {RED}+25%{RESET}.",
                "accept_s":  "+4% all player happiness; −4% your revenue share.",
                "counter_s": "+2% all player happiness.",
                "reject_s":  "−4% all player happiness; +25% stoppage risk.",
                "risk": 25,
            },
            "contract_sec": {
                "title":     "CONTRACT SECURITY",
                "quote":     '"Loyalty deserves stability. Short deals leave us exposed every few years."',
                "union_ask": "Longer maximum contract terms; job security for committed players.",
                "accept":    f"Loyalty-motivated players {GREEN}+5%{RESET} happiness per season.",
                "counter":   f"Loyalty-motivated players {GOLD}+2%{RESET} happiness.",
                "reject":    f"Loyalty-motivated players {RED}−4%{RESET} happiness. Risk {RED}+15%{RESET}.",
                "accept_s":  "+5% loyalty-player happiness.",
                "counter_s": "+2% loyalty-player happiness.",
                "reject_s":  "−4% loyalty-player happiness; +15% risk.",
                "risk": 15,
            },
            "fa_rights": {
                "title":     "FREE AGENCY RIGHTS",
                "quote":     '"Players should be able to choose their market. Free movement is a right."',
                "union_ask": "Expanded free agency access; fewer restrictions on player mobility.",
                "accept":    f"Market-motivated players {GREEN}+5%{RESET} happiness per season.",
                "counter":   f"Market-motivated players {GOLD}+2%{RESET} happiness.",
                "reject":    f"Market-motivated players {RED}−4%{RESET} happiness. Risk {RED}+15%{RESET}.",
                "accept_s":  "+5% market-player happiness.",
                "counter_s": "+2% market-player happiness.",
                "reject_s":  "−4% market-player happiness; +15% risk.",
                "risk": 15,
            },
            "reloc_protect": {
                "title":     "RELOCATION PROTECTIONS",
                "quote":     '"Players shouldn\'t pay the price when an owner moves a franchise."',
                "union_ask": "Binding player protections when franchises relocate cities.",
                "accept":    (f"Relocation threat penalty on player happiness {GREEN}halved{RESET}."
                              f" League mood {GREEN}+2%{RESET}."),
                "counter":   f"Token stability gesture. League mood {GOLD}+1%{RESET}.",
                "reject":    f"League mood {RED}−2%{RESET}. Stoppage risk {RED}+20%{RESET}.",
                "accept_s":  "Reloc penalty halved; league mood +2%.",
                "counter_s": "League mood +1%.",
                "reject_s":  "League mood −2%; +20% risk.",
                "risk": 20,
            },
            "veteran_sec": {
                "title":     "VETERAN SECURITY",
                "quote":     '"You can\'t just discard aging players. Experience deserves protection."',
                "union_ask": "Guaranteed roster protections for veterans past their competitive peak.",
                "accept":    f"Veterans past their prime {GREEN}+4%{RESET} happiness per season.",
                "counter":   f"Veterans {GOLD}+2%{RESET} happiness.",
                "reject":    f"Winning-motivated players {RED}−3%{RESET} happiness. Risk {RED}+10%{RESET}.",
                "accept_s":  "+4% veteran happiness.",
                "counter_s": "+2% veteran happiness.",
                "reject_s":  "−3% winning-player happiness; +10% risk.",
                "risk": 10,
            },
        }

        mood_c = {
            "furious": RED, "restless": GOLD, "watchful": GOLD, "content": GREEN,
        }[mood]

        clear()
        header("COLLECTIVE BARGAINING AGREEMENT", f"After Season {sn}")
        past_note = (f"  {RED}The union still remembers the last work stoppage.{RESET}\n"
                     if league._work_stoppages > 0 else "")
        print(f"""
{past_note}  The Players Association has demanded renegotiation.
  Union sentiment: {mood_c}{mood.capitalize()}{RESET} — avg player happiness {mood_c}{avg_h:.0%}{RESET}

  {BOLD}{n_demands}{RESET} demand(s) on the table.
  Rejected demands raise work stoppage risk; counters split the difference.
  CBA terms take effect Season {sn + 1} and expire after Season {sn + 5}.
""")
        press_enter()

        base_risk = 15 if avg_h < 0.40 else 0
        stoppage_risk = base_risk
        results = []  # (demand_id, decision_char, short_effect_str)

        for idx, did in enumerate(selected, 1):
            d = DEMANDS[did]
            risk_c = RED if stoppage_risk >= 40 else GOLD if stoppage_risk > 0 else GREEN

            clear()
            header("COLLECTIVE BARGAINING AGREEMENT", f"Demand {idx} of {n_demands}")
            print(f"""
  {BOLD}{d['title']}{RESET}

  {MUTED}{d['quote']}{RESET}

  Union asks:  {d['union_ask']}

  ─────────────────────────────────────────────────────────
  {GREEN}[1] Accept{RESET}   {d['accept']}
  {GOLD}[2] Counter{RESET}  {d['counter']}
  {RED}[3] Reject{RESET}   {d['reject']}
  ─────────────────────────────────────────────────────────
  Current work stoppage risk: {risk_c}{stoppage_risk}%{RESET}
""")
            default = random.choice(["1", "2", "3"])
            default_lbl = {
                "1": f"{GREEN}Accept{RESET}",
                "2": f"{GOLD}Counter{RESET}",
                "3": f"{RED}Reject{RESET}",
            }[default]
            while True:
                raw = prompt(f"Your decision [1/2/3]  (default: {default_lbl}): ").strip()
                if raw == "":
                    raw = default
                if raw in ("1", "2", "3"):
                    break

            if raw == "1":
                self._cba_apply(league, did, "accept")
                results.append((did, "1", d["accept_s"]))
            elif raw == "2":
                self._cba_apply(league, did, "counter")
                results.append((did, "2", d["counter_s"]))
            else:
                stoppage_risk += d["risk"]
                self._cba_apply(league, did, "reject")
                results.append((did, "3", d["reject_s"]))

        # Outcome summary
        clear()
        header("CBA OUTCOME", f"After Season {sn}")
        print()
        print(f"  {'Demand':<26} {'Decision':<14} Effect")
        divider()
        for did, dec, eff in results:
            d = DEMANDS[did]
            if dec == "1":
                dec_str = f"{GREEN}✓ Accepted{RESET}    "
            elif dec == "2":
                dec_str = f"{GOLD}~ Countered{RESET}   "
            else:
                dec_str = f"{RED}✗ Rejected{RESET}    "
            print(f"  {d['title']:<26} {dec_str} {MUTED}{eff}{RESET}")

        print()
        risk_pct = min(90, stoppage_risk)
        risk_c   = RED if risk_pct >= 40 else GOLD if risk_pct > 0 else GREEN
        print(f"  Work stoppage risk: {risk_c}{risk_pct}%{RESET}")
        print()

        roll = random.randint(1, 100)
        if roll <= risk_pct:
            league._work_stoppages += 1
            league.work_stoppage_this_season = True
            league._stoppage_hangover = 5   # 5-season fan resentment arc
            if risk_pct >= 55:
                print(f"  {RED}{BOLD}✗ WORK STOPPAGE — Season {sn + 1} cancelled{RESET}")
                print(f"  {RED}Players refuse to play. No games. No champion this year.{RESET}")
                league.legitimacy -= 0.15
                league.legitimacy  = max(0.0, league.legitimacy)
                league.cba_player_happiness_mod -= 0.08   # players also lose income
                # Engagement crash: city loses faith in the league as an institution
                for team in league.teams:
                    team.market_engagement = max(0.05, team.market_engagement * 0.50)
                # Popularity crash: team brands suffer when they go dark for a full season
                for team in league.teams:
                    team.popularity = max(0.05, team.popularity * 0.75)
                print(f"  {RED}Market engagement and team popularity crashed. Recovery will take years.{RESET}")
                # Full work stoppage can escalate to a Type C player walkout
                league._league_name = self.league_name
                if league.check_rival_c_trigger(sn):
                    self._walkout_just_formed = True
                else:
                    self._walkout_just_formed = False
            else:
                print(f"  {GOLD}{BOLD}⚠ PARTIAL WORK STOPPAGE — Season {sn + 1} shortened{RESET}")
                print(f"  {GOLD}Players strike part of the season. Fan engagement drops.{RESET}")
                league.legitimacy -= 0.08
                league.legitimacy  = max(0.0, league.legitimacy)
                league.cba_player_happiness_mod -= 0.04
                # Partial drops — fans frustrated but brands not destroyed
                for team in league.teams:
                    team.market_engagement = max(0.05, team.market_engagement * 0.70)
                for team in league.teams:
                    team.popularity = max(0.05, team.popularity * 0.85)
                print(f"  {GOLD}Engagement and team popularity down. Fans will be slow to return.{RESET}")
        else:
            if risk_pct == 0:
                print(f"  {GREEN}✓ Clean agreement — CBA ratified without incident.{RESET}")
            else:
                print(f"  {GREEN}✓ No work stoppage.{RESET} The CBA is ratified for 5 seasons.")

        print(f"\n  New terms effective Season {sn + 1}. Next CBA after Season {sn + 5}.")
        league._cba_log.append({
            "season":   sn,
            "results":  results,
            "risk":     risk_pct,
            "stoppage": league.work_stoppage_this_season,
        })
        press_enter()

    def _cba_apply(self, league, demand_id: str, decision: str) -> None:
        """Apply a single CBA demand outcome to league state."""
        if demand_id == "rev_share":
            if decision == "accept":
                league.cba_player_happiness_mod += 0.04
                league.cba_revenue_share_mod = 0.04
            elif decision == "counter":
                league.cba_player_happiness_mod += 0.02
            else:
                league.cba_player_happiness_mod -= 0.04

        elif demand_id == "contract_sec":
            if decision == "accept":
                league.cba_loyalty_happiness_mod += 0.05
            elif decision == "counter":
                league.cba_loyalty_happiness_mod += 0.02
            else:
                league.cba_loyalty_happiness_mod -= 0.04

        elif demand_id == "fa_rights":
            if decision == "accept":
                league.cba_market_happiness_mod += 0.05
            elif decision == "counter":
                league.cba_market_happiness_mod += 0.02
            else:
                league.cba_market_happiness_mod -= 0.04

        elif demand_id == "reloc_protect":
            if decision == "accept":
                league.cba_reloc_protection = True
                league.cba_player_happiness_mod += 0.02
            elif decision == "counter":
                league.cba_player_happiness_mod += 0.01
            else:
                league.cba_player_happiness_mod -= 0.02

        elif demand_id == "veteran_sec":
            if decision == "accept":
                league.cba_veteran_protection = True
            elif decision == "counter":
                league.cba_player_happiness_mod += 0.01
            else:
                league.cba_winning_happiness_mod -= 0.03

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
        ], "Commissioner Decision:", default=0)

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
