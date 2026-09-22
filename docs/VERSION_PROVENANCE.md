# Version and source provenance

The new repository intentionally has one ANCF source tree (`src/ancf`). Historical
candidate workers are not copied as production alternatives.

| component | new path | original lineage | original commit | status |
|---|---|---|---|---|
| ANCF kernel | `src/ancf/ancf_kernel.cpp/.hpp` | `machao-fat/CFD_ANCF_VIV`, `feature/ancf-spanwise-hydro-matrix-v1` | `355640e11925b9feddd1a52bb3d93596e5ee8251` | QUALIFIED capability baseline |
| persistent worker | `src/ancf/ancf_worker_main.cpp` | same as above, with Phase 1A.5 repair | `355640e11925b9feddd1a52bb3d93596e5ee8251` | source repair committed; offline lineage qualification PASS; HH06 runtime deployment not qualified |
| Python wire protocol | `src/ancf/kernel_protocol.py`, `protocol.py` | same as above | `355640e11925b9feddd1a52bb3d93596e5ee8251` | SHM1/DMP1 capability baseline |
| checkpoint | `src/coupling/checkpoint/atomic_checkpoint.py` | same as above | `355640e11925b9feddd1a52bb3d93596e5ee8251` | QUALIFIED offline semantics |
| SHM1 | `src/ancf/kernel_protocol.py` + C++ kernel | same as above | `355640e11925b9feddd1a52bb3d93596e5ee8251` | QUALIFIED protocol capability |
| distributed mapping | `src/coupling/arbitrary_n_live_orchestration_v1`, `multi_slice_mapping` | HH06 development lineage | `ea7909748da5d6be399abedaa405a0df549360d5` | QUALIFIED_ISOLATED / not full production FSI |
| Structure_0000 wrapper | `src/coupling/hh06_structure_0000` | HH06 development lineage | `ea7909748da5d6be399abedaa405a0df549360d5` | QUALIFIED_ISOLATED |
| preCICE backend | `src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py` | HH06 development lineage | `ea7909748da5d6be399abedaa405a0df549360d5` | QUALIFIED_ISOLATED |
| OpenFOAM motion source | `src/openfoam_adapter/ancfFileMotion` | HH06 development lineage | `ea7909748da5d6be399abedaa405a0df549360d5` | UNQUALIFIED production adapter |
| HH06 case | `cases/hh06_single_slice` | `/home/machao/OpenFOAM/coupling/singal_slice/slice0000` | runtime snapshot, not Git source | KNOWN_DEFECT / frozen config |

## Known source hashes

The case `SOURCE_MANIFEST.md` recorded these hashes for the original ANCF source snapshot:

```text
ancf_kernel.cpp       6DDE195A8EA27F253A21D4A859BF41A620697963AB0A834BB9D982B51863AC06
ancf_kernel.hpp       C1182AB921D5517C2A5282F8B5FE51C3AB298BEC8B6015BFDCDBCA733C17E22C
ancf_worker_main.cpp  83F2D643F855894C8E74AAA11D0C76684E74886FFA0CCFA044B9FB368367DEB9
```

These are handoff-era source snapshot hashes, not the current repaired worker
hash. The qualified historical worker binary hash is retained in evidence only
and is not copied into this repository. Source and binary lineage must not be
inferred from a filename.

## Phase 1A.5 current worker lineage

```text
repair commit = 0383920
commit message = fix: replace worker sequence parity with physical identity checks
source = src/ancf/ancf_worker_main.cpp
source SHA-256 = c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e
build target = cfd_ancf_ancf_kernel_worker
CMake = 3.22.1, Release, Unix Makefiles
compiler = GNU C++ 11.4.0, gnu++17
offline worker binary SHA-256 = 3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596
offline lineage qualification = PASS
HH06 runtime deployment/qualification = NOT DONE
```

The source repair removes transport-sequence parity from physical window
classification. Same-window retry and next-window continuity are classified
from `(global_step, bridge_step, integer_tick, time_s, dt_s)`. See
`PHASE1A5_PARITY_REPAIR_QUALIFICATION_REPORT.md` for the bounded offline
qualification and its limitations.

## V2 copied-file hashes

These hashes were computed after extraction into the WSL V2 tree:

```text
src/ancf/ancf_kernel.cpp                                      6dde195a8ea27f253a21d4a859bf41a620697963ab0a834bb9d982b51863ac06
src/ancf/ancf_kernel.hpp                                      c1182ab921d5517c2a5282f8b5fe51c3ab298bec8b6015bfdcdbca733c17e22c
src/ancf/ancf_worker_main.cpp                                 83f2d643f855894c8e74aaa11d0c76684e74886ffa0ccfa044b9fb368367deb9
src/ancf/kernel_protocol.py                                   a2f002830d15c47880b6050bcde525e543f2bbadb916c340a06dfc4079a8a840
src/coupling/hh06_structure_0000/structure_0000_participant.py 731b910cadcf760172a76208ee8c55916a29384fad15f7af1ce7c95470ab6ed2
src/coupling/arbitrary_n_live_orchestration_v1/coordinator.py e612d5bfdffb54db07a7a325934cbb9d1cff65ec22b48639ad085b79cb0a90a3
src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py c2cdcef8c77135de71307ae5c9ad74c468c4c67a78f8442bb6329f94921f3aa6
cases/hh06_single_slice/contract.json                        040d81a692658d3c075e80d37873297e4d1d5fcc5b3a68eca48dfa6200c6957d
cases/hh06_single_slice/precice-config.xml                    2c67b8628e428e3d53faa935574bba644a433749109120de34e0026c5ec95c76
cases/hh06_single_slice/30/U                                a71a708e7bc12280ce60d0ad141c826ccd39e2100a0e98322cd0a7f53de3668a
```
