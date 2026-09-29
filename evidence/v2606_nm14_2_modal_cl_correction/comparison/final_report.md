# Phase V2606-NM14.2: modal-family and distributed-Cl correction

Classification: `V2606_NM14_2_MODAL_AND_CL_CORRECTED`. This revision checks the user-supplied Huera-Huarte 2006 thesis PDF against the distributed Cl definition. All work was offline postprocessing of the completed NM13/NM14 run. The PDF identity and exact page locations are recorded in [the source audit](../reference/huera_thesis_source_audit.json); the PDF itself is intentionally excluded from this upload.

## Modal families

The previous `ny=4, nx=1` labels were raw eigenvector ordinals from a six-vector basis, not complete physical bending-family assignments. The first 12 current-model M-normalized lateral eigenvectors form six nearly-degenerate pairs. The pair frequencies (Hz) are:

| Physical bending family | Eigenvector ordinals | Offline ANCF | Thesis Table 5.2 |
|---:|:---:|---:|---:|
| 1 | 1–2 | 0.808958 | 0.80865 |
| 2 | 3–4 | 1.621754 | 1.6211 |
| 3 | 5–6 | 2.442019 | 2.4411 |
| 4 | 7–8 | 3.273435 | 3.2722 |
| 5 | 9–10 | 4.119592 | 4.1181 |
| 6 | 11–12 | 4.983970 | 4.9822 |

The six reference values are from thesis Table 5.2 (PDF p102, printed p101), row **C001 May19 at mean top tension 1188.28 N**, calculated with 65 FEM nodes. The current model has 33 ANCF nodes and nominal 1175 N, so this is a *near-tension, cross-discretization* comparison, not identical-state modal equivalence or the Case-1 run's measured frequencies. Maximum relative discrepancy is 0.0404%. The modal subspace amplitude is `sqrt(mean(a[2m-1]^2 + a[2m]^2))`, after subtracting the separate window mean and selecting x-only or y-only DOFs. This is invariant to a rotation of either near-degenerate eigenspace. Coordinates are M-normalized; their numerical amplitudes are not displacement in metres.

| Window | IL family RMS 1,2,3,4,5,6 | CF family RMS 1,2,3,4,5,6 | Physical nx | Physical ny |
|:---|:---|:---|---:|---:|
| 5–10 s | 0.007117, 0.003765, 0.001952, 0.001335, 0.008031, 0.001940 | 0.013057, 0.015408, 0.013620, 0.007832, 0.002234, 0.001615 | 5 | 2 |
| 7.5–10 s | 0.004151, 0.003380, 0.002128, 0.001164, 0.008854, 0.002240 | 0.008008, 0.018824, 0.012044, 0.006708, 0.002347, 0.001462 | 5 | 2 |

The CF late spectral peaks at 1.8001 and 1.6003 Hz bracket the physical family-2 natural frequency 1.6218 Hz; family 2 also has the greatest pair-invariant CF amplitude. The IL candidate peak near 4.000 Hz is closer to family 5 (4.1196 Hz) than family 4 (3.2734 Hz); family 5 has the greatest pair-invariant IL amplitude in both late windows. This is a simulated short-time modal diagnosis, **not** a forced match to experimental `nx=4`.

## Thesis definition and distributed lift coefficient

Accepted **direct OpenFOAM** `Fy` samples were converted once by `/0.028 m`, then reconstructed as the production piecewise-linear force field with NearestConstant ends on `[0,5.94] m`. Local `Cl(s,t)=fy(s,t)/(0.5 ρ U² D)` uses `ρ=1000 kg/m³`, `U=0.31 m/s`, `D=0.028 m`.

The thesis states in §6.4.2 (PDF pp171–172, printed pp170–171) that each transverse-force-coefficient RMS point is computed **along the riser and in time** by applying Eq. (5.18). That equation (PDF p110, printed p109) is the standard deviation of a time signal after subtracting its time mean. The preceding spatial-temporal definition for a distributed signal, Eq. (5.20), first averages squared local fluctuations spatially, then temporally, and finally takes the square root. The continuous analogue implemented here over the **active current region** is

`C_L,rms,active = sqrt( (1/(5.94 T)) ∫_window ∫_0^5.94 [Cl(s,t)-mean_window Cl(s)]² ds dt )`.

The spatial integral of the squared linear segments is analytic, not a five-point average. `RMS_INTEGRATED_TOTAL_CL` is independently the temporal standard deviation of the axially integrated/length-normalized lift coefficient and must **not** be compared directly with the experimental distributed `1.93`.

| Window | Accepted samples | Active-region local Cl RMS | Full-riser zero-extended diagnostic | Integrated-total Cl RMS | Mean Cd |
|:---|---:|---:|---:|---:|---:|
| 0–10 s | 24,999 | 1.094890 | 0.736710 | 0.385103 | 1.710615 |
| 2–10 s | 19,999 | 1.131361 | 0.761250 | 0.343335 | 1.739415 |
| 5–10 s | 12,499 | 1.155148 | 0.777256 | 0.388271 | 1.742821 |
| 7.5–10 s | 6,249 | 1.152607 | 0.775546 | 0.454276 | 1.769855 |

The **domain remains a comparison limitation**. Thesis §6.4 (PDF p164) says all displayed cases except Case 4 had water around the entire 13.12 m riser; Case 1's Table 6.1 value 1.93 is a whole-riser distributed statistic. The production CFD force mapper reconstructs direct forces only over `[0,5.94] m` and is exactly zero above that. The full-riser column is therefore just `active RMS × sqrt(5.94/13.12)`: it explicitly zero-extends the mapped load and **does not recover hydrodynamic forces in the upper still-water region**. Neither that diagnostic nor the active-region RMS is a strict like-for-like physical validation against 1.93. The thesis also reconstructs forces from measured motion and its FEM, whereas this simulation uses direct CFD forces. Thesis Eq. (6.9) divides integrated mean drag by the length exposed to the current, supporting the `5.94 m` denominator used for mean Cd.

## Late-window Case-1 table

The sigma values are the **maximum spanwise temporal RMS displacement divided by D**, inherited from the corrected NM14.1 window definitions. The simulated frequencies come from a representative `s=2.97 m` point signal; the thesis (PDF p109, printed p108) obtains dominant frequencies from spectra of dominant modal amplitudes, so the frequency-extraction methods are not identical.

| Quantity | 5–10 s | 7.5–10 s | Huera Case 1 |
|:---|---:|---:|---:|
| CF frequency `fy` (Hz) | 1.8001 | 1.6003 | 1.66 |
| Physical CF family `ny` | 2 | 2 | 2 |
| IL candidate frequency `fx` (Hz) | 4.0003 | 4.0006 | 3.40 |
| Candidate `fx/fy` | 2.222 | 2.500 | 2.048 |
| Physical IL family `nx` | 5 | 5 | 4 |
| `sigma_y/D` | 0.20017 | 0.20767 | not supplied |
| `sigma_x/D` | 0.10174 | 0.09574 | not supplied |
| Mean Cd | 1.74282 | 1.76985 | 1.86 |
| Active-region distributed local Cl RMS | 1.15515 | 1.15261 | 1.93 (whole-riser; not strict like-for-like) |
| Full-riser zero-extended diagnostic | 0.77726 | 0.77555 | not a matched measurement |
| Integrated-total Cl RMS | 0.38827 | 0.45428 | **not comparable** |

## Provenance, numerical checks and decision

The thesis Table 6.1 Case 1 gives `U=0.31 m/s`, `Re=7622`, initial top tension `1175 N`, `ny=2`, `fy=1.66 Hz`, `nx=4`, `fx=3.40 Hz`, mean `Cd=1.86` and distributed `Cl RMS=1.93`. The PDF geometry table gives `D=0.028 m` and `L=13.12 m`; its `Ls=5.94 m` entry is clarified by §4.1 (PDF pp79–80) as the lower 45% exposed to uniform moving current, while the upper portion was in still water.

Checks: 25,000 accepted direct-force records and 25,000 accepted states; M-orthonormality max error `1.11e-15`; a rotated family-2 basis changes its norm by `5.20e-18`; analytic squared-field integration versus a dense-grid independent trapezoid differs by `3.88e-10`; integrated Cd/Cl RMS exactly reproduces the NM14.1 values within `1e-12`. Frozen ANCF core SHA-256 remains `6dde195a...` (`.cpp`) and `c1182ab9...` (`.hpp`). Details: [numerical checks](../analysis/numerical_self_checks.json), [12-vector modal audit](../modal/family_frequency_audit.json) and [distributed Cl results](../analysis/distributed_huera_cl.json).

`10_TO_15_EXTENSION = RECOMMENDED`, but **not started**. The two late spectral windows are only 5 and 2.5 s (0.2/0.4 Hz bin resolution). Local distributed Cl RMS is nearly unchanged, yet integrated-total Cl RMS and some response metrics remain window-dependent; stationary long-time VIV and a definitive in-line frequency are not established.
