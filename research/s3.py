import pplx_sdk, json
Q = ["TidalCycles MPE support per note pitch bend",
     "Strudel voicings chords documentation",
     "LilyPond MIDI output articulate limitations",
     "MusicXML limitations performance expression",
     "Dorico expression map switches conditions",
     "Sonic Pi midi out cc pitch bend",
     "Ziffers voice leading chord progressions",
     "Scaler 3 voice grouping performances MIDI capture",
     "Hookpad borrowed chords magic chord reharmonize",
     "RapidComposer phrase variation generator chord",
     "MIDI 2.0 per note pitch bend registered controllers",
     "why MPE editing tedious DAW piano roll",
     "text based music notation expression bend Guitar Pro ASCII tab",
     "Csound score envelope pfields expression per note",
     "ChucK music programming language",
]
out=[]
for e in pplx_sdk.search.web_many(Q, limit_per_query=6):
    print("##", e.spec)
    if e.ok:
        for h in e.result: print("  ",h.url,"|",h.title,"|",(h.snippet or "")[:200].replace("\n"," "))
