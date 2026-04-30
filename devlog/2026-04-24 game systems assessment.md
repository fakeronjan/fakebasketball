# Game Systems Assessment
*Date: 2026-04-24*

## Game Engine

The possession-level simulation is the strongest part of the stack numerically. The calibration check — `0.10×FT(0.76×2) + 0.45×paint(0.57×2) + 0.20×mid(0.42×2) + 0.25×3pt(0.36×3) = 1.103 pts/poss` — is exactly right for a 110 pts/100 poss baseline. That math is load-bearing and it holds.

A few things to flag:

**Free throws are the most efficient zone by a significant margin.** FT zone gives `0.76 × 2 = 1.52 expected points per possession`. Paint gives `0.57 × 2 = 1.14`. FTs win by ~33%. In real basketball this is true, but it means any player or team biased toward the FT zone is systematically over-performing their apparent rating. Players whose `preferred_zone = ZONE_FT` (Bigs with 25% weight) are secretly the most efficient shooters in the game. This probably doesn't create visible bugs, but it's a hidden imbalance worth being aware of.

**Bench quality range is asymmetric.** The formula returns roughly `[-0.040, +0.020]`. The floor is twice as far from zero as the ceiling. Elite bench depth gives you +0.020, a gutted bench costs you -0.040. That asymmetry is actually realistic — bad benches lose games more than great benches win them — but it means the primary driver of bench outcomes is avoiding disaster, not achieving greatness.

**Defender assignment is positional and always deterministic.** `_pick_defender` takes the first same-position defender it finds, always. There's no randomization or scheme-level logic. The star defender always covers the star offensive player at their position. This matters for DPOY: whoever plays the same position as the opponent's best scorer gets credit for defending them. A coach mechanic could fix this elegantly.

**Seed bonus in playoffs.** The `playoff_seed_pscore_bonus` is an additive probability on every possession for the higher seed, on top of home court. These stack — so the #1 seed playing at home gets `home_base + pop_scale × popularity + seed_bonus` on every possession. If these parameters are large, top seeds can be dominant to the point of making upsets rare. Worth watching if the simulation tends to produce predictable champions.

---

## Player Model

The career arc math is genuinely good. The `t^1.3` accelerating decline is better than linear — it produces the right shape where a player holds near-peak form for a few seasons then falls off faster. Floor of 0.45 prevents complete irrelevance.

**Tier boundary issue.** High tier tops out at `ortg=9.0, drtg=-7.0`. Elite tier bottoms at `ortg=9.0, drtg=-7.0`. They share a boundary. A player at the top of High and the bottom of Elite are statistically identical. Tier is a generation label, not a floor — which is fine — but it means the tier display in the commissioner UI is misleading at the boundaries. A "High" ceiling player and an "Elite" ceiling player can be the same player. The `ceiling_noise: gauss(0, 2.0)` makes this worse by scrambling the perceived tier further.

**Low-tier players can actively hurt the team.** `peak_ortg` ranges from -2.0 to 3.0 and `peak_drtg` from -2.0 to 4.0. A low-tier player with `peak_ortg=-2, peak_drtg=+4` has `peak_overall = -2 - 4 = -6`. They score below league average AND give up more than the defense baseline. These players exist in the game and get rostered. Whether that's intentional flavor (desperate teams sign bad players) or an accident depends on how the commissioner mode presents them. If they show up with an "overall" score in the reports, the negative number may be confusing.

**Happiness multiplier is a cliff, not a slope.** Above 0.50 → 1.0 performance. Between 0.25-0.50 → 0.93. Below 0.25 → 0.85. Two threshold jumps. Numerically fine, but it means a player at happiness 0.50 and happiness 0.99 perform identically — no reward for keeping a player happy above the threshold. There's no upside. This is a design choice but worth being deliberate about.

**Fatigue only accumulates in playoffs.** Regular season games don't degrade players regardless of how many games they play. Durability only matters for the pre-season injury roll. A player with `durability=0.50` and `durability=1.00` have identical performance unless one gets injured. The durability stat feels thin as a result — it's really just "injury probability modifier" rather than a meaningful performance dimension.

---

## Season

**Schedule length shrinks as the league grows.** `_games_per_pair` targets ~40 total games, calculated as `target / (n_teams - 1)` rounded to an even number. With 8 teams, pairs play 6 games (42 total). With 16 teams, pairs play 2 games (30 total). A 30-game regular season is NBA preseason length. At 20+ teams you're still at 2 games per pair (38 games), but it feels short. This is probably fine since the game isn't tracking game-by-game but it might affect award stat distributions (fewer games = more PPG variance for MVP race).

**Finals MVP doesn't use playoff stats.** It's `max(p.overall for p in champion.roster)`. So whoever has the highest current overall rating wins it, regardless of what they did in the playoffs. If your star player got injured in Game 1 of the Finals but recovered, they still win FMVP. The fix is simple — use the playoff game logs from `season.playoff_rounds` games — but this is the current behavior.

**DPOY is vulnerable to assignment bias.** Since `_pick_defender` always matches same-position first, a defender who plays the same position as many weak offensive players will have a great defensive rating through no merit of their own. DPOY on small rosters (where one player guards most of the opponents at their position) is inherently noisy.

**Injury model is solid.** The formula `base + (1-durability)×scale + fatigue×scale + max(0, age-threshold)×scale` capped at 0.80 is clean and multi-factor. Pre-season injury block (miss a contiguous chunk of games) is better than per-game rolls for simulation performance.

---

## Owner System

The motivation-differentiated happiness formulas are the right architecture. Making the three motivations produce dramatically different behavior is what makes the owner meeting genuinely interesting. But there are calibration issues:

**Money owner formula hits its ceiling way too fast.** `base = 0.50 + profit × 0.06`. At `profit = +8.3M`, the formula hits 1.0 (clamped to 0.95). The described typical range is -$20M to +$60M. So any team making more than $8.3M in profit makes the money owner equally happy at 0.95. A team making $10M and a team making $60M are indistinguishable. Only the -$20M to +$8.3M range actually produces differentiated happiness. Given that popular teams in big markets can make well over $8.3M consistently, money owners in major markets will almost always be at or near 0.95. This feels wrong — money owners should want more money, and there should be meaningful gradient across the $0–$60M range. The scale factor should probably be closer to `0.006` (divide by 10) to spread the full profit range across the 0.0–1.0 happiness space.

**Local hero owners are hard to upset.** At average `popularity=0.5, engagement=0.5`: `0.15 + 0.5 × 1.40 = 0.85`. An average team in an average market makes a local hero owner thriving. They need to be genuinely bad (popularity below ~0.25) before they start feeling the pain. This might be intentional (local heroes are patient) but it does mean they rarely escalate to DEMAND unless the team tanks severely.

**STEADY owner patience (8 seasons) is very long.** 8 consecutive seasons below the lean threshold before they escalate to DEMAND. A team can miss the playoffs for 8 years under a steady owner and never force a hard decision. In a 20-year career game this is a long time to let a situation fester before it becomes a crisis.

**The 40%/60% happiness blend is good.** It prevents single-season variance from wrecking an owner's happiness and creates inertia in both directions. This is one of the most realistic touches in the system.

---

## Revenue & League Economy

The revenue formula (`market_engagement × pop_mult × effective_metro × revenue_per_fan_million`) is well-structured. Market size is permanent leverage for big-market teams, which is correct. Popularity creates a [0.80, 1.20] multiplier — modest enough that small markets aren't dead, significant enough that building a popular team in a small market is meaningful.

The progressive cost curve (cost_scale `0.85 + 0.15 × metro/max_metro`) is a nice touch. Small markets pay slightly less to operate, which protects them from structural losses while keeping the big-market economic advantage real.

Revenue efficiency (`0.60 + 0.40 × competence`) creates a meaningful hidden dimension for owners — an incompetent owner with high-revenue markets still loses money they shouldn't. Range is [0.60, 1.00], so the worst owner captures 60% of gross. This seems reasonable.

---

## Rival League

The three types (external investors / owner defection / player walkout) are well-differentiated conceptually. The walkout mechanic is the most creative because it inverts the rival dynamic — the threat is internal, not external.

**FA pull formula is strong.** `0.05 + strength × 0.25` = 5% to 30% of the FA pool. At full strength, 30% of free agents go to the rival every offseason. Over several seasons this compounds significantly. This is probably the right level of urgency once the rival is established.

**Type B starts very strong.** Owner defection creates a league with `strength = avg_team_strength + 0.10`, typically 0.60-0.75 from the start. A Type B event is immediately a major crisis. The narrative consequence (you lose 2-4 real franchises from your league) makes it the most severe event type. Good.

**Lightweight simulation is appropriately thin.** The rival season simulation is just strength + noise → win%, then a simplified bracket. It's a narrative device and doesn't need more depth than this. The notable player PPG generation (`16.0 + strength × 14.0 + gauss(0, 2.5)`) produces a range of roughly 16-32 PPG at full strength — these numbers look realistic without any actual simulation.

---

## Coaching Mechanic — Design Notes

The current systems are missing one layer of control between the roster and the game engine: how the roster is deployed. That's exactly where a coach lives, and there's a natural hook for it in two places already: `zone_dist()` and `_pick_defender()`.

**What a coach could affect:**

1. **Shot zone selection** — The `preferred_zone` of each player determines their zone distribution, but a coach style could modify the weights. A "pace-and-space" coach shifts all players' distributions toward 3pt by say 10-15%. A "paint-heavy" coach pushes toward paint. A "balanced" coach does nothing. This is one line of code in `_pick_zone()` — multiply the base zone weights by a coach modifier before `random.choices()`.

2. **Defensive assignment** — Currently `_pick_defender` takes the first same-position match. A coach scheme could change this. A "pack the paint" scheme assigns the best available defender regardless of position, biased toward whoever is near the basket. A "switch everything" scheme randomizes the match. This is also one function, already clean for modification.

3. **Bench quality modifier** — The bench quality formula has three input factors (profit, competence, popularity). A coach `development_rating` could add a fourth term in `_bench_quality()`, representing how well the coach prepares backup players.

4. **Chemistry evolution rate** — A good coach could improve chemistry gain speed or reduce loss from player conflicts.

5. **Fatigue management** — A coach `load_management_rating` could reduce the `fatigue × 0.12` offensive penalty or the rate at which playoff fatigue accumulates.

**Proposed system:**

Coaches have one visible stat (`style`: pace-and-space / defensive / balanced / player-development) and one hidden stat (`rating`: 0-1). The style affects zone weights and defense assignment. The rating affects bench quality and chemistry.

Each team has a coach with a 2-4 year contract. Commissioner events:
- Coach contract expiry → hire from free agent pool or extend
- Coach fired → costs treasury, owner happiness hit (especially winning owners)
- Coach poached by rival league → narrative event, team loses them mid-contract
- Coach of the Year award → goes to coach of the best-record team

Owner happiness adds a small coach-sensitivity term: winning owners get -0.05 if the coach's team has missed playoffs 2+ consecutive years under the same coach.

The key design goal: the visible style choice must feel like it matters. If "defensive" + "paint-heavy roster" creates a DPOY factory and lower opponent scores, and "pace-and-space" + "Guard-heavy roster" produces higher scores and an MVP candidate — that's a satisfying system where the coach-roster fit is a real strategic question.

---

## Outstanding Issues (as of this assessment)

| Issue | Severity | File | Notes |
|-------|----------|------|-------|
| Money owner happiness ceiling at $8.3M profit | Medium | `league.py` | Rescale `0.06` → `~0.006` |
| Finals MVP uses `overall` not playoff stats | Low | `season.py` | Easy fix: use playoff game logs |
| DPOY attribution bias from positional defender match | Low | `game.py` | Coaching mechanic may resolve |
| FT zone secretly most efficient zone | Low | `game.py` | Monitor for Big-heavy roster exploitation |
| Schedule shrinks with league growth (30 games at 16 teams) | Low | `season.py` | Consider a floor on games_per_pair |
| Durability is injury-only, not a performance dimension | Low | `player.py` | Consider regular-season fatigue |
| STEADY owner patience = 8 seasons before DEMAND | Low | `owner.py` | May be too patient for engaging gameplay |
