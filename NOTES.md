# Fake Basketball — Project Notes

## What It Is

A text-based basketball league simulation / management game. Two modes:

- **Headless sim** (`main.py`, archived) — runs N seasons automatically, outputs results
- **Commissioner game** (`commissioner.py`) — interactive, season-by-season. You are the league commissioner: manage expansion, mergers, relocations, CBA negotiations, owner relations, playoff interventions, rival leagues, and financial health across a multi-decade sim

---

## What We've Built

### Game Engine (`game.py`)
- Possession-by-possession simulation: roll shooter → roll zone → match defender → roll outcome
- Four shot zones: Paint, Mid, 3pt, FT — each with calibrated base make% (0.57 / 0.42 / 0.36 / 0.76)
- Era-driven zone shift: `3pt_base += league_meta × 0.13`; `paint_base -= league_meta × 0.10` — FT and mid stay fixed
- Player-level shot attribution: Star (21%), Co-Star (22%), Starter (16%), Bench aggregate (37%)
- Bench quality is dynamic — influenced by owner profit, GM competence, and team popularity
- Make% formula: `base × (1 + off_adj + def_adj) + prob_bonus` where adjustments scale off player ortg/drtg contributions
- Home court advantage is **dynamic**: `base (0.007) + pop_scale (0.014) × home.popularity` — popular teams get meaningfully stronger home floors
- Playoff seed bonus (0.005) is intentionally small — better/more popular teams already get the home advantage
- Overtime: alternate possessions until tie breaks
- Per-game player logs: PPG, FGA/FGM, 3PA/3PM, FTA/FTM, poss defended, pts allowed
- Injured players are excluded per-game via `out_home`/`out_away` frozensets; `random.choices` weight normalization redistributes their possessions naturally

### Player Model (`player.py`, `season.py`)
- 3 rostered slots per team: Star (50% rating weight), Co-Star (30%), Starter (20%)
- Hidden career arcs: peak season, career length, start multiplier — players develop and decline naturally
- **Chemistry**: bonus-only cohesion multiplier (floor 1.00, ceiling 1.15). Two components:
  - Fit bonus: positional variety (+0.03) + zone diversity (+0.02)
  - Continuity bonus: saturating curve `max_bonus × (1 − e^(−k × avg_pair_seasons))`, ceiling 0.07
  - Bad roster fit = no bonus, not a penalty; the talent hit from suboptimal construction is punishment enough
- **Durability** (`durability: float`, 0.50–1.00): base injury resistance, drawn at creation. Labels: Glass / Average / Sturdy / Iron
- **Fatigue** (`fatigue: float`, 0.0–1.0): accumulated playoff load. Decays 32% each offseason (68% carries over). Displayed as energy % (`(1−fatigue)×100%`) — 🔋100% = fresh, 🔋0% = exhausted
- **Fatigue in-game effect**: tired players perform worse each possession — offensive `ortg_contrib` scaled by `(1 − fatigue×0.12)` (max ~12% penalty), defensive `drtg_contrib` scaled by `(1 − fatigue×0.07)` (max ~7% penalty). Dynasty teams entering the playoffs fatigued are genuinely weaker, not just injury-prone.
- **Injury system**: pre-season roll per player. Probability = `base (12%) + (1−dur)×20% + fatigue×28% + age_penalty`. If injured: misses 5–20 games; those slots use bench production. Repeat champions compound fatigue → rising injury risk
- Season stats accumulated in `PlayerSeasonStats` (PPG, FG%, 3P%, FT%, Def Rtg, games missed)
- Awards: MVP (PPG × win% weighting), OPOY (pure PPG, non-MVP), DPOY (lowest Def Rtg), Finals MVP
- Award pool is league-wide — lottery team stars can win with dominant enough production
- Career leaders and best single seasons tracked; name/team snapshots baked into each Season object (survives retirements without showing placeholder IDs)

### League Systems (`league.py`)
- **Expansion**: triggers on sustained popularity threshold; normal (2 teams) and boom (4 teams) waves
- **Merger**: rival league absorbs into the main league when league popularity stays below the trigger threshold for consecutive seasons
- **Relocation**: chronically losing teams in small markets can move; grudge system tracks vacated cities
- **League meta (era dynamics)**: 3pt vs paint lean drifts over time; champion style influences direction; rule-change shocks can reverse momentum; meta directly shifts zone base make%
- **Market engagement**: each city's fan engagement evolves separately from team popularity
- **Playoff fatigue**: each offseason, `fatigue += playoff_games × 0.020` for rostered players; then `fatigue *= 0.68` (decay). Dynasty teams accumulate meaningful fatigue by year 2–3
- **Champion entropy**: after each title defense, the champion's ortg/drtg regress toward baseline by `0.84^N` (N = consecutive titles, capped at 3). 1st defense: ~−1.3 pts; 2nd: ~−2.4 pts; 3rd+: ~−3.4 pts. Simulates scouting saturation, complacency, and the difficulty of maintaining peak intensity year after year.

### Owner System (`owner.py`, `league.py`)
- Each team has an owner with: motivation (money / winning / local hero), competence (hidden), personality, loyalty
- Owner happiness drives threat escalation: Quiet → Watching → Demanding
- Revenue efficiency scales with competence (60–100%)
- Owner lifecycle: scandals, heir succession, ownership changes, walk-outs
- CBA negotiations every 5 seasons — affects player happiness modifiers, relocation protection, revenue sharing
- All owner decisions use number input (1/2/3); CBA has a random pre-selected default
- **Name deduplication**: first names are globally unique across the league; first + last name pool doubled (108 male, 72 female, 54 swing, 90 WASP, 75 southern, 45 hyphen)

### Revenue & Finances
- Each team earns: `market_engagement × effective_metro × revenue_per_fan_million`
- Commissioner takes 20% (treasury); teams keep 80% adjusted by owner competence
- Operating costs scale with market size
- Treasury funds commissioner interventions (playoff rigs, showcase events, rule changes)

### Rival League System (`rival.py`, `league.py`)
Three rival formation paths, each a different flavor of crisis:

- **Type A — External investors**: triggers when league popularity stays above 0.43 for 5 consecutive seasons (first possible ~season 13). Passive legitimacy drain once rival exceeds 35% strength. Actions: monitor / talent war / legal pressure / brokered merger. Frequency: ~1 per 30-season save.
- **Type B — Owner defection**: a THREAT_DEMAND ringleader spends 2 seasons recruiting followers; split fires if ≥4 owners defect. Warning appears on commissioner desk. ~6% chance of actual split per sim; rare but real.
- **Type C — Player walkout**: triggers off an unresolved CBA work stoppage. Striking players form a barnstorming circuit; your league runs scab replacement rosters. Hold firm destroys legitimacy/popularity; concede or partial deal ends the crisis faster. The most mechanically severe rival path.

All three types integrate with the FA pool, legitimacy, treasury, owner pressure, and expansion/merger logic.

### Coach System (`coach.py`, `league.py`)
- Five archetypes: Culture Coach, Star Whisperer, Defensive Mastermind, Offensive Innovator, Motivator
- Each archetype has six base modifiers: ortg_mod, drtg_mod, chem_scale, star_hap, depth_hap, fa_draw
- Scaling: `flex_scale = 1.35 − 0.70 × flexibility`; `rating_scale = 0.50 + rating`; combined `scale = flex_scale × rating_scale`
- COY bonus: `+0.02 × min(3, coy_wins)` added to fa_draw — legends attract more stars
- FA draw: coach `fa_draw × 10.0` wired into all three motivation branches; loyalty-motivated players rank destinations by coach fa_draw
- COY always fires: season 1 = best net rating, season 2+ = largest net-rating improvement (no threshold gatekeeping)
- Coach lifecycle: hot seat set/cleared by owner happiness; auto-fired when demanding owner + tenure ≥ 2; COY always clears hot seat
- Two coach types: lifer (generated fresh) and former player (retired → coach, skews star whisperer / chemistry)
- `generate_coaches_balanced(n)`: ensures near-equal archetype distribution at league init
- Balance tuned via 5×30 simulation (Star Whisperer 25.7% titles, Offensive 20.1% — plausible variance, no archetype dominant)

### Commissioner Game Features
- **Playoff interventions**: nudge or rig series outcomes at legitimacy cost; cost compounds per intervention per season
- **Star FA events**: commissioner can influence where star free agents land
- **Rule changes**: shift league meta; legitimacy cost escalates with prior changes
- **Talent investment**: boost draft class quality for N seasons
- **Expansion / merger decisions**: interactive approval with financial projections
- **Owner meetings**: respond to demands, discipline, negotiate — consequences affect legitimacy and team behavior
- **CBA negotiations**: union proposals, commissioner counter-offers, work stoppage risk; random default pre-selected
- **Revenue sharing toggle**: reduce commissioner take to help struggling teams

### Save / Load System
- Single save slot (`save.pkl`) in the game directory
- Autosave fires automatically after every completed season
- On startup: if a save file exists, offers "Continue / New league / Quit"; otherwise goes straight to setup
- Between-season menu includes "Save & quit" and "Quit without saving" options
- Pickle serializes the full `CommissionerGame` object graph (handles circular refs automatically)
- Module-level player globals (`_next_id`, `_used_names`) are saved separately in the payload dict and restored on load — they live outside the object graph
- Atomic write: saves to `.tmp` then `os.replace()` to prevent corrupt saves on interruption
- Version mismatch or corruption: graceful error, offers "Start new league / Quit"

### Reporting System
- **League History**: season-by-season champion, runner-up, top scorer, era tag, parity (win% σ), events
- **Team History**: franchise season log with top player + PPG per season
- **Player Stats**: season leaderboards (scoring, defense, efficiency) · best single seasons all-time · career leaders; all screens use season-start snapshots (no placeholder P{id} names for retired players)
- **Rosters**: current players with last season's actual stats (PPG, FG%, Def Rtg, games missed) + Dur label + 🔋 fatigue level (color-coded)
- **Owner Dashboard**: per-team happiness, competence, P&L, threat level, revenue efficiency
- **Coaching Dashboard**: all teams with archetype, flex, horizon, tenure, COY wins, happiness, computed ORtg/DRtg modifiers, hot seat; COY history last 10 seasons; archetype mix summary
- **Market Map**: popularity, engagement, fan counts, grudge cities
- **Event Log**: all expansions, mergers, relocations with season tags
- **All-Time Records**: championships table, streaks/droughts, best/worst team seasons
- **Rivalries**: RS head-to-head, playoff series history, Finals matchup history
- **Playoff Analysis**: higher-seed win% by round, series length distribution, home court win% by popularity tier

### Injury & Fatigue Visibility
Three places surface the system during play:
1. **Regular season recap** (before playoff bracket) — "Notable Injuries" table: any player who missed 5+ games listed with games missed, durability label, and fatigue
2. **Pre-playoff series scout card** — each Star/Co-Star row shows games missed (red if 5+) and 🔋 fatigue reading
3. **Commissioner desk flags** — playoff-bound teams with any player at 0.35+ fatigue get a 🔋 flag (gold ≥0.35, red ≥0.50)

### Season Summary (3 screens)
**Screen A — Standings**: champion callout (defeated runner-up, series score), regular season standings table with seed/record/pts/diff/net rtg/top player, playoff bracket recap with `(#N)` seeds on every team.

**Screen B — Awards Night**: MVP / OPOY / DPOY / Finals MVP / COY — each with the exact selection metric, career win count (e.g. "3×"), and streak badge ("2 in a row" when applicable). Stars to Watch block (top 8 by tier with mood/contract/trend flags).

**Screen C — League Health / Fan Engagement**: per-market table (sorted by market size) showing pop bar, %, fans, engagement %, and commissioner flags (CHAMP, RELOC RISK, LOSING STREAK, HOT SEAT, STAR RISK, STAR EXP, SURGING, FADING, LOW POP). Four-pillar summary with top 2 drivers. Notable events. [H] for full pillar breakdown.

### UI Consistency
- All decision inputs use numbers (1/2/3) throughout — no letter-based inputs (A/C/R, S/F/I, etc.)
- `_pick()` / `choose()` helper always has a default; Enter accepts it
- CBA and commissioner desk default to a reasonable pre-selection; owner agenda/scandal screens require explicit choice (intentional — every option has real consequences)
- Award displays always surface the metric that drove the selection — no "trust me" awards

---

## Simulation Findings (5×30 benchmark, post-rival-league)

| Metric | Before | After fixes | Target |
|---|---|---|---|
| Avg scoring leader PPG | 38.8 (old) / 30.7 (pre-fix) | **28.5** | 26–30 ✓ |
| Repeat title rate | 42.9% (old) / 32.4% (pre-fix) | **32.4%** avg (range 14–52%) | 25–30% |
| Three-peat rate | 26.2% (old) / 13.6% (pre-fix) | **12.9%** | 10–15% ✓ |
| Home win rate | 56.8% | ~57% (unchanged) | ~57% acceptable |
| Type A rival frequency | 0 / 30 seasons | **1 / 30 seasons** | ~1–2 ✓ |

Notes:
- Repeat rate high-end outlier (52%) is a seed with exceptional founding-roster talent concentration; average is improving
- Chemistry effect: 5-year continuity edge ≈ +0.66 pts/game; "meaningful tiebreaker" tier — intentional

---

## Backlog (top items)

See `devlog/2026-04-26 revision backlog.md` for full list with priority picks.

- **Fan dialogue** — commissioner receives fan sentiment signals (letters, social pulse, market reactions) as flavor and pressure
- **Career stat tracking / Hall of Fame** — cumulative stats across seasons; HOF induction as late-game prestige moment
- **Generational prospect event** — flag elite-ceiling prospects the season *before* the draft; LeBron 2003 / Wemby 2023 model
- **Star FA as league-wide event** — when a big name hits FA, it's broadcast-level entertainment for the whole league, not just a commissioner decision
- **In-game box scores** — per-game stat display during playoff interactive mode
- **Coach hire/fire cycle** — interactive coaching market when a seat opens; coach contracts and poaching
- **Calibration**: money owner happiness rescale (#1), engagement pull config (#4), happiness as slope not cliff (#22)
- **Multi-slot saves** — currently single slot only
- **Expansion bidding** — franchise fees, market research, owner vetting; currently auto-triggered

---

## Key Config Reference

```python
# Game engine
home_pscore_bonus_base      = 0.007   # floor for all teams
home_pscore_bonus_pop_scale = 0.014   # × team.popularity → crowd bonus
playoff_seed_pscore_bonus   = 0.005   # small always-on edge for higher seed

# Era-driven zone shift
meta_3pt_base_scale         = 0.13    # 3pt base += league_meta × this
meta_paint_base_scale       = 0.10    # paint base -= league_meta × this

# Player model — rating weights
slot_weight_star    = 0.50
slot_weight_costar  = 0.30
slot_weight_starter = 0.20

# Player model — possession frequency (calibrated for 26–30 PPG scoring leader)
slot_shot_star      = 0.21
slot_shot_costar    = 0.22
slot_shot_starter   = 0.16
slot_shot_bench     = 0.37

# Zone base make%
ZONE_FT    = 0.76
ZONE_PAINT = 0.57
ZONE_MID   = 0.42
ZONE_3PT   = 0.36

# Chemistry
chemistry_min               = 1.00   # floor — never hurts
chemistry_max               = 1.15   # ceiling
chemistry_positional_bonus  = 0.03
chemistry_zone_bonus        = 0.02
chemistry_continuity_max    = 0.07
chemistry_continuity_k      = 0.55

# Injury & fatigue
player_injury_base_prob          = 0.12
player_injury_durability_scale   = 0.20
player_injury_fatigue_scale      = 0.28
player_injury_age_threshold      = 30
player_injury_age_scale          = 0.012
player_injury_games_min          = 5
player_injury_games_max          = 20
player_fatigue_per_playoff_game  = 0.020   # was 0.012
player_fatigue_decay             = 0.68    # fraction carried to next season (was 0.60)

# Dynasty decay
champion_entropy_factor = 0.84   # compounds per consecutive title (up to 3×)

# Rival league — Type A
rival_a_popularity_threshold = 0.43   # calibrated to actual equilibrium ~0.47 (was 0.72)
rival_a_consecutive_seasons  = 5      # seasons above threshold (was 3)
rival_a_min_season           = 8      # earliest trigger (was 5)
rival_a_cooldown             = 10     # seasons between rivals (was 8)
rival_a_legit_drain_rate     = 0.015  # legitimacy drained per season once rival > 35% strength
```
