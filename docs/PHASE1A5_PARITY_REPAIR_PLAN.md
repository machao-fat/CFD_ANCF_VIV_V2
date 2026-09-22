# Phase 1A.5 — Authoritative Worker Parity Repair Plan

## Review gate

```text
PLAN_STATUS = AWAITING_REVIEW
CODE_MODIFICATION = NOT_STARTED
BUILD = NOT_STARTED
RUNTIME = NOT_STARTED
```

This plan reconstructs the isolated parity-removal semantics from the
migrated evidence. It does not copy a historical patch or binary and does not
modify the current C++ source.

## 1. Authoritative implementation target

The implementation target is:

```text
src/ancf/ancf_worker_main.cpp
```

built by the current target:

```text
src/ancf/CMakeLists.txt:
cfd_ancf_ancf_kernel_worker = ancf_kernel.cpp + ancf_worker_main.cpp
```

The lightweight `src/ancf/worker_main.cpp` target is not the HH06 full ANCF
worker and is outside this repair.

## 2. Old logic location and behavior

### Function interface/state

The old lineage state is introduced at:

```text
src/ancf/ancf_worker_main.cpp:255–268
process_step(..., int& lineage_mode, ..., bool allow_implicit_retry, ...)
```

The persistent state is initialized at:

```text
src/ancf/ancf_worker_main.cpp:809–816
int lineage_mode = 0;
```

The state transition is implemented at:

```text
src/ancf/ancf_worker_main.cpp:546–610
```

The parity-dependent branches are:

```text
lineage_mode == 2 && expected_sequence % 2 == 0
allow_implicit_retry && lineage_mode == 2 && expected_sequence % 2 == 1
```

The call site passes the mutable `lineage_mode` at:

```text
src/ancf/ancf_worker_main.cpp:886–893
```

### Why the old logic is invalid

After the first repeated-identity request selects `lineage_mode == 2`, the
worker uses the parity of the transport sequence to select the physical
identity rule. A five-request same-window sequence can therefore make the next
accepted physical window arrive on an even sequence, where the old branch
incorrectly requires the old physical identity. The sequence number cannot
encode the number of retries in a preCICE implicit window.

## 3. New logic to implement

### 3.1 Preserve transport validation

The following checks remain unchanged and execute before physical identity
classification:

1. schema/protocol and payload validation;
2. non-zero, finite and bounded request/transaction IDs;
3. process-lifetime duplicate-ID rejection via `seen_request_ids` and
   `seen_transaction_ids`;
4. `sequence == expected_sequence`;
5. run/case/endpoint identity checks;
6. model/contract/payload hash checks;
7. `last_sequence` increment only after a successful response.

No transport counter, seen-ID set, or `last_sequence` state is added to the
physical checkpoint or altered by this repair.

### 3.2 Replace physical lineage classification

For `expected_sequence == 1`, retain the current seed behavior: record the
request's `global_step`, `bridge_step`, `integer_tick`, `time_s`, and `dt_s` as
the expected physical identity.

For every subsequent request, calculate two booleans from the request and the
last accepted physical identity.

#### Same-window retry

```text
same_window_retry =
    global_step == expected_global_step
    && bridge_step == expected_bridge_step
    && integer_tick == expected_tick
    && abs(time_s - expected_time_s) <= 1e-12
    && abs(dt_s - expected_dt_s) <= 1e-15
```

#### Next-window request

Use the existing `next_tick(expected_tick, expected_dt_s, next_tick_value)`
helper and canonical time-tick validation:

```text
next_window_request =
    global_step == expected_global_step + 1
    && bridge_step == expected_bridge_step + 1
    && next_tick(expected_tick, expected_dt_s, next_tick_value)
    && integer_tick == next_tick_value
    && canonical_time_tick(time_s, request_tick)
    && integer_tick == request_tick
    && abs(time_s - (expected_time_s + expected_dt_s)) <= 1e-12
    && abs(dt_s - expected_dt_s) <= 1e-15
```

Acceptance rule:

```text
if allow_implicit_retry:
    accept if same_window_retry OR next_window_request
else:
    accept only if next_window_request
```

Any other physical identity is rejected with the existing identity-continuity
failure classification. After acceptance, update the expected physical identity
fields to the accepted request exactly as the current code does.

### 3.3 Remove parity state

The implementation should remove the obsolete `lineage_mode` state and its
parameter/call-site plumbing, because no valid post-seed decision depends on
sequence parity after the replacement. The `allow_implicit_retry` setting
remains because it controls whether same-window retries are legal at all.

No new wire field is needed. The physical identity remains represented by the
existing authoritative tuple:

```text
global_step, bridge_step, integer_tick, time_s, dt_s
```

## 4. Affected state variables

| state | planned handling |
|---|---|
| `expected_global_step` | retain; compare equal for retry or `+1` for next window |
| `expected_bridge_step` | retain; compare equal for retry or `+1` for next window |
| `expected_tick` | retain; compare equal for retry or exact `dt_s` tick advance |
| `expected_time_s` | retain; compare equal for retry or exact `dt_s` advance |
| `expected_dt_s` | retain; require unchanged for both legal identities |
| `lineage_mode` | remove; it is the state carrying parity-dependent classification |
| `allow_implicit_retry` | retain; gate same-window retry acceptance |
| `last_sequence` | retain; session-monotonic transport order |
| `seen_request_ids` | retain; process-lifetime duplicate guard |
| `seen_transaction_ids` | retain; process-lifetime duplicate guard |
| `request_id`, `transaction_id` | retain as fresh transport identities per request |
| `q`, `qdot`, `qddot` | not owned by this classification patch; preserve numerical path |

## 5. Required tests before qualification

No tests are run as part of this plan-only step. After review and code
modification, the following tests are required before any real preCICE
qualification:

### Source/static checks

- no remaining `sequence %`, `expected_sequence %`, `parity`, or odd/even
  branch in the authoritative worker lineage state machine;
- the alternate hash-padding/index modulo operations remain unchanged and are
  not misclassified as lineage logic;
- `lineage_mode` is absent from the full-worker implementation;
- transport duplicate guards and `last_sequence + 1` remain present.

### Deterministic worker lineage cases

1. One physical window with multiple retries.
2. Two physical windows.
3. Five requests per physical window, giving sequences `1..10`.
4. Monotonic `sequence`, `request_id`, and `transaction_id`.
5. Unchanged physical identity during every same-window retry.
6. Exactly one-window physical advancement at the accepted next window.
7. Constant `dt_s`; exact tick/time advancement by one `dt_s`.
8. Invalid mixed identities rejected.
9. Duplicate transport identities rejected even when physical identity is valid.

### Checkpoint and regression cases

- rollback restores `q`, `qdot`, `qddot`, physical step and physical time;
- rollback does not restore or reuse sequence/request/transaction identity;
- a discarded trial cannot contaminate a later independent request;
- cold restart still requires a valid first physical identity and fresh session
  transport counters;
- SHM1 and DMP1 request/response serialization remains unchanged;
- existing checkpoint lifecycle, ANCF kernel and SHM1 regressions remain PASS.

### Build/evidence requirements

The post-change evidence must record:

- current Git commit and source SHA-256 values;
- CMake/compiler/build flags;
- worker binary SHA-256 generated from the current source;
- raw deterministic test output and machine-readable result;
- worker start count, PID/ownership, exit code, cleanup result and residual;
- explicit distinction between offline worker qualification and real FSI
  qualification.

## 6. Explicit non-goals

This repair plan does not authorize:

- changes to the implicit preCICE trial-displacement ordering;
- changes to `dt`, relaxation, damping, turbulence, mesh, force scaling, or
  HH06 physical parameters;
- OpenFOAM or preCICE startup;
- copying or selecting a historical binary;
- three-slice work or long-duration FSI.

## 7. Review stop condition

```text
PLAN_READY_FOR_REVIEW = YES
CPP_MODIFICATION = WAITING_FOR_REVIEW
BUILD = NOT_AUTHORIZED_AT_THIS_STEP
RUNTIME = NOT_AUTHORIZED_AT_THIS_STEP
```

Implementation must not begin until this source-level plan is reviewed and
accepted.
