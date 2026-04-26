# Revision Backlog
*Last updated: 2026-04-26*
*Compiled from: game systems assessment, ChatGPT decision-quality teardown, league health analysis, session work*

---

## ✅ Already Shipped

- **Co-tenant founding split UI** — description said 80/20, code does 50/50. Fixed.
- **#8 Schedule shrinkage at expansion** — commissioner prompt with before/after table; red warning on shrinkage.
- **#9 Finals MVP** — rewritten to use actual Finals game logs; 60/40 offense/defense formula.
- **#11 Tier boundary overlap** — elite ortg floor raised 9.0 → 10.0.
- **#12 Negative overall fix** — Low-tier players: `p_drtg = min(p_drtg, p_ortg)` floors peak_overall at 0.
- **#15 Showcase city tags** — relocation risk and owner threat levels shown at decision time.
- **#16 Owner denial patience signal** — deny option shows probabilistic breaking point risk (color-coded).
- **#17 FA rigging legitimacy warning** — low legitimacy (<50%) shows red consequence note at FA screen.
- **MVP/OPOY/DPOY overhaul** — all three awards use 60/40 two-way formula with empirical def_rtg from game logs.
- **Ownership transition redesign** — probabilistic breaking point; sell-vs-breakaway choice; $20M buyout roll.
- **Work stoppage hangover extended** — 3 seasons → 5 seasons; steeper early curve.
- **Four-pillar league health framework** — Integrity / Parity / Drama / Entertainment; letter grades; [H] drill-down.
- **Owner meeting noise reduction** — raised playoff-miss happiness base; drought curve now explicit.
- **Elite player / star system** — Players' Meeting filtered to elite/high only; Stars to Watch; generational draft splash; marquee FA upgrade.
- **#29 Elite player visibility** — ✅ Shipped as part of star system above.
- **Coach system** — Five archetypes (Chemistry, Star Whisperer, Defensive, Offensive, Motivator); modifiers for ortg/drtg/chemistry/star happiness/depth happiness/FA draw; coach lifecycle (hot seat, COY); coach-player fit and coach-owner fit scoring; FA draw wired into all three motivation branches; balanced archetype distribution at league init. Archetype balance tuned via simulation (5×30). *(2026-04-26)*
- **Coach surface area** — Coach Dashboard report; always-on coach landscape in commissioner meeting; COY award always fires (season 1: best net rating; season 2+: best net rating delta); season-1 baseline fix; multi-COY career callout. *(2026-04-26)*
- **Award metric display** — MVP, OPOY, DPOY, FMVP, COY all surface the exact stat(s) used to select them. *(2026-04-26)*
- **Finals MVP in interactive path** — bug fix; now computed and shown at championship moment before celebration screen. *(2026-04-26)*
- **Season summary split** — three screens: (A) Standings/champion/bracket recap with seeds, (B) Awards Night, (C) League Health/Fan Engagement. *(2026-04-26)*
- **Playoff seed consistency** — both live round results and bracket recap show `(#N)` seeds. *(2026-04-26)*
- **Award career count + streak** — every award row shows total career wins and "N in a row" when applicable. *(2026-04-26)*
- **League Health / Fan Engagement screen** — per-market table (market size, pop bar, engagement, fans) with commissioner flags: CHAMP, RELOC RISK, LOSING STREAK, HOT SEAT, STAR RISK, STAR EXP, SURGING, FADING, LOW POP. Four-pillar summary with top 2 drivers. Notable events. *(2026-04-26)*

---

## 🔧 Calibration Fixes
*Numerical values that need tuning, no design changes required.*

| # | Issue | Where | Fix |
|---|---|---|---|
| 1 | Money owner happiness hits ceiling at $8.3M profit — teams making $10M and $60M look identical | `league.py` | Scale factor `0.06` → `~0.006` |
| 2 | Local hero owners hard to upset — average team (pop 0.5, eng 0.5) already reads as 0.85 happiness | `league.py` | Adjust multiplier or base |
| 3 | STEADY owner patience = 8 seasons before DEMAND — too long for engaging gameplay | `owner.py` | Reduce to 5–6 |
| 4 | `league_pop_engagement_pull: 0.15` too high — fan composite drowns all narrative signals | `config.py` | Reduce to `0.06–0.08` |
| 5 | Finals buzz neutral point fixed at 0.30 engagement — almost always negative in early seasons regardless of matchup quality | `league.py` | Make relative to current league avg engagement |
| 6 | `league_pop_drama_max: 0.08` outsizes all other signals | `config.py` | Reduce to `~0.03` |
| 7 | FT zone is secretly the most efficient zone (1.52 pts/poss vs 1.14 paint) — hidden overperformers | `game.py` | Monitor for exploits |

---

## 🐛 Code Bugs
*Behavior that's wrong relative to clear intent.*

| # | Issue | Where | Fix |
|---|---|---|---|
| 10 | DPOY attribution bias — same-position defender always assigned first, deterministic | `game.py` | Add randomization or coach scheme logic |

---

## 🎮 Decision Quality Improvements
*Mechanics that work but present weak or one-sided choices.*

| # | Issue | Fix |
|---|---|---|
| 13 | **Invest in talent** is near no-brainer (UI literally says "Low risk / High reward") | Add: talent investment increases probability of player-friendly CBA demand next negotiation by ~10% |
| 14 | **Revenue sharing** has no downside — it's charity, not governance | Money-motivated owners in profitable markets take a small happiness penalty when heavy sharing is set |
| 18 | Showcase events have no explicit link to relocation risk | Surface connection: flag cities whose owner is watching/demanding in showcase UI |
| 19 | Indirect FA influence is never framed as a choice | One callout in offseason FA summary: "Market-motivated players are avoiding small markets this year" |
| 20 | Legitimacy's downstream effects aren't shown at moment of costly decisions | Add one-line reminder at rule change / FA rigging screens when legitimacy is low |

---

## 🧱 Thin Systems
*Mechanics that exist but feel underdeveloped.*

| # | Issue | Notes |
|---|---|---|
| 21 | **Durability** is effectively just "injury probability modifier" | High fatigue players could take a small performance penalty even without injury |
| 22 | **Happiness multiplier** is a cliff, not a slope — no reward above 0.50 | Small performance bonus above 0.75 (Content) — makes keeping stars happy feel like active upside |
| 23 | **Legacy matchup** and **Rivalries** signals don't activate until seasons 3–4 | Add note in early seasons: *"Rivalries and legacy matchups will develop as the league matures"* |

---

## 🆕 New Features (Backlog)
*Discussed and designed but not yet built.*

| # | Feature | Notes |
|---|---|---|
| 25 | **Career stat tracking / Hall of Fame** | Cumulative player stats across seasons; HOF induction as a late-game prestige moment |
| 26 | **In-game box scores** | Per-game stat display during playoff interactive mode |
| 27 | **Mobile number pad** | Row of 1–9 + Enter + Backspace buttons overlaid on terminal for phone users |
| 30 | **Generational draft prospect event** | Flag elite-ceiling prospects the season *before* the draft; pre-draft anticipation Entertainment boost; LeBron 2003 / Wemby 2023 model |
| 31 | **Big FA transition as league-wide event** | Star FA events should register as Entertainment + Drama spike for the whole league, not just a commissioner decision |
| 32 | **Regular season stakes signal** | `playoff_fraction = playoff_teams / total_teams` as moderate Entertainment signal; sweet spot ~33–40% |
| 33 | **Consecutive finals trips dynasty curve** | Replace consecutive championships with consecutive finals appearances as Drama dynasty signal; bell curve peak at 2 trips |
| 34 | **Style diversity signal** | Variance in `style_3pt` across teams as moderate Entertainment signal; homogeneous league = bad |
| 35 | **Small market success signal (Parity)** | Fraction of playoff/champion teams in bottom-quartile `effective_metro` |
| 36 | **Playoff drought normalized (Parity)** | `longest_playoff_drought / num_teams`; long championship drought as Drama narrative payoff |
| 37 | **Fan dialogue** | Discussed but deferred; commissioner receives fan sentiment signals (letters, social pulse, market-specific reactions) as flavor and soft pressure |
| 38 | **Coach hire/fire cycle** | Interactive coaching market — when a coach is fired or retires, commissioner sees available pool and can influence (or let teams decide); coach contracts, salary, and poaching |
| 39 | **Award history in Reports menu** | Dedicated awards report: all-time leaders by award, consecutive win records, double/triple award seasons |

---

## Priority picks
*Highest-leverage items that are also relatively low-effort.*

1. **#1** — Money owner happiness formula (one-line rescale)
2. **#4** — Engagement pull config value (one-line change)
3. **#22** — Happiness as a slope not a cliff (small performance bonus above 0.75)
4. **#30** — Generational prospect event (pre-draft hype; strong Entertainment signal)
5. **#31** — Star FA as league-wide event (existing event upgraded with broadcast framing)
6. **#25** — Career stat tracking / Hall of Fame (late-game prestige; needed for multi-decade saves)
