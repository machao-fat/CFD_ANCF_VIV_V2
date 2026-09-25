# Phase 1K.23 — Single-Window Implicit Convergence Mechanism Diagnostic Plan

## Status and scope

This plan defines a diagnostic-only investigation of the repaired Fluid–RBF–preCICE–ANCF coupling map. It is not a production change and does not authorize a five-window, 25-window, multi-slice, or parameter-tuning run.

The diagnostic branch is:

```text
diagnostic/phase1k23-single-window-convergence-v1
```

The starting HEAD is the accepted Phase 1 state-closure commit `d3890deb0e609cc7e38e3f38ff6203787f889c07`. The production repair branch and `main` are not modified by this diagnostic.

The questions are deliberately separated:

* `FIXED_POINT_SLOW_BUT_CONTRACTIVE`: the operator is repeatable and residuals contract, but the selected acceleration/relaxation needs more iterations;
* `FLUID_OPERATOR_NOT_REPEATABLE_OR_INNER_UNCONVERGED`: identical physical state and displacement do not produce a sufficiently repeatable force, or inner CFD error is comparable to the coupling tolerance;
* `NONCONTRACTIVE_OR_POORLY_ACCELERATED_FIXED_POINT`: the repeatable map is oscillatory, non-monotone, or locally non-contracting under the current coupling iteration.

No classification will be selected before the measurements below are available.

## Frozen baseline and identity boundary

The diagnostic starts from the same unadvanced 30.0 s new-mesh restart used by Phase 1K.22. It must not use a 30.0002 s or later endpoint and must not overwrite Phase 1K.20–1K.22 evidence.

The following identities are frozen and must be recorded in `runtime_identity.json` before any runtime:

| Item | Frozen identity |
|---|---|
| worker source SHA256 | `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` |
| worker binary SHA256 | `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596` |
| Phase 1K.20 experimental adapter | `libpreciceAdapterPhase1K20.so` |
| Phase 1K.20 adapter SHA256 | `225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165` |
| historical qualified adapter SHA256 | `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572` |
| K22 diagnostic RBF SHA256 | `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11` |
| OpenFOAM | Foundation 10, to be re-recorded at runtime |
| preCICE | 3.4.1, to be re-recorded at runtime |
| Python | `/usr/bin/python3.10`, pyprecice metadata 3.4.0, to be re-recorded |

The historical adapter is not used by this phase. The Phase 1K.20 adapter remains a separate experimental identity; no replacement or in-place rebuild is permitted.

## Scratch layout and fail-closed rules

Create one unique directory below:

```text
evidence/phase1k23_single_window_convergence/<run-id>/
```

The run ID must include a timestamp or monotonic identifier and the current short Git SHA. Each diagnostic subtest gets a distinct child directory. A fresh scratch copy of the exact K22 30.0 s new-mesh restart is used for each subtest.

Before every subtest:

1. Verify the restart time is exactly 30.0 s.
2. Hash the restart fields, mesh, `fvSolution`, `fvSchemes`, `dynamicMeshDict`, preCICE XML, worker, adapter, and RBF library.
3. Verify the F0 provenance and the new-mesh force contract.
4. Verify the working directory is the scratch case directory before Fluid starts.
5. Verify no participant, worker, or stale socket from an earlier subtest is alive.

Any mismatch, missing field, missing binary, process-cleanup failure, or identity mismatch stops the phase. No automatic retry is allowed.

## Step 1 — repository and K22 evidence audit

The audit records the current branch, HEAD, clean/dirty state, and the requested project contracts and Phase 1H/K reports. It then extracts the K22 evidence needed as the comparison baseline:

* 100 attempt records over five windows;
* all five windows accepted at the iteration limit, with convergence flag 0;
* Force and displacement traces, including `D_trial`, `D_written`, Force input and returned Force;
* retry/accepted read-time events;
* exact rollback snapshots and transport identities;
* preCICE iterations, profiling, participant logs, and the known zero-valued convergence-log columns.

The K22 convergence log's zero per-data residual columns are preserved as forensic evidence but are not used as primary quantitative convergence data. The iterations log, detailed participant traces, Force differences, and direct Fluid outputs are kept separate.

## Step 2 — one-window extended coupling diagnostic

Use the K22 repaired experimental adapter, RBF library, mesh, physics, F0, and coupling settings. The scratch preCICE configuration has exactly one physical time window and retains the K22 Force/Displacement convergence criteria and minimum-iteration setting.

The diagnostic may raise the scratch preCICE maximum iteration count to 40 (or 50 if required by the observed tail). This is a diagnostic ceiling only, not a production setting. The scratch contract value must match the scratch XML because the participant contract audit checks this consistency. The participant's existing authorization interface currently requires a 25-window authorization; therefore the participant invocation will retain a scratch execution authorization of 25 while the scratch preCICE XML limits the actual run to one window. This is an interface constraint, not permission to execute a second window. The run is stopped if the one window reaches the diagnostic ceiling without convergence and is classified `NOT_CONVERGED`; it is never accepted merely because the ceiling was reached.

For every coupling attempt, write `single_window_trace.jsonl` with distinct fields for:

* window and iteration identity;
* physical tuple and transport IDs;
* input Force raw/applied and Force returned after advance;
* ANCF checkpoint identity, Newton count, and nonlinear residual;
* `D_previous_committed`, `D_trial`, and `D_written_to_precice`;
* Fluid displacement read value and explicit relative read time;
* point/cell displacement values at the cylinder where the runtime artifacts expose them;
* direct OpenFOAM force, preCICE exchanged Force, and Structure received Force;
* rollback/commit state and the preCICE acceptance/convergence classification.

Compute independently, without conflating diagnostics:

```text
r_D(k)   = ||D_k - D_(k-1)||
r_F(k)   = ||F_k - F_(k-1)||
rho_D(k) = r_D(k+1) / r_D(k)
rho_F(k) = r_F(k+1) / r_F(k)
```

Participant residuals, preCICE convergence measures, and direct OpenFOAM force differences are different quantities and remain in separate fields and analysis tables.

## Step 3 — same-input Fluid repeatability test

This is the required operator-isolation test. It uses the same exact K22 30.0 s Fluid checkpoint `S0` and a fixed nonzero displacement `D*` selected from an actual K22 trial (not an invented large displacement). Two independent replay legs use:

```text
S0 -> apply D* -> Fluid solve -> F1
rollback to S0
S0 -> apply identical D* -> Fluid solve -> F2
```

A third replay is permitted only if needed to resolve an ambiguity. Each leg must verify or explicitly mark as `NOT_MEASURED`:

* exact pointDisplacement, cellDisplacement, and mesh restoration;
* required CFD-state/checkpoint identity;
* numerical identity of the applied `D*`;
* Fluid time and force provenance;
* cleanup and process exit status.

Compute:

```text
delta_F = ||F2 - F1||
relative_delta_F = delta_F / max(||F1||, small)
```

Compare `delta_F` with the established absolute Force convergence limit `1e-3 N`; do not predeclare either result as pass. If the required state or full force replay cannot be measured safely, record `NOT_MEASURED` and stop before the inner-convergence A/B and acceleration interpretation.

## Step 4 — CFD inner-convergence diagnostic A/B

This step is executed only if the repeatability gate is established. It uses identical `S0`, identical `D*`, identical mesh/RBF/adapter, and independent scratch copies.

* A: exact K22 `fvSolution` (`nOuterCorrectors=3`, `nCorrectors=2`, no `residualControl`).
* B: diagnostic-only increased inner convergence effort, initially `nOuterCorrectors=4`, with all other solver settings unchanged. The exact edit and hash are recorded before execution.

No production solver file is changed. Record `F_current`, `F_strict`, `||F_strict-F_current||`, solver residual histories, and process status. Compare the force change against `1e-3 N`. If the A/B isolation cannot be made exact, mark the result `NOT_MEASURED` instead of inferring inner-error significance.

## Step 5 — repaired-adapter constant-relaxation baseline

Only after the repeatability and inner-convergence gates are complete, run one independent single-window diagnostic with the same repaired adapter, restart, mesh, RBF, physics, timestep, and tolerances. The only coupling change is IQN-ILS replaced by constant relaxation `0.2`. The scratch ceiling may be 40/50 and remains diagnostic-only.

Record the complete `r_D`, `r_F`, `rho_D`, and `rho_F` histories, cap/convergence status, and CFD/ANCF costs. Interpret the tail as:

* monotone with stable `rho < 1`: `SLOW_BUT_CONTRACTIVE`;
* oscillatory but decaying: `OSCILLATORY_CONTRACTIVE`;
* no stable decrease or growth: `NONCONTRACTIVE_OR_UNSTABLE`.

The K22 IQN run is compared as evidence, not as a claim that IQN settings caused the behavior. K22's `QNColumns=1` and cumulative dropped columns `18, 37, 56, 75, 94` are explained only from preCICE 3.4.1 logs/documentation or marked `UNRESOLVED`; they are not interpreted from names alone.

## Required evidence files

The run directory should contain, when the corresponding test is reached:

```text
runtime_identity.json
restart_identity.json
configuration_sha256.json
single_window_trace.jsonl
repeatability_test.json
inner_convergence_ab.json
constant_relaxation_trace.jsonl
preCICE logs and profiling
Fluid logs
Structure logs
process_cleanup.json
qualification_summary.json
```

Missing measurements are written as `NOT_MEASURED` with a reason. No value is reconstructed from a different run or inferred from a downstream symptom.

## Stop and classification rules

Stop immediately on any provenance mismatch, missing required restart state, field-identity mismatch, stale process/socket, NaN/Inf, participant crash, worker protocol error, failed rollback invariant, or inability to prove which scratch configuration was executed.

The final report must answer:

1. Whether a stable fixed point is supported, not supported, or unresolved.
2. Whether the dominant behavior is slow contraction, oscillatory contraction, noncontractive behavior, or a noisy/unresolved Fluid operator.
3. The measured same-input Force difference `||F2-F1||` and relative difference.
4. The measured current-versus-strict inner-convergence Force difference, or `NOT_MEASURED`.
5. The evidence-supported next action: acceleration, inner convergence, checkpoint/state determinism, restart transient, or other.

The phase ends after the report. It does not start Phase 1K.24, parameter sweeps, another 25-window run, or multi-slice work.
