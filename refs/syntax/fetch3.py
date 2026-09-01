import pplx_sdk
OUT="refs/syntax/rival_docs"
jobs=[
 ("sonicpi_tutorial_extract","https://sonic-pi.net/tutorial.html","Extract verbatim, with code examples: (1) the *_slide options and control/synth handle usage including note_slide, slide curve opts (*_slide_shape, *_slide_curve); (2) chord and chord_degree and chord_invert functions with args (num_octaves:, invert:); (3) all MIDI out functions midi_note_on/midi_note_off/midi_cc/midi_pitch_bend with their arg ranges, channel: and port: opts; (4) note opts vibrato_rate/vibrato_depth/vibrato_delay/vibrato_onset if they exist; (5) use_synth_defaults / with_synth_defaults; (6) define for reusable functions."),
 ("lilypond_marks_notes","https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-attached-to-notes","Extract verbatim the articulation/script list and dynamics syntax with code examples."),
 ("lilypond_marks_lines","https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-lines","Extract verbatim documentation and examples for glissando, \\bendAfter (falls and doits), trills \\trill \\startTrillSpan \\pitchedTrill, and any vibrato-related commands."),
 ("lilypond_enhancing_midi","https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output","Extract verbatim the \\articulate usage, the list of supported articulations/ornaments it handles, and all documented limitations/known issues."),
 ("ziffers_cheatsheet","https://github.com/amiika/ziffers","Extract verbatim the syntax cheatsheet table: pitches, durations, chords, roman numeral chords, named chords/quality suffixes, modal interchange letters, key/scale opts, repeats, transformations, list operations, and how zplay/zloop pass Sonic Pi opts."),
]
res=pplx_sdk.content.fetch([u for _,u,_ in jobs], prompt=None)
for (n,u,p),r in zip(jobs,res):
    t=r.content or ("ERROR: "+str(r.error))
    open(f"{OUT}/{n}.md","w").write(f"# {n}\nSource: {u}\nFetched: 2026-08-30\n\n{t}\n")
    print(n,len(t))
