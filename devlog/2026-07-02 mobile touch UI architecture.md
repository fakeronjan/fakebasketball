# Mobile Touch UI — Architecture & Roadmap

**Date:** 2026-07-02
**Goal:** Turn the terminal Commissioner game into a real mobile app with a touch
UI (buttons/cards/tabs), not a terminal-on-a-phone. Chosen ambition level: **Tier 3**
(the full touch UI), built incrementally so the game stays playable throughout.

**Target device:** Samsung Galaxy Fold (Chrome / Android), tested in **both folded
(tall, narrow cover screen) and unfolded (large near-square) modes**. Implication:
Android Chrome has solid SharedArrayBuffer + service-worker COI support, so the
iOS-Safari transport risk is off the table — the existing worker+SAB bridge is a
safe foundation. The Fold's two form factors make **fluid, responsive layout** a
first-class requirement from Phase 0.

**Framework:** deferred. Phase 0 ships in vanilla JS (renders text blocks + buttons —
a framework would be overhead). We pick a framework at Phase 2 with a working app in
hand. The engine→view-model→renderer boundary makes that swap mechanical, not a rewrite.

---

## Guiding principle

**Keep the calibrated Python sim engine. Replace only the presentation.**

The sim (`game.py`, `league.py`, `player.py`, `season.py`, `owner.py`, `coach.py`,
`rival.py`) is years of tuning and stays untouched. The work is decoupling
`commissioner.py`'s terminal I/O from the logic and rendering structured state as
native touch components.

```
┌───────────────────────────────────────────────────────────┐
│  TOUCH UI  (mobile-first web — framework TBD)             │
│  renders view-models → cards/tables/buttons; emits actions │
└─────────────▲─────────────────────────────┬───────────────┘
        view-model (JSON)              action (JSON: chosen id)
┌─────────────┴─────────────────────────────▼───────────────┐
│  BRIDGE  (thin, in commissioner.py + a JS transport)      │
│  • choose()/prompt()/press_enter() emit a prompt-request  │
│    and block until the UI returns a choice (NO input())   │
│  • screens emit VIEW-MODELS instead of print()            │
└─────────────▲─────────────────────────────────────────────┘
              │  (unchanged calls)
┌─────────────┴─────────────────────────────────────────────┐
│  SIM ENGINE  game/league/player/season/owner/coach/rival  │
│  the calibrated logic — DO NOT TOUCH                       │
└───────────────────────────────────────────────────────────┘
```

---

## Why this is tractable (findings from the code map)

- **Input is already centralized.** Every decision funnels through three module-level
  helpers — `prompt()` (216), `choose()` (240), `press_enter()` (237). Redefining
  those three redirects *all* menus to the UI with **zero changes to the ~87
  call sites** (40 `choose`, 47 `prompt`). Only 5 raw `input()` paginator bypasses
  exist (5669, 6467, 6480, 6554, 6818) — normalize them to `press_enter()` first.
- **Output is the real work.** ~786 `print()` calls across ~55 screens, fused
  print-as-you-go. These become structured view-models one screen at a time.
- **Precedent exists.** `_export_all_reports` (2623) already re-renders every report
  into an ANSI-free `list[str]` buffer via `w()`/`section()` helpers — proof a
  print-free rendering layer works. Plus reusable `-> list[str]/-> str` helpers
  (`_desk_flags` 6235, `_runner_up_rows` 2078, `_player_row` 1437, `pop_bar` 85,
  `trend` 91, `era_label` 96) seed view-models directly.
- **State is "clean nouns, derived adjectives."** Core facts are object attributes
  (`league.teams`, `season.player_stats`, etc.); the values computed *inline in
  print blocks* (odds, badges, relative net rating) are what we lift into view-models.

---

## The input transport (how a tap crosses JS ↔ Python)

This is one **isolated** concern with a proven default and a fallback — decoupled
from all the view-model work:

- **Reuse the existing SharedArrayBuffer + Web Worker bridge.** It already works today
  (`worker.js` + `Atomics.wait`). We change only the *payload*: before blocking for
  input, the three helpers emit a structured prompt-request (`{kind, title, options,
  default}`) so the UI can draw buttons; the answer returns over the same SAB channel
  as a string, so `choose()`'s existing digit-parsing is unchanged.
- **Transport risk: LOW on the target device.** Galaxy Fold = Android Chrome, which
  has solid SAB + service-worker COI support. No iOS Safari concern. (If a future iOS
  build is ever wanted, the `run_sync`/JSPI fallback below is swappable behind the
  same three helpers.)
- **Fallback (only if ever needed): Pyodide `run_sync` (Asyncify/JSPI).** Lets
  synchronous Python block on a JS promise with no async-contagion, no SAB, no COI.

Either way, going action-driven means **no blocking `input()`**, which is the whole
reason the SAB/iOS question stops being load-bearing.

---

## View-model contract (draft)

A screen serializes to a typed document the UI renders generically:

```jsonc
{
  "screen": "star_fa_event",
  "header": { "title": "MARQUEE FREE AGENCY", "subtitle": "After Season 14" },
  "blocks": [
    { "type": "banner", "tone": "elite", "icon": "⭐", "title": "THE LEAGUE IS WATCHING",
      "text": "An elite-tier player is on the open market." },
    { "type": "player_card", "name": "…", "mood": "😀", "meta": "F · Age 26 · 6 seasons left",
      "ortg": 3.2, "drtg": -1.1, "trend": "↗", "motivation": "WINNING", "tone": "green" },
    { "type": "table", "columns": ["Destination","Market","Net","Odds","Coach draw","Notes"],
      "rows": [ /* per-destination */ ] },
    { "type": "status", "treasury": 120, "legitimacy": 0.62, "warning": null }
  ],
  "options": [
    { "id": 0, "kind": "nudge", "label": "Nudge → Detroit", "cost": 10, "leg": 0.02 },
    { "id": 6, "kind": "none",  "label": "No intervention — let it play out" }
  ],
  "default": 6
}
```

Un-migrated screens fall back to `{ "type": "raw_text", "ansi": "…" }`, rendered in a
scrollable terminal-style block — so **the whole game is playable from day one** and
each screen migration is an independent, shippable upgrade.

---

## Phased roadmap

**Phase 0 — Bridge + mobile shell (the unlock). ✅ BUILT 2026-07-02 (pending device test).**
- ✅ Normalized the 5 raw `input()` bypasses to `press_enter()` (5669/6467/6480/6554/6818).
- ✅ `choose`/`prompt`/`press_enter` now emit structured prompt-requests + await the UI
  answer over the existing SAB transport, gated by `commissioner._frontend_active`
  (default False → terminal behavior byte-for-byte unchanged; verified). Quit/reports
  intercept factored into `_intercept()`; reports detour re-emits the prompt via `_fe_read(meta)`.
- ✅ `mobile-worker.js` — Pyodide worker that injects `webPrompt`, sets `_frontend_active`,
  reuses the SAB input channel. Terminal `worker.js` left untouched.
- ✅ `mobile.html` — vanilla touch shell: header (Reports/Menu), scrollable ANSI-stripped
  log, sticky controls that render `choose`→buttons, `text`→field, `enter`→Continue.
  Responsive for Fold (folded stack / unfolded 2-col grid for >6 options).
- Validated headlessly: bridge logic (7 cases incl. default/invalid/reports/quit),
  terminal path intact, JS syntax, serve.py serves all files with COOP/COEP.
- **Remaining:** live device test on the Galaxy Fold (folded + unfolded) via GitHub
  Pages HTTPS (`/mobile.html`). LAN-IP HTTP won't work — SAB needs a secure context.
- **Outcome:** entire game playable on a phone with tap-to-choose menus (no keyboard).
  This alone is the biggest single mobile-UX win and validates the architecture.

**Phase 1 — View-model contract + first structured screen (vertical slice).**
- Lock the view-model schema.
- Migrate `_handle_star_fa_event` (5962–6094) to emit a structured view-model; build
  the matching touch components (player card + destination list + decision buttons).
- **Outcome:** one screen looks native; proves the display+decision contract.

**Phase 2+ — Migrate screens by frequency/impact (waves).**
- Every-season screens first: season summary A/B/C (1845/1949/2149), commissioner's
  desk (6820), offseason recap (5743).
- Then high-interaction: owner actions (7978), draft (6095), CBA (9520), rival events.
- Reuse `_export_all_reports` buffer + existing row-formatters as view-model seeds.

**Phase N — Packaging.**
- PWA manifest + icons (installable). Optionally Capacitor for App Store / Play Store,
  bundling Pyodide locally to kill the ~10MB first-load download.

---

## Open decisions

1. **UI framework** — React (biggest ecosystem + Capacitor path), Svelte (lightest),
   or vanilla + a small lib. Affects the shell but not the Python bridge.
2. **iPhone SAB test** — user to run, decides transport (SAB vs `run_sync` fallback).
3. **Distribution** — PWA (install from web) vs native store build. Deferrable to Phase N.
</content>
</invoke>
