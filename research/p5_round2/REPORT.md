# P5 round 2 — builder report

96-bar 16th probe, 120 bpm, reference estimator, median over 5 seeds
(loose / tight / pushed / breath). Reference = `refs/specs/feel_truth.md`.

| statistic | round 2 | reference median [IQR] |
|---|---|---|
| median \|residual\| ms | 8.70 / 8.57 / 8.72 / 8.31 | 8.32 [6.90, 10.30] |
| residual excess kurtosis | +3.68 / +4.05 / +4.01 / +5.44 | +5.64 [+2.87, +7.79] |
| velocity sd | 13.4 / 11.6 / 12.6 / 12.9 | 11.86 [10.73, 14.53] |
| velocity lag-1 r | +0.42 / +0.44 / +0.44 / +0.49 | +0.452 [+0.385, +0.538] |
| gate IQR width | 2.60 / 1.74 / 1.85 / 3.05 | 2.93 [1.59, 3.63] |
| gate median | 1.09 / 0.97 / 0.91 / 1.09 | 0.986 |

Seventh row, disclosed as a miss: residual ÷ tatum 0.070 / 0.068 / 0.070 / 0.066
against 0.076 [0.071, 0.084]. Timing lag-1 r +0.76…+0.87 against +0.55
[+0.45, +0.68] — my rubato is smoother than a real player's.

Full suite: `PYTHONPATH=src python -m pytest -q` → **853 passed, 0 failed**.
