import pplx_sdk, json
Q = [
 "TidalCycles syntax pattern language",
 "Strudel web live coding docs",
 "Sonic Pi tutorial syntax",
 "FoxDot python live coding",
 "Gibber live coding javascript",
 "Mercury live coding language",
 "Alda music programming language syntax",
 "Ziffers numeric notation live coding",
 "Orca esoteric programming sequencer",
 "Glicol graph oriented live coding language",
 "LilyPond notation syntax tutorial",
 "ABC notation standard 2.1",
 "MusicXML specification",
 "GUIDO music notation format",
 "Bol Processor grammar music",
 "SuperCollider patterns Pbind tutorial",
 "Csound score f-table statements",
]
out=[]
for e in pplx_sdk.search.web_many(Q, limit_per_query=6):
    row={"q":e.spec.get("query") if isinstance(e.spec,dict) else str(e.spec),"ok":e.ok,
         "hits":[{"u":h.url,"t":h.title,"s":(h.snippet or "")[:300]} for h in (e.result or [])] if e.ok else []}
    out.append(row)
open("/home/user/workspace/filigree/research/s1.json","w").write(json.dumps(out,indent=1))
for r in out:
    print("##",r["q"])
    for h in r["hits"]: print(" ",h["u"],"|",h["t"])
