# V2 distributed-load reference contract

Authoritative source is the annotated tag `ancf-coupling-baseline-v2` in
`machao-fat/CFD_ANCF_VIV`, peeled commit
`8443209c4db39572f5099bec5d66a093eec7cdc3`.

Reviewed paths:

- `src/coupling/cpp_worker_persistent_ipc_v1/ancf_kernel.cpp`
- `src/coupling/cpp_worker_persistent_ipc_v1/ancf_kernel.hpp`
- `src/coupling/arbitrary_n_live_orchestration_v1/coordinator.py` (reference
  only; not ported)

The historical mathematical contract is `PiecewiseLinearDistributed` with
`NearestConstant` endpoints. Fluid raw force is converted once from N to
sectional line force N/m by division by the local CFD span. The reconstructed
line field is constant from the active-region start to the first sample,
linear between ordered samples, and constant from the last sample to the
active-region end; it is zero outside the active region. The consistent load is
`Q = integral H(s)^T f(s) ds`, split at element/sample boundaries and evaluated
with the ANCF shape function machinery.

The current implementation calls the frozen public `external_force(Model,
SpanwiseLoadInput)` API for H(s) and integration. No Python coordinator,
worker, IPC/wire state machine, carried force, force-read offset, old rollback,
parallel-explicit topology generator, or OF10/RBF/G2 hack is restored.

Reference URL:
<https://github.com/machao-fat/CFD_ANCF_VIV/tree/8443209c4db39572f5099bec5d66a093eec7cdc3/src/coupling/cpp_worker_persistent_ipc_v1>
