# NM4 legacy-code boundary audit

The old project is `${D_DRIVE_ROOT}/CFD_Work/projects/CFD_ANCF_VIV_V2`, Git HEAD
`e30c9583895746fc266b5d8ef1f0e4749cf882e1`. It is read-only for NM4.

## KEEP — mathematical/numerical core, byte-identical snapshot

- `src/ancf/ancf_kernel.cpp` SHA256
  `6dde195a8ea27f253a21d4a859bf41a620697963ab0a834bb9d982b51863ac06`
  and `ancf_kernel.hpp` SHA256
  `c1182ab921d5517c2a5282f8b5fe51c3ab298bec8b6015bfdcdbca733c17e22c`.
  Copied without modification into this evidence tree. The core supplies the
  32-element, 33-node, 198-DOF ANCF model, mass/added-mass assembly,
  nonlinear internal force and tangent, Newmark advance, and `mapping_H3`
  / `external_force = H^T F`. The new participant links this source directly,
  rather than spawning the historical worker or reimplementing the kernel.
- P1 `ancf_static.raw`, `CASE REF_NE32` / `Q 198` record, SHA256
  `b298979244f67e23d02a63566e718ccb1f8897570c12b0aab98f7cbbf6577091`.
  It is copied intact for q0. Initial qdot and qddot are zero. No new static
  equilibrium replaces P1. The physical top-tension input is 1175 N; the
  historical 1188.28 N quantity is not substituted for that input.
- `src/ancf/ancf_kernel.cpp::external_force` calls the validated shape-function
  virtual-work map; the coupling point is `s=2.97 m`. Its eight nonzero
  generalized-force DOFs are audited per attempt. The scale is applied once
  before calling this mapping: `(F_raw/0.028)*1.98`.

## REWRITE — coupling wrapper

- `src/coupling/hh06_structure_0000/structure_0000_participant.py` is replaced
  by `source/clean_structure_participant/main.cpp`. The new file uses the
  installed preCICE 3.4.1 `Participant` lifecycle directly: single mesh
  vertex, initial zero displacement if requested, initialize, checkpoint,
  read Force, ANCF trial, absolute Displacement write, advance, restore or
  accept, finalize. The participant owns ANCF state in-process and stores
  only physical/numerical state for rollback. Diagnostic ordinal is monotonic.
- Its numerical model construction follows the P1 explicit-section/SHM1
  values documented in `cases/hh06_single_slice/structure_contract.json`,
  but uses the NM4 production dt `4e-4 s`. The old wrapper's preCICE/worker
  orchestration is not copied.

## DO NOT PORT — lifecycle and protocol machinery

- `src/ancf/ancf_worker_main.cpp`, `src/ancf/kernel_protocol.py`,
  `src/ancf/worker_client.py`: worker wire identity, sequence/transaction,
  bridge/global-step fields, and rollback state machine.
- Old participant fields and branches around `returned_force_read_offset_s`,
  `committed_motion_m`, `rollback_request`, carried returned Force, and
  trial-motion overwrite (old file around lines 732–895). These are replaced
  by the official `requiresWritingCheckpoint` and
  `requiresReadingCheckpoint` lifecycle.
- Any OF10/G2/RBF/meshPhi-zeroing/adaptor-patch path. The official adapter
  binary is used unchanged.

This is a capability/provenance audit, not a new MATLAB/C++ mathematical
equivalence qualification. The previously validated core is frozen bytewise.
