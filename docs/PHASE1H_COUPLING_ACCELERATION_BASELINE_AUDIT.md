# Phase 1H — preCICE Coupling Acceleration Baseline Audit

## Outcome

**Observed behavior:** `SLOW_MONOTONIC_CONVERGENCE` (accepted Phase 1G finding).

**Recommendation:** `TEST_ACCELERATION_CHANGE` — if separately authorized, compare one carefully bounded `IQN-ILS` candidate against the existing constant-relaxation baseline. This is a recommendation for a later controlled experiment, not evidence that IQN-ILS will pass, and not authorization to edit the XML or run HH06 now.

The Phase 1F data are consistent with the fixed relaxation being a major limiter: the late Force residual contraction is about `0.8`, matching the old-iterate weight `1 - 0.2`. They do **not** isolate the acceleration strategy from the coupled fluid/structure fixed-point response, so the causal claim remains unproven. The displacement convergence measure is slower in later windows; in windows 3–5 both configured measures still fail at the iteration cap. A 25-window qualification remains not recommended.

## Scope and frozen baseline

This audit made no source, case, XML, physics, or runtime changes. No OpenFOAM, preCICE participant, or HH06 runtime was started.

The audited baseline is the accepted Phase 1F run `run-20260923T103144Z-pid128756`, at Git HEAD `02d9a1f180082e83bcc9f7acdcb090502262b2d1`. Its archived runtime identity records preCICE `3.4.1`. The current [preCICE configuration](../cases/hh06_single_slice/precice-config.xml) has SHA256 `e4987ec7d768517feefe312a9ddcbd391ff052981aa84bae6934b555e97d1f71`; this is the already-existing Phase 1F profile, not a Phase 1H edit.

Evidence:

- [Phase 1F structure trace](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/structure_trace.jsonl), SHA256 `8291e66c79e4f182f1ba67db78137411365df46d27de04f794ddfddeb9b2fd2a`, 93 attempts.
- [Phase 1F Fluid/preCICE log](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/fluid.stdout), SHA256 `4a74fbec2d1fcf5a21039447945dd533f7123b18e5636794f6770b0e1777389a`, with 186 convergence-measure records.
- [Phase 1F runtime identity](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/runtime_identity.json), SHA256 `8ef32fe0bd026402a0fec7f01d2b545bc7731806b1b0034276d6cb321e08c9d6`.
- The accepted [Phase 1G residual analysis](PHASE1G_IMPLICIT_CONVERGENCE_EFFICIENCY_AUDIT.md) supplies the per-window residual definitions and computed contraction ratios.

## Current preCICE acceleration and convergence contract

| Item | Current setting |
|---|---|
| Coupling scheme | `parallel-implicit` |
| Iteration bounds | minimum 2, maximum 20 |
| Phase 1F physical-window bound | 5 windows, `dt = 0.0002 s` |
| Acceleration | constant under-relaxation, `relaxation = 0.2` |
| Exchanged fields | 2D vector `Displacement` and 2D vector `Force`; both waveform degree 0, no substeps |
| Displacement convergence | absolute `1e-8 m` **or** relative `1e-5` |
| Force convergence | absolute `1e-3 N` **or** relative `1e-5` |

Because this is a parallel scheme, preCICE applies the same fixed linear-combination coefficients to both exchanged directions: Force and Displacement are both relaxed. For constant relaxation, the current iterate receives weight `0.2` and the previous iterate weight `0.8`. This is documented by preCICE’s [acceleration configuration](https://precice.org/configuration-acceleration). There is no separate Force-only or Displacement-only coefficient in the current XML.

The XML contains two convergence measures and neither has `suffices="yes"`; both must pass for a window to converge. Each `absolute-or-relative` measure passes if its absolute **or** relative condition is satisfied. Thus both fields remain required, while either test within each field can satisfy that field’s measure. This matches the [preCICE coupling configuration documentation](https://precice.org/configuration-coupling). The archived Phase 1F preCICE log is the run-specific record of these tests.

## What the five-window traces distinguish

These are three different quantities; they must not be conflated:

1. **Participant ANCF trial-motion residual.** `trial_displacement_residual_m` compares the current ANCF trial interface motion with the preceding trial (or committed motion on the first attempt). Its within-window tail contracts at about `0.8`. It is a participant diagnostic, not preCICE’s convergence test.
2. **preCICE Displacement residual.** The preCICE log measures the coupling fixed-point difference for exchanged Displacement after preCICE’s advance/acceleration lifecycle. Its late-window contraction factor increases from about `0.799` in window 1 to `0.846` in window 5. It is not the participant’s raw trial-to-trial residual.
3. **Force residuals.** The preCICE Force measure is a separate exchanged-data convergence test. The trace also records an endpoint-Force-minus-input norm on retry attempts; its late contraction is about `0.8`. Accepted-boundary reads are at a different read time and are excluded from the within-window retry contraction calculation.

| Window | Attempts | Force criterion | Displacement criterion | Acceptance / limiting observation |
|---:|---:|---|---|---|
| 1 | 13 | Passes from iteration 2 | Passes at iteration 13 | Converged before cap; Displacement is last to pass |
| 2 | 20 | Passes at iterations 18–20 | Fails at cap (`1.11e-8 m` vs `1e-8 m`) | Accepted at cap; Displacement blocks convergence |
| 3 | 20 | Fails at cap (`2.52e-3 N` vs `1e-3 N`) | Fails at cap (`3.06e-8 m` vs `1e-8 m`) | Both fail; Displacement contracts more slowly over the late tail |
| 4 | 20 | Fails at cap (`6.51e-3 N`) | Fails at cap (`6.10e-8 m`) | Both fail |
| 5 | 20 | Fails at cap (`1.24e-2 N`) | Fails at cap (`1.01e-7 m`) | Both fail |

The tail ratios and cap statuses agree with Phase 1G. The participant trial residual and the Force retry residual show nearly fixed `0.8` contraction, which is expected to be strongly shaped by constant relaxation. The preCICE Displacement measure slows over the later windows and has small local increases in window 5. Therefore:

- **The main efficiency concern is slow displacement contraction.** Window 1 and 2 acceptance are specifically Displacement-limited; windows 3–5 are jointly limited by Force and Displacement.
- **The 0.2 constant-relaxation choice is a plausible major cause of the observed slow tail, not a proven sole root cause.** The effective fixed-point map, changing fluid response, and structural response also determine the convergence rate. Only a controlled acceleration comparison can establish whether another scheme materially reduces iterations without degrading convergence behavior.
- The run’s participant trial residual, preCICE residuals, and cap acceptance support `SLOW_MONOTONIC_CONVERGENCE`, not an implicit-contract failure.

## Candidate accelerators

| Candidate | Suitability here | History and rollback interaction | Main risks / assessment |
|---|---|---|---|
| **A. Constant relaxation** | Existing reference. Simple and deterministic. In parallel, the same coefficient acts on Force and Displacement. | Uses the current/previous iteration combination; no multi-window quasi-Newton history. Physical ANCF rollback remains separate. | Stable and auditable, but the measured `~0.8` tail under `0.2` relaxation is slow. Keep unchanged as the comparison baseline. |
| **B. Aitken** | Can adapt relaxation from iteration residuals and may respond to changing convergence rate. However, preCICE generally advises against Aitken with parallel coupling; its parallel implementation applies a shared acceleration coefficient to both fields. | Needs prior iteration residuals within the active implicit window. Those belong to preCICE’s coupling iteration, not the ANCF physical checkpoint; do not reset them on participant rollback. | One adaptive coefficient must serve differently scaled metre and newton fields. If selected data do not represent both directions, behavior may be poorly informed. Not the preferred first candidate for this parallel case. |
| **C. IQN-ILS** | Strong candidate for a fixed-point coupling with strong interaction; preCICE identifies it as the simpler quasi-Newton method to start with. In parallel, configure both Force and Displacement as primary data and scale/precondition their very different units. | Builds a least-squares update from iteration history and can reuse prior-window data. History is preCICE-owned; rejected ANCF physical trial state still rolls back, while the coupling iterate/history must remain with the active coupling session. A new comparison run must start a fresh preCICE session. | The current structure interface has one 2D coupling point. With both 2D vector fields primary, this is nominally four scalar interface data DOFs. The current official guide cautions that `max-used-iterations` should be below half the interface DOFs; under the apparent four-value concatenated vector, that points to at most one column. Confirm the exact count/constraint interpretation for the installed 3.4.1 build and use its config parser before freezing a candidate. Do not silently copy the large default. Transient window-to-window changes can also make reused history stale. Despite these constraints, this is the clearest first candidate to test. |
| **D. IQN-IMVJ** | Also a quasi-Newton option for strong interaction, but not needed as the first comparison when IQN-ILS is available. | Uses iteration and potentially prior-window information, with additional Jacobian/restart-mode history management. It remains separate from ANCF physical rollback. | More configuration and history complexity than needed for a first test. The tiny interface limits the useful independent history; it offers no evidence-based advantage over IQN-ILS here. Defer unless IQN-ILS comparison later motivates it. |

The candidate descriptions follow the official [preCICE acceleration guide](https://precice.org/configuration-acceleration) and [XML reference](https://precice.org/configuration-xml-reference). The installed package is `libprecice3 3.4.1`; its local `/usr/bin/precice-config-doc` was inspected read-only with `--help` and `md`. The generated v3.4.1 reference confirms the available constant, Aitken, IQN-ILS and IQN-IMVJ elements and their schema. In particular, it reports IQN-ILS defaults of initial relaxation `0.1`, `max-used-iterations=100`, `time-windows-reused=10`, and residual-sum preconditioning when unspecified; IQN-IMVJ defaults differ. This makes it important not to inherit a large default blindly. The low-interface-DOF heuristic above is also in the current official guide; before any runtime, verify its count interpretation against the installed v3.4.1 behavior and validate the pinned candidate XML using the local 3.4.1 parser/documentation.

## Controlled comparison protocol (proposal only)

No comparison was run in Phase 1H. If authorized later, compare a paired five-window baseline replay against one five-window IQN-ILS run:

1. Start each run from an independent scratch copy of the exact 30.0 s restart and mesh; verify the field/mesh hashes and use the already-qualified physical `F0`. Do not let the first run’s advanced CFD state become the second run’s restart.
2. Keep the same `dt=0.0002 s`, five physical windows, `max-iterations=20`, `min-iterations=2`, Force/Displacement convergence criteria, force mapping, worker/adapter/Python/preCICE identities, participant code, and all physics settings.
3. Baseline is constant relaxation `0.2`. Candidate changes only the acceleration block to IQN-ILS; list both Force and Displacement as primary data in the two coupling directions, use a preconditioner to address their scale difference, and set the initial relaxation to `0.2` so the initial fixed-point step matches the baseline. Freeze the filter/history settings and complete XML hash before either run. Resolve the small-interface `max-used-iterations` rule against the installed 3.4.1 documentation/configuration before launch; do not use a large default without review.
4. Run both configurations with a fresh preCICE session, same bounded launcher and clean per-run output/socket directories. Preserve every coupling iteration. No mid-run config changes, tuning, retries with altered settings, or extension beyond five physical windows.
5. Compare iterations/window and cap/convergence status; both preCICE Force and Displacement residual histories; participant trial-displacement residual separately; wall-clock from the same start/stop definition; and process/runtime identities. Report all five windows, not only an average, and keep cap acceptance distinct from convergence.

The Phase 1F evidence does **not** contain a measured run wall-clock duration. Therefore, a fair wall-clock comparison requires replaying the baseline and the candidate with the same timing instrumentation; do not infer the baseline duration from log timestamps. The Phase 1F five-window run remains the scientific/iteration-history reference, not a wall-clock reference.

## Physical coupling context and limits of inference

The existing Phase 1G audit records structural line mass `1.845 kg/m`, added mass `0.616 kg/m`, mass ratio about `3.0` against the stated circular displaced-fluid reference, benchmark top tension `1175 N`, zero Rayleigh/lineal damping, and `dt=0.0002 s`. These unchanged parameters are relevant context, but none individually establishes the slow convergence cause. The one-millisecond five-window observation is too short to infer long-horizon behavior or whether the historical ALE/flow/turbulence runaway is resolved.

## Final recommendation and boundary

**`TEST_ACCELERATION_CHANGE`**: the observed late residual contraction is consistent with a strong fixed-relaxation effect, and four windows were accepted at the 20-iteration cap. A controlled IQN-ILS comparison is justified before reconsidering 25 windows. This audit does not establish that acceleration is the only cause, does not authorize a runtime, and does not change the accepted Phase 1F result.

Keep the present XML and all physical/numerical settings frozen until the candidate configuration and a bounded A/B run are separately reviewed and authorized. No 25-window qualification, acceleration edit, parameter tuning, or runtime is authorized by this report.

Phase 1H added this report only. Current HEAD remains `02d9a1f180082e83bcc9f7acdcb090502262b2d1`; the worktree was already dirty from prior accepted Phase 1E.6/1F work and evidence and remains so. No prior changes were cleaned, staged, committed, or reverted.
