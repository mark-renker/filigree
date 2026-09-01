import pplx_sdk
OUT="refs/syntax/rival_docs"
jobs=[
 ("sonicpi_midi_pitch_bend","https://sunderb.me/sonic-pi-docs-test/en/reference/lang/midi_pitch_bend.html"),
 ("sonicpi_chord","https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord.html"),
 ("sonicpi_chord_degree","https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_degree.html"),
 ("sonicpi_control","https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html"),
 ("strudel_synths_vib","https://strudel.cc/learn/synths/"),
 ("tidal_oscillators","https://tidalcycles.org/docs/reference/oscillators/"),
 ("alda_attributes","https://alda.readthedocs.io/en/latest/attributes/"),
 ("alda_tutorial","https://alda.io/tutorial/"),
 ("alda_cheatsheet","https://alda.io/cheat-sheet/"),
 ("lilypond_midi_creating","https://lilypond.org/doc/v2.25/Documentation/notation/creating-midi-output"),
]
res=pplx_sdk.content.fetch([u for _,u in jobs])
for (n,u),r in zip(jobs,res):
    t=r.content or ("ERROR: "+str(r.error))
    open(f"{OUT}/{n}.md","w").write(f"# {n}\nSource: {u}\nFetched: 2026-08-30\n\n{t}\n")
    print(n,len(t))
