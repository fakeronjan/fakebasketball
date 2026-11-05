// Sound for the web page and the desktop app: opening jingle + event cues
// (jingle.js). Python asks for a cue with play_sound(); index.html passes it
// to fbPlaySound. Ctrl+M turns sound on or off and is remembered.
//
// Browsers only allow sound after the player presses a key or clicks, so on
// the web the opening jingle plays only if the page is already allowed to
// (the desktop app always is), and cues start working after the first key.
(function () {
  const KEY = 'fb_sound';
  let soundOn = true;
  try { soundOn = localStorage.getItem(KEY) !== 'off'; } catch (_) {}

  let actx = null;
  try { actx = new AudioContext(); } catch (_) { return; }
  let current = null;   // gain node of the cue that is playing

  const play = (schedule) => {
    if (!soundOn || actx.state !== 'running') return;
    try {
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

  // Opening jingle: only if sound is already allowed. A jingle that waited for
  // the first key press would start in the middle of the game.
  const startJingle = () => play((c, d, t) => fbScheduleJingle(c, d, t));
  const loaded = performance.now();
  if (actx.state === 'running') startJingle();
  else actx.resume().then(() => { if (performance.now() - loaded < 1500) startJingle(); }).catch(() => {});

  const unlock = () => { if (actx.state !== 'running') actx.resume().catch(() => {}); };
  window.addEventListener('keydown', unlock, true);
  window.addEventListener('pointerdown', unlock, true);

  // ── Ctrl+M toggle with a small note in the corner ─────────────────────────
  const toast = document.createElement('div');
  toast.style.cssText = 'position:fixed;top:12px;right:16px;padding:6px 12px;'
    + 'background:#262626;color:#d8d8d8;border:1px solid #3a3a3a;border-radius:4px;'
    + "font:13px 'Cascadia Mono',monospace;opacity:0;transition:opacity .3s;pointer-events:none;z-index:10";
  document.body.appendChild(toast);
  let toastTimer = null;
  const toggle = () => {
    soundOn = !soundOn;
    try { localStorage.setItem(KEY, soundOn ? 'on' : 'off'); } catch (_) {}
    if (!soundOn && current) { current.disconnect(); current = null; }
    toast.textContent = soundOn ? 'Sound on' : 'Sound off';
    toast.style.opacity = '1';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.style.opacity = '0'; }, 1500);
  };
  if (window.fbDesktop && window.fbDesktop.onSoundToggle) {
    // Desktop: main.js catches Ctrl+M before the page sees it
    window.fbDesktop.onSoundToggle(toggle);
  } else {
    // Web: catch Ctrl+M before the terminal turns it into Enter
    window.addEventListener('keydown', (e) => {
      if (e.ctrlKey && !e.altKey && !e.metaKey && e.key.toLowerCase() === 'm') {
        e.preventDefault();
        e.stopPropagation();
        toggle();
      }
    }, true);
  }
})();
