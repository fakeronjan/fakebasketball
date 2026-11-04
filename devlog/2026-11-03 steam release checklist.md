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
6. [ ] Remove the "Lakers" nickname option (`franchises.py:71`) and "NBA standard" text (`commissioner.py:953`)
7. [ ] Decide which interface ships: terminal port, or the mobile touch shell adapted for desktop
8. [ ] Wrap it in Electron and set the cross-origin headers in the shell (drops the service-worker workaround)
9. [ ] Bundle Pyodide inside the app so it runs fully offline
10. [ ] Move saves to the user's AppData folder
11. [ ] Desktop polish: window title, app icon, resizing/fullscreen, clean quit (no leftover "[q] quit" hints)
12. [ ] Set up a Windows test machine (free Windows 11 VM via UTM)
13. [ ] Build the Windows version and test it on that machine from scratch
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
