# Capsule art generator

`art.html` draws every Steam capsule on a canvas (direction A, "Terminal").
Query params: `d=A&w=<width>&h=<height>`, plus `&hero` (artwork only) or `&logo` (transparent title).

`render.cjs` renders a list of jobs with headless Chromium (playwright-core):

    node render.cjs '[["A",920,430,"../header_capsule_920x430.png"]]'

Fonts: Cascadia Mono (SIL OFL 1.1), copied from desktop/node_modules/@fontsource/cascadia-mono.
