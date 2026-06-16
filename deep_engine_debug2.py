"""
Diagnostic 2 — investigate why ELITE vs LOW shows ~50% win rate in Analysis 3
but 86% in Diagnostic A. The issue is player_adj_scale vs team ortg capping.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))

from player import Player, GUARD, WING, BIG, ZONE_3PT, ZONE_PAINT, ZONE_MID
from team import Team
from game import play_game, _compute_make_pct, _game_pace
from config import Config
from franchises import Franchise

cfg = Config()
_pid = 19000
_fid = 19000

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
print("ROOT CAUSE: How play_game uses team ortg vs player contrib")
print("=" * 60)
print("""
play_game() does NOT use team.ortg/team.drtg directly for scoring.
It calls _sim_possession → _compute_make_pct which uses PLAYER-level
ortg_contrib/drtg_contrib divided by cfg.player_adj_scale (=88).

team.ortg/drtg (computed from roster) are stored on the Team object
but play_game() only reads them if _bench_quality uses owner.last_net_profit
— which is zero here. The clamp on team.ortg (ortg_max=120) therefore
only affects ortg/drtg display and team rating, NOT per-possession scoring.

So: the real question is whether player-level contrib differences create
distinguishable win rates. Let's verify by checking what happens in
_compute_make_pct with exact player stats.
""")

# Confirm the ortg computation path in play_game vs _compute_make_pct
print("Per-zone make-% for key player matchups (player_adj_scale=88):")
print()

def show_matchup(off_ortg, def_drtg, label):
    off = _player(GUARD, off_ortg, 0.0)
    dff = _player(GUARD, 0.0, def_drtg)
    print(f"  {label}")
    for zone in ["ft", "paint", "mid", "3pt"]:
        pct = _compute_make_pct(off, dff, zone, 1.0, 1.0, 0.0, 0.0, cfg.player_adj_scale)
        print(f"    {zone:6}: {pct:.4f}")
    print()

show_matchup(11.0, -8.5, "ELITE offense (ortg_contrib=11.0) vs ELITE defense (drtg=-8.5)")
show_matchup(11.0,  1.0, "ELITE offense (ortg_contrib=11.0) vs LOW defense (drtg=1.0)")
show_matchup( 4.0, -2.5, "MID offense   (ortg_contrib=4.0)  vs MID defense (drtg=-2.5)")
show_matchup( 4.0, -8.5, "MID offense   (ortg_contrib=4.0)  vs ELITE defense (drtg=-8.5)")
show_matchup( 1.0,  1.0, "LOW offense   (ortg_contrib=1.0)  vs LOW defense (drtg=1.0)")
show_matchup( 1.0, -8.5, "LOW offense   (ortg_contrib=1.0)  vs ELITE defense (drtg=-8.5)")

print("=" * 60)
print("KEY TEST: Does win rate correlate with net ortg delta?")
print("=" * 60)

# The net rating difference should predict outcomes
# Let's build teams with staggered ortg/drtg and see win rates
print()

# Manual stagger: instead of using tier midpoints, test net ratings at fixed intervals
scenarios = [
    # (desc, off_ortg, off_drtg, def_ortg_contrib, def_drtg_contrib)
    ("net+3 vs net+0",   4.0, -2.5, 0.0,  0.0),
    ("net+6 vs net+0",   6.0, -4.0, 0.0,  0.0),  # ~mid floor vs nothing
    ("net+10 vs net+0",  7.5, -5.5, 0.0,  0.0),  # ~high vs nothing
    ("net+19 vs net+0", 11.0, -8.5, 0.0,  0.0),  # ~elite vs nothing
]

for desc, ao, ad, bo, bd in scenarios:
    ta = make_team([_player(GUARD, ao, ad), _player(WING, ao, ad), _player(BIG, ao, ad)])
    # For team B with (0,0) players: ortg_contrib=0, drtg_contrib=0 means league-average
    tb = make_team([_player(GUARD, bo, bd), _player(WING, bo, bd), _player(BIG, bo, bd)])
    wr = win_rate(ta, tb, n=1000)
    print(f"  {desc:<22} → win rate A: {wr:.3f}   ORtg_A={ta.ortg:.1f} DRtg_A={ta.drtg:.1f}  ORtg_B={tb.ortg:.1f} DRtg_B={tb.drtg:.1f}")

print()
print("=" * 60)
print("ANALYSIS 3 BUG REPRODUCTION - why tier teams showed ~50%")
print("=" * 60)
print("""
In Analysis 3 the '_player()' helper uses MID-POINT stats for each tier:
  elite: p_ortg=11.0, p_drtg=-8.5  (peak_overall=19.5)
  high:  p_ortg=7.5,  p_drtg=-5.5  (peak_overall=13.0)
  mid:   p_ortg=4.0,  p_drtg=-2.5  (peak_overall=6.5)
  low:   p_ortg=1.0,  p_drtg=1.0   (peak_overall=0.0)

BUT team.ortg is CLAMPED to [100, 120]. Let's check if ortg_max=120 is
the culprit — elite teams may saturate at 120.
""")

for label, po, pd in [("ELITE",11.0,-8.5),("HIGH",7.5,-5.5),("MID",4.0,-2.5),("LOW",1.0,1.0)]:
    t = make_team([_player(GUARD,po,pd), _player(WING,po,pd), _player(BIG,po,pd)])
    print(f"  {label}: raw ORtg before clamp = ?  stored ORtg={t.ortg:.2f}  DRtg={t.drtg:.2f}  Net={t.ortg-t.drtg:.2f}")
    # manually compute raw
    w = (0.5, 0.3, 0.2)
    ortg_delta = sum(w[i] * po for i in range(3))
    drtg_delta = sum(w[i] * pd for i in range(3))
    raw_ortg = 110.0 + ortg_delta
    raw_drtg = 110.0 + drtg_delta
    print(f"    raw ORtg (no clamp): {raw_ortg:.2f}  raw DRtg: {raw_drtg:.2f}")
    clamped_o = max(100.0, min(120.0, raw_ortg))
    clamped_d = max(100.0, min(120.0, raw_drtg))
    print(f"    clamped: ORtg={clamped_o:.2f}  DRtg={clamped_d:.2f}")
    print()

print("""
So the team.ortg DOES saturate at 120 for ELITE (raw=121.0).
BUT play_game uses player-level ortg_contrib directly, not team.ortg!

The real question: does the ELITE 3-player team (each with ortg_contrib=11,
drtg_contrib=-8.5) produce distinguishable game outcomes vs the HIGH team?

Recall from Diagnostic C: ELITE vs HIGH showed 0.497 and ELITE vs LOW showed 0.499.
This is because _compute_make_pct uses the INDIVIDUAL PLAYER's contrib stats.
When the full roster of 3 elites faces a roster of 3 lows, each possession pits
one player against one defender — and the calculation should show a clear edge.

Let's directly test 1 ELITE player vs 1 LOW player (single-slot team) to
isolate the signal from statistical noise in the 3-player case.
""")

# Single-player teams (elite vs low)
ta_1p = make_team([_player(GUARD, 11.0, -8.5)])
tb_1p = make_team([_player(GUARD, 1.0, 1.0)])
wr_1p = win_rate(ta_1p, tb_1p, n=2000)
print(f"1-player: ELITE(11/-8.5) vs LOW(1/1): win rate = {wr_1p:.3f}")

# 3-player teams but this time run 2000 games
ta_3p = make_team([_player(GUARD,11.0,-8.5), _player(WING,11.0,-8.5), _player(BIG,11.0,-8.5)])
tb_3p = make_team([_player(GUARD,1.0,1.0),   _player(WING,1.0,1.0),   _player(BIG,1.0,1.0)])
wr_3p = win_rate(ta_3p, tb_3p, n=2000)
print(f"3-player: ELITE(11/-8.5) vs LOW(1/1): win rate = {wr_3p:.3f}")

print()
print("If win rates are ~50% even with full elite vs full low, the discrimination")
print("mechanism is too compressed. player_adj_scale=88 may be too large.")

# Let's check what the raw probability difference looks like
print()
print("Delta in per-possession expected points (approximate):")
for zone in ["ft","paint","mid","3pt"]:
    e_sh = _player(GUARD, 11.0, -8.5)
    l_sh = _player(GUARD, 1.0, 1.0)
    e_df = _player(GUARD, 11.0, -8.5)
    l_df = _player(GUARD, 1.0, 1.0)
    # Elite shoots vs Low defends
    pct_e_vs_l = _compute_make_pct(e_sh, l_df, zone, 1.0, 1.0, 0.0, 0.0, cfg.player_adj_scale)
    # Low shoots vs Elite defends
    pct_l_vs_e = _compute_make_pct(l_sh, e_df, zone, 1.0, 1.0, 0.0, 0.0, cfg.player_adj_scale)
    from game import _ZONE_PTS
    pts_e = pct_e_vs_l * _ZONE_PTS[zone]
    pts_l = pct_l_vs_e * _ZONE_PTS[zone]
    print(f"  {zone:6}: E_off_vs_L_def={pts_e:.3f}pts  L_off_vs_E_def={pts_l:.3f}pts  delta={pts_e-pts_l:+.3f}")

print()
print("=== Debug 2 complete ===")
