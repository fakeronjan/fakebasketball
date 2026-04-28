"""
Game engine validation suite.

Tests scoring, usage, and competitive outcomes across:
  1. Team quality ladder (elite → cellar-dweller)
  2. Roster shape (top-heavy vs balanced vs superteam vs one-man-band)
  3. Defensive stoppers (elite individual, team defense, positional matchups)
  4. Coach archetype effects on shot distribution
  5. Home-court and popularity effects

NBA reference benchmarks are noted throughout.
"""
from __future__ import annotations
import math
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from coach import (Coach, ARCH_CHEMISTRY, ARCH_WHISPERER, ARCH_DEFENSIVE,
                   ARCH_OFFENSIVE, ARCH_MOTIVATOR, ARCHETYPE_LABELS, generate_coach)
from config import Config
from franchises import ALL_FRANCHISES, Franchise
from game import play_game
from player import (Player, GUARD, WING, BIG, ZONE_PAINT, ZONE_MID, ZONE_3PT,
                    MOT_WINNING)
from team import Team

# ── Reproducibility ───────────────────────────────────────────────────────────
random.seed(99)

CFG  = Config()
N    = 2_000   # games per scenario — enough for tight confidence intervals

DIVIDER = "─" * 70

# ── Builder helpers ───────────────────────────────────────────────────────────

_pid_counter = 1_000_000   # start high to avoid any collision with league IDs


def _new_pid() -> int:
    global _pid_counter
    _pid_counter += 1
    return _pid_counter


def make_franchise(city: str = "Testville", nickname: str = "Testers") -> Franchise:
    return Franchise(city=city, nickname=nickname, metro=3.0, market_factor=1.0)


def make_coach(archetype: str = ARCH_OFFENSIVE) -> Coach:
    """Build a mid-rating, mid-flexibility coach of the given archetype."""
    return Coach(
        coach_id=str(_new_pid()),
        name=f"Coach {archetype}",
        gender="male",
        archetype=archetype,
        flexibility=0.5,   # mid: neither rigid nor adaptable
        horizon=0.5,
        rating=0.5,        # mid quality — modifiers scale to ~1× archetype base
    )


def make_player(
    position: str = GUARD,
    ortg_contrib: float = 0.0,
    drtg_contrib: float = 0.0,
    preferred_zone: str = ZONE_3PT,
    fatigue: float = 0.0,
) -> Player:
    """Build a player locked at peak with the exact given contributions."""
    # Set peak_season = 0, seasons_played = 0 → mult = 1.0 → contrib = peak
    p = Player(
        player_id=_new_pid(),
        name=f"P{_pid_counter}",
        gender="male",
        position=position,
        age=26,
        preferred_zone=preferred_zone,
        pace_contrib=0.0,
        motivation=MOT_WINNING,
        contract_years_remaining=3,
        contract_length=3,
        peak_ortg=ortg_contrib,    # mult=1.0 so ortg_contrib == peak_ortg
        peak_drtg=drtg_contrib,    # same for drtg
        career_length=15,
        peak_season=0,             # already at peak from season 0
        start_mult=1.0,
        ceiling_noise=0.0,
        durability=1.0,
        seasons_played=0,
        fatigue=fatigue,
    )
    return p


def make_team(
    tid: int,
    ortg: float,
    drtg: float,
    roster: list[Player],
    archetype: str = ARCH_OFFENSIVE,
    style_3pt: float = 0.25,
    pace: float = 95.0,
    popularity: float = 0.50,
) -> Team:
    """Build a Team with given ratings, roster, and coach archetype."""
    fran = make_franchise(f"City{tid}", f"Team{tid}")
    t = Team(tid, fran, ortg=ortg, drtg=drtg, pace=pace,
             style_3pt=style_3pt, popularity=popularity)
    t.roster = roster + [None] * (3 - len(roster))   # pad to 3 slots
    t.coach  = make_coach(archetype)
    return t


# ── Metric collectors ─────────────────────────────────────────────────────────

def run_matchup(
    team_a: Team,
    team_b: Team,
    n: int = N,
    swap_home: bool = True,
) -> dict:
    """Play n games between team_a (home) and team_b (away).

    With swap_home=True, alternates home/away each game so home advantage
    cancels out for win-rate measurements.
    """
    a_wins = b_wins = 0
    a_scores, b_scores = [], []
    margins = []
    # Per-player slot accumulators: keyed by player_id
    poss_by_pid:  dict[int, int]   = defaultdict(int)
    pts_by_pid:   dict[int, float] = defaultdict(int)
    pid_to_slot:  dict[int, int]   = {}
    for i, p in enumerate(team_a.roster):
        if p: pid_to_slot[p.player_id] = i
    for i, p in enumerate(team_b.roster):
        if p: pid_to_slot[p.player_id] = (i + 10)  # offset so we can split later

    for g in range(n):
        home, away = (team_a, team_b) if (g % 2 == 0 or not swap_home) else (team_b, team_a)
        result = play_game(home, away, CFG, league_meta=0.0)

        hs, as_ = result.home_score, result.away_score

        # Attribute scores back to team_a / team_b
        if home is team_a:
            a_scores.append(hs); b_scores.append(as_)
            margins.append(hs - as_)
            if hs > as_: a_wins += 1
            else:        b_wins += 1
        else:
            a_scores.append(as_); b_scores.append(hs)
            margins.append(as_ - hs)
            if as_ > hs: a_wins += 1
            else:        b_wins += 1

        # Collect usage from both log dicts
        for pid, log in list(result.home_logs.items()) + list(result.away_logs.items()):
            poss_by_pid[pid] += log.fga + log.fta // 2
            pts_by_pid[pid]  += log.points

    total_poss = sum(poss_by_pid.values())

    # Aggregate by slot for team_a (slots 0/1/2) and team_b (slots 10/11/12)
    slot_usage = {}
    for pid, poss in poss_by_pid.items():
        raw = pid_to_slot.get(pid, 99)
        slot_idx = raw if raw < 10 else raw - 10
        key = ("A" if raw < 10 else "B", slot_idx)
        slot_usage[key] = slot_usage.get(key, 0) + poss

    return dict(
        a_wins=a_wins,
        b_wins=b_wins,
        win_rate_a=a_wins / n,
        a_ppg=statistics.mean(a_scores),
        b_ppg=statistics.mean(b_scores),
        avg_margin=statistics.mean(margins),
        margin_sd=statistics.stdev(margins) if len(margins) > 1 else 0,
        poss_by_pid=dict(poss_by_pid),
        pts_by_pid=dict(pts_by_pid),
        total_poss=total_poss,
        pid_to_slot=pid_to_slot,
        slot_usage=slot_usage,
        n=n,
    )


def slot_pcts(res: dict, team: str = "A") -> tuple[float, float, float, float]:
    """Return (star%, costar%, starter%, bench%) for team_a or team_b."""
    su   = res["slot_usage"]
    tp   = res["total_poss"]
    s0   = su.get((team, 0), 0)
    s1   = su.get((team, 1), 0)
    s2   = su.get((team, 2), 0)
    bench = tp / 2 - s0 - s1 - s2   # bench = half total poss minus named-player poss for this team
    # total_poss is combined both teams; divide by 2 for one team's share
    half = tp / 2
    if half <= 0:
        return 0, 0, 0, 0
    return s0/half*100, s1/half*100, s2/half*100, bench/half*100


def player_ppg(res: dict, pid: int, n: int = N) -> float:
    return res["pts_by_pid"].get(pid, 0) / n


def blowout_rate(a_scores: list, b_scores: list, threshold: int = 20) -> float:
    margins = [abs(a - b) for a, b in zip(a_scores, b_scores)]
    return sum(1 for m in margins if m >= threshold) / len(margins)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Team Quality Ladder
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  SECTION 1 — TEAM QUALITY LADDER")
print(f"  NBA refs: avg ~114 PPG/team (2024), ~57% home win rate")
print(f"  Win-rate measured with home advantage cancelled (alternating home)")
print(f"{'═'*70}\n")

# Tier-calibrated rosters: ortg AND drtg contribs match the team rating tier.
# Negative drtg_contrib = good defender. Cellar players have negative ortg = below-avg shooters.
# Calibrated 2026-04-27: these contribs produce Elite vs Cellar ~85% win rate at player_adj_scale=85.
def balanced_roster(ortg_s0, ortg_s1, ortg_s2, drtg_s0, drtg_s1, drtg_s2):
    return [
        make_player(GUARD, ortg_contrib=ortg_s0, drtg_contrib=drtg_s0, preferred_zone=ZONE_3PT),
        make_player(WING,  ortg_contrib=ortg_s1, drtg_contrib=drtg_s1, preferred_zone=ZONE_MID),
        make_player(BIG,   ortg_contrib=ortg_s2, drtg_contrib=drtg_s2, preferred_zone=ZONE_PAINT),
    ]

QUALITY_LADDER = [
    # label,           ortg,   drtg,   s0_ortg s1_ortg s2_ortg  s0_drtg s1_drtg s2_drtg
    ("Elite contender",    118.0, 104.0, 12.0,  6.0,  2.0,  -7.0, -4.0, -1.0),
    ("Good playoff team",  115.0, 107.0,  8.0,  4.0,  1.5,  -5.0, -2.0, -0.5),
    ("Average team",       110.0, 110.0,  3.0,  1.0,  0.0,  -1.0,  0.0,  1.0),
    ("Below average",      106.0, 113.0,  1.0, -0.5, -1.0,   1.5,  2.5,  3.5),
    ("Cellar dweller",     103.0, 117.0, -1.0, -2.0, -2.0,   3.0,  4.0,  5.0),
]

print(f"  {'Matchup':<42} {'A PPG':>6} {'B PPG':>6} {'Margin':>7} {'A Win%':>7}")
print(f"  {'-'*42} {'-'*6} {'-'*6} {'-'*7} {'-'*7}")

for i, (la, oa, da, a0, a1, a2, ad0, ad1, ad2) in enumerate(QUALITY_LADDER):
    for j, (lb, ob, db, b0, b1, b2, bd0, bd1, bd2) in enumerate(QUALITY_LADDER):
        if j <= i: continue   # upper triangle only
        ta = make_team(100+i, oa, da, balanced_roster(a0, a1, a2, ad0, ad1, ad2))
        tb = make_team(200+j, ob, db, balanced_roster(b0, b1, b2, bd0, bd1, bd2))
        r  = run_matchup(ta, tb)
        print(f"  {la:<20} vs {lb:<18} "
              f"{r['a_ppg']:>6.1f} {r['b_ppg']:>6.1f} "
              f"{r['avg_margin']:>+7.1f} {r['win_rate_a']:>7.1%}")

# Same-quality games (used for home court calibration later)
print(f"\n  Same-quality mirrors (expected ~50% each):")
for la, oa, da, a0, a1, a2, ad0, ad1, ad2 in QUALITY_LADDER:
    ta = make_team(300, oa, da, balanced_roster(a0, a1, a2, ad0, ad1, ad2))
    tb = make_team(301, oa, da, balanced_roster(a0, a1, a2, ad0, ad1, ad2))
    r  = run_matchup(ta, tb)
    print(f"    {la:<22}  PPG {r['a_ppg']:.1f}/{r['b_ppg']:.1f}  "
          f"win% {r['win_rate_a']:.1%}  margin σ={r['margin_sd']:.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Roster Shape — same team quality, different talent distribution
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  SECTION 2 — ROSTER SHAPE (all teams 113 ORtg / 109 DRtg)")
print(f"  NBA refs: elite star 28-36% usage, balanced team 22-27% star")
print(f"{'═'*70}\n")

ORTG = 113.0
DRTG = 109.0

ROSTER_SHAPES = {
    "Top-heavy  [18, 4, 0]":   (18.0,  4.0,  0.0),
    "Balanced   [12, 10, 8]":  (12.0, 10.0,  8.0),
    "Superteam  [16, 15, 14]": (16.0, 15.0, 14.0),
    "One-man    [22, 3, 0]":   (22.0,  3.0,  0.0),
    "Mid-tier   [8,  6, 4]":   ( 8.0,  6.0,  4.0),
}

print(f"  {'Shape':<26} {'Star%':>6} {'CoStr%':>7} {'Start%':>7} {'Bench%':>7} {'Star PPG':>9}")
print(f"  {'-'*26} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*9}")

for label, (c0, c1, c2) in ROSTER_SHAPES.items():
    star   = make_player(GUARD, ortg_contrib=c0, drtg_contrib=-2.0, preferred_zone=ZONE_3PT)
    costar = make_player(WING,  ortg_contrib=c1, drtg_contrib=-1.0, preferred_zone=ZONE_MID)
    start  = make_player(BIG,   ortg_contrib=c2, drtg_contrib= 0.0, preferred_zone=ZONE_PAINT)

    ta = make_team(400, ORTG, DRTG, [star, costar, start])
    tb = make_team(401, ORTG, DRTG, balanced_roster(12.0, 8.0, 4.0))  # neutral opponent

    r  = run_matchup(ta, tb)
    s0, s1, s2, bench = slot_pcts(r, "A")
    star_ppg = player_ppg(r, star.player_id)
    print(f"  {label:<26} {s0:>6.1f} {s1:>7.1f} {s2:>7.1f} {bench:>7.1f} {star_ppg:>9.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: Defensive Stoppers
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  SECTION 3 — DEFENSIVE STOPPERS")
print(f"  NBA refs: elite lockdown reduces guarded player usage 3-8 ppts")
print(f"  (Kawhi on LeBron, Butler on Durant, Jrue on Harden)")
print(f"{'═'*70}\n")

# Offense: star-heavy [18, 6, 3] — star is a Guard
off_star   = make_player(GUARD, ortg_contrib=18.0, drtg_contrib=-2.0, preferred_zone=ZONE_3PT)
off_costar = make_player(WING,  ortg_contrib= 6.0, drtg_contrib=-1.0, preferred_zone=ZONE_MID)
off_start  = make_player(BIG,   ortg_contrib= 3.0, drtg_contrib= 0.0, preferred_zone=ZONE_PAINT)
off_team   = make_team(500, 115.0, 108.0, [off_star, off_costar, off_start])

# Defense configurations for the opposing team (110/110 strength)
def def_roster(g_drtg, w_drtg, b_drtg):
    return [
        make_player(GUARD, ortg_contrib=5.0, drtg_contrib=g_drtg, preferred_zone=ZONE_3PT),
        make_player(WING,  ortg_contrib=3.0, drtg_contrib=w_drtg, preferred_zone=ZONE_MID),
        make_player(BIG,   ortg_contrib=2.0, drtg_contrib=b_drtg, preferred_zone=ZONE_PAINT),
    ]

DEF_SCENARIOS = {
    "No stoppers          [0,  0,  0]":  ( 0.0,  0.0,  0.0),
    "Avg guard stopper    [-4, 0,  0]":  (-4.0,  0.0,  0.0),
    "Good guard stopper   [-7, 0,  0]":  (-7.0,  0.0,  0.0),
    "Elite guard stopper  [-10,0,  0]":  (-10.0, 0.0,  0.0),
    "Elite on wing (mismatch) [0,-10,0]":( 0.0,-10.0,  0.0),
    "All-defensive team   [-6,-6, -6]":  (-6.0, -6.0, -6.0),
}

print(f"  {'Defense setup':<42} {'Star%':>6} {'CoStr%':>7} {'Star PPG':>9} {'OffPPG':>7}")
print(f"  {'-'*42} {'-'*6} {'-'*7} {'-'*9} {'-'*7}")

baseline_star_pct = None
for label, (gd, wd, bd) in DEF_SCENARIOS.items():
    def_team = make_team(600, 110.0, 110.0, def_roster(gd, wd, bd))
    r = run_matchup(off_team, def_team)
    s0, s1, s2, bench = slot_pcts(r, "A")
    star_ppg = player_ppg(r, off_star.player_id)
    if baseline_star_pct is None:
        baseline_star_pct = s0
    delta = f"({s0 - baseline_star_pct:+.1f})" if baseline_star_pct is not None and label != list(DEF_SCENARIOS)[0] else "     "
    print(f"  {label:<42} {s0:>5.1f}{delta} {s1:>7.1f} {star_ppg:>9.1f} {r['a_ppg']:>7.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: Coach Archetype Effects
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  SECTION 4 — COACH ARCHETYPE EFFECTS")
print(f"  Star-heavy roster [18, 6, 3] vs neutral opponent")
print(f"  Star Whisperer should push star usage; Motivator should lift bench")
print(f"{'═'*70}\n")

NEUTRAL_DEF = make_team(700, 110.0, 110.0, def_roster(0.0, 0.0, 0.0))

COACHES = [
    (ARCH_OFFENSIVE,  "Offensive Innovator"),
    (ARCH_WHISPERER,  "Star Whisperer     "),
    (ARCH_MOTIVATOR,  "Motivator          "),
    (ARCH_CHEMISTRY,  "Culture Coach      "),
    (ARCH_DEFENSIVE,  "Defensive Mastermind"),
]

print(f"  {'Coach':<22} {'Star%':>6} {'CoStr%':>7} {'Start%':>7} {'Bench%':>7} {'Star PPG':>9}")
print(f"  {'-'*22} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*9}")

for arch, label in COACHES:
    s   = make_player(GUARD, ortg_contrib=18.0, drtg_contrib=-2.0, preferred_zone=ZONE_3PT)
    cs  = make_player(WING,  ortg_contrib= 6.0, drtg_contrib=-1.0, preferred_zone=ZONE_MID)
    st  = make_player(BIG,   ortg_contrib= 3.0, drtg_contrib= 0.0, preferred_zone=ZONE_PAINT)
    ot  = make_team(800, 115.0, 108.0, [s, cs, st], archetype=arch)

    def_t = make_team(801, 110.0, 110.0, def_roster(0.0, 0.0, 0.0))
    r = run_matchup(ot, def_t)
    s0, s1, s2, bench = slot_pcts(r, "A")
    star_ppg = player_ppg(r, s.player_id)
    print(f"  {label:<22} {s0:>6.1f} {s1:>7.1f} {s2:>7.1f} {bench:>7.1f} {star_ppg:>9.1f}")


# Same roster, superteam [16, 15, 14]:
print(f"\n  Same archetypes, balanced superteam [16, 15, 14]:")
print(f"  {'Coach':<22} {'Star%':>6} {'CoStr%':>7} {'Start%':>7} {'Bench%':>7}")
print(f"  {'-'*22} {'-'*6} {'-'*7} {'-'*7} {'-'*7}")

for arch, label in COACHES:
    s   = make_player(GUARD, ortg_contrib=16.0, drtg_contrib=-2.0, preferred_zone=ZONE_3PT)
    cs  = make_player(WING,  ortg_contrib=15.0, drtg_contrib=-1.0, preferred_zone=ZONE_MID)
    st  = make_player(BIG,   ortg_contrib=14.0, drtg_contrib= 0.0, preferred_zone=ZONE_PAINT)
    ot  = make_team(810, 116.0, 106.0, [s, cs, st], archetype=arch)
    def_t = make_team(811, 110.0, 110.0, def_roster(0.0, 0.0, 0.0))
    r = run_matchup(ot, def_t)
    s0, s1, s2, bench = slot_pcts(r, "A")
    print(f"  {label:<22} {s0:>6.1f} {s1:>7.1f} {s2:>7.1f} {bench:>7.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: Home Court & Popularity
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  SECTION 5 — HOME COURT & POPULARITY EFFECTS")
print(f"  NBA refs: ~57% home win rate across all eras")
print(f"  High-profile teams (LAL, GSW) historically ~62-65% home win rate")
print(f"{'═'*70}\n")

base_roster = balanced_roster(8.0, 5.0, 2.0)

POP_LEVELS = [
    ("Low-pop  (0.20)", 0.20),
    ("Mid-pop  (0.50)", 0.50),
    ("High-pop (0.80)", 0.80),
]

print(f"  {'Home team popularity':<24} {'Home Win%':>10} {'Home PPG':>9} {'Away PPG':>9}")
print(f"  {'-'*24} {'-'*10} {'-'*9} {'-'*9}")

for label, pop in POP_LEVELS:
    home_team = make_team(900, 110.0, 110.0, balanced_roster(8.0, 5.0, 2.0), popularity=pop)
    away_team = make_team(901, 110.0, 110.0, balanced_roster(8.0, 5.0, 2.0), popularity=0.50)

    h_wins = h_scores = a_scores = 0
    h_score_list, a_score_list = [], []
    for _ in range(N):
        result = play_game(home_team, away_team, CFG, league_meta=0.0)
        h_score_list.append(result.home_score)
        a_score_list.append(result.away_score)
        if result.home_score > result.away_score:
            h_wins += 1

    print(f"  {label:<24} {h_wins/N:>10.1%} {statistics.mean(h_score_list):>9.1f} {statistics.mean(a_score_list):>9.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: Score Distribution (close games / blowouts)
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  SECTION 6 — SCORE DISTRIBUTION")
print(f"  NBA refs: ~30% games decided ≤5 pts, ~15% blowouts ≥20 pts")
print(f"{'═'*70}\n")

DIST_SCENARIOS = [
    ("Equal teams (110/110)", 110.0, 110.0, 110.0, 110.0),
    ("Slight edge (113/108 vs 110/110)", 113.0, 108.0, 110.0, 110.0),
    ("Clear edge (116/106 vs 107/114)", 116.0, 106.0, 107.0, 114.0),
]

print(f"  {'Scenario':<40} {'Close≤5':>8} {'Mid 6-19':>9} {'Blow≥20':>8} {'Avg Δ':>7}")
print(f"  {'-'*40} {'-'*8} {'-'*9} {'-'*8} {'-'*7}")

for label, oa, da, ob, db in DIST_SCENARIOS:
    ta = make_team(950, oa, da, balanced_roster(6.0, 3.0, 1.0))
    tb = make_team(951, ob, db, balanced_roster(6.0, 3.0, 1.0))
    margins = []
    for g in range(N):
        home, away = (ta, tb) if g % 2 == 0 else (tb, ta)
        result = play_game(home, away, CFG, league_meta=0.0)
        margins.append(abs(result.home_score - result.away_score))
    close   = sum(1 for m in margins if m <= 5)  / N
    mid     = sum(1 for m in margins if 6 <= m <= 19) / N
    blowout = sum(1 for m in margins if m >= 20) / N
    avg_abs = statistics.mean(margins)
    print(f"  {label:<40} {close:>8.1%} {mid:>9.1%} {blowout:>8.1%} {avg_abs:>7.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 7: Full season scoring leaders (PPG distribution)
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  SECTION 7 — PER-GAME SCORING LEADER DISTRIBUTION (400 games × 8 players)")
print(f"  NBA refs: scoring titles 28-36 PPG; 40+ PPG is Wilt/Jordan-rare")
print(f"{'═'*70}\n")

# Simulate a mini 8-team round-robin (each pair plays once each direction = 56 games)
# for multiple independent 82-game-equivalent 'seasons'

ROSTER_CONFIGS = [
    # (star ortg, costar ortg, starter ortg)
    (18.0,  6.0, 2.0),   # team A: top-heavy
    (14.0, 12.0, 8.0),   # team B: balanced elite
    (12.0, 10.0, 6.0),   # team C: balanced good
    ( 8.0,  5.0, 2.0),   # team D: mid
    (16.0,  4.0, 1.0),   # team E: another star-driven
    (10.0,  8.0, 5.0),   # team F: balanced mid
    ( 6.0,  4.0, 2.0),   # team G: weak
    (20.0,  3.0, 0.0),   # team H: god + scrubs
]

MINI_TEAMS = []
for i, (c0, c1, c2) in enumerate(ROSTER_CONFIGS):
    star   = make_player(GUARD, ortg_contrib=c0, drtg_contrib=-2.0, preferred_zone=ZONE_3PT)
    costar = make_player(WING,  ortg_contrib=c1, drtg_contrib=-1.0, preferred_zone=ZONE_MID)
    start  = make_player(BIG,   ortg_contrib=c2, drtg_contrib= 0.0, preferred_zone=ZONE_PAINT)
    # Team ORtg roughly derived from weighted contrib (50/30/20)
    team_ortg = 110.0 + 0.50*c0 + 0.30*c1 + 0.20*c2
    team_drtg = 110.0  # all neutral defense
    t = make_team(2000+i, team_ortg, team_drtg, [star, costar, start])
    MINI_TEAMS.append((t, [star, costar, start]))

NUM_MINI_SEASONS = 30
GAMES_PER_PAIR   = 2   # each pair plays 2 games — home and away

scoring_leader_ppg = []
all_star_ppg       = []   # every star's season avg

for season in range(NUM_MINI_SEASONS):
    season_pts: dict[int, int] = defaultdict(int)
    season_gms: dict[int, int] = defaultdict(int)

    # Build pid→player lookup
    pid_to_player: dict[int, Player] = {}
    for t, players in MINI_TEAMS:
        for p in players:
            if p: pid_to_player[p.player_id] = p

    for i, (ta, _) in enumerate(MINI_TEAMS):
        for j, (tb, _) in enumerate(MINI_TEAMS):
            if i == j: continue
            for _ in range(GAMES_PER_PAIR):
                result = play_game(ta, tb, CFG, league_meta=0.0)
                for pid, log in list(result.home_logs.items()) + list(result.away_logs.items()):
                    if pid in pid_to_player:
                        season_pts[pid] += log.points
                        season_gms[pid] += 1

    # Per-player PPG this mini-season
    ppg_this_season = {pid: season_pts[pid] / season_gms[pid]
                       for pid in season_pts if season_gms[pid] >= 5}

    if ppg_this_season:
        top = max(ppg_this_season.values())
        scoring_leader_ppg.append(top)
        # Collect all star ppgs
        for t, players in MINI_TEAMS:
            star = players[0]
            if star.player_id in ppg_this_season:
                all_star_ppg.append(ppg_this_season[star.player_id])

if scoring_leader_ppg:
    sl = sorted(scoring_leader_ppg, reverse=True)
    p95 = sl[max(0, int(len(sl)*0.05))]
    count_40 = sum(1 for x in scoring_leader_ppg if x >= 40)
    count_36 = sum(1 for x in scoring_leader_ppg if x >= 36)
    print(f"  Scoring leader PPG across {NUM_MINI_SEASONS} seasons:")
    print(f"    Mean:    {statistics.mean(scoring_leader_ppg):.1f}")
    print(f"    Median:  {statistics.median(scoring_leader_ppg):.1f}")
    print(f"    Max:     {sl[0]:.1f}")
    print(f"    95th pct:{p95:.1f}")
    print(f"    36+ PPG seasons: {count_36} / {NUM_MINI_SEASONS}")
    print(f"    40+ PPG seasons: {count_40} / {NUM_MINI_SEASONS}  (NBA: basically never)")

if all_star_ppg:
    print(f"\n  All stars' PPG distribution (every star, every season):")
    print(f"    Mean: {statistics.mean(all_star_ppg):.1f}  "
          f"Median: {statistics.median(all_star_ppg):.1f}  "
          f"Max: {max(all_star_ppg):.1f}  "
          f"Min: {min(all_star_ppg):.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# Summary vs NBA Benchmarks
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'═'*70}")
print("  BENCHMARK SUMMARY")
print(f"{'═'*70}")
print("""
  Metric                        NBA Reference        Model target
  ─────────────────────────────────────────────────────────────
  Avg team score                112–118 PPG          105–115 PPG
  Equal-team home win rate      ~57%                 54–60%
  High-pop home win rate        62–65% (LAL/GSW)     58–64%
  Close games (≤5 pt margin)    ~30%                 25–35%
  Blowouts (≥20 pt margin)      ~15%                 10–20%
  Scoring leader avg PPG        28–34                28–35
  Scoring leader max            36–38 (rare 40+)     ≤42 (40+ very rare)
  Elite star usage              28–35%               26–32%
  Balanced star usage           22–27%               24–28%
  Star Whisperer vs neutral     +3–5 ppt star usage  +3–5 ppt
  Elite stopper vs star         −3–8 ppt star usage  −3–6 ppt
""")

print("Done.")
