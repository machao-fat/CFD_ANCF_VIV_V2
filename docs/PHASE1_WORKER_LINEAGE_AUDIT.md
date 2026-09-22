# Phase 1A — Authoritative Worker Lineage Audit

## Audit boundary

| item | value |
|---|---|
| repository | `/home/machao/projects/CFD_ANCF_VIV_V2` |
| branch | `repair/worker-lineage-implicit-contract-v1` |
| HEAD | `1e964fc6b6d77c76f474da950a28e6d3ed163e38` (`v0.1-clean-handoff`) |
| audit type | static source/evidence lineage audit |
| old repository access | **none** |
| OpenFOAM started | **no** |
| preCICE initialized | **no** |
| ANCF runtime started | **no** |
| production source modified | **no** |

Only the current V2 tree, its contracts, and the evidence already migrated into
`evidence/legacy_qualification/` were inspected. Historical paths appearing
inside those documents were treated as recorded evidence, not accessed.

## Gate

```text
AUTHORITATIVE_WORKER_LINEAGE = NOT_CLOSED
WORKER_TRANSITION_REPAIR = PASS_ISOLATED_ONLY
PYTHON_TRANSPORT_COUNTER_SEPARATION = PRESENT_IN_CURRENT_SOURCE
CPP_SEQUENCE_PARITY_LOGIC = STILL_PRESENT
SOURCE_TO_BUILD_TO_RUNTIME_TRACEABILITY = NOT_PROVEN
PRODUCTION_QUALIFICATION = DO_NOT_PASS
```

The isolated transition evidence remains valid as isolated evidence. It does
not promote the current V2 worker to production-qualified status because the
current authoritative C++ source is the unpatched source identity and the
isolated patched source/binary was not deployed into this repository's runtime
path.

## 1. Current source lineage table

| layer | current V2 path | current dependency/consumer | source identity observed | audit classification |
|---|---|---|---|---|
| ANCF numerical kernel | `src/ancf/ancf_kernel.cpp`, `src/ancf/ancf_kernel.hpp` | linked by the full ANCF worker target in `src/ancf/CMakeLists.txt` | `6dde195a...`, `c1182ab9...`; matches the V2 copied-file hashes in `docs/VERSION_PROVENANCE.md` | authoritative capability source |
| full persistent ANCF worker | `src/ancf/ancf_worker_main.cpp` | CMake target `cfd_ancf_ancf_kernel_worker` | `83f2d643f855894c8e74aaa11d0c76684e74886ffa0ccfa044b9fb368367deb9` | authoritative candidate, but still contains parity logic |
| alternate lightweight worker | `src/ancf/worker_main.cpp` | CMake target `cfd_ancf_cpp_worker`; does not link `ancf_kernel.cpp` and uses consumer `cpp_ancf_worker` | current V2 source only | legacy/low-level protocol target, not the HH06 ANCF runtime worker |
| kernel request/response codec | `src/ancf/kernel_protocol.py` | imported by `src/coupling/hh06_structure_0000/structure_0000_participant.py` | `a2f002830d15c47880b6050bcde525e543f2bbadb916c340a06dfc4079a8a840` | current HH06 kernel wire source; carries SHM1/DMP1 extensions |
| frame/control codec | `src/ancf/protocol.py` | imported by the current HH06 participant and `kernel_protocol.py` | `0c66ca5947d9788d8fa9525e29c0f7ba55f65ea3073a9edac7223b5627b84abb` | current persistent-IPC framing/control source |
| HH06 Structure participant | `src/coupling/hh06_structure_0000/structure_0000_participant.py` | imports current ANCF codecs, coordinator, mapping and preCICE backend; launches a caller-supplied worker | `238883ca21cfcb2e8abb2dbac3878020d8ce083a172ceb2e0f276610ad405257` | current structural runtime entry source; provenance hash differs from the V2 copied-file hash recorded in `docs/VERSION_PROVENANCE.md` |
| generic coordinator/checkpoint owner | `src/coupling/arbitrary_n_live_orchestration_v1/coordinator.py` and `src/coupling/checkpoint/atomic_checkpoint.py` | used by the HH06 participant | coordinator `e612d5bfdffb54db07a7a325934cbb9d1cff65ec22b48639ad085b79cb0a90a3`; checkpoint source is current V2 tree | current orchestration/checkpoint source; not a worker binary identity mechanism |
| preCICE structure backend | `src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py` | used by the HH06 participant | `c2cdcef8c77135de71307ae5c9ad74c468c4c67a78f8442bb6329f94921f3aa6` | current isolated preCICE backend source; no runtime binary identity binding |
| alternate adapter contracts | `src/coupling/precice_adapter_v1/`, `src/coupling/precice_ancf_adapter_v1/` | contract/mock/reference layers; not imported by the HH06 participant entry path | current V2 sources; separate protocol namespaces | must not be confused with the HH06 production path |
| OpenFOAM motion source | `src/openfoam_adapter/ancfFileMotion.C`, `.H` | OpenFOAM 10 solid-body-motion library when separately built | C `e1984dd6...`; H `6716db8b...` | source snapshot only; production adapter remains unqualified and has no V2 runtime binary |

The full worker target is therefore the only current C++ target that combines
the ANCF kernel with the HH06-capable worker main. The alternate
`cfd_ancf_cpp_worker` target is not evidence that the full worker lineage has
been repaired.

## 2. Wire and identity ownership observed in current source

The current kernel request prefix in `src/ancf/kernel_protocol.py` carries:

```text
schema_version, protocol_version, sequence,
global_step, case_local_bridge_step, integer_tick,
time_s, dt_s, request_id, transaction_id
```

The request also carries run/case and producer/consumer identities, model and
state payloads, and a SHA-256 payload digest. The response validator checks
the echoed physical and transport identity, endpoint identities, return code,
finite-state audit, checkpoint identity, and response-state digest.

The C++ worker additionally keeps process-lifetime
`seen_request_ids`/`seen_transaction_ids` sets and advances `last_sequence`
only after a valid response. This is the correct ownership direction for
transport identities: physical checkpoint restore must not erase the worker's
session transport history.

## 3. Transport-ID repair status

### 3.1 Python-side rollback transport separation is present

The current `PersistentHH06KernelBackend` in
`src/coupling/hh06_structure_0000/structure_0000_participant.py` contains the
following repair semantics:

- session counters `_transport_sequence_counter`,
  `_transport_request_id_counter`, and
  `_transport_transaction_id_counter` are initialized independently;
- `snapshot()` stores physical/tentative state (`q`, `qdot`, `qddot`,
  committed count, and pending state), not transport counters;
- `restore()` restores physical state and committed-window state without
  restoring the transport counters;
- `advance()` allocates fresh transport identities for every request;
- `physical_window = committed_advance_count + 1`, so a retry can retain the
  physical window identity while using a fresh wire identity.

These semantics are visible at current source lines 324–451. The current
source therefore contains the Python/backend portion of the prior rollback
transport-ID repair.

The exact current wrapper hash is `238883ca...`, whereas the copied-file hash
recorded for this path in `docs/VERSION_PROVENANCE.md` is
`731b910c...`. This documentation/source hash discrepancy prevents claiming
complete source provenance for that wrapper without a separate reconciliation;
the semantic repair is nevertheless directly present in the checked-out file.

### 3.2 Isolated C++ transition repair is not integrated

The migrated transition evidence records a separate isolated patch:

| item | evidence identity |
|---|---|
| unpatched baseline `ancf_worker_main.cpp` | `83F2D643...` |
| isolated parity-removal source | `22072322...` |
| isolated qualified worker binary | `6CD66A7B...` |
| isolated deployment | `false` |
| tested requests | sequences `1..10` |
| physical windows | 2 windows, 5 requests each |
| rollback count | 8 |
| physical identity | window 1 `(1,1,200000,0.0002,0.0002)`; window 2 `(2,2,400000,0.0004,0.0002)` |

The current V2 `src/ancf/ancf_worker_main.cpp` hash is exactly the recorded
unpatched baseline hash `83F2D643...`, not the isolated patched hash. More
importantly, the current source still contains:

```text
src/ancf/ancf_worker_main.cpp:570
    expected_sequence % 2 == 0
src/ancf/ancf_worker_main.cpp:574
    expected_sequence % 2 == 1
```

The source first classifies sequence 2 using physical identity, but once
`lineage_mode == 2`, later retry/next-window acceptance still branches on
sequence parity. This violates the Phase 1A requirement that physical-window
identity, rather than wire-sequence parity, determine the state transition.

The isolated evidence is therefore `PASS_ISOLATED_ONLY`; it is not integrated
into the authoritative V2 worker source and must not be promoted.

## 4. Source → build → runtime traceability

The current source-to-build edge is explicit but the runtime edge is not
closed:

```text
src/ancf/ancf_kernel.cpp
src/ancf/ancf_worker_main.cpp
        │
        └── src/ancf/CMakeLists.txt
              target: cfd_ancf_ancf_kernel_worker
        │
        └── no build artifact or generated source/build manifest in V2
        │
        └── current HH06 participant accepts an arbitrary --worker path
```

Specific blockers:

1. `cases/hh06_single_slice/SOURCE_MANIFEST.md` records a historical binary
   hash `7B246C53...` and explicitly says ABI identity still needs confirmation.
   That binary is not in the V2 repository.
2. Migrated deployment evidence records another external binary,
   `69F045EB...`, from the prior runtime path. It is also not in V2 and is not
   the isolated parity-removal binary `6CD66A7B...`.
3. The current participant starts exactly the path supplied by `--worker`
   (`structure_0000_participant.py:331–356`) and does not verify the worker
   against `SOURCE_MANIFEST.md`, a generated build manifest, or a source
   commit/hash before starting it.
4. `cases/hh06_single_slice/launch.sh` defaults to a case-local
   `cfd_ancf_ancf_kernel_worker`, but the clean V2 case snapshot contains no
   such binary and no case-local `ancf_single_slice_participant.py` entry file.
   The current source entry is under `src/coupling/hh06_structure_0000/`.
5. `cases/hh06_single_slice/SOURCE_MANIFEST.md` says the canonical source
   remains in the former Windows project tree, while the clean-handoff
   documents state that `src/ancf` is the sole authoritative V2 source tree.
   The manifest statement is stale/conflicting and cannot be used as current
   authority.
6. `docs/ANCF_COUPLING_BASELINE_V1_MANIFEST.json` retains paths such as
   `src/coupling/cpp_worker_persistent_ipc_v1/...` that are absent from the
   current V2 tree. It is historical baseline metadata, not a current runtime
   manifest.

Consequently, the current checkout provides a reproducible source/build recipe
but does not provide a source-identifiable runtime binary or a runtime selector
that proves the binary was built from the current source. The full
source → build → runtime chain is **not proven**.

## 5. Lineage conclusion

1. **Authoritative current worker source:**
   `src/ancf/ancf_worker_main.cpp` linked with
   `src/ancf/ancf_kernel.cpp/.hpp` by target
   `cfd_ancf_ancf_kernel_worker`.
2. **Python protocol source:**
   `src/ancf/protocol.py` plus `src/ancf/kernel_protocol.py`, consumed by the
   current HH06 Structure participant.
3. **Structure participant source:**
   `src/coupling/hh06_structure_0000/structure_0000_participant.py`, with
   generic orchestration in `src/coupling/arbitrary_n_live_orchestration_v1/`.
4. **Python transport-ID rollback repair:** present in the current checked-out
   participant source, but its recorded copied-file hash needs provenance
   reconciliation.
5. **C++ worker physical/transport transition repair:** not integrated. The
   current authoritative source still contains sequence-parity logic, and its
   hash is the unpatched baseline identity.
6. **Source/runtime identity:** not closed. Historical external binaries and
   isolated patched binaries remain evidence only; none is a current V2 build
   artifact proven to be selected by the current participant.
7. **Current status:** retain `PASS_ISOLATED_ONLY`; do not promote to
   production-qualified and do not begin Phase 1B or any FSI qualification
   from this audit alone.

## Audit output and modification boundary

This report is the only file added by this Phase 1A audit. No production source,
case input, protocol, binary, OpenFOAM adapter build, or runtime artifact was
modified. The branch is intentionally left uncommitted for review.
