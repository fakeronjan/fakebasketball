# Steam release checklist

Plan: Windows-only launch at $1.99. Live copy at fakebasketball.com/checklist/ (unlinked, noindex). Keep this file and `checklist/index.html` in sync.

Two Steam clocks set the order: paying the $100 fee starts a 30-day wait before release, and the store page must be public as "Coming Soon" for at least 2 weeks before release. Start both early and do the game work while they run.

**Fee paid 2026-11-04. Earliest possible release: 2026-12-04.** Releasing that day means the store page goes public (Coming Soon) by 2026-11-20.

## Phase 1: Sign up (outside the game, do first)
1. [x] Pick the developer/publisher name shown on the store: fakeronjan for both
2. [x] Search Steam to confirm no game is already called "Fake Basketball" (none found 2026-11-04)
3. [x] Create a Steamworks account and sign the distribution agreement (https://partner.steamgames.com/steamdirect)
4. [ ] Enter bank info, W-9 tax form, and identity verification (bank + tax done 2026-11-04, identity pending review)
5. [x] Pay the $100 fee (starts the 30-day clock, gives you an App ID)

## Phase 2: Game work (during the 30 days)
6. [x] Replace real team names and remove "NBA standard" text (done 2026-11-04). Rule: replace any name matching an ACTIVE team in the same city (any sport/level) or a DEFUNCT BASKETBALL team in the same city; college names replaced; defunct non-basketball names are OK to keep. Rival leagues block exact real city+name pairs (`_REAL_TEAM_PAIRS` in `rival.py`).
7. [x] Decide which interface ships: terminal version (decided 2026-11-04; touch UI can follow as a later update)
8. [x] Wrap it in Electron and set the cross-origin headers in the shell (done 2026-11-04: `desktop/`, Electron 44.9.2, app:// scheme with COOP/COEP; run with `cd desktop && npm start`)
9. [x] Bundle Pyodide inside the app so it runs fully offline (done 2026-11-04: `desktop/build-app.mjs` vendors Pyodide 0.27.0 + xterm.js into `desktop/app/`; tested with all external requests blocked)
10. [x] Move saves to the user's AppData folder (done 2026-11-04: Electron keeps the save in %APPDATA%\Fake Basketball; closing the window saves first. A real save file is only needed if we add Steam Cloud)
11. [x] Desktop polish (done 2026-11-04): app icon (`desktop/assets/`), bundled Cascadia Mono font, F11 / Alt+Enter fullscreen, Ctrl +/-/0 text size (remembered), window size/position remembered, single instance, closing the window saves first, standings W-L column fits 100+ wins
12. [x] Set up a Windows test machine (done 2026-11-05: UTM VM "Windows 11", Windows 11 ARM build 26300, ISO in `desktop/vm/`; `utmctl exec`/`file push`/`file pull` work via the guest agent)
13. [x] Build the Windows version and test it on that machine from scratch (done 2026-11-05 in the VM: offline load, font, F11/Alt+Enter/Esc, Ctrl +/-/0, resize/maximize reflow, full season on Enter only, close-with-X saves in 0.6s, relaunch restores save + text size + window, Continue resumes at Season 2, single instance. Launch to menu ~9s in the VM under x64 emulation. Test runner lives at C:\fbtest in the VM)
14. [ ] Upload the build to Steam with SteamPipe and set launch options
15. [ ] Install through Steam on the test machine and play a full season

## Phase 3: Store page (alongside Phase 2)
16. [ ] Capsule art: header, small, main, vertical, library capsule, hero, logo (exact sizes in Steamworks)
17. [ ] At least 5 screenshots at 1920x1080
18. [ ] Short and long descriptions
19. [ ] Tags, genre, system requirements, $1.99 price
20. [ ] Content-rating questionnaire
21. [ ] Trailer (optional)
22. [ ] Submit the store page for review; once public as Coming Soon, the 2-week clock starts

## Phase 4: Release
23. [ ] Free Steam keys or a beta branch for a few friends (optional)
24. [ ] Submit the build for Valve's review
25. [ ] Set the release date (at least 30 days after the fee and 2 weeks after Coming Soon)
26. [ ] Release
27. [ ] After launch: patch pipeline, read reviews and discussions
