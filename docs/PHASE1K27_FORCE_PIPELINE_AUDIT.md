# Phase 1K.27 — Force pipeline audit

Status: complete — source audit plus one bounded diagnostic runtime. This is
an experimental-path result only. It does not qualify or replace the historical
adapter and does not alter the production case.

## Frozen diagnostic context

- K26 was frozen at commit `e0da50c5660ec266c4bee50769ab95f94f0b014a`;
  K27 uses branch `diagnostic/phase1k27-force-pipeline-decomposition-v1`.
- K26's selected G2 run used one window, `dt=0.0002 s`, two minimum and four
  maximum iterations, the unchanged IQN-ILS profile, the exact 30.0 s mapped
  restart, and `D*=(1.0633832164606064e-7, 9.530777190012017e-8) m`.
- The K25 G2 experimental adapter SHA256 was
  `f9a89b21b0a0fe92f297a0c8bceb67bc5df5f52e5f7a9c35fa17df5b7eb8b754`.
  It is not the historical qualified adapter. K27 built a separately named
  diagnostic derivative; its patch, source-tree, binary SHA256, and ELF Build
  ID are recorded in the run's `runtime_identity.json`.
- The source base is the OpenFOAM adapter tree at commit
  `d53753b1c927b2413b02299c9da15725b3e772f0`, with the already documented
  K20 field/read-time repair and K25 G2 `meshPhi` canonicalization changes.
  Source-to-qualified-binary lineage remains unresolved.

## Source-level pipeline

| Stage | Exact implementation / value | Meaning in this report |
|---|---|---|
| Pressure field | `FSI/ForceBase.C`, `ForceBase::writeToBuffer()`: incompressible pressure contribution is `Sf * p_boundary * rho_boundary`; the source retains a FIXME that reference pressure is not subtracted. | Per-face pressure contribution, dimensional force. |
| Wall viscous traction | `ForceBase::devRhoReff()` selects the registered incompressible momentum-transport model and returns `rho * devSigma()`; `writeToBuffer()` contracts this with face area vector as `Sf & devRhoReff_boundary`. | Per-face viscous contribution, dimensional force. |
| Per-face total | `ForceBase::writeToBuffer()` stores pressure contribution plus viscous contribution in the configured `Force` field boundary values. | **`RAW_OPENFOAM_FORCE`** at each coupling face before preCICE mapping or acceleration. Its patch integral is the sum of these per-face vectors. |
| Adapter packing | `FSI/Force.C::write()` delegates to `writeToBuffer()`. For the configured 2-D mesh, the writer packs x/y for each face, in configured patch order and local face order. | Adapter representation of the raw face force. The z component is not sent on this 2-D coupling mesh. |
| Adapter buffer | `Interface::writeCouplingData()` calls the writer, then passes exactly `dataBuffer_[0:nWrittenData]` and `vertexIDs_` to `precice_.writeData(...)`. | **`ADAPTER_UNACCELERATED_WRITE_PAYLOAD`** (`F_adapter_preWrite`): the complete packed face array immediately before preCICE receives it. It has not yet undergone preCICE mapping or acceleration. |
| Mapping | The scratch XML configures Fluid's write mapping from `Fluid-Mesh` to `Structure-Mesh` with `nearest-neighbor`, `direction="write"`, `constraint="conservative"`. The Fluid mesh has 200 cylinder face-center vertices; the Structure mesh has one point. | **`PRECICE_MAPPED_VALUE`**: mapped Force on the Structure mesh. It is distinct from the unaccelerated face payload. |
| Coupling acceleration | The XML uses `parallel-implicit`; IQN-ILS lists both `Displacement` and `Force` on `Structure-Mesh` as primary data. The configured second participant is `Fluid_0000`. preCICE performs mapping/exchange and acceleration as part of `advance()`. | **`PRECICE_ACCELERATED_COUPLING_ITERATE`**: the stateful coupling value after preCICE's implicit acceleration, not a pure Fluid output. |
| Structure read | The diagnostic Structure participant calls `read_data("Structure-Mesh", "Force", vertex_ids, relative_read_time)` after `advance()`. On retry it reads at `dt`; on the terminal accepted/cap branch it reads at `0.0` only if coupling continues. | **`STRUCTURE_RECEIVED_FORCE`** (`F_structure_read`): the value returned to Structure by preCICE after its mapping/coupling-scheme processing. Never use it as raw OpenFOAM Force. |

The 2-D Fluid coupling buffer contains 200 × 2 = 400 scalars. The direct
per-face diagnostic retained all three physical vector components for pressure,
viscous, and total face forces. The x/y sums and full face ordering can be
compared directly with the preWrite buffer; z is diagnostic only and absent
from the 2-D preCICE payload.

Initialization is a separate event: because the Force exchange has
`initialize="yes"`, the adapter writes initial Force before participant
`initialize()`. K27 labels this `write_index=0` / `event_kind=initial`.
Subsequent Force writes are `write_index=1..4`, corresponding to physical
window 1 coupling attempts 1..4. Direct-force and preWrite logs contain the
same five ordinals, matching time/timeIndex and payload count.

## Evidence-backed preCICE semantics

The loaded runtime was preCICE 3.4.1; its path and hash are in the run identity.
The preCICE Participant API defines `relativeReadTime=0` as the current-window
start and `relativeReadTime=dt` as its end. Official acceleration
documentation explains that coupling data are modified in `advance()` using
iteration history and that parallel coupling applies the common acceleration
coefficients to all coupling data. Official mapping documentation states that
write mappings execute during `advance()` after data are written, and that a
conservative mapping preserves the global sum for extensive quantities such
as Force. These are external documentation claims, separate from the local
logs and hashes.

These documents explain why a changed Structure read value alone does not
identify a raw Fluid-force discrepancy. They do not provide the internal
pre-acceleration vector for this runtime; it was not directly observed and is
explicitly `NOT_DIRECTLY_OBSERVABLE`.

- [preCICE Participant API: `readData(relativeReadTime)`](https://api.precice.org/cpp/latest/classprecice_1_1Participant.html)
- [preCICE acceleration configuration](https://precice.org/configuration-acceleration)
- [preCICE mapping configuration](https://precice.org/configuration-mapping)
- [preCICE coupling scheme configuration](https://precice.org/configuration-coupling)

## Runtime result

At the end of K26, attempts 3/4 had equal recorded Fluid displacement, cell and point
displacement, RBF input, candidate mesh, mesh points, and solver stages through
S11. Their Structure-received Forces differed by
`0.018694803000146195 N`. K26 did not measure direct per-face raw Force or the
unaccelerated preWrite buffer, so the stage of that discrepancy was unresolved
at that point. K27 adds the following measurements.

K27 recorded and compared, aligned by writer ordinal and attempt identity:

1. actual Fluid-read Displacement vector and offset;
2. direct per-face pressure, viscous, and total Force plus integrated sums;
3. exact preWrite vertex IDs and full 400-scalar buffer;
4. existing Structure-received Force and preCICE iteration/convergence logs.

No sparse `forces.dat` output was used as a substitute. No acceleration,
solver, tolerance, mesh, RBF, physics, or production-adapter setting changed.

The exact accepted comparison is attempts 3 and 4, not attempts 1 and 2:

| Observation | Attempt 3 | Attempt 4 | Comparison |
|---|---:|---:|---|
| Fluid-read displacement | `D*=(1.0633832164606064e-7, 9.530777190012017e-8) m` | same | identical 400-value SHA256 `d32bcccbaeeca2e6685266c70dc358dfd0ba7a76ec226990fa27cc741b1fb339` |
| Solver records S01–S11 | time `30.0002 s`, index `150001` | same | all 15 paired stage records equal, excluding only `solve_id` and PID |
| Raw OpenFOAM pressure Force (x,y) | `(0.09491663342849935, -0.04864713153160179) N` | same | exact per-face arrays; difference `0 N` |
| Raw OpenFOAM viscous Force (x,y) | `(0.0016816169665504375, 0.0005520383013623268) N` | same | exact per-face arrays; difference `0 N` |
| `RAW_OPENFOAM_FORCE` (x,y) | `(0.09659825039505082, -0.04809509323023877) N` | same | exact 200-face arrays; difference `0 N` |
| Adapter preWrite sum (x,y) | same raw sum | same raw sum | 400-scalar payload SHA256 equal; L2 difference `0` |
| Structure Force read (x,y) | `(0.11051428672025433, -0.03561152033583504) N` | `(0.09659825039505082, -0.04809509323023877) N` | difference norm `0.01869480300014619 N` |
| Structure Force read offset | `dt = 0.0002 s` (retry) | `0.0 s` (accepted boundary) | **different read branches** |

The Fluid displacement read offsets match (`dt` on both attempts); the
Structure Force read offsets do not. Thus K27 establishes, for this tested G2
branch and pair, repeatability of solver trajectory through S11, the raw
per-face Force, and the unaccelerated adapter payload. It locates the remaining
received-Force difference downstream of the adapter write. It does **not**
separate temporal sampling/read-branch effects from mapping or stateful IQN
acceleration, because the Structure read offsets differ and the pre-acceleration
value was not directly instrumented.

The window stopped after four attempts at the diagnostic ceiling. preCICE
reported `Convergence=0`; the result is `ACCEPTED_AT_ITERATION_LIMIT`, not
converged. Both Fluid and Structure exited with code 0. The experimental K27
adapter SHA256 is
`0edcfae77d51d8a57a354a1b745c77f6c15108bf532be0d4893394e80a2d785d`, Build ID
`90bd299327c280ecd4b72d5a9695a64540dd389b`; the qualified historical adapter
was not loaded. Full runtime identity, per-attempt arrays, alignment, preCICE
logs, and cleanup record are preserved in
`evidence/phase1k27_force_pipeline/run-20260925T090832Z-e0da50c/`.
