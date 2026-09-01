import pplx_sdk
OUT="refs/syntax/rival_docs"
jobs=[
 ("sonicpi_midi_out","https://raw.githubusercontent.com/sonic-pi-net/sonic-pi/dev/etc/doc/tutorial/11.2-MIDI-Out.md","Extract verbatim all documented MIDI out functions and options: midi_note_on, midi_note_off, midi_cc, midi_pitch_bend, port:, channel:, value ranges, and code examples."),
 ("sonicpi_slide","https://raw.githubusercontent.com/sonic-pi-net/sonic-pi/dev/etc/doc/tutorial/07.2-Slide.md","Extract verbatim the documentation of *_slide options, control, and code examples, including note_slide, cutoff_slide, slide shape/curve options if documented."),
 ("sonicpi_chords","https://raw.githubusercontent.com/sonic-pi-net/sonic-pi/dev/etc/doc/tutorial/05.2-Chords.md","Extract verbatim documentation of chord, chord_degree, play_chord, chord inversion/invert options and examples."),
 ("ziffers_readme","https://raw.githubusercontent.com/amiika/ziffers/main/README.md","Extract verbatim the syntax cheatsheet: pitches, durations, chords, roman numeral chords, named chords, modal interchange letters, repeats, transformations, key/scale options, and how zplay/zloop are called with Sonic Pi opts, plus any vibrato/expression related opts."),
 ("lilypond_midi_articulation","https://lilypond.org/doc/v2.25/Documentation/usage/midi-articulation","Extract verbatim what articulate.ly does, which articulations it supports, how it is invoked (\\include \"articulate.ly\", \\articulate), and its documented limitations."),
 ("lilypond_expressive_marks","https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks","List verbatim the documented expressive marks: articulations, dynamics, hairpins, trills (\\trill, \\startTrillSpan), glissando, bendAfter, and note-bend/portamento related commands with example code."),
]
res=pplx_sdk.content.fetch([u for _,u,_ in jobs])
for (n,u,p),r in zip(jobs,res):
    t=r.content or ("ERROR: "+str(r.error))
    open(f"{OUT}/{n}.md","w").write(f"# {n}\nSource: {u}\nFetched: 2026-08-30\n\n{t}\n")
    print(n,len(t))
