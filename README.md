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

## Current stage

```text
ANCF numerical baseline
  -> fixed-cylinder CFD baseline
  -> force/displacement mapping
  -> HH06 single-slice coupling repair
  -> single-slice qualification (currently blocked)
  -> 3-slice smoke
  -> slice-number sensitivity
  -> HH06 quantitative validation
```

The current project is not authorized to start a new production FSI run. The latest
25-window HH06 qualification is `DO_NOT_PASS` because a late-window
`LATE_WINDOW_ALE_FLOW_TURBULENCE_RUNAWAY` was observed. The main remaining hypothesis
is an unverified implicit retry / trial-displacement feedback defect; see
`docs/KNOWN_ISSUES.md`.

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
