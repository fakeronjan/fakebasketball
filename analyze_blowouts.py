"""
Blowout Decomposition Analysis
================================
For games with a margin >= BLOWOUT_THRESHOLD, what fraction of that
margin came from each slot matchup (star vs star, co-star vs co-star,
starter vs starter, bench vs bench)?

Methodology
-----------
- Each game: map player_id → roster slot (0=Star, 1=Co-Star, 2=Starter, None=Bench)
- For blowout games: net_slot_contrib[slot] = winner_slot_pts - loser_slot_pts
- Sum and average across all blowout games
- Also compare to close games as baseline

Scenarios
---------
A) Equal teams (Avg vs Avg)     — blowouts from pure variance
B) Mismatch (Elite vs Cellar)   — blowouts from talent imbalance
C) Star-heavy vs balanced       — top-heavy vs spread-out talent
"""
from __future__ import annotations
import random
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from coach import ARCH_OFFENSIVE
from config import Config
from game import play_game
from player import Player, GUARD, WING, BIG, ZONE_3PT, ZONE_MID, ZONE_PAINT, MOT_WINNING
from team import Team
from franchises import Franchise

random.seed(42)

CFG = Config()
CFG.ortg_baseline = 85.0   # approved player_adj_scale = 85

N = 5_000
BLOWOUT  = 20   # >= 20 pt margin = blowout
CLOSE    = 8    # <= 8 pt margin = close game

SLOT_LABELS = {0: "Star", 1: "Co-Star", 2: "Starter", None: "Bench"}

# ──────────────────────────────────────────────────────────────────────────────
# Builder helpers
# ──────────────────────────────────────────────────────────────────────────────

_pid = 2_000_000

def _new_pid() -> int:
    global _pid
    _pid += 1
    return _pid

def make_player(pos=GUARD, ortg=0.0, drtg=0.0, zone=ZONE_3PT) -> Player:
    return Player(
        player_id=_new_pid(), name=f"P{_pid}", gender="male",
        position=pos, age=26, preferred_zone=zone,
        pace_contrib=0.0, motivation=MOT_WINNING,
        contract_years_remaining=3, contract_length=3,
        peak_ortg=ortg, peak_drtg=drtg,
        career_length=15, peak_season=0,
        start_mult=1.0, ceiling_noise=0.0,
        durability=1.0, seasons_played=0, fatigue=0.0,
    )

def make_team(tid, ortg, drtg, players) -> Team:
    from coach import Coach
    fran = Franchise(city=f"City{tid}", nickname=f"Team{tid}", metro=3.0, market_factor=1.0)
    t = Team(tid, fran, ortg=ortg, drtg=drtg, pace=95.0,
             style_3pt=0.25, popularity=0.50)
    t.roster = players + [None] * (3 - len(players))
    c = Coach(
        coach_id=str(_new_pid()), name="Coach", gender="male",
        archetype=ARCH_OFFENSIVE, flexibility=0.5, horizon=0.5, rating=0.5,
    )
    t.coach = c
    return t

# ──────────────────────────────────────────────────────────────────────────────
# Team tier definitions (same contribs as quality ladder calibration)
# ──────────────────────────────────────────────────────────────────────────────
#  (ortg, drtg, star_ortg, costar_ortg, starter_ortg, star_drtg, costar_drtg, starter_drtg)

TIER_ELITE  = (118.0, 104.0, 12.0,  6.0,  2.0, -7.0, -4.0, -1.0)
TIER_GOOD   = (115.0, 107.0,  8.0,  4.0,  1.5, -5.0, -2.0, -0.5)
TIER_AVG    = (110.0, 110.0,  3.0,  1.0,  0.0, -1.0,  0.0,  1.0)
TIER_BELOW  = (106.0, 113.0,  1.0, -0.5, -1.0,  1.5,  2.5,  3.5)
TIER_CELLAR = (103.0, 117.0, -1.0, -2.0, -2.0,  3.0,  4.0,  5.0)

def build_tier_team(tid, tier) -> tuple[Team, dict[int, int]]:
    """Build a team for a tier. Returns (team, pid_to_slot)."""
    ortg, drtg, so, co, sto, sd, cd, strd = tier
    star    = make_player(GUARD, ortg=so,  drtg=sd,   zone=ZONE_3PT)
    costar  = make_player(WING,  ortg=co,  drtg=cd,   zone=ZONE_MID)
    starter = make_player(BIG,   ortg=sto, drtg=strd, zone=ZONE_PAINT)
    t = make_team(tid, ortg, drtg, [star, costar, starter])
    pid_to_slot = {
        star.player_id:    0,
        costar.player_id:  1,
        starter.player_id: 2,
    }
    return t, pid_to_slot

# ──────────────────────────────────────────────────────────────────────────────
# Star-heavy vs Balanced (same overall ortg ≈ 110)
# Star-heavy: star=10, costar=0, starter=-2 (weighted: 10*.5+0*.3-2*.2 = 4.6... but
#             compute_ratings_from_roster uses those weights)
# Let's set ortg identically at 110 for both teams manually.
# ──────────────────────────────────────────────────────────────────────────────

def build_top_heavy(tid) -> tuple[Team, dict[int, int]]:
    """Star-heavy: monster star, weak co-star and starter. Same ~avg ortg/drtg."""
    star    = make_player(GUARD, ortg=12.0,  drtg=-3.0, zone=ZONE_3PT)
    costar  = make_player(WING,  ortg=-1.0,  drtg=2.0,  zone=ZONE_MID)
    starter = make_player(BIG,   ortg=-2.5,  drtg=3.0,  zone=ZONE_PAINT)
    t = make_team(tid, 110.0, 110.0, [star, costar, starter])
    return t, {star.player_id: 0, costar.player_id: 1, starter.player_id: 2}

def build_balanced(tid) -> tuple[Team, dict[int, int]]:
    """Balanced: spread evenly. Same overall ortg/drtg."""
    star    = make_player(GUARD, ortg=4.0, drtg=-1.5, zone=ZONE_3PT)
    costar  = make_player(WING,  ortg=3.0, drtg=-0.5, zone=ZONE_MID)
    starter = make_player(BIG,   ortg=2.0, drtg=0.5,  zone=ZONE_PAINT)
    t = make_team(tid, 110.0, 110.0, [star, costar, starter])
    return t, {star.player_id: 0, costar.player_id: 1, starter.player_id: 2}

# ──────────────────────────────────────────────────────────────────────────────
# Core analysis function
# ──────────────────────────────────────────────────────────────────────────────

def analyze_blowouts(
    team_a: Team,
    team_b: Team,
    pid_to_slot_a: dict[int, int],
    pid_to_slot_b: dict[int, int],
    label: str,
    n: int = N,
):
    """Run n games, split into blowouts and close games, decompose margins by slot."""

    # Accumulators: {slot: total_net_pts_in_blowouts}
    blowout_slot_net   = defaultdict(float)   # winner_slot - loser_slot, summed
    blowout_slot_abs   = defaultdict(float)   # |winner_slot - loser_slot|, summed
    close_slot_net     = defaultdict(float)
    close_slot_abs     = defaultdict(float)

    blowout_margins    = []
    close_margins      = []
    all_margins        = []

    # To decompose: for each game, get slot-level pts for team_a and team_b
    for g in range(n):
        # Alternate home/away to cancel home advantage
        if g % 2 == 0:
            home, away = team_a, team_b
            home_p2s, away_p2s = pid_to_slot_a, pid_to_slot_b
        else:
            home, away = team_b, team_a
            home_p2s, away_p2s = pid_to_slot_b, pid_to_slot_a

        result = play_game(home, away, CFG, league_meta=0.0)

        # Slot-level points: winner perspective
        home_slot_pts = defaultdict(int)
        away_slot_pts = defaultdict(int)

        for pid, log in result.home_logs.items():
            slot = home_p2s.get(pid, None)   # None = bench
            home_slot_pts[slot] += log.points

        for pid, log in result.away_logs.items():
            slot = away_p2s.get(pid, None)
            away_slot_pts[slot] += log.points

        hs, as_ = result.home_score, result.away_score
        margin  = abs(hs - as_)
        all_margins.append(margin)

        if hs > as_:
            winner_slots, loser_slots = home_slot_pts, away_slot_pts
        else:
            winner_slots, loser_slots = away_slot_pts, home_slot_pts

        net_by_slot = {
            s: winner_slots[s] - loser_slots[s]
            for s in [0, 1, 2, None]
        }

        if margin >= BLOWOUT:
            blowout_margins.append(margin)
            for s, net in net_by_slot.items():
                blowout_slot_net[s] += net
                blowout_slot_abs[s] += abs(net)
        elif margin <= CLOSE:
            close_margins.append(margin)
            for s, net in net_by_slot.items():
                close_slot_net[s] += net
                close_slot_abs[s] += abs(net)

    n_blowouts = len(blowout_margins)
    n_close    = len(close_margins)

    print(f"\n{'═' * 68}")
    print(f"  {label}")
    print(f"{'═' * 68}")
    print(f"  Games: {n}  |  Blowouts (≥{BLOWOUT}): {n_blowouts} ({100*n_blowouts/n:.1f}%)  |  "
          f"Close (≤{CLOSE}): {n_close} ({100*n_close/n:.1f}%)")

    if n_blowouts == 0:
        print("  [no blowouts recorded]")
        return

    avg_blowout = sum(blowout_margins) / n_blowouts
    avg_close   = sum(close_margins) / n_close if n_close else 0.0

    print(f"  Avg blowout margin: {avg_blowout:.1f} pts  |  "
          f"Avg close game margin: {avg_close:.1f} pts")
    print()

    # Slot contribution in blowout games
    total_abs = sum(blowout_slot_abs.values())

    print(f"  {'Slot':<12}  {'Avg net/game':>13}  {'Avg |diff|/game':>15}  {'% of abs margin':>15}")
    print(f"  {'-'*12}  {'-'*13}  {'-'*15}  {'-'*15}")
    for slot in [0, 1, 2, None]:
        lbl  = SLOT_LABELS[slot]
        net  = blowout_slot_net[slot] / n_blowouts
        absd = blowout_slot_abs[slot] / n_blowouts
        pct  = 100 * blowout_slot_abs[slot] / total_abs if total_abs else 0
        sign = "+" if net >= 0 else ""
        print(f"  {lbl:<12}  {sign}{net:>12.1f}  {absd:>15.1f}  {pct:>14.1f}%")

    print()
    print(f"  Context: same slots in CLOSE games (<= {CLOSE} pts)")
    total_close_abs = sum(close_slot_abs.values())
    for slot in [0, 1, 2, None]:
        lbl  = SLOT_LABELS[slot]
        absd = close_slot_abs[slot] / n_close if n_close else 0
        pct  = 100 * close_slot_abs[slot] / total_close_abs if total_close_abs else 0
        print(f"  {lbl:<12}  {'':>13}  {absd:>15.1f}  {pct:>14.1f}%  (close)")


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO A: Equal teams (Avg vs Avg)
# ──────────────────────────────────────────────────────────────────────────────

team_a1, p2s_a1 = build_tier_team(1, TIER_AVG)
team_b1, p2s_b1 = build_tier_team(2, TIER_AVG)
analyze_blowouts(team_a1, team_b1, p2s_a1, p2s_b1, "Scenario A: Equal Quality (Avg vs Avg)")

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO B: Mismatch (Elite vs Cellar)
# ──────────────────────────────────────────────────────────────────────────────

team_a2, p2s_a2 = build_tier_team(3, TIER_ELITE)
team_b2, p2s_b2 = build_tier_team(4, TIER_CELLAR)
analyze_blowouts(team_a2, team_b2, p2s_a2, p2s_b2, "Scenario B: Quality Mismatch (Elite vs Cellar)")

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO C: Elite vs Good
# ──────────────────────────────────────────────────────────────────────────────

team_a3, p2s_a3 = build_tier_team(5, TIER_ELITE)
team_b3, p2s_b3 = build_tier_team(6, TIER_GOOD)
analyze_blowouts(team_a3, team_b3, p2s_a3, p2s_b3, "Scenario C: Moderate Mismatch (Elite vs Good)")

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO D: Top-heavy vs Balanced (same overall quality)
# ──────────────────────────────────────────────────────────────────────────────

team_a4, p2s_a4 = build_top_heavy(7)
team_b4, p2s_b4 = build_balanced(8)
analyze_blowouts(team_a4, team_b4, p2s_a4, p2s_b4, "Scenario D: Top-Heavy vs Balanced (equal ortg)")

print()
