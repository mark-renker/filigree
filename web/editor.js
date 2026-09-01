/* editor.js — textarea-backed Filigree editor with overlay syntax highlighting.
 *
 * Alignment contract (round 2 — now structural, not a promise):
 *   #hl (a <pre>) and #ta (the <textarea>) are absolutely stacked with
 *   IDENTICAL font, size, line-height, padding, tab-size, letter-spacing and
 *   `white-space:pre`, ligatures disabled.  Crucially the overlay does NOT lay
 *   its coloured tokens out in the inline flow: each line is one block whose
 *   *only* in-flow content is the raw line text (transparent, so it sets the
 *   line's exact width and metrics), and every coloured token is an absolutely
 *   positioned span at `left: <column>ch`.
 *
 *   That makes a token's x-position a function of its column alone, so the
 *   1/64-px rounding every inline text run costs can no longer accumulate.
 *   Measured drift (see web/tools/measure_drift.py): 0.016 px at 100 chars and
 *   0.016 px at 4000 chars — constant, i.e. 0.002 characters, not 7.
 *
 *   Nothing in the overlay may change advance width: no bold, no padding, no
 *   transforms.  Weights live nowhere in style.css's token rules.
 *
 * Vendored here; zero dependencies, zero network.
 */
(function (global) {
  'use strict';

  var TAB = 2;                 // must match `tab-size` in style.css

  // ── lexical tables ──────────────────────────────────────────────────────
  var BLOCK_KW = /^(stave|gesture|feel|voicing|part|play|channelgroup|after)\b/;
  var LANE_RE = /^([a-z][a-z0-9]*)(?:@([A-Za-z_][\w-]*))?((?:![^\s|]+)*)\s*(?=\||$)/;
  var LANE_CLASS = {
    notes: 'notes', harm: 'harm', voices: 'notes',
    bend: 'bend', press: 'press', timbre: 'timbre',
    amp: 'press', pan: 'other'
  };
  var CURVE_LANES = { bend: 1, press: 1, timbre: 1, amp: 1, pan: 1 };

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function laneKind(name) {
    if (LANE_CLASS[name]) return LANE_CLASS[name];
    if (/^cc\d+$/.test(name)) return 'other';
    return null;
  }
  function isCurve(name) {
    return !!CURVE_LANES[name] || /^cc\d+$/.test(name);
  }

  /* A token collector.  It tracks the *visual column* of everything it is
   * handed (tabs advance to the next multiple of TAB), coalesces adjacent runs
   * that share a class, and never emits an element for whitespace. */
  function Out(raw) { this.toks = []; this.col = 0; this.raw = raw; }

  Out.prototype.push = function (txt, cls) {
    if (!txt) return;
    var parts = txt.split('\t');
    for (var k = 0; k < parts.length; k++) {
      if (k > 0) this.col = (Math.floor(this.col / TAB) + 1) * TAB;   // tab stop
      var seg = parts[k];
      if (!seg) continue;
      if (!cls || /^ +$/.test(seg)) { this.col += seg.length; continue; }
      var last = this.toks[this.toks.length - 1];
      if (last && last.cls === cls && last.col + last.text.length === this.col) {
        last.text += seg;                                             // coalesce
      } else {
        this.toks.push({ col: this.col, cls: cls, text: seg });
      }
      this.col += seg.length;
    }
  };

  /** Inner HTML of one overlay line: transparent base text + absolute tokens. */
  Out.prototype.html = function () {
    var h = '<span class="lb">' + esc(this.raw) + '</span>';
    for (var i = 0; i < this.toks.length; i++) {
      var t = this.toks[i];
      h += '<span class="tk ' + t.cls + '" style="left:' + t.col + 'ch">' +
        esc(t.text) + '</span>';
    }
    return h;
  };

  // ── per-lane content tokenizers ─────────────────────────────────────────
  /* Curve lanes are scanned char-by-char but emitted as coalesced RUNS, so a
   * 4000-char lane is a few hundred spans rather than 4000. */
  function tokCurve(out, s) {
    var i = 0, n = s.length;
    while (i < n) {
      var c = s[i];
      if (c === ' ' || c === '\t') { out.push(c, null); i++; continue; }
      if (c === '|') { out.push(c, 't-bar'); i++; continue; }
      if (c === '>') {                       // harmonic resolve target
        var m = /^>([0-9]+|[+\-|])?/.exec(s.slice(i));
        out.push(m[0], 't-tgt'); i += m[0].length; continue;
      }
      if (c === '~') {
        var mw = /^~[0-9]?/.exec(s.slice(i));
        out.push(mw[0], 't-wig'); i += mw[0].length; continue;
      }
      if (/^[A-Za-z_][\w-]*\(/.test(s.slice(i))) {   // inline gesture call
        var mg = /^[A-Za-z_][\w-]*/.exec(s.slice(i));
        out.push(mg[0], 't-gest'); i += mg[0].length; continue;
      }
      if (c === '^' || c === '/') { out.push(c, 't-up'); i++; continue; }
      if (c === '_' || c === '\\') { out.push(c, 't-dn'); i++; continue; }
      if (c === '-') { out.push(c, 't-mid'); i++; continue; }
      if (c === 'x') { out.push(c, 't-tie'); i++; continue; }
      if (c >= '0' && c <= '9') { out.push(c, 't-lvl'); i++; continue; }
      if ('[]()*:'.indexOf(c) >= 0) { out.push(c, 't-grp'); i++; continue; }
      out.push(c, 't-op'); i++;
    }
  }

  function tokNotes(out, s) {
    var re = /(\s+)|(\|)|(#.*$)|([A-Za-z_][\w-]*\s*:)|([_^]+)|(~[0-9]+)|(@[a-z]+)|([A-Za-z][b#]?-?[0-9])|([#b]?-?[0-9]+)|(!\s*[A-Za-z_][\w-]*|![a-z]+=[\w.]+)|(:v[0-9]+|%[0-9]+|\?[0-9]*)|([',])|([-.=])|([[\]<>(){}*;])|(.)/g;
    var m;
    while ((m = re.exec(s)) !== null) {
      var t = m[0];
      if (m[1]) out.push(t, null);
      else if (m[2]) out.push(t, 't-bar');
      else if (m[3]) out.push(t, 't-com');
      else if (m[4]) out.push(t, 't-voice');
      else if (m[5]) out.push(t, 't-up');
      else if (m[6]) out.push(t, 't-wig');
      else if (m[7]) out.push(t, 't-tgt');
      else if (m[8]) out.push(t, 't-abs');
      else if (m[9]) out.push(t, 't-deg');
      else if (m[10]) out.push(t, 't-gest');
      else if (m[11]) out.push(t, 't-vel');
      else if (m[12]) out.push(t, 't-vel');
      else if (m[13]) out.push(t, t === '-' ? 't-tie' : 't-rest');
      else if (m[14]) out.push(t, 't-grp');
      else out.push(t, 't-op');
      if (re.lastIndex >= s.length) break;
    }
  }

  function tokHarm(out, s) {
    var re = /(\s+)|(\|)|(#.*$)|(\{[^}]*\})|([b#]?(?:VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)[A-Za-z0-9^#b/\-+]*)|([A-G][b#]?[A-Za-z0-9^#b/()+\-]*)|([-.])|(.)/g;
    var m;
    while ((m = re.exec(s)) !== null) {
      var t = m[0];
      if (m[1]) out.push(t, null);
      else if (m[2]) out.push(t, 't-bar');
      else if (m[3]) out.push(t, 't-com');
      else if (m[4]) out.push(t, 't-chord');
      else if (m[5]) out.push(t, 't-chord');
      else if (m[6]) out.push(t, 't-chord');
      else if (m[7]) out.push(t, t === '-' ? 't-tie' : 't-rest');
      else out.push(t, 't-op');
      if (re.lastIndex >= s.length) break;
    }
  }

  function tokGeneric(out, s) {
    var re = /(\s+)|(#.*$)|("(?:[^"\\]|\\.)*")|(\b\d+(?:\.\d+)?(?:bpm|hz|st|ms|%)?\b)|(\b(?:shape|range|mode|size|drop|spread|top|rate|depth|onset|timing|velocity|gate|seed|per-voice-spread|gauss|flat|on|ease|linear|hold|exp|snap|smooth|close|open|quartal|shell|rootless|literal|melody)\b)|([A-Za-z_][\w-]*)|(->|>>|\||[=+*@:,;{}()\[\]<>.\/\\!-])|(.)/g;
    var m;
    while ((m = re.exec(s)) !== null) {
      var t = m[0];
      if (m[1]) out.push(t, null);
      else if (m[2]) out.push(t, 't-com');
      else if (m[3]) out.push(t, 't-str');
      else if (m[4]) out.push(t, 't-num');
      else if (m[5]) out.push(t, 't-kw');
      else if (m[6]) out.push(t, 't-name');
      else if (m[7]) out.push(t, 't-op');
      else out.push(t, 't-op');
      if (re.lastIndex >= s.length) break;
    }
  }

  // ── one line, given the lane the previous line established ──────────────
  function highlightLine(line, lastLane) {
    var out = new Out(line);

    var ws = /^[ \t]*/.exec(line)[0];
    out.push(ws, null);
    var body = line.slice(ws.length);

    if (body === '') return { out: out, lane: lastLane };

    if (body[0] === '#') { out.push(body, 't-com'); return { out: out, lane: lastLane }; }

    // trailing comment is peeled off first (never inside a string here)
    var cmt = '';
    var hashAt = -1, inStr = false;
    for (var k = 0; k < body.length; k++) {
      if (body[k] === '"') inStr = !inStr;
      else if (body[k] === '#' && !inStr) { hashAt = k; break; }
    }
    if (hashAt >= 0) { cmt = body.slice(hashAt); body = body.slice(0, hashAt); }

    if (body[0] === '@') {                                   // directive
      var md = /^@[a-z-]+/.exec(body);
      out.push(md[0], 't-dir');
      tokGeneric(out, body.slice(md[0].length));
      lastLane = null;
    } else if (body[0] === '|') {                             // lane continuation
      if (lastLane && isCurve(lastLane)) tokCurve(out, body);
      else if (lastLane === 'harm') tokHarm(out, body);
      else if (lastLane) tokNotes(out, body);
      else tokGeneric(out, body);
    } else if (BLOCK_KW.test(body)) {                         // block header
      var mk = BLOCK_KW.exec(body);
      out.push(mk[0], 't-kw');
      tokGeneric(out, body.slice(mk[0].length));
      lastLane = null;
    } else {
      var ml = LANE_RE.exec(body);
      var kind = ml ? laneKind(ml[1]) : null;
      if (ml && kind) {
        out.push(ml[1], 't-lane-' + kind);                    // lane name
        var off = ml[1].length;
        if (ml[2]) { out.push('@', 't-op'); out.push(ml[2], 't-voice'); off += 1 + ml[2].length; }
        if (ml[3]) { tokGeneric(out, ml[3]); off += ml[3].length; }
        var rest = body.slice(off);
        var lead = /^\s*/.exec(rest)[0];
        out.push(lead, null);
        rest = rest.slice(lead.length);
        if (isCurve(ml[1])) tokCurve(out, rest);
        else if (ml[1] === 'harm') tokHarm(out, rest);
        else tokNotes(out, rest);
        lastLane = ml[1];
      } else {
        tokGeneric(out, body);
      }
    }
    if (cmt) out.push(cmt, 't-com');
    return { out: out, lane: lastLane };
  }

  /** Public: full-document HTML (one `.ln` block per source line). */
  function highlight(src) {
    var lines = src.split('\n');
    var lane = null, html = [];
    for (var i = 0; i < lines.length; i++) {
      var r = highlightLine(lines[i], lane);
      lane = r.lane;
      html.push('<span class="ln">' + r.out.html() + '</span>');
    }
    return html.join('');
  }

  /** Public: the tokens of one line, for tests/measurement. */
  function tokensOf(line, lane) {
    return highlightLine(line, lane === undefined ? null : lane).out.toks;
  }

  // ── the editor controller ───────────────────────────────────────────────
  function Editor(ta, hl, gutter, scroll, opts) {
    this.ta = ta; this.hl = hl; this.gutter = gutter; this.scroll = scroll;
    this.opts = opts || {};
    this.badLines = {};
    this._nLines = -1;         // gutter row count actually in the DOM
    this._lineHtml = [];       // per-line overlay HTML currently in the DOM
    this._memo = Object.create(null);
    this._memoN = 0;
    this._curGut = -1;
    this._escaped = false;     // Escape pressed: the next Tab leaves the editor
    var self = this;

    ta.addEventListener('input', function () { self.render(); self._dirty(); });
    ta.addEventListener('scroll', function () { self.sync(); });
    ta.addEventListener('keydown', function (e) { self.onKey(e); });
    ta.addEventListener('click', function () { self.renderGutter(); });
    ta.addEventListener('keyup', function () { self.renderGutter(); });
    ta.addEventListener('blur', function () { self._setEscaped(false); });
    window.addEventListener('resize', function () { self.sync(); });
  }

  Editor.prototype._dirty = function () {
    if (this.opts.onChange) this.opts.onChange();
  };

  Editor.prototype._setEscaped = function (on) {
    if (this._escaped === on) return;
    this._escaped = on;
    if (this.opts.onEscape) this.opts.onEscape(on);
  };

  Editor.prototype.setValue = function (v) {
    this.ta.value = v;
    this.render();
  };
  Editor.prototype.getValue = function () { return this.ta.value; };

  // ── rendering: only the lines that actually changed touch the DOM ────────
  Editor.prototype.render = function () {
    var lines = this.ta.value.split('\n');
    var host = this.hl;
    var memo = this._memo;
    var lane = null;
    var prev = this._lineHtml;
    var next = new Array(lines.length);

    if (this._memoN > 4000) { this._memo = memo = Object.create(null); this._memoN = 0; }

    for (var i = 0; i < lines.length; i++) {
      var key = (lane === null ? '' : lane) + '\u0000' + lines[i];
      var hit = memo[key];
      if (hit === undefined) {
        var r = highlightLine(lines[i], lane);
        hit = memo[key] = { h: r.out.html(), lane: r.lane };
        this._memoN++;
      }
      next[i] = hit.h;
      lane = hit.lane;
    }

    var kids = host.children;
    while (kids.length > lines.length) host.removeChild(host.lastChild);
    while (kids.length < lines.length) {
      var el = document.createElement('span');
      el.className = 'ln';
      host.appendChild(el);
    }
    for (i = 0; i < lines.length; i++) {
      if (prev[i] !== next[i] || !kids[i].firstChild) kids[i].innerHTML = next[i];
    }
    this._lineHtml = next;

    this.renderGutter(lines.length);
    this.sync();
  };

  Editor.prototype.curLine = function () {
    var v = this.ta.value.slice(0, this.ta.selectionStart);
    return v.split('\n').length;
  };

  Editor.prototype.renderGutter = function (n) {
    if (n === undefined) n = this.ta.value.split('\n').length;
    var g = this.gutter;
    if (n !== this._nLines) {
      var rows = [];
      for (var i = 1; i <= n; i++) rows.push('<div>' + i + '</div>');
      g.innerHTML = rows.join('');
      this._nLines = n;
      this._curGut = -1;
      this._paintBad();
    }
    var cur = this.curLine();
    if (cur !== this._curGut) {
      var kids = g.children;
      if (this._curGut >= 1 && kids[this._curGut - 1]) {
        kids[this._curGut - 1].classList.remove('gl-cur');
      }
      if (kids[cur - 1]) kids[cur - 1].classList.add('gl-cur');
      this._curGut = cur;
    }
  };

  Editor.prototype._paintBad = function () {
    var kids = this.gutter.children;
    for (var i = 0; i < kids.length; i++) {
      kids[i].classList.toggle('gl-bad', !!this.badLines[i + 1]);
    }
  };

  Editor.prototype.setBadLines = function (map) {
    this.badLines = map || {};
    this._paintBad();
  };

  Editor.prototype.sync = function () {
    this.hl.scrollTop = this.ta.scrollTop;
    this.hl.scrollLeft = this.ta.scrollLeft;
    this.gutter.scrollTop = this.ta.scrollTop;
  };

  Editor.prototype.lineHeight = function () {
    var lh = parseFloat(getComputedStyle(this.ta).lineHeight);
    return lh > 0 ? lh : 22;
  };

  Editor.prototype.gotoLine = function (line, col) {
    var lines = this.ta.value.split('\n');
    line = Math.max(1, Math.min(line, lines.length));
    var pos = 0;
    for (var i = 0; i < line - 1; i++) pos += lines[i].length + 1;
    var text = lines[line - 1] || '';
    var end = pos + text.length;
    this.ta.focus();
    if (col && col > 0 && col <= text.length + 1) {
      this.ta.setSelectionRange(pos + col - 1, Math.min(end, pos + col));
    } else {
      this.ta.setSelectionRange(pos, end);
    }
    var lh = this.lineHeight();
    this.ta.scrollTop = Math.max(0, (line - 3) * lh);
    this.sync();
    this.renderGutter();
  };

  // ── keys ────────────────────────────────────────────────────────────────
  /* Tab is a *conditional* indent, never a keyboard trap (WCAG 2.1.2):
   *   • selection spanning text            → indent / outdent the block
   *   • caret inside leading whitespace     → insert one indent
   *   • caret anywhere else                 → move focus (browser default)
   *   • Shift+Tab with no selection         → move focus backwards
   *   • Escape, then Tab                    → always moves focus, no matter what
   */
  Editor.prototype.onKey = function (e) {
    var ta = this.ta, self = this;
    var INDENT = '  ';

    if (e.key === 'Escape') { this._setEscaped(true); return; }

    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      this._setEscaped(false);
      if (this.opts.onCompile) this.opts.onCompile();
      return;
    }

    if (e.key === 'Tab') {
      var s = ta.selectionStart, t = ta.selectionEnd, v = ta.value;
      var lineStart = v.lastIndexOf('\n', s - 1) + 1;
      var inLeadingWs = /^[ \t]*$/.test(v.slice(lineStart, s));
      var escapeNow = this._escaped || (s === t && (e.shiftKey || !inLeadingWs));
      if (escapeNow) { this._setEscaped(false); return; }   // let focus move on

      e.preventDefault();
      if (s === t) {
        ta.value = v.slice(0, s) + INDENT + v.slice(t);
        ta.selectionStart = ta.selectionEnd = s + INDENT.length;
      } else {
        var ls = lineStart;
        var le = v.indexOf('\n', t); if (le < 0) le = v.length;
        var block = v.slice(ls, le).split('\n');
        var delta = 0;
        block = block.map(function (ln) {
          if (e.shiftKey) {
            var m = /^( {1,2}|\t)/.exec(ln);
            if (m) { delta -= m[0].length; return ln.slice(m[0].length); }
            return ln;
          }
          delta += INDENT.length; return INDENT + ln;
        });
        ta.value = v.slice(0, ls) + block.join('\n') + v.slice(le);
        ta.selectionStart = ls;
        ta.selectionEnd = Math.max(ls, le + delta);
      }
      this.render(); this._dirty();
      return;
    }

    this._setEscaped(false);

    if (e.key === 'Enter') {                       // keep the current indent
      var p = ta.selectionStart, vv = ta.value;
      var s0 = vv.lastIndexOf('\n', p - 1) + 1;
      var ind = /^[ \t]*/.exec(vv.slice(s0, p))[0];
      if (/[{]\s*$/.test(vv.slice(s0, p))) ind += INDENT;
      if (ind) {
        e.preventDefault();
        ta.value = vv.slice(0, p) + '\n' + ind + vv.slice(ta.selectionEnd);
        ta.selectionStart = ta.selectionEnd = p + 1 + ind.length;
        this.render(); this._dirty();
      }
      return;
    }
    if (e.key === '}') { setTimeout(function () { self.render(); }, 0); }
  };

  global.FiligreeEditor = {
    Editor: Editor, highlight: highlight, highlightLine: highlightLine,
    tokensOf: tokensOf, TAB: TAB
  };
})(window);
