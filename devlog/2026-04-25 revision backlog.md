# Revision Backlog
*Date: 2026-04-25*
*Compiled from: game systems assessment, ChatGPT decision-quality teardown, league health analysis*

---

## ✅ Already Shipped
- **Co-tenant founding split UI** — description said 80/20, code does 50/50. Fixed and pushed.
- **#8 Schedule shrinkage at expansion** — replaced auto-adjust with commissioner prompt showing before/after table; red warning on shrinkage.
- **#9 Finals MVP** — rewrote to use actual Finals game logs; 60/40 offense/defense formula matching regular-season MVP logic.
- **#11 Tier boundary overlap** — elite ortg floor raised 9.0 → 10.0, closing overlap with High tier ceiling.
- **#12 Negative overall fix** — Low-tier players: `p_drtg = min(p_drtg, p_ortg)` floors peak_overall at 0.
- **#15 Showcase city tags** — relocation risk and owner threat levels shown at decision time.
- **#16 Owner denial patience signal** — deny option shows probabilistic breaking point risk (color-coded).
- **#17 FA rigging legitimacy warning** — low legitimacy (<50%) shows red consequence note at FA screen.
- **MVP/OPOY/DPOY overhaul** — all three awards use 60/40 two-way formula with empirical def_rtg from game logs; MVP restricted to playoff teams; OPOY/DPOY allowed to overlap with MVP.
- **Ownership transition redesign** — probabilistic breaking point (replaces hard 3-denial cap); sell-vs-breakaway choice; $20M buyout roll; reframed as "transition" not "crisis."
- **Work stoppage hangover extended** — 3 seasons → 5 seasons; steeper early curve (-7%/-4.5%/-2.5%/-1%/-0.5%); 5 annotation phases.
- **Four-pillar league health framework** — Integrity / Parity / Drama / Entertainment composite scores computed each season; pillar_history stored on League; letter-grade display (A+ through F) with top 3 drivers shown in season summary; [H] full drill-down screen; League Health report in Reports menu with season-by-season trend table.
- **Owner meeting noise reduction** — removed contract-cycling grievance (multi-expiry penalty); raised playoff-miss happiness base from 0.42 → 0.52; drought curve now explicit (tolerable for first miss, LEAN threshold around 4 consecutive misses). Result: ~20% restless after 5 seasons vs ~50% before.
- **Elite player / star system** — three-part system: (1) Players' Meeting now shows only elite/high-tier players (peak_overall ≥ 12) with a summary line for the rest ("23 other rostered players — 2 unhappy"); (2) Season summary adds "Stars to Watch" block showing top 8 stars by tier with mood/contract/declining flags; (3) Draft screen fires a dedicated "Generational Draft Class" splash when an elite-ceiling prospect is on the board; (4) Star FA event upgrades to "MARQUEE FREE AGENCY" header for elite players with "⭐ THE LEAGUE IS WATCHING" banner.
- **#29 Elite player visibility** — ✅ Shipped as part of star system above.

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
| 6 | `league_pop_drama_max: 0.08` outsizes all other signals — could theoretically outweigh dynasty + entertainment + Finals buzz combined | `config.py` | Reduce to `~0.03` |
| 7 | FT zone is secretly the most efficient zone (1.52 pts/poss vs 1.14 paint) — Bigs with FT preference are hidden overperformers | `game.py` | Awareness issue; monitor for exploits |
| 8 | Schedule shrinks with league growth — 16-team league plays only 30 games (NBA preseason length) | `season.py` | Add floor on `games_per_pair` |

---

## 🐛 Code Bugs
*Behavior that's wrong relative to clear intent.*

| # | Issue | Where | Fix |
|---|---|---|---|
| 9 | Finals MVP uses `max(overall)` from champion's current roster, not playoff game stats | `season.py` | Use playoff game logs to find leading scorer |
| 10 | DPOY attribution bias — same-position defender always assigned first, so defending bad shooters at your position looks great | `game.py` | Add randomization or coach scheme logic |
| 11 | Tier boundary overlap — top of "High" tier and bottom of "Elite" tier are numerically identical | `player.py` | Widen the gap or adjust thresholds |
| 12 | Low-tier players can have negative `overall` (−6 at worst) and actively hurt the team | `player.py` | Decide if intentional; if not, floor at 0 |

---

## 🎮 Decision Quality Improvements
*Mechanics that work but present weak or one-sided choices.*

| # | Issue | Fix |
|---|---|---|
| 13 | **Invest in talent** is near no-brainer (UI literally says "Low risk / High reward") | Add: talent investment increases probability of player-friendly CBA demand next negotiation by ~10% |
| 14 | **Revenue sharing** has no downside — it's charity, not governance | Money-motivated owners in profitable markets take a small happiness penalty when heavy sharing is set |
| 15 | **Showcase event** UI frames it as "fix the weakest market" — undersells competing reasons | Add city tags at decision time: `low engagement`, `relocation risk`, `grudge`, `Finals buzz`, `co-tenant rivalry` |
| 16 | **Owner demand denials** lack visible consequence forecasting | Add patience signal on deny option: *"Owner patience wearing thin — further denials risk ownership transition"* |
| 17 | **Star FA rigging**: legitimacy loss feels abstract until it cascades | Surface the consequence: show a note when legitimacy drops below 50% that rival vulnerability and fan trust are at risk |

---

## 🔌 Missing Connections
*Existing systems that should be wired together but aren't.*

| # | Gap | How to close it |
|---|---|---|
| 18 | Showcase events have no explicit link to relocation risk — ignoring a struggling market repeatedly should make its owner more likely to demand relocation | Surface the connection in showcase UI: flag cities whose owner is watching/demanding |
| 19 | Indirect FA influence (CBA terms, league popularity, era affecting player value) is never framed as a choice | Consider one callout in the offseason FA summary: "Market-motivated players are avoiding small markets this year" — makes the connection visible |
| 20 | Legitimacy's downstream effects (popularity penalty, rival vulnerability) aren't shown at the moment of decisions that cost legitimacy | Add a one-line reminder at rule change / FA rigging screens when legitimacy is low |

---

## 🧱 Thin Systems
*Mechanics that exist but feel underdeveloped as performance dimensions.*

| # | Issue | Notes |
|---|---|---|
| 21 | **Durability** is effectively just "injury probability modifier" — no effect on performance for healthy players | Consider: high fatigue players take a small performance penalty even without injury, making durability meaningful outside injury rolls |
| 22 | **Happiness multiplier** is a cliff, not a slope — no reward for players above 0.50 happiness | Consider: small performance bonus above 0.75 (Content) — makes keeping stars happy feel like active upside |
| 23 | **Legacy matchup** and **Rivalries** signals in league health don't activate until seasons 3–4 — player may not know they exist | Add a note in early seasons: *"Rivalries and legacy matchups will develop as the league matures"* |

---

## 🆕 New Features (Backlog)
*Discussed and designed but not yet built.*

| # | Feature | Notes |
|---|---|---|
| 24 | **Coaching mechanic** | Full design in devlog: coach style (pace-and-space / defensive / balanced / player-development) modifies zone distributions and defender assignment; coach rating affects bench quality and chemistry; hire/fire cycle with owner happiness connection |
| 25 | **Career stat tracking / Hall of Fame** | Track cumulative player stats across seasons; HOF induction as a late-game prestige moment |
| 26 | **In-game box scores** | Per-game stat display during playoff interactive mode |
| 27 | **Mobile number pad** | Row of 1–9 + Enter + Backspace buttons overlaid on terminal for phone users |
| 28 | ~~**Four-pillar league health framework**~~ | ✅ **Shipped 2026-04-25.** Integrity/Parity/Drama/Entertainment composite scores; letter grades A+–F; top-3 drivers in summary; [H] drill-down; League Health trend report. |
| 29 | ~~**Elite player visibility**~~ | ✅ **Shipped 2026-04-25.** Stars to Watch in summary; player meeting filtered to elite/high only; generational draft splash; marquee FA upgrade. |
| 30 | **Generational draft prospect event** | When a draft class contains a player with projected peak_overall ≥ 16+, flag them the season *before* as a "generational prospect." Creates pre-draft anticipation Entertainment boost; lottery drama becomes the storyline. (LeBron 2003 / Wemby 2023 model.) |
| 31 | **Big FA transition as league-wide event** | Star FA events (peak_overall > `star_fa_threshold`) should register as a significant Entertainment + Drama spike for the whole league, not just a commissioner decision. "LeBron is on the market" is appointment television regardless of destination. |
| 32 | **Regular season stakes signal** | `playoff_fraction = playoff_teams / total_teams` as a moderate Entertainment signal. Sweet spot ~33–40%. Above 50% (current NBA criticism) regular season loses stakes. Creates tension with Parity — more playoff teams = more inclusive but less meaningful regular season. |
| 33 | **Consecutive finals trips dynasty curve** | Replace consecutive championships with consecutive finals appearances as the Drama dynasty signal. Bell curve: peak at 2 trips (+0.04), flat at 3 (0.00), negative at 4 (−0.05), significantly negative at 5+ (−0.10). Captures Bills-style fatigue from repeated appearances whether winning or losing. |
| 34 | **Style diversity signal** | Variance in `style_3pt` across teams as a moderate Entertainment signal. Homogeneous league (everyone jacks threes) = bad; mixed identities (run-and-gun vs. grind vs. three-point) = good entertainment. |
| 35 | **Small market success signal (Parity)** | Fraction of playoff/champion teams in bottom-quartile `effective_metro`. Higher = better parity. Small-market championship = significant positive spike. |
| 36 | **Playoff drought normalized (Parity)** | `longest_playoff_drought / num_teams` as a moderate Parity signal. Identifies structurally excluded franchises. Long championship drought moved to Drama (narrative payoff when broken). |

---

## Priority picks
*Highest-leverage items that are also low-effort to implement.*

1. **#1** — Money owner happiness formula (one-line rescale)
2. **#4** — Engagement pull config value (one-line change)
3. **#9** — Finals MVP using playoff stats instead of roster overall
4. **#13** — Talent investment → increased CBA pressure next round
5. **#15** — Showcase event city tags
