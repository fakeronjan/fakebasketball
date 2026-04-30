# Fake Basketball Commissioner — Project History
*A timeline of the build, from first simulation to v1.0 release*

---

## Background

The project started as a pure simulation engine — no UI, no interactivity. A Python script that could simulate a fictional basketball league through seasons, handle expansion, track team ratings, and produce results. The goal was to see how much emergent narrative could come out of a well-calibrated simulation before any human decision-making was layered on top.

The commissioner game came later, and changed everything.

---

## Sim Engine Era (pre-April 12)

Before the first GitHub commit, the simulation engine went through five major versions. Each was a standalone Python project — run from the terminal, outputs to the console, no interactivity.

**v1.0** — The foundation. Teams had a single `strength` float (0–100). Seasons were simulated round-robin, playoffs were a bracket. Relocation logic existed from day one — teams that consistently finished bottom-2 could move markets. The franchise pool (cities, nicknames, metro sizes) was built out as a proper database from the start, which turned out to be load-bearing for everything that came after.

**v2.0** — Teams gained ORtg/DRtg/Pace as separate dimensions instead of a single strength float. Expansion and rival league mechanics were introduced. The league could grow, contract, and face external pressure. Popularity became a tracked stat that diverged from market size based on performance.

**v3.0** — Era dynamics. `league_meta` was introduced as a float tracking whether the league was in an offensive or defensive era. The meta drifted each season, was influenced by the champion's style, could be shocked by rule changes, and affected zone efficiency across all teams. Championship dynasty decay was added — consecutive titles regressed a team's ratings, simulating complacency and opponent film study.

**v4.0** — The player model. Three named players per team (Star, Co-Star, Starter) with weighted contributions (50/30/20). Career arcs with rising and declining phases, peak seasons, start multipliers, and an accelerating `t^1.3` decline curve. Chemistry system — positional diversity and zone diversity bonuses. The possession engine went from team-level probability to player-level attribution.

**v5.0** — Published April 12. The version that became the foundation for the commissioner game. ORtg and DRtg contributions per player were wired into a possession-level simulation. Each possession had a shooter, a zone, a make probability computed from player quality, and outcomes tracked as scored points. The box score didn't exist yet — just scores and winner — but the architecture for full player-level attribution was in place. 110 lines of `game.py`. By v1.0 commissioner release, it would grow to 739.

---

## April 12 — First Commit

> *"Initial publish: RBL simulation v5.0"*

The sim engine is published to GitHub. It can run 20-season simulations, produce league histories, handle expansion and relocation, model era shifts, and print readable terminal output. There is no interactivity. You run it, you watch it.

---

## April 15 — First Playable Prototype

> *"First playable prototype of commissioner game"*

The commissioner game ships for the first time. At 2,882 lines, it's roughly 1/3 the size it'll reach at v1.0. The core loop exists: seasons run, standings are shown, playoffs happen, an offseason screen appears. You can name your league. There's a start menu.

What's missing: almost everything that makes it a *game*. No owner system. No draft. No free agency. No coaches. No rivals. No player model. The commissioner is a spectator who presses Enter.

But the terminal infrastructure is right — ANSI colors, header/divider formatting, the `press_enter` / `choose` / `prompt` helper pattern that will carry through to v1.0 unchanged.

---

## April 21 — The Game Gets Real

> *"v0.2: rival leagues, player model, dynasty decay, scoring calibration"*

The three rival league types land together:
- **Type A** — external investors form a competing league when yours gets popular enough
- **Type B** — disgruntled owners defect and take their franchises with them
- **Type C** — players walk out over CBA disputes

Each has different triggers, different mechanics, and different resolution options. Type B is the most severe (you lose real franchises). Type C is the most creative (the threat is internal). The commissioner now has adversaries.

The player model lands in the commissioner game. Three slots per team. Contract years. Happiness. Draft. Free agency. Players develop, age, and retire. The owner system comes with it — each team owner has a motivation (Winning / Market / Loyalty), a happiness level, and a threat level that escalates from Quiet → Lean → Demand when they're unhappy long enough.

---

## April 23 — Web Port

> *"Add Pyodide web port (index.html + worker.js + COI service worker)"*

The game is ported to run in the browser via Pyodide (Python compiled to WebAssembly). The terminal experience is faithfully reproduced in a browser textarea. CORS isolation headers, a service worker, a web worker thread — all the infrastructure to make Python run client-side with no server. This is non-trivial and it works.

---

## April 24 — Stability and the First Deep Assessment

Several fixes land: the `_QuitSignal` exception system replaces `SystemExit` (which Pyodide couldn't handle), reports become accessible from any screen mid-season via `[r]`, and the UI gets its persistent `[q] save & quit  ·  [r] reports` hint on every header.

More importantly, a full **game systems assessment** is written. Every subsystem is evaluated honestly: what's working, what's broken, what's a known limitation. Key findings:

- *The possession-level simulation is the strongest part of the stack numerically.* The calibration math holds.
- *Fatigue only accumulates in playoffs. Regular season games don't degrade players.* (Filed as a future fix — becomes the Form + Fatigue system on April 29.)
- *The Finals MVP uses `p.overall`, not playoff stats.* (Fixed in April 26 awards overhaul.)
- *DPOY attribution bias from positional defender matching.* (Filed. Partially addressed by quality-weighted defensive stat attribution on April 29.)
- *Happiness multiplier is a cliff, not a slope. No upside for keeping a player happy above the threshold.* (Design decision: accepted as-is for v1.0.)
- *A coaching layer is missing.* The entire coach system architecture is sketched out in this document — archetypes, lifecycle, COY, commissioner meeting, wiring into zone selection and bench quality.

The assessment is a turning point. The sessions after it are execution against a known plan.

---

## April 25 — The Big Systems Day

The most architecturally significant single day of the project. Four major systems land.

**Star / Elite player system.** Players above a quality threshold are flagged as stars and surfaced prominently throughout the UI. The star FA event fires when a star enters free agency — a special commissioner moment with outsized consequences.

**Four-pillar league health framework.** The flat "league health" metric is replaced with four scored dimensions:
- *Integrity* — governance, legitimacy, owner stability, star happiness
- *Parity* — rating spread, playoff rotation breadth, championship concentration, market equity
- *Drama* — dynasty arcs, Game 7 rate, drought-breaking moments, Finals interest
- *Entertainment* — product quality, star power, era engagement

Each pillar is scored A through F, displayed with component breakdowns. The commissioner now has a genuine dashboard, not a single number.

**Owner system overhaul.** The probabilistic breaking-point system replaces the deterministic one. When an owner's patience runs out, they face a choice: sell the team or break away to a rival. The sell path has a cost and an acceptance roll. The breakaway path feeds into Type B rival league formation. Owner motivation (Winning / Market / Loyalty) produces genuinely different happiness curves — a market owner in a profitable big-market city almost never demands anything; a winning owner who misses the playoffs for three years starts escalating fast.

**Coach system — full design and first implementation.** Coaches get archetypes (Star Whisperer, Offensive Innovator, Defensive Mastermind, Chemistry Coach, Motivator), contracts, career lengths, a COY award, and a commissioner meeting. The archetypes modify role weights in `_pick_shooter`, bench quality, chemistry scaling, and FA draw probability. The hot seat system tracks coach performance and creates narrative consequences for sustained losing.

---

## April 26 — The UI and Awards Marathon

The longest commit day of the project — 25+ commits. Everything that makes the game feel finished as an experience gets built.

**Awards overhaul.** MVP, OPOY, DPOY, ROY, Finals MVP, MIP, and COY all get proper formulas (60/40 PPG/defensive-value two-way composite for MVP; pure PPG for OPOY; pure def_rtg for DPOY), eligibility rules, and award night presentation. The Finals MVP is computed from actual playoff game logs rather than the player's season attribute. Coach of the Year tracks net-rating improvement across seasons.

**Playoff preview redesign.** Win probability moves from a ratings-only estimate to a 4-signal model: actual regular-season win% (60%), pre-season talent rating (40%), weighted fatigue drag, and key-player injury penalties. The preview shows each team's full player and coach block with stats, missed games, and fatigue.

**Offseason recap screen.** A narrative summary before each new season — retirements, notable FA signings, award flashbacks, the pulse of the league.

**Hall of Fame.** Players and coaches are inducted based on career totals and historical significance. The induction ceremony has a proper presentation screen. Career stat tracking is backfilled into the player model.

**Revenue sharing redesign.** Three tiers of revenue sharing (voluntary, moderate, heavy), with an owner resentment mechanic — top earners resist repeated sharing asks. The commissioner's treasury takes a cut of gross revenue and can deploy funds on interventions.

**Generational draft system.** One season ahead of an elite prospect entering the draft, the league signals their presence. Tanking teams get a popularity penalty. The fanbase pulse screen tracks fan sentiment around the draft class.

**Constituency framing.** Commissioner decisions — rule changes, talent investment, revenue sharing — now frame the choice in terms of which stakeholder group benefits. Owners, players, and fans have visible interests, and the commissioner's choices affect each differently.

**Save compatibility system.** Version stamping and `_post_load_fixup` — a function that patches missing attributes on loaded objects when schema changes are additive. This allows old saves to load cleanly after new fields are added without bumping the save version.

---

## April 27 — The Engine Gets Rebuilt

Two foundational problems are solved.

**Problem 1: Shot selection was static and backwards.**
The original `_pick_shooter` used hardcoded slot shares from Config (`star: 21%, costar: 22%`). Stars got fewer shots than co-stars. Usage was completely static regardless of roster shape. There was no heliocentric offense, no coach influence on shot distribution.

Three formulas were tried before landing:
- *Exponential talent factor* — rejected. A +18 star got 9.5× the weight of a neutral player. Produced 91 PPG for star-heavy rosters.
- *Linear scale 0.04* — rejected. League-wide scoring leaders averaged 37.7 PPG.
- *Linear scale 0.02* — rejected. Still high at 34.1 PPG.
- ***`safe_linear_B` formula*** — shipped. `max(0.75, min(1.35, 1.0 + 0.025 × ortg_contrib))`. Stars get more shots, bench stays a real share, scores land in the right range. Scoring leaders average 27–30 PPG across full-league simulations.

**Problem 2: Coach archetypes were display-only.**
`ortg_mod` and `drtg_mod` appeared in the team's displayed ratings but were invisible to `_compute_make_pct`, which drives actual possession outcomes. Coaches affected the aesthetics of team ratings without affecting games.

Fix: `_compute_make_pct` gets `coach_ortg_mod` and `coach_drtg_mod` parameters. `_sim_possession` extracts these from `coach.compute_modifiers()` at possession time and adds them to the shooter's effective `ortg_contrib` and the defender's effective `drtg_contrib`. Coach archetypes now affect every possession.

The **commissioner's inbox** also lands — an event-driven fan dialogue system that surfaces a rotating set of fan messages each offseason based on actual league conditions (dynasty concerns, parity complaints, star player drama, rival league anxiety). The league feels inhabited.

---

## April 28 — The Full Box Score

The game's biggest single feature gap is closed: `REB / STL / BLK / TOV` are added to the possession-level engine.

Before this: the game tracked points and wins. The player stat line was PPG and DRtg. After: every possession has full turnover attribution (ball handler weighted by position), steal attribution, block attribution (rim protectors), and rebound attribution (bigs weighted 4:2:1 vs guards). The stat leaders section becomes meaningful.

The implementation detail that matters: bench players compete for stat credit using a quality-weighted model mirroring `_pick_shooter`. A bench entry with weight 12.0 competes against named players for rebounding credit. Named players' weights are scaled by `_def_quality(player)` — a function of `drtg_contrib`, so elite defenders are proportionally more likely to get credit for steals and blocks. The result: realistic per-game lines without any named player absorbing 100% of team stats.

Coach career arcs and formal retirement also land — coaches have career lengths, age each offseason, and retire when their arc ends. The coaching pool manages depth across the league.

---

## April 29 — Form, Fatigue, and v1.0

The final session. Four streams of work close the game.

**Form + Fatigue system.** The April 24 assessment called durability "injury-only, not a performance dimension" and flagged that "regular season games don't degrade players." Both are fixed.

- `form: float = 1.0` — a per-player momentum tracker (range 0.80–1.20). After each regular-season game, form shifts based on win/loss and PPG-vs-season-average. Random regression-to-mean fires with configurable probability. Coach archetypes modify regression: Star Whisperer slows peak-form decay for stars; Motivator accelerates recovery for slumping players. Team average form translates to a prob_bonus applied to `play_game` via `home_advantage`/`away_advantage`, creating genuine game-to-game momentum.
- `effective_durability` — derived property replacing raw `durability` in injury calculations. Formula: `max(0.10, durability − age_decay − mileage_penalty)`. Veterans with 800+ career games and players over 30 become meaningfully more fragile than their base stat suggests.
- Regular-season fatigue accumulation — proportional to PPG usage, scaled by owner competence. Better GMs manage player load.

**Deep engine validation.** A 5-axis analysis is run against the live engine: coach archetype win rates (5×5 matrix, 300 games per pair), team construction philosophies, quality tier discrimination (ELITE vs LOW: 86% win rate at 2,000 games), position impact, and age/career stage. Key finding: the engine discriminates correctly between quality tiers at full season sample sizes. Score variance (~10–11 pts stdev) correctly produces realistic game-to-game outcomes — a +10 net-rating team wins ~57% of games, matching real NBA analytics.

**UI consistency pass.** Battery emoji spacing normalized across all screens. MIP award stat replaced "composite score" with a full stat line. Top scorer in standings shows full name. Stat leaders reduced to top 3 with team names. Playoff preview renamed to "PLAYOFF-BOUND READINESS" with Form column added.

**v1.0 release.** The welcome screen is rebuilt: possession-level simulation is called out explicitly, all new systems (form, fatigue, coach archetypes, effective durability) are listed. `v1.0` appears under the logo. The welcome now shows for returning players loading a save — the game announces itself on every boot.

---

## The Numbers

| Metric | Value |
|--------|-------|
| First commit | April 12, 2026 |
| v1.0 release | April 29, 2026 |
| Build duration | 17 days |
| Total commits | 80+ |
| commissioner.py at first prototype | 2,882 lines |
| commissioner.py at v1.0 | 9,893 lines |
| game.py at sim engine publish | 110 lines |
| game.py at v1.0 | 739 lines |
| Sim engine versions before commissioner | 5 (v1.0–v5.0) |
| Commissioner major versions | 2 (v0.1 prototype → v0.2 → v1.0) |
| Franchise pool size | 63 cities |

---

## What Got Built

A possession-level basketball simulation where every game unfolds shot by shot, player by player. Three named players per team — Star, Co-Star, Starter — with career arcs that rise and fall over 8–20 seasons. Coaches with archetypes that shift usage patterns and modify possession outcomes. Owners with motivations who escalate demands and, if ignored long enough, try to break away.

On top of that simulation: rival leagues that emerge organically from your success and can collapse, merge, or outlast you. Expansion waves and franchise relocations. An era system where the league drifts toward offensive or defensive basketball, shaped by rule changes and the champion's style. A Hall of Fame that accumulates real history. Revenue flows, treasury management, and legitimacy as a resource you spend and rebuild.

And underneath all of it: a game-to-game momentum system where players carry their form from one night to the next, where veterans' bodies accumulate the weight of a career, and where the right coach can keep a star from slumping or pull a struggling player back to baseline.

The commissioner doesn't control outcomes. They build the conditions that produce them.

---

*Built with Claude Code, April 2026.*
