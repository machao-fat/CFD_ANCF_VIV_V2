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

The stage graph below describes the original source/evidence lineage on this
`main` branch. Its older HH06 single-slice result remains `DO_NOT_PASS`; the
V2606 results summarized next were produced in a separate clean project tree and
do not silently qualify or replace the code currently checked into `main`.

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

The latest qualification recorded for the source line on this branch is the
25-window HH06 `DO_NOT_PASS` caused by a late-window
`LATE_WINDOW_ALE_FLOW_TURBULENCE_RUNAWAY`. The implicit retry / trial-displacement
feedback issue remains open for that source line; see `docs/KNOWN_ISSUES.md`.

## Latest V2606 program and validation summary (2026-09-29)

The later V2606 campaign used a separate clean project tree
(`CFD_ANCF_VIV_V2_of2606`). Its offline scripts and curated evidence are on the
[`diagnostic/v2606-nm14-offline-postprocessing` branch](https://github.com/machao-fat/CFD_ANCF_VIV_V2/tree/diagnostic/v2606-nm14-offline-postprocessing).
This `main` update is a program/status summary only: it does not merge the whole
diagnostic evidence branch or claim that its participant source has been merged
into this repository's `src/` tree.

The V2606 coupled architecture exercised was five independent OpenFOAM Fluid
participants (four MPI ranks each) connected through official preCICE 3.4.1 to
one in-process C++ Structure participant, which advances one global ANCF state.
The production distributed-load mapping was
`PiecewiseLinearDistributed + NearestConstant`: each Fluid resultant was divided
by its 0.028 m local CFD span exactly once, reconstructed over the active
`[0, 5.94] m` region, and integrated consistently as `Q = integral H(s)^T f(s) ds`.
No slice-cell-width or tributary multiplier is used in that distributed path.

| Milestone | Recorded result | Limit |
|---|---|---|
| NM10.1R mapping closeout | Offline production-mapping closeout passed; original NM10.1 classification remains `V2606_NM10_1_INCONCLUSIVE` | M1 piecewise-constant trajectory remains optional diagnostic evidence |
| NM10.4 three-slice M2 | 100 accepted windows; distributed mapping coupled qualification passed | Does not establish spatial adequacy |
| NM11 four-rank requalification | Historical result remains `V2606_NM11_FOUR_RANK_MOVING_WALL_COUPLING_FAIL` | The R3 failure was before window 1 at preCICE handshake |
| NM12 five-slice / four-rank target | 100 accepted windows; `N5_TARGET_ARCHITECTURE_RUNTIME = QUALIFIED_SHORT100`; Q reconstruction max error `3.11e-15`; rollback `247/247` passed; all six participant exits were 0 | Short diagnostic horizon only; N5 spatial adequacy and long-duration behavior are not established |
| NM13 / NM14 postprocessing | Completed 10 s trajectory (25,000 accepted records); NM14.1 plotting/window corrections and NM14.2 modal-family/Cl correction passed | No 10-to-15 s continuation has been run |

Corrected late-window results from NM14.2:

| Metric | 5–10 s | 7.5–10 s |
|---|---:|---:|
| Cross-flow candidate `fy` | 1.8001 Hz | 1.6003 Hz |
| In-line candidate `fx` | 4.0003 Hz | 4.0006 Hz |
| Candidate `fx/fy` | 2.222 | 2.500 |
| Physical bending families `(ny, nx)` | `(2, 5)` | `(2, 5)` |
| Mean `Cd` | 1.74282 | 1.76985 |
| Active-region distributed local `Cl` RMS | 1.15515 | 1.15261 |

The active-region distributed `Cl` RMS is not a strict like-for-like comparison
with the thesis Case-1 whole-riser value 1.93; the mapped hydrodynamic load is
zero above 5.94 m. `N5_SPATIAL_ADEQUACY = NOT_ESTABLISHED`, and
`10_TO_15_EXTENSION = RECOMMENDED` (not started). These are short-time numerical
and postprocessing findings, not a claim of steady VIV validation or spatial
convergence.

The [NM-series archive index](https://github.com/machao-fat/CFD_ANCF_VIV_V2/blob/636dbd38b885cbf8a5a0ccf1976c0fac95e5a5b1/evidence/V2606_NM_SERIES_OFFLINE_ARCHIVE.md)
lists the curated NM2–NM14 evidence and exclusions. The [full NM14.2 report](https://github.com/machao-fat/CFD_ANCF_VIV_V2/blob/636dbd38b885cbf8a5a0ccf1976c0fac95e5a5b1/evidence/v2606_nm14_2_modal_cl_correction/comparison/final_report.md)
contains definitions, source references, and the full limitations.

## Architecture

The diagram below describes the source architecture currently checked into this
`main` branch. The separate V2606 in-process Structure architecture summarized
above is documented in its linked evidence package; it has not been merged into
this source tree by the README-only update.

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
