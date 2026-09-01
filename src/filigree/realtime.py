"""Realtime MPE output.

Sends the stream produced by :func:`filigree.mpe.render_events` to a MIDI
output port, scheduled against a monotonic clock.  ``mido``/``rtmidi`` are
imported lazily inside the functions so this module imports cleanly on a machine
without ``python-rtmidi`` installed (see docs/ARCH.md rule 3).

Routing notes (research/mpe_technical.md §4): RtMidi is the only backend that can
create virtual ports, so ``port=None`` publishes a virtual CoreMIDI source named
``"Filigree"`` that a DAW can subscribe to; the macOS IAC Driver bus is the
fallback when a persistent endpoint is wanted.

Owned by piece P4.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from . import errors
from .ir import Score
from .mpe import (CC_ALL_NOTES_OFF, CC_ALL_SOUND_OFF, CC_RESET_ALL, CC_SUSTAIN,
                  MpeOptions, _bend_msg, _note_off, _opts_from_score, _cc,
                  _press, render_events)

PORT_NAME = "Filigree"


def _mido():
    try:
        import mido  # noqa: WPS433 (lazy on purpose)
    except Exception as exc:                     # pragma: no cover - env dependent
        raise errors.RenderError(
            "mido is required for realtime output",
            suggestion="pip install mido python-rtmidi") from exc
    try:
        import rtmidi  # noqa: F401
        mido.set_backend("mido.backends.rtmidi")
    except Exception:                            # pragma: no cover - env dependent
        pass                                     # leave mido's default backend
    return mido


def list_ports() -> list[str]:
    """Names of available MIDI output ports (empty list if no backend)."""
    try:
        mido = _mido()
    except errors.RenderError:                   # pragma: no cover - env dependent
        return []
    try:
        return list(mido.get_output_names())
    except Exception:                            # pragma: no cover - env dependent
        return []


def _open_output(mido, port: Optional[str]):
    if port is None:
        try:
            return mido.open_output(PORT_NAME, virtual=True, client_name=PORT_NAME)
        except Exception as exc:
            names = []
            try:
                names = list(mido.get_output_names())
            except Exception:
                pass
            raise errors.RenderError(
                "could not open a virtual MIDI port named %r" % PORT_NAME,
                suggestion=("install python-rtmidi, or pass an existing port name "
                            "(available: %s)" % (", ".join(names) or "none"))) from exc
    return mido.open_output(port)


def panic_stream(opts: MpeOptions,
                 sounding: Optional[set] = None) -> list[list[int]]:
    """The full teardown stream, in send order.

    Per note per channel: pressure 0 and an explicit note-off for every note we
    know is sounding (a receiver that ignores CC 123 still stops), then pitch
    bend re-centred to 0x2000, sustain off, reset-all-controllers, all-notes-off
    and all-sound-off.  Re-centring matters because a hold receiver keeps the
    last bend forever: without it the next thing to use the channel starts
    detuned (research/mpe_technical.md §2).
    """
    chans = sorted(set(opts.members) | {0, 15})
    out: list[list[int]] = []
    for ch in chans:
        out.append(_press(ch, 0))
        for (nch, pitch) in sorted(sounding or ()):
            if nch == ch:
                out.append(_note_off(ch, pitch, 0))
        out.append(_bend_msg(ch, 0))
        out.append(_cc(ch, CC_SUSTAIN, 0))
        out.append(_cc(ch, CC_RESET_ALL, 0))
        out.append(_cc(ch, CC_ALL_NOTES_OFF, 0))
        out.append(_cc(ch, CC_ALL_SOUND_OFF, 0))
    return out


def _panic(out, opts: MpeOptions, sounding: Optional[set] = None) -> None:
    """Send :func:`panic_stream`.  Never raises: a panic runs in a ``finally``
    block, so an exception here would mask the original failure."""
    try:
        mido = _mido()
    except Exception:                            # pragma: no cover - env dependent
        return
    for data in panic_stream(opts, sounding):
        try:
            out.send(mido.Message.from_bytes(bytes(data)))
        except Exception:                        # pragma: no cover - env dependent
            pass


def play(score: Score, port: Optional[str] = None, opts: Optional[MpeOptions] = None,
         loop: bool = False, on_event: Optional[Callable] = None) -> None:
    """Play ``score`` as live MPE on ``port`` (virtual ``"Filigree"`` if None).

    ``on_event(beat, data)`` is called for every message just before it is sent,
    which makes the scheduler testable without a MIDI backend.  Pressure 0 and
    all-notes-off are flushed on normal exit, on ``KeyboardInterrupt`` and on any
    exception.
    """
    opts = opts or _opts_from_score(score)
    events = render_events(score, opts)
    if not events:
        return
    spb = 60.0 / max(1e-9, score.tempo)
    span = max(beat for beat, _ in events) * spb + 0.25

    mido = _mido()
    out = _open_output(mido, port)
    sounding: set = set()
    try:
        while True:
            t0 = time.monotonic()
            for beat, data in events:
                st = data[0] & 0xF0
                if st == 0x90 and len(data) > 2 and data[2]:
                    sounding.add((data[0] & 0x0F, data[1]))
                elif st in (0x80, 0x90) and len(data) > 1:
                    sounding.discard((data[0] & 0x0F, data[1]))
                target = t0 + beat * spb
                while True:
                    dt = target - time.monotonic()
                    if dt <= 0:
                        break
                    time.sleep(min(dt, 0.001))
                if on_event is not None:
                    on_event(beat, list(data))
                out.send(mido.Message.from_bytes(bytes(data)))
            while time.monotonic() - t0 < span:
                time.sleep(0.001)
            if not loop:
                break
            # Panic between passes: the next pass restates every preamble, but a
            # hold receiver would otherwise carry stuck notes/bend across the seam.
            _panic(out, opts, sounding)
            sounding.clear()
    except KeyboardInterrupt:
        pass
    finally:
        _panic(out, opts, sounding)
        try:
            out.close()
        except Exception:                        # pragma: no cover - env dependent
            pass


def dry_run(score: Score, opts: Optional[MpeOptions] = None) -> list[tuple[float, list[int]]]:
    """The exact stream :func:`play` would send, without opening a port."""
    return render_events(score, opts or _opts_from_score(score))
