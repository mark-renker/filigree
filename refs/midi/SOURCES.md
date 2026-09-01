# Reference performance MIDI corpus

All files here are excerpts of the **MAESTRO v3.0.0** dataset (Google Magenta): real human
performances captured on Yamaha Disklavier concert grands at the International Piano-e-Competition,
with ~3 ms MIDI capture accuracy — i.e. genuine expressive human timing/velocity, not quantised
score MIDI. Source page: https://magenta.tensorflow.org/datasets/maestro

* **Archive downloaded:** https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip
  (58,416,533 bytes, md5 `t2VlidD/jxFw0T9pg3OQug==`). 12 files extracted; the archive itself is not kept in-repo.
* **License:** Creative Commons Attribution Non-Commercial Share-Alike 4.0 (CC BY-NC-SA 4.0),
  granted by Google LLC — see `LICENSE` inside the archive and the dataset page above.
  Attribution + non-commercial + share-alike apply to these files and to any statistics distributed with them.
* **Citation:** Hawthorne et al., “Enabling Factorized Piano Music Modeling and Generation with the
  MAESTRO Dataset”, ICLR 2019 — https://openreview.net/forum?id=r1lYRjC9F7

No other corpus was needed; the MAESTRO archive was reachable on first attempt.

## Files

| file | composer | piece | perf. year | dur (s) | bytes | path inside archive |
|---|---|---|---|---|---|---|
| `Alexander_Scriabin__3_Etudes_Op_65.mid` | Alexander Scriabin | 3 Etudes, Op. 65 | 2006 | 397.9 | 47516 | `maestro-v3.0.0/2006/MIDI-Unprocessed_17_R1_2006_01-06_ORIG_MID--AUDIO_17_R1_2006_04_Track04_wav.midi` |
| `Antonio_Soler__Sonata_No_10_in_B_Minor.mid` | Antonio Soler | Sonata No. 10 in B Minor | 2009 | 232.8 | 26224 | `maestro-v3.0.0/2009/MIDI-Unprocessed_09_R1_2009_01-04_ORIG_MID--AUDIO_09_R1_2009_09_R1_2009_01_WAV.midi` |
| `Claude_Debussy__Feux_d_artifice_from_Book_II.mid` | Claude Debussy | "Feux d'artifice" from Book II | 2008 | 242.8 | 29106 | `maestro-v3.0.0/2008/MIDI-Unprocessed_10_R3_2008_01-05_ORIG_MID--AUDIO_10_R3_2008_wav--4.midi` |
| `Domenico_Scarlatti__Sonata_K_54.mid` | Domenico Scarlatti | Sonata K. 54 | 2008 | 205.8 | 24896 | `maestro-v3.0.0/2008/MIDI-Unprocessed_09_R3_2008_01-07_ORIG_MID--AUDIO_09_R3_2008_wav--1.midi` |
| `Felix_Mendelssohn__Rondo_Capriccioso_in_E_Minor_Op_14.mid` | Felix Mendelssohn | Rondo Capriccioso in E Minor, Op. 14 | 2013 | 362.8 | 46567 | `maestro-v3.0.0/2013/ORIG-MIDI_02_7_6_13_Group__MID--AUDIO_06_R1_2013_wav--4.midi` |
| `Franz_Liszt__La_Campanella.mid` | Franz Liszt | "La Campanella" | 2008 | 273.2 | 37375 | `maestro-v3.0.0/2008/MIDI-Unprocessed_09_R1_2008_01-05_ORIG_MID--AUDIO_09_R1_2008_wav--3.midi` |
| `Franz_Schubert__Der_Mueller_und_der_Bach.mid` | Franz Schubert | "Der Mueller und der Bach" | 2009 | 336.4 | 34415 | `maestro-v3.0.0/2009/MIDI-Unprocessed_08_R1_2009_01-04_ORIG_MID--AUDIO_08_R1_2009_08_R1_2009_02_WAV.midi` |
| `Fritz_Kreisler__Liebesfreud.mid` | Fritz Kreisler / Sergei Rachmaninoff | Liebesfreud | 2011 | 370.0 | 52123 | `maestro-v3.0.0/2011/MIDI-Unprocessed_17_R2_2011_MID--AUDIO_R2-D5_06_Track06_wav.midi` |
| `Fr_d_ric_Chopin__12_Etudes_Op_25.mid` | Frédéric Chopin | 12 Etudes, Op. 25 | 2004 | 327.3 | 47553 | `maestro-v3.0.0/2004/MIDI-Unprocessed_SMF_05_R1_2004_01_ORIG_MID--AUDIO_05_R1_2004_03_Track03_wav.midi` |
| `George_Frideric_Handel__Chaconne_in_G.mid` | George Frideric Handel | Chaconne in G | 2009 | 329.0 | 39985 | `maestro-v3.0.0/2009/MIDI-Unprocessed_18_R1_2009_01-03_ORIG_MID--AUDIO_18_R1_2009_18_R1_2009_01_WAV.midi` |
| `Georges_Bizet__Chanson_Boheme_de_l_Opera_Carmen_by_Geor.mid` | Georges Bizet / Moritz Moszkowski | Chanson Boheme de l'Opera "Carmen" by Georges Bizet | 2017 | 336.5 | 47422 | `maestro-v3.0.0/2017/MIDI-Unprocessed_058_PIANO058_MID--AUDIO-split_07-07-17_Piano-e_2-02_wav--5.midi` |
| `Isaac_Alb_niz__Asturias.mid` | Isaac Albéniz | Asturias | 2009 | 308.7 | 30626 | `maestro-v3.0.0/2009/MIDI-Unprocessed_03_R1_2009_03-08_ORIG_MID--AUDIO_03_R1_2009_03_R1_2009_06_WAV.midi` |

Performer names are not published per-recording by MAESTRO (competition entrants are anonymised);
the composer/title/year triple above is the full provenance the dataset provides.

Statistics computed from these files live in `stats.json` (see `tools/perf_stats.py`).
