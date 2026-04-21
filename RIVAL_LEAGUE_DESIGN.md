# Rival League — Full Design Document

## Concept

A competing basketball league that exists in parallel to the commissioner's league. It does not simulate games possession-by-possession — it runs on a lightweight abstraction — but it generates real standings, champions, notable players, and commissioner decisions every season. Three distinct formation types with different triggers, stakes, and resolution mechanics. Multiple rival league events can occur across a single save; each type has its own cooldown after resolution.

---

## Formation Types

### Type A — External Investors

**Trigger:** Commissioner's league has been highly popular (`league_popularity >= threshold`) for several consecutive seasons. Success attracts competition.

**What it means:** A group of outside investors launches a competing league. The commissioner's league loses nothing immediately — no teams, no players — but the rival begins recruiting in the FA pool and building infrastructure. The threat level is **unknown at formation**: the rival could be well-funded (serious talent war) or a paper tiger (collapses within 2–3 seasons on its own).

**Key mechanic — uncertainty reveal:** The rival's true funding level (`rival_funding: float`, 0.0–1.0) is hidden at formation. Over 1–2 seasons, events surface intel:
- *"The [Name] League has secured a national broadcast deal."* → high funding revealed
- *"The [Name] League has reportedly failed to secure stadium leases in two cities."* → low funding
- *"[Star Name] has signed a contract with the [Name] League."* → mid-to-high funding

Commissioner must decide how aggressively to respond without knowing the full picture.

**Cooldown after resolution:** 8 seasons before a new Type A rival can form.

---

### Type B — Owner Defection

**Trigger:** One owner reaches `THREAT_DEMAND` and becomes a **ringleader** — they begin quietly recruiting other disgruntled owners. Defection fires if 4+ owners commit.

**Recruitment mechanic:**
- Ringleader = any owner at `THREAT_DEMAND` for 2+ consecutive seasons
- Each other owner rolls to commit based on threat level:
  - `THREAT_DEMAND` → ~75% chance
  - `THREAT_LEAN` → ~35% chance
  - `THREAT_QUIET` → ~5%
- If total committed < 4: attempt fails. Ringleader is forced into an ownership change (they sell, leave the league). Other followers stay, threat levels cool slightly.
- If total committed ≥ 4: defection fires at the start of next season.

**Warning window:** The season before the split fires, commissioner receives a desk flag: *"[Owner] is reportedly in contact with other ownership groups about alternative arrangements."* One offseason to act — emergency owner meeting, appease followers, or accept what's coming.

**What it means:** Defecting owners take their **teams and full rosters** with them. Those teams immediately become franchises in the rival league. The commissioner's league is suddenly short N franchises. The rival league starts with real teams, real markets, real talent — no ramp-up period.

**Cooldown after resolution:** 6 seasons before a new Type B rival can form.

---

### Type C — Player Walkout

**Trigger:** CBA negotiations result in a work stoppage that is **not resolved** by season start. Currently work stoppages resolve in one cycle; Type C is the extended failure state. Requires at least one failed CBA negotiation with no settlement reached.

**What it means:** All rostered players walk. Teams are intact; rosters are gutted. The season runs with **replacement players**. Striking players form a barnstorming circuit (the "player league") — not a full infrastructure, but enough to generate narrative events and apply return pressure.

**Replacement roster construction:**
1. FA pool players are offered replacement contracts first — the best available become **scab stars** (flagged, surfaced as named events if above a rating threshold: *"[Name], formerly of the [Team], has agreed to a replacement contract."*)
2. Remaining slots filled with freshly generated low-rated players (nobodies)
3. One scab star event per team maximum

**Scab flag:** Any FA pool player who signs a replacement contract gets `crossed_picket = True`. When regulars return, scab players are released. The flag persists — some returning stars may refuse to sign with teams that prominently used scabs; scab players face happiness/chemistry penalties if they re-enter the league.

**Dual degradation pressure:** Both sides weaken each offseason:
- Player circuit degrades without stadium deals, TV contracts, infrastructure
- Commissioner's league loses fan engagement (replacement ball is obvious), legitimacy drops, owner P&L suffers

**Cooldown after resolution:** 10 seasons before a new Type C rival can form (the players got real CBA protections out of it).

---

## Rival League Identity

Every rival league — regardless of type — gets a **generated identity** at formation.

### Name Generation

Pulls from pools:

**Adjective pool:** National, Continental, American, United, Independent, Professional, Premier, Alliance, Federal

**Noun pool:** Basketball League, Basketball Association, Basketball Union, Hoops League, Basketball Conference, Basketball Circuit

Examples: *"Continental Basketball Association"*, *"National Hoops League"*, *"United Basketball Union"*

Avoids name-collisions with the commissioner's league name.

### Team Generation

Type A and Type C rivals generate **new fictional franchises** (not drawn from the commissioner's reserve pool — these are independent entities). Each team gets:
- A city (drawn from a pool of cities not currently occupied by the commissioner's league)
- A nickname from a separate rival-league nickname pool
- A color identifier for display purposes (single ANSI color)

Type B rivals inherit the defecting teams' identities — they keep their names, cities, and rosters.

**Team count by type:**
- Type A: starts with 4–6 teams, can grow to 8–10 if well-funded
- Type B: exactly the number of defecting owners' teams
- Type C: 6–8 barnstorming teams (lighter structure, not city-anchored)

---

## Rival League State

```python
@dataclass
class RivalLeague:
    name: str
    formation_type: str          # "external" | "defection" | "walkout"
    formed_season: int
    active: bool

    # Core strength
    strength: float              # 0.0–1.0 — overall establishment level
    funding: float               # 0.0–1.0 — hidden for Type A until revealed
    funding_revealed: bool       # False until intel event fires

    # Teams
    teams: list[RivalTeam]

    # Season history (lightweight)
    season_records: list[RivalSeasonRecord]   # one per season active

    # Type-specific flags
    ringleader_owner_id: int | None          # Type B only
    defected_team_ids: list[int]             # Type B only — original team IDs
    scab_player_ids: list[int]               # Type C only

@dataclass
class RivalTeam:
    name: str                    # "City Nickname"
    strength: float              # 0.0–1.0 — talent level
    original_team_id: int | None # Type B only — links back to commissioner's team

@dataclass
class RivalSeasonRecord:
    season: int
    standings: list[tuple[str, int, int]]    # (team_name, wins, losses)
    champion: str                             # team name
    champion_strength: float
    notable_players: list[tuple[str, float]] # (name, ppg)
    strength_delta: float                    # how much rival grew/shrank this season
```

---

## Lightweight Season Simulation

The rival league does not simulate possessions. Each season, it generates results abstractly:

**Standings generation:**
- Each team's win% is derived from its `strength` with noise: `win_pct = strength + random.gauss(0, 0.12)`
- Win/loss records back-calculated from win% across a fixed 40-game schedule
- Sorted by win%

**Champion selection:**
- Top 4 teams enter a playoff bracket
- Each series: higher-strength team wins with probability = `0.5 + (strength_diff × 0.4)`
- Produces one champion per season

**Notable players:**
- Each team has 1–2 named players (generated at team formation, or real players for Type B/C)
- PPG estimated from team strength and a per-player multiplier
- Top 3 league-wide surface in the report

**Rival strength evolution (each offseason):**
- Base growth: `+0.04` if active and not under commissioner pressure
- Commissioner actions reduce it (see below)
- Type A: also affected by funding level (high funding → faster growth)
- Type C: player circuit degrades `−0.06` naturally each season regardless of commissioner action
- Floored at 0.0 (triggers collapse event); capped at 1.0

---

## Commissioner Decisions

### Each Offseason (while rival is active)

Presented as a commissioner desk event. Options vary by type and rival strength.

#### Type A & General Options

| Option | Effect | Cost |
|---|---|---|
| **Monitor** | Rival grows +0.05 | Nothing |
| **Wage talent war** | Rival FA pull reduced this season; rival strength −0.08 | $15–25M treasury |
| **Legal & media pressure** | Rival strength −0.12; may slow team expansion | Legitimacy −0.05 |
| **Offer merger terms** | Available when rival strength ≤ 0.40; rival dissolves, some teams join your league | $30–50M + legitimacy −0.08 |

#### Type B Additional Options

| Option | Effect | Cost |
|---|---|---|
| **Negotiate return** | Approach defected owners; 1–2 may return (with their teams + rosters) | $20–40M + legitimacy −0.06 |
| **Poach their players** | Star FA events from defected teams' rosters; players can be lured back | Normal FA mechanics |
| **Emergency expansion** | Fill gaps with new franchises to stabilize team count | Standard expansion cost |
| **Contest their markets** | Place expansion team in a defected team's home city | Standard expansion cost |

#### Type C Additional Options

| Option | Effect | Cost |
|---|---|---|
| **Offer CBA concessions** | Players may return; ends Type C if accepted | Legitimacy −0.05 to −0.15 depending on terms |
| **Hold firm** | Season runs with replacements again; player circuit degrades | Fan engagement −0.08, legitimacy −0.05 |
| **Partial deal** | Some stars return (chosen randomly), others stay out one more season | Legitimacy −0.03 |

---

## Passive Effects (Each Season, While Active)

| Rival Strength | Effect |
|---|---|
| Any | FA pool reduced by `rival_fa_pull` — some players sign rival contracts |
| ≥ 0.30 | Owner dissatisfaction ticks up slightly each offseason for unhappy owners |
| ≥ 0.50 | League popularity growth dampened; fan engagement grows slower |
| ≥ 0.70 | Each offseason: chance a `THREAT_DEMAND` owner defects (Type A only) |
| Type C any | Fan engagement −0.06/season; legitimacy −0.04/season during replacement play |

`rival_fa_pull` scales with strength: `0.05 + strength × 0.25` (max ~30% of FA pool siphoned at full strength).

---

## Resolution Paths

### Rival Collapses (strength → 0.0)
- Event fires: *"The [Name] League has ceased operations."*
- Type A: any rival-signed players re-enter FA pool next season
- Type B: defected teams may return (commissioner gets option to re-absorb at reduced cost); players re-enter FA pool if team doesn't return
- Type C: striking players return to their original teams; scab players released; normal FA resumes
- Popularity boost: `+0.03` (your league is the only game in town again)

### Rival Forces Merger (legitimacy < 0.20 while rival strength ≥ 0.70)
- Rival negotiates from strength — commissioner gets no choice
- Rival teams (4–8) absorb into your league as new franchises
- Treasury cost: $50–80M
- Legitimacy: −0.10
- Rival dissolves after absorption

### Commissioner Brokers Merger (option 4 above)
- Commissioner controls timing and terms
- 2–4 rival teams absorb into your league
- Cheaper and cleaner than forced merger

### Stalemate
- Neither collapses, no merger. Both leagues persist. Rare but possible if commissioner keeps choosing Monitor and rival doesn't have the funding to dominate.

---

## Cross-Type Interactions

**Type A + Type B simultaneously:** If a well-funded external rival (Type A) is active when owner defections occur, the rival can recruit defecting owners — their teams go directly into the rival league rather than forming a new one. Type A rival is strengthened significantly; no new rival forms.

**Type B leading to Type C:** If owner defections have already fired AND a subsequent CBA fails, Type C can stack on top. Remaining teams in your league lose their players on top of already being fewer teams. Worst-case scenario — mechanically possible, probability naturally low.

**Type C and scabs:** When regulars return after Type C resolves, teams with high-profile scabs may see happiness penalties for returning stars who don't want to play alongside them. Scab players face an open FA market but with reduced signing interest.

---

## Reporting — Rival League Tab

When a rival league is active, a **Rival League** option appears in the reports menu.

### Page 1 — Overview
- League name, formation type, seasons active
- Current strength meter (bar display, color-coded: green weak / gold moderate / red strong)
- Funding level (shown as "Unknown" until reveal event fires, then "Modest / Adequate / Well-funded / Flush")
- Active teams list with strength indicators
- This season's commissioner decision and its effect

### Page 2 — Standings & Champion
- Current season standings (team, W, L, win%)
- Champion for each season the rival has been active
- Notable players this season (name, team, estimated PPG)

### Page 3 — History
- Season-by-season strength trend
- All champions since formation
- Key events (funding reveals, team additions, commissioner actions taken)

### After Resolution
- Report becomes historical ("Former Rival Leagues") — one entry per resolved rival, showing how it ended and how many seasons it ran.

---

## Integration With Existing Systems

| System | Impact |
|---|---|
| **Free agency** | `rival_fa_pull` removes a fraction of the pool before commissioner sees star FA events |
| **CBA** | Type C is the extended failure state of a work stoppage; CBA screen gains a "risk of walkout" warning when player happiness is low |
| **Owner system** | Type B adds ringleader detection; `THREAT_DEMAND` owners flagged as defection risks; owner meeting gains "rival league overture" flag |
| **Legitimacy** | Rival strength ≥ 0.50 adds passive legitimacy drain; forced merger is a legitimacy crisis |
| **Treasury** | Adds meaningful spending options; hoarding money while rival grows is a valid but risky strategy |
| **Commissioner desk flags** | Rival strength ≥ 0.50 → gold flag; ≥ 0.70 → red flag; ringleader detected → gold flag |
| **Expansion** | Type B may prompt emergency expansion; merger resolutions add new franchises |
| **Existing merger mechanic** | Kept as-is — fires when league popularity is low, adds reserve-pool teams. Separate from the rival league system (early-game absorption vs. mid-game narrative threat) |

---

## Build Phases

### Phase 1 — Type A (External Investors)
Establishes the shared infrastructure all types will use:
- `RivalLeague` / `RivalTeam` / `RivalSeasonRecord` data model
- Rival name + team generation
- Lightweight season simulation (standings, champion, notable players)
- Commissioner decision event (offseason, desk flag)
- Rival league reports tab (3 pages)
- Resolution logic (collapse, forced merger, brokered merger)
- History log for resolved rivals

### Phase 2 — Type C (Player Walkout)
- Replacement player season mode
- Scab star mechanic (FA pool draw, `crossed_picket` flag, naming event)
- Dual degradation pressure (player circuit + commissioner league)
- CBA integration (work stoppage → Type C if unresolved)
- Return negotiation options and resolution

### Phase 3 — Type B (Owner Defection)
- Ringleader detection and recruitment simulation
- Warning window desk flag
- Team defection (remove from commissioner's league, add to rival)
- Win-back negotiation
- Emergency expansion hooks
- Market contest mechanics
- Type A + Type B interaction (external rival absorbs defecting owners)

---

## Key Config Values (Proposed)

```python
# Type A trigger
rival_a_popularity_threshold    = 0.72    # league_popularity must exceed this
rival_a_consecutive_seasons     = 3       # seasons above threshold before rival forms
rival_a_cooldown                = 8       # seasons after resolution

# Type B trigger
rival_b_ringleader_seasons      = 2       # THREAT_DEMAND seasons before recruiting starts
rival_b_min_defectors           = 4       # minimum owners to trigger split
rival_b_follow_prob_demand      = 0.75
rival_b_follow_prob_lean        = 0.35
rival_b_follow_prob_quiet       = 0.05
rival_b_cooldown                = 6

# Type C trigger
rival_c_cooldown                = 10

# Rival strength
rival_base_growth_per_season    = 0.04
rival_fa_pull_base              = 0.05
rival_fa_pull_strength_scale    = 0.25    # rival_fa_pull = base + strength × scale
rival_strength_collapse         = 0.0
rival_forced_merger_legitimacy  = 0.20
rival_forced_merger_strength    = 0.70

# Commissioner action costs
rival_talent_war_cost_min       = 15      # $M
rival_talent_war_cost_max       = 25
rival_talent_war_strength_delta = -0.08
rival_legal_pressure_strength_delta = -0.12
rival_legal_pressure_legit_cost = 0.05
rival_merger_cost_min           = 30
rival_merger_cost_max           = 50
rival_merger_legit_cost         = 0.08
rival_merger_max_strength       = 0.40    # must be this weak for option to appear

# Type C replacement
rival_c_player_circuit_decay    = -0.06   # per season, regardless of commissioner action
rival_c_fan_engagement_penalty  = -0.06   # per season during replacement play
rival_c_legitimacy_penalty      = -0.04   # per season during replacement play
```

---

## Open Design Questions (Parked)

- **Rival commissioner as a named character?** Adds personality to negotiations but also complexity. Parked for now — treat the rival as an institution, not a person.
- **Multi-slot saves with rival history?** The resolved rivals history log handles this adequately for single-slot. Multi-slot saves would need no special handling.
- **Can a rival league become dominant and absorb the commissioner's league?** Interesting endgame state but probably out of scope for Phase 1.
