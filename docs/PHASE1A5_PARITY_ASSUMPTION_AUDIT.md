# Phase 1A.5 — Parity Assumption Audit

## Scope and execution boundary

| item | value |
|---|---|
| repository | `/home/machao/projects/CFD_ANCF_VIV_V2` |
| branch | `repair/worker-lineage-implicit-contract-v1` |
| source search scope | current `src/` only |
| old repository access | **none** |
| C++ source modified | **no** |
| build performed | **no** |
| runtime started | **no** |
| preCICE/OpenFOAM started | **no** |
| audit status | `PARITY_ASSUMPTION_FOUND` |

The search was performed before any implementation change. The patterns
searched in the current `src/` tree were equivalent to:

```text
sequence.*%
even
odd
parity
request_id
transaction_id
%
```

## 1. Direct sequence-parity findings

Only one current source file contains sequence-parity logic:

| path and lines | finding | classification |
|---|---|---|
| `src/ancf/ancf_worker_main.cpp:570` | `lineage_mode == 2 && expected_sequence % 2 == 0` | direct worker lineage assumption |
| `src/ancf/ancf_worker_main.cpp:574` | `allow_implicit_retry && lineage_mode == 2 && expected_sequence % 2 == 1` | direct worker lineage assumption |
| `src/ancf/ancf_worker_main.cpp:575–579` | comment describes the next odd sequence as a next-window prediction | direct parity-dependent explanation |

The surrounding state machine is:

1. `expected_sequence == 1` seeds the expected physical identity.
2. At sequence 2, the worker chooses `lineage_mode == 2` if the second
   request repeats the physical identity, or `lineage_mode == 1` if it is the
   next physical window.
3. Once `lineage_mode == 2`, later request acceptance is selected by sequence
   parity. Even sequences are forced through the same-window branch; odd
   sequences use the implicit-retry branch and may represent either a retry or
   a next-window prediction.

This is the defect. The accepted physical identity must decide whether a
request is a same-window retry or a next-window request. The wire sequence may
only enforce session order and uniqueness.

The current full-worker source hash is:

```text
src/ancf/ancf_worker_main.cpp
83f2d643f855894c8e74aaa11d0c76684e74886ffa0ccfa044b9fb368367deb9
```

The migrated isolated repair evidence identifies the parity-removal source as
`22072322...` and the isolated binary as `6CD66A7B...`; neither identity is the
current checked-out source/binary lineage.

## 2. Non-lineage `even`/`odd`/`parity` hits

The remaining textual matches do not classify coupling-window identity:

| path | match | why it is not the target defect |
|---|---|---|
| `src/ancf/matlab_step_diagnostic.m:2` | `parity audit` | name of a MATLAB/C++ numerical comparison diagnostic |
| `src/ancf/protocol.py:43` | `ties-to-even` | Python rounding documentation for canonical time ticks; not sequence state |
| `src/ancf/ancf_modal_free_diagnostic.cpp:287` | `step % output_every` | diagnostic output sampling |
| `src/ancf/ancf_spanwise_hydrodynamic_matrix_selftest.cpp:130,303–304` | component/index modulo | matrix/component indexing |
| `src/ancf/worker_main.cpp:101` | `bytes.size() % 64` | SHA-256 padding |
| `src/ancf/sha256.hpp:29` | `bytes.size() % 64` | SHA-256 padding |

No other `sequence %`, `sequence` parity, or `lineage_mode` assumption was
found in the current `src/` tree.

## 3. Transport identity findings

The `request_id` and `transaction_id` search shows the following ownership:

| owner/path | observed behavior | parity risk |
|---|---|---|
| `src/ancf/ancf_worker_main.cpp:291–295,543–544` | rejects zero/duplicate IDs and retains process-lifetime seen-ID sets | no parity use; must remain unchanged |
| `src/ancf/ancf_worker_main.cpp:840,893` | owns the seen-ID sets for the persistent worker session | must not be checkpoint-restored |
| `src/coupling/hh06_structure_0000/structure_0000_participant.py:327–349,410–421` | allocates independent session-monotonic sequence/request/transaction counters | no parity use; preserve |
| `src/ancf/worker_client.py:34–35,159–194` | duplicate-ID client guard | no parity use; preserve |
| `src/ancf/protocol.py:103–160,203–236` | serializes and validates transport IDs | no parity use; preserve |
| `src/ancf/kernel_protocol.py:395–536,632–645` | serializes and validates full kernel identity and hashes | no parity use; preserve |
| `src/cpp_physics_ownership_v1/physics_ownership_worker_main.cpp` | separate physics-ownership worker with duplicate-ID guards | not the HH06 full-worker lineage path; no parity hit |
| `src/coupling/precice_adapter_v1/` and `src/coupling/precice_ancf_adapter_v1/` | string envelope identities and validation layers | no sequence-parity hit; not the current HH06 C++ worker |

No current source search result shows `request_id` or `transaction_id` being
restored from a physical checkpoint. The planned C++ change must not alter
these guards or Python counter ownership.

## 4. Required physical identity semantics

The repair must classify each request after the initial seed using the complete
physical identity tuple:

```text
(global_step, bridge_step, integer_tick, time_s, dt_s)
```

### Same physical-window retry

All five fields equal the last accepted physical identity within the existing
floating-point tolerances for `time_s` and `dt_s`.

### Next physical window

```text
global_step       = expected_global_step + 1
bridge_step       = expected_bridge_step + 1
integer_tick      = expected_tick + canonical_tick_delta(expected_dt_s)
time_s            = expected_time_s + expected_dt_s
dt_s              = expected_dt_s
```

The existing `next_tick()` and `canonical_time_tick()` helpers are suitable
for the tick/time checks and should be reused rather than introducing a second
rounding policy.

### Transport identity

The following remain session-monotonic and independent of physical rollback:

```text
sequence
request_id
transaction_id
```

They must continue to be validated before acceptance, never selected by parity,
and never restored by the physical checkpoint path.

## 5. Audit conclusion before implementation

```text
DIRECT_PARITY_ASSUMPTION = FOUND
DIRECT_PARITY_LOCATIONS = ancf_worker_main.cpp:570,574,575-579
OTHER_SEQUENCE_PARITY_HITS = NONE
TRANSPORT_ID_PARITY_HITS = NONE
PYTHON_TRANSPORT_SEPARATION = PRESENT
CPP_PARITY_REPAIR_IN_CURRENT_SOURCE = NO
IMPLEMENTATION_AUTHORIZED_BY_THIS_DOCUMENT = NO
```

The exact source-level change plan is recorded separately in
`docs/PHASE1A5_PARITY_REPAIR_PLAN.md`. No C++ modification is included in this
audit document.
