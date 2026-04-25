# Four-Pillar League Health Framework
*Session: 2026-04-25*

## What was built

### Design
Replaced the flat league health signal list with a four-pillar framework:

| Pillar | Measures | Baseline (no events) |
|--------|----------|----------------------|
| **Integrity** | Trustworthiness & governance | A (high by default; drops when rigging/grudges/stoppages accumulate) |
| **Parity** | Competitive balance & access | C (genuine challenge; needs active attention) |
| **Drama** | Narrative & story arcs | C- (requires actual events — dynasties, droughts, rivals — to lift) |
| **Entertainment** | Product quality & star power | B+/A (good by default; drops with injuries or extreme defensive eras) |

### Integrity inputs
| Signal | Weight |
|--------|--------|
| Legitimacy | 0.50 (Major) |
| Grudge markets (metro-weighted avg) | 0.20 (Moderate) |
| Work stoppage hangover (5-yr arc) | 0.15 (Acute) |
| Owner stability (fraction QUIET) | 0.08 (Minor) |
| Star player happiness (peak_overall ≥ 12 weighted avg) | 0.07 (Minor) |

### Parity inputs
| Signal | Weight |
|--------|--------|
| Rating spread (std dev of team net ratings) | 0.25 |
| Playoff rotation breadth (distinct playoff teams, 8-season window) | 0.25 |
| Championship concentration (distinct champions, 8-season window) | 0.20 |
| Longest playoff drought (normalized by league size) | 0.20 |
| Revenue gap (top vs. bottom team net profit) | 0.05 |
| Small market success (playoff rate for bottom-quartile metro teams) | 0.05 |

### Drama inputs
| Signal | Weight | Notes |
|--------|--------|-------|
| Consecutive finals trips curve | 0.30 | Bell curve: peak at 2 (+0.65), flat at 3 (0.50), negative at 4 (0.30), very negative at 5+ (0.15) |
| Playoff drama index (Game 7s, series length, upset rate) | 0.30 | Range 0.30–1.00 |
| Championship drought broken | 0.15 | Spike: 10+ seasons = 0.90; 5–9 = 0.70; baseline 0.50 |
| Rival league existence | 0.15 | Active = 0.65; resolved = 0.60; none = 0.50 |
| Meta shock events (rule changes) | 0.05 | Fires = 0.80; none = 0.50 |
| Star playoff injuries (tier-weighted) | 0.05 | Injury rate drives score down |

### Entertainment inputs
| Signal | Weight | Notes |
|--------|--------|-------|
| Scoring environment (inverted-U on league_meta) | 0.25 | Optimal at slight offensive lean (+0.05) |
| Star power (elite/high tier count, scaled per team) | 0.25 | Elite=1.0pt, High=0.5pt; target 0.5/team |
| Star availability (fraction of star games played) | 0.20 | Directly from player_stats.games_missed |
| Playoff fraction (playoff_teams / total_teams) | 0.10 | Sweet spot 30–45%; penalty above 55% |
| Style diversity (std dev of team style_3pt) | 0.10 | Target ±0.06+ for good variety |
| Regular season competitiveness (win% std dev) | 0.05 | Lower spread = better |
| Rivalry playoff matchups | 0.05 | Grudge matchups in bracket = 0.75 |

### Grade scale
```
A+  ≥ 0.93      B+  ≥ 0.80      C+  ≥ 0.65      D+  ≥ 0.50
A   ≥ 0.88      B   ≥ 0.75      C   ≥ 0.60      D   ≥ 0.45
A-  ≥ 0.85      B-  ≥ 0.70      C-  ≥ 0.55      D-  ≥ 0.40
                                                  F   < 0.40
```

## Implementation

### `league.py`
- `League.__init__`: added `self.pillar_history: dict[int, dict]`
- `League.compute_pillar_scores(season)`: ~250-line method computing all four pillars. Returns `{"integrity": {"score", "components", "drivers"}, ...}`. Also snapshots scores to `pillar_history[season_number]`.
- Headless sim loop: added `self.compute_pillar_scores(season)` call after `_evolve_meta()`

### `commissioner.py`
- `_pillar_grade(score)`: converts float to letter grade string
- `_grade_color(grade)`: GREEN/CYAN/GOLD/RED by band
- `Commissioner.__init__`: added `_last_pillar_scores: dict`
- `_run_one_season()`: added `self._last_pillar_scores = league.compute_pillar_scores(season)` after `_evolve_meta()`
- `_show_summary()`: replaced flat signal list with four-pillar display (grade + score + trend + top 3 drivers). `press_enter()` replaced with `[H]` prompt loop.
- `_show_league_health_detail(season)`: full drill-down showing all components with progress bars and weights; raw popularity signals at bottom.
- `_show_reports()`: added "League Health" entry (index 10); Rival League shifted to index 11; Back to index 12.
- `_show_league_health_report(season)`: trend table showing all four pillar grades for every season played.

## Calibration notes (from test runs)
- **Integrity** starts A+ in a clean league; degrades to B range by season 8–10 as grudges/legitimacy erode naturally. Responsive to commissioner rigging.
- **Parity** settles in C range — structural challenge. Never trivially achieved.
- **Drama** baseline is C- (decent playoffs) to D+ (sweepy playoffs). Spikes on actual story events (dynasties, drought-breaking, rivals). Designed to require earning.
- **Entertainment** is B+/A by default in a healthy league. Degrades naturally as star pool ages out in late-game seasons (seasons 8–10 showed drop to B+).

## Backlog items still pending (related)
- #29 Elite player visibility (commissioner dashboard)
- #30 Generational draft prospect event
- #31 Big FA transition as league-wide Entertainment/Drama spike
- #32 Regular season stakes signal (playoff fraction — now included in Entertainment)
- #33 Consecutive finals trips curve (now implemented in Drama pillar)
- #34 Style diversity signal (now implemented in Entertainment pillar)
- #35 Small market success signal (now implemented in Parity pillar)
- #36 Playoff drought normalized (now implemented in Parity pillar)
- Legitimacy upweighting (coefficient needs ~3-4x increase; recovery rate to slow)
