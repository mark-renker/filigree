/* synth.js — MPE-aware WebAudio voice bank for the Filigree playground.
 *
 * One voice per note, exactly like an MPE member channel:
 *   bend   (semitones, bipolar) -> per-voice detune at audio rate
 *   press  (0..1)               -> amplitude + filter cutoff + drive
 *   timbre (0..1, .5 centre)    -> filter cutoff + waveshape brightness
 *
 * The voice is a warm subtractive one: three detuned saws + a sine sub through
 * a resonant lowpass and a soft saturator, with a short algorithmic plate and a
 * tempo-locked delay send. No samples, no network, no dependencies.
 */
(function (global) {
  'use strict';

  var LOOKAHEAD = 0.65;      // seconds of notes scheduled ahead of the clock
  var TICK_MS = 60;
  var MAX_VOICES = 96;       // hard polyphony ceiling; oldest voice is stolen

  // ── curve helpers (mirror ir.Curve.value_at exactly) ────────────────────
  function valueAt(points, beat) {
    if (!points || !points.length) return 0;
    if (beat <= points[0][0]) return points[0][1];
    var last = points[points.length - 1];
    if (beat >= last[0]) return last[1];
    var lo = 0, hi = points.length - 1;
    while (lo + 1 < hi) {
      var mid = (lo + hi) >> 1;
      if (points[mid][0] <= beat) lo = mid; else hi = mid;
    }
    var a = points[lo], b = points[hi];
    if (b[0] === a[0]) return b[1];
    var f = (beat - a[0]) / (b[0] - a[0]);
    return a[1] + f * (b[1] - a[1]);
  }

  function sampleLane(points, start, dur, n, dflt) {
    var arr = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      var beat = start + dur * (i / (n - 1));
      arr[i] = points && points.length ? valueAt(points, beat) : dflt;
    }
    return arr;
  }

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  // ── shared nodes ────────────────────────────────────────────────────────
  function makeReverbIR(ctx, seconds, decay) {
    var rate = ctx.sampleRate;
    var len = Math.floor(rate * seconds);
    var buf = ctx.createBuffer(2, len, rate);
    for (var c = 0; c < 2; c++) {
      var d = buf.getChannelData(c);
      var seed = c === 0 ? 1234567 : 7654321;
      for (var i = 0; i < len; i++) {
        // deterministic LCG noise so the plate is identical every session
        seed = (seed * 1103515245 + 12345) & 0x7fffffff;
        var r = (seed / 0x7fffffff) * 2 - 1;
        var t = i / len;
        var env = Math.pow(1 - t, decay);
        // early build-up so it reads as a room rather than a burst
        env *= Math.min(1, t * 60);
        d[i] = r * env;
      }
    }
    return buf;
  }

  function makeSatCurve() {
    var n = 1024, curve = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      var x = (i / (n - 1)) * 2 - 1;
      curve[i] = Math.tanh(x * 1.9) * 0.86;
    }
    return curve;
  }

  // ── synth ───────────────────────────────────────────────────────────────
  function Synth() {
    this.ctx = null;
    this.score = null;
    this.tempo = 120;
    this.playing = false;
    this.startBeat = 0;
    this.startTime = 0;
    this.endBeat = 0;
    this.loop = true;
    this.volume = 0.72;
    this.staveGain = {};
    this.stavePan = {};
    this.mute = {};
    this.solo = {};
    this._queue = [];
    this._qi = 0;
    this._timer = null;
    this._live = [];
    this.onNote = null;
  }

  Synth.prototype.ensure = function () {
    if (this.ctx) return this.ctx;
    var AC = global.AudioContext || global.webkitAudioContext;
    var ctx = this.ctx = new AC();

    this.master = ctx.createGain();
    this.master.gain.value = this.volume;

    // A limiter, not a mild bus compressor: 40 staves x many voices must not be
    // able to clip the destination, so this brick-walls instead of gently
    // squeezing (ratio 4 / knee 12 dB let peaks straight through).
    this.limiter = ctx.createDynamicsCompressor();
    this.limiter.threshold.value = -6;
    this.limiter.knee.value = 0;
    this.limiter.ratio.value = 20;
    this.limiter.attack.value = 0.003;
    this.limiter.release.value = 0.1;

    // gentle high shelf cut so the saw stack stays warm
    this.tone = ctx.createBiquadFilter();
    this.tone.type = 'highshelf';
    this.tone.frequency.value = 5200;
    this.tone.gain.value = -4.5;

    this.dry = ctx.createGain(); this.dry.gain.value = 0.92;

    this.verb = ctx.createConvolver();
    this.verb.buffer = makeReverbIR(ctx, 1.9, 2.6);
    this.verbSend = ctx.createGain(); this.verbSend.gain.value = 0.26;
    this.verbRet = ctx.createGain(); this.verbRet.gain.value = 0.9;
    this.verbLP = ctx.createBiquadFilter();
    this.verbLP.type = 'lowpass'; this.verbLP.frequency.value = 3400;

    this.delay = ctx.createDelay(2.0);
    this.delay.delayTime.value = 0.375;
    this.delayFb = ctx.createGain(); this.delayFb.gain.value = 0.3;
    this.delayLP = ctx.createBiquadFilter();
    this.delayLP.type = 'lowpass'; this.delayLP.frequency.value = 2600;
    this.delaySend = ctx.createGain(); this.delaySend.gain.value = 0.16;
    this.delayRet = ctx.createGain(); this.delayRet.gain.value = 0.62;

    this.bus = ctx.createGain(); this.bus.gain.value = 1;

    this.bus.connect(this.dry);
    this.bus.connect(this.verbSend);
    this.bus.connect(this.delaySend);

    this.verbSend.connect(this.verb);
    this.verb.connect(this.verbLP);
    this.verbLP.connect(this.verbRet);

    this.delaySend.connect(this.delay);
    this.delay.connect(this.delayLP);
    this.delayLP.connect(this.delayFb);
    this.delayFb.connect(this.delay);
    this.delayLP.connect(this.delayRet);

    this.dry.connect(this.tone);
    this.verbRet.connect(this.tone);
    this.delayRet.connect(this.tone);
    this.tone.connect(this.limiter);
    this.limiter.connect(this.master);
    this.master.connect(ctx.destination);

    this.satCurve = makeSatCurve();

    // Voices are reaped on their own heartbeat, not only while the transport is
    // running: auditioning notes with the transport stopped used to leak an
    // 8-node graph per click, for the life of the page.
    var self = this;
    if (!this._reaper) {
      this._reaper = setInterval(function () { self._reap(); }, 250);
    }
    return ctx;
  };

  /** Free the WebAudio graph of every voice whose tail has finished. */
  Synth.prototype._reap = function () {
    if (!this.ctx) return;
    var now = this.ctx.currentTime, live = [];
    for (var i = 0; i < this._live.length; i++) {
      var r = this._live[i];
      if (r.until > now) live.push(r);
      else r.dispose();
    }
    this._live = live;
  };

  Synth.prototype.setVolume = function (v) {
    this.volume = v;
    if (this.ctx) this.master.gain.setTargetAtTime(v, this.ctx.currentTime, 0.02);
  };

  Synth.prototype.load = function (score) {
    this.score = score;
    this.tempo = score.tempo || 120;
    this.endBeat = score.durationBeats || 0;
    var self = this;
    if (this.ctx) this.delay.delayTime.value = (60 / this.tempo) * 0.75;
    (score.staves || []).forEach(function (s, i) {
      if (!(s.name in self.mute)) self.mute[s.name] = false;
      if (!(s.name in self.solo)) self.solo[s.name] = false;
      self.stavePan[s.name] = [-0.18, 0.14, 0.0][i % 3];
    });
    this._build();
  };

  Synth.prototype._audible = function (name) {
    var anySolo = false, self = this;
    Object.keys(this.solo).forEach(function (k) { if (self.solo[k]) anySolo = true; });
    if (anySolo) return !!this.solo[name] && !this.mute[name];
    return !this.mute[name];
  };

  Synth.prototype._build = function () {
    var q = [];
    var staves = (this.score && this.score.staves) || [];
    for (var si = 0; si < staves.length; si++) {
      var st = staves[si];
      for (var ni = 0; ni < st.notes.length; ni++) {
        q.push({ n: st.notes[ni], stave: st.name, si: si });
      }
    }
    q.sort(function (a, b) { return a.n.start - b.n.start; });
    this._queue = q;
  };

  // ── the voice ───────────────────────────────────────────────────────────
  Synth.prototype._voice = function (item, when, beatOffset) {
    var ctx = this.ctx, n = item.n;
    // Polyphony ceiling.  40 staves of simultaneous notes would otherwise build
    // hundreds of 8-node voices and stall the audio thread; steal the oldest.
    if (this._live.length >= MAX_VOICES) {
      var victim = this._live.shift();
      try { victim.env.gain.cancelScheduledValues(ctx.currentTime); } catch (e) { /* noop */ }
      try {
        victim.env.gain.setValueAtTime(victim.env.gain.value, ctx.currentTime);
        victim.env.gain.linearRampToValueAtTime(0.00001, ctx.currentTime + 0.02);
      } catch (e2) { /* noop */ }
      for (var vi = 0; vi < victim.oscs.length; vi++) {
        try { victim.oscs[vi].stop(ctx.currentTime + 0.04); } catch (e3) { /* noop */ }
      }
      setTimeout(function () { victim.dispose(); }, 200);
    }
    var tempo = this.tempo;
    var spb = 60 / tempo;
    var dur = Math.max(0.06, n.dur * spb);
    var rel = clamp(dur * 0.35, 0.09, 0.5);
    var vel = (n.velocity || 90) / 127;

    var cur = n.curves || {};
    // ~160 control points per second, so a 200-beat note is not reduced to 220
    // samples (which turned a smooth bend into audible stair-steps).
    var N = Math.max(24, Math.min(8192, Math.round(dur * 160)));
    var bend = sampleLane(cur.bend, n.start, n.dur, N, 0);
    var press = sampleLane(cur.press, n.start, n.dur, N, 0.7);
    var timb = sampleLane(cur.timbre, n.start, n.dur, N, 0.5);

    var freq = 440 * Math.pow(2, (n.pitch - 69) / 12);
    var baseCents = (n.detune || 0) * 100;

    // ── detune curve, in cents, at audio rate ──
    var cents = new Float32Array(N);
    for (var i = 0; i < N; i++) cents[i] = baseCents + bend[i] * 100;

    // ── amplitude: attack/decay shaped by the press lane ──
    var amp = new Float32Array(N);
    var peak = 0.16 + 0.3 * vel * vel;
    var atk = clamp(0.012 + (1 - vel) * 0.05, 0.008, 0.09);
    for (i = 0; i < N; i++) {
      var t = (i / (N - 1)) * dur;
      var a = t < atk ? (t / atk) : 1;
      var body = 0.3 + 0.7 * clamp(press[i], 0, 1);
      var tail = 1;
      var fromEnd = dur - t;
      if (fromEnd < rel) tail = Math.pow(fromEnd / rel, 1.4);
      amp[i] = peak * a * body * tail + 0.00001;
    }

    // ── filter: timbre opens it, press pushes it ──
    var cut = new Float32Array(N);
    for (i = 0; i < N; i++) {
      var tb = clamp(timb[i], 0, 1);
      var pr = clamp(press[i], 0, 1);
      var f = 200 + 4600 * Math.pow(0.18 + 0.82 * tb, 1.7) * (0.45 + 0.62 * pr);
      cut[i] = clamp(f * (0.7 + 0.5 * vel), 120, 11000);
    }

    // ── drive from press+timbre ──
    var drv = new Float32Array(N);
    for (i = 0; i < N; i++) {
      drv[i] = 0.5 + 1.5 * clamp(press[i], 0, 1) * (0.5 + 0.6 * clamp(timb[i], 0, 1));
    }

    var mix = ctx.createGain(); mix.gain.value = 0.32;
    var filt = ctx.createBiquadFilter();
    filt.type = 'lowpass';
    filt.Q.value = 3.1 + 3.4 * clamp(timb[0], 0, 1);
    var pre = ctx.createGain();
    var shaper = ctx.createWaveShaper();
    shaper.curve = this.satCurve;
    shaper.oversample = '2x';
    var post = ctx.createGain(); post.gain.value = 1;
    var env = ctx.createGain(); env.gain.value = 0.00001;
    var pan = ctx.createStereoPanner();
    var p = this.stavePan[item.stave] || 0;
    // small per-note spread keyed off pitch so chords open up
    pan.pan.value = clamp(p + ((n.pitch % 7) - 3) * 0.035, -0.85, 0.85);

    mix.connect(filt); filt.connect(pre); pre.connect(shaper);
    shaper.connect(post); post.connect(env); env.connect(pan); pan.connect(this.bus);

    var unison = [
      { type: 'sawtooth', c: 0, g: 1.0, oct: 1 },
      { type: 'sawtooth', c: +7.5, g: 0.72, oct: 1 },
      { type: 'sawtooth', c: -9.0, g: 0.72, oct: 1 },
      { type: 'triangle', c: +2.0, g: 0.55, oct: 0.5 }
    ];
    var oscs = [];
    for (i = 0; i < unison.length; i++) {
      var u = unison[i];
      var o = ctx.createOscillator();
      o.type = u.type;
      o.frequency.value = freq * u.oct * Math.pow(2, u.c / 1200);
      var g = ctx.createGain(); g.gain.value = u.g;
      o.connect(g); g.connect(mix);
      // the bend curve rides the detune param -> genuinely per-note pitch
      try {
        o.detune.setValueCurveAtTime(cents, when, dur);
      } catch (e) {
        o.detune.setValueAtTime(cents[0], when);
        for (var k = 1; k < N; k += 2) {
          o.detune.linearRampToValueAtTime(cents[k], when + dur * (k / (N - 1)));
        }
      }
      o.start(when);
      o.stop(when + dur + rel + 0.05);
      oscs.push(o);
    }

    function curveOn(param, arr, floor) {
      try {
        param.setValueCurveAtTime(arr, when, dur);
      } catch (e) {
        param.setValueAtTime(arr[0], when);
        for (var j = 1; j < arr.length; j += 2) {
          param.linearRampToValueAtTime(Math.max(floor, arr[j]), when + dur * (j / (arr.length - 1)));
        }
      }
    }
    curveOn(env.gain, amp, 0.00001);
    curveOn(filt.frequency, cut, 60);
    curveOn(pre.gain, drv, 0.05);

    // Release tail: a real linear ramp that REACHES ~0 before the oscillators
    // are stopped.  setTargetAtTime is exponential and never arrives, so
    // osc.stop() used to cut a still-audible tail and click.
    var tEnd = when + dur;
    env.gain.setValueAtTime(amp[N - 1], tEnd);
    env.gain.linearRampToValueAtTime(0.00001, tEnd + rel);
    filt.frequency.setTargetAtTime(Math.max(160, cut[N - 1] * 0.45), tEnd, rel * 0.5);

    var nodes = [mix, filt, pre, shaper, post, env, pan];
    var rec = {
      oscs: oscs, env: env, until: tEnd + rel + 0.1, item: item,
      // Explicitly tear the voice's graph down.  Without this every note leaked
      // seven nodes plus its oscillators, so a long score slowly starved the
      // audio thread and the tab's memory.
      dispose: function () {
        if (this._dead) return;
        this._dead = true;
        for (var i = 0; i < this.oscs.length; i++) {
          try { this.oscs[i].disconnect(); } catch (e) { /* gone */ }
        }
        for (i = 0; i < nodes.length; i++) {
          try { nodes[i].disconnect(); } catch (e) { /* gone */ }
        }
      }
    };
    this._live.push(rec);
    if (this.onNote) this.onNote(item, when);
  };

  // ── transport ───────────────────────────────────────────────────────────
  Synth.prototype.play = function (fromBeat) {
    var ctx = this.ensure();
    if (ctx.state === 'suspended') ctx.resume();
    this.stopVoices();
    this.delay.delayTime.value = (60 / this.tempo) * 0.75;
    this.startBeat = fromBeat || 0;
    this.startTime = ctx.currentTime + 0.06;
    this.playing = true;
    this._qi = 0;
    var q = this._queue;
    while (this._qi < q.length && q[this._qi].n.start < this.startBeat) this._qi++;
    var self = this;
    this._timer = setInterval(function () { self._tick(); }, TICK_MS);
    this._tick();
  };

  Synth.prototype._tick = function () {
    if (!this.playing) return;
    var ctx = this.ctx, spb = 60 / this.tempo;
    var nowBeat = this.beat();
    var horizon = nowBeat + LOOKAHEAD / spb;
    var q = this._queue;

    while (this._qi < q.length && q[this._qi].n.start <= horizon) {
      var item = q[this._qi++];
      if (!this._audible(item.stave)) continue;
      var when = this.startTime + (item.n.start - this.startBeat) * spb;
      // A note whose start has just slipped past the clock (a slow frame, a big
      // score) is played immediately rather than silently dropped.
      if (when < ctx.currentTime + 0.005) when = ctx.currentTime + 0.005;
      this._voice(item, when, this.startBeat);
    }

    this._reap();

    var tail = 0.9;
    if (nowBeat > this.endBeat + tail) {
      if (this.loop) {
        this.startBeat = 0;
        this.startTime = ctx.currentTime + 0.02;
        this._qi = 0;
      } else {
        this.stop();
      }
    }
  };

  Synth.prototype.beat = function () {
    if (!this.playing || !this.ctx) return this.startBeat;
    return this.startBeat + (this.ctx.currentTime - this.startTime) * (this.tempo / 60);
  };

  Synth.prototype.stopVoices = function () {
    if (!this.ctx) return;
    var t = this.ctx.currentTime;
    var self = this;
    var dying = this._live;
    this._live = [];
    for (var i = 0; i < dying.length; i++) {
      var r = dying[i];
      // Each step gets its own try: a throw from cancelScheduledValues used to
      // skip the osc.stop() calls entirely, leaving voices ringing forever.
      try { r.env.gain.cancelScheduledValues(t); } catch (e) { /* noop */ }
      try {
        r.env.gain.setValueAtTime(r.env.gain.value, t);
        r.env.gain.linearRampToValueAtTime(0.00001, t + 0.03);
      } catch (e2) { /* noop */ }
      for (var j = 0; j < r.oscs.length; j++) {
        try { r.oscs[j].stop(t + 0.05); } catch (e3) { /* already stopped */ }
      }
      // free the graph once the 30 ms fade has certainly finished
      (function (rec) { setTimeout(function () { rec.dispose(); }, 200); })(r);
    }
  };

  Synth.prototype.stop = function () {
    this.playing = false;
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
    this.stopVoices();
  };

  Synth.prototype.setMute = function (name, on) {
    this.mute[name] = !!on;
  };
  Synth.prototype.setSolo = function (name, on) {
    this.solo[name] = !!on;
  };

  /** Audition a single note on its own (used by the piano roll). */
  Synth.prototype.audition = function (note, staveName) {
    var ctx = this.ensure();
    if (ctx.state === 'suspended') ctx.resume();
    var clone = { n: note, stave: staveName || '', si: 0 };
    this._voice(clone, ctx.currentTime + 0.02, note.start);
  };

  global.FiligreeSynth = Synth;
  global.filigreeCurveValueAt = valueAt;
})(window);
