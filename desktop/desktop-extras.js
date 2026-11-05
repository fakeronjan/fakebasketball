// Desktop-only behavior, loaded after the game page's own script (see
// build-app.mjs). Uses the page's globals: term, fitAddon, worker, sendInput,
// awaitingInput.
(function () {
  if (!window.fbDesktop) return;

  // ── Bundled font: re-measure the terminal once it has loaded ──────────────
  const refit = () => { try { fitAddon.fit(); } catch (_) {} };
  if (document.fonts && document.fonts.load) {
    Promise.all([
      document.fonts.load("14px 'Cascadia Mono'"),
      document.fonts.load("bold 14px 'Cascadia Mono'"),
    ]).then(() => {
      const fam = term.options.fontFamily;
      term.options.fontFamily = 'monospace';   // force xterm to re-measure
      term.options.fontFamily = fam;
      refit();
    }).catch(() => {});
  }

  // ── Text size: Ctrl/Cmd + plus / minus / 0 ─────────────────────────────────
  const KEY = 'fb_font_size';
  const DEFAULT = 14, MIN = 10, MAX = 26;
  let size = DEFAULT;
  try { size = Math.min(MAX, Math.max(MIN, parseInt(localStorage.getItem(KEY), 10) || DEFAULT)); } catch (_) {}
  const applySize = () => {
    term.options.fontSize = size;
    refit();
    try { localStorage.setItem(KEY, String(size)); } catch (_) {}
  };
  if (size !== DEFAULT) applySize();
  window.fbDesktop.onFontStep((step) => {
    size = step === 0 ? DEFAULT : Math.min(MAX, Math.max(MIN, size + step));
    applySize();
  });

  // ── Save before closing ───────────────────────────────────────────────────
  // The game's global "q" command saves and exits. Plain "press Enter" screens
  // don't listen for it, so keep answering "q" at each prompt until the game
  // reports it is done; main.js force-closes after a timeout as a backstop.
  let closeRequested = false;
  window.fbDesktop.onCloseRequested(() => {
    closeRequested = true;
    if (awaitingInput) sendInput('q');
  });
  worker.addEventListener('message', (e) => {
    const t = e.data && e.data.type;
    if (closeRequested && t === 'input_needed') sendInput('q');
    if (t === 'error') {
      // Python crashed: nothing left to save, let the window close normally.
      if (closeRequested) window.fbDesktop.quit();
    }
  });
})();
