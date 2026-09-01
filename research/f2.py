import pplx_sdk, json
P = ("Extract concrete facts and verbatim syntax/parameter names about: continuous or per-note expression "
     "(pitch bend, vibrato, pressure, timbre, CC automation curves, micro-timing, articulation), "
     "chord/harmony/voice-leading features, and MIDI or MPE output/limitations. Include code or config examples verbatim.")
U = [
 "https://tidalcycles.org/docs/configuration/MIDIOSC/midi/",
 "https://strudel.cc/learn/signals/",
 "https://strudel.cc/learn/input-output/",
 "https://strudel.cc/learn/chords/",
 "https://sonic-pi.net/tutorial.html#section-12",
 "https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks",
 "https://www.w3.org/2021/06/musicxml40/tutorial/chord-symbols/",
 "https://w3c.github.io/mnx/docs/",
 "https://sfzformat.com/opcodes/",
 "https://midi.org/mpe-midi-polyphonic-expression",
 "https://polyphonicexpression.com/mpe-how-it-works",
 "https://www.bitwig.com/userguide/latest/operators",
 "https://polarity.me/posts/bitwig-guides/2022-05-31-expressions-bitwig-modulator-guide/",
 "https://www.steinberg.help/r/cubase-pro/14.0/en/cubase_nuendo/topics/expression_maps/expression_maps_c.html",
 "https://support.apple.com/guide/logicpro/use-mpe-with-software-instruments-lgcp8f599497/mac",
]
res = pplx_sdk.content.fetch_many(U, prompt=P)
out=[]
for u,e in zip(U,res):
    r = (e.result[0] if isinstance(e.result,list) else e.result) if e.ok and e.result else None
    out.append({"url":u,"content":getattr(r,"content",None) if r else None,"err":(getattr(r,"error",None) if r else str(e.error))})
open("/home/user/workspace/filigree/research/f2.json","w").write(json.dumps(out,indent=1))
for o in out:
    print("\n======",o["url"]); print((o["content"] or o["err"] or "")[:2200])
