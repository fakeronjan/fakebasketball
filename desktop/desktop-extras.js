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

  // ── Sound: opening jingle + event cues (jingle.js), Ctrl+M toggles ───────
  const SOUND_KEY = 'fb_sound';
  let soundOn = true;
  try { soundOn = localStorage.getItem(SOUND_KEY) !== 'off'; } catch (_) {}
  let actx = null;
  let current = null;   // gain node of the cue that is playing
  const play = (schedule) => {
    if (!soundOn) return;
    try {
      if (!actx) actx = new AudioContext();
      if (actx.state === 'suspended') actx.resume();
      const now = actx.currentTime;
      if (current) {   // a new cue cuts off the one still playing
        current.gain.setValueAtTime(current.gain.value, now);
        current.gain.linearRampToValueAtTime(0, now + 0.05);
        const old = current;
        setTimeout(() => old.disconnect(), 200);
      }
      const g = actx.createGain();
      g.connect(actx.destination);
      current = g;
      schedule(actx, g, now + 0.03);
    } catch (_) {}
  };
  window.fbPlaySound = (name) => play((c, d, t) => fbScheduleCue(c, d, t, name));
  play((c, d, t) => fbScheduleJingle(c, d, t));

  const toast = document.createElement('div');
  toast.style.cssText = 'position:fixed;top:12px;right:16px;padding:6px 12px;'
    + 'background:#262626;color:#d8d8d8;border:1px solid #3a3a3a;border-radius:4px;'
    + "font:13px 'Cascadia Mono',monospace;opacity:0;transition:opacity .3s;pointer-events:none;z-index:10";
  document.body.appendChild(toast);
  let toastTimer = null;
  window.fbDesktop.onSoundToggle(() => {
    soundOn = !soundOn;
    try { localStorage.setItem(SOUND_KEY, soundOn ? 'on' : 'off'); } catch (_) {}
    if (!soundOn && current) { current.disconnect(); current = null; }
    toast.textContent = soundOn ? 'Sound on' : 'Sound off';
    toast.style.opacity = '1';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.style.opacity = '0'; }, 1500);
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
