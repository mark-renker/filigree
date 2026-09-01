import pplx_sdk
OUT="refs/syntax/rival_docs"
jobs=[
 ("lilypond_falls_doits","https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-curves"),
 ("tidal_mini_notation","https://tidalcycles.org/docs/reference/mini_notation/"),
 ("tidal_arithmetic","https://tidalcycles.org/docs/reference/arithmetic/"),
 ("tidal_time","https://tidalcycles.org/docs/reference/time/"),
 ("sonicpi_fx_list","https://sunderb.me/sonic-pi-docs-test/en/reference/fx/index.html"),
 ("sonicpi_chord_names","https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_names.html"),
 ("strudel_mini_notation","https://strudel.cc/learn/mini-notation/"),
 ("strudel_arithmetic","https://strudel.cc/learn/numbers/"),
]
res=pplx_sdk.content.fetch([u for _,u in jobs])
for (n,u),r in zip(jobs,res):
    t=r.content or ("ERROR: "+str(r.error))
    open(f"{OUT}/{n}.md","w").write(f"# {n}\nSource: {u}\nFetched: 2026-08-30\n\n{t}\n")
    print(n,len(t))
