# Phase 1E.6 — Force Read-Time Contract Repair

## Result

**Classification: `PASS_OFFLINE_FORCE_READ_TIME_REPAIR`.** The retry Force
read now selects the endpoint sample of the current implicit window; an
accepted exchange selects relative time zero at the window boundary. Offline
qualification passed. No real preCICE, OpenFOAM, HH06, or moving-structure run
was started, and no Phase 1E result was overwritten or reclassified.

## Evidence preservation

The accepted historical failure remains at
`evidence/phase1e_bounded_2window/run-20260923T065444Z-02d9a1f1/`.
Its `structure_trace.jsonl` SHA256 remains
`2d96f0d2f6fb0cc73290203a379b14336bc25b24951d13598f1d983208f96b74`.
Phase 1E.5's passing 3.4.1 scratch evidence remains at
`evidence/phase1e5_precice_force_read_timing/run-20260923T074627Z-pid112440/`;
its `result.json` SHA256 is
`b8095d5765bce468fd1b1b94101eb01b6ddeae2248e1ca771b9d886f1110297e`.
Neither evidence set was deleted or modified.

## Exact changes

Production/test files changed:

1. `src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py`
2. `src/coupling/hh06_structure_0000/structure_0000_participant.py`
3. `tests/coupling/test_implicit_iteration_trace.py`

New report/evidence:

- `docs/PHASE1E6_FORCE_READ_TIME_REPAIR_REPORT.md`
- `evidence/phase1e6_offline_force_read_time/implicit_fixed_point_trace.jsonl`
- `evidence/phase1e6_offline_force_read_time/iteration_cap_trace.jsonl`
- `evidence/phase1e6_offline_force_read_time/physical_f0_seed_trace.jsonl`
- `evidence/phase1e6_offline_force_read_time/worker_transport_qualification.json`
- Final verified rerun artifacts are under `evidence/phase1e6_offline_force_read_time/final_verified/`,
  including the explicit two-window `force_window_transition_trace.jsonl`.

The pre-existing untracked Phase 1E and Phase 1E.5 report/evidence remain
unmodified. No worker, coordinator/checkpoint implementation, XML, OpenFOAM
adapter, force scaling, timestep, mesh, turbulence, or damping files changed.

## Before/after lifecycle

Before, `PreciceStructureFleetBackend.read_force()` always called
`read_data(..., 0.0)`. The Structure participant read Force after every
`advance()` and only then queried `requires_reading_checkpoint()`. On retries,
this returned the unchanged window-start Force, so the next ANCF solve repeated
the same Force input despite preCICE producing a new endpoint iterate.

Now `read_force(slice_id, *, relative_read_time_s)` requires the caller to
choose the sample time. It validates that the offset is finite and
nonnegative, then passes it directly to pyprecice; it contains no retry-policy
default.

The participant lifecycle is now:

```text
after initialize:
    read Force at 0.0                 # frozen physical release F0
    validate F0

each coupling attempt:
    solve ANCF with current Force
    write exact D_trial
    advance(dt)
    retry = requires_reading_checkpoint()

    if retry:
        read Force at dt              # current window endpoint iterate
        rollback physical ANCF state
        retain returned Force and iteration history
    else:
        read Force at 0.0              # accepted boundary / next-window start
        commit accepted trial
```

The worker transport IDs, physical checkpoint/rollback calls, Force unit
conversion, and Strategy C write-before-advance ordering are unchanged.

## Trace changes

Every attempt retains distinct input and returned Force records. New trace
fields record:

- consumed Force source time, source kind, raw vector, read offset, and the
  consuming window/iteration;
- returned Force source time, source kind, raw vector, actual read offset, and
  the producing window/iteration;
- explicit `force_read_time_s` and `force_read_offset_s` values (`dt_s` on
  retry, `0.0` on acceptance).

The existing `force_input_raw_N` and `returned_force_raw_N` remain separate.
No Force provenance is inferred from its timestamp alone. Attempt events now
show `advance`, checkpoint decision, selected Force read, and then rollback or
commit.

## Offline regression results

Command:

```text
PHASE1D_EVIDENCE_DIR=evidence/phase1e6_offline_force_read_time/final_verified /usr/bin/python3.10 -m unittest -v tests.coupling.test_implicit_iteration_trace tests.coupling.test_worker_transport_regression
```

Result: **10 tests passed**.

- Strategy C deterministic fixed-point convergence: **PASS**.
- Physical checkpoint lifecycle / exact q, qdot, qddot restore across retries:
  **PASS**.
- Explicit backend API forwards the selected offset and rejects an omitted
  offset: **PASS**.
- Retry endpoint Force sequence (`F0`, then preceding-advance `F1`, `F2`, …):
  **PASS**.
- Accepted branch reads zero and does not attempt `dt` after window completion:
  **PASS**.
- Two-window fake passes window 1's accepted Force into window 2; it does not
  reset to the original seed; a dedicated `F0 -> F1 -> accept`, then
  window-2-starts-at-`F1` test: **PASS**.
- Initial physical F0 x/y values and frozen provenance: **PASS**; initial read
  remains at `0.0` after initialize.
- One-time force conversion and `D_written == D_trial` across attempts:
  **PASS**.
- Current-source worker two-window/five-attempt transport regression, physical
  rollback, and duplicate request/transaction guards: **PASS**.

Worker qualification details and attempt traces are preserved under
`evidence/phase1e6_offline_force_read_time/final_verified/`. These are offline tests only and
do not qualify real Fluid/Structure runtime behavior.

## Source identities and repository state

| File | SHA256 before | SHA256 after |
|---|---|---|
| `precice_backend.py` | `c2cdcef8c77135de71307ae5c9ad74c468c4c67a78f8442bb6329f94921f3aa6` | `e5f37644e1b31391aed48c47473e336733e0c492191b166ed6354b2a3eb07cf6` |
| `structure_0000_participant.py` | `34baa21a7f286ce64af7afa23f4d59f426706cdfd32f26ad98ef56b12c62c6ed` | `da578e517948c8facfdd3cfe22c01fb0df29c19a6fa48a11ecf646705c1f8cca` |
| `test_implicit_iteration_trace.py` | not separately recorded before this phase | `e74d9c9641ccb5062e485bafa2546c1ddd7ba0513ba12fbd9a4e0f1825c44fa6` |

`git diff --check` passes. The tracked diff is limited to the three files above.
Current branch is `repair/worker-lineage-implicit-contract-v1`; HEAD remains
`02d9a1f180082e83bcc9f7acdcb090502262b2d1`. Nothing was committed. The prior
Phase 1E failure classification remains historically valid, and no real
qualification rerun is authorized by this offline result.
