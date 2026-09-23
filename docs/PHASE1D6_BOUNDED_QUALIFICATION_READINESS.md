# Phase 1D.6 — Bounded Qualification Launch Contract Readiness

**Classification:** `PASS_BOUNDED_QUALIFICATION_READINESS`
**Branch:** `repair/worker-lineage-implicit-contract-v1`
**Scope:** launcher/readiness contract only; no real HH06 runtime was started.

## Disposition

The HH06 single-slice launcher is now fail-closed and can construct only the
explicit two-physical-window qualification profile after every preflight gate
passes. This does not start Phase 1E and does not establish real coupling
convergence, HH06 stability, VIV reproduction, or production readiness.

The scientific maturity status remains `READY_FOR_DRY_RUN` in the root,
structure, and interface contracts. Execution permission is separate:

```json
{
  "mode": "BOUNDED_COUPLING_QUALIFICATION",
  "max_windows": 2
}
```

The structure and interface contracts retain their default-deny launch flags
and declare the same narrowly scoped override. Preflight validates all three
contracts and rejects a missing, malformed, or non-exact override. Repository
inspection found no JSON Schema or existing consumer that rejects additive
contract fields; the active launcher now validates these additions explicitly.

## Runtime contract

| Item | Required/current value | Result |
|---|---|---|
| Scientific status | `READY_FOR_DRY_RUN` | Preserved; not promoted |
| Execution mode | `BOUNDED_COUPLING_QUALIFICATION` | Explicitly required |
| Physical windows | `max_windows=2` | Root authorization, linked overrides, CLI, participant guard, and XML agree |
| Implicit iterations | `max_iterations=20` | Contract and preCICE XML agree |
| Time window | `dt=0.0002 s` | Contract, XML, and restart `uniform/time` agree |
| preCICE termination | `<max-time-windows value="2"/>` | Exact two-window cap; no duration-only `max-time` remains |
| Force initialization | Fluid → Structure `Force`, `initialize="yes"` | Present and XML validator passes |
| Scientific duration metadata | `duration_s=0.2`, `accepted_window_limit=1000` | Preserved; not confused with the two-window qualification bound |

The installed OpenFOAM v10 `pimpleFoam -help` exposes `-case` and not
`-endTime`; the Fluid command therefore uses the supported `-case` form. The
preCICE OpenFOAM adapter documentation describes delegating end-time control to
preCICE by default, and the configuration validator accepts the two-window
scheme. The launcher also checks that the adapter function object is enabled in
`system/controlDict`. See the official [preCICE XML reference](https://precice.org/configuration-xml-reference)
and [OpenFOAM adapter support documentation](https://precice.org/adapter-openfoam-support).

## Commands constructed by preflight (not executed)

Fluid:

```text
/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin/pimpleFoam \
  -case /home/machao/projects/CFD_ANCF_VIV_V2/cases/hh06_single_slice
```

Structure:

```text
/usr/bin/python3.10 \
  /home/machao/projects/CFD_ANCF_VIV_V2/src/coupling/hh06_structure_0000/structure_0000_participant.py \
  --case /home/machao/projects/CFD_ANCF_VIV_V2/cases/hh06_single_slice \
  --run \
  --worker /home/machao/projects/CFD_ANCF_VIV_V2/build/phase1d6_worker/cfd_ancf_ancf_kernel_worker \
  --max-windows 2 \
  --audit-output <run-directory>/structure_audit.json \
  --trace-output <run-directory>/structure_trace.jsonl
```

The obsolete `--contract` argument is absent. The participant is resolved from
the repository source tree. Logs and per-run audit/trace outputs are placed in
`evidence/phase1e_bounded_2window/<unique-run-id>/`; preflight does not create
that run directory. The worker path is an explicit required CLI argument with
no `/tmp` or case-local fallback.

## Worker and adapter identity

Worker source:
`src/ancf/ancf_worker_main.cpp`, SHA256
`c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e`.

The source-built worker at
`/home/machao/projects/CFD_ANCF_VIV_V2/build/phase1d6_worker/cfd_ancf_ancf_kernel_worker`
is executable and matches qualified binary SHA256
`3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`.
Its recorded Build ID is `f1e2a4d34ca5c4fe8bb3ccfbf6d695a34b88c512`; it was built
with CMake 3.22.1, GNU C++ 11.4.0, Release configuration, and `-O3 -DNDEBUG`.
The binary is ignored build output and is not committed.

The only accepted Fluid adapter is
`/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so`,
SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`,
Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`.

```text
ADAPTER_RUNTIME_BINARY_PINNED = YES
ADAPTER_SOURCE_PROVENANCE_RESOLVED = NO
```

The SHA guard runs before socket checks or participant startup. The verified
adapter directory is explicitly prepended to the `LD_LIBRARY_PATH` inherited by
the Fluid process. A different adapter path or SHA fails closed. This does not
resolve adapter source-to-binary provenance.

## Python/preCICE runtime identity

Classification: `PYTHON_PRECICE_BINDING_RUNTIME_CONFIRMED`.

The isolated scratch test used the same interpreter selected for Structure and
ran both minimal participants through construction, mesh vertex definition,
`requires_initial_data()`, initial writes, `initialize()`, initialized-data read
at relative time `0.0`, data writes, one harmless `advance()`, and `finalize()`.
Both exit codes were zero. The initial probe Force `(3.25, -2.5)` was explicitly
synthetic and is not the HH06 physical release Force.

| Runtime component | Identity |
|---|---|
| Python | `/usr/bin/python3.10`, version `3.10.12` |
| Package metadata | `pyprecice 3.4.0` |
| Imported module | `/home/machao/.local/lib/python3.10/site-packages/precice/__init__.py`, SHA256 `a110a4ab07722a6f21d727a7c179b9295db961a74a595f12b01ad07d7cf1f751` |
| Extension | `/home/machao/.local/lib/python3.10/site-packages/cyprecice.cpython-310-x86_64-linux-gnu.so`, SHA256 `184b94ac58397ee2de696b10b3ccb11955033f9d4563146368f5b097f0c1684c` |
| Loaded runtime | `/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1`, runtime version `3.4.1`, SHA256 `b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7` |
| Scratch XML SHA256 | `17e3e366cf78afc67b01ce554896282e1b82fa4f34d2beef1c2eaa4660093c58` |
| Fluid / Structure exits | `0 / 0` |

Machine-readable evidence is
`evidence/phase1d6_python_precice_binding/qualification.json`.

## F0, restart, socket, and preflight

The preflight revalidated the frozen F0 evidence and exact restart identity:

```text
restart case/time/index = ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1 / 30.0 s / 150000
Fx0_raw =  0.0655270406544 N
Fy0_raw =  0.05872987413554 N
Fz0_raw = -2.44420351566e-21 N (provenance record)
F0 result JSON SHA256 = 6b272f695ebefe28daa176723483f611c42f8d25dbae8d83de928f3790811b8a
F0 recovery report SHA256 = 6737908b9b29f4ff8550ba4353ff88ad90ad5cfc1355a57a885d655f7d3d7b3b
```

The already-qualified one-time conversion remains unchanged:
`F_section=F_raw/0.028 m`, then `F_strip=F_section*1.98 m`.

The single exchange directory resolved from the production XML is
`/home/machao/OpenFOAM/coupling/singal_slice/slice0000/precice-sockets`.
It exists, is writable, contains no stale files/sockets, and the active-process
scan found no participant using it. The launcher does not create a second
case-local socket directory and does not delete stale contents; stale files
cause a fail-closed stop. A nonblocking lock also prevents two instances of this
launcher from using the same exchange path concurrently.

The actual invocation was:

```text
cases/hh06_single_slice/launch.sh --preflight-only \
  --worker /home/machao/projects/CFD_ANCF_VIV_V2/build/phase1d6_worker/cfd_ancf_ancf_kernel_worker \
  --max-windows 2
```

Result: `PASS_PREFLIGHT_ONLY`, exit code `0`; all required checks passed,
including strict JSON, linked bounded authorization, cap/dt consistency, F0 and
restart hashes, Force initialization, adapter SHA, worker SHA, participant
path/CLI, Python binding identity, XML socket path/process-use check, OpenFOAM
executable, and log-parent availability. `runtime_started=false`.

## Targeted tests and limits

| Qualification | Result |
|---|---|
| Existing Phase 1D implicit fixed-point/F0/cap-honesty tests | PASS |
| Physical checkpoint lifecycle tests | PASS |
| Current worker two-window transport/duplicate-ID tests | PASS |
| Adapter SHA exact-pass / deliberately wrong-SHA fail-closed tests | PASS |
| Launcher command construction / wrong cap / contract strictness / socket-user checks | PASS |
| Python preCICE scratch two-participant runtime | PASS |
| Targeted command: six test modules | 21 tests, PASS |
| `bash -n` for both launcher scripts | PASS |
| Python bytecode compilation for launcher helper and participant | PASS |
| JSON syntax checks for all three case contracts | PASS |
| `precice-config-validate` on production XML | PASS, “No major issues detected” |
| `git diff --check` | PASS |

The repository-wide `tests/ancf` suite remains
`PREEXISTING_TEST_INFRASTRUCTURE_INCOMPLETE`. The prior Phase 1D evidence
records missing modules `coupling.stage303_interface_mapping_repair_v1`,
`coupling.openfoam_quality_contract_v3`, `coupling.moment_mapping_audit_v1`,
and missing `results/...` JSON artifacts. This suite was not repaired or
re-run, and no repository-wide PASS is claimed.

No `pimpleFoam` solver, HH06 preCICE participant, persistent ANCF worker, or
real FSI run was started. The scratch Python binding test is the only participant
runtime in this phase and used an isolated temporary configuration.

## Git record and stop condition

The Strategy C production implementation and its offline evidence were committed
separately before the bounded-launch changes:

| Commit | Subject |
|---|---|
| `5cac610` | `fix: implement implicit trial feedback lifecycle` |
| `4b70bb3` | `test: qualify Strategy C offline coupling contract` |
| `67abda3` | `fix: gate HH06 launcher to bounded qualification` |

The Phase 1D.6 test/evidence/documentation commit is the final HEAD recorded by
the handoff after this report is committed. The worktree must be clean at
handoff. This report does not authorize starting Phase 1E; wait for a separate
explicit instruction before any real HH06 run.
