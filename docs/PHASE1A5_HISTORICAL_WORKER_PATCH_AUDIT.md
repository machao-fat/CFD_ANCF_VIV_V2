# PHASE1A5 — Historical Worker Patch Audit

## Audit boundary

| item | result |
|---|---|
| audit type | read-only forensic audit |
| current repository | `/home/machao/projects/CFD_ANCF_VIV_V2` |
| current source inspected | `src/ancf/ancf_worker_main.cpp` |
| historical repository | `D:/研二文件/开题准备/CFD_ANCF_VIV` (read-only inspection) |
| historical capability commit | `355640e11925b9feddd1a52bb3d93596e5ee8251` on `feature/ancf-spanwise-hydro-matrix-v1` |
| historical HH06 evidence commit | `ea7909748da5d6be399abedaa405a0df549360d5` on `validation/g1-terminal-diagnostic-serialization-repair-v1` |
| source modified | **no** |
| commit/merge/cherry-pick | **none** |
| build/runtime/OpenFOAM/preCICE | **not performed** |

The report distinguishes the current V2 source, the unpatched historical
baseline, and the isolated parity-removal source. The isolated source was
qualified as an external source snapshot; it was not a Git commit in the
historical repository and was not deployed to `slice0000`.

## 1. Historical defect summary

### 1.1 Discovery event

The defect was exposed by the `HH06_IMPLICIT_RETRY_ENABLED_MULTIITER_QUALIFICATION`
run: a bounded real Fluid/Structure test with `max-iterations=5`,
`parallel-implicit`, and one accepted first physical window followed by a
second-window request. The archived result is:

`evidence/legacy_qualification/hh06_single_slice_coupling_history_v1/evidence/runtime/hh06_bounded_multiwindow_ale_qualification_v1/implicit_retry_enabled_5window_v1/HH06_IMPLICIT_RETRY_ENABLED_MULTIITER_QUALIFICATION_RESULT.json`

The evidence was archived in historical commit
`ea7909748da5d6be399abedaa405a0df549360d5` (2026-09-22 21:46:34 +0800).

### 1.2 Exact sequence-6 failure

The first physical window used transport sequences `1..5`. It completed after
four rollbacks and was committed at sequence 5. The next physical window then
sent:

```text
sequence      = 6
global_step   = 2
bridge_step   = 2
integer_tick  = 400000
time_s        = 0.0004
dt_s          = 0.0002
```

The old worker had already selected `lineage_mode == 2` and used
`expected_sequence % 2` to select the physical-identity branch. Since 6 is
even, it entered the same-window branch, which required the old identity
`(1, 1, 200000, 0.0002, 0.0002)`. The request was therefore rejected with the
worker identity-continuity failure (return code 16), no response header was
returned, and the participant reported:

```text
HH06_STRUCTURE_0000_WRAPPER_ERROR:
HH06ContractError: worker response header missing at sequence 6
```

The subsequent Fluid-side broken pipe was downstream of this worker protocol
failure, not the primary cause.

### 1.3 Why parity is invalid

`sequence` is a session transport counter. It depends on how many implicit
iterations/retries happened in the preceding physical window. Therefore the
next physical window can begin at an even or odd sequence. It cannot be
encoded by sequence parity.

## 2. Historical patch summary

### 2.1 Source identities

| role | path/identity | SHA256 or commit | status |
|---|---|---|---|
| unpatched capability baseline | `CFD_ANCF_VIV_BUILD/hh06_shm1_source_blob_355640e1/ancf_worker_main.cpp` | `83f2d643f855894c8e74aaa11d0c76684e74886ffa0ccfa044b9fb368367deb9` | baseline |
| baseline Git provenance | `feature/ancf-spanwise-hydro-matrix-v1` | `355640e11925b9feddd1a52bb3d93596e5ee8251` | capability source |
| isolated qualified patch | `runtime/hh06_worker_lineage_transition_fix_audit_v1/qualified_source_v1/ancf_worker_main.cpp` | `22072322a4d0559c1958c81c0d70d57ab89c0c4d5b30db54fa86e0863d044e0c` | isolated qualified source |
| isolated qualified binary | `runtime/hh06_worker_lineage_transition_fix_audit_v1/qualified_source_v1/build/cfd_ancf_ancf_kernel_worker_lineage_transition_qualified` | `6cd66a7b37028c6bfd24c8190e46a7f9074aae1e9561b63302555d60d78ec06d` | not deployed |

No Git commit was recorded for the patched source snapshot itself. The source
hash and the archived qualification manifest are the authoritative identity
for that isolated patch.

### 2.2 Production-source change

The direct baseline-to-qualified diff changes only
`ancf_worker_main.cpp`:

1. Removes the `lineage_mode` argument and persistent state.
2. Removes the `sequence % 2 == 0/1` branches.
3. Classifies every post-seed request using the physical tuple:
   `global_step`, `bridge_step`, `integer_tick`, `time_s`, `dt_s`.
4. Accepts a same-window identity only when `allow_implicit_retry` is true.
5. Accepts a next-window identity only after exactly one `dt_s` tick/time and
   one-step increments of `global_step` and `bridge_step`.
6. Retains sequence ordering, duplicate request/transaction-ID guards, model
   and contract hashes, and finite-state validation.

The isolated test harness and JSON reports are qualification artifacts. The
forensic diff provides no evidence that `kernel_protocol.py`, `protocol.py`,
the ANCF kernel, SHM1/DMP1 serialization, or checkpoint mathematics were
changed by this parity patch.

The archived qualification exercised sequences `1..10`, two physical windows,
four rollbacks per window, and returned all ten response headers. It was
`PASS_ISOLATED_ONLY`; production deployment was explicitly false.

## 3. CURRENT vs HISTORICAL QUALIFIED PATCH

| component | historical source / qualified patch | current V2 source | difference | impact |
|---|---|---|---|---|
| worker implementation | `ancf_worker_main.cpp`, baseline `83f2...`; isolated patch `220723...` | `src/ancf/ancf_worker_main.cpp`, `83f2...` | current is byte-identical to unpatched baseline, not to `220723...` | parity defect remains |
| protocol wire layout | existing production KernelModel/KernelStepRequest layout | `src/ancf/kernel_protocol.py`, `src/ancf/protocol.py` | no parity-specific change evidenced | retain; not root cause |
| request validation | schema, protocol, sequence equality, run/case/endpoints, hashes, finite checks | same validation plus current duplicate-ID sets | no relevant difference | retain |
| physical state machine | `same_window_retry OR next_window_request`, controlled by physical identity | `lineage_mode` plus parity-selected branches after sequence 2 | missing historical replacement | sequence 6 can be rejected |
| checkpoint/rollback | physical `q/qdot/qddot` rollback; transport identity remains session-monotonic | Python backend separation is present; C++ worker maintains process-lifetime seen-ID sets | parity patch did not change math/checkpoint payload | no change required for this defect |
| transport identity | `sequence`, `request_id`, `transaction_id` monotonic/unique and not checkpoint-restored | current worker validates exact sequence and duplicate IDs | semantics retained in current source | must not be coupled to parity |
| ANCF kernel/SHM1/DMP1 | same capability baseline; no patch evidence | current `src/ancf` baseline | no relevant difference | out of scope for parity migration |

## 4. Parity-logic audit

### 4.1 Current source

The current file contains the direct defect at the following locations:

```text
src/ancf/ancf_worker_main.cpp:570
    lineage_mode == 2 && expected_sequence % 2 == 0

src/ancf/ancf_worker_main.cpp:574
    allow_implicit_retry && lineage_mode == 2 && expected_sequence % 2 == 1
```

The surrounding comment explicitly describes an odd sequence as the
next-window prediction. This is not merely a comment discrepancy: the branch
controls which physical identity is accepted.

### 4.2 Historical qualified semantics

The isolated patch does more than delete two textual `% 2` expressions. It
removes the `lineage_mode` state and its function/call-site plumbing, then
applies the following deterministic rules to every request after the first:

```text
same-window retry:
  global_step, bridge_step, integer_tick, time_s, dt_s unchanged

next-window request:
  global_step + 1
  bridge_step + 1
  integer_tick = exact next dt_s tick
  time_s = previous time_s + dt_s
  dt_s unchanged
```

With implicit retry enabled, either identity is legal. With it disabled, only
the next-window identity is legal. `sequence`, `request_id`, and
`transaction_id` remain transport identities and are still checked
independently.

### 4.3 Identity ownership table

| field | role | current handling | historical qualified handling |
|---|---|---|---|
| `global_step` | physical window identity | stored/checked, but selected through parity after mode selection | equal for retry or `+1` for next window |
| `bridge_step` | physical window identity | stored/checked, parity-selected branch | equal for retry or `+1` for next window |
| `integer_tick` | physical time identity | stored/checked, parity-selected branch | equal for retry or exact `dt_s` advance |
| `time_s` | physical time identity | stored/checked, parity-selected branch | equal for retry or `+dt_s` |
| `dt_s` | physical time-step identity | required unchanged in branches | required unchanged in both legal identities |
| `sequence` | transport/session order | exact expected sequence plus parity misuse | exact expected sequence only; never physical classification |
| `request_id` | transport uniqueness | process-lifetime duplicate guard | same guard retained |
| `transaction_id` | transport uniqueness | process-lifetime duplicate guard | same guard retained |
| `seen_request_ids` / `seen_transaction_ids` | transport state | process-lifetime sets | retained; not physical checkpoint state |

## 5. Current source status

The current V2 source is **not** the historical qualified patch. The current
worker SHA256 equals the unpatched `355640e1` source blob and the direct parity
branches are still present. The current Python/backend transport-counter
separation is present, but it cannot repair the C++ physical-lineage decision
inside the worker.

The historical isolated binary and its patched source are evidence only. They
were not copied into `src/ancf`, not deployed to the V2 HH06 case, and not
proven as the binary selected by the current participant.

## 6. Migration conclusion

```text
CURRENT_V2_CPP_PARITY_LOGIC = PRESENT
HISTORICAL_QUALIFIED_PATCH_IN_CURRENT_SOURCE = NO
HISTORICAL_PATCH_DEPLOYED_TO_V2_RUNTIME = NO
AUDIT_CLASSIFICATION = REPAIR_REQUIRED
```

This is conclusion **B — `REPAIR_REQUIRED`**. The required migration scope is
limited to the authoritative full worker lineage state machine in
`src/ancf/ancf_worker_main.cpp`; it does not authorize implementation in this
audit.

## 7. Recommended migration scope

When separately authorized, migrate only the verified state-machine semantics
from the isolated source, while preserving the current V2 source baseline for
comparison. Do not copy the isolated binary as a substitute for source
integration. The migration should record:

- baseline and post-patch SHA256;
- exact source diff;
- current CMake target and compiler identity;
- worker binary SHA256;
- source-to-build-to-runtime selection manifest;
- explicit distinction between physical state rollback and transport identity;
- no changes to ANCF kernel, SHM1/DMP1 codec, HH06 physical parameters, or
  OpenFOAM/preCICE files.

## 8. Tests required before production qualification

Before any HH06 runtime qualification, the following offline tests are
required:

1. One physical window with multiple retries at both even and odd sequences.
2. Two physical windows with five requests each (`sequence=1..10`), proving
   the second window can begin at sequence 6.
3. Exact physical identity checks for retry versus one-`dt_s` advancement.
4. Strict monotonic and duplicate rejection for sequence/request/transaction
   IDs across rollback.
5. Physical checkpoint restore for `q`, `qdot`, and `qddot` without restoring
   transport counters.
6. Invalid mixed identities rejected.
7. Existing SHM1/DMP1, protocol, checkpoint, and worker lifecycle regressions.
8. A source → build → selected-runtime hash manifest before any preCICE
   handshake or OpenFOAM run.

## Final audit gate

```text
HISTORICAL_DEFECT_CONFIRMED = YES
HISTORICAL_PATCH_SOURCE_CONFIRMED = YES (isolated source hash 22072322...)
CURRENT_CPP_PARITY_DEFECT = PRESENT
PATCH_DEPLOYMENT_CONFIRMED = NO
FINAL_CLASSIFICATION = REPAIR_REQUIRED
NO_CODE_MODIFIED = TRUE
NO_COMMIT_CREATED = TRUE
NO_BUILD_OR_RUNTIME_EXECUTED = TRUE
```
