import pplx_sdk, json
Q = [
 "Scaler 3 plugin features chord",
 "Captain Plugins Epic Mixed In Key",
 "Xfer Cthulhu chord arpeggiator",
 "InstaChord 2 plugin",
 "Hooktheory Hookpad features",
 "RapidComposer software features",
 "Orb Producer Suite 3",
 "Melodya plugin melody generator",
 "Nonlinear Labs C15 synthesizer expression",
 "Bitwig note FX operators",
 "MPE support Bitwig Studio per-note expression",
 "Logic Pro MPE support per-note",
 "Expressive E Noise app",
 "ROLI Seaboard MPE dimensions",
 "MIDI 2.0 per-note controllers specification",
 "Cubase expression maps VST expression",
 "Dorico playback expression maps",
 "SFZ format opcodes modulation",
 "MNX music notation W3C draft",
 "MIDI Polyphonic Expression specification MPE",
]
out=[]
for e in pplx_sdk.search.web_many(Q, limit_per_query=6):
    row={"q":e.spec.get("query") if isinstance(e.spec,dict) else str(e.spec),"ok":e.ok,
         "hits":[{"u":h.url,"t":h.title,"s":(h.snippet or "")[:300]} for h in (e.result or [])] if e.ok else []}
    out.append(row)
open("/home/user/workspace/filigree/research/s2.json","w").write(json.dumps(out,indent=1))
for r in out:
    print("##",r["q"])
    for h in r["hits"]: print(" ",h["u"],"|",h["t"])
