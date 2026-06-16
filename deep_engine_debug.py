"""
Supplementary diagnostic script — investigates surprising findings from the main analysis.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))

from player import Player, GUARD, WING, BIG, ZONE_3PT, ZONE_PAINT, ZONE_MID, _career_mult
from team import Team
from game import play_game, _compute_make_pct, _game_pace
from config import Config
from franchises import Franchise

cfg = Config()
_pid = 9000
_fid = 9000

def _player(position, p_ortg, p_drtg, zone=None, seasons_played=4, peak_season=4, career_length=14):
    global _pid
    _pid += 1
    if zone is None:
        zone = ZONE_3PT if position == GUARD else (ZONE_PAINT if position == BIG else ZONE_MID)
    return Player(
        player_id=_pid, name=f"P{_pid}", gender="male",
        position=position, age=26, preferred_zone=zone, pace_contrib=0.0,
        motivation="winning", contract_years_remaining=3, contract_length=3,
        peak_ortg=p_ortg, peak_drtg=p_drtg, career_length=career_length,
        peak_season=peak_season, start_mult=0.78, ceiling_noise=0.0, durability=0.80,
        seasons_played=seasons_played,
    )

def _franchise():
    global _fid
    _fid += 1
    return Franchise(city=f"C{_fid}", nickname="T", metro=5.0, lat=40.0, lon=-74.0)

def make_team(players):
    global _fid
    t = Team(team_id=_fid, franchise=_franchise())
    t.roster = (players + [None, None, None])[:3]
    t.coach = None
    t.popularity = 0.5
    t.compute_ratings_from_roster(cfg)
    return t

def win_rate(a, b, n=1000):
    wins = 0
    for i in range(n):
        if i < n // 2:
            r = play_game(a, b, cfg, home_advantage=0.0)
            if r.winner is a: wins += 1
        else:
            r = play_game(b, a, cfg, home_advantage=0.0)
            if r.winner is b: wins += 1
    return wins / n

print("=" * 60)
print("DIAGNOSTIC A — Score Distribution (1000 games, ELITE vs LOW)")
print("=" * 60)

elite_t = make_team([_player(GUARD,11.0,-8.5), _player(WING,11.0,-8.5), _player(BIG,11.0,-8.5)])
low_t   = make_team([_player(GUARD,1.0,1.0),   _player(WING,1.0,1.0),   _player(BIG,1.0,1.0)])

print(f"ELITE: ORtg={elite_t.ortg:.1f} DRtg={elite_t.drtg:.1f}")
print(f"LOW:   ORtg={low_t.ortg:.1f} DRtg={low_t.drtg:.1f}")

scores_e, scores_l = [], []
wins_e = 0
N = 1000
for i in range(N):
    r = play_game(elite_t, low_t, cfg, home_advantage=0.0)
    scores_e.append(r.home_score)
    scores_l.append(r.away_score)
    if r.winner is elite_t: wins_e += 1

import statistics
print(f"\nOver {N} games:")
print(f"  ELITE avg score: {sum(scores_e)/N:.1f}  stdev: {statistics.stdev(scores_e):.1f}")
print(f"  LOW   avg score: {sum(scores_l)/N:.1f}  stdev: {statistics.stdev(scores_l):.1f}")
print(f"  ELITE win rate:  {wins_e/N:.3f}")

margins = [e - l for e, l in zip(scores_e, scores_l)]
print(f"  Avg margin:      {sum(margins)/N:+.1f}  stdev: {statistics.stdev(margins):.1f}")
print(f"  Games within 5: {sum(1 for m in margins if abs(m) <= 5)}")
print(f"  Games within 10:{sum(1 for m in margins if abs(m) <= 10)}")

print()
print("=" * 60)
print("DIAGNOSTIC B — Effective make-% per zone for ELITE vs LOW shooter/defender")
print("=" * 60)

e_shooter = _player(GUARD, 11.0, -8.5)
l_defender = _player(GUARD, 1.0, 1.0)
e_defender = _player(GUARD, 11.0, -8.5)
l_shooter  = _player(GUARD, 1.0, 1.0)

print(f"\nElite shooter (ortg_contrib={e_shooter.ortg_contrib}) vs Low defender (drtg_contrib={l_defender.drtg_contrib}):")
for zone in ["ft", "paint", "mid", "3pt"]:
    pct = _compute_make_pct(e_shooter, l_defender, zone, 1.0, 1.0, 0.0, 0.0, cfg.player_adj_scale)
    print(f"  {zone:6}: {pct:.3f}")

print(f"\nLow shooter (ortg_contrib={l_shooter.ortg_contrib}) vs Elite defender (drtg_contrib={e_defender.drtg_contrib}):")
for zone in ["ft", "paint", "mid", "3pt"]:
    pct = _compute_make_pct(l_shooter, e_defender, zone, 1.0, 1.0, 0.0, 0.0, cfg.player_adj_scale)
    print(f"  {zone:6}: {pct:.3f}")

print()
print("=" * 60)
print("DIAGNOSTIC C — Win rates across wider tier gaps (1000 games)")
print("=" * 60)

# Use extreme peak values to stress-test discrimination
def make_extreme_team(p_ortg, p_drtg):
    return make_team([_player(GUARD, p_ortg, p_drtg),
                      _player(WING,  p_ortg, p_drtg),
                      _player(BIG,   p_ortg, p_drtg)])

combos = [
    ("ELITE(11/-8.5)", "HIGH(7.5/-5.5)", 11.0, -8.5, 7.5, -5.5),
    ("ELITE(11/-8.5)", "MID(4/-2.5)",    11.0, -8.5, 4.0, -2.5),
    ("ELITE(11/-8.5)", "LOW(1/1.0)",     11.0, -8.5, 1.0,  1.0),
    ("HIGH(7.5/-5.5)", "MID(4/-2.5)",    7.5,  -5.5, 4.0, -2.5),
    ("HIGH(7.5/-5.5)", "LOW(1/1.0)",     7.5,  -5.5, 1.0,  1.0),
    ("MID(4/-2.5)",    "LOW(1/1.0)",     4.0,  -2.5, 1.0,  1.0),
]

print(f"\n{'Matchup':<45} {'WR(A)':>8}  ORtgA  DRtgA  ORtgB  DRtgB")
for a_label, b_label, a_ortg, a_drtg, b_ortg, b_drtg in combos:
    ta = make_extreme_team(a_ortg, a_drtg)
    tb = make_extreme_team(b_ortg, b_drtg)
    wr = win_rate(ta, tb, n=1000)
    matchup = f"{a_label} vs {b_label}"
    print(f"  {matchup:<43} {wr:.3f}   {ta.ortg:.1f}  {ta.drtg:.1f}  {tb.ortg:.1f}  {tb.drtg:.1f}")

print()
print("=" * 60)
print("DIAGNOSTIC D — Possession count and pace check")
print("=" * 60)

mid1 = make_team([_player(GUARD,4.0,-2.5), _player(WING,4.0,-2.5), _player(BIG,4.0,-2.5)])
mid2 = make_team([_player(GUARD,4.0,-2.5), _player(WING,4.0,-2.5), _player(BIG,4.0,-2.5)])
poss = _game_pace(mid1, mid2, cfg, 0.0)
print(f"\nPossessions per team per game (two MID teams): {poss}")
print(f"cfg.pace_baseline = {cfg.pace_baseline}")
print(f"cfg.player_adj_scale = {cfg.player_adj_scale}")

print()
print("=" * 60)
print("DIAGNOSTIC E — Tier discrimination with EXTREME values (stress test)")
print("=" * 60)
# Use the absolute ceiling/floor of each tier per generate_player() ranges
extreme_combos = [
    ("GODSTAR(12/-10)", "FLOOR_LOW(1/1)",  12.0, -10.0, 1.0, 1.0),
    ("GODSTAR(12/-10)", "FLOOR_HIGH(6/-7)",12.0, -10.0, 6.0,-7.0),
    ("TOP_ELITE(12/-10)","BOT_ELITE(10/-7)",12.0,-10.0,10.0,-7.0),
    ("TOP_HIGH(9/-7)",  "BOT_HIGH(6/-4)",   9.0,  -7.0, 6.0, -4.0),
    ("TOP_MID(6/-4)",   "BOT_MID(2/-1)",    6.0,  -4.0, 2.0, -1.0),
]
print(f"\n{'Matchup':<50} {'WR(A)':>8}")
for a_label, b_label, a_ortg, a_drtg, b_ortg, b_drtg in extreme_combos:
    ta = make_extreme_team(a_ortg, a_drtg)
    tb = make_extreme_team(b_ortg, b_drtg)
    wr = win_rate(ta, tb, n=1000)
    print(f"  {a_label} vs {b_label:<25} {wr:.3f}")

print()
print("=" * 60)
print("DIAGNOSTIC F — Age analysis: what rating delta does the age mult create?")
print("=" * 60)

for label, sp in [("YOUNG(sp=1)",1),("PRIME(sp=4)",4),("VETERAN(sp=11)",11),("DEEP_VET(sp=13)",13)]:
    m = _career_mult(sp, 4, 14, 0.78)
    # High-tier player: peak_ortg=7.5, peak_drtg=-5.5
    ortg_c = round(7.5 * min(1.0, m), 2)
    drtg_c = round(-5.5 * min(1.0, m), 2)
    overall = ortg_c - drtg_c
    print(f"  {label:<20} mult={m:.3f}  ortg_contrib={ortg_c:+.2f}  drtg_contrib={drtg_c:+.2f}  overall={overall:.2f}")

print()
print("=== Diagnostics complete ===")
