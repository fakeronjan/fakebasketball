# Coach System & UI Polish
*Session: 2026-04-26*

## What was built

### Coach system (`coach.py`, `league.py`, `season.py`)

Five archetypes, each with six base modifiers:

| Archetype | ortg_mod | drtg_mod | chem_scale | star_hap | depth_hap | fa_draw |
|---|---|---|---|---|---|---|
| Culture Coach | +1.0 | −1.0 | 1.40 | +0.03 | +0.05 | 0.03 |
| Star Whisperer | +2.0 | +0.5 | 1.10 | +0.08 | 0.00 | 0.06 |
| Defensive Mastermind | −1.0 | −3.5 | 1.10 | −0.02 | +0.03 | −0.02 |
| Offensive Innovator | +3.0 | +1.0 | 1.00 | +0.04 | +0.01 | 0.06 |
| Motivator | +1.0 | −1.0 | 1.20 | +0.02 | +0.07 | 0.02 |

Scaling: `flex_scale = 1.35 − 0.70 × flexibility`; `rating_scale = 0.50 + rating`; combined `scale = flex_scale × rating_scale`. COY bonus: `+0.02 × min(3, coy_wins)` added to fa_draw.

**Archetype balance** tuned via 5×30 sim. Before: Star Whisperer 26.7% titles, Offensive Innovator 13.3%. After tuning fa_draw values: Offensive 20.1%, Whisperer 25.7% — plausible variance without any archetype being dominant.

**FA draw wiring**: coach `fa_draw × 10.0` added to team score in all three FA motivation branches; loyalty-motivated players now rank destinations by coach fa_draw.

**COY award**:
- Season 1: awarded to coach of highest net-rating team; displayed as "best net rating"
- Season 2+: always fires (threshold removed); awarded on largest net-rating improvement
- COY win increments `coy_wins` (used for fa_draw COY bonus) and clears hot seat

**Coach lifecycle**: hot seat set/cleared by owner happiness; auto-fire when demanding owner + tenure ≥ 2; COY always clears hot seat.

---

### Commissioner surface area (`commissioner.py`)

**Coach Dashboard** (Reports menu, item 5): full table of all teams with archetype, flex, horizon, tenure, COY wins, happiness, ORtg/DRtg modifiers, hot seat indicator. COY history last 10 seasons. Archetype mix summary.

**Always-on coach meeting**: removed silent-skip; every meeting shows coaching landscape (archetype distribution, avg happiness, avg tenure, hot seat count, longest-tenured callout). COY spotlight and hot-seat blocks layered on top when newsworthy.

---

### Season summary split (3 screens)

**Screen A — Standings**: champion callout with runner-up + series score, regular season table (seed, name, W-L, pts diff, net rtg, top player), playoff bracket recap with seeds on every team name.

**Screen B — Awards Night**: MVP / OPOY / DPOY / Finals MVP / COY — each with the exact stat(s) used for selection + career count (e.g. "3×") + streak indicator ("2 in a row"). Stars to Watch (top 8 by tier).

**Screen C — League Health / Fan Engagement** (new standalone screen):
- League-wide summary: popularity bar + trend, total fans, era, avg pts/game
- Per-market table sorted by market size: pop bar, %, fan count, engagement %, commissioner flags
- Commissioner flags: `CHAMP`, `RELOC RISK (N losing)`, `LOSING STREAK (N)`, `HOT SEAT`, `STAR RISK`, `STAR EXP`, `SURGING`, `FADING`, `LOW POP`
- Four-pillar summary (Integrity / Parity / Drama / Entertainment) with top 2 drivers per pillar
- Notable events (relocations, expansions, mergers)
- [H] for full pillar breakdown

---

### Other fixes

- **Playoff seed consistency**: both `_show_round_results` (live per-round) and `_show_standings_screen` (bracket recap) show `(#N)` seeds before team names.
- **Finals MVP bug fix**: in interactive path, `_compute_finals_mvp()` was never called (only called in headless `season.play_playoffs()`). Fixed by detecting Finals completion (`len(next_bracket) == 1`) and setting champion + computing FMVP before the celebration screen.
- **Award metric display**: MVP shows PPG + DRtg + seed; FMVP shows PPG + DRtg; OPOY shows PPG + shooting splits; DPOY shows Def Rtg + possessions defended; COY shows net rating delta (or "best net rating" in season 1).

---

## Commits

```
9a09ef4  Add standalone League Health / Fan Engagement screen (Screen C)
812abc9  Awards: show career win count and consecutive-win streak for all awards
7deb00a  Playoffs: add seed numbers to round results screen + split season summary
16dbc05  Finals MVP: compute and surface at the championship moment
3f36b14  MVP/FMVP: show PPG + DRtg + seed — all three formula inputs
a6caa05  Surface award selection metrics at every display site
e9affa1  COY: always award in season 2+ regardless of delta magnitude
d542797  COY: award in season 1 on best net rating; surface metric at all display sites
650d556  Surface coaches as a player-facing system: dashboard report + always-on meeting
0fe540f  Tune coach archetype balance
77895be  Coach impact simulation suite, fa_draw wiring, COY long-term effects
56fad7b  Redesign coach meeting: signal-only, skip routine seasons
90a121d  Surface coaches in founding teams, desk flags, and owner demand screens
```
