import pplx_sdk, re, os, json
OUT="/home/user/workspace/filigree/refs/syntax/rival_docs"
jobs = [
 ("tidal_harmony_melody","https://tidalcycles.org/docs/reference/harmony_melody","Extract exactly the documented functions and code examples for notes, chords, chord names/modifiers (e.g. arpg, chordList, quality suffixes), scales, toScale, arpeggiate, and voicing-related helpers. Quote code verbatim."),
 ("tidal_midi","https://tidalcycles.org/docs/configuration/MIDIOSC/midi/","Extract verbatim all documented MIDI control functions: midinote, midibend, miditouch, ccn, ccv, nrpnn, nrpnv, midichan, polyTouch, with their value ranges and code examples."),
 ("tidal_signals","https://tidalcycles.org/docs/reference/signals","Extract verbatim documented continuous signal functions (sine, saw, envL, range, segment, slow, fast, quantise, etc.) with code examples and value ranges."),
 ("strudel_tonal","https://strudel.cc/learn/tonal/","Extract verbatim all documented functions and examples: n, note, scale, chord, dict, voicing, voicings, anchor, mode, offset, rootNotes, arpeggiate/arp, and their arguments."),
 ("strudel_input_output","https://strudel.cc/learn/input-output/","Extract verbatim the MIDI output documentation: midi(), midichan, midibend, miditouch, ccn, ccv, midimaps, progNum, sysex, and any statement about ranges and structure alignment. Include code examples."),
 ("strudel_signals","https://strudel.cc/learn/signals/","Extract verbatim documented signals and modifiers: sine, saw, tri, square, isaw, perlin, rand, and range, segment, slow, and the -2 variants. Include code examples."),
]
res = pplx_sdk.content.fetch([u for _,u,_ in jobs], prompt=None)
for (name,url,prompt),r in zip(jobs,res):
    txt = r.content or ("ERROR: "+str(r.error))
    open(f"{OUT}/{name}.md","w").write(f"# {name}\nSource: {url}\nFetched: 2026-08-30\n\n{txt}\n")
    print(name, len(txt))
