# V2606-NM14.1 Read-only correction closeout

Classification: **V2606_NM14_1_LONG10S_POSTPROCESS_CORRECTED**.

No CFD, preCICE, Structure, restart, or production-case operation was started.
All results use the completed NM13/NM14 25,000-window trajectory.

## Axis and window corrections

- The old full-riser plotting code contained an incorrect `s/0.13` coordinate.
- It is fixed in the NM14.1 replacement figures.
- All corrected full-riser figures use vertical `s/L` in `[0,1]`.
- Current/still-water boundary is shaded at `s/L = 0.4527439024390244`.
- The Chaplin-style figure now has vertical `s/L`, horizontal mean `x/D`, dynamic
  `(x-xbar)/D`, and `y/D`, with current exposure shown as a shaded region.

Each analysis window now has its own mean subtraction. The maximum spanwise
standard deviations are:

| window | max sigma_x/D | max sigma_y/D | dynamic x/D min..max | dynamic y/D min..max |
|---|---:|---:|---:|---:|
| 0–10 s | 0.16363 | 0.21850 | -0.80743 .. 0.46258 | -0.62961 .. 0.51531 |
| 2–10 s | 0.10435 | 0.21984 | -0.25574 .. 0.26650 | -0.62249 .. 0.51622 |
| 5–10 s | 0.10174 | 0.20017 | -0.25615 .. 0.26414 | -0.51773 .. 0.43369 |
| 7.5–10 s | 0.09574 | 0.20767 | -0.21153 .. 0.23185 | -0.46830 .. 0.37517 |

Thus the large 0–10 s inline excursion is startup/quasi-static contamination,
not a late-time dynamic RMS. At s=2.97 m, late inline RMS is 1.885e-3 m and
cross-flow RMS is 4.478e-3 m for 7.5–10 s.

## Windowed frequency re-audit

The inline peak near 0.7–0.75 Hz weakens and is no longer the leading late-time
feature. The persistent late candidate is approximately 4.00 Hz:

- 5–10 s: fx = 4.0003 Hz
- 7.5–10 s: fx = 4.0006 Hz

Linear-detrend sensitivity gives the same leading late peak. Cross-flow remains
multi-peak but is led by:

- 5–10 s: fy = 1.8001 Hz
- 7.5–10 s: fy = 1.6003 Hz

The corresponding candidate ratios are approximately 2.22 and 2.50. They are
reported descriptively, not forced toward 2. The actual FFT bin resolutions are
0.2 Hz for 5–10 s and 0.4 Hz for 7.5–10 s.

The complete five-peak tables, including the ~0.7, ~1.5–2 and ~4 Hz features,
are in `analysis/windowed_frequency_peaks.json`.

## Hydrodynamic stationarity

| window | mean Cd | integrated-total Cl RMS |
|---|---:|---:|
| 0–10 s | 1.7106 | 0.3851 |
| 2–10 s | 1.7394 | 0.3433 |
| 5–10 s | 1.7428 | 0.3883 |
| 7.5–10 s | 1.7699 | 0.4543 |

The last column is explicitly the RMS of the integrated total lift coefficient,
not the Huera distributed space-time RMS Cl. The latter remains source-definition
limited because the local Huera paper was not available.

## Modal basis

No compatible retained 13.12 m / 32-element / 198-DOF eigenvector artifact was
found. An M-normalized basis was generated offline from the unchanged current
kernel mass matrix and q0 tangent, with the canonical fixed DOFs removed. The
first six generated frequencies are approximately:

`0.80896, 0.80896, 1.62175, 1.62175, 2.44202, 2.44202 Hz`.

There is no retained qualified current-model frequency artifact for cross-check,
so this basis remains **LIMITED_UNVERIFIED_CROSSCHECK**. Diagnostic late-window
projection gives `nx = 1` and `ny = 4`; these are not promoted to qualified
physical modal identification.

## Extension decision

`TEN_SECOND_STATUS = EXTENSION_RECOMMENDED`.

The main drifting quantities are startup-sensitive inline RMS/peak structure and
the late cross-flow frequency moving from about 1.80 to 1.60 Hz over the two late
windows. A first extension from 10 s to 15 s is justified; reassess before any
10-to-20 s extension. No continuation was started.

Evidence: `evidence/v2606_nm14_1_long10s_correction/`.
