# Phase 1D.5 — Runtime Coupling Contract Closure

## Disposition

**`READINESS_GATE_UNRESOLVED`**

The iteration-cap inconsistency has been resolved by aligning the contract
metadata to the configured preCICE runtime cap of 20. The bounded real-run
readiness gate is not closed: the current case status and launcher do not
describe or invoke the Phase 1D participant consistently. No real preCICE,
OpenFOAM, HH06, or ANCF participant runtime was started. No commit was created.

## Reviewed worktree

- Repository: `/home/machao/projects/CFD_ANCF_VIV_V2`
- Branch: `repair/worker-lineage-implicit-contract-v1`
- HEAD: `8550e6a4cd7fb62c0f8b49471a704604965a7ff6`
- Base: `1e964fc6b6d77c76f474da950a28e6d3ed163e38` (`v0.1-clean-handoff`)
- `git diff --check`: PASS
- Initial tracked diff: 8 files, 787 insertions, 285 deletions; no file-mode
  summary changes.

The dirty files were the documented Phase 1D Strategy C implementation,
configuration, test, and report/evidence changes. No unrelated path was found.
The Phase 1D report and machine evidence were left unchanged. This phase changes
only `cases/hh06_single_slice/contract.json` for the iteration cap and adds this
report; the existing Phase 1D changes remain uncommitted.

## Iteration-cap provenance and resolution

| Value | Location / provenance | Runtime meaning | Evidence assessment |
|---:|---|---|---|
| 8 | `contract.json` at clean-handoff commit `1e964fc`; no later V2 history explains it | No current participant or launcher uses this number to terminate implicit iterations | No migrated qualification found that used 8. Its original intent is undocumented; it is stale metadata, not a proven runtime limit. |
| 20 | `precice-config.xml` at the same clean-handoff commit; also present in migrated RETRY11 runtime diagnostics | The configured preCICE implicit-scheme maximum | Historical RETRY11 reports 20 iterations and 16 accepted-at-cap windows with `Convergence=0`. Other migrated bounded studies used 5 and 10; none relied on 8. |

The current Structure participant obtains its trace cap from the XML
`max-iterations` element. preCICE 3.4.1 configuration documentation defines
`min-iterations` / `max-iterations` as the implicit-loop iteration bounds, and
the installed 3.4.1 `precice-tools check` accepted the current configuration
with no major issues. See the [preCICE coupling-scheme configuration
reference](https://precice.org/configuration-coupling).

Therefore the XML value 20 is authoritative for runtime termination. The JSON
contract was corrected from 8 to 20; the XML was not changed. The participant
audit now reports `contract_json=20`, `precice_xml=20`, `values_match=true`.
The audit reports this comparison but does not currently make a mismatch a
blocking check; at this reviewed state the values are equal.

The accepted Phase 1D report and its qualification summary retain their
historical snapshot showing 8 versus 20 at the time Phase 1D was completed.
They were not rewritten to erase that provenance.

## Cap-honesty behavior

Each attempt records `iteration_index` and `precice_max_iterations`. When
preCICE ends an attempt without requesting rollback at the configured maximum,
the trace records `ACCEPTED_AT_ITERATION_LIMIT`; it does not call that
convergence. An earlier non-retry acceptance is recorded conservatively as
`accepted_by_precice_before_iteration_limit`.

The installed Python `Participant` exposes checkpoint-requirement methods but
no separate convergence-status query. Thus the trace does not claim an
independently queried `CONVERGED` bit. The existing offline cap-honesty test
passed after the cap alignment. A window accepted exactly at the cap remains
classified conservatively as `ACCEPTED_AT_ITERATION_LIMIT`, even if the
underlying final iteration may also have met a convergence measure.

## Readiness and launcher audit

Current readiness semantics are inconsistent:

- `contract.json` remains `READY_FOR_DRY_RUN`; its purpose and existing case
  documents explicitly do not authorize integration.
- The Structure participant's audit accepts exactly `READY_FOR_DRY_RUN`.
- `launch.sh` requires exactly `READY` and numeric values for `Mx/My/Kx/Ky/Cx/Cy`
  and `ax0/ay0`, which remain `null` in the contract. The participant instead
  loads its structural model from the P1 artifact, and the contract says initial
  acceleration is not required.
- There is no repository schema or existing consumer for
  `READY_FOR_BOUNDED_COUPLING_QUALIFICATION`; introducing that status and
  changing its consumers needs review. The case was not promoted to `READY` or
  any validated/production state.
- Launcher defaults point to nonexistent case-local participant and worker
  files. The current participant source exists under `src/`, and the current
  worker build exists under `/tmp`, but neither is the launcher's default.
- The launch command passes `--contract`, which the current participant CLI
  does not accept, and omits the CLI's required `--run --worker` pair. Running
  that launcher command would not start the current Strategy C participant
  correctly.
- `jq` is absent from this environment, while `launch.sh` requires it before
  reaching its adapter guard.
- The XML exchange directory
  `/home/machao/OpenFOAM/coupling/singal_slice/slice0000/precice-sockets` exists
  and is writable. The launcher creates a different case-local
  `precice-sockets` directory, which the XML does not reference. The case log
  directory is writable and the four launcher log files were absent at audit
  time; the launcher removes those files before a run if they exist.

These are launch/readiness contract defects, not evidence to change ANCF or CFD
physics. Because no bounded-qualification status is defined and the launcher
does not invoke the accepted participant interface, readiness is unresolved.
No launcher or status changes were made in this phase pending review.

## Offline preflight results

| Gate | Result | Evidence |
|---|---|---|
| Contract JSON parse | PASS | `python3 -m json.tool` |
| Structure `--audit-only` | PASS; reports no runtime started | F0 provenance and hashes, Force initial exchange, SHM1 capability, geometry and mapping pass; iteration caps match at 20 |
| F0 evidence | PASS | Result JSON SHA256 `6b272f695ebefe28daa176723483f611c42f8d25dbae8d83de928f3790811b8a`; recovery report SHA256 `6737908b9b29f4ff8550ba4353ff88ad90ad5cfc1355a57a885d655f7d3d7b3b`; restart is case `ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1`, time directory/global time `30` / `30.0 s`, index `150000` |
| Force initialization config | PASS | Force exchange has `initialize="yes"`; preCICE 3.4.1 static config validation reports no major issues |
| Adapter runtime SHA | PASS | Active adapter path `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so`; SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`; expected-hash case passed and deliberately wrong hash failed closed. Source provenance remains unresolved. |
| Worker source/build identity | PASS for the recorded offline build | Source SHA256 `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e`; binary SHA256 `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`; Build ID `f1e2a4d34ca5c4fe8bb3ccfbf6d695a34b88c512`; Release, CMake 3.22.1, GNU C++ 11.4.0. The binary is currently in `/tmp`, not at the launcher default. |
| Time-step consistency | PASS | Contract `dt_s=0.0002`, XML `time-window-size=0.0002`, OpenFOAM `deltaT=2e-4`, and restart `deltaT=0.0002` agree. |
| Restart identity | PASS | `30/uniform/time` records time 30.0, index 150000, deltaT 0.0002; only numeric time directory `30` exists. All Phase 1C.7A field hashes and polyMesh hashes rechecked equal the frozen provenance. |
| XML socket path | PASS as configured; launcher path differs | XML path exists and is writable; case-local path created by launch is separate. |
| Runtime executable/readiness gate | FAIL / unresolved | `pimpleFoam` exists, but `jq` is absent; default participant/worker paths are missing; launcher arguments do not match the current participant CLI; status and required numeric fields conflict. |

The system `libprecice.so` and `precice-tools` report preCICE 3.4.1. The
installed Python package metadata reports `pyprecice` 3.4.0, while its extension
dynamically resolves `libprecice.so.3` to the 3.4.1 library. No participant was
initialized, so this binding/library combination was not runtime-qualified in
this phase and should be explicitly checked before Phase 1E.

No OpenFOAM solver, preCICE participant, or ANCF participant was run. Static
configuration validation, source/hash inspection, `--audit-only`, adapter SHA
preflight, and the offline fake cap-honesty unit test were the only executable
checks in this phase.

## Test-suite limitation

The repository-wide Python `tests/ancf` suite remains recorded as
`PREEXISTING_TEST_INFRASTRUCTURE_INCOMPLETE` in the Phase 1D report. Its prior
attempt found missing modules (`coupling.stage303_interface_mapping_repair_v1`,
`coupling.openfoam_quality_contract_v3`, and
`coupling.moment_mapping_audit_v1`) and missing `results/...` artifacts. It was
not rerun or repaired here. The accepted targeted ANCF/SHM1 C++ results remain
the Phase 1D evidence; no repository-wide test PASS is claimed.

## Git and stop condition

No commits were created because the readiness gate is unresolved. The
Phase 1D implementation and evidence remain uncommitted, together with the
contract-cap correction and this report. Current HEAD remains
`8550e6a4cd7fb62c0f8b49471a704604965a7ff6`.

Recommended next action: review and explicitly authorize the minimum
launch-only contract changes needed to represent a bounded qualification and
invoke the current participant/worker safely. Do not start Phase 1E until that
review closes the status, executable, CLI, and Python-binding identity gates.
