# Known issues and forbidden shortcuts

## HIGH PRIORITY — real implicit FSI and runaway requalification remain open

Phase 1B source tracing and a deterministic fake backend confirmed the participant's
old retry behavior: after rollback it restored ANCF physical state and wrote the
previous `committed_motion`, discarding the just-computed trial interface
displacement. This explains the identically zero displacement residual in that
historical participant path (`STALE_COMMITTED_MOTION`).

Phase 1D implements a participant-side fixed-point lifecycle and passes offline
deterministic qualification. Every attempt now writes its own ANCF trial before the
associated preCICE `advance`; rejected physical ANCF state is rolled back while the
Force iterate and iteration history survive. This has **not** been qualified in a
real preCICE/OpenFOAM run. Therefore the stale-motion defect is confirmed, but its
role in the historical late-window ALE/flow/turbulence runaway remains unconfirmed.
Do not infer long-run stability or change physical/numerical parameters from the
offline test alone.

## Worker lineage parity repair — offline qualified, runtime deployment pending

The authoritative V2 worker source no longer uses sequence parity to classify
same-window retries versus next-window requests. Commit `0383920` classifies
physical identity using `(global_step, bridge_step, integer_tick, time_s,
dt_s)` and preserves independent monotonic transport identities. The current
source-built worker passed the bounded offline 2-window x 5-request test,
including acceptance of sequence 6 as the next physical window and physical
rollback without transport-ID rollback.

The repair has not been deployed or runtime-qualified in the HH06 slice.
Production runtime qualification remains pending.

## ALE/flow runaway

The bounded test showed a late feedback chain consistent with large force, large
absolute structural displacement change, high mesh velocity/mesh Co, flow velocity
growth and SST `omega` growth. Do not mask this with arbitrary dt, relaxation, SST,
fvSchemes or fvSolution changes. First establish the actual displacement read/write
semantics and retry state lineage.

## Bounded HH06 runtime is launch-ready only; real qualification remains pending

Phase 1D.6 closes the bounded launcher contract with a separate
`BOUNDED_COUPLING_QUALIFICATION` authorization for exactly two physical windows.
The maturity/status remains `READY_FOR_DRY_RUN`. Preflight requires the pinned
worker and Fluid adapter, the frozen 30.0 s F0 evidence, Force initial data,
`dt=0.0002`, `max-iterations=20`, Python/preCICE runtime qualification, and a
clear XML-configured socket directory. It does not start either participant.

No real HH06 Fluid/Structure coupling was started in Phase 1D.6. Real two-window
qualification, convergence behavior, and stability remain unqualified; this
authorization is not production readiness and does not resolve the historical
25-window ALE/flow/turbulence runaway.

## Adapter source lineage remains unresolved

The source-to-binary provenance of the installed Fluid adapter is unresolved. Phase
1C.7C qualified initial Force configuration behavior only for SHA256
`26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572` (Build ID
`e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`). The HH06 launcher fails closed on a
different adapter binary. The pin is restricted to the bounded qualification
profile; it does not resolve adapter source/build provenance or imply production
readiness.

## Forbidden historical shortcuts

- Do not revive the old Re=100 / D=1 m / 50 m / 604-vertex participant for HH06.
- Do not map CFD faces one-to-one to ANCF nodes.
- Do not treat `1188.28 N` equilibrium reaction as the `1175 N` benchmark input.
- Do not change SHM1 from full length to `0--5.94 m` merely to cure divergence.
- Do not call a diagnostic displacement offset a physical HH06 result.
