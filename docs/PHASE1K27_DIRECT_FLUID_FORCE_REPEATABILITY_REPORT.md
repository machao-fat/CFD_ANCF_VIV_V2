# Phase 1K.27 — Direct Fluid Force / Adapter Payload / preCICE Decomposition

## Result

Primary classification: **`PRECICE_DOWNSTREAM_STATE_EXPLAINS_RECEIVED_FORCE_DIFFERENCE`**.

This classification locates the measured discrepancy after the adapter's
unaccelerated `writeData(Force)` payload. It does not claim that IQN alone is
the cause: the two Structure Force reads use different relative offsets, and
preCICE's pre-acceleration value was not directly observed.

The tested G2 Fluid branch is repeatable through the direct per-face Force and
adapter preWrite payload for attempts 3 and 4. This is a scoped diagnostic
finding, not a global Fluid-operator qualification or an FSI convergence pass.
The one-window run reached its four-attempt diagnostic ceiling and was
`ACCEPTED_AT_ITERATION_LIMIT` with preCICE `Convergence=0`.

## Frozen identity and scope

- K26 checkpoint HEAD / K27 runtime HEAD: `e0da50c5660ec266c4bee50769ab95f94f0b014a`.
- K27 branch: `diagnostic/phase1k27-force-pipeline-decomposition-v1`.
- Restart: fresh scratch copy of the frozen new-mesh restart at global time
  `30.0 s`; exact restart field and mesh hashes are in `runtime_identity.json`
  and `restart_identity.json`.
- Fluid inputs: `D*=(1.0633832164606064e-7,
  9.530777190012017e-8) m`; one physical window, `dt=0.0002 s`, attempts 1–4.
- OpenFOAM Foundation 10; preCICE runtime 3.4.1 at
  `/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1`, SHA256
  `b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7`.
- Python `/usr/bin/python3.10`, 3.10.12; pyprecice metadata 3.4.0.
- Worker source SHA256
  `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` and
  worker binary SHA256
  `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596` were
  identity-checked; no worker process was started.
- RBF diagnostic library SHA256
  `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`.
- Diagnostic solver `pimpleFoamPhase1K26Diag`, SHA256
  `e895e5f1788146da2205e4c8bb0b959f99f66e426c92dc7233d7ac303fd91e96`.
- K27 diagnostic-only adapter:
  `libpreciceAdapterPhase1K27ForceDiag.so`, SHA256
  `0edcfae77d51d8a57a354a1b745c77f6c15108bf532be0d4893394e80a2d785d`, Build
  ID `90bd299327c280ecd4b72d5a9695a64540dd389b`. Adapter source tree SHA256
  `3cc6158625fdb90900468786603deb0e316d087d45f6e68a3f69ced8eb0bf6e2`,
  instrumentation patch SHA256
  `800bdf3d1712b97976a396450e1cd946ea1217114aa4cace9297fd72874fc966`.
  Source base commit `d53753b1c927b2413b02299c9da15725b3e772f0`; built with
  GCC 11.4.0 using `source /opt/openfoam10/etc/bashrc; wmake libso .` in an
  isolated source tree (`linux64GccDPInt32Opt`, `-std=c++14`). It was built
  separately from the K25 G2 experimental adapter; source-to-historically-
  qualified-binary provenance remains unresolved. The qualified historical
  adapter was not loaded.
- Frozen new-mesh release-force result SHA256
  `ce2cbf6edcda28ae46bf3d0a10b2a6d75ec8641b8417549818acda9c98369949`;
  restart-provenance JSON SHA256
  `24d572f35e9b06bd34c3a934a67db61559e109e8f4d59a398075822cd208a7f2`.
- No production adapter, XML, solver settings, mesh, RBF parameters, physics,
  timestep, convergence tolerances, or IQN settings were changed. No worker
  process was started.

The Fluid and Structure participant processes both exited with code 0 after
9.49 s. The process cleanup record shows no stop reason or orphan participant.
The scratch socket directory and all experiment artifacts were preserved.

## Data-path meanings

The locally inspected adapter source path is:

`ForceBase::writeToBuffer()` pressure and viscous face traction
→ Force field per-face values
→ `Force::write()` / `Interface::writeCouplingData()` packing
→ `Participant::writeData(Fluid-Mesh, Force, vertexIDs, buffer)`
→ preCICE mapping and implicit coupling processing in `advance()`
→ `Participant::readData(Structure-Mesh, Force, ..., relativeReadTime)`.

| Name | Meaning | K27 observability |
|---|---|---|
| `RAW_OPENFOAM_FORCE` | Per-face pressure plus viscous traction evaluated by the adapter's OpenFOAM `ForceBase` expression, before preCICE. Integrated result is the sum over the cylinder's 200 faces. | Directly captured per face, per contribution, and integrated. This is not an independent second `forces` function-object calculation. |
| `F_adapter_preWrite` | Exact packed 2D x/y buffer and vertex ordering passed immediately to `writeData(Force)`, before preCICE processing. | Full 400-scalar array, IDs, SHA256, and sums captured. |
| `PRECICE_MAPPED_VALUE` | Force after configured Fluid-Mesh → Structure-Mesh conservative nearest-neighbor write mapping. | Mapping configuration and mapping events observed; a separate mapped-value buffer was not directly exposed. |
| `PRECICE_ACCELERATED_COUPLING_ITERATE` | Stateful coupling value after implicit coupling processing/acceleration across iterations. | pre-acceleration vector and internal mapped/accelerated intermediate buffers were `NOT_DIRECTLY_OBSERVABLE`. |
| `F_structure_read` | Value returned to Structure by `readData()` at its selected relative time. | Captured exactly with time/offset and attempt ordinal. It is not raw Fluid Force. |

The exact configuration is `parallel-implicit`; Force is written from
`Fluid-Mesh` to `Structure-Mesh` with conservative nearest-neighbor mapping.
IQN-ILS uses `Displacement` and `Force` as primary data with the unchanged
one-column profile. Locally, the preCICE logs show mapping calls at `t=0` for
initialization and `t=0.0002` for each subsequent attempt. External preCICE
documentation states that write mapping occurs during `advance()`, and that
parallel coupling accelerates all coupling data using common coefficients;
this explains why a participant's written value is not necessarily what the
other participant reads, but it does not reveal this run's internal
pre-acceleration vector. [Acceleration semantics](https://precice.org/configuration-acceleration),
[mapping semantics](https://precice.org/configuration-mapping),
[coupling-scheme semantics](https://precice.org/configuration-coupling), and
the [Participant `readData` API](https://api.precice.org/cpp/latest/classprecice_1_1Participant.html)
are external documentation evidence. The installed 3.4.1 runtime identity is
separately pinned in the local evidence.

## Attempt alignment and exact results

K27 used event-ordinal alignment because this adapter path does not expose a
native preCICE coupling-attempt ID in its write buffer. The alignment combines
Fluid displacement read ordinal and next solve index, Force writer ordinal,
Structure attempt ordinal, physical time/timeIndex, and the G2 solver's
`solve_id`. The full derivation is in `attempt_alignment.json`.

Attempts 3 and 4 satisfy the valid same-Fluid-input prerequisites:

- Both are in physical window 1, global solve time `30.0002 s`, time index
  `150001`; both Fluid `readData(Displacement)` calls occurred at OpenFOAM
  time `30 s`, index `150000`, with relative read offset `dt=0.0002 s`.
- Each Fluid read has 200 vertices / 400 scalars and the same exact displacement
  array SHA256:
  `d32bcccbaeeca2e6685266c70dc358dfd0ba7a76ec226990fa27cc741b1fb339`.
- All 15 paired S01–S11 solver-stage records compare equal after excluding
  only solve ordinal and process ID. The RBF input/candidate geometry and mesh
  points are included in this stage evidence.

| Quantity | Attempt 3 | Attempt 4 | Difference / identity |
|---|---:|---:|---|
| Pressure Force `(Fx,Fy)` | `(0.09491663342849935, -0.04864713153160179) N` | same | exact per-face hash `e2f1235726bf983976a4d9e1e5950ea47afbc0ec7d4f4ba48d7273186ae0c913`; norm delta `0 N` |
| Viscous Force `(Fx,Fy)` | `(0.0016816169665504375, 0.0005520383013623268) N` | same | exact per-face hash `9836cd4609999efbe5d7e7f8d02e73977df8d0180dec18c9407530acadfc54e5`; norm delta `0 N` |
| `Fraw` `(Fx,Fy,Fz)` | `(0.09659825039505082, -0.04809509323023877, 8.580926016153679e-17) N` | same | 200-face total hash `d32ff95f148848d3b7c8d7dfb9337c543a05fb90cca3f4d8a4ee37ac6f070f23`; exact delta `0 N` |
| Adapter preWrite sum `(Fx,Fy)` | `(0.09659825039505082, -0.04809509323023877) N` | same | 400 scalars; payload SHA256 `093a44f3bbe918a4897ad8b8f6dd579a105028ef470ed78735ed2b3042cf3fc6`; vertex-ID hash `de663cfb3b82787ec7c32624aba8cd8de6555fc906b507971a2c2f3207b5fe52`; L2 delta `0` |
| `F_structure_read` `(Fx,Fy)` | `(0.11051428672025433, -0.03561152033583504) N` | `(0.09659825039505082, -0.04809509323023877) N` | vector delta `(-0.01391603632520351,-0.01248357289440373) N`; norm `0.01869480300014619 N` |
| Structure Force read offset | `dt=0.0002 s` (retry endpoint) | `0.0 s` (accepted boundary) | not the same read branch/relative offset |

The initial release Force gate also passed using the established componentwise
x/y tolerance interpretation; the frozen new-mesh F0 was not modified.

## Interpretation and required answers

1. **Were attempts 3/4 actual Fluid-read displacement inputs equal? Yes.**
   Their full-array hash, vertex IDs, offsets, physical window, and time
   identity match; exact values are stated above.
2. **Direct raw Force:** `Fraw_3 = Fraw_4`; difference norm is exactly `0 N`.
3. **Pressure and viscous terms:** both full per-face arrays and integrated
   x/y components are exactly equal between attempts 3 and 4.
4. **Adapter payload:** full payload hashes, vertex ordering, and sums are
   identical; full-array L2 difference is zero.
5. **Why does Structure receive a different Force?** The discrepancy first
   appears downstream of the adapter `writeData` buffer. The two Structure
   reads select different relative offsets (`dt` for retry vs `0` at accepted
   boundary). Mapping and stateful parallel-implicit acceleration also occur
   downstream, but their intermediate values were not separately observed.
   Therefore the broad attribution is `PRECICE_DOWNSTREAM_STATE`; the exact
   sub-cause among temporal read sampling, mapping, and acceleration history
   remains unresolved.
6. **Is the Fluid operator repeatable on the tested G2 branch? SUPPORTED**,
   narrowly: same observed Fluid input and same S01–S11 stages yielded bitwise-
   equal captured per-face raw Force and adapter preWrite data for this pair.
   This does not prove repeatability for all states, windows, or branches.
7. **Historical wording correction:** K23/K24/K25 attempts 1 and 2 are not
   valid same-Fluid-input Force replay evidence. Structure writing the same
   nominal `D*` did not mean Fluid read the same displacement. Keep K24's
   observed S0/S1 object/history mismatch and K25's per-candidate state
   snapshots as valid observations, but withdraw their causal claims that
   those Force deltas measured Fluid operator non-repeatability or that Group
   1 causally reduced the same-input Force difference. K23's 40-attempt
   non-converged-at-cap observation remains valid; its replay-force inference
   is superseded by K26/K27 input alignment.
8. **CFD inner-convergence A/B:** **YES, authorized as the next diagnostic
   only**, because the tested G2 raw Force and outgoing adapter payload now
   repeat for a verified same-input pair. K27 did not execute that A/B; any
   broader claim that all Fluid rollback state is repaired is not established.
9. **IQN retest:** **NO**. It remains gated on the next authorized inner-
   convergence adequacy diagnostic; K27 does not authorize acceleration
   retuning or requalification.

## Logs and evidence

The coupling window had four attempts, three rollback requests, `QNColumns=1`,
`DeletedQNColumns=0`, `DroppedQNColumns=2`, and `Convergence=0`. The last
preCICE Force convergence residual was `1.87e-2 N` against `1e-3 N`; the
window was accepted only at the diagnostic iteration ceiling. Per-data zeros
in `convergence.log` are not used as quantitative evidence; detailed stdout
`measureConvergence` messages and `iterations.log` are preserved.

Machine-readable run directory:
[`evidence/phase1k27_force_pipeline/run-20260925T090832Z-e0da50c/`](../evidence/phase1k27_force_pipeline/run-20260925T090832Z-e0da50c/).
Key artifacts include `runtime_identity.json`, `restart_identity.json`,
`fluid_input_trace.jsonl`, `solver_stage_trace.jsonl`,
`direct_force_trace.jsonl`, `adapter_prewrite_force.jsonl`,
`structure_received_force.jsonl`, `attempt_alignment.json`,
`force_stage_diff.json`, `precice_acceleration_audit.json`,
`precice_iterations.log`, `precice_convergence.log`, participant logs, and
`process_cleanup.json`. Runtime artifacts and instrumentation binaries remain
experimental and uncommitted.
