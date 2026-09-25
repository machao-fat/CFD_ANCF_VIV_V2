# Phase 1K.28 - Old-native baseline audit

Status: `PASS_AUDIT_AND_BOUNDED_REFERENCE_RUN`

This audit qualifies an old-mesh software reference only. It does not claim a
from-t=0 native 30 s reproduction, long-window ALE stability, HH06 validation,
or production suitability. The old-native runs used the authoritative old mesh
and its own 30 s fields, without `mapFields`, without the K27 new-mesh restart,
and without RBF motion.

## Provenance

| Item | Result | Evidence |
|---|---|---|
| Git branch | PASS | `diagnostic/phase1k28-old-mesh-native-reference-v1` |
| K28 audit checkpoint | PASS | `ed3e8e2d5cb49e5d1dd7ebe3b2a91ea586494545` is an ancestor of runtime commits |
| Runtime HEAD | PASS | `4a10ee68d9d03d5bbc509191b4b1fdaf8933998f` |
| OpenFOAM | PASS | Foundation OpenFOAM 10 |
| preCICE | PASS | 3.4.1, SHA256 `b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7` |
| dt | PASS | `0.0002 s` |
| Restart | PASS, scoped | old polyMesh, native 30.0 s fields, time index 150000 |
| mapFields | PASS | not used for this restart |
| motion | PASS | `displacementLaplacian`, quadratic inverseDistance, no RBF |
| production adapter | PASS | not modified; B0/B1 are isolated libraries |

The restart identity is preserved in `old_native_restart_identity.json` and in
each run's `restart_identity.json`. Checked field and mesh hashes are recorded
there, including `U`, `p`, `k`, `omega`, `nut`, displacement fields, `phi`,
history fields, and the old polyMesh files.

## Runtime boundary

Both candidates used one physical time window and four attempts. The result is
`ACCEPTED_AT_ITERATION_LIMIT / NOT_CONVERGED`; preCICE did not report coupling
convergence. No second window, 5/25-window run, IQN sweep, relaxation sweep,
PIMPLE sweep, dt change, mesh change, RBF change, or turbulence-parameter change
was performed. The fixed-displacement Structure participant was used only as a
diagnostic participant; no ANCF worker was started.

## Motion and rollback observations

The old-native baseline reproduced the same lifecycle pattern observed in the
new-mesh baseline:

| State | meshPhi / meshPhi_0 | fvMesh flags | Other observable topology |
|---|---|---|---|
| B0 S0 checkpoint | absent | `moving=false`, `changing=false` | no `yPlus`; `Uf` has no old-time chain |
| B0 S1 after rollback | present with current/old-time objects | `moving=true`, `changing=true` | `meshPhi_0`, `V/V0/V00`, `yPlus`, and `Uf` history present |
| B1 S1 after rollback | present and canonicalized to zero values | `moving=true`, `changing=true` | same runtime topology, but meshPhi current/old values are zero |

Current `U`, `p`, `phi`, `k`, `omega`, `nut`, displacement fields, and mesh
points remained byte-level-equivalent in the captured observable summaries.
The relevant mismatch is runtime/ALE lifecycle state, not a claim that the
primary current fields were restored incorrectly.

## Gate

The old authoritative mesh plus native 30 s restart is proven consistent as a
software-reference input for this bounded run. It is not proven to be a native
from-t=0 trajectory. B0 showed an effect-relevant `meshPhi` mismatch, so B1
was authorized as the single isolated G2 candidate. B1 restored the tested
Fluid raw-force and adapter preWrite repeatability. Under the stop rule, no
additional candidate was run.
