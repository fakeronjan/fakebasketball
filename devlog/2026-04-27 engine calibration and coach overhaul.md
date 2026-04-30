# 2026-04-27 — Engine Calibration & Coach System Overhaul (Session 5)

## What we did

Five distinct things shipped this session, all committed and pushed to GitHub.

---

### 1. Quality ladder calibration (`player_adj_scale = 85`)  
**Commits:** 5a32193

The quality ladder was previously showing barely 58% win rate for Elite vs Cellar — not because the formula was wrong, but because the validation test was broken. It used `team.ortg = 103` for cellar teams but player contribs of `[1.5, 0.5, 0]`, meaning the possession engine was actually evaluating them as average-quality. Fixed the tier definitions to use proper per-tier ortg AND drtg contribs (cellar players have negative ortg; elite players have negative drtg).

Added `player_adj_scale: float = 85.0` to Config as a separate parameter from `ortg_baseline`. `_sim_possession` now passes `cfg.player_adj_scale` to `_compute_make_pct` instead of `cfg.ortg_baseline`. This sharpens quality discrimination without affecting displayed team ratings or `compute_ratings_from_roster`.

**Results at scale=85:**
| Matchup | Win% | Target |
|---|---|---|
| Elite vs Cellar | 84.5% | 78–85% ✓ |
| Elite vs Avg | 72.5% | 65–73% ✓ |
| Good vs Avg | 63.7% | 58–63% ✓ |

Also updated `validate_game_engine.py` quality ladder tier defs to match corrected contribs.

---

### 2. Blowout decomposition analysis  
**File:** `analyze_blowouts.py`

Ran 5,000 games per scenario and tracked slot-level (star/co-star/starter/bench) contribution to the point margin in blowout (≥20) vs close (≤8) games.

Key findings:
- **Equal-team blowouts** are pure variance — slot distribution barely changes between blowouts and close games. All slots run hot or cold together. The σ≈16 baseline is the culprit.
- **Quality-mismatch blowouts** are star-driven — in Elite vs Cellar games, the star slot accounts for **42% of the blowout margin** (vs 27% baseline in equal-team games). The elite star nets +18 pts per blowout game.
- Blowout *rate* (43.8% for Elite vs Cellar vs 22.9% for equal teams) is the quality signal; decomposition within blowouts tells the structural story.
- Baseline 23% blowout rate for equal teams is a separate variance problem, deferred.

---

### 3. Coach system fully wired into possession engine  
**Commits:** 51651e9

**Before:** Coach archetypes only affected `_pick_shooter()` usage weights. `ortg_mod`/`drtg_mod` showed up in displayed `team.ortg`/`team.drtg` but were invisible to `_compute_make_pct`, which uses `player.ortg_contrib / player_adj_scale`.

**After:** `_compute_make_pct` has two new params `coach_ortg_mod` and `coach_drtg_mod` (default 0.0, backward-compatible). `_sim_possession` extracts these from `coach.compute_modifiers()` at possession time and adds them to the shooter's `ortg_contrib` and the defender's `drtg_contrib`.

Effect: an Offensive Innovator (avg coach, scale=1.0) adds +3 to every named player's effective ortg_contrib; a Defensive Mastermind adds −3.5 to every defender's effective drtg_contrib. This is in the same pts/100 units as player contribs, so the magnitudes are calibrated.

**Validation:**
- Quality ladder unchanged (both teams use same archetype — effects cancel symmetrically)
- Defensive beats Offensive: 53.9% on equal rosters ✓
- Coach quality matters: elite (rating=1.0) vs poor (rating=0.0) same archetype → 56–59% win rate
- Same-archetype mirrors: 50% ✓

Every coach archetype now touches three layers: (1) usage distribution via `_pick_shooter`, (2) shot quality via `_compute_make_pct`, (3) off-court effects (happiness, FA draw, chemistry).

---

### 4. Interactive coaching market  
**Commits:** e690ee6

**Before:** When a hot-seat coach got auto-fired, `_coaching_pool_hire()` silently assigned the best-fit coach. Commissioner had zero agency.

**After:**
- `league._pending_coach_hires`: new list that captures `(team, fired_coach_name)` tuples instead of immediately hiring
- `league.resolve_coaching_hire(team, recommended=None)`: does the actual hire; commissioner recommendation gets +0.40 scoring bonus (strong influence, but owner fit can still override)
- `commissioner._handle_coaching_market(season)`: new interactive screen in `_post_season` (after player offseason, before commissioner desk). Shows each vacancy with team context, owner mood/motivation, full coach pool with star rating, archetype, fit label (Strong/Neutral/Poor), and former-player bio. Commissioner can recommend a candidate or defer to owner. Results screen confirms who was hired and whether recommendation was followed.

---

### 5. COY/championship coach immunity + standings top scorer  
**Commits:** 53daedc, b5823cb

**Immunity:** Added `immunity_seasons: int = 0` to Coach dataclass. COY win and championship both award `max(current, 2)` immunity seasons. Each season of immunity consumed decrements the counter and blocks hot_seat assignment regardless of owner mood.

**Standings:** Removed ORtg/DRtg columns (were team config values, not game-computed — confusing noise). Replaced with per-team top scorer: last name (≤13 chars) + PPG from `season.player_stats`, muted styling so it doesn't compete with the record/diff highlights.

---

## Star player variance (sanity check)

Ran 500-game analysis on star player game-level stats:

| Profile | Avg PPG | SD | Min | p25 | Med | p75 | Max |
|---|---|---|---|---|---|---|---|
| Elite star (+12, Offensive) | 34.9 | 8.8 | 10 | 29 | 34 | 41 | 61 |
| Good star (+8, Offensive) | 31.7 | 8.5 | 11 | 26 | 31 | 37 | 60 |
| Elite star (+12, Whisperer) | 37.3 | 9.2 | 15 | 31 | 37 | 43 | 67 |

Variance shape feels right — no goose eggs, realistic explosions, clustered around mean. Usage is slightly high vs real NBA (structural compression from 3-slot model), but internally consistent.

---

## Current backlog (priority order)

1. Fan dialogue — commissioner receives fan sentiment signals
2. Career stat tracking / Hall of Fame
3. Generational prospect event — pre-draft hype
4. In-game box scores during playoffs
5. Expansion bidding
6. Multi-slot saves
7. Baseline blowout rate fix (~23% equal-team, should be ~15%)
8. Calibration: owner happiness rescale, engagement pull, happiness as slope not cliff

## Known deferred issues

- Baseline blowout rate ~23% for equal-quality teams (NBA ref ~15%). Not a quality-discrimination problem — it's σ≈16 game variance. Needs pace or possession count adjustment.
- Coach fire currently only triggers on owner-demand auto-fires. No voluntary departures or retirements from coaching yet.
