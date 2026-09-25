# CFD_ANCF_VIV_V2

Clean Linux/WSL handoff for the CFD--preCICE--ANCF flexible-riser VIV project.

## Project goal

Build a traceable two-dimensional strip-CFD / preCICE / ANCF solver for vortex-induced
vibration of a slender flexible riser, then extend the validated single-slice loop to
distributed multi-slice loading and HH06/Chaplin benchmark comparisons.

The authoritative working directory is this Linux tree:

```text
/home/machao/projects/CFD_ANCF_VIV_V2
```

The former Windows repository `machao-fat/CFD_ANCF_VIV` is legacy forensic history.
Do not merge, rebase, force-push, or infer authority from its newest filename.

## Current state

The repair branch has completed the single-slice implicit-coupling and RBF/ALE
qualification work through Phase 1K.22. The results have different qualification
levels:

| Phase | Status | Scope of the result |
|---|---|---|
| Phase 1E-R | `REAL_IMPLICIT_FORCE_ITERATION_CONTRACT_PASS` | Two-window real Structure/Fluid lifecycle with the qualified historical adapter |
| Phase 1F | `PASS_REAL_5WINDOW_STRATEGY_C` | Five-window real lifecycle; the windows remain bounded observations |
| Phase 1I | `FAIL_ALE_OR_FLUID_RUNTIME` | Old mesh plus Laplacian ALE; the historical late-window failure occurred after 20 accepted windows |
| Phase 1K.11 | `REVIEW_REQUIRED` | New 6D O-grid plus RBF completed 25 windows, but the displacement-to-mesh path was not closed |
| Phase 1K.20 | `PASS_EXPERIMENTAL_NONZERO_POINT_CHECKPOINT_ONE_RETRY` | Experimental adapter restored a nonzero point-displacement checkpoint for one retry |
| Phase 1K.21 | `PASS_EXPERIMENTAL_TWO_WINDOW_LIFECYCLE` | Experimental adapter completed two windows with nonzero rollback checks; both reached the iteration cap |
| Phase 1K.22 | `PASS_EXPERIMENTAL_FIVE_WINDOW_LIFECYCLE` | Experimental adapter completed five windows; every window reached the 20-iteration cap |

K20--K22 use the separately identified experimental adapter
`libpreciceAdapterPhase1K20.so` (SHA-256
`225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165`). Their
results cover field restoration and the tested retry/read handoff lifecycle.
They do not qualify the historically installed adapter for replacement or
establish converged or long-run FSI behavior. The K11 RBF displacement path and
the historical adapter source-to-binary provenance remain open issues.

The repair branch is currently not ready to merge into `main`. The merge gate is
recorded in `docs/ROADMAP.md`: production adapter adoption, the K11
displacement-to-mesh path, and convergence beyond iteration-cap acceptance need
separate review.

## Architecture

```text
OpenFOAM pimpleFoam
   |  integrated wall force
   v
preCICE Fluid_0000 <----> Structure_0000
                             |
                             v
                    ANCF coordinator / persistent worker
                             |
                             v
                    ANCF q, qdot, qddot and SHM1 model
```

The structure participant receives one resultant force per coupling slice and returns
absolute section displacement. CFD wall faces are never mapped one-to-one to ANCF
nodes.

## Authoritative source lineages

- ANCF/SHM1 capability baseline: `feature/ancf-spanwise-hydro-matrix-v1` at
  `355640e11925b9feddd1a52bb3d93596e5ee8251`.
- HH06 coupling development history: `validation/g1-terminal-diagnostic-serialization-repair-v1`
  at `ea7909748da5d6be399abedaa405a0df549360d5`.

These are deliberately separated. HH06 orchestration code is not automatically
production-qualified merely because it is present in the development lineage.

## Read first

1. `docs/PROJECT_CONTEXT.md`
2. `docs/PHYSICS_CONTRACT.md`
3. `docs/COUPLING_CONTRACT.md`
4. `docs/VERSION_PROVENANCE.md`
5. `docs/VALIDATION_LEDGER.md`
6. `docs/KNOWN_ISSUES.md`
7. `docs/ROADMAP.md`
8. `docs/NEW_CODEX_START_HERE.md`

## Repository layout

```text
src/ancf/                         authoritative C++ ANCF + SHM1 worker source
src/ancf_matlab/                  MATLAB reference implementation
src/coupling/                     preCICE, mapping and coordinator layers
src/openfoam_adapter/             OpenFOAM motion source snapshot
cases/ancf_validation/            small offline validation references
cases/cfd_fixed_cylinder_re7622/  clean fixed-cylinder parent snapshot
cases/hh06_single_slice/          30 s restart and HH06 single-slice contracts
tests/                            offline/unit/regression tests only
evidence/                         copied qualification evidence, no runtime outputs
scripts/                          offline analysis and validation helpers
docs/                             project contracts and handoff documents
archive/                          legacy-history policy
```

## Offline checks

These checks do not start OpenFOAM, preCICE, or ANCF physical time integration:

```bash
python3 -m compileall -q src tests scripts
cmake -S . -B build
cmake --build build -j2
```

Run only the explicitly named offline tests. A test result is permanent evidence only
when it is linked to a report, source commit, and machine-readable result in the ledger.

## Status vocabulary

`QUALIFIED` means validated by the cited evidence; `QUALIFIED_ISOLATED` means a
diagnostic/isolated path only; `KNOWN_DEFECT` means a reproducible issue remains;
`UNQUALIFIED` means no production claim; `HISTORICAL_ONLY` means retained for forensic
context.
