# Phase 1K.17 — Experimental adapter field ownership repair

**Classification: `EXPERIMENTAL_ADAPTER_REPAIR_PASS` for the single-window displacement-path experiment only.** Nonzero Structure trial displacement reached the Fluid preCICE read, adapter-owned `cellDisplacement`, RBF-owned `pointDisplacement`, RBF moving controls, and actual mesh points. This is **not** a production adapter replacement, a converged first-window result, or an FSI stability qualification. No 5- or 25-window run was performed.

## Identity and scope

- V2 branch: `repair/worker-lineage-implicit-contract-v1`; HEAD `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`. The existing qualified adapter was untouched and remained SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`.
- Experimental source: independent copy of official `precice/openfoam-adapter` `OpenFOAM10` checkout at `d53753b1c927b2413b02299c9da15725b3e772f0`, carrying the separate Phase 1K.16B experimental read-time patch and the Phase 1K.17 field/trace patch. This source is **not claimed to be the source of the qualified adapter binary**. Tracked-source SHA256 manifest hash (lexical `git ls-files` order, each line a `sha256sum` of the repository-relative file under the experimental tree): `cc433e5af284cb34a31d81b0e82e66f6f6d77ba720fb61e338196d1a8f172c89`. Complete experimental `git diff --binary` SHA256: `3a88aabd45f408ef3c41b0c5a59f3199c284d54e251ada04e300df6a71f1cba7`.
- Source changes relative to the selected upstream commit: `Adapter.C`, `FSI/Displacement.C`, `Interface.C`, `Make/files` only. The Phase 1K.17 part creates/registers and validates `cellDisplacement` before reader construction completes, retains face-to-point interpolation, logs the displacement/rollback chain with scientific precision, and names the separate library. It does not change OpenFOAM equations, ANCF, RBF settings, mesh, IQN, or `dt`.
- Build: `source /opt/openfoam10/etc/bashrc`; `ADAPTER_TARGET_DIR=/home/machao/projects/CFD_ANCF_VIV_V2/evidence/phase1k17_adapter/lib ADAPTER_PKG_CONFIG_CFLAGS="$(pkg-config --cflags libprecice)" ADAPTER_PKG_CONFIG_LIBS="$(pkg-config --libs libprecice)" wmake libso`. Foundation OpenFOAM `10-c4cf895ad8fa`, `linux64GccDPInt32Opt`, GCC 11.4.0, preCICE 3.4.1. The sourced-environment `ldd -r` found no missing libraries or unresolved symbols.
- Experimental binary: `evidence/phase1k17_adapter/lib/libpreciceAdapterPhase1K17.so`, SHA256 `1bc5cf6a1ea481082b01b903d317313be01212413c8bf2718481fa43c485c495`, ELF Build ID `ef890a9afffa253f4aceb051c4c3fed89e64cffe`. The single-window process maps confirmed that exact path was loaded. The separately named RBF diagnostic library was `libRBFMeshMotionSolverPhase1K13Diag.so`, SHA256 `4a739721bfaa4734151e79bca285545d6934b2f5a9450080a5e833542a4c84ee`; it is not the qualified RBF binary.
- Worker source/binary SHA256 remained `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` / `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`.

## Field ownership and corrected startup order

The Phase 1K.16B adapter aborted while constructing `FSI::Displacement`, *before* preCICE initialization: it looked up a missing `volVectorField cellDisplacement`. The 30.0 s restart contains `pointDisplacement` but not this adapter staging field. The new experimental constructor now creates a registered zero-length-dimension `volVectorField` when missing, with 200-face `cylinder` patch and mesh-compatible `empty`/`symmetryPlane` constraints. An existing field is checked for dimensions and patch sizes. The field is registered before `setupCheckpointing()` discovers fields. The RBF solver continues to consume only the registered `pointDisplacement` cylinder boundary, not the cell staging field. At 30.0 s the new field is zero; neither frozen restart file nor production case was altered.

The full attempt order remains `advance → requiresReadingCheckpoint → physical rollback (if retry) → read Displacement(dt)`; on an accepted boundary with continuing coupling it selects `read Displacement(0)`. The one-window terminal acceptance does not exercise a subsequent accepted-boundary read; that branch is supported here by the synthetic preCICE test, not by this real run.

## Offline gates

1. Synthetic two-participant preCICE 3.4.1 replay: **PASS**, six attempts over two windows. Retry endpoint `dt=0.1` yielded new displacement; accepted-boundary offset `0` yielded next-window start. Evidence: `evidence/phase1k17_adapter/offline_precice/result.json`. This reuses the Phase 1K.16B probe and does not execute the OpenFOAM adapter.
2. Compiled OpenFOAM-10 field test against the *experimental library* on a scratch copy of the mapped 6D mesh: **PASS**. It verified missing-field creation, registry lookup, `dimLength`, 46,826 zero-initialized cell values, 200 cylinder face values, and 400 point-boundary values. A uniform nonzero vector and a nonuniform per-face pattern both transferred through the actual `FSI::Displacement::read()` and `primitivePatchInterpolation`. Source: `evidence/phase1k17_adapter/field_contract_test/fieldContractTest.C`; observed `PHASE1K17_FIELD_TEST_PASS faces=200 points=400`.
3. Scratch Structure `--audit-only`: **PASS**, including new-mesh F0 provenance. `git diff --check` for the experimental source and sourced `ldd -r` passed.

## Exactly one real diagnostic window

Evidence: `evidence/phase1k17_adapter/run-20260924T120749Z-c2245ff/`. The scratch case starts from the Phase 1K.10 *unadvanced mapped 30.0 s* state. Runner verified hashes for `30/{U,p,k,omega,nut,pointDisplacement,uniform/time}` and the principal mesh files against that source. It verified the qualified worker, unchanged qualified adapter, experimental adapter and diagnostic RBF hashes before launch. Scratch XML SHA256 `a13320726bb45f8f8f2d89355f0ae84db4493e3aac2d454db1757d25ca959fac`; it alone sets `max-time-windows=1`, retains `dt=0.0002`, `min-iterations=2`, `max-iterations=20`, and the frozen IQN-ILS profile. The production Structure CLI retains its existing `--max-windows 25` contract, but preCICE XML is the active one-window termination bound; logs show only window 1. No second attempt was launched.

The first nonzero retry gives the decisive correlated chain:

| Event | Observed value |
| --- | ---: |
| Structure attempt 1 `D_trial = D_written` | `(1.06338321646e-7, 9.53077719001e-8)` m |
| Fluid `readData(Displacement, dt)` after rollback | 400 scalars; max component `2.12676643292e-8` m |
| `cellDisplacement.cylinder` | 200 faces; max norm `2.85596989025e-8` m |
| `pointDisplacement.cylinder` | 400 points; max norm `2.85596989025e-8` m |
| RBF call 3 moving controls | 200 moving controls, nonzero representative `(2.126766433e-8, 1.906155438e-8, 0)` m; 20 controls selected after coarsening |
| RBF call 3 interpolated/actual mesh points | max displacement from `points0` `2.866340695e-8` m; cylinder mesh max also nonzero |

The smaller Fluid displacement is consistent with preCICE's frozen 0.2 initial IQN relaxation, so the Structure trial and Fluid *received* values must not be naively equated. The actual nonzero path is established by same-attempt read/field/RBF/mesh records, not by accepted-time saved mesh files.

Checkpoint discovery logged both staging and point fields. Before the first *nonzero* retry rollback, `cell_max=2.85596989025e-8`, `point_max=2.85596989025e-8`, and mesh displacement relative to checkpoint `2.86634069506e-8` m. Immediately after rollback all three were zero; the next endpoint read then populated new nonzero values. `nOldTimes=0` for both displacement fields in this observed window, so no separately instantiated old-time displacement snapshot needed restoration in this run. This does not establish old-time behavior for every possible OpenFOAM case.

The Structure trace contains exactly 20 attempts, sequences 1–20, 19 rollbacks, one committed window, and `D_written == D_trial` for every attempt. Force input for each retry equals the prior returned Force. Window 1 was **`ACCEPTED_AT_ITERATION_LIMIT`**, not converged. Fluid and Structure both exited 0; no worker or participant remained. The experimental path therefore passes the displacement-delivery and rollback experiment, **not** any convergence-efficiency or long-run-stability claim.

## Boundaries and remaining work

- The source-to-binary lineage of the historical qualified adapter remains unresolved. This experimental binary is isolated by filename, SHA and Build ID; no production replacement was made.
- The test uses the diagnostic RBF library and a scratch XML/controlDict/contract only. The authoritative HH06 case and frozen mapped restart remain unchanged.
- No 5-/25-window run or parameter tuning is authorized by this result. Before production adoption, review the experimental adapter's broader field ownership, accepted-boundary handoff over more than one window, and convergence/mesh response; the one-window cap acceptance is a separate numerical issue.

**Phase stop:** one diagnostic physical window only. No production source/configuration changes, commit, or follow-on FSI run.
