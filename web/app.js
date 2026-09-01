/* app.js — Filigree playground shell: transport, piano roll, chord ribbon,
 * diagnostics, and the compile bridge.
 *
 * Data contract: exactly `ir.Score.to_json()` (see src/filigree/ir.py).
 * Source of truth at boot is the bundled fixture, so the whole app works with
 * no backend at all; if `POST {base}/api/compile` answers, we switch to it.
 * base = window.FILIGREE_API || ''  (same origin by default).
 */
(function () {
  'use strict';

  var API = (typeof window.FILIGREE_API === 'string' ? window.FILIGREE_API : '') || '';
  var FIXTURE_JSON = 'fixtures/score.json';
  var FIXTURE_SRC = 'fixtures/source.fil';

  var RIBBON_H = 38, RULER_H = 18, PADL = 8, PADR = 24;
  var INSP_CANVAS_H = 88;
  var MAX_CANVAS_PX = 6e6;      // above this, stop multiplying by devicePixelRatio
  var PC_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
  var MODE_SHORT = { major: 'maj', minor: 'min', ionian: 'ion', dorian: 'dor',
    phrygian: 'phr', lydian: 'lyd', mixolydian: 'mix', aeolian: 'aeo',
    locrian: 'loc' };
  // 12 well-separated hues, so 40 staves are not 8-deep in one colour
  var HUES = [212, 272, 152, 32, 328, 188, 252, 96, 12, 302, 170, 52];
  var BLACK = { 1: 1, 3: 1, 6: 1, 8: 1, 10: 1 };

  var $ = function (id) { return document.getElementById(id); };
  var valueAt = window.filigreeCurveValueAt;

  // ── state ───────────────────────────────────────────────────────────────
  var S = {
    score: null,
    fixture: null,
    apiOnline: false,
    ppb: 46,           // pixels per beat
    rowH: 9,
    lo: 36, hi: 84,
    showCurves: true,
    sel: null,         // {note, stave, si}
    hover: null,
    dirty: false,
    autoZoom: true,
    autoRows: true,
    lastGood: null,
    stale: false,       // the roll no longer matches the source in the editor
    overlayDirty: true, // renderOverlay only runs when something actually moved
    bendRange: 2
  };

  var synth = new window.FiligreeSynth();
  var ed = null;

  // ── geometry ────────────────────────────────────────────────────────────
  function rows() { return S.hi - S.lo + 1; }
  function rollH() { return rows() * S.rowH; }
  function totalW() { return PADL + (S.score ? S.score.durationBeats : 32) * S.ppb + PADR; }
  function x2b(x) { return (x - PADL) / S.ppb; }
  function b2x(b) { return PADL + b * S.ppb; }
  function p2y(p) { return (S.hi - p) * S.rowH; }

  function dpr() { return window.devicePixelRatio || 1; }
  /** Device-pixel ratio, backed off on very large canvases so a 400-bar score
   *  cannot allocate hundreds of megabytes of backing store. */
  function dprFor(w, h) {
    var r = dpr();
    while (r > 1 && w * h * r * r > MAX_CANVAS_PX) r -= 0.5;
    return Math.max(1, r);
  }
  function fit(cv, w, h) {
    var r = dprFor(w, h);
    cv.width = Math.max(1, Math.round(w * r));
    cv.height = Math.max(1, Math.round(h * r));
    cv.style.width = w + 'px';
    cv.style.height = h + 'px';
    var g = cv.getContext('2d');
    g.setTransform(r, 0, 0, r, 0, 0);
    return g;
  }

  function staveHue(i) { return HUES[i % HUES.length]; }
  function staveCss(i, l, a) {
    return 'hsla(' + staveHue(i) + ',72%,' + (l || 62) + '%,' + (a === undefined ? 1 : a) + ')';
  }

  // ── score ingest ────────────────────────────────────────────────────────
  function pitchRange(score) {
    var lo = 127, hi = 0;
    (score.staves || []).forEach(function (st) {
      st.notes.forEach(function (n) {
        if (n.pitch < lo) lo = n.pitch;
        if (n.pitch > hi) hi = n.pitch;
      });
    });
    if (hi < lo) { lo = 48; hi = 72; }
    lo -= 2; hi += 2;
    while (hi - lo < 26) { hi++; lo--; }
    return [Math.max(0, lo), Math.min(127, hi)];
  }

  function noteCount(score) {
    var c = 0;
    (score.staves || []).forEach(function (s) { c += s.notes.length; });
    return c;
  }

  function setScore(score, label) {
    S.score = score;
    S.stale = false;
    S.bendRange = (typeof score.bendRange === 'number' && score.bendRange > 0)
      ? score.bendRange : 2;
    var r = pitchRange(score);
    S.lo = r[0]; S.hi = r[1];
    synth.load(score);
    $('mTempo').textContent = (Math.round(score.tempo * 10) / 10).toString();
    var k = score.key || { tonic: 0, mode: 'major' };
    $('mKey').textContent = PC_NAMES[k.tonic % 12] + ' ' + (MODE_SHORT[k.mode] || k.mode);
    $('mMeter').textContent = (score.meter || [4, 4]).join('/');
    $('mNotes').textContent = noteCount(score);
    document.title = 'Filigree — ' + (score.title || 'playground');
    var empty = noteCount(score) === 0;
    $('rollHost').classList.toggle('empty', empty);
    buildLegend();
    showDiagnostics(score.warnings || [], label, null, empty);
    S.sel = null;
    S.hover = null;
    layout();
  }

  /** How many bars of the score are actually on screen right now. */
  function updateRange() {
    var el = $('rollRange');
    if (!el || !S.score) return;
    var m = S.score.meter || [4, 4];
    var bpb = m[0] * (4 / m[1]);
    var total = Math.max(1, Math.ceil(S.score.durationBeats / bpb));
    var sc = $('rollScroll');
    var from = Math.floor(x2b(sc.scrollLeft) / bpb) + 1;
    var to = Math.min(total, Math.ceil(x2b(sc.scrollLeft + sc.clientWidth) / bpb));
    if (to < from) to = from;
    from = Math.max(1, Math.min(from, total));
    el.textContent = (to - from + 1 >= total)
      ? ('all ' + total + (total === 1 ? ' bar' : ' bars'))
      : ('bars ' + from + '–' + to + ' of ' + total);
  }

  // ── stave legend / mute / solo ───────────────────────────────────────────
  function buildLegend() {
    var host = $('staveLegend');
    host.innerHTML = '';
    (S.score.staves || []).forEach(function (st, i) {
      var el = document.createElement('span');
      el.className = 'stv';
      el.innerHTML =
        '<span class="sw" style="background:' + staveCss(i, 58) + '" aria-hidden="true"></span>' +
        '<span class="nm"></span>' +
        '<span class="cnt">' + st.notes.length + '</span>' +
        '<button type="button" class="mm" aria-pressed="false">M</button>' +
        '<button type="button" class="ss" aria-pressed="false">S</button>';
      el.querySelector('.nm').textContent = st.name;
      var mm = el.querySelector('.mm'), ss = el.querySelector('.ss');
      mm.title = 'mute ' + st.name;
      mm.setAttribute('aria-label', 'Mute stave ' + st.name);
      ss.title = 'solo ' + st.name;
      ss.setAttribute('aria-label', 'Solo stave ' + st.name);
      mm.onclick = function () {
        synth.setMute(st.name, !synth.mute[st.name]);
        refreshLegend(); renderRoll();
      };
      ss.onclick = function () {
        synth.setSolo(st.name, !synth.solo[st.name]);
        refreshLegend(); renderRoll();
      };
      host.appendChild(el);
    });
    // the legend scrolls horizontally rather than shoving the zoom controls off
    // the right edge; say out loud how many staves there are.
    var n = (S.score.staves || []).length;
    host.setAttribute('aria-label', 'Staves (' + n + '): mute and solo');
    if (n > 4) {
      var more = document.createElement('span');
      more.className = 'stvMore';
      more.textContent = n + ' staves →';
      more.title = 'the stave list scrolls';
      host.appendChild(more);
    }
    refreshLegend();
  }

  function refreshLegend() {
    var els = $('staveLegend').children;
    (S.score.staves || []).forEach(function (st, i) {
      var el = els[i]; if (!el) return;
      var mm = el.querySelector('.mm'), ss = el.querySelector('.ss');
      if (!mm || !ss) return;
      mm.setAttribute('aria-pressed', synth.mute[st.name] ? 'true' : 'false');
      ss.setAttribute('aria-pressed', synth.solo[st.name] ? 'true' : 'false');
      el.className = 'stv' + (synth._audible(st.name) ? '' : ' muted');
    });
  }

  // ── diagnostics ─────────────────────────────────────────────────────────
  function showDiagnostics(warnings, extra, forceSev, isEmptyDoc) {
    var host = $('diag');
    host.innerHTML = '';
    var items = [];
    if (extra) items.push({ sev: 'note', line: 0, col: 0, msg: extra });
    (warnings || []).forEach(function (raw) {
      // accept plain strings (score.warnings) or {text, sev} (API errors+warnings)
      var w = (raw && raw.text !== undefined) ? raw.text : raw;
      var m = /^([^\s:]+):(\d+):(\d+):\s*(.*)$/.exec(w);
      var sev = (raw && raw.sev) || forceSev || (/error/i.test(w) ? 'error' : 'warn');
      if (raw && raw.line) {
        // collectErrors() already carries a structured position from the
        // backend's {line, col}; trust it over re-parsing the prose.
        items.push({ sev: sev, line: +raw.line, col: +(raw.col || 1), msg: w });
      } else if (m) {
        items.push({ sev: sev, line: +m[2], col: +m[3], msg: m[4] });
      } else {
        items.push({ sev: sev, line: 0, col: 0, msg: w });
      }
    });

    var bad = {};
    items.forEach(function (it) { if (it.line) bad[it.line] = 1; });
    if (ed) ed.setBadLines(bad);

    var nProblems = items.filter(function (i) { return i.sev !== 'note'; }).length;
    var chip = $('diagCount');
    chip.textContent = nProblems;
    chip.className = 'chip' + (items.some(function (i) { return i.sev === 'error'; }) ? ' bad' : '');

    if (!items.length) {
      host.innerHTML = isEmptyDoc
        ? '<div class="empty"><b>Nothing compiled yet.</b> This document has no notes — ' +
          'write a <code>stave</code> block with a <code>notes</code> lane and hit compile.</div>'
        : '<div class="empty">No warnings. Harmony, lanes and gestures resolved cleanly.</div>';
      return;
    }
    items.forEach(function (it) {
      var jump = !!it.line;
      var row = document.createElement(jump ? 'button' : 'div');
      if (jump) row.type = 'button';
      row.className = 'row ' + (it.sev === 'error' ? 'e' : (it.sev === 'note' ? 'n' : 'w')) +
        (jump ? '' : ' static');
      row.innerHTML =
        '<span class="sev">' + it.sev + '</span>' +
        '<span class="loc">' + (jump ? it.line + ':' + it.col : '—') + '</span>' +
        '<span class="msg"></span>';
      row.querySelector('.msg').textContent = it.msg;
      if (jump) {
        row.setAttribute('aria-label', it.sev + ' at line ' + it.line + ' column ' + it.col +
          ': ' + it.msg + '. Activate to jump there.');
        row.onclick = function () { ed.gotoLine(it.line, it.col); };
      }
      host.appendChild(row);
    });
  }

  // ── piano keys column ───────────────────────────────────────────────────
  function renderKeys() {
    var h = RIBBON_H + RULER_H + rollH();
    var g = fit($('cKeys'), 46, h);
    g.clearRect(0, 0, 46, h);
    g.fillStyle = '#0c0f13'; g.fillRect(0, 0, 46, h);

    g.fillStyle = '#9aa6b4';
    g.font = '10px ui-monospace,monospace';
    g.textAlign = 'left';
    g.fillText('chord', 4, 14);
    g.fillStyle = '#8d99a7';
    g.fillText('bar', 6, RIBBON_H + 12);

    var top = RIBBON_H + RULER_H;
    for (var p = S.lo; p <= S.hi; p++) {
      var y = top + p2y(p);
      var isB = BLACK[p % 12];
      g.fillStyle = isB ? '#0f1318' : '#161b21';
      g.fillRect(0, y, 46, S.rowH - 0.5);
      if (p % 12 === 0) {
        g.fillStyle = '#8b98a8';
        g.font = (S.rowH >= 9 ? 9 : 8) + 'px ui-monospace,monospace';
        g.fillText('C' + (Math.floor(p / 12) - 1), 3, y + S.rowH - 1.5);
        g.fillStyle = '#232b34';
        g.fillRect(0, y + S.rowH - 0.5, 46, 0.5);
      } else if (S.rowH >= 13) {
        g.fillStyle = '#8d99a7';
        g.font = '9px ui-monospace,monospace';
        g.fillText(PC_NAMES[p % 12], 3, y + S.rowH - 2);
      }
    }
    g.fillStyle = '#1e242c'; g.fillRect(45, 0, 1, h);
  }

  // ── chord ribbon ────────────────────────────────────────────────────────
  function allChords() {
    if (!S.score) return [];
    var seen = {}, out = [];
    (S.score.staves || []).forEach(function (st) {
      (st.chords || []).forEach(function (c) {
        var k = c.start + '|' + c.symbol;
        if (seen[k]) return;
        seen[k] = 1; out.push(c);
      });
    });
    out.sort(function (a, b) { return a.start - b.start; });
    return out;
  }

  function renderRibbon() {
    var w = totalW();
    var g = fit($('cRibbon'), w, RIBBON_H);
    g.clearRect(0, 0, w, RIBBON_H);
    g.fillStyle = '#0d1116'; g.fillRect(0, 0, w, RIBBON_H);
    g.fillStyle = '#1e242c'; g.fillRect(0, RIBBON_H - 1, w, 1);

    // Two staves may declare DIFFERENT harmony at the same beat.  allChords()
    // only de-duplicates identical symbols, so divergent ones used to be painted
    // on top of each other and came out as unreadable mush.  Group by start and
    // show the disagreement explicitly instead.
    var byStart = {}, order = [];
    allChords().forEach(function (c) {
      var k = c.start.toFixed(4);
      if (!byStart[k]) { byStart[k] = { start: c.start, dur: c.dur, all: [] }; order.push(k); }
      byStart[k].dur = Math.max(byStart[k].dur, c.dur);
      byStart[k].all.push(c);
    });
    order.map(function (k) {
      var grp = byStart[k];
      var head = grp.all[0];
      var syms = [];
      grp.all.forEach(function (c) {
        if (syms.indexOf(c.symbol) < 0) syms.push(c.symbol);
      });
      return {
        start: grp.start, dur: grp.dur, rootPc: head.rootPc, quality: head.quality,
        guideTones: head.guideTones,
        symbol: syms.length > 1 ? syms.join(' / ') : syms[0],
        split: syms.length > 1
      };
    }).forEach(function (c, i) {
      var x = b2x(c.start), cw = Math.max(10, c.dur * S.ppb);
      g.save();
      g.beginPath(); g.rect(x, 0, cw - 1.5, RIBBON_H - 1); g.clip();

      g.fillStyle = i % 2 ? 'rgba(242,163,199,0.05)' : 'rgba(242,163,199,0.095)';
      g.fillRect(x, 0, cw - 1.5, RIBBON_H - 1);
      g.fillStyle = '#333b45'; g.fillRect(x, 2, 1, RIBBON_H - 5);

      g.textAlign = 'left';
      g.fillStyle = '#fbcfe4';
      // No synthetic bold here: a weighted `ui-monospace` resolves to a face with
      // no glyph coverage in some engines and every chord symbol came out as
      // tofu boxes.  Size carries the emphasis instead.
      g.font = '13px ui-monospace,monospace';
      var sym = c.symbol;
      // never let a symbol bleed past its own chord cell
      while (sym.length > 3 && g.measureText(sym).width > cw - 9) sym = sym.slice(0, -1);
      if (sym !== c.symbol) sym = sym.slice(0, -1) + '\u2026';
      g.fillText(sym, x + 5, 15);

      // second line: quality, then the guide tones, marked
      g.font = '9px ui-monospace,monospace';
      var rootName = PC_NAMES[(c.rootPc || 0) % 12];
      var qual = rootName + (c.quality ? ' ' + c.quality : '');
      g.fillStyle = '#9aa6b4';
      g.fillText(qual, x + 5, 29);
      var gx = x + 5 + g.measureText(qual).width + 7;
      var gt = (c.guideTones || []);
      if (gt.length && gx < x + cw - 22) {
        g.fillStyle = '#6ee7d0';
        g.beginPath(); g.arc(gx + 1.5, 25.5, 1.8, 0, 6.284); g.fill();
        g.fillStyle = '#8ef0dc';
        g.fillText(gt.map(function (pc) { return PC_NAMES[pc % 12]; }).join(' '), gx + 6, 29);
      }
      g.restore();
    });
  }

  // ── bar / beat ruler ────────────────────────────────────────────────────
  function renderRuler() {
    var w = totalW(), beats = S.score ? S.score.durationBeats : 32;
    var m = (S.score && S.score.meter) || [4, 4];
    var bpb = m[0] * (4 / m[1]);      // quarter notes per bar
    var g = fit($('cRuler'), w, RULER_H);
    g.clearRect(0, 0, w, RULER_H);
    g.fillStyle = '#0a0c0f'; g.fillRect(0, 0, w, RULER_H);
    g.font = '10px ui-monospace,monospace';
    g.textAlign = 'left';
    // a beat step that keeps the ruler readable however far out we are zoomed
    var step = S.ppb >= 10 ? 1 : Math.max(1, Math.round(bpb * Math.ceil(10 / Math.max(1, S.ppb * bpb))));
    for (var b = 0; b <= beats + 0.001; b += step) {
      var x = b2x(b);
      var isBar = Math.abs((b / bpb) - Math.round(b / bpb)) < 1e-6;
      g.fillStyle = isBar ? '#5b6673' : '#39424e';
      g.fillRect(x, isBar ? 4 : 10, 1, RULER_H - (isBar ? 5 : 11));
      if (isBar && (S.ppb * bpb > 26)) {
        g.fillStyle = '#aab6c4';
        g.fillText(String(Math.round(b / bpb) + 1), x + 3, 11);
      } else if (!isBar && S.ppb > 34) {
        g.fillStyle = '#8d99a7';
        g.fillText(String((b % bpb) + 1), x + 2, 9);
      }
    }
    g.fillStyle = '#1e242c'; g.fillRect(0, RULER_H - 1, w, 1);
  }

  // ── the roll ────────────────────────────────────────────────────────────
  function renderRoll() {
    if (!S.score) return;
    var w = totalW(), h = rollH();
    var g = fit($('cRoll'), w, h);
    var m = S.score.meter || [4, 4];
    var bpb = m[0] * (4 / m[1]);
    var beats = S.score.durationBeats;

    g.clearRect(0, 0, w, h);
    g.fillStyle = '#0a0c0f'; g.fillRect(0, 0, w, h);

    // row shading
    for (var p = S.lo; p <= S.hi; p++) {
      var y = p2y(p);
      g.fillStyle = BLACK[p % 12] ? '#0c1014' : '#101519';
      g.fillRect(0, y, w, S.rowH - 0.4);
      if (p % 12 === 0) { g.fillStyle = '#1a2027'; g.fillRect(0, y + S.rowH - 0.4, w, 0.6); }
    }

    // faint per-stave register bands: turns dead vertical space into structure
    (S.score.staves || []).forEach(function (st, si) {
      var lo = 127, hi = 0;
      st.notes.forEach(function (n) { if (n.pitch < lo) lo = n.pitch; if (n.pitch > hi) hi = n.pitch; });
      if (hi < lo) return;
      var yTop = p2y(hi), yBot = p2y(lo) + S.rowH;
      var grd = g.createLinearGradient(0, yTop, 0, yBot);
      grd.addColorStop(0, 'hsla(' + staveHue(si) + ',70%,55%,0.085)');
      grd.addColorStop(0.5, 'hsla(' + staveHue(si) + ',70%,55%,0.03)');
      grd.addColorStop(1, 'hsla(' + staveHue(si) + ',70%,55%,0.085)');
      g.fillStyle = grd;
      g.fillRect(0, yTop, w, yBot - yTop);
      g.fillStyle = 'hsla(' + staveHue(si) + ',70%,60%,0.22)';
      g.fillRect(0, yTop - 0.5, w, 0.7);
      g.fillRect(0, yBot - 0.5, w, 0.7);
      g.save();
      g.font = '8px ui-monospace,monospace';
      g.fillStyle = 'hsla(' + staveHue(si) + ',60%,75%,0.6)';
      g.fillText(st.name, 3, yTop + 8);
      g.restore();
    });

    // chord spans + guide-tone rows.  The dashed guide tones are the single most
    // expensive thing on the canvas, so they are budgeted: on a long score we
    // draw the chord band only.
    var chords = allChords();
    var guideBudget = 2600;
    chords.forEach(function (c) {
      var x = b2x(c.start), cw = c.dur * S.ppb;
      g.fillStyle = 'rgba(242,163,199,0.028)';
      g.fillRect(x, 0, cw, h);
      if (cw < 6) return;
      (c.guideTones || []).forEach(function (pc) {
        for (var q = S.lo; q <= S.hi; q++) {
          if (q % 12 !== pc % 12) continue;
          if (guideBudget-- <= 0) return;
          var yy = p2y(q) + (S.rowH - 0.4) / 2;
          g.strokeStyle = 'rgba(110,231,208,0.16)';
          g.lineWidth = 1;
          g.setLineDash([2, 4]);
          g.beginPath(); g.moveTo(x + 1, yy); g.lineTo(x + cw - 2, yy); g.stroke();
          g.setLineDash([]);
        }
      });
    });

    // grid — never more lines than there are pixels to put them on
    var gstep = S.ppb >= 24 ? 0.5 : (S.ppb >= 8 ? 1 : bpb);
    for (var b = 0; b <= beats + 0.001; b += gstep) {
      var gx = Math.round(b2x(b)) + 0.5;
      var isBar = Math.abs((b / bpb) - Math.round(b / bpb)) < 1e-6;
      g.strokeStyle = isBar ? '#242c35' : (b % 1 === 0 ? '#181e25' : '#12171c');
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(gx, 0); g.lineTo(gx, h); g.stroke();
    }

    // notes, back-to-front by stave order
    (S.score.staves || []).forEach(function (st, si) {
      var audible = synth._audible(st.name);
      st.notes.forEach(function (n) { drawNote(g, n, si, audible); });
    });
  }

  /** The vertical full-scale, in semitones, used to draw one note's bend.
   *  Never smaller than 2 st (so small vibrato still reads) and never smaller
   *  than the note's own excursion (so nothing is silently clipped). Bounded by
   *  the score's `@bend-range`. */
  function noteBendScale(n) {
    var b = (n.curves || {}).bend;
    var mx = 0;
    if (b) for (var i = 0; i < b.length; i++) {
      var a = Math.abs(b[i][1]); if (a > mx) mx = a;
    }
    var sc = Math.max(2, mx * 1.06);
    return Math.min(sc, Math.max(2, S.bendRange));
  }

  function drawNote(g, n, si, audible) {
    var x = b2x(n.start), w = Math.max(2.5, n.dur * S.ppb - 1);
    var y = p2y(n.pitch), h = Math.max(3, S.rowH - 1.2);
    var hue = staveHue(si);
    var cur = n.curves || {};
    var press = cur.press, timb = cur.timbre, bend = cur.bend;
    var vel = (n.velocity || 90) / 127;
    var alphaScale = audible ? 1 : 0.28;

    // body: press (opacity) x timbre (hue shift) along the note.  One gradient
    // with a bounded number of stops, not one fillRect per horizontal pixel —
    // a 2000 px note used to cost 2000 draw calls.
    var stops = Math.max(2, Math.min(24, Math.ceil(w / 6)));
    var grad = g.createLinearGradient(x, 0, x + Math.max(1, w), 0);
    for (var i = 0; i <= stops; i++) {
      var f = i / stops;
      var beat = n.start + f * n.dur;
      var pr = press ? valueAt(press, beat) : 0.7;
      var tb = timb ? valueAt(timb, beat) : 0.5;
      pr = pr < 0 ? 0 : (pr > 1 ? 1 : pr);
      tb = tb < 0 ? 0 : (tb > 1 ? 1 : tb);
      var hh = hue + (tb - 0.5) * 78;
      var li = 34 + 26 * tb + 10 * pr;
      var al = (0.20 + 0.68 * pr) * (0.55 + 0.45 * vel) * alphaScale;
      grad.addColorStop(f, 'hsla(' + hh + ',78%,' + li + '%,' + al.toFixed(3) + ')');
    }
    g.fillStyle = grad;
    g.fillRect(x, y, Math.max(1, w), h);

    // outline + velocity cap
    g.strokeStyle = 'hsla(' + hue + ',80%,' + (68) + '%,' + (0.55 * alphaScale) + ')';
    g.lineWidth = 1;
    g.strokeRect(Math.round(x) + 0.5, Math.round(y) + 0.5, Math.max(2, w - 1), h - 1);
    var capH = Math.max(1.5, h * (0.25 + 0.75 * vel));
    g.fillStyle = 'hsla(' + hue + ',92%,80%,' + (0.85 * alphaScale) + ')';
    g.fillRect(x, y + h - capH, 1.8, capH);

    if (!S.showCurves) return;

    // This note's OWN bend curve, drawn through its rectangle and CONTAINED by
    // it: the vertical scale is the note's real excursion (min 2 st), so a
    // 40-semitone bend is shown in full instead of being silently flattened,
    // and it never sweeps across the pitch rows that belong to other notes.
    var span = S.rowH * 1.9;
    var bScale = noteBendScale(n);
    var cy = y + h / 2;
    g.save();
    g.beginPath();
    g.rect(x - 0.5, y - span * 0.5, w + 1, h + span);
    g.clip();

    // centre reference
    g.strokeStyle = 'rgba(255,255,255,0.10)';
    g.setLineDash([1, 3]); g.lineWidth = 1;
    g.beginPath(); g.moveTo(x, Math.round(cy) + 0.5); g.lineTo(x + w, Math.round(cy) + 0.5); g.stroke();
    g.setLineDash([]);

    if (bend && bend.length) {
      // enough samples to honour the curve's own resolution, capped for sanity
      var steps = Math.max(6, Math.min(2400,
        Math.max(Math.ceil(w * 1.5), Math.min(2400, bend.length))));
      // soft halo so the line reads over the body
      for (var pass = 0; pass < 2; pass++) {
        g.beginPath();
        for (var k = 0; k <= steps; k++) {
          var t = k / steps;
          var bv = valueAt(bend, n.start + t * n.dur);
          var by = cy - (bv / bScale) * (span / 2);
          var bx = x + t * w;
          if (k === 0) g.moveTo(bx, by); else g.lineTo(bx, by);
        }
        if (pass === 0) {
          g.strokeStyle = 'rgba(4,6,9,' + (0.75 * alphaScale) + ')';
          g.lineWidth = 3;
        } else {
          g.strokeStyle = 'hsla(' + hue + ',100%,88%,' + (0.96 * alphaScale) + ')';
          g.lineWidth = 1.5;
        }
        g.lineJoin = 'round'; g.lineCap = 'round';
        g.stroke();
      }
      // terminal dot: where the bend actually lands
      var lastV = valueAt(bend, n.start + n.dur);
      if (Math.abs(lastV) > 0.12) {
        g.fillStyle = 'hsla(' + hue + ',100%,92%,' + alphaScale + ')';
        g.beginPath();
        g.arc(x + w, cy - (lastV / bScale) * (span / 2), 1.7, 0, 6.284);
        g.fill();
      }
    }
    g.restore();
  }

  // ── overlay: playhead, hover, selection ─────────────────────────────────
  function renderOverlay() {
    var w = totalW(), h = RIBBON_H + RULER_H + rollH();
    var cv = $('cOver');
    var r = dprFor(w, h);
    if (cv.width !== Math.round(w * r) || cv.height !== Math.round(h * r)) fit(cv, w, h);
    var g = cv.getContext('2d');
    g.setTransform(r, 0, 0, r, 0, 0);
    g.clearRect(0, 0, w, h);
    var top = RIBBON_H + RULER_H;

    function boxFor(o) {
      var n = o.note;
      return { x: b2x(n.start), y: top + p2y(n.pitch),
        w: Math.max(2.5, n.dur * S.ppb - 1), h: Math.max(3, S.rowH - 1.2) };
    }
    if (S.hover) {
      var b1 = boxFor(S.hover);
      g.strokeStyle = 'rgba(255,255,255,0.5)'; g.lineWidth = 1;
      g.strokeRect(b1.x - 1.5, b1.y - 1.5, b1.w + 3, b1.h + 3);
    }
    if (S.sel) {
      var b2 = boxFor(S.sel);
      g.strokeStyle = '#6ee7d0'; g.lineWidth = 1.4;
      g.strokeRect(b2.x - 2, b2.y - 2, b2.w + 4, b2.h + 4);
      g.fillStyle = 'rgba(110,231,208,0.10)';
      g.fillRect(b2.x, top, b2.w, 0);
    }

    if (synth.playing) {
      var pb = synth.beat();
      var px = Math.round(b2x(pb)) + 0.5;
      g.fillStyle = 'rgba(110,231,208,0.06)';
      g.fillRect(0, top, px, rollH());
      g.strokeStyle = '#6ee7d0'; g.lineWidth = 1;
      g.beginPath(); g.moveTo(px, 0); g.lineTo(px, h); g.stroke();
      g.fillStyle = '#6ee7d0';
      g.beginPath();
      g.moveTo(px - 4, 0); g.lineTo(px + 4, 0); g.lineTo(px, 5); g.closePath(); g.fill();
    }
  }

  // ── inspector ───────────────────────────────────────────────────────────
  function renderInspector() {
    var o = S.sel || S.hover;
    var meta = $('inspMeta');
    var box = $('insp');
    var cv = $('cInsp');
    var w = Math.max(120, box.clientWidth - 18);
    var h = Math.max(48, cv.clientHeight || INSP_CANVAS_H);
    var g = fit(cv, w, h);
    g.clearRect(0, 0, w, h);
    g.fillStyle = '#0a0c0f'; g.fillRect(0, 0, w, h);

    if (!o) {
      meta.innerHTML = '<span class="dim">no note selected — hover the roll to preview a note, click to pin it</span>';
      g.fillStyle = '#8d99a7';                       // 6.5:1, was #2b333d at 1.53:1
      g.font = '11px ui-monospace,monospace';
      g.fillText('bend / press / timbre for one note appear here', 8, h / 2);
      return;
    }
    var n = o.note, si = o.si;
    var name = PC_NAMES[n.pitch % 12] + (Math.floor(n.pitch / 12) - 1);
    var bend = (n.curves || {}).bend;
    var bmin = 0, bmax = 0;
    if (bend) bend.forEach(function (p) { bmin = Math.min(bmin, p[1]); bmax = Math.max(bmax, p[1]); });
    meta.innerHTML =
      '<span><b>' + name + '</b> <span class="dim">' + n.pitch + '</span></span>' +
      '<span class="dim">stave</span><b style="color:' + staveCss(si, 70) + '">' + o.stave + '</b>' +
      '<span class="dim">voice</span><b>' + (n.voice || '—') + '</b>' +
      '<span class="dim">beat</span><b>' + n.start.toFixed(3) + '</b>' +
      '<span class="dim">dur</span><b>' + n.dur.toFixed(3) + '</b>' +
      '<span class="dim">vel</span><b>' + n.velocity + '</b>' +
      '<span class="dim">ch</span><b>' + (n.channel === null || n.channel === undefined ? '—' : n.channel) + '</b>' +
      '<span class="dim">bend</span><b>' + bmin.toFixed(2) + '…' + bmax.toFixed(2) + ' st</b>' +
      '<span class="dim">pts</span><b>' + Object.keys(n.curves || {}).map(function (k) {
        return k[0] + (n.curves[k].length);
      }).join(' ') + '</b>';

    // grid
    g.strokeStyle = '#161c22'; g.lineWidth = 1;
    for (var i = 0; i <= 8; i++) {
      var x = (i / 8) * (w - 1) + 0.5;
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke();
    }
    g.strokeStyle = '#2b333d';
    g.beginPath(); g.moveTo(0, h / 2 + 0.5); g.lineTo(w, h / 2 + 0.5); g.stroke();
    // axis labels are the NOTE's real bend scale, never a hard-coded ±2 st
    var sc = noteBendScale(n);
    var scL = (Math.round(sc * 10) / 10) + 'st';
    g.fillStyle = '#8d99a7'; g.font = '9px ui-monospace,monospace';   // 6.5:1, was 1.92:1
    g.fillText('+' + scL, 2, 9); g.fillText('0', 2, h / 2 - 2); g.fillText('-' + scL, 2, h - 2);
    var lg = $('lgBend');
    if (lg) lg.textContent = 'bend ±' + scL + ' (range ' + S.bendRange + 'st)';
    var hr = $('hintRange');
    if (hr) hr.textContent = '±' + scL;

    function line(points, color, map, wd) {
      if (!points || !points.length) return;
      g.strokeStyle = color; g.lineWidth = wd || 1.4;
      g.lineJoin = 'round'; g.lineCap = 'round';
      g.beginPath();
      var steps = Math.max(24, Math.min(600, Math.round(w)));
      for (var k = 0; k <= steps; k++) {
        var t = k / steps;
        var v = valueAt(points, n.start + t * n.dur);
        var yy = map(v);
        var xx = t * (w - 1);
        if (k === 0) g.moveTo(xx, yy); else g.lineTo(xx, yy);
      }
      g.stroke();
    }
    var c = n.curves || {};
    if (c.press && c.press.length) {                 // filled press envelope
      g.beginPath();
      var st2 = Math.max(24, Math.min(600, Math.round(w)));
      g.moveTo(0, h - 2);
      for (var q = 0; q <= st2; q++) {
        var tq = q / st2;
        g.lineTo(tq * (w - 1), h - 2 - valueAt(c.press, n.start + tq * n.dur) * (h - 4));
      }
      g.lineTo(w - 1, h - 2); g.closePath();
      var pg2 = g.createLinearGradient(0, 0, 0, h);
      pg2.addColorStop(0, 'rgba(245,185,107,0.20)');
      pg2.addColorStop(1, 'rgba(245,185,107,0.03)');
      g.fillStyle = pg2; g.fill();
    }
    line(c.press, 'rgba(245,192,124,0.98)', function (v) { return h - 2 - v * (h - 4); });
    line(c.timbre, 'rgba(203,182,255,0.96)', function (v) { return h - 2 - v * (h - 4); });
    line(c.bend, '#a8c6f9', function (v) { return h / 2 - (v / sc) * (h / 2 - 3); }, 1.8);
  }

  /** Fit rows to the available height and beats to the available width once. */
  function autofit() {
    if (!S.score) return;
    var host = $('rollHost');
    var availH = host.clientHeight - RIBBON_H - RULER_H - 2;
    var availW = host.clientWidth - 46 - PADL - PADR;
    if (S.autoRows && availH > 60) {
      S.rowH = Math.max(4, Math.min(18, Math.floor(availH / rows())));
      $('zoomY').value = S.rowH;
    }
    if (S.autoZoom && availW > 100) {
      // fit-to-window must be *possible*: the old floor of 10 px/beat made any
      // score over ~130 beats impossible to see whole.
      var fitAll = availW / Math.max(1, S.score.durationBeats);
      S.ppb = Math.max(1, Math.min(60, fitAll));
      $('zoom').value = Math.max(1, Math.round(S.ppb));
    }
  }

  // ── layout ──────────────────────────────────────────────────────────────
  function layout() {
    if (!S.score) return;
    autofit();
    var w = totalW(), h = RIBBON_H + RULER_H + rollH();
    var inner = $('rollInner');
    inner.style.width = w + 'px';
    inner.style.height = h + 'px';
    $('cRibbon').style.top = '0px';
    $('cRuler').style.top = RIBBON_H + 'px';
    $('cRoll').style.top = (RIBBON_H + RULER_H) + 'px';
    $('cOver').style.top = '0px';
    renderKeys(); renderRibbon(); renderRuler(); renderRoll();
    S.overlayDirty = true;
    renderOverlay(); renderInspector();
    updateRange();
  }

  // ── hit testing ─────────────────────────────────────────────────────────
  function hitTest(mx, my) {
    var beat = x2b(mx);
    var pitch = S.hi - Math.floor(my / S.rowH);
    var best = null;
    (S.score.staves || []).forEach(function (st, si) {
      st.notes.forEach(function (n) {
        if (n.pitch !== pitch) return;
        if (beat < n.start - 0.02 || beat > n.start + n.dur + 0.02) return;
        best = { note: n, stave: st.name, si: si };
      });
    });
    return best;
  }

  // ── compile bridge ──────────────────────────────────────────────────────
  function postCompile(source) {
    return fetch(API + '/api/compile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: source })
    }).then(function (r) {
      if (!r.ok) return r.text().then(function (t) { throw new Error('HTTP ' + r.status + ' ' + t.slice(0, 200)); });
      return r.json();
    });
  }

  function setApi(on, why, label) {
    S.apiOnline = on;
    var pill = $('apiPill');
    pill.textContent = label || (on ? 'compiler live' : 'fixture');
    pill.className = 'pill ' + (label === 'compile error' ? 'bad' : (on ? 'online' : 'offline'));
    pill.title = why || (on ? 'POST /api/compile is answering' : 'Backend unreachable — rendering the bundled fixture');
  }

  // Normalise every error shape the backend can return into [{text, sev, line, col}].
  function collectErrors(j) {
    if (!j || typeof j !== 'object') return [];
    var out = [];
    function push(e) {
      if (!e) return;
      if (typeof e === 'string') { out.push({ text: e, sev: 'error' }); return; }
      // The row renders line:col in its own column, so it is not repeated here.
      var where = '';
      var what = e.message || e.msg || 'compile failed';
      var tok = e.token ? '  ‹' + e.token + '›' : '';
      var fix = e.suggestion ? '\n    → ' + e.suggestion : '';
      out.push({
        text: (e.kind ? e.kind + ': ' : '') + where + what + tok + fix,
        sev: 'error', line: e.line || 0, col: e.col || 0
      });
    }
    if (j.error) push(j.error);
    if (Array.isArray(j.errors)) j.errors.forEach(push);
    else if (j.errors) push(j.errors);
    // further shapes seen in the wild: {detail:{...}}, {diagnostics:[...]}
    if (j.detail && !out.length) push(j.detail);
    if (Array.isArray(j.diagnostics)) j.diagnostics.forEach(push);
    if (!out.length && j.ok === false) push({ message: 'compile failed' });
    return out;
  }

  function looksLikeScore(j) {
    return !!j && typeof j === 'object' && Array.isArray(j.staves) &&
      typeof j.durationBeats === 'number';
  }

  function compile(explicit) {
    var src = ed.getValue();
    var btn = $('btnCompile');
    btn.textContent = 'compiling…';
    postCompile(src).then(function (j) {
      btn.innerHTML = 'compile <kbd>⌘⏎</kbd>';
      // The server answers a failed compile with {ok:false, error:{message,line,col,token,
      // suggestion,kind}} (see server.py _diag). Older/alternate shapes send a list in
      // `errors`. Accept both, and never mistake a compiler error for a dead backend.
      var diags = collectErrors(j);
      if (diags.length) {
        // A compiler error is a compiler error: the backend answered.  We keep
        // the previous roll on screen but say so, and we NEVER silently swap in
        // the bundled fixture or leave the previous score's warnings up.
        setApi(true, 'the compiler answered and rejected this source', 'compile error');
        S.stale = true;
        showDiagnostics(diags, S.score
          ? 'the roll below is the last score that compiled — fix the error above and compile again'
          : null);
        say(diags[0].text);
        return;
      }
      if (!looksLikeScore(j)) throw new Error('response is not a Score.to_json() object');
      setApi(true);
      S.lastGood = j;
      setScore(j, null);
      markClean();
      say('compiled: ' + noteCount(j) + ' notes, ' + (j.warnings || []).length + ' warnings');
    }).catch(function (err) {
      btn.innerHTML = 'compile <kbd>⌘⏎</kbd>';
      var why = String(err.message || err);
      setApi(false, why);
      S.stale = true;
      // No silent revert to the fixture: the editor and the roll must never
      // disagree without saying so.
      showDiagnostics([{ text: 'could not reach the compiler at ' + (API || location.origin) +
        '/api/compile — ' + why.slice(0, 140), sev: 'error' }],
        S.score ? 'the roll below is the last score that compiled' : null);
      say('compile failed: ' + why.slice(0, 80));
    });
  }

  /** Announce something to assistive tech (and nothing visually). */
  function say(msg) {
    var el = $('rollStatus');
    if (el) el.textContent = msg;
  }

  function markDirty() {
    S.dirty = true; $('dirty').hidden = false;
  }
  function markClean() {
    S.dirty = false; $('dirty').hidden = true;
  }

  // ── transport UI ────────────────────────────────────────────────────────
  function togglePlay() {
    if (synth.playing) {
      synth.stop();
    } else {
      synth.play(S.sel ? S.sel.note.start : 0);
    }
    S.overlayDirty = true;
    updatePlayBtn();
  }
  function updatePlayBtn() {
    var b = $('btnPlay');
    $('playGlyph').textContent = synth.playing ? '❚❚' : '▶';
    $('playLabel').textContent = synth.playing ? 'stop' : 'play';
    b.className = 'btn primary' + (synth.playing ? ' on' : '');
  }

  function formatPos(beat) {
    var m = (S.score && S.score.meter) || [4, 4];
    var bpb = m[0] * (4 / m[1]);
    var bar = Math.floor(beat / bpb) + 1;
    var bt = Math.floor(beat % bpb) + 1;
    var tick = Math.floor(((beat % 1) * 100));
    return bar + '.' + bt + '.' + (tick < 10 ? '0' + tick : tick);
  }

  function frame() {
    if (synth.playing) {
      var b = synth.beat();
      $('mPos').textContent = formatPos(Math.max(0, b));
      // keep the playhead in view
      var sc = $('rollScroll');
      var px = b2x(b);
      if (px > sc.scrollLeft + sc.clientWidth - 120) sc.scrollLeft = px - sc.clientWidth + 240;
      else if (px < sc.scrollLeft) sc.scrollLeft = Math.max(0, px - 40);
      S.overlayDirty = true;
    }
    // Only repaint the overlay when something actually moved: a static idle page
    // should not burn a canvas clear + redraw 60x a second.
    if (S.overlayDirty) { S.overlayDirty = false; renderOverlay(); }
    requestAnimationFrame(frame);
  }

  /** Move the pinned selection by (dBeatIndex, dPitchRow) within its stave. */
  function moveSel(dx, dy) {
    var staves = (S.score && S.score.staves) || [];
    if (!staves.length) return;
    // NB: `stave` is the stave NAME everywhere in this app (renderInspector
    // prints it and synth.audition() looks it up), so keyboard navigation must
    // build the same shape hitTest() does.
    function pick(si, note) {
      return { note: note, si: si, stave: staves[si].name };
    }
    if (!S.sel) {
      for (var i = 0; i < staves.length; i++) {
        if (staves[i].notes && staves[i].notes.length) { S.sel = pick(i, staves[i].notes[0]); break; }
      }
    } else if (dx) {
      var ns = (staves[S.sel.si].notes || []).slice()
        .sort(function (a, b) { return a.start - b.start; });
      var at = ns.indexOf(S.sel.note);
      var nx = Math.max(0, Math.min(ns.length - 1, at + (dx > 0 ? 1 : -1)));
      if (ns[nx]) S.sel = pick(S.sel.si, ns[nx]);
    } else if (dy) {
      var si2 = Math.max(0, Math.min(staves.length - 1, S.sel.si + (dy > 0 ? 1 : -1)));
      var tgt = staves[si2];
      if (tgt && tgt.notes && tgt.notes.length) {
        var best = tgt.notes[0], bd = Infinity;
        tgt.notes.forEach(function (n) {
          var d = Math.abs(n.start - S.sel.note.start);
          if (d < bd) { bd = d; best = n; }
        });
        S.sel = pick(si2, best);
      }
    }
    if (!S.sel) return;
    S.overlayDirty = true;
    renderInspector();
    // scroll the selection into view
    var sc = $('rollScroll');
    var px = b2x(S.sel.note.start);
    if (px < sc.scrollLeft + 40) sc.scrollLeft = Math.max(0, px - 80);
    else if (px > sc.scrollLeft + sc.clientWidth - 60) sc.scrollLeft = px - sc.clientWidth + 160;
    var n = S.sel.note;
    say(S.sel.stave + ' — pitch ' + PC_NAMES[n.pitch % 12] + (Math.floor(n.pitch / 12) - 1) +
      ', bar ' + formatPos(n.start) + ', ' + n.dur + ' beats, velocity ' + (n.velocity || 90));
  }

  // ── boot ────────────────────────────────────────────────────────────────
  function boot() {
    ed = new window.FiligreeEditor.Editor($('ta'), $('hl'), $('gutter'), $('edScroll'), {
      onCompile: function () { compile(true); },
      onChange: markDirty,
      // editor.js tells us when Escape has armed "the next Tab leaves"
      onEscape: function (on) { $('edWrap').classList.toggle('escaped', !!on); }
    });

    Promise.all([
      fetch(FIXTURE_SRC).then(function (r) { return r.text(); }),
      fetch(FIXTURE_JSON).then(function (r) { return r.json(); })
    ]).then(function (res) {
      ed.setValue(res[0]);
      S.fixture = res[1];
      setScore(res[1], null);
      markClean();
      // opportunistic upgrade to the real compiler
      postCompile(res[0]).then(function (j) {
        if (looksLikeScore(j)) { setApi(true); S.lastGood = j; setScore(j, null); }
        else setApi(false, 'backend responded but not with a Score');
      }).catch(function (e) {
        setApi(false, 'offline: ' + String(e.message || e).slice(0, 120));
      });
    }).catch(function (e) {
      showDiagnostics(['fixtures/score.json could not be loaded: ' + (e.message || e) +
        ' — serve this directory over HTTP (python -m http.server) rather than opening the file directly.'], null);
    });

    // controls
    $('btnPlay').onclick = togglePlay;
    $('btnStop').onclick = function () {
      synth.stop(); $('mPos').textContent = formatPos(0);
      S.overlayDirty = true; updatePlayBtn();
    };
    $('btnCompile').onclick = function () { compile(true); };
    $('vol').oninput = function () { synth.setVolume(this.value / 100); };
    synth.setVolume($('vol').value / 100);

    $('zoom').oninput = function () { S.autoZoom = false; S.ppb = +this.value; layout(); };
    $('zoomY').oninput = function () { S.autoRows = false; S.rowH = +this.value; layout(); };
    $('showCurves').onchange = function () { S.showCurves = this.checked; renderRoll(); };

    // the always-visible "first five seconds" strip
    var stepPlay = $('stepPlay'), stepEdit = $('stepEdit'), stepCompile = $('stepCompile');
    if (stepPlay) stepPlay.onclick = function () { togglePlay(); };
    if (stepEdit) stepEdit.onclick = function () {
      var ta = $('ta');
      ta.focus();
      // land on the first note lane so "change something" has an obvious target
      var lines = ta.value.split('\n');
      for (var i = 0; i < lines.length; i++) {
        if (/^\s*notes\b/.test(lines[i])) { ed.gotoLine(i + 1, (lines[i].indexOf('notes') + 7)); break; }
      }
    };
    if (stepCompile) stepCompile.onclick = function () { compile(true); };

    // roll interaction
    var host = $('rollScroll');
    var over = $('cOver');
    host.addEventListener('mousemove', function (e) {
      var r = $('cRoll').getBoundingClientRect();
      var mx = e.clientX - r.left, my = e.clientY - r.top;
      if (my < 0 || my > rollH()) { if (S.hover) { S.hover = null; renderInspector(); } return; }
      var h = hitTest(mx, my);
      if (h !== S.hover && (!h || !S.hover || h.note !== S.hover.note)) {
        S.hover = h;
        S.overlayDirty = true;
        if (!S.sel) renderInspector();
      }
      host.style.cursor = h ? 'pointer' : 'default';
    });
    host.addEventListener('mouseleave', function () {
      S.hover = null; S.overlayDirty = true; renderInspector();
    });
    host.addEventListener('click', function (e) {
      var rr = $('cRoll').getBoundingClientRect();
      var mx = e.clientX - rr.left, my = e.clientY - rr.top;
      if (my < 0) {                                  // clicked ruler/ribbon: seek
        var b = Math.max(0, x2b(mx));
        if (synth.playing) synth.play(b);
        $('mPos').textContent = formatPos(b);
        return;
      }
      var h = hitTest(mx, my);
      S.sel = h;
      S.overlayDirty = true;
      renderInspector();
      if (h) synth.audition(h.note, h.stave);
    });
    host.addEventListener('scroll', function () { updateRange(); });

    // Roll keyboard navigation: the piano roll is a real focusable widget, not a
    // mouse-only picture.  Arrows walk notes/staves, Enter auditions, Esc clears.
    host.addEventListener('keydown', function (e) {
      var k = e.key;
      if (k === 'ArrowRight' || k === 'ArrowLeft') {
        e.preventDefault(); moveSel(k === 'ArrowRight' ? 1 : -1, 0);
      } else if (k === 'ArrowDown' || k === 'ArrowUp') {
        e.preventDefault(); moveSel(0, k === 'ArrowDown' ? 1 : -1);
      } else if (k === 'Enter' || k === ' ') {
        if (S.sel) { e.preventDefault(); synth.audition(S.sel.note, S.sel.stave); }
      } else if (k === 'Home') {
        e.preventDefault(); host.scrollLeft = 0;
      } else if (k === 'End') {
        e.preventDefault(); host.scrollLeft = host.scrollWidth;
      } else if (k === 'Escape') {
        S.sel = null; S.overlayDirty = true; renderInspector(); say('selection cleared');
      }
    });
    host.addEventListener('wheel', function (e) {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      var f = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      S.autoZoom = false;
      S.ppb = Math.max(1, Math.min(220, S.ppb * f));
      $('zoom').value = Math.round(S.ppb);
      layout();
    }, { passive: false });

    // global keys
    document.addEventListener('keydown', function (e) {
      var inEd = document.activeElement === $('ta');
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); compile(true); return; }
      if (e.code === 'Space' && !inEd) { e.preventDefault(); togglePlay(); }
      if (e.key === 'Escape' && !inEd) { S.sel = null; S.overlayDirty = true; renderInspector(); }
    });

    // splitter — relayouts live while dragging (rAF-throttled) and is operable
    // from the keyboard as an ARIA separator.
    var dragging = false, pending = false;
    function setSplit(pct) {
      pct = Math.max(22, Math.min(72, pct));
      $('left').style.width = pct + '%';
      $('split').setAttribute('aria-valuenow', Math.round(pct));
      if (pending) return;
      pending = true;
      requestAnimationFrame(function () { pending = false; layout(); });
    }
    $('split').addEventListener('mousedown', function (e) {
      e.preventDefault(); dragging = true; document.body.style.cursor = 'col-resize';
    });
    window.addEventListener('mouseup', function () {
      if (dragging) { dragging = false; document.body.style.cursor = ''; layout(); }
    });
    window.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      setSplit((e.clientX / window.innerWidth) * 100);
    });
    $('split').addEventListener('keydown', function (e) {
      var cur = parseFloat($('left').style.width) ||
        ($('left').getBoundingClientRect().width / window.innerWidth) * 100;
      if (e.key === 'ArrowLeft') { e.preventDefault(); setSplit(cur - 2); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); setSplit(cur + 2); }
      else if (e.key === 'Home') { e.preventDefault(); setSplit(22); }
      else if (e.key === 'End') { e.preventDefault(); setSplit(72); }
    });
    window.addEventListener('resize', function () { layout(); });

    // Poll only the two things that change without a DOM event of their own:
    // playback ending on its own, and voices being reaped.
    setInterval(function () {
      if (!synth.playing && $('playLabel').textContent === 'stop') {
        updatePlayBtn(); S.overlayDirty = true;
      }
    }, 300);

    // tiny dev hook used by web/_shot.js to click an exact note
    window.__dbgVoices = function () {
      return { live: synth._live.length, playing: synth.playing,
               ctx: synth.ctx ? synth.ctx.state : 'none', queued: synth._qi };
    };
    window.__geo = function () {
      return { b2x: b2x, p2y: p2y, rowH: S.rowH, ppb: S.ppb };
    };
    // dev hook: measure real output level, so "play makes sound" is verifiable
    window.__rms = function (ms) {
      if (!synth.ctx) return Promise.resolve(0);
      var an = synth.ctx.createAnalyser();
      an.fftSize = 2048;
      synth.master.connect(an);
      var buf = new Float32Array(an.fftSize);
      var peak = 0;
      var until = Date.now() + (ms || 800);
      return new Promise(function (done) {
        (function poll() {
          an.getFloatTimeDomainData(buf);
          var s = 0;
          for (var i = 0; i < buf.length; i++) s += buf[i] * buf[i];
          peak = Math.max(peak, Math.sqrt(s / buf.length));
          if (Date.now() < until) setTimeout(poll, 40);
          else { try { synth.master.disconnect(an); } catch (e) { } done(peak); }
        })();
      });
    };

    requestAnimationFrame(frame);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
