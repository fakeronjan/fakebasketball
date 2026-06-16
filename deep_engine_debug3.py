"""
Diagnostic 3 — Understand why symmetrical 3-elite vs 3-low shows ~50%.
The key: Elite offense vs Low defense vs Low offense vs Elite defense.
Are the advantages canceling out?
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from player import Player, GUARD, WING, BIG, ZONE_3PT, ZONE_PAINT, ZONE_MID
from team import Team
from game import play_game, _compute_make_pct, _ZONE_PTS, _ZONE_BASE_PCT
from config import Config
from franchises import Franchise
import statistics

cfg = Config()
_pid = 29000
_fid = 29000

def _player(position, p_ortg, p_drtg, zone=None):
    global _pid
    _pid += 1
    if zone is None:
        zone = ZONE_3PT if position == GUARD else (ZONE_PAINT if position == BIG else ZONE_MID)
    return Player(
        player_id=_pid, name=f"P{_pid}", gender="male",
        position=position, age=26, preferred_zone=zone, pace_contrib=0.0,
        motivation="winning", contract_years_remaining=3, contract_length=3,
        peak_ortg=p_ortg, peak_drtg=p_drtg, career_length=14,
        peak_season=4, start_mult=0.78, ceiling_noise=0.0, durability=0.80,
        seasons_played=4,
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

def win_rate(a, b, n=2000):
    wins = 0
    home_scores, away_scores = [], []
    for i in range(n):
        if i < n // 2:
            r = play_game(a, b, cfg, home_advantage=0.0)
            if r.winner is a: wins += 1
            home_scores.append(r.home_score)
            away_scores.append(r.away_score)
        else:
            r = play_game(b, a, cfg, home_advantage=0.0)
            if r.winner is b: wins += 1
            home_scores.append(r.away_score)
            away_scores.append(r.home_score)
    return wins / n, sum(home_scores)/len(home_scores), sum(away_scores)/len(away_scores)

print("=" * 65)
print("CORE INSIGHT: The symmetric problem")
print("=" * 65)
print("""
When ELITE plays LOW:
  - ELITE offense vs LOW defense: elite gets better shots
  - LOW offense vs ELITE defense: low gets worse shots
Both effects COMBINE to favor ELITE. So ~50% for elite vs low is WRONG.
The question is: what's actually happening?
""")

# Let's compute expected pts per possession manually
# Assume each shooter is picked with probability proportional to role weights
# Guard: slot 0 (star), Wing: slot 1 (costar), Big: slot 2 (starter)
# role_wts = [1.12, 1.00, 0.86], bench_wt = 1.75
# talent_factor = clamp(1.0 + 0.025 * ortg_contrib, 0.75, 1.35)

def expected_pts_per_100(off_ortg, off_drtg, def_ortg, def_drtg):
    """Hand-compute expected pts/100 for offense team vs defense team.
    Simplification: assume each named player gets equal zone distribution (avg).
    """
    # Zone weights from zone_dist (default = 0.12,0.48,0.20,0.20)
    zone_wts = {"ft": 0.12, "paint": 0.48, "mid": 0.20, "3pt": 0.20}

    # Positions: Guard, Wing, Big, all with same ortg/drtg for simplicity
    # In the test teams we actually use same stats per position in each team
    off_player = _player(GUARD, off_ortg, off_drtg)
    def_player = _player(GUARD, def_ortg, def_drtg)

    # TO rate 13% → 0.87 shot attempts per possession
    to_rate = 0.130
    expected = 0.0
    for zone, wt in zone_wts.items():
        pct = _compute_make_pct(off_player, def_player, zone, 1.0, 1.0, 0.0, 0.0, cfg.player_adj_scale)
        pts = _ZONE_PTS[zone]
        expected += wt * pct * pts
    # Apply TO rate
    expected *= (1 - to_rate)
    # Scale to per 100 possessions
    return expected * 100

print("Expected pts/100 poss (hand-calc, named player vs named player):")
matchups = [
    ("ELITE off vs LOW def",   11.0, -8.5, 1.0, 1.0),
    ("ELITE off vs HIGH def",  11.0, -8.5, 7.5, -5.5),
    ("ELITE off vs MID def",   11.0, -8.5, 4.0, -2.5),
    ("ELITE off vs ELITE def", 11.0, -8.5, 11.0, -8.5),
    ("HIGH off vs LOW def",    7.5,  -5.5, 1.0, 1.0),
    ("HIGH off vs MID def",    7.5,  -5.5, 4.0, -2.5),
    ("MID off vs LOW def",     4.0,  -2.5, 1.0, 1.0),
    ("MID off vs MID def",     4.0,  -2.5, 4.0, -2.5),
    ("LOW off vs LOW def",     1.0,   1.0, 1.0, 1.0),
    ("LOW off vs ELITE def",   1.0,   1.0, 11.0, -8.5),
]
for label, ao, ad, do, dd in matchups:
    pts = expected_pts_per_100(ao, ad, do, dd)
    print(f"  {label:<30}: {pts:.2f} pts/100")

print()
print("=" * 65)
print("ACTUAL NET RATING: ELITE team (off) - LOW team (off) = advantage?")
print("=" * 65)

# ELITE TEAM: all players elite
# vs LOW TEAM: all players low
# In a game: ELITE's offense runs against LOW's defense, and LOW's offense runs against ELITE's defense

e_off_vs_l_def = expected_pts_per_100(11.0, -8.5, 1.0, 1.0)
l_off_vs_e_def = expected_pts_per_100(1.0, 1.0, 11.0, -8.5)

print(f"\nELITE team scoring rate (vs LOW defense): {e_off_vs_l_def:.2f}/100")
print(f"LOW team scoring rate  (vs ELITE defense): {l_off_vs_e_def:.2f}/100")
print(f"Expected margin per 100 poss: {e_off_vs_l_def - l_off_vs_e_def:+.2f}")
print()

# But wait: this is for named player matchups only. Bench and cross-position matchups exist.
# Also: within a team, the defensive player who guards an attacker is positional-matched.
# All-guard team: guard attacker gets guarded by guard (same position both teams)
# This means: ELITE guard scores more vs LOW guard defender, AND LOW guard scores less vs ELITE guard defender.

print("Net per 95-possession game:")
poss = 95
elite_pts = e_off_vs_l_def / 100 * poss
low_pts   = l_off_vs_e_def / 100 * poss
print(f"  ELITE: {elite_pts:.1f} pts")
print(f"  LOW:   {low_pts:.1f} pts")
print(f"  Margin: {elite_pts - low_pts:+.1f}")

print()
print("But! bench possessions (~37% of possessions) see bench vs bench,")
print("which partly obscures the named-player quality differential.")
print()

# Let's verify with actual game simulation — score distribution only
ta = make_team([_player(GUARD,11.0,-8.5), _player(WING,11.0,-8.5), _player(BIG,11.0,-8.5)])
tb = make_team([_player(GUARD,1.0,1.0),   _player(WING,1.0,1.0),   _player(BIG,1.0,1.0)])

print("Actual simulation — ELITE vs LOW (2000 games, no home court):")
wr, avg_e, avg_l = win_rate(ta, tb, n=2000)
print(f"  ELITE win rate: {wr:.3f}")
print(f"  ELITE avg pts: {avg_e:.1f}")
print(f"  LOW   avg pts: {avg_l:.1f}")
print(f"  Avg margin: {avg_e - avg_l:+.1f}")

print()
print("=" * 65)
print("MIXED TEAM TEST: Elite offense + Low defense vs Low offense + Elite defense")
print("=" * 65)
# Asymmetric test to verify direction:
# Team A: elite ortg, poor drtg (offensive specialist)
# Team B: poor ortg, elite drtg (defensive specialist)

ta_asym = make_team([
    _player(GUARD, 11.0, 1.0),   # elite scorer, no defense
    _player(WING, 11.0, 1.0),
    _player(BIG, 11.0, 1.0),
])
tb_asym = make_team([
    _player(GUARD, 1.0, -8.5),   # no offense, elite defender
    _player(WING, 1.0, -8.5),
    _player(BIG, 1.0, -8.5),
])
wr_asym, avg_a, avg_b = win_rate(ta_asym, tb_asym, n=2000)
print(f"\nOFF-SPEC (ortg=11, drtg=+1) vs DEF-SPEC (ortg=1, drtg=-8.5):")
print(f"  OFF-SPEC win rate: {wr_asym:.3f}  avg score: {avg_a:.1f} vs {avg_b:.1f}")

print()
print("=" * 65)
print("PLAYER_ADJ_SCALE SENSITIVITY CHECK")
print("=" * 65)
print("What if player_adj_scale were 44 (half current)? Expected pts would double-diff.")
print()

for scale in [44.0, 66.0, 88.0, 110.0]:
    e_sh = _player(GUARD, 11.0, -8.5)
    l_df = _player(GUARD, 1.0, 1.0)
    e_df = _player(GUARD, 11.0, -8.5)
    l_sh = _player(GUARD, 1.0, 1.0)

    e_paint = _compute_make_pct(e_sh, l_df, "paint", 1.0, 1.0, 0.0, 0.0, scale) * 2
    l_paint = _compute_make_pct(l_sh, e_df, "paint", 1.0, 1.0, 0.0, 0.0, scale) * 2
    e_3pt   = _compute_make_pct(e_sh, l_df, "3pt", 1.0, 1.0, 0.0, 0.0, scale) * 3
    l_3pt   = _compute_make_pct(l_sh, e_df, "3pt", 1.0, 1.0, 0.0, 0.0, scale) * 3
    print(f"  scale={scale:.0f}: E_paint={e_paint:.3f}pts  L_paint={l_paint:.3f}pts  E_3pt={e_3pt:.3f}pts  L_3pt={l_3pt:.3f}pts")

print()
print("=" * 65)
print("WHAT IS THE BENCH DOING? — bench_wt = 1.75 out of total ~4.73")
print("=> bench gets ~37% of possessions")
print("=" * 65)
role_wts = [1.12, 1.00, 0.86]
bench_wt = 1.75
# talent_factor for elite: 1.0 + 0.025 * 11.0 = 1.275 (capped)
talent_e = min(1.35, 1.0 + 0.025 * 11.0)
talent_l = max(0.75, 1.0 + 0.025 * 1.0)

# Approximate weights for 3-player elite team
wts_e = [role_wts[i] * talent_e for i in range(3)]
wts_l = [role_wts[i] * talent_l for i in range(3)]
total_e = sum(wts_e) + bench_wt
total_l = sum(wts_l) + bench_wt

bench_pct_e = bench_wt / total_e
bench_pct_l = bench_wt / total_l
named_pct_e = sum(wts_e) / total_e
named_pct_l = sum(wts_l) / total_l

print(f"\nElite team: talent_factor={talent_e:.3f}")
print(f"  Named player weight total: {sum(wts_e):.3f}")
print(f"  Bench weight: {bench_wt:.3f}")
print(f"  Bench share of possessions: {bench_pct_e:.1%}")
print(f"  Named player share: {named_pct_e:.1%}")

print(f"\nLow team: talent_factor={talent_l:.3f}")
print(f"  Named player weight total: {sum(wts_l):.3f}")
print(f"  Bench weight: {bench_wt:.3f}")
print(f"  Bench share of possessions: {bench_pct_l:.1%}")
print(f"  Named player share: {named_pct_l:.1%}")

print(f"\nBench scoring uses _bench_quality() → no owner → _BENCH_BASELINE - 0.015 = -0.025 adjustment")
print("So bench performance is effectively league-average - 0.025 for ALL teams in our test.")
print("Since bench quality is IDENTICAL for elite and low teams in our test,")
print("the ~37% bench possessions cancel out perfectly, washing away the quality signal!")
print()
print("This is THE root cause of low tier discrimination in the 3-player equal-bench test.")

print()
print("=== Debug 3 complete ===")
