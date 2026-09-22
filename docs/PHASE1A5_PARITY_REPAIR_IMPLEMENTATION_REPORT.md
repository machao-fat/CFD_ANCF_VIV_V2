# Phase 1A.5 — Authoritative Worker Parity Repair Implementation Report

## Scope and status

```text
branch = repair/worker-lineage-implicit-contract-v1
git_commit_at_implementation = 1e964fc6b6d77c76f474da950a28e6d3ed163e38
worker_repair_commit = 0383920
implementation_status = SOURCE_REPAIRED_AND_BUILT
preCICE_runtime = NOT_RUN
OpenFOAM_runtime = NOT_RUN
Phase_1B = NOT_STARTED
```

The implementation follows the approved Phase 1A.5 plan. No historical
binary or historical source snapshot was copied. The old repository was not
accessed.

## Source identity

| item | value |
|---|---|
| old authoritative source SHA-256 | `83f2d643f855894c8e74aaa11d0c76684e74886ffa0ccfa044b9fb368367deb9` |
| new authoritative source SHA-256 | `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` |
| source changed by implementation | `src/ancf/ancf_worker_main.cpp` only |
| source diff | 8 insertions, 45 deletions |
| other production source files changed | none |

The pre-edit source snapshot and empty pre-edit Git diff for the target file
were saved outside the repository under:

```text
/home/machao/projects/CFD_ANCF_VIV_V2_prephase1_evidence/phase1a5_parity_repair/
```

## Exact semantic change

The obsolete `lineage_mode` state, function parameter, main-loop state, and
call-site argument were removed from the authoritative full ANCF worker.

For every request after the first physical identity seed, the worker now
computes:

```text
same_window_retry =
    (global_step, bridge_step, integer_tick, time_s, dt_s)
    == the last accepted physical identity

next_window_request =
    global_step       = expected_global_step + 1
    bridge_step       = expected_bridge_step + 1
    integer_tick      = next_tick(expected_tick, expected_dt_s)
    time_s            = expected_time_s + expected_dt_s
    dt_s              = expected_dt_s
```

The existing canonical time/tick helpers and tolerances are retained. When
`allow_implicit_retry` is enabled, either exact same-window retry or exact
next-window identity is accepted. When it is disabled, only the next physical
window is accepted.

The transport sequence is no longer used to choose physical identity
classification. Existing sequence ordering, duplicate request-ID guards,
duplicate transaction-ID guards, protocol validation, finite checks, model
validation, contract/hash validation, ANCF kernel execution, and the existing
accepted-identity update remain in the worker.

## Static checks

The following checks passed against the modified authoritative worker:

- no `lineage_mode` remains in `src/ancf/ancf_worker_main.cpp`;
- no `sequence %` or `expected_sequence %` expression remains there;
- no exact-word `even`, `odd`, or `parity` lineage branch remains there;
- `git diff --check` passed.

## Build identity and result

The current worker target was configured and built from the current source
tree with:

```text
cmake version 3.22.1
GNU C++ 11.4.0
compiler = GNU 11.4.0 (/usr/bin/c++)
C++ standard = gnu++17
build type = Release
target = cfd_ancf_ancf_kernel_worker
source CMake directory = src/ancf
```

The observed compile flags were:

```text
-O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror -std=gnu++17
```

Build result:

```text
[100%] Built target cfd_ancf_ancf_kernel_worker
```

The generated worker binary was:

```text
/tmp/cfd_ancf_viv_phase1a5_build.B7PESs/cfd_ancf_ancf_kernel_worker
SHA-256 = 3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596
```

This is a source-built binary from the current branch; it was not executed.

## Tests executed

| test/check | result |
|---|---|
| authoritative-worker parity/static search | PASS |
| `git diff --check` | PASS |
| CMake configure for current `src/ancf` target | PASS |
| build `cfd_ancf_ancf_kernel_worker` | PASS |

## Tests not executed

The following were intentionally not run in this implementation step:

- deterministic one-window/multi-retry worker protocol tests;
- deterministic two-window and five-requests-per-window identity tests;
- transport monotonicity and duplicate-ID runtime tests;
- physical checkpoint/rollback tests;
- discarded-trial contamination tests;
- cold-restart tests;
- SHM1/DMP1 regression tests;
- ANCF numerical regression tests;
- real preCICE qualification;
- OpenFOAM or coupled FSI runtime;
- Phase 1B implicit trial-displacement audit;
- 2-window, 5-window, or 25-window FSI qualification.

Therefore this report establishes a source-level repair and successful
compilation only. It does not promote the transport-ID status to runtime
production-qualified and does not change any FSI qualification status.
