# MPE Technical Implementation Reference (compiler → expressive MIDI → macOS DAWs)

Target: a compiler that emits (a) Standard MIDI Files and (b) realtime MIDI, consumed by Ableton Live 12.x, Bitwig Studio 5.x, Logic Pro on macOS (Apple Silicon).
Every factual claim below is tied to a primary source URL. Items marked **[UNCERTAIN]** are not documented by a vendor and rest on secondary evidence or on inference.

---

## 1. MPE specification details (MMA/AMEI RP-053 / CA-034)

### 1.1 Zones, master channel, member channels

The MPE spec (MMA/AMEI *MIDI Polyphonic Expression*, RP-053) is built entirely on MIDI 1.0 channel voice messages ([RP-053 spec PDF](https://midimpe.neocities.org/rp53spec.pdf)):

- A **Zone** = "a group of contiguous MIDI Channels comprising a Master Channel and one or more Member Channels" ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- **Lower Zone**: Master Channel = **channel 1**, Member Channels assigned sequentially from **channel 2 upwards**. **Upper Zone**: Master Channel = **channel 16**, Members from **channel 15 downwards** ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- Master Channel carries data that applies to the whole zone (zone pitch bend, pedals, program change, CC1/CC7/CC64, all other CCs, all RPNs/NRPNs). Member Channels carry **per-note** data ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- "Wherever possible, every sounding note is assigned its own MIDI Channel for the lifetime of that note" ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- A single active zone may use up to **15 member channels**; the unused zone's master channel may be used as a member channel; a channel cannot belong to two zones; the most recent MCM wins ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- Notes *are* legal on the master channel (MIDI 1.0 compatibility) but then "Channel Pressure, Pitch Bend, and Modulation cannot be controlled for notes on a Master Channel without also affecting the rest of the Zone" ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)). **Do not put compiler notes on the master channel.**
- MPE mode is *on* when at least one zone is configured, *off* when both zones are set to zero channels ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).

### 1.2 MPE Configuration Message (MCM), RPN 0x00 0x06

Defined as RPN "00 06" (AMEI/MMA CA-034). Format ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)):

```
[Bn 64 06]  RPN LSB = 06
[Bn 65 00]  RPN MSB = 00
[Bn 06 mm]  Data Entry MSB = number of Member Channels (LSB unused)

n  = 0x0 → Lower Zone master (ch 1);  n = 0xF → Upper Zone master (ch 16); other n invalid
mm = 0   → zone off;  mm = 1..F → that many member channels
```

Canonical example from the spec — enable Lower Zone with 7 member channels (ch 2–8) and switch the Upper Zone off ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)):

```
B0 79 00      ; Reset All Controllers on the zone master (spec's example precedes MCM with this)
B0 64 06
B0 65 00
B0 06 07
BF 79 00
BF 64 06
BF 65 00
BF 06 00
```

Upper Zone with 15 members (ch 1–15): `BF 79 00 / BF 64 06 / BF 65 00 / BF 06 0F` — channel 1 becomes a member because the Lower Zone is unallocated ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).

Ordering note: the spec examples show **RPN LSB (CC 100 = 0x64) then RPN MSB (CC 101 = 0x65)**, and note "If using Running Status, omit bytes in parenthesis" ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)). Real receivers differ; Bitwig explicitly changed its transmitter in 5.2.5: "MPE: We now send MCM messages with the MSB (before the LSB)" ([Bitwig 5.2 release notes](https://www.bitwig.com/dl/Bitwig%20Studio/5.2.5/release_notes/)). **Recommendation: send both CC101 and CC100 immediately adjacent, MSB first, then Data Entry MSB — that order is what a modern DAW transmits and every receiver parses RPN pairs order-independently in practice.** [UNCERTAIN — ordering is not normatively fixed by the spec text.]

### 1.3 Pitch bend ranges (defaults and how to set them)

- Defaults on receipt of an MCM: **Member/per-note bend = ±48 semitones**, **Master/zone bend = ±2 semitones** — "it shall set the Manager Channel Pitch Bend Sensitivity to 2 semitones, and the Pitch Bend Sensitivity of every Member Channel to 48 semitones" ([MIDI.org: How MIDI MPE pitch bend works](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works)).
- Either range is changed with **RPN 0** (`00 00`), accepted range ±1…±96 semitones; whole semitones recommended, LSB transmitted as zero or omitted ([MIDI.org](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works), [RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- Master sensitivity is set by sending RPN 0 **to the master channel**; member sensitivity by sending RPN 0 **to every member channel individually** ([MIDI.org](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works)). Channels in one zone may not have different sensitivities; a receiver must apply the last member-channel RPN 0 to all members ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)). Bitwig now also does the belt-and-braces version: "We now send the pitch bend range for all channels (instead of just for channels 1 and 2)" ([Bitwig 5.2 release notes](https://www.bitwig.com/dl/Bitwig%20Studio/5.2.5/release_notes/)).
- At ±96 st, 14-bit bend granularity is still "smaller than 1.2 cents" ([MIDI.org](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works)).

### 1.4 The three dimensions

| Dimension | Message | Per note | Zone-wide |
|---|---|---|---|
| Pitch | Pitch Bend (14-bit) | member channel | master channel (default ±2 st) |
| Pressure | **Channel Pressure** (Dxh, 1 data byte, 0–127) | member channel | master channel |
| Timbre / "slide" / Y | **CC #74** | member channel | master channel |

([RP-053 Implementation Summary](https://midimpe.neocities.org/rp53spec.pdf)) Additional rules from the spec:

- **Polyphonic Key Pressure must not be sent on member channels** (reserved for a future extension); it may be used for notes on the master channel only ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- Channel Pressure "must be set to zero immediately before a Note On or a Note Off wherever appropriate to the design of the controller" ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- CC74 has two sanctioned interpretations: *initial-position* (value at note-on = physical position) or *initial-64*, where "its initial value must be 40h, or 64 decimal, so movement can proceed in either a positive or negative direction". Some devices use CC #75 for the static initial position ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)). The spec does **not** define a universal CC74 default; 64 is required only under initial-64.
- Per-note control **stops at Note Off**: "Per-note Pitch Bend must have no effect after Note Off", even during release/sustain. Master pitch bend keeps affecting releasing notes ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)). Bitwig fixed exactly this class of bug in 5.2.4: "Fixed note expression handling after note off" ([Bitwig 5.2 release notes](https://www.bitwig.com/dl/Bitwig%20Studio/5.2.5/release_notes/)).
- **Send initial state before Note On.** The pitch of a new note is set by the last bend value received on that channel before note-on; synths must track bend on idle channels. The spec recommends sending the initial bend before note-on "to avoid 'swooping' noises" ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).
- Note Off shorthand (note-on velocity 0) should be read as note-off velocity 64 ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).

Spec's own canonical note start — quarter-tone above middle C, timbre 64, on channel 3 ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)):

```
E2 2B 41   ; pitch bend, +50 cents at ±48 st sensitivity
B2 4A 40   ; CC74 = 64
D2 00      ; channel pressure = 0
92 3C 38   ; note on C4, velocity 56
```

### 1.5 Channel allocation / rotation

Spec guidance ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)):

- MPE assumes **MIDI Mode 3 (Omni Off, Poly)**; each channel is maximally polyphonic. A channel is *occupied* while it has ≥1 active note.
- "Simple circular assignment of new notes to Member Channels of a Zone will not usually provide satisfactory results." The simplest workable algorithm: **(1) assign a new note to the channel with the lowest count of active notes; (2) tie-break by oldest last Note Off.**
- Additionally, **prefer reusing the channel that most recently played the same note number** (once that note is in note-off state), to avoid "stacking and chorusing identical notes".
- When all channels are occupied, sharing a channel is preferable to dropping/stealing notes; a controller may pick the channel where the new note's bend requires the smallest pitch disturbance to other notes.
- Mode 4 (mono-per-channel, e.g. one channel per string) is also allowed; use the **Lower Zone** for Mode 4 ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)).

Reference allocator (spec-compliant, deterministic, what the compiler should use):

```python
from dataclasses import dataclass, field

@dataclass
class Alloc:
    members: list          # e.g. list(range(1, 16)) → MIDI channels 2..16 (0-based)
    active: dict = field(default_factory=dict)   # ch -> set of note numbers
    last_off: dict = field(default_factory=dict) # ch -> time of last note-off
    last_note: dict = field(default_factory=dict)# ch -> last note number played

    def __post_init__(self):
        for ch in self.members:
            self.active.setdefault(ch, set())
            self.last_off.setdefault(ch, -1.0)
            self.last_note.setdefault(ch, None)

    def acquire(self, note: int, t: float) -> int:
        free = [c for c in self.members if not self.active[c]]
        if free:
            # rule 3: prefer a free channel that last played this same note
            same = [c for c in free if self.last_note[c] == note]
            pool = same or free
            ch = min(pool, key=lambda c: (self.last_off[c],))   # oldest note-off first
        else:
            # rules 1+2: fewest active notes, then oldest note-off
            ch = min(self.members, key=lambda c: (len(self.active[c]), self.last_off[c]))
        self.active[ch].add(note)
        self.last_note[ch] = note
        return ch

    def release(self, ch: int, note: int, t: float) -> None:
        self.active[ch].discard(note)
        if not self.active[ch]:
            self.last_off[ch] = t
```

### 1.6 What each DAW actually does

**Ableton Live 11/12.**
- Recorded/edited per-note dimensions in the clip are exactly five: "Pitch (per-note pitch bend), Slide (per-note Y-Axis), Pressure (Poly Aftertouch/MPE Pressure), Velocity and Release Velocity (Note Off Velocity)" ([Live 12 manual, Editing MPE](https://www.ableton.com/en/live-manual/12/editing-mpe/)). Note Live's internal model is *note-scoped*: moving/stretching a note moves/stretches its envelopes.
- MPE input must be enabled per controller in Link/Tempo/MIDI settings; once enabled the track input channel routing is **forced to "All Channels"** ([Live 12 manual](https://www.ableton.com/en/live-manual/12/editing-mpe/), [MPE in Live 11 and later FAQ](https://help.ableton.com/hc/en-us/articles/360019144999-MPE-in-Live-11-and-later-FAQ)).
- Output side: an **MPE/Multi-channel Settings** dialog (Ext. Instrument device, mixer I/O section, or plug-in title-bar context menu) selects upper/lower zone and the number of note channels, or an arbitrary "multi-channel" range. Global channel is **ch 1 (lower) / ch 16 (upper)**; **one track can output to only one zone** ([Live 12 manual](https://www.ableton.com/en/live-manual/12/editing-mpe/)).
- "Live uses MIDI channel 1 as a global channel and will therefore never send notes on that channel in MPE mode" ([MPE Zone Configuration](https://help.ableton.com/hc/en-us/articles/4409113250322-MPE-Zone-Configuration)) — i.e. Live is a strict lower-zone transmitter by default, and mismatched channel counts cause *silent notes* with fixed-channel hardware (OB-6 = voices hard-wired to ch 2–7) and non-MPE multitimbral plug-ins (Omnisphere 8 parts → restrict to ch 1–8).
- All Live 12 instruments support MPE ("As of Live 12, all Live instruments support MPE"); in Live 11 the MPE devices were Drift, Wavetable, Sampler, Simpler (via Sampler), Arpeggiator, Analog, Tension, Collision, Electric ([MPE FAQ](https://help.ableton.com/hc/en-us/articles/360019144999-MPE-in-Live-11-and-later-FAQ)). Live 12 also added MPE MIDI Tools (Glissando, LFO) that generate pitch-bend envelopes ([Live 12 release notes](https://www.ableton.com/en/release-notes/live-12/)).
- Bend range: Live only states "the Pitch Bend range of your MPE controller and the MPE-capable instrument need to match for correct tracking" ([MPE FAQ](https://help.ableton.com/hc/en-us/articles/360019144999-MPE-in-Live-11-and-later-FAQ)); per-instrument "Note PB" is set in the device's MPE matrix. Live's selectable ranges are reported by users as ±2/12/24/36/48/60/72/84/96 st, per track ([Polyphonic Expression community thread](https://community.polyexpression.com/t/mpe-in-ableton-live-11/681/31)) — [UNCERTAIN, not vendor-documented].

**Bitwig Studio 5.x.** Bitwig does not model MPE as MIDI channels at all; it models **note expressions**: Micro-pitch ("a precise, polyphonic version of MIDI pitch bend, where each note played has its own pitch curve", range **±24 semitones**, semitone snapping on by default), Pressure (0…100 %, "similar to the idea of polyphonic key pressure"), Timbre (**bipolar**, −100…+100 %), plus Gain, Pan, Velocity, Chance ([Bitwig user guide, Working with Note Events](https://www.bitwig.com/userguide/latest/working_with_note_events)). Conversion to/from MIDI happens at the edges:
- Outbound to hardware: HW Instrument has a **`Use MPE`** option that "convert[s] note expressions to appropriate channel voice messages, dynamically allocating channels as necessary, and providing a pitch-bend range parameter" ([Bitwig user guide, Hardware](https://www.bitwig.com/userguide/latest/hardware)); introduced in 2.4 ("HW Instrument now has an MPE mode that outputs note expressions as MIDI channel voice messages and dynamically allocates MIDI channels") ([Bitwig 2.4 release notes](https://downloads.bitwig.com/stable/2.4.1/Release-Notes-2.4.1.html)).
- Plug-ins: MPE can be forced per plug-in from the device header context menu ([Bitwig user guide PDF 5.3](https://www.bitwig.com/media/bitwig_userguide/pdf/Bitwig_Studio_User_Guide_English_XfuP7Nz.pdf)); CLAP note expressions are used when the plug-in asks for them ("CLAP: Uses MIDI MPE if the plug-in asks for it") ([Bitwig 5.1 release notes](https://downloads.bitwig.com/5.1.3/Release-Notes-5.1.3.html)), and micro-pitch "will function properly with Bitwig's instrument devices, and they can work with CLAP plug-ins as well" ([Working with Note Events](https://www.bitwig.com/userguide/latest/working_with_note_events)).
- **Important asymmetry:** micro-pitch is ±24 st, while MPE's default member bend is ±48 st. Anything the compiler bends beyond ±24 st cannot be represented as a Bitwig micro-pitch curve.

**Logic Pro.** Logic implements MPE via **MIDI Mono Mode** on the instrument: "With MPE, every note and its messages are sent on a separate MIDI channel"; set the plug-in's extended parameter **MIDI Mono Mode → "On (with common base channel 1)"** and enter a value in **Mono Mode Pitch Range**; "each note and its control change messages are received on a different MIDI channel. MIDI messages sent on the base channel affect all notes being played"; polyphony max **15 notes**; supported instruments: Alchemy, EFM1, ES2, Quick Sampler, Retro Synth, Sampler, Sculpture, Vintage Clav; "the pitch bend ranges of the MPE controller and the Logic Pro instrument must be equal" ([Apple: Use MPE with software instruments in Logic Pro](https://support.apple.com/guide/logicpro/use-mpe-with-software-instruments-lgcp8f599497/mac)). Logic is therefore the **most literal channel-per-voice consumer** of the three: it wants exactly lower-zone base channel 1 + members 2–16, and it needs its Mono Mode Pitch Range set to whatever the compiler declares (48 by default).

---

## 2. Writing MPE into a Standard MIDI File

### 2.1 What the spec permits and what it doesn't say

RP-053 says nothing about MIDI file serialization ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)). It does say sequencer/DAW software may **dynamically reassign member channels during playback**, that channel numbers need not be preserved when editing in Poly Mode, and that per-channel bend/pressure/CC74 state must be tracked even with no note sounding so a new note gets a correct initial state ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)). So: an SMF holding channel-per-voice MPE is legal MIDI 1.0, but nothing guarantees a DAW will re-*interpret* it as note-scoped expression.

### 2.2 Recommended file layout (SMF type 1)

```
Header: format 1, division = 960 ticks per quarter note

Track 0  "conductor"  – tempo (set_tempo), time signature, track/marker names only
Track 1  "MPE config" – MCM + RPN 0 for master and every member channel, all at tick 0
Track 2  "zone notes" – ALL note + per-note expression events, channels 2..16 interleaved
                        (optionally: one track per member channel, see below)
```

Two viable variants for the note data:

1. **Single track, 15 channels (recommended default).** Robust: Logic imports channelised events verbatim into one region; Live's importer splits by track/channel; nothing depends on the writer's track partitioning. Live imports SMF0/SMF1/SMF2 ([Understanding MIDI files](https://help.ableton.com/hc/en-us/articles/209068169-Understanding-MIDI-files)).
2. **One track per member channel** (15 note tracks). Easier to inspect/debug and makes per-voice muting trivial in Logic's event list, but Live will import it as up to 15 separate MIDI tracks ("SMF1: MIDI data is stored in separate tracks/channels… the MIDI data appears in different tracks") ([Understanding MIDI files](https://help.ableton.com/hc/en-us/articles/209068169-Understanding-MIDI-files)) — usually not what the user wants. Offer it as a flag, not the default.

Ordering inside a tick (critical, from §1.4): for each note-on, emit **pitch bend → CC74 → channel pressure → note-on**; at note-off, emit **channel pressure 0 → note-off**; never emit per-note expression for a channel after that note's note-off.

### 2.3 Resolution / PPQN

- mido: `ticks_per_beat` is the file's PPQN; "typical values range from 96 to 480, although some files use more" ([mido: Standard MIDI Files](https://mido.readthedocs.io/en/stable/files/midi.html)).
- Use **960 PPQN** (or 480 if a consumer complains). At 120 BPM, 960 PPQN = 0.52 ms/tick, so a 5 ms expression grid is ~9.6 ticks — no rounding collisions between successive expression frames.
- Do not rely on Live for round-tripping: **Live exports SMF0 only, quantised to 96 ppq**, and warns "the position of MIDI information, like note and controller events, has changed when exporting" ([Understanding MIDI files](https://help.ableton.com/hc/en-us/articles/209068169-Understanding-MIDI-files)). 96 ppq ≈ 5.2 ms/tick at 120 BPM, which is right at the edge of the useful expression grid.

### 2.4 Known pitfalls

- **Live/Bitwig may not convert file channel data into note-scoped expression.** Neither vendor documents SMF→MPE conversion ([Live 12 manual](https://www.ableton.com/en/live-manual/12/editing-mpe/), [Bitwig exporting MIDI](https://www.bitwig.com/userguide/latest/exporting_midi)). Community tests report generated pitch bend in a `.mid` not producing per-note bends in Bitwig ([Music StackExchange](https://music.stackexchange.com/questions/105600/can-bitwig-recognize-pitch-bend-information-from-an-mid-file)), and "no conversion between MPE recorded data (recorded into Bitwig as pitch expression) & 'standard multichannel' MIDI with a single channel per note with pitch bend" ([KVR forum](https://www.kvraudio.com/forum/viewtopic.php?t=460902&start=60)). **[UNCERTAIN — this is the single biggest risk in the file path; test empirically per DAW version.]**
- Channel bend still *works* even without conversion, provided the receiving instrument is in a multi-channel/MPE mode: in Live that is MPE-mode/multi-channel plug-in settings ([MPE Zone Configuration](https://help.ableton.com/hc/en-us/articles/4409113250322-MPE-Zone-Configuration)); in Logic that is MIDI Mono Mode ([Apple](https://support.apple.com/guide/logicpro/use-mpe-with-software-instruments-lgcp8f599497/mac)). So the SMF path is really "channelised multi-timbral MIDI that happens to be MPE-shaped".
- **Export back out is lossy everywhere.** Bitwig's MIDI export "will include all notes present in your project's Arranger Timeline" ([Exporting MIDI](https://www.bitwig.com/userguide/latest/exporting_midi)); 5.3 added only "time-signature and tempo automation, as well as MIDI track automation of channel parameters (including sustain pedal)" ([Bitwig 5.3 release notes](https://www.bitwig.com/dl/Bitwig%20Studio/5.3.8/release_notes/)) — note expressions are not mentioned. Live exports SMF0 at 96 ppq, one clip at a time ([Understanding MIDI files](https://help.ableton.com/hc/en-us/articles/209068169-Understanding-MIDI-files)).
- **Interchange alternative: DAWproject.** Open XML container that explicitly lists "Notes Note Expressions" and "Note Expressions (using MPE)" among supported data; supported in Bitwig Studio 5.0.9, Studio One 6.5, Cubase 14, Cubasis 3.7.1, VST Live 2.2 ([Bitwig DAWproject FAQ](https://www.bitwig.com/support/technical_support/dawproject-file-format-faqs-62/)). No Logic or Live support. Worth considering as a second exporter *only* if Bitwig users demand true note-scoped expression.
- Drum-channel superstition: nothing in MPE reserves channel 10; but some tools (see pretty_midi below) still special-case it.
- Emit note-offs as real `note_off` (status 8n), not note-on-velocity-0, so note-off velocity survives (Live edits Release Velocity as a first-class dimension ([Live 12 manual](https://www.ableton.com/en/live-manual/12/editing-mpe/))).

### 2.5 Writer skeleton (mido, SMF type 1)

```python
import mido
from mido import Message, MetaMessage, MidiFile, MidiTrack

PPQ = 960
LOWER_MASTER = 0            # MIDI ch 1 (mido is 0-based: 0..15)
MEMBERS = list(range(1, 16))  # MIDI ch 2..16
BEND_RANGE_ST = 48

def rpn(ch, msb, lsb, value_msb, value_lsb=None):
    out = [Message('control_change', channel=ch, control=101, value=msb, time=0),
           Message('control_change', channel=ch, control=100, value=lsb, time=0),
           Message('control_change', channel=ch, control=6,   value=value_msb, time=0)]
    if value_lsb is not None:
        out.append(Message('control_change', channel=ch, control=38, value=value_lsb, time=0))
    # RPN null (127/127) closes the parameter so later CC6 can't be misread
    out += [Message('control_change', channel=ch, control=101, value=127, time=0),
            Message('control_change', channel=ch, control=100, value=127, time=0)]
    return out

def mpe_config_track():
    t = MidiTrack()
    t.append(MetaMessage('track_name', name='MPE Configuration', time=0))
    # MCM: lower zone, 15 member channels; upper zone off
    t += rpn(LOWER_MASTER, 0, 6, len(MEMBERS))
    t += rpn(15, 0, 6, 0)
    # RPN 0: master ±2 st, every member ±48 st
    t += rpn(LOWER_MASTER, 0, 0, 2, 0)
    for ch in MEMBERS:
        t += rpn(ch, 0, 0, BEND_RANGE_ST, 0)
    return t

def build(events, tempo_bpm=120.0):
    """events: list of (abs_seconds, mido.Message) with channels already allocated."""
    mid = MidiFile(type=1, ticks_per_beat=PPQ)
    tempo = mido.bpm2tempo(tempo_bpm)

    conductor = MidiTrack()
    conductor.append(MetaMessage('set_tempo', tempo=tempo, time=0))
    mid.tracks.append(conductor)
    mid.tracks.append(mpe_config_track())

    notes = MidiTrack()
    notes.append(MetaMessage('track_name', name='MPE Zone 1', time=0))
    prev = 0
    for sec, msg in sorted(events, key=lambda e: (e[0], _prio(e[1]))):
        tick = int(round(mido.second2tick(sec, PPQ, tempo)))
        notes.append(msg.copy(time=tick - prev))
        prev = tick
    mid.tracks.append(notes)
    return mid

def _prio(m):   # within a tick: expression before note-on, pressure-0 before note-off
    return {'pitchwheel': 0, 'control_change': 1, 'aftertouch': 2,
            'note_off': 3, 'note_on': 4}.get(m.type, 5)
```

`mido.second2tick(second, ticks_per_beat, tempo)` and `mido.bpm2tempo(bpm, time_signature=(4,4))` are the documented signatures ([mido API](https://mido.readthedocs.io/en/stable/api.html)); default MIDI tempo is 500000 µs/quarter ([mido SMF docs](https://mido.readthedocs.io/en/stable/files/midi.html)).

---

## 3. Python libraries

| Library | Pitch bend | Channel pressure | Per-channel control | macOS/Apple Silicon install | Verdict |
|---|---|---|---|---|---|
| **mido** ≥1.3 | `Message('pitchwheel', pitch=-8192..8191)` | `Message('aftertouch', value=0..127)` (+ `polytouch`) | full, explicit `channel=0..15` on every message | pure Python wheel; needs a backend only for realtime | **Use for file writing and as realtime front-end** |
| **python-rtmidi** ≥1.5 | raw bytes | raw bytes | full | prebuilt wheels incl. `arm64` (M1/M2), macOS ≥11.0, compiled with CoreMIDI | **Use as mido's realtime backend** |
| **pretty_midi** 0.2.11 | `PitchBend` per Instrument | **not supported at all** | **no** — channels auto-assigned | pure Python wheel | **Reject** |
| **mrmidi** | – | – | – | not on PyPI (`pip download mrmidi` → "No matching distribution found") | **Doesn't exist / unusable** |

Evidence:

- mido message vocabulary and ranges: `pitchwheel.pitch` = −8192…8191 (default 0); `aftertouch.value`, `polytouch.value`, `control_change.value` = 0…127; `channel` = 0…15 ("Mido numbers channels 0 to 15 instead of 1 to 16") ([mido: Message Types](https://mido.readthedocs.io/en/stable/message_types.html)). `velocity` defaults to 64.
- mido file API: `MidiFile(type=1)`, `ticks_per_beat`, in-track `time` = **delta ticks (integer)** ([mido SMF docs](https://mido.readthedocs.io/en/stable/files/midi.html)).
- python-rtmidi wheels: "Pre-compiled binary wheels … are available on PyPI for supported Python versions on Windows, macOS and Linux", macOS wheels "compiled with CoreMIDI support", available for "arm64 (a.k.a. M1/M2/Apple silicon), version 11.0 or later"; a C++ compiler/Xcode is needed **only** when no wheel matches ([python-rtmidi installation](https://spotlightkid.github.io/python-rtmidi/installation.html)).
- pretty_midi's writer assigns channels itself: `channels = list(range(16)); channels.remove(9)` then `channel = channels[n % len(channels)]` per instrument, and it only ever emits `program_change`, `note_on`, `pitchwheel`, `control_change` — there is no aftertouch/channel-pressure path at all ([pretty_midi source, `PrettyMIDI.write`](https://github.com/craffel/pretty-midi/blob/main/pretty_midi/pretty_midi.py)); default resolution is 220 PPQ (`PrettyMIDI(..., resolution=220)`), and its pitch-bend↔semitone helper defaults to a ±2 st range, which is wrong for MPE ([pretty-midi issue #229](https://github.com/craffel/pretty-midi/issues/229)). Any MPE use would require one `Instrument` per voice channel *and* out-of-band pressure — not worth it.

---

## 4. macOS realtime MIDI routing

### 4.1 Option A — virtual source straight out of Python (preferred)

python-rtmidi/CoreMIDI can publish a virtual port that DAWs see as a MIDI source; no driver setup, no Audio MIDI Setup:

```python
import mido
mido.set_backend('mido.backends.rtmidi')          # rtmidi is the default/recommended backend
port = mido.open_output('Filigree MPE', virtual=True, client_name='Filigree')
port.send(mido.Message('control_change', channel=0, control=101, value=0))  # ...MCM etc.
```

- `mido.open_output(name=None, virtual=False, autoreset=False, **kwargs)`; "Passing `virtual=True` opens a new port that other applications can connect to"; raises `IOError` if the backend can't do virtual ports ([mido API](https://mido.readthedocs.io/en/stable/api.html)).
- "RtMidi is the only backend that can create virtual ports"; virtual ports unavailable on Windows; `client_name=` (mido ≥1.2, python-rtmidi ≥1.0rc1) forces a virtual port and names the CoreMIDI client ([mido RtMidi backend](https://mido.readthedocs.io/en/latest/backends/rtmidi.html)).
- Underlying API: `MidiOut.open_virtual_port(self, name=None)`; a virtual port "is not connected to a physical MIDI device or system port when first opened" and is wired up with OS tools — for CoreMIDI, "the Audio & MIDI settings dialog"; default names are "RtMidi virtual input/output"; only one port per `MidiIn`/`MidiOut` instance; close by deleting the instance ([python-rtmidi API docs](https://spotlightkid.github.io/python-rtmidi/rtmidi.html)). Select CoreMIDI explicitly with `rtmidi.API_MACOSX_CORE` if several APIs are compiled in.
- Caveat: at least on Linux "RtMidi cannot see its own virtual ports" ([mido RtMidi backend](https://mido.readthedocs.io/en/latest/backends/rtmidi.html)) — so don't plan on a Python-to-Python loopback through your own virtual port; use IAC for that.

DAW hookup: the virtual port appears as an input device — Live: Link/Tempo/MIDI settings, enable Track/Remote **and MPE** for it ([Live 12 manual](https://www.ableton.com/en/live-manual/12/editing-mpe/)); Bitwig: Dashboard ▸ Settings ▸ Controllers (5.2.5 pops a notification for unknown ports and the track input chooser has an "Add MIDI Controller" submenu) ([Bitwig 5.2 release notes](https://www.bitwig.com/dl/Bitwig%20Studio/5.2.5/release_notes/)); Logic: the port is picked up automatically as a MIDI input — set the instrument's MIDI Mono Mode + pitch range ([Apple](https://support.apple.com/guide/logicpro/use-mpe-with-software-instruments-lgcp8f599497/mac)).

### 4.2 Option B — IAC Driver bus

Apple's documented procedure ([Audio MIDI Setup: Transfer MIDI information between apps](https://support.apple.com/guide/audio-midi-setup/transfer-midi-information-between-apps-ams1013/mac)):

1. Audio MIDI Setup ▸ **Window ▸ Show MIDI Studio**.
2. Double-click **IAC Driver**.
3. In Properties, tick **"Device is online"**.
4. Add/rename buses with the Add button (a bus is also called a *port*); set the number of MIDI In/Out connectors; **Apply**.
5. One app uses the bus as a destination (sender), another as a source (receiver).

Use IAC when the user wants a stable, pre-named endpoint that persists across compiler restarts, or when Python must both send and receive.

### 4.3 Latency and pacing

- CoreMIDI/IAC is in-memory, not 31250 baud, so the DIN bandwidth limit does not apply — but the *musical* limits still do: on a DIN-rate link a 3-byte message takes "nearly 1 millisecond", events on 16 channels can be delayed "by as much as 16 ms", and this is the classic source of "MIDI slop" ([Wikipedia: MIDI](https://en.wikipedia.org/wiki/MIDI)). Treat those numbers as the worst case if the user's chain ever touches hardware.
- Python is not sample-accurate: schedule with a monotonic clock, sleep in small slices, and pre-sort all events; keep the per-frame message count bounded (see §6.3). Bitwig's own hardware path exposes a per-port latency offset in samples, evidence that a few ms of jitter is expected and normally compensated downstream ([Bitwig user guide, Hardware](https://www.bitwig.com/userguide/latest/hardware)).
- For anything tighter than ~5 ms jitter, write an SMF and let the DAW sequence it.

---

## 5. MIDI 2.0 / per-note controllers in 2026 — do not target yet

- MIDI 2.0 channel voice adds 16-bit velocity, 32-bit controllers/pressure/pitch bend, **per-note controllers, per-note management and per-note pitch bend** — features with no MIDI 1.0 equivalent; "All future MIDI transports will be based on UMP" ([MIDI.org: The State of MIDI 2.0, Feb 2026](https://midi.org/the-state-of-midi-2-0-high-resolution-performance-and-the-rise-of-profiles-update-feb-2026)).
- Transports adopted: **USB MIDI 2.0 and UDP Network**; BLE MIDI 2.0 in progress; Web MIDI 2.0 only an aspiration ("We want to push W3C to adopt a Web MIDI 2.0 specification as well") ([MIDI.org](https://midi.org/the-state-of-midi-2-0-high-resolution-performance-and-the-rise-of-profiles-update-feb-2026)).
- File formats: MIDI Clip File spec (M2-116-U v1.0) published; **SMF2 container "soon to be finished"**, with a reference open-source implementation still being written ([MIDI.org](https://midi.org/the-state-of-midi-2-0-high-resolution-performance-and-the-rise-of-profiles-update-feb-2026)). There is no shipping SMF2 target for a compiler in 2026.
- DAW reality check: the Feb 2026 status page names Apple (AU), Avid (AAX), Bitwig (CLAP), Steinberg (VST) and JUCE as collaborators on MIDI-CI helper code, and describes three DAW Profiles as *planned*; **it does not state that any DAW has full MIDI 2.0 or per-note-controller support** ([MIDI.org](https://midi.org/the-state-of-midi-2-0-high-resolution-performance-and-the-rise-of-profiles-update-feb-2026)). At SUPERBOOTH 2026 the working demo was Cubase converting MIDI 2.0 note messages into **VST3 Note Expressions** over Network MIDI 2.0, with Apple and Microsoft having implemented Network MIDI 2.0 at OS level ([MIDI.org: SUPERBOOTH26](https://midi.org/superbooth26-shows-midi-2-0-becoming-reality)).
- Notably, the MIDI Association's own plan is for helper software to extract information plug-ins need "to support the Orchestral Articulation Profile, **MPE**, and the Piano Profile" ([MIDI.org](https://midi.org/the-state-of-midi-2-0-high-resolution-performance-and-the-rise-of-profiles-update-feb-2026)) — i.e. MPE remains the interop layer.

**Decision: emit MPE over MIDI 1.0. Keep the expression model abstract (per-note float envelopes) so a UMP/MIDI-2.0 backend can be added later without touching the compiler front end.**

---

## 6. Practical numerics

### 6.1 Pitch bend, 14-bit

- Wire format: `En lsb msb`, value = `128 * MSB + LSB`, range **0…16383**, centre **8192** (`00 40` as LSB,MSB), and it behaves as a signed 14-bit quantity −8192…+8191 ([François Georgy: MIDI Pitch Bend](https://www.francoisgeorgy.ch/midi/midi-pitch-bend/)). mido hides this: `Message('pitchwheel', pitch=-8192..8191)`, 0 = centre ([mido message types](https://mido.readthedocs.io/en/stable/message_types.html)).
- Scale factor: `values_per_semitone = 8192 / bend_range` → at ±48 st, **170.67 units/semitone** (±171 ≈ 1 st, ±2048 = 1 octave) ([François Georgy](https://www.francoisgeorgy.ch/midi/midi-pitch-bend/)).
- Resolution at ±48 st: `48 * 100 / 8192 ≈ 0.586 cents` per LSB; at ±96 st ≈ 1.17 cents, consistent with the spec's "smaller than 1.2 cents" ([MIDI.org](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works)).

```python
def semitones_to_bend(st: float, bend_range: int = 48) -> int:
    """→ mido pitchwheel value (-8192..8191), clamped."""
    v = int(round(st / bend_range * 8192.0))
    return max(-8192, min(8191, v))

def bend_bytes(v: int) -> tuple[int, int]:
    """→ (lsb, msb) wire bytes for status En."""
    u = max(0, min(16383, v + 8192))
    return u & 0x7F, (u >> 7) & 0x7F
```

### 6.2 Other ranges

| Datum | Range | Notes |
|---|---|---|
| Pitch bend | 0…16383 (centre 8192) | 14-bit ([François Georgy](https://www.francoisgeorgy.ch/midi/midi-pitch-bend/)) |
| Channel pressure (`Dn vv`) | **0…127**, 7-bit, single data byte | mido `aftertouch.value` 0…127 ([mido](https://mido.readthedocs.io/en/stable/message_types.html)); set to 0 immediately before note-on and note-off ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)) |
| CC74 timbre | **0…127**, 7-bit | initial 64 (`0x40`) under the initial-64 convention; no 14-bit MSB/LSB pairing is defined ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)) |
| Velocity / release velocity | 0…127 | note-on-velocity-0 note-offs should be read as release velocity 64 ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)) |
| Master (zone) bend | ±2 st default | ([MIDI.org](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works)) |

Bitwig mapping when authoring for its expression model: micro-pitch ±24 st, pressure 0…100 %, timbre −100…+100 % (bipolar, i.e. CC74 64 = 0 %) ([Bitwig user guide](https://www.bitwig.com/userguide/latest/working_with_note_events)).

### 6.3 Sampling an LFO / bend curve without flooding

Budget reasoning: a 3-byte message is ~1 ms on a DIN-rate link, and simultaneous traffic on many channels compounds into "as much as 16 ms" of skew ([Wikipedia: MIDI](https://en.wikipedia.org/wiki/MIDI)). The MPE spec sets no rate limit but does say zone-wide messages should go on the master channel only "to reduce MIDI traffic and make event editing easier" ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)). Practical policy:

- **Grid: 5 ms (200 Hz) for pitch, 10 ms (100 Hz) for pressure and CC74.** A 6 Hz vibrato at 5 ms gives ~33 samples/cycle — far above audible stepping.
- **Global ceiling ≈ 1000 messages/s** across the zone (≈1 ms/message worst case). With 8 sounding voices that is ~40 pitch frames/s/voice after thinning; enforce it by widening the grid when polyphony is high.
- **Deduplicate**: never emit a value equal to the last emitted value on that channel (per message type). For pitch, quantise to the 14-bit integer first, so sub-LSB motion vanishes automatically.
- **Deadband + linear-prediction thinning**: drop a frame when the receiver's linear interpolation of the previous two emitted points already lands within tolerance (2 LSB ≈ 1.2 cents at ±48 st for pitch; 1 step for 7-bit CCs).
- **Always emit** the first frame of a note (before note-on), the last frame before note-off, every local extremum, and pressure 0 before note-on/off — otherwise curves lose their peaks.

```python
def thin(frames, tol=2, min_dt=0.005, force_idx=()):
    """frames: [(t_seconds, int_value)] monotonic in t → thinned list.
    Keeps first/last, forced indices, extrema, and any point whose value
    deviates from linear prediction by more than `tol`."""
    if len(frames) <= 2:
        return list(frames)
    out = [frames[0]]
    for i in range(1, len(frames) - 1):
        t, v = frames[i]
        pt, pv = out[-1]
        nt, nv = frames[i + 1]
        is_extremum = (v - pv) * (nv - v) < 0
        if i in force_idx or is_extremum:
            out.append((t, v)); continue
        if t - pt < min_dt:                      # rate limit
            continue
        span = nt - pt
        pred = pv if span <= 0 else pv + (nv - pv) * (t - pt) / span
        if abs(v - pred) > tol or v == pv:
            if v != pv:
                out.append((t, v))
    out.append(frames[-1])
    return out

def vibrato(dur, rate_hz, depth_st, grid=0.005, bend_range=48):
    import math
    n = int(dur / grid) + 1
    raw = [(i * grid,
            semitones_to_bend(depth_st * math.sin(2 * math.pi * rate_hz * i * grid),
                              bend_range))
           for i in range(n)]
    return thin(raw, tol=2, min_dt=grid, force_idx={0, n - 1})
```

Measured on this implementation: 1 s of 6 Hz vibrato at ±0.25 st on a 5 ms grid = 201 raw frames → **38 emitted pitch-bend messages** (≈5× reduction) with extrema preserved.

Note-lifecycle helper (spec-ordered):

```python
def note_events(t0, t1, ch, note, vel, bend_curve, cc74_curve, pres_curve, rel_vel=64):
    ev = [(t0, Message('pitchwheel', channel=ch, pitch=bend_curve[0][1])),
          (t0, Message('control_change', channel=ch, control=74, value=cc74_curve[0][1])),
          (t0, Message('aftertouch', channel=ch, value=0)),
          (t0, Message('note_on', channel=ch, note=note, velocity=vel))]
    for t, v in bend_curve[1:]:
        if t0 < t0 + t < t1: ev.append((t0 + t, Message('pitchwheel', channel=ch, pitch=v)))
    for t, v in cc74_curve[1:]:
        if t0 < t0 + t < t1: ev.append((t0 + t, Message('control_change', channel=ch, control=74, value=v)))
    for t, v in pres_curve:
        if t0 <= t0 + t < t1: ev.append((t0 + t, Message('aftertouch', channel=ch, value=v)))
    ev.append((t1, Message('aftertouch', channel=ch, value=0)))       # pressure → 0 before note off
    ev.append((t1, Message('note_off', channel=ch, note=note, velocity=rel_vel)))
    return ev                                                          # no per-note data after t1
```

---


> **Correction (round 2, appended by the P4 builder — nothing above is deleted).**
> The "linear-prediction thinning" bullet and the `thin()` sketch above are **not
> sourced**: no clause of RP-053 and no line of the MIDI 1.0 spec says a receiver
> interpolates between transmitted pitch-bend / channel-pressure / CC values.
> MIDI 1.0 continuous controllers are **hold-last-value**: the receiver keeps the
> last value it was sent until the next message arrives (the tuning-relevant
> statement in the sources cited in this file is only about *resolution* — "<1.2
> cents granularity" at ±48 st, [MIDI.org on MPE pitch bend](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works)
> — never about interpolation). Budgeting thinning error against a linear
> reconstruction therefore understates what a synth actually hears: a straight
> ramp thinned "to its endpoints" is heard as a step, and the critic's round-1
> probe measured up to 98.75 cents of hold error against a 3-cent bar for a
> stream that was within 3 cents under the interpolating model.
>
> The renderer now budgets **zero-order-hold** error instead: after thinning, for
> every grid sample `t` in a note's lifetime,
> `|value_held(t) - value_true(t)| <= tol` (default 3 cents for bend, 1 LSB for
> 7-bit lanes), with the grid interval as the minimum spacing. Between grid
> samples the residual is bounded by the curve's own motion across one emission
> interval — the sampler's resolution floor, reported as `grid_floor_cents`.
> The `min_dt` rate limit, the deduplication rule and the "emit every extremum"
> rule above all survive unchanged; only the error metric changed.
> See `NOTES_P4.md` "round 2" and `src/filigree/mpe.py` (`thin`, `hold_error`,
> `hold_budget_cents`).

## 7. Optional: browser previews and JS MIDI writers

- **Web MIDI API is not an option for Safari.** caniuse lists Safari 3.1–27/TP and iOS Safari as *not supported*, while Chrome 43+, Edge 79+, Firefox 108+ and Opera 30+ support it ([caniuse: Web MIDI API](https://caniuse.com/midi)). So a browser preview must synthesise audio itself (Web Audio) rather than drive an external MPE synth, unless the user is on Chrome/Firefox.
- **Web Audio MPE-aware preview design**: one voice = one `OscillatorNode`/`AudioWorklet` voice; per-note pitch = `detune.setValueAtTime()`/`linearRampToValueAtTime()` in cents driven by the same bend curve (cents = `semitones * 100`); pressure → a per-voice `GainNode` and/or filter cutoff; CC74 → a per-voice filter/wavefolder parameter, bipolar around 64. Because Web Audio parameter automation is per-node, the MPE channel-allocation problem disappears in the browser — schedule the compiler's per-note envelopes directly and skip channelisation for previews. See the Web Audio API parameter-automation model ([MDN: Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)); the Web MIDI spec itself is at [W3C Web MIDI API](https://webaudio.github.io/web-midi-api/).
- **JS SMF writers**:
  - `midi-file` (npm) — low-level `parseMidi(input)` / `writeMidi(parsed)` over a `{header, tracks:[[events]]}` structure, with options `{running: true}` for running status and `{useByte9ForNoteOff: true}`; because you hand it raw event objects it is the only one of these that can express arbitrary channel-voice events such as pitch bend and channel aftertouch ([npm: midi-file](https://www.npmjs.com/package/midi-file)). **Recommended for a JS-side MPE writer.**
  - `MidiWriterJS` — "expressive multi-track MIDI files", `NoteEvent` has a `channel` option, `ProgramChangeEvent`, `Track.addEvent()`, `Writer(tracks).buildFile()/base64()/dataUri()`; **pitch bend and aftertouch are not documented** ([MidiWriterJS README](https://github.com/grimmdude/MidiWriterJS)).
  - `@tonejs/midi` — `new Midi()`, `addTrack()`, `addNote()`, `addCC()`, `toArray()`; control changes only, **no documented pitch-bend or channel-pressure API** ([Tonejs/Midi](https://github.com/Tonejs/Midi)).

---

## 8. Recommended defaults for the compiler (summary table)

| Decision | Value | Source |
|---|---|---|
| Zone | Lower zone, master ch 1, members ch 2–16 (15 voices) | ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)); Live never sends notes on ch 1 ([Ableton](https://help.ableton.com/hc/en-us/articles/4409113250322-MPE-Zone-Configuration)); Logic base channel 1, max 15 notes ([Apple](https://support.apple.com/guide/logicpro/use-mpe-with-software-instruments-lgcp8f599497/mac)) |
| Configuration | MCM RPN 00 06 on ch 1 (mm=15) + RPN 00 06 mm=0 on ch 16; RPN 0 = 2 st on ch 1; RPN 0 = 48 st on each of ch 2–16; null-RPN after each | ([RP-053](https://midimpe.neocities.org/rp53spec.pdf), [MIDI.org](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works), [Bitwig 5.2.5](https://www.bitwig.com/dl/Bitwig%20Studio/5.2.5/release_notes/)) |
| Per-note bend range | ±48 st (configurable; expose ±24 for Bitwig-first projects) | ([MIDI.org](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works)); Bitwig micro-pitch is ±24 ([Bitwig](https://www.bitwig.com/userguide/latest/working_with_note_events)) |
| Note-on preamble | bend → CC74 (default 64) → pressure 0 → note-on | ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)) |
| Allocation | fewest-active-notes, tie-break oldest note-off, prefer channel that last played same note | ([RP-053](https://midimpe.neocities.org/rp53spec.pdf)) |
| SMF | type 1, 960 PPQN, conductor + config + notes tracks, real note_off events | ([mido](https://mido.readthedocs.io/en/stable/files/midi.html)); Live imports SMF0/1/2 ([Ableton](https://help.ableton.com/hc/en-us/articles/209068169-Understanding-MIDI-files)) |
| Expression grid | 5 ms pitch / 10 ms pressure+timbre, dedup + 2-LSB deadband, ≤1000 msg/s | ([Wikipedia: MIDI](https://en.wikipedia.org/wiki/MIDI), [RP-053](https://midimpe.neocities.org/rp53spec.pdf)) |
| Libraries | mido (+ python-rtmidi backend); no pretty_midi | ([mido](https://mido.readthedocs.io/en/stable/message_types.html), [python-rtmidi](https://spotlightkid.github.io/python-rtmidi/installation.html), [pretty_midi source](https://github.com/craffel/pretty-midi/blob/main/pretty_midi/pretty_midi.py)) |
| Realtime | `mido.open_output('Filigree MPE', virtual=True)`; IAC bus as fallback | ([mido API](https://mido.readthedocs.io/en/stable/api.html), [python-rtmidi](https://spotlightkid.github.io/python-rtmidi/rtmidi.html), [Apple AMS](https://support.apple.com/guide/audio-midi-setup/transfer-midi-information-between-apps-ams1013/mac)) |
| MIDI 2.0 | not targeted in 2026; keep expression model backend-agnostic | ([MIDI.org Feb 2026](https://midi.org/the-state-of-midi-2-0-high-resolution-performance-and-the-rise-of-profiles-update-feb-2026), [SUPERBOOTH26](https://midi.org/superbooth26-shows-midi-2-0-becoming-reality)) |

## 9. Open questions to settle by experiment

1. Does Live 12.x / Bitwig 5.x convert channel-per-voice SMF data into note-scoped expression on import, or only pass channel messages through to a multi-channel instrument? Undocumented; community evidence says the latter ([Music StackExchange](https://music.stackexchange.com/questions/105600/can-bitwig-recognize-pitch-bend-information-from-an-mid-file), [KVR](https://www.kvraudio.com/forum/viewtopic.php?t=460902&start=60)). **Test matrix: SMF → Live (Wavetable, MPE on) / Bitwig (Polymer + CLAP) / Logic (Alchemy, MIDI Mono Mode).**
2. Whether any of the three honours a **file-embedded MCM/RPN** at all, or whether the zone must be configured in the DAW UI. Not documented by any vendor.
3. Exact MCM byte order accepted by each DAW's receiver (MSB-first vs spec's LSB-first) — Bitwig's own change log suggests MSB-first is the safer transmit order ([Bitwig 5.2.5](https://www.bitwig.com/dl/Bitwig%20Studio/5.2.5/release_notes/)).
4. Live's exact selectable per-instrument Note-PB values (community-reported ±2…±96) ([Polyphonic Expression](https://community.polyexpression.com/t/mpe-in-ableton-live-11/681/31)).
