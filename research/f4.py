import pplx_sdk, json
P = ("Extract verbatim syntax examples and named features about how this system writes notes, chords/harmony, "
     "and any continuous expression (bend, vibrato, pressure, timbre, CC, micro-timing, articulation), plus MIDI/MPE output "
     "and any stated design goals or limitations.")
U = [
 "https://github.com/tmhglnd/mercury-examples",
 "https://iclc.toplap.org/2019/papers/paper67.pdf",
 "https://ziffers.world/",
 "https://www.w3.org/2021/06/musicxml40/tutorial/percussion/",
 "https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/bend/",
 "https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/harmony/",
 "https://www.expressivee.com/88-noisy-two",
 "https://bolprocessor.org/modelling-music-with-grammars/",
 "https://csound.com/manual/reference/scoreStatementsRef/",
 "https://studiocode.dev/resources/mpe/",
]
res = pplx_sdk.content.fetch_many(U, prompt=P)
out=[]
for u,e in zip(U,res):
    r = (e.result[0] if isinstance(e.result,list) else e.result) if e.ok and e.result else None
    out.append({"url":u,"content":getattr(r,"content",None) if r else None,"err":(getattr(r,"error",None) if r else str(e.error))})
open("/home/user/workspace/filigree/research/f4.json","w").write(json.dumps(out,indent=1))
for o in out:
    print("\n======",o["url"]); print((o["content"] or o["err"] or "")[:1800])
