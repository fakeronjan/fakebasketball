# Elite Player / Star System
*Session: 2026-04-25*

## What was built

### Design goal
The game was surfacing too much noise in the player-facing screens. The player meeting showed one mid-tier rep per team regardless of quality, and marquee moments (generational draft class, elite FA events) had no special treatment. This pass reorients the commissioner around star talent.

---

### ① Stars to Watch — Season Summary

Added a compact block in `_show_summary` (between playoff recap and League Health) showing the top 8 elite/high players in the league.

- Scans all roster slots across all teams for `peak_overall >= 12`
- Sorted by `peak_overall` descending (elite players always first)
- Each row: mood emoji · name · team · tier label · PPG stat
- Flags: `EXP` (red) for expiring contracts; `↓` (muted) for declining players
- Tier colors: **gold** for Elite, **cyan** for High

This is now the default view of league star health every season — no drilling required.

---

### ② Players' Meeting retool

Rewrote `_handle_players_meeting` to show only elite/high players.

**Before:** One slot-0 rep per team, all tiers mixed.

**After:**
- Collects all players with `peak_overall >= 12` from all roster slots (not just slot 0)
- Sorted by peak_overall descending
- Mid/low players summarized in one line: `"23 other rostered players  2 unhappy"`
- If no stars exist yet (early league): shows "No elite or high-tier players in the league yet."

Commissioner action options (marketing, rule change request, stability pledge) unchanged — they fire from the player audience drill-down exactly as before.

---

### ③ Generational Draft Class splash

Added a dedicated pre-screen in `_handle_draft` that fires before the main draft table when any prospect has `ceiling_tier == TIER_ELITE`.

Shows:
- `⭐ A GENERATIONAL TALENT IS IN THIS DRAFT CLASS` banner
- Player name, position, age
- Note that lottery influence has never mattered more

Existing lottery influence option ($10M) becomes much higher stakes in these years. No mechanical change — just surfacing the signal that was already there.

---

### ④ Elite FA showcase upgrade

Upgraded `_handle_star_fa_event` for elite-tier players (`peak_overall >= 18`):

- Header changes from `STAR FREE AGENT` → `MARQUEE FREE AGENCY`
- Gold banner: `⭐ THE LEAGUE IS WATCHING`
- Player card now shows "seasons left" (career runway) alongside existing stats
- Normal high-tier star FAs (`12–17`) keep existing screen without the dramatic framing

---

### ⑤ Popularity signals removed from health detail

Removed the "Popularity signals this season (underlying drivers)" section from `_show_league_health_detail`. The four-pillar component breakdown already covers everything that section was saying, more clearly. The underlying signal tracking (`_last_pop_signals`) is preserved for internal use (work stoppage annotations, etc.) but no longer displayed.

---

## Calibration notes

- Stars to Watch will be empty in Season 1 of small leagues — that's correct. High-tier players emerge by season 2–3 as draft classes are processed.
- Player meeting is significantly quieter now: a 6-team league might show 3–5 star reps instead of 6, and a 16-team league might show 6–10 instead of 16.
- Generational prospect splash will be rare (~3% chance per draft slot at baseline weights). When it fires, it should feel like an event.
