# Phase 1A.5 — Parity Repair Qualification Report

## Qualification boundary

```text
qualification = PASS_OFFLINE_WORKER_PARITY_REPAIR
branch = repair/worker-lineage-implicit-contract-v1
git_commit_at_qualification = 1e964fc6b6d77c76f474da950a28e6d3ed163e38
worker_repair_commit = 0383920
preCICE = NOT_RUN
OpenFOAM = NOT_RUN
HH06_case_runtime = NOT_RUN
Phase_1B = NOT_STARTED
commit_created = NO
```

This qualification executed the current source-built persistent C++ worker
directly through the current `KernelStepRequest` and kernel response codecs.
It did not load an HH06 case, initialize preCICE, start OpenFOAM, or modify
production source during testing.

## Source, build, and runtime identity

| item | recorded identity |
|---|---|
| Git commit at qualification | `1e964fc6b6d77c76f474da950a28e6d3ed163e38` |
| worker repair commit created after qualification | `0383920` |
| branch | `repair/worker-lineage-implicit-contract-v1` |
| modified worker source | `src/ancf/ancf_worker_main.cpp` |
| modified worker source SHA-256 | `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` |
| built target | `cfd_ancf_ancf_kernel_worker` |
| worker binary | `/tmp/cfd_ancf_viv_phase1a5_build.B7PESs/cfd_ancf_ancf_kernel_worker` |
| worker binary SHA-256 | `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596` |
| CMake | `3.22.1` |
| compiler | GNU C++ `11.4.0` (`/usr/bin/c++`) |
| CMake source directory | `src/ancf` |
| CMake generator | `Unix Makefiles` |
| build type | `Release` |
| C++ standard | `gnu++17` |
| observed flags | `-O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror -std=gnu++17` |

The worker binary was launched only by the offline lineage harness and exited
cleanly with return code 0 for every positive test session. No historical
binary was used.

## Equivalence target

The migrated current-repository evidence records the isolated repair
semantics as:

```text
same-window retry:
  global_step, bridge_step, integer_tick, time_s, dt_s unchanged

next physical window:
  global_step + 1
  bridge_step + 1
  integer_tick advanced by exactly one dt_s tick
  time_s advanced by exactly dt_s
  dt_s unchanged

transport identity:
  sequence, request_id, transaction_id independent of physical rollback
```

The current source-level repair was qualified against these behavioral
semantics. This is behavioral equivalence; it is not a claim that the current
source or binary has the historical isolated source or binary hash.

## Offline worker lineage tests

The deterministic direct-worker harness used a non-HH06 two-element model,
`dt_s = 0.001`, integer tick delta `1,000,000`, and a finite test force. Each
positive session used a persistent worker process and fresh transport IDs.

| case | request/physical identity pattern | result |
|---|---|---|
| A. one physical window, multiple retries | sequences `1..5`; all `(global_step, bridge_step, tick, time) = (1, 1, 1,000,000, 0.001)` | PASS |
| B. two physical windows | sequences `1..5` at window 1, `6..10` at window 2 | PASS |
| C. sequence 6 classification | sequence 6 accepted with `(2, 2, 2,000,000, 0.002, 0.001)` | PASS; next-window, not retry |
| D. same-window even/odd retry | same physical identity accepted at sequence 2 and sequence 3 | PASS |
| E. next-window even/odd | next window accepted at sequence 2 and at sequence 3 after one retry | PASS |
| F. transport identity | sequence/request/transaction IDs strictly increasing and unique; response echoes matched | PASS |
| G. physical rollback | q/qdot/qddot restored to checkpoint input; retry retained window identity and used fresh IDs | PASS |

The decisive historical failure pattern is therefore repaired: after five
requests in physical window 1, sequence 6 is accepted as the first request
of physical window 2. The worker returned all ten response frames.

## Rollback and transport separation

The persistent-worker rollback case used this sequence:

```text
sequence 1, request_id 900001, transaction_id 1900001: window 1 trial
physical rollback: restore q, qdot, qddot and window-1 identity
sequence 2, request_id 900002, transaction_id 1900002: window 1 retry
sequence 3, request_id 900003, transaction_id 1900003: window 2 request
```

The retry request carried the checkpoint physical identity unchanged. Its
replayed q/qdot/qddot response matched the first trial to a maximum absolute
difference of `1e-14`. Sequence, request ID, and transaction ID were not
restored or reused.

The existing V2 checkpoint lifecycle regression was also run:

```text
Ran 3 tests ... OK
```

It passed the exact q/qdot/qddot restore, checkpoint retention, retry/commit,
and monotonic transport-counter checks. The worker-level duplicate guards
were separately exercised: duplicate `request_id` and duplicate
`transaction_id` were each rejected with return code 18.

## Current V2 contract preservation

Static and source-scope checks confirmed:

- `lineage_mode` is absent from `src/ancf/ancf_worker_main.cpp`;
- no `sequence %` or `expected_sequence %` branch remains in the worker;
- no exact-word `even`, `odd`, or `parity` physical-lineage branch remains;
- the worker still validates exact sequence ordering;
- duplicate request/transaction-ID guards remain active;
- protocol, finite-value, model, contract/hash, ANCF kernel, and response
  validation paths were not changed by the parity repair;
- `ancf_kernel.cpp`, `ancf_kernel.hpp`, `kernel_protocol.py`, `protocol.py`,
  SHM1/DMP1 serialization, checkpoint format, OpenFOAM files, preCICE files,
  and HH06 physical parameters were not modified.

The current implementation diff is limited to the approved authoritative
worker source. The qualification report and earlier audit documents are
documentation artifacts; no production contract source was changed outside
the worker.

## Evidence artifacts

The raw qualification outputs are preserved outside the repository under:

```text
/home/machao/projects/CFD_ANCF_VIV_V2_prephase1_evidence/phase1a5_parity_repair/
```

Relevant files include:

```text
qualification_provenance.txt
qualification_static_checks.txt
offline_worker_lineage_qualification.json
transport_identity_guard_qualification.json
checkpoint_lifecycle_qualification.log
```

## Final classification

```text
SOURCE_TO_BUILD = TRACEABLE
PARITY_ASSUMPTION = REMOVED
HISTORICAL_SEQUENCE_6_FAILURE_PATTERN = REPAIRED_OFFLINE
PHYSICAL_IDENTITY_SEMANTICS = QUALIFIED_OFFLINE
TRANSPORT_IDENTITY_SEMANTICS = PRESERVED_AND_QUALIFIED_OFFLINE
CHECKPOINT_ROLLBACK_REGRESSION = PASS
OFFLINE_QUALIFICATION = PASS
REAL_PRECICE_QUALIFICATION = NOT_RUN
FSI_STABILITY_CLAIM = NOT_AUTHORIZED
```

This report does not promote the result to HH06 validation, VIV
reproduction, long-run stability, or production FSI qualification. No further
work is started in this phase.
