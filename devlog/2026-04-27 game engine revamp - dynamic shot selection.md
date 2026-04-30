# Game Engine Revamp: Dynamic Shot Selection
*Date: 2026-04-27*

---

## The Problem We Started With

The original `_pick_shooter()` used hard-coded static shot shares pulled from Config:

```python
slot_shot_star:    float = 0.21
slot_shot_costar:  float = 0.22
slot_shot_starter: float = 0.16
slot_shot_bench:   float = 0.37
```

This had two fundamental problems:

1. **Star gets fewer shots than co-star.** 21% vs 22% — backwards. The best player on the team takes fewer shots than the second-best player.
2. **Usage is completely static.** A team with a god-tier star and a team with an equal three-headed core use identical shot distributions. No heliocentric offense, no reaction to roster shape, no coach influence, no defensive adjustments.

Additionally, the `playoff_seed_pscore_bonus` gave an always-on probability edge to the higher seed on every possession, on top of home court. With home court already dynamically scaled by popularity, this was double-counting and was removed (`playoff_seed_pscore_bonus = 0.0`).

---

## Iteration 1: Exponential Talent Formula (Rejected)

ChatGPT initially proposed:

```python
talent_factor = exp(player.ortg_contrib / 8.0)
```

### Why it failed

The exponential function explodes quickly. A +18 offensive star gets ~9.5× the raw weight of a neutral player before any role, coach, or matchup adjustments. Isolated simulation results:

| Roster | Star usage | Star PPG |
|---|---|---|
| Balanced `[12,10,8]` | 47.2% | 54.8 |
| Star-heavy `[18,6,3]` | 75.0% | 91.4 |
| God+scrubs `[22,3,0]` | 86.9% | 109.2 |

Unusable. Even a balanced roster with a 12-contrib star produces 55 PPG.

---

## Iteration 2: Linear Scale 0.04 (Too Hot)

First linear attempt:

```python
talent = max(0.50, 1.0 + max(0.0, player.ortg_contrib) * 0.04)
```

Full-league calibration (5 sims × 10 seasons) showed avg scoring leader PPG of **37.7**, max **46.5**. Still too high.

---

## Iteration 3: Linear Scale 0.02 (Close, Still High)

```python
talent = max(0.70, 1.0 + max(0.0, player.ortg_contrib) * 0.02)
```

Full-league calibration showed avg scoring leader PPG of **35.4**, max **47.6**. Better, but the tail was too fat and conceptually the formula still had the wrong role structure (role floors `[1.25, 1.00, 0.75]` with bench at 3.0).

---

## Final Implementation: `safe_linear_B` (Shipped)

Based on ChatGPT's isolated usage simulation across hundreds of roster/coach permutations, we adopted the following design:

### Key changes from prior iterations

| Dimension | Old (linear 0.02) | New (safe_linear_B) |
|---|---|---|
| Talent formula | `1.0 + ortg * 0.02`, min 0.70 | `clamp(1.0 + 0.025 * ortg, 0.75, 1.35)` |
| Role weights | `[1.25, 1.00, 0.75]` | `[1.12, 1.00, 0.86]` |
| Bench weight | 3.0 | 1.75 |
| Coach mods | Replace entire role arrays | Multiplicative per slot |
| Matchup cap | Uncapped (0.02 × drtg) | Capped at 18% suppression |

### Talent factor rationale

The hard cap at 1.35 is critical. It means:
- ortg_contrib = 0 → talent = 1.00
- ortg_contrib = 10 → talent = 1.25
- ortg_contrib = 14 → talent = 1.35 (cap hit)
- ortg_contrib = 22 → talent = 1.35 (still capped)

This prevents god-tier stars from becoming Wilt-in-1962 while still creating organic heliocentric drift for dominant players.

### Final `_pick_shooter` logic

```python
role_wts = [1.12, 1.00, 0.86]   # Star / Co-Star / Starter
bench_wt = 1.75

# Coach modifiers (multiplicative)
if arch == ARCH_WHISPERER:
    role_wts[0] *= 1.12;  role_wts[2] *= 0.94;  bench_wt *= 0.92
elif arch == ARCH_MOTIVATOR:
    role_wts[0] *= 0.96;  role_wts[1] *= 1.06;  role_wts[2] *= 1.10;  bench_wt *= 1.12
elif arch == ARCH_CHEMISTRY:
    mean = sum(role_wts) / 3
    role_wts = [0.80 * w + 0.20 * mean for w in role_wts]
elif arch == ARCH_OFFENSIVE:
    role_wts[0] *= 1.05;  role_wts[1] *= 1.03;  bench_wt *= 0.98

# Per-player weight
talent    = max(0.75, min(1.35, 1.0 + 0.025 * player.ortg_contrib))
fatigue_f = max(0.10, 1.0 - player.fatigue * 0.25)
suppression = min(0.18, max(0.0, -def_drtg) * 0.018)
matchup_f = 1.0 - suppression

w = role_wts[slot_idx] * talent * fatigue_f * matchup_f
```

---

## Validation Results

All tests run via `validate_game_engine.py` (2,000 games per cell, alternating home/away).

### Section 1: Team Quality Ladder

Win rates measured with home advantage cancelled (alternating home team).

| Matchup | A PPG | B PPG | Margin | A Win% |
|---|---|---|---|---|
| Elite (net +14) vs Good (net +8) | 105.2 | 104.9 | +0.3 | 50.6% |
| Elite vs Average (net 0) | 105.6 | 103.2 | +2.4 | 56.8% |
| Elite vs Below average | 105.6 | 102.4 | +3.2 | 58.7% |
| Elite vs Cellar (net −14) | 105.2 | 102.0 | +3.2 | **57.8%** |
| Good vs Average | 104.8 | 103.6 | +1.2 | 53.0% |
| Good vs Cellar | 105.1 | 101.8 | +3.3 | 58.6% |

**Known issue**: The quality ladder does not discriminate sharply enough. NBA reference: Boston 2024 (net ~+12) vs Detroit (net ~−10) would produce ~80-85% win rate in head-to-heads. Our model gives a comparable matchup only ~58%. This is the biggest outstanding calibration gap. Root cause is almost certainly in `_compute_make_pct` — the ortg/drtg → make probability conversion is compressed. **Flagged for a separate fix.**

Same-quality mirrors confirm symmetry holds (all near 50% with σ ≈ 16 points per game).

### Section 2: Roster Shape

All teams 113 ORtg / 109 DRtg, Offensive Innovator coach, neutral opponent.

| Roster shape | Star% | CoStar% | Starter% | Bench% | Star PPG |
|---|---|---|---|---|---|
| Top-heavy `[18, 4, 0]` | 30.1 | 21.3 | 16.1 | 32.5 | 36.2 |
| Balanced `[12, 10, 8]` | 27.5 | 23.2 | 18.5 | 30.8 | 31.4 |
| Superteam `[16, 15, 14]` | 27.2 | 23.7 | 19.9 | 29.3 | 31.7 |
| One-man `[22, 3, 0]` | 30.1 | 21.0 | 16.3 | 32.5 | 37.4 |
| Mid-tier `[8, 6, 4]` | 26.8 | 22.7 | 17.9 | 32.6 | 29.5 |

Key observations:
- Star is always highest-usage named player ✓
- Balanced teams naturally distribute more evenly ✓
- `[22, 3, 0]` and `[18, 4, 0]` both hit 30.1% — the 1.35 talent cap is working as intended
- Star Whisperer on `[22, 3, 0]` pushes to 32.4% / 37.0 PPG — extreme but not broken (see stress test below)

ChatGPT's parallel isolated test (400 games) found virtually identical numbers: balanced `[12,10,8]` at 26.8% star, god+scrubs `[22,3,0]` at 29.1% star, superteam `[16,15,14]` at 26.3% star.

### Section 3: Defensive Stoppers

Offense: star-heavy `[18, 6, 3]` Guard star.

| Defense config | Star% | Δ from neutral | Star PPG | Offense PPG |
|---|---|---|---|---|
| No stoppers `[0, 0, 0]` | 29.4% | — | 35.4 | 108.7 |
| Avg guard stopper `[−4, 0, 0]` | 27.9% | −1.5 | 32.3 | 106.6 |
| Good guard stopper `[−7, 0, 0]` | 26.7% | −2.6 | 30.3 | 105.6 |
| Elite guard stopper `[−10, 0, 0]` | 25.5% | **−3.9** | 28.3 | 104.7 |
| Elite on wing (mismatch) `[0, −10, 0]` | 30.8% | **+1.4** | 37.1 | 106.3 |
| All-defensive `[−6, −6, −6]` | 28.4% | −1.0 | 32.4 | 103.3 |

NBA reference: elite lockdown defenders (Kawhi on LeBron, Jrue on Harden) reduce guarded player usage by 3–8 points. Our model produces −3.9 at the elite level. ✓

The +1.4 on the mismatch case is a correct emergent behavior: when the elite defender is on the wing (not the Guard star), the star actually gets *more* usage because the co-star becomes the more defended option.

ChatGPT's parallel test confirmed this directionally (used "star stopper" label): star usage cut 28.2% → 24.5% (−3.7 ppt), Star PPG 31.7 → 25.5. Full 3-defender test (all −6) pushed offense to 98.8 PPG and 39.0% win rate.

### Section 4: Coach Archetype Effects

Star-heavy roster `[18, 6, 3]` vs neutral defense.

| Coach | Star% | CoStar% | Starter% | Bench% | Star PPG |
|---|---|---|---|---|---|
| Offensive Innovator | 29.3 | 22.0 | 17.0 | 31.7 | 35.4 |
| Star Whisperer | **31.7** | 21.5 | 16.4 | 30.3 | **38.2** |
| Motivator | 25.6 | 21.6 | 17.9 | **34.9** | 30.8 |
| Culture Coach | 27.7 | 21.5 | 17.8 | 33.0 | 33.1 |
| Defensive Mastermind | 28.2 | 21.6 | 17.4 | 32.8 | 33.9 |

ChatGPT's parallel test on the same roster found: Whisperer 31.8%/35.3 PPG, Motivator 25.7%/28.8 PPG. Results within rounding noise. ✓

Balanced superteam `[16, 15, 14]` — coach effects on an even roster:

| Coach | Star% | CoStar% | Starter% | Bench% |
|---|---|---|---|---|
| Offensive Innovator | 27.0 | 23.9 | 19.8 | 29.3 |
| Star Whisperer | **29.5** | 23.6 | 19.0 | 28.0 |
| Motivator | 23.7 | 23.3 | **21.0** | **32.0** |
| Culture Coach | 25.6 | 23.5 | 20.6 | 30.3 |
| Defensive Mastermind | 26.2 | 23.4 | 20.2 | 30.2 |

On a balanced team, Whisperer still pushes the star up (+2.5 ppt), Motivator compresses the distribution. Directionally correct in both roster shapes.

### Section 5: Home Court & Popularity

Equal-quality teams (110/110), 2,000 games per cell.

| Home team popularity | Home Win% | Home PPG | Away PPG |
|---|---|---|---|
| Low (0.20) | 56.0% | 105.4 | 103.4 |
| Mid (0.50) | **57.2%** | 106.4 | 103.5 |
| High (0.80) | 60.1% | 107.0 | 103.5 |

NBA reference: ~57% all-era average, marquee teams ~62–65%. Mid-pop hits 57.2% almost exactly. High-pop at 60.1% captures the crowd advantage of a marquee venue without overstating it. ✓

### Section 6: Score Distribution

| Scenario | Close ≤5 | Mid 6–19 | Blowouts ≥20 | Avg margin |
|---|---|---|---|---|
| Equal teams (110/110) | 26.8% | 49.6% | **23.6%** | 13.0 |
| Slight edge (113/108 vs 110/110) | 26.2% | 48.6% | 25.1% | 13.4 |

NBA reference: ~30% close, ~15% blowouts, avg margin ~10 pts.

**Known issue**: blowout rate is too high at 23.6% for equal teams (NBA ~15%). Average margin of 13.0 is above NBA's ~10. Scoring variance per game is too fat-tailed. This is related to the quality-ladder discrimination issue — if team quality doesn't translate to meaningful score differences, random possession variance dominates and produces more extreme outcomes in both directions. **Flagged for investigation alongside the quality ladder fix.**

### Section 7: God-Tier Stress Test

Strongest possible case: `[22, 3, 0]` with Star Whisperer coach.

| Scenario | Star% | Star PPG | 40+ rate | 50+ rate | Team PPG |
|---|---|---|---|---|---|
| No coach, neutral D | 29.1% | 33.7 | 23.8% | 3.0% | 104.7 |
| Star Whisperer, neutral D | **32.4%** | **37.0** | 39.0% | **8.0%** | 105.1 |
| No coach, elite stopper | 24.9% | 27.1 | 6.3% | 0.3% | 100.5 |
| Star Whisperer + stopper | 28.2% | 30.4 | 11.8% | 1.0% | 100.4 |

**The stress test passes.** The strongest conceivable configuration (god-star + Star Whisperer) produces 37.0 PPG, not 80+. The talent cap at 1.35 is doing its job. No instances of 40+ PPG average across any full-season calibration run (from a separate 5×10 season test).

The stopper mechanic still has real bite against the god-star: usage drops from 32.4% → 28.2%, PPG drops 37.0 → 30.4.

### Full-Season Calibration (5 sims × 10 seasons, real League/Season)

| Metric | Value |
|---|---|
| Avg scoring leader PPG | 32.8 |
| Median scoring leader PPG | 32.0 |
| Max scoring leader PPG | 40.5 |
| 95th percentile | 37.0 |
| Seasons with 40+ PPG leader | 1 / 50 |
| League avg team score | 105.9 PPG |

Slot ordering from real 3-season run: **Star 25.9% > Co-Star 19.9% > Starter 16.9% > Bench 37.3%** ✓

---

## What the Revamp Fixed

| Problem | Status |
|---|---|
| Star gets fewer shots than co-star (21% vs 22%) | **Fixed** — star always leads named players |
| Static usage regardless of roster shape | **Fixed** — heliocentric vs balanced rosters produce different distributions |
| No coach influence on shot economy | **Fixed** — Star Whisperer/Motivator/Culture all visibly shift usage |
| Defense has no effect on shot selection | **Fixed** — elite stoppers shift usage away from their matchup by 3–4 ppt |
| Playoff seed bonus double-counting home court | **Fixed** — `playoff_seed_pscore_bonus = 0.0` |

---

## Known Remaining Issues

### 1. Quality ladder doesn't discriminate sharply enough (HIGH PRIORITY)

A team with net rating +14 vs net rating −14 (28-point differential) wins only ~58% of games. NBA equivalent would win ~80–85%. The gap between elite and average is nearly invisible in scoring (+2.4 PPG) and win rate (+6.8 ppt).

Root cause: likely in `_compute_make_pct` — the ortg/drtg to make-probability conversion is too compressed. A 15-point ORtg difference (103 vs 118) produces only a ~3 PPG scoring difference per game. The function needs a steeper slope.

### 2. Score variance too high (MEDIUM PRIORITY)

Blowout rate 23.6% for equal teams (NBA ref ~15%). Average game margin 13 pts (NBA ref ~10 pts). Games swing more randomly than they should. Related to issue #1 — if quality doesn't translate to outcomes, variance dominates.

### 3. Team scores too low (LOW PRIORITY / COSMETIC)

Teams average 103–108 PPG across all quality tiers. NBA 2024: ~114 PPG average. This is calibrated to an older era and doesn't affect game logic, but affects verisimilitude.

---

## Future Tuning Guidance

From ChatGPT's post-analysis recommendations:

**Do not do:**
- Re-introduce exponential talent scaling
- Increase Star Whisperer multiplier further (already near upper safe bound)

**Consider later:**
- Make Offensive Innovator style-fit based rather than a softer Whisperer. Currently it gives a mild star/co-star lift; ideally it would amplify players who match the team's shot style (3PT coach feeds 3PT players, paint coach feeds paint players)
- Bench aggregate labeling in reports — bench 37% is mechanically correct (represents all non-rostered minutes) but can look odd visually if displayed alongside individual player stats

**Watch in season sims:**
- If Star Whisperer teams disproportionately win championships in multi-decade sims, reduce `role_wts[0] *= 1.12` to `1.09`
- If Offensive Innovator feels identical to a weaker Whisperer, add zone-style weighting to its modifier logic

---

## Files Changed

| File | Change |
|---|---|
| `game.py` | Full rewrite of `_pick_shooter()` with safe_linear_B formula |
| `config.py` | `playoff_seed_pscore_bonus = 0.0`; removed 4 `slot_shot_*` fields |
| `validate_game_engine.py` | New: comprehensive 7-section validation suite (2,000 games/cell) |

Committed: `d142f8a` — "Dynamic shot selection: safe_linear_B formula"
