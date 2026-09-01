import pplx_sdk
OUT="refs/syntax/rival_docs"
jobs=[
 ("ziffers_wiki_chords","https://github.com/amiika/ziffers/wiki/Chords","Verbatim: roman numeral chords, chord extensions (+n), named chord suffixes, inversions (%n), modal interchange letters a-g table, voice leading <lead> transformation, arpeggio list syntax, and options passed to zplay/z1."),
 ("ziffers_wiki_effects","https://github.com/amiika/ziffers/wiki/Effects","Verbatim: all documented effects/opts Ziffers supports and how Sonic Pi synth opts are passed through, including any slide/vibrato/pitch related opts."),
 ("ziffers_wiki_rhythm","https://github.com/amiika/ziffers/wiki/Rhythm","Verbatim: note length characters, subdivision, decimal durations, and any articulation/expression syntax."),
 ("ziffers_wiki_basic","https://github.com/amiika/ziffers/wiki/Basic-syntax","Verbatim: pitches, octaves, accidentals, rests, escaped octaves, and any per-note option syntax."),
 ("strudel_understand_voicings","https://strudel.cc/understand/voicings/","Verbatim: how voicing/voicings work, the dictionaries available ('ireal','lefthand','triads'), anchor/mode defaults, and the claim about smoothest voice leading."),
]
res=pplx_sdk.content.fetch([u for _,u,_ in jobs], prompt=None)
for (n,u,p),r in zip(jobs,res):
    t=r.content or ("ERROR: "+str(r.error))
    open(f"{OUT}/{n}.md","w").write(f"# {n}\nSource: {u}\nFetched: 2026-08-30\n\n{t}\n")
    print(n,len(t))
