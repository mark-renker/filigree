import pplx_sdk, json
P = ("Extract, with concrete syntax/code examples: (1) the syntax paradigm of this language/tool; "
     "(2) a short representative code example; (3) how continuous per-note expression is written "
     "(pitch bend, vibrato, pressure, timbre/CC curves, micro-timing, articulation) and any limits; "
     "(4) how chords, chord progressions, voice leading, or scale/harmony are expressed; "
     "(5) MIDI / MPE output capability and named limitations. Quote actual syntax verbatim where possible.")
U = [
 "https://tidalcycles.org/docs/reference/patterns/",
 "https://strudel.cc/learn/getting-started/",
 "https://sonic-pi.net/tutorial.html",
 "https://github.com/Qirky/FoxDot",
 "https://github.com/gibber-cc/gibberwocky.midi",
 "https://tmhglnd.github.io/mercury/docs/",
 "https://alda.io/tutorial/",
 "https://github.com/amiika/ziffers",
 "https://github.com/hundredrabbits/Orca",
 "https://github.com/chaosprint/glicol/blob/main/README.md",
 "https://abcnotation.com/wiki/abc:standard:v2.1",
 "https://wiki.ccarh.org/wiki/Guido_Music_Notation",
 "https://bolprocessor.org/bol-processor-grammars/",
 "https://depts.washington.edu/dxscdoc/Help/Tutorials/A-Practical-Guide/PG_03_What_Is_Pbind.html",
 "https://csound.com/manual/scoregens/f/",
]
res = pplx_sdk.content.fetch_many(U, prompt=P)
out=[]
for u,e in zip(U,res):
    if e.ok and e.result:
        r = e.result[0] if isinstance(e.result,list) else e.result
        out.append({"url":u,"content":getattr(r,"content",None),"err":getattr(r,"error",None)})
    else:
        out.append({"url":u,"content":None,"err":str(e.error)})
open("/home/user/workspace/filigree/research/f1.json","w").write(json.dumps(out,indent=1))
for o in out:
    print("\n======",o["url"]); print((o["content"] or o["err"] or "")[:3500])
