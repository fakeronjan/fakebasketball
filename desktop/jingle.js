// Opening jingle: A minor, i-VI-VII-V (Am F G E) then a big Am finish.
// Synthesized with Web Audio (square lead, triangle bass, noise drums) in the
// style of an old PC sound card, so there is no audio file to ship.
// fbScheduleJingle(ctx, dest, t0) works with a live or an offline context.
(function () {
  const BPM = 168;
  const BEAT = 60 / BPM;

  const NOTE = { C: 0, 'C#': 1, D: 2, 'D#': 3, E: 4, F: 5, 'F#': 6, G: 7, 'G#': 8, A: 9, 'A#': 10, B: 11 };
  const hz = (name) => {
    const m = /^([A-G]#?)(\d)$/.exec(name);
    const midi = 12 * (Number(m[2]) + 1) + NOTE[m[1]];
    return 440 * Math.pow(2, (midi - 69) / 12);
  };

  // [note, beats]; null = rest
  const LEAD = [
    // Am
    ['A4', 1], ['C5', 0.5], ['E5', 0.5], ['A5', 1], ['G5', 0.5], ['E5', 0.5],
    // F
    ['F5', 1], ['E5', 0.5], ['C5', 0.5], ['A4', 1], ['C5', 1],
    // G
    ['D5', 1], ['B4', 0.5], ['D5', 0.5], ['G5', 1.5], ['F5', 0.5],
    // E (harmonic-minor run back down)
    ['E5', 0.5], ['G#5', 0.5], ['B5', 0.5], ['G#5', 0.5], ['E5', 0.5], ['D5', 0.5], ['B4', 0.5], ['G#4', 0.5],
    // finish
    ['A5', 3],
  ];

  const BASS_ROOTS = ['A2', 'F2', 'G2', 'E2'];

  function tone(ctx, dest, type, freq, t, dur, vol, opts = {}) {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (opts.bend) {   // slide to freq * bend over the note (sad trombone)
      osc.frequency.setValueAtTime(freq, t + dur * 0.35);
      osc.frequency.linearRampToValueAtTime(freq * opts.bend, t + dur);
    }
    if (opts.vibrato) {
      const lfo = ctx.createOscillator();
      const lg = ctx.createGain();
      lfo.frequency.value = 6;
      lg.gain.setValueAtTime(0, t);
      lg.gain.linearRampToValueAtTime(freq * 0.025, t + dur * 0.5);
      lfo.connect(lg).connect(osc.frequency);
      lfo.start(t);
      lfo.stop(t + dur);
    }
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(vol, t + 0.005);
    g.gain.setValueAtTime(vol * (opts.sustain ?? 0.8), t + 0.06);
    g.gain.linearRampToValueAtTime(0, t + dur);
    osc.connect(g).connect(dest);
    osc.start(t);
    osc.stop(t + dur + 0.01);
  }

  function noiseBuffer(ctx) {
    const len = Math.floor(ctx.sampleRate * 1.5);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    return buf;
  }

  function hit(ctx, dest, noise, t, dur, vol, cutoff) {
    const src = ctx.createBufferSource();
    src.buffer = noise;
    const f = ctx.createBiquadFilter();
    f.type = 'highpass';
    f.frequency.value = cutoff;
    const g = ctx.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    src.connect(f).connect(g).connect(dest);
    src.start(t);
    src.stop(t + dur);
  }

  function kick(ctx, dest, t) {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.frequency.setValueAtTime(150, t);
    osc.frequency.exponentialRampToValueAtTime(40, t + 0.12);
    g.gain.setValueAtTime(0.9, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.15);
    osc.connect(g).connect(dest);
    osc.start(t);
    osc.stop(t + 0.16);
  }

  // Returns the jingle length in seconds.
  function schedule(ctx, dest, t0) {
    const master = ctx.createGain();
    master.gain.value = 0.22;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 5000;
    master.connect(lp).connect(dest);
    const noise = noiseBuffer(ctx);

    // Lead: square, an octave-up pulse doubled quietly for extra cheese
    let t = t0;
    for (const [n, beats] of LEAD) {
      const dur = beats * BEAT;
      if (n) {
        const last = beats >= 3;
        tone(ctx, master, 'square', hz(n), t, dur * (last ? 1 : 0.9), 0.32, { vibrato: last, sustain: last ? 0.9 : 0.7 });
        tone(ctx, master, 'square', hz(n) * 2, t, dur * 0.5, 0.06);
      }
      t += dur;
    }

    // Bass: triangle octave bounce in eighths, one bar per chord
    for (let bar = 0; bar < 4; bar++) {
      const root = hz(BASS_ROOTS[bar]);
      for (let i = 0; i < 8; i++) {
        const tt = t0 + (bar * 4 + i * 0.5) * BEAT;
        tone(ctx, master, 'triangle', i % 2 ? root * 2 : root, tt, 0.45 * BEAT, 0.55);
      }
    }
    const end = t0 + 16 * BEAT;
    tone(ctx, master, 'triangle', hz('A1'), end, 3 * BEAT, 0.7, { sustain: 0.9 });
    tone(ctx, master, 'triangle', hz('A2'), end, 3 * BEAT, 0.4, { sustain: 0.9 });
    // Final chord stab under the held A
    for (const n of ['C5', 'E5']) tone(ctx, master, 'square', hz(n), end, 3 * BEAT, 0.12, { sustain: 0.9 });

    // Drums: kick on 1 and 3, snare on 2 and 4, a fill into the finish
    for (let beat = 0; beat < 16; beat++) {
      const tt = t0 + beat * BEAT;
      if (beat >= 14) continue;
      if (beat % 2 === 0) kick(ctx, master, tt);
      else hit(ctx, master, noise, tt, 0.12, 0.5, 1500);
    }
    for (let i = 0; i < 4; i++) hit(ctx, master, noise, t0 + (14 + i * 0.5) * BEAT, 0.1, 0.35 + i * 0.1, 1500);
    kick(ctx, master, end);
    hit(ctx, master, noise, end, 1.2, 0.45, 4000);   // crash

    return 19 * BEAT;
  }

  // ── Short cues, same instruments and tempo as the opening jingle ──────────
  // Each takes (ctx, dest, t0) and returns its length in seconds.
  function cueSetup(ctx, dest) {
    const master = ctx.createGain();
    master.gain.value = 0.22;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 5000;
    master.connect(lp).connect(dest);
    return { m: master, noise: noiseBuffer(ctx) };
  }
  const lead = (ctx, m, n, t, beats, opts = {}) => {
    const dur = beats * BEAT;
    tone(ctx, m, 'square', hz(n), t, dur * (opts.vibrato ? 1 : 0.9), 0.32,
         { vibrato: opts.vibrato, sustain: opts.vibrato ? 0.9 : 0.7 });
    tone(ctx, m, 'square', hz(n) * 2, t, dur * 0.5, 0.06);
  };
  const bounce = (ctx, m, root, t, eighths) => {
    for (let i = 0; i < eighths; i++)
      tone(ctx, m, 'triangle', i % 2 ? hz(root) * 2 : hz(root), t + i * 0.5 * BEAT, 0.45 * BEAT, 0.55);
  };
  const finish = (ctx, m, noise, t, beats, low, chord) => {
    const dur = beats * BEAT;
    tone(ctx, m, 'triangle', hz(low), t, dur, 0.7, { sustain: 0.9 });
    tone(ctx, m, 'triangle', hz(low) * 2, t, dur, 0.4, { sustain: 0.9 });
    for (const n of chord) tone(ctx, m, 'square', hz(n), t, dur, 0.12, { sustain: 0.9 });
    kick(ctx, m, t);
    hit(ctx, m, noise, t, 1.0, 0.45, 4000);
  };

  const CUES = {
    // Champion crowned: triplet pickup, then the A minor tune flips to A major
    champion(ctx, dest, t0) {
      const { m, noise } = cueSetup(ctx, dest);
      const b = (x) => t0 + x * BEAT;
      const tri = 1 / 3;
      ['E5', 'E5', 'E5'].forEach((n, i) => {
        lead(ctx, m, n, b(i * tri), tri);
        hit(ctx, m, noise, b(i * tri), 0.08, 0.3 + i * 0.1, 1500);
      });
      lead(ctx, m, 'A5', b(1), 1);
      bounce(ctx, m, 'A2', b(1), 2);
      kick(ctx, m, b(1));
      hit(ctx, m, noise, b(1), 0.5, 0.35, 4000);
      lead(ctx, m, 'E5', b(2), 0.5);
      lead(ctx, m, 'A5', b(2.5), 0.5);
      bounce(ctx, m, 'E2', b(2), 2);
      hit(ctx, m, noise, b(2), 0.12, 0.5, 1500);
      lead(ctx, m, 'C#6', b(3), 3, { vibrato: true });
      finish(ctx, m, noise, b(3), 3, 'A1', ['C#5', 'E5']);
      return 6 * BEAT;
    },

    // Playoffs begin: climbs up and hangs on G#, the note that wants to go home
    playoffs(ctx, dest, t0) {
      const { m, noise } = cueSetup(ctx, dest);
      const b = (x) => t0 + x * BEAT;
      ['A4', 'C5', 'E5', 'A5'].forEach((n, i) => lead(ctx, m, n, b(i * 0.5), 0.5));
      bounce(ctx, m, 'A2', b(0), 4);
      kick(ctx, m, b(0));
      hit(ctx, m, noise, b(1), 0.12, 0.5, 1500);
      lead(ctx, m, 'G#5', b(2), 2.5, { vibrato: true });
      tone(ctx, m, 'triangle', hz('E2'), b(2), 2.5 * BEAT, 0.7, { sustain: 0.9 });
      tone(ctx, m, 'square', hz('B4'), b(2), 2.5 * BEAT, 0.12, { sustain: 0.9 });
      kick(ctx, m, b(2));
      for (let i = 0; i < 6; i++) hit(ctx, m, noise, b(2 + i * 0.25), 0.06, 0.15 + i * 0.05, 2500);
      return 4.5 * BEAT;
    },

    // New season tip-off: the jingle's first bar, cut short
    tipoff(ctx, dest, t0) {
      const { m, noise } = cueSetup(ctx, dest);
      const b = (x) => t0 + x * BEAT;
      lead(ctx, m, 'A4', b(0), 1);
      lead(ctx, m, 'C5', b(1), 0.5);
      lead(ctx, m, 'E5', b(1.5), 0.5);
      bounce(ctx, m, 'A2', b(0), 4);
      kick(ctx, m, b(0));
      hit(ctx, m, noise, b(1), 0.12, 0.5, 1500);
      lead(ctx, m, 'A5', b(2), 0.5);
      tone(ctx, m, 'triangle', hz('A2'), b(2), 0.5 * BEAT, 0.7);
      kick(ctx, m, b(2));
      hit(ctx, m, noise, b(2), 0.5, 0.35, 4000);
      return 3 * BEAT;
    },

    // Scandal: two stabs, then a low diminished chord that hangs
    scandal(ctx, dest, t0) {
      const { m, noise } = cueSetup(ctx, dest);
      const b = (x) => t0 + x * BEAT;
      for (const x of [0, 0.75]) {
        tone(ctx, m, 'square', hz('A4'), b(x), 0.35 * BEAT, 0.32);
        tone(ctx, m, 'square', hz('A3'), b(x), 0.35 * BEAT, 0.18);
        tone(ctx, m, 'triangle', hz('A1'), b(x), 0.35 * BEAT, 0.7);
        kick(ctx, m, b(x));
      }
      lead(ctx, m, 'F4', b(1.75), 3.5, { vibrato: true });
      tone(ctx, m, 'square', hz('G#3'), b(1.75), 3.5 * BEAT, 0.14, { sustain: 0.9 });
      tone(ctx, m, 'square', hz('B3'), b(1.75), 3.5 * BEAT, 0.14, { sustain: 0.9 });
      tone(ctx, m, 'triangle', hz('F1'), b(1.75), 3.5 * BEAT, 0.8, { sustain: 0.9 });
      kick(ctx, m, b(1.75));
      hit(ctx, m, noise, b(1.75), 1.3, 0.5, 3000);
      return 5.25 * BEAT;
    },

    // Rival league: a bass line creeping down while the lead holds a tritone
    rival(ctx, dest, t0) {
      const { m, noise } = cueSetup(ctx, dest);
      const b = (x) => t0 + x * BEAT;
      ['A2', 'G#2', 'G2', 'F#2'].forEach((n, i) => {
        tone(ctx, m, 'triangle', hz(n), b(i), 0.45 * BEAT, 0.7);
        tone(ctx, m, 'triangle', hz(n) * 2, b(i + 0.5), 0.45 * BEAT, 0.5);
        kick(ctx, m, b(i));
        if (i % 2) hit(ctx, m, noise, b(i), 0.12, 0.45, 1500);
      });
      tone(ctx, m, 'square', hz('A4'), b(0), 2 * BEAT, 0.22, { sustain: 0.8 });
      tone(ctx, m, 'square', hz('D#5'), b(2), 2.5 * BEAT, 0.28, { sustain: 0.9, vibrato: true });
      tone(ctx, m, 'triangle', hz('D#2'), b(4), 2 * BEAT, 0.8, { sustain: 0.9 });
      tone(ctx, m, 'square', hz('A3'), b(4), 2 * BEAT, 0.12, { sustain: 0.9 });
      kick(ctx, m, b(4));
      hit(ctx, m, noise, b(4), 1.0, 0.4, 3000);
      return 6 * BEAT;
    },

    // Bad news (walkout, a team leaving town): wah, wah, wah, wahhh
    womp(ctx, dest, t0) {
      const { m } = cueSetup(ctx, dest);
      const b = (x) => t0 + x * BEAT;
      const notes = [['D#4', 1, 0.97], ['D4', 1, 0.97], ['C#4', 1, 0.97]];
      notes.forEach(([n, beats, bend], i) => {
        tone(ctx, m, 'square', hz(n), b(i), beats * BEAT * 0.95, 0.3, { bend, sustain: 0.7 });
        tone(ctx, m, 'triangle', hz(n) / 4, b(i), beats * BEAT * 0.95, 0.5, { bend });
      });
      tone(ctx, m, 'square', hz('C4'), b(3), 3 * BEAT, 0.3, { vibrato: true, sustain: 0.9 });
      tone(ctx, m, 'triangle', hz('C2'), b(3), 3 * BEAT, 0.6, { sustain: 0.9 });
      return 6 * BEAT;
    },
  };

  window.fbScheduleJingle = schedule;
  window.fbScheduleCue = (ctx, dest, t0, name) => CUES[name](ctx, dest, t0);
})();
