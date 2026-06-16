"""
Deep Engine Analysis — 5 structured analyses of the Fake Basketball sim engine.
Run with: python3 deep_engine_analysis.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))

from player import Player, GUARD, WING, BIG, ZONE_FT, ZONE_PAINT, ZONE_MID, ZONE_3PT
from team import Team
from game import play_game
from config import Config
from coach import Coach, ARCH_OFFENSIVE, ARCH_DEFENSIVE, ARCH_WHISPERER, ARCH_CHEMISTRY, ARCH_MOTIVATOR
from franchises import Franchise

cfg = Config()

# ── Helpers ───────────────────────────────────────────────────────────────────

_pid = 1000

def _player(position, tier, zone=None, age=26, seasons_played=4, peak_season=4,
            career_length=14):
    """Create a controlled Player with deterministic (mid-range) stats for its tier."""
    global _pid
    _pid += 1

    # Deterministic mid-point peak stats per tier
    if tier == "elite":
        p_ortg, p_drtg = 11.0, -8.5        # peak_overall ≈ 19.5
    elif tier == "high":
        p_ortg, p_drtg = 7.5, -5.5         # peak_overall ≈ 13.0
    elif tier == "mid":
        p_ortg, p_drtg = 4.0, -2.5         # peak_overall ≈ 6.5
    else:  # low
        p_ortg, p_drtg = 1.0, 1.0          # peak_overall ≈ 0.0 (clamped to ≥ 0)
        p_drtg = min(p_drtg, p_ortg)       # enforce floor

    if zone is None:
        if position == GUARD: zone = ZONE_3PT
        elif position == BIG:  zone = ZONE_PAINT
        else:                  zone = ZONE_MID

    return Player(
        player_id=_pid,
        name=f"Player_{_pid}",
        gender="male",
        position=position,
        age=age,
        preferred_zone=zone,
        pace_contrib=0.0,
        motivation="winning",
        contract_years_remaining=3,
        contract_length=3,
        peak_ortg=p_ortg,
        peak_drtg=p_drtg,
        career_length=career_length,
        peak_season=peak_season,
        start_mult=0.78,
        ceiling_noise=0.0,
        durability=0.80,
        seasons_played=seasons_played,
    )


_fid = 1

def _franchise():
    global _fid
    f = Franchise(
        city=f"City{_fid}", nickname="Team", metro=5.0,
        lat=40.0, lon=-74.0
    )
    _fid += 1
    return f


def make_team(players, coach=None, team_id=None):
    """Build a Team from a list of ≤3 Players. Computes ratings from roster."""
    global _fid
    tid = team_id or _fid
    t = Team(team_id=tid, franchise=_franchise())
    t.roster = (players + [None, None, None])[:3]
    t.coach = coach
    # Set neutral popularity so home advantage is consistent
    t.popularity = 0.5
    t.compute_ratings_from_roster(cfg)
    return t


def win_rate(team_a, team_b, n=500):
    """team_a is home for half, away for half to neutralise home court."""
    wins = 0
    half = n // 2
    for i in range(n):
        if i < half:
            result = play_game(team_a, team_b, cfg, home_advantage=0.0)
            if result.winner is team_a:
                wins += 1
        else:
            result = play_game(team_b, team_a, cfg, home_advantage=0.0)
            if result.winner is team_b:
                wins += 1
    return wins / n


def matrix_win_rates(teams, labels, n_games=300):
    """Compute an N×N win-rate matrix. Entry [i][j] = P(team i beats team j)."""
    n = len(teams)
    matrix = [[0.5] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            matrix[i][j] = win_rate(teams[i], teams[j], n_games)
    return matrix


def print_matrix(labels, matrix):
    w = max(len(l) for l in labels) + 2
    header = " " * w + "".join(f"{l:>{w}}" for l in labels)
    print(header)
    for i, row in enumerate(matrix):
        cells = "".join(
            "  —  " if i == j else f"{row[j]:>{w}.3f}"
            for j in range(len(labels))
        )
        print(f"{labels[i]:<{w}}{cells}")


def sep(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ── ANALYSIS 1: Coach Archetype Win Rates ────────────────────────────────────

sep("ANALYSIS 1 — Coach Archetype Win Rates")

def make_coach(archetype):
    return Coach(
        coach_id=f"c_{archetype}",
        name=f"Coach_{archetype}",
        gender="male",
        archetype=archetype,
        flexibility=0.50,   # neutral
        horizon=0.50,
        rating=0.70,        # above-average quality, consistent
        career_length=14,
        peak_season=5,
        start_mult=0.70,
        seasons_coached=5,  # at peak
    )

arch_labels = ["CHEM", "WHIS", "DEF", "OFF", "MOT"]
arch_list   = [ARCH_CHEMISTRY, ARCH_WHISPERER, ARCH_DEFENSIVE, ARCH_OFFENSIVE, ARCH_MOTIVATOR]

# Shared roster: elite star + high co-star + mid starter (fixed players reused across teams)
def arch_roster():
    return [
        _player(GUARD, "elite"),
        _player(WING,  "high"),
        _player(BIG,   "mid"),
    ]

# Neutral team: same roster quality, no coach
neutral_players = arch_roster()
neutral_team    = make_team(neutral_players, coach=None)

print("\nPart A — Each archetype vs Neutral team (500 games, no home court)")
print(f"{'Archetype':<14} {'Win Rate vs Neutral':>20}")
arch_teams = []
for arch, label in zip(arch_list, arch_labels):
    coach = make_coach(arch)
    players = arch_roster()
    t = make_team(players, coach=coach)
    arch_teams.append(t)
    wr = win_rate(t, neutral_team, n=500)
    print(f"  {label} ({arch:<18})   {wr:.3f}")

print()
print("Part B — 5×5 Archetype vs Archetype matrix (300 games per pair)")
print("Row = team with that archetype, Column = opponent archetype")
print("Entry = P(row team wins)")
m1 = matrix_win_rates(arch_teams, arch_labels, n_games=300)
print_matrix(arch_labels, m1)

# Row means (average win rate across all matchups)
print()
print("Row averages (avg win rate across all opponents):")
for i, label in enumerate(arch_labels):
    others = [m1[i][j] for j in range(len(arch_labels)) if i != j]
    print(f"  {label}: {sum(others)/len(others):.3f}")


# ── ANALYSIS 2: Team Construction ────────────────────────────────────────────

sep("ANALYSIS 2 — Team Construction Philosophies")

# Talent budget note:
#   TOP_HEAVY  elite(~19.5) + mid(~6.5)  + mid(~6.5)  → weighted 0.5×19.5 + 0.3×6.5 + 0.2×6.5 ≈ 13.0
#   BALANCED   high(~13.0)  + high(~13.0)+ high(~13.0) → 0.5×13 + 0.3×13 + 0.2×13 = 13.0
#   STAR_COSTAR elite(~19.5)+ high(~13.0)+ low(~0.0)  → 0.5×19.5 + 0.3×13 + 0.2×0 = 13.65

top_heavy_team = make_team([
    _player(GUARD, "elite"),
    _player(WING,  "mid"),
    _player(BIG,   "mid"),
])

balanced_team = make_team([
    _player(GUARD, "high"),
    _player(WING,  "high"),
    _player(BIG,   "high"),
])

star_costar_team = make_team([
    _player(GUARD, "elite"),
    _player(WING,  "high"),
    _player(BIG,   "low"),
])

# Benchmark: 3× mid
benchmark_team = make_team([
    _player(GUARD, "mid"),
    _player(WING,  "mid"),
    _player(BIG,   "mid"),
])

constructions = {
    "TOP_HEAVY":   top_heavy_team,
    "BALANCED":    balanced_team,
    "STAR_COSTAR": star_costar_team,
}

print("\nPart A — Each construction vs Benchmark (3×mid, 500 games)")
print(f"{'Construction':<14}  {'Win Rate vs Benchmark':>22}")
for name, team in constructions.items():
    wr = win_rate(team, benchmark_team, n=500)
    print(f"  {name:<14} {wr:.3f}")

print()
print("Part B — Head-to-head matrix (500 games per pair)")
c_labels = list(constructions.keys())
c_teams  = list(constructions.values())
m2 = matrix_win_rates(c_teams, c_labels, n_games=500)
print_matrix(c_labels, m2)

# Show computed ratings for each construction
print()
print("Computed team ratings:")
for name, team in {**constructions, "BENCHMARK": benchmark_team}.items():
    print(f"  {name:<14}  ORtg={team.ortg:.1f}  DRtg={team.drtg:.1f}  Net={team.ortg - team.drtg:+.1f}")


# ── ANALYSIS 3: Quality Tier Matchups ────────────────────────────────────────

sep("ANALYSIS 3 — Quality Tier Matchup Win Rates")

elite_team = make_team([_player(GUARD,"elite"), _player(WING,"elite"), _player(BIG,"elite")])
high_team  = make_team([_player(GUARD,"high"),  _player(WING,"high"),  _player(BIG,"high")])
mid_team   = make_team([_player(GUARD,"mid"),   _player(WING,"mid"),   _player(BIG,"mid")])
low_team   = make_team([_player(GUARD,"low"),   _player(WING,"low"),   _player(BIG,"low")])

tier_teams  = [elite_team, high_team, mid_team, low_team]
tier_labels = ["ELITE", "HIGH", "MID", "LOW"]

print("\nComputed team ratings by tier:")
for label, team in zip(tier_labels, tier_teams):
    print(f"  {label:<6}  ORtg={team.ortg:.1f}  DRtg={team.drtg:.1f}  Net={team.ortg - team.drtg:+.1f}")

print()
print("Pairwise win-rate matrix (500 games per pair)")
print("Entry = P(row team wins)")
m3 = matrix_win_rates(tier_teams, tier_labels, n_games=500)
print_matrix(tier_labels, m3)


# ── ANALYSIS 4: Player Position Impact ───────────────────────────────────────

sep("ANALYSIS 4 — Player Position Impact (all high tier)")

all_guards   = make_team([_player(GUARD,"high"), _player(GUARD,"high"), _player(GUARD,"high")])
all_wings    = make_team([_player(WING, "high"), _player(WING, "high"), _player(WING, "high")])
all_bigs     = make_team([_player(BIG,  "high"), _player(BIG,  "high"), _player(BIG,  "high")])
standard     = make_team([_player(GUARD,"high"), _player(WING, "high"), _player(BIG,  "high")])
guard_heavy  = make_team([_player(GUARD,"high"), _player(GUARD,"high"), _player(WING, "high")])
big_heavy    = make_team([_player(BIG,  "high"), _player(BIG,  "high"), _player(WING, "high")])

pos_teams  = [all_guards, all_wings, all_bigs, standard, guard_heavy, big_heavy]
pos_labels = ["ALL_G", "ALL_W", "ALL_B", "STD", "G_HEAVY", "B_HEAVY"]

print("\nPart A — Each composition vs STANDARD (500 games)")
print(f"{'Composition':<12}  {'Win Rate vs Standard':>22}  {'ORtg':>6}  {'DRtg':>6}  {'Net':>6}")
for label, team in zip(pos_labels, pos_teams):
    wr = win_rate(team, standard, n=500) if team is not standard else 0.5
    print(f"  {label:<12} {wr:.3f}               ORtg={team.ortg:.1f}  DRtg={team.drtg:.1f}  Net={team.ortg - team.drtg:+.1f}")

print()
print("Part B — Full 6×6 position matrix (300 games per pair)")
m4 = matrix_win_rates(pos_teams, pos_labels, n_games=300)
print_matrix(pos_labels, m4)


# ── ANALYSIS 5: Player Age / Career Stage Impact ─────────────────────────────

sep("ANALYSIS 5 — Player Age / Career Stage Impact")

# All high-tier players; vary seasons_played relative to peak_season
# Career arc: peak_season=4, career_length=14  => decline starts season 5
# YOUNG:    seasons_played=1  (mult ≈ start_mult + 0.25 × (1-start_mult) ≈ 0.84)
# PRIME:    seasons_played=4  (mult = 1.0)
# VETERAN:  seasons_played=11 (well past peak; t=7/10=0.7 → mult ≈ 0.80)
# MIXED:    one of each

def age_player(position, seasons_played, peak_season=4, career_length=14):
    return _player(position, "high",
                   seasons_played=seasons_played,
                   peak_season=peak_season,
                   career_length=career_length)

young_team   = make_team([age_player(GUARD,1), age_player(WING,1), age_player(BIG,1)])
prime_team   = make_team([age_player(GUARD,4), age_player(WING,4), age_player(BIG,4)])
veteran_team = make_team([age_player(GUARD,11), age_player(WING,11), age_player(BIG,11)])
mixed_team   = make_team([age_player(GUARD,1), age_player(WING,4), age_player(BIG,11)])

age_teams  = [young_team, prime_team, veteran_team, mixed_team]
age_labels = ["YOUNG", "PRIME", "VETERAN", "MIXED"]

# Print mult values for transparency
print("\nCareer multipliers (career_mult) at each age stage (peak_season=4, career_length=14):")
from player import _career_mult
for label, sp in [("YOUNG",1),("PRIME",4),("VETERAN",11)]:
    m = _career_mult(sp, 4, 14, 0.78)
    print(f"  {label}: seasons_played={sp}, mult={m:.3f}")

print()
print("Computed team ratings by age profile:")
for label, team in zip(age_labels, age_teams):
    print(f"  {label:<8}  ORtg={team.ortg:.1f}  DRtg={team.drtg:.1f}  Net={team.ortg - team.drtg:+.1f}")

print()
print("Part A — Each age profile vs PRIME (500 games)")
print(f"{'Profile':<10}  {'Win Rate vs Prime':>20}")
for label, team in zip(age_labels, age_teams):
    wr = win_rate(team, prime_team, n=500)
    print(f"  {label:<10} {wr:.3f}")

print()
print("Part B — 4×4 age-profile matrix (300 games per pair)")
m5 = matrix_win_rates(age_teams, age_labels, n_games=300)
print_matrix(age_labels, m5)

print()
print("=== Analysis complete ===")
