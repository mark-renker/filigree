import pplx_sdk, json
P = ("Extract concrete named features, verbatim syntax/parameter names, and stated limitations relevant to: "
     "(a) chord/scale/progression/voice-leading generation and reharmonization; (b) continuous per-note expression "
     "(bend, vibrato, pressure, timbre, CC curves, micro-timing, articulation); (c) MIDI/MPE output; (d) workflow speed. "
     "Include short verbatim examples.")
U = [
 "https://strudel.cc/learn/tonal/",
 "https://strudel.cc/understand/voicings/",
 "https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output",
 "https://lilypond.org/doc/v2.25/Documentation/usage/midi-articulation",
 "https://www.musicxml.com/publications/makemusic-recordare/max-2002/musicxml-translation-issues/",
 "https://www.hooktheory.com/support/hookpad",
 "https://scalermusic.com/products/scaler-3/",
 "https://xferrecords.com/products/cthulhu",
 "https://www.waproduction.com/plugins/view/instachord-2",
 "https://rapidcomposer.com/features.html",
 "https://www.landr.com/plugins/producer-suite-3",
 "https://mixedinkey.com/captain-plugins/version-7/",
 "https://www.musicdevelopments.com/melodya.html",
 "https://www.bitwig.com/userguide/latest/note_fx",
 "https://www.steinberg.help/r/dorico-pro/6.1/en/dorico/topics/library/library_expression_maps_dialog_r.html",
 "https://github.com/sonic-pi-net/sonic-pi/blob/dev/etc/doc/tutorial/11.2-MIDI-Out.md",
 "https://midi.org/the-state-of-midi-2-0-high-resolution-performance-and-the-rise-of-profiles-update-feb-2026",
 "https://www.guitar-pro.com/blog/p/12520-bends-and-vibrato-in-guitar-pro-6",
 "https://www.nonlinear-labs.de/support/help/docs/C15-Synth-Engine-1.7.pdf",
]
res = pplx_sdk.content.fetch_many(U, prompt=P)
out=[]
for u,e in zip(U,res):
    r = (e.result[0] if isinstance(e.result,list) else e.result) if e.ok and e.result else None
    out.append({"url":u,"content":getattr(r,"content",None) if r else None,"err":(getattr(r,"error",None) if r else str(e.error))})
open("/home/user/workspace/filigree/research/f3.json","w").write(json.dumps(out,indent=1))
for o in out:
    print("\n======",o["url"]); print((o["content"] or o["err"] or "")[:1900])
