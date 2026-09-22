# Known issues and forbidden shortcuts

## HIGH PRIORITY — unverified coupling-loop defect hypothesis

The historical Structure participant loop checkpoints a physical trial, advances
preCICE, reads force, solves ANCF and scatters trial motion. The 5-iteration audit
showed force residuals decreasing (`0.0874, 0.0699, 0.0559, 0.0448, 0.0358 N`) while
displacement residual remained zero. The leading hypothesis is that the trial
displacement is not written back to Fluid_0000 before the next implicit solve, so the
fluid sees stale committed motion during retries.

This is a hypothesis, not a proven root cause. The new repository records it for a
future targeted preCICE 3.4.1 semantic audit. Do not silently “fix” it during a
benchmark run.

## Worker lineage parity defect

An old worker classified same-window retry versus next-window request using sequence
parity. That is invalid. Physical window identity must use
`(global_step, bridge_step, integer_tick, time_s, dt_s)`; transport IDs
`sequence/request_id/transaction_id` must remain session-monotonic and never be
restored from a physical checkpoint. The isolated repair passed 2 windows x 5
requests with 8 rollbacks, but it was not deployed and re-qualified in `slice0000`.

## ALE/flow runaway

The bounded test showed a late feedback chain consistent with large force, large
absolute structural displacement change, high mesh velocity/mesh Co, flow velocity
growth and SST `omega` growth. Do not mask this with arbitrary dt, relaxation, SST,
fvSchemes or fvSolution changes. First establish the actual displacement read/write
semantics and retry state lineage.

## Adapter lineage mismatch

The source used for an isolated adapter read-path qualification and the production
adapter/binary lineage were not proven identical. A diagnostic one-window pass cannot
be promoted to production qualification without source and binary identity evidence.

## Forbidden historical shortcuts

- Do not revive the old Re=100 / D=1 m / 50 m / 604-vertex participant for HH06.
- Do not map CFD faces one-to-one to ANCF nodes.
- Do not treat `1188.28 N` equilibrium reaction as the `1175 N` benchmark input.
- Do not change SHM1 from full length to `0--5.94 m` merely to cure divergence.
- Do not call a diagnostic displacement offset a physical HH06 result.
