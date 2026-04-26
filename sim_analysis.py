"""
100×100 simulation analysis.
Runs NUM_SIMS full simulations of NUM_SEASONS each, collects metrics,
and prints a structured breakdown of every major system.
"""
import math
import random
import statistics
import sys
import time
from collections import Counter, defaultdict

from config import Config
from league import League
from season import Season

NUM_SIMS    = 50
NUM_SEASONS = 30

# ── Metric buckets ────────────────────────────────────────────────────────────

# Coach impact (per-archetype and per-flexibility-quartile)
from coach import ARCHETYPES as _ARCHETYPES
arch_team_seasons: dict[str, int]          = {a: 0   for a in _ARCHETYPES}
arch_win_pcts:     dict[str, list[float]]  = {a: []  for a in _ARCHETYPES}
arch_net_ratings:  dict[str, list[float]]  = {a: []  for a in _ARCHETYPES}
arch_titles:       dict[str, int]          = {a: 0   for a in _ARCHETYPES}
arch_coy_wins:     dict[str, int]          = {a: 0   for a in _ARCHETYPES}
arch_chemistry:    dict[str, list[float]]  = {a: []  for a in _ARCHETYPES}
arch_star_hap:     dict[str, list[float]]  = {a: []  for a in _ARCHETYPES}
arch_depth_hap:    dict[str, list[float]]  = {a: []  for a in _ARCHETYPES}
# Flexibility quartile: 0=[0,0.25), 1=[0.25,0.5), 2=[0.5,0.75), 3=[0.75,1]
flex_win_pcts:     list[list[float]]       = [[], [], [], []]

# Game engine
home_wins_total = 0
home_games_total = 0
all_scores: list[float] = []          # one entry per team per game
all_paces: list[int]   = []           # possessions per team per game

# Competitive balance
all_win_pcts: list[float] = []        # every team's season win%
champ_counts: Counter = Counter()     # team_name → titles across all sims
champ_concentrations: list[float] = [] # HHI per sim
back2backs = 0
three_peats = 0
total_season_pairs = 0                # for back2back/threepeat denominators

# Playoffs
higher_seed_wins = 0
series_total = 0
series_lengths: Counter = Counter()

# Awards
mvp_team_ranks: list[int] = []        # what standing rank was the MVP's team?
dpoy_def_rtg: list[float] = []

# Player / PPG
top_ppg: list[float] = []            # highest PPG in each season
season_avg_ppg: list[float] = []     # league-average PPG each season

# Home court by popularity bucket
# bucket 0 = pop < 0.33, 1 = 0.33–0.66, 2 = 0.66+
home_by_pop_wins  = [0, 0, 0]
home_by_pop_games = [0, 0, 0]

# League evolution
final_team_counts: list[int] = []
expansion_counts: list[int]  = []
merger_counts: list[int]     = []
reloc_counts: list[int]      = []

# Popularity
starting_league_pops: list[float] = []
ending_league_pops: list[float]   = []

# Meta (3pt era)
meta_highs: list[float]  = []
meta_lows: list[float]   = []
meta_finals: list[float] = []

# Revenue
commissioner_takes: list[float] = []  # per-season commissioner share, across all seasons
team_profits: list[float]        = []  # per team per season net profit

# Work stoppages
total_work_stoppages = 0

# Chemistry
all_chemistries: list[float] = []

# ── Run simulations ───────────────────────────────────────────────────────────

t0 = time.time()
print(f"Running {NUM_SIMS} × {NUM_SEASONS} season simulations...", flush=True)

for sim_idx in range(NUM_SIMS):
    cfg = Config(num_seasons=NUM_SEASONS)
    league = League(cfg)

    starting_league_pops.append(league.league_popularity)

    # Patch simulate() to collect per-season metrics inline
    for season_num in range(1, cfg.num_seasons + 1):
        season = Season(season_num, list(league.teams), cfg, league.league_meta)
        season.run()
        league.seasons.append(season)

        # ── Coach impact metrics ─────────────────────────────────────────────
        for t in season.regular_season_standings:
            if t.coach is None:
                continue
            arch = t.coach.archetype
            flex = t.coach.flexibility
            wpc  = season.reg_win_pct(t)
            nr   = t.ortg - t.drtg

            arch_team_seasons[arch] += 1
            arch_win_pcts[arch].append(wpc)
            arch_net_ratings[arch].append(nr)
            flex_win_pcts[min(3, int(flex * 4))].append(wpc)
            arch_chemistry[arch].append(t.compute_chemistry(cfg))

            stars = [p for p in t.roster if p is not None and p.peak_overall >= 12]
            depth = [p for p in t.roster if p is not None and p.peak_overall < 12]
            if stars:
                arch_star_hap[arch].append(statistics.mean(p.happiness for p in stars))
            if depth:
                arch_depth_hap[arch].append(statistics.mean(p.happiness for p in depth))

        if season.champion and season.champion.coach:
            arch_titles[season.champion.coach.archetype] += 1
        # COY collected after update_all_coach_happiness (see below)

        # ── Game engine metrics ──────────────────────────────────────────────
        for g in season.regular_season_games:
            if g.home_score > g.away_score:
                home_wins_total += 1
            home_games_total += 1
            all_scores.append(g.home_score)
            all_scores.append(g.away_score)

            # Home court by popularity
            pop = g.home.popularity
            bucket = 0 if pop < 0.33 else (1 if pop < 0.66 else 2)
            home_by_pop_games[bucket] += 1
            if g.home_score > g.away_score:
                home_by_pop_wins[bucket] += 1

        # ── Pace proxy: back-calculate from game scores
        # (actual pace tracked via # of RS games / teams)
        n_teams = len(season.regular_season_standings)
        n_games = len(season.regular_season_games)
        if n_games > 0:
            avg_total = statistics.mean(g.home_score + g.away_score
                                        for g in season.regular_season_games)
            # rough pace = total pts / (2 × expected pts/poss)
            # expected pts/poss ≈ 1.10
            all_paces.append(avg_total / 2.0 / 1.10 * 100 if avg_total else 0)

        # ── Win% spread ──────────────────────────────────────────────────────
        for t in season.regular_season_standings:
            all_win_pcts.append(season.reg_win_pct(t))

        # ── PPG ──────────────────────────────────────────────────────────────
        if season.player_stats:
            qualified = [s.ppg for s in season.player_stats.values()
                         if s.player_id != 0 and s.games >= 10]
            if qualified:
                top_ppg.append(max(qualified))
            season_avg_ppg.append(season.league_avg_ppg())

        # ── Awards ───────────────────────────────────────────────────────────
        if season.mvp and season.mvp_team:
            standings = season.regular_season_standings
            if season.mvp_team in standings:
                rank = standings.index(season.mvp_team) + 1
                mvp_team_ranks.append(rank)

        if season.dpoy:
            s = season.player_stats.get(season.dpoy.player_id)
            if s and s.def_rtg > 0:
                dpoy_def_rtg.append(s.def_rtg)

        # ── Chemistry ────────────────────────────────────────────────────────
        for t in league.teams:
            all_chemistries.append(t.compute_chemistry(cfg))

        # ── Playoffs ─────────────────────────────────────────────────────────
        for rnd in season.playoff_rounds:
            for series in rnd:
                n_games_series = series.seed1_wins + series.seed2_wins
                series_lengths[n_games_series] += 1
                series_total += 1
                if series.winner is series.seed1:
                    higher_seed_wins += 1

        # ── Championships ────────────────────────────────────────────────────
        if season.champion:
            champ_counts[f"sim{sim_idx}_{season.champion.franchise.city}"] += 1

        # ── Meta ─────────────────────────────────────────────────────────────
        # (collected per-season, then summarised per-sim)

        league._offseason_adjustments(season)
        league.distribute_revenue()
        league.update_all_owner_happiness(season)
        league.update_all_coach_happiness(season)
        if season.coy:  # COY is set by update_all_coach_happiness — collect after
            arch_coy_wins[season.coy.archetype] += 1
        league._update_losing_streaks(season)
        league._check_relocations(season)
        league._decay_grudges()
        league._evolve_popularity(season)
        league._evolve_market_engagements(season)
        league._evolve_league_popularity(season)
        league._evolve_meta()
        season._popularity          = {t: t.popularity for t in league.teams}
        season._market_engagement   = {t: t.market_engagement for t in league.teams}
        season._league_popularity   = league.league_popularity
        league._check_expansions(season)
        league._check_merger(season)

        # Revenue proxy: owner net profits this season
        for t in league.teams:
            if t.owner:
                team_profits.append(t.owner.last_net_profit)

    # ── Per-sim summaries ────────────────────────────────────────────────────
    ending_league_pops.append(league.league_popularity)
    final_team_counts.append(len(league.teams))
    expansion_counts.append(len(league.expansion_log))
    merger_counts.append(len(league.merger_log))
    reloc_counts.append(len(league.relocation_log))
    total_work_stoppages += league._work_stoppages

    # Meta range this sim
    meta_vals = [league.league_meta]  # final value
    meta_finals.append(league.league_meta)

    # Championship concentration (HHI): per team in this sim
    city_titles: Counter = Counter()
    for s in league.seasons:
        if s.champion:
            city_titles[s.champion.franchise.city] += 1
    n_s = len(league.seasons)
    if n_s > 0:
        hhi = sum((c / n_s) ** 2 for c in city_titles.values())
        champ_concentrations.append(hhi)

    # Back-to-backs / three-peats
    champs = [s.champion for s in league.seasons if s.champion]
    for i in range(len(champs) - 1):
        total_season_pairs += 1
        if champs[i] is champs[i + 1]:
            back2backs += 1
        if i < len(champs) - 2 and champs[i] is champs[i + 1] is champs[i + 2]:
            three_peats += 1

    if (sim_idx + 1) % 10 == 0:
        elapsed = time.time() - t0
        eta = elapsed / (sim_idx + 1) * (NUM_SIMS - sim_idx - 1)
        print(f"  [{sim_idx+1:3d}/{NUM_SIMS}]  {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining",
              flush=True)

elapsed_total = time.time() - t0
print(f"\nDone in {elapsed_total:.1f}s\n")

# ── Helper ────────────────────────────────────────────────────────────────────

def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "n/a"

def fmt(vals, unit="", digits=1):
    if not vals:
        return "n/a"
    mu = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    lo, hi = min(vals), max(vals)
    return f"{mu:.{digits}f}{unit}  (σ={sd:.{digits}f}, range {lo:.{digits}f}–{hi:.{digits}f})"

def section(title):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")

# ── Report ────────────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"  FAKE BASKETBALL — 100×100 SEASON SIMULATION REPORT")
print(f"  {NUM_SIMS} sims × {NUM_SEASONS} seasons  |  {elapsed_total:.0f}s total")
print(f"{'='*60}")

# ── 1. Game Engine ────────────────────────────────────────────────────────────
section("1. GAME ENGINE")
print(f"  Home win rate (reg season):  {pct(home_wins_total, home_games_total)}")
print(f"  Avg score per team/game:     {fmt(all_scores, 'pts', 1)}")
print(f"  Avg implied pace:            {fmt(all_paces, ' poss', 0)}")

print(f"\n  Home win rate by popularity bucket:")
labels = ["Low  (pop < 0.33)", "Mid  (0.33–0.66)", "High (pop > 0.66)"]
for i, lbl in enumerate(labels):
    print(f"    {lbl}:  {pct(home_by_pop_wins[i], home_by_pop_games[i])}"
          f"  ({home_by_pop_games[i]:,} games)")

# ── 2. Scoring & Player Stats ─────────────────────────────────────────────────
section("2. SCORING & PLAYER STATS")
print(f"  League avg PPG (team):       {fmt(season_avg_ppg, 'pts', 1)}")
print(f"  Top player PPG per season:   {fmt(top_ppg, 'pts', 1)}")

if top_ppg:
    buckets = [0, 0, 0, 0]  # <20, 20-25, 25-30, 30+
    for v in top_ppg:
        if   v < 20: buckets[0] += 1
        elif v < 25: buckets[1] += 1
        elif v < 30: buckets[2] += 1
        else:        buckets[3] += 1
    total_s = len(top_ppg)
    print(f"\n  Best player PPG distribution:")
    print(f"    < 20 PPG:   {pct(buckets[0], total_s)}")
    print(f"    20–25 PPG:  {pct(buckets[1], total_s)}")
    print(f"    25–30 PPG:  {pct(buckets[2], total_s)}")
    print(f"    30+ PPG:    {pct(buckets[3], total_s)}")

# ── 3. Competitive Balance ────────────────────────────────────────────────────
section("3. COMPETITIVE BALANCE")
if all_win_pcts:
    print(f"  Win% std dev (per season):   {fmt(all_win_pcts, '', 3)}")
    win_pct_sd_per_sim = []
    # Rough: collect stdev of win% for all teams in a season across all sims
    # (we stored all win%s flat; the stdev of all_win_pcts already serves as the signal)

print(f"  Champ concentration (HHI):   {fmt(champ_concentrations, '', 3)}")
print(f"    (0=perfectly distributed, 1=same team every year)")
print(f"  Back-to-back champs rate:    {pct(back2backs, total_season_pairs)}")
print(f"  Three-peat rate:             {pct(three_peats, max(total_season_pairs-1,1))}")

# ── 4. Playoffs ───────────────────────────────────────────────────────────────
section("4. PLAYOFFS")
print(f"  Higher seed series win rate: {pct(higher_seed_wins, series_total)}")
print(f"\n  Series length distribution ({series_total:,} total series):")
for length in sorted(series_lengths):
    print(f"    {length}-game series:  {pct(series_lengths[length], series_total)}"
          f"  ({series_lengths[length]:,})")

# ── 5. Awards ─────────────────────────────────────────────────────────────────
section("5. AWARDS")
if mvp_team_ranks:
    rank_dist = Counter(mvp_team_ranks)
    total_awards = len(mvp_team_ranks)
    print(f"  MVP team standing (out of total teams in league):")
    for rank in sorted(rank_dist):
        if rank <= 10:
            print(f"    #{rank:2d} seed:  {pct(rank_dist[rank], total_awards)}")
    top5_pct = sum(rank_dist[r] for r in range(1, 6)) / total_awards * 100
    print(f"\n  MVP on a top-5 team:    {top5_pct:.1f}%")
    print(f"  MVP team rank:          {fmt(mvp_team_ranks, '', 1)}")

if dpoy_def_rtg:
    print(f"\n  DPOY def rating:        {fmt(dpoy_def_rtg, ' pts/100', 1)}")

# ── 6. Chemistry ─────────────────────────────────────────────────────────────
section("6. ROSTER CHEMISTRY")
if all_chemistries:
    print(f"  Chemistry multiplier:    {fmt(all_chemistries, 'x', 3)}")
    below_1 = sum(1 for c in all_chemistries if c < 1.0) / len(all_chemistries) * 100
    above_1 = 100 - below_1
    print(f"  Rosters below 1.0x:      {below_1:.1f}%")
    print(f"  Rosters above 1.0x:      {above_1:.1f}%")

# ── 7. League Evolution ───────────────────────────────────────────────────────
section("7. LEAGUE EVOLUTION")
print(f"  Final team count:        {fmt(final_team_counts, ' teams', 1)}")
print(f"  Expansion waves:         {fmt(expansion_counts, '', 1)}")
print(f"  Merger waves:            {fmt(merger_counts, '', 1)}")
print(f"  Relocations:             {fmt(reloc_counts, '', 1)}")
print(f"  Work stoppages:          {total_work_stoppages} total  "
      f"({total_work_stoppages/NUM_SIMS:.2f} per sim avg)")

# ── 8. League Popularity ──────────────────────────────────────────────────────
section("8. LEAGUE POPULARITY")
print(f"  Starting popularity:     {fmt(starting_league_pops, '', 3)}")
print(f"  Ending popularity:       {fmt(ending_league_pops, '', 3)}")
pop_gains = [e - s for e, s in zip(ending_league_pops, starting_league_pops)]
print(f"  Change over 100 seasons: {fmt(pop_gains, '', 3)}")

if ending_league_pops:
    buckets = {"<0.40": 0, "0.40–0.55": 0, "0.55–0.70": 0, ">0.70": 0}
    for p in ending_league_pops:
        if   p < 0.40: buckets["<0.40"] += 1
        elif p < 0.55: buckets["0.40–0.55"] += 1
        elif p < 0.70: buckets["0.55–0.70"] += 1
        else:          buckets[">0.70"] += 1
    print(f"\n  Final popularity distribution ({NUM_SIMS} sims):")
    for k, v in buckets.items():
        print(f"    {k}:  {v} sims  ({100*v/NUM_SIMS:.0f}%)")

# ── 9. Revenue ────────────────────────────────────────────────────────────────
section("9. REVENUE & FINANCES")
if team_profits:
    print(f"  Team net profit/season:  {fmt(team_profits, 'M', 1)}")
    profitable = sum(1 for p in team_profits if p > 0) / len(team_profits) * 100
    print(f"  Profitable team-seasons: {profitable:.1f}%")
    loss_seasons = [p for p in team_profits if p < 0]
    profit_seasons = [p for p in team_profits if p >= 0]
    if loss_seasons:
        print(f"  Avg loss (when losing):  ${statistics.mean(loss_seasons):.1f}M")
    if profit_seasons:
        print(f"  Avg profit (when +):     ${statistics.mean(profit_seasons):.1f}M")

# ── 10. League Meta (3pt era) ─────────────────────────────────────────────────
section("10. LEAGUE META (3PT ERA DYNAMICS)")
print(f"  Final meta value:        {fmt(meta_finals, '', 3)}")
print(f"    (0 = neutral; +0.15 = max 3pt era; -0.15 = min)")
if meta_finals:
    positive = sum(1 for m in meta_finals if m > 0.02) / len(meta_finals) * 100
    negative = sum(1 for m in meta_finals if m < -0.02) / len(meta_finals) * 100
    neutral  = 100 - positive - negative
    print(f"  Final meta distribution:")
    print(f"    3pt-heavy era (>+0.02):  {positive:.0f}%")
    print(f"    Balanced era  (±0.02):   {neutral:.0f}%")
    print(f"    Paint-heavy era (<-0.02):{negative:.0f}%")

print(f"\n{'='*60}")
print(f"  End of report")
print(f"{'='*60}\n")

# ── 11. Coach Impact ──────────────────────────────────────────────────────────
section("11. COACH IMPACT BY ARCHETYPE")

from coach import ARCHETYPE_LABELS as _ARCH_LABELS

total_seasons_all = sum(arch_team_seasons.values())
total_titles_all  = sum(arch_titles.values())
total_coy_all     = sum(arch_coy_wins.values())

# Header
print(f"  {'Archetype':<24}  {'Team-Szns':>9}  {'Win%':>6}  {'NetRtg':>7}  "
      f"{'Titles':>7}  {'COY':>5}  {'Chem':>6}  {'StarHap':>8}  {'DepthHap':>9}")
print(f"  {'-'*100}")

for arch in _ARCHETYPES:
    label      = _ARCH_LABELS.get(arch, arch)
    ts         = arch_team_seasons[arch]
    if ts == 0:
        print(f"  {label:<24}  {'—':>9}")
        continue
    win_pct    = statistics.mean(arch_win_pcts[arch])
    win_sd     = statistics.stdev(arch_win_pcts[arch]) if len(arch_win_pcts[arch]) > 1 else 0.0
    nr         = statistics.mean(arch_net_ratings[arch])
    titles     = arch_titles[arch]
    title_pct  = 100 * titles / total_titles_all if total_titles_all else 0
    coy        = arch_coy_wins[arch]
    coy_pct    = 100 * coy / total_coy_all if total_coy_all else 0
    chem       = statistics.mean(arch_chemistry[arch]) if arch_chemistry[arch] else 0.0
    star_h     = statistics.mean(arch_star_hap[arch]) if arch_star_hap[arch] else 0.0
    depth_h    = statistics.mean(arch_depth_hap[arch]) if arch_depth_hap[arch] else 0.0

    # Expected win% if balanced: 50%; expected title share: 20%; expected COY: 20%
    win_flag   = " ▲" if win_pct > 0.525 else (" ▼" if win_pct < 0.475 else "  ")
    title_flag = " ▲" if title_pct > 25.0 else (" ▼" if title_pct < 15.0 else "  ")
    coy_flag   = " ▲" if coy_pct > 25.0 else (" ▼" if coy_pct < 15.0 else "  ")

    print(f"  {label:<24}  {ts:>9,}  {win_pct:.3f}{win_flag}  {nr:>+7.2f}  "
          f"{title_pct:>6.1f}%{title_flag}  {coy_pct:>4.1f}%{coy_flag}  "
          f"{chem:>6.3f}  {star_h:>8.3f}  {depth_h:>9.3f}")

print(f"\n  Total team-seasons: {total_seasons_all:,}  |  "
      f"Titles awarded: {total_titles_all}  |  COY awarded: {total_coy_all}")
print(f"\n  Win% std dev by archetype (variance / risk):")
for arch in _ARCHETYPES:
    label = _ARCH_LABELS.get(arch, arch)
    if len(arch_win_pcts[arch]) > 1:
        sd = statistics.stdev(arch_win_pcts[arch])
        print(f"    {label:<24}  σ={sd:.4f}")

# ── 12. Coach Impact by Flexibility Quartile ─────────────────────────────────
section("12. COACH FLEXIBILITY QUARTILES")
flex_labels = ["Rigid   (0.00–0.25)", "Firm    (0.25–0.50)",
               "Adapt.  (0.50–0.75)", "Flexible(0.75–1.00)"]
print(f"  {'Quartile':<22}  {'Team-Szns':>9}  {'Win%':>6}  {'σ(Win%)':>8}")
print(f"  {'-'*54}")
for q, lbl in enumerate(flex_labels):
    vals = flex_win_pcts[q]
    if not vals:
        print(f"  {lbl:<22}  {'—':>9}")
        continue
    mu = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    flag = " ▲" if mu > 0.525 else (" ▼" if mu < 0.475 else "  ")
    print(f"  {lbl:<22}  {len(vals):>9,}  {mu:.3f}{flag}  {sd:>8.4f}")

print(f"\n  Interpretation:")
print(f"    ▲ = notably above 50% win rate  (archetype over-performing)")
print(f"    ▼ = notably below 50% win rate  (archetype under-performing)")
print(f"    Expected title share per archetype: 20%  |  Expected COY share: 20%")
