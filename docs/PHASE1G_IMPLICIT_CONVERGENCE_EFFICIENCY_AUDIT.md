# Phase 1G — Implicit Convergence Efficiency Audit

## Outcome

**Observed iteration behavior: `SLOW_MONOTONIC_CONVERGENCE`.**

**25-window readiness decision: `NO — convergence efficiency issue should be addressed first`.**

This is an efficiency finding, not a coupling-contract failure. It does not change the accepted `PASS_REAL_5WINDOW_STRATEGY_C` result. Four windows were accepted at the 20-iteration cap, so the five-window run does not establish convergence for those windows or provide enough efficiency margin to justify extending directly to 25 windows. No parameter or code change is recommended by this audit.

## Evidence and method

This audit is read-only apart from this report. It analyzes the Phase 1F run `run-20260923T103144Z-pid128756` at HEAD `02d9a1f180082e83bcc9f7acdcb090502262b2d1`:

- Structure trace: [`structure_trace.jsonl`](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/structure_trace.jsonl), SHA256 `8291e66c79e4f182f1ba67db78137411365df46d27de04f794ddfddeb9b2fd2a`, 93 attempt records.
- Fluid/OpenFOAM/preCICE log: [`fluid.stdout`](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/fluid.stdout), SHA256 `4a74fbec2d1fcf5a21039447945dd533f7123b18e5636794f6770b0e1777389a`.
- The log contains 186 preCICE convergence-measure records: one Displacement and one Force measure for each of the 93 attempts. Those `conv=` values and absolute residuals are the authoritative configured convergence tests. The XML has two required measures and no `suffices="yes"`; both must pass.

Residual definitions matter here:

- `trial_displacement_residual_m` in the Structure trace is the norm of the current ANCF trial interface displacement minus the preceding trial (the first trial is compared with the committed motion).
- For retry attempts, `force_residual_raw_N` is the norm of the endpoint Force returned after advance minus the Force supplied to that ANCF solve. Only rows with `rollback_request=true` are used for the within-window endpoint-force contraction ratios.
- On an accepted attempt the participant intentionally reads Force at relative time 0, which is the accepted-window boundary/next-window handoff. The trace field `force_residual_raw_N` on that row therefore compares different time levels and is **excluded** from the current window’s fixed-point residual ratios. The accepted-attempt preCICE convergence log remains valid for its own window.

The participant trace preserves every Force input, endpoint return, accepted boundary read, ANCF trial and iteration. The tables below show representative endpoints and residual summaries; they do not replace the raw per-attempt trace.

## Per-window convergence

The preCICE absolute limits are `1e-8 m` for Displacement and `1e-3 N` for Force, with relative limits `1e-5`. In this run the relative criteria did not rescue any failed absolute criterion.

| Window | Attempts | preCICE Displacement norm, first → last | Displacement pass | preCICE Force norm, first → last | Force pass | Result |
|---:|---:|---:|---|---:|---|---|
| 1 | 13 | `1.43e-7 → 9.62e-9 m` | iteration 13 | `1.18e-3 → 8.08e-5 N` | iteration 2 onward | converged before cap |
| 2 | 20 | `5.66e-7 → 1.11e-8 m` | never (1.11× limit at cap) | `1.39e-1 → 5.20e-4 N` | iterations 18–20 | cap accepted; displacement gates |
| 3 | 20 | `1.13e-6 → 3.06e-8 m` | never | `6.98e-1 → 2.52e-3 N` | never | cap accepted; both fail, displacement slower |
| 4 | 20 | `1.67e-6 → 6.10e-8 m` | never | `1.81 → 6.51e-3 N` | never | cap accepted; both fail, displacement slower |
| 5 | 20 | `2.16e-6 → 1.01e-7 m` | never | `3.44 → 1.24e-2 N` | never | cap accepted; both fail, displacement slower |

The Force endpoint residuals in the trace, using retry rows only, decrease as follows:

| Window | Retry endpoint residual, first → last (raw N) | Adjacent-ratio behavior |
|---:|---:|---|
| 1 | `2.3508e-4 → 2.0193e-5` | 11/11 ratios `0.800` |
| 2 | `2.7804e-2 → 1.3006e-4` | first ratio `0.208`, then approximately `0.800` |
| 3 | `1.3960e-1 → 6.2929e-4` | first ratio `0.200`, then approximately `0.800` |
| 4 | `3.6123e-1 → 1.6266e-3` | first ratio `0.200`, then approximately `0.800` |
| 5 | `6.8783e-1 → 3.0974e-3` | first ratio `0.200`, then approximately `0.800` |

The participant’s trial-displacement residual decreased within each window. The preCICE Displacement residual also decreased monotonically for windows 1–4; window 5 had two small local increases (largest adjacent ratio about `1.05`) before continuing downward. This is a minor non-monotonicity, not a sustained alternating sequence.

## Force and trial-motion sequence behavior

The full vector sequence for every iteration is in the linked JSONL trace. The following compact view shows the start Force, the Force returned after the first trial, the last retry endpoint Force, the accepted boundary Force, and the first/accepted ANCF trial motions:

| Window | Force input at start `[Fx,Fy]` N | First endpoint return `[Fx,Fy]` N | Last retry endpoint `[Fx,Fy]` N | Accepted boundary read `[Fx,Fy]` N | `D_trial` first → accepted `[Dx,Dy]` m |
|---:|---:|---:|---:|---:|---:|
| 1 | `[0.06553, 0.05873]` | `[0.06530, 0.05880]` | `[0.06448, 0.05906]` | `[0.06441, 0.05909]` | `[1.063e-7, 9.531e-8] → [1.046e-7, 9.585e-8]` |
| 2 | `[0.06441, 0.05909]` | `[0.04403, 0.04017]` | `[0.06539, 0.05882]` | `[0.06579, 0.05916]` | `[5.217e-7, 4.780e-7] → [5.233e-7, 4.776e-7]` |
| 3 | `[0.06579, 0.05916]` | `[-0.03725, -0.03502]` | `[0.06412, 0.05749]` | `[0.06598, 0.05919]` | `[1.359e-6, 1.236e-6] → [1.356e-6, 1.233e-6]` |
| 4 | `[0.06598, 0.05919]` | `[-0.20115, -0.18398]` | `[0.06112, 0.05479]` | `[0.06594, 0.05917]` | `[2.592e-6, 2.350e-6] → [2.584e-6, 2.343e-6]` |
| 5 | `[0.06594, 0.05917]` | `[-0.44333, -0.40317]` | `[0.05665, 0.05087]` | `[0.06582, 0.05920]` | `[4.188e-6, 3.789e-6] → [4.172e-6, 3.776e-6]` |

Windows 2–5 show a large first endpoint-force excursion; windows 3–5 cross zero. The first response is followed by a one-direction approach of the relaxed Force iterate and trial displacement toward the accepted state. The residual norms do not show repeated oscillation. The initial excursion grows with window index, which increases the absolute residual the later-window iteration must remove; this audit does not identify its physical cause.

## Fixed-point ratios and classification

Ratios below use consecutive preCICE logged residual norms over the final five transitions in each window (logs print rounded values):

| Window | Force residual ratio | Displacement residual ratio |
|---:|---:|---:|
| 1 | `0.800` | `0.799` |
| 2 | `0.800` | `0.815` |
| 3 | `0.800` | `0.830` |
| 4 | `0.800` | `0.840` |
| 5 | `0.800` | `0.846` |

Interpretation:

- **Geometric contraction exists.** Retry endpoint Force residuals contract at about `0.8` per iteration after the initial transition; trial-motion and preCICE residuals also contract overall.
- **The Force contraction rate is nearly constant.** Its approximate `0.8` factor matches a fixed relaxation coefficient of `0.2` qualitatively; this agreement is not proof that relaxation alone causes the observed map.
- **Displacement convergence slows across later windows.** Its late-window factor rises from about `0.80` to `0.85`, and its starting residual grows. This, rather than persistent Force oscillation, is the principal iteration-count bottleneck. Force also remains above tolerance at the cap in windows 3–5.
- **Classification: `SLOW_MONOTONIC_CONVERGENCE`.** There is no evidence of sustained `DIVERGING_ITERATION` or repeated `OSCILLATORY_CONVERGENCE` in the measured histories. Window 5’s two small Displacement-residual rises and the one-step Force startup excursions are recorded, but do not change that classification.

The participant-level `trial_displacement_residual_m` and retry-only endpoint Force residual exhibit nearly exact `0.8` tails, while the preCICE Displacement measure slows more noticeably. These are different observations: the participant residual compares its ANCF trial sequence; preCICE evaluates the configured exchanged coupling data after its acceleration.

## Relaxation and acceleration capability

Current `precice-config.xml`:

- `parallel-implicit`, `min-iterations=2`, `max-iterations=20`;
- constant under-relaxation, `relaxation=0.2`;
- both exchanged data have `waveform-degree=0`; no substeps are exchanged;
- absolute-or-relative convergence measures are configured for both Displacement and Force.
- No Aitken, IQN-ILS or IQN-IMVJ configuration is present.

For parallel coupling, preCICE applies the configured acceleration to both exchanged fields using the same coefficients. The installed configuration therefore relaxes both Displacement and Force; the near-`0.8` residual contraction is consistent with that fixed coefficient. Official preCICE documentation describes the available schemes as constant under-relaxation, Aitken, IQN-ILS and IQN-IMVJ; it cautions against Aitken for parallel coupling and presents IQN-ILS / IQN-IMVJ for strong interactions. These are capability facts only, **not a recommendation to change this case**. Any future selection requires a separate design/review and qualification. [Acceleration configuration](https://precice.org/configuration-acceleration), [coupling scheme and convergence measures](https://precice.org/configuration-coupling).

## Physical coupling context

Values below are existing contract values, not new tuning:

- `rho=1000 kg/m^3`, `D=0.028 m`, `U=0.31 m/s`, `Re≈7622`;
- structural line mass `1.845 kg/m`; added mass `0.616 kg/m` in x/y; wet transverse line mass `2.461 kg/m`;
- using the explicitly defined circular displaced-fluid reference `rho*pi*D^2/4`, displaced mass per length is about `0.61575 kg/m`, giving structural/displaced-fluid mass ratio about `3.00`. Added/structural mass is about `0.334`;
- benchmark top-tension input is `1175 N`. The distinct P1 equilibrium reaction is `1188.28 N` and is not substituted for the benchmark input;
- `dt=0.0002 s`, giving `U*dt/D≈0.00221`; five windows span only `0.001 s`;
- the structural contract has zero Rayleigh damping and zero lineal damping.

This is not an extremely light structural mass relative to displaced fluid, but the hydrodynamic added mass is material and the run uses parallel implicit coupling at high Reynolds number. These values alone do not predict a specific iteration count. Zero damping and the increasing first-iteration Force excursion are relevant context, not proven causes. The five-window trace cannot establish whether the later coupling is limited primarily by physical added-mass strength, transient flow response, participant inner convergence, or other nonlinear effects.

The official coupling documentation states that all configured convergence measures must pass to continue unless a measure explicitly uses `suffices="yes"`; this configuration has no such override. Accordingly, cap acceptance in windows 2–5 is not convergence. The Phase 1F pass remains valid as a bounded runtime/contract qualification, but its efficiency is insufficient evidence for a 25-window qualification.

## Long-run readiness and stop

**Decision: `NO — convergence efficiency issue should be addressed first`.** This is not a request to tune relaxation or increase the cap now. Keep `dt`, relaxation, damping, turbulence, mesh, force scaling, and `max-iterations` unchanged. The evidence shows a repeatable roughly 0.8 contraction of Force residuals, slower displacement contraction approaching 0.85, and four cap-accepted windows. A 25-window run would extend an unresolved near-cap pattern without clarifying it and is not authorized by this audit.

Documentation note: `docs/COUPLING_CONTRACT.md` still describes the earlier two-window authorization, while the accepted Phase 1F execution profile in `contract.json` and the current XML is five windows. This audit does not rewrite that historical document.

No code, configuration, parameter, runtime, or evidence artifact was changed by Phase 1G other than this report. HEAD remains `02d9a1f180082e83bcc9f7acdcb090502262b2d1`; the existing worktree remains dirty from accepted Phase 1E.6 / Phase 1F work and evidence.
