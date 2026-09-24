# Phase 1K.7 — RBF Configuration Semantic Recovery

## Result

**Classification: `RBF_SOURCE_STILL_REQUIRED`.**

The source-provenance search found no RBF source, matching `wmake` recipe, or
build record for the candidate library. Read-only ELF analysis confirms the
runtime selection name and recovers a partial dictionary grammar, including
parameter types, a patch-name default, and positivity checks. It does not
recover the RBF kernel, control-point construction, far-field constraints, or
the units/meaning of `supportRadius`. A safe, scientifically interpretable
configuration is therefore not ready.

## Scope and identity

The search covered the local OpenFOAM user tree, OpenFOAM installation source,
tutorials and templates, and the current V2 source/case directories. The user
tree was searched read-only because this phase explicitly asks for source/build
provenance. No historical implementation was copied or adopted. The old
development repository was not searched.

| Item | Result |
|---|---|
| Git branch / HEAD | `repair/worker-lineage-implicit-contract-v1` / `c2245ff396ff42dfa5e80fee6555a9ede93e3b04` |
| OpenFOAM | `OpenFOAM-10`, `WM_PROJECT_DIR=/opt/openfoam10` |
| OpenFOAM user directory | `WM_PROJECT_USER_DIR=/home/machao/OpenFOAM/machao-10` |
| Candidate library | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libRBFMotionSolver.so` |
| Library SHA256 | `e783ae0aa3765dee2a7f11f24d3a041b9d9b028795c4c703e48aca3a508cf188` |
| ELF Build ID | `d12bef3602874632c74204341110e7f8008e5dc7` |
| Current HH06 `dynamicMeshDict` SHA256 | `56158d50b619174c67a343d2660c87c4c0c5e1370e2fde44a4a4c6f07c5ccdc5` |

## Provenance search

Searched locations and results:

| Location | Search/result |
|---|---|
| `/home/machao/OpenFOAM/` user OpenFOAM trees, build directories, and library paths | No exact RBF identifiers found in source/config/build text; no matching `Make/files` or `Make/options`; the only RBF-named file is the candidate `.so` |
| `/opt/openfoam10/src/`, `/opt/openfoam10/tutorials/`, `/opt/openfoam10/etc/` | Generic OpenFOAM motion-solver loader/source and non-RBF examples found; no RBF implementation or RBF-specific dictionary example |
| Current V2 `src/` and `cases/` | No RBF implementation or RBF configuration |
| RBF-named source scan in searched OpenFOAM trees | No `*rbf*.C`, `*rbf*.H`, `*rbf*.cpp`, or `*rbf*.hpp` |
| Binary/build relationship | The `.so` embeds `rbfMotionSolver.C` and OpenFOAM `lnInclude` paths, but there is no corresponding source file, source hash, source revision, `Make` recipe, or build manifest to bind those strings to authoritative source |

The binary is ELF64 x86-64 and records GCC 11.4.0 in `.comment`. Its exported
demangled symbols include `Foam::rbfMotionSolver`, `buildControls`,
`updateDisplacement`, `solve`, and `curPoints`. These establish class/symbol
identity only; method names do not establish their numerical behavior.

## Recovered dictionary grammar

OpenFOAM 10 source verifies the configuration layers:

- `fvMeshMover::New` selects `dynamicMeshDict/mover/type` and loads the outer
  `mover/libs` (`/opt/openfoam10/src/finiteVolume/fvMesh/fvMeshMovers/fvMeshMover/fvMeshMoverNew.C:50-63`).
- The outer `Foam::fvMeshMovers::motionSolver` calls
  `Foam::motionSolver::New` with the `mover` dictionary
  (`/opt/openfoam10/src/fvMeshMovers/motionSolver/fvMeshMoversMotionSolver.C:32-48`).
- `motionSolver::New` reads `motionSolver`, loads `motionSolverLibs`, and
  selects from the motion-solver dictionary table
  (`/opt/openfoam10/src/dynamicMesh/motionSolvers/motionSolver/motionSolver.C:65-103`).
- The base solver constructs a coefficient subdictionary named from the
  selected runtime type plus `Coeffs`
  (`/opt/openfoam10/src/dynamicMesh/motionSolvers/motionSolver/motionSolver.C:42-53`).

Static disassembly of the candidate binary shows `rbfDisplacement` being used
for `Foam::rbfMotionSolver::typeName` and passed to the
`motionSolver::adddictionaryConstructorToTable` registration constructor.
Thus the C++ class is `Foam::rbfMotionSolver`, while the inner runtime
selection key is `rbfDisplacement`.

| Entry | Recovered type / default / check | Still unknown |
|---|---|---|
| `motionSolver` | Required OpenFOAM word selecting `rbfDisplacement` | None for the selection name; actual load/run not exercised |
| `motionSolverLibs` | OpenFOAM library-list entry consumed by the inner solver loader; candidate library path/name is known | Whether an alternative outer preload route is intended; no runtime configuration tested |
| `rbfDisplacementCoeffs` | Coefficient subdictionary name derived by the OpenFOAM base class | Not a source-level RBF specification |
| `movingPatch` | Word; binary uses a default lookup with default exactly `cyl`; selected name is resolved against mesh patches and a missing patch triggers an error | Beyond patch lookup, what constraints the algorithm imposes on the selected patch |
| `controlStride` | Required integer entry; no default found; constructor rejects values `<= 0` | Meaning of stride, control-point selection/order, useful upper bound |
| `supportRadius` | Required scalar entry; no default found; constructor rejects values `<= 0` | Units, normalization, mathematical role, useful range |
| `cellDisplacement` | Internal field-name string visible in the constructor | Field lifecycle and its algorithmic role are not established by the name alone |
| Kernel/basis | No kernel selector or identifiable kernel name recovered from strings/symbols/examples | Kernel family, formula, compact/global support, and implementation details |

The recoverable schema shape is therefore only:

```foam
mover
{
    type                motionSolver;
    libs                ("libfvMeshMovers.so" "libfvMotionSolvers.so");
    motionSolverLibs    ("libRBFMotionSolver.so");
    motionSolver        rbfDisplacement;

    rbfDisplacementCoeffs
    {
        movingPatch     cylinder;
        controlStride   <positive integer; semantics unresolved>;
        supportRadius   <positive scalar; units and semantics unresolved>;
    }
}
```

This is **not** a runnable or approved configuration. The `movingPatch`
override is necessary for the current HH06 patch name `cylinder`, since the
binary default is `cyl`. Positive-value checks do not supply engineering
limits, unit conventions, or scientifically justified parameter values.

## Duanmu concept boundary

The conceptual acceptance target remains: keep the near-cylinder mesh stable
and propagate deformation outward with RBF motion. No conclusion about this
binary's compliance follows from its filename, class name, or parameter names.
In particular, the audit cannot confirm whether the boundary-layer points are
preserved, how controls are generated, whether far-field points are fixed, or
how influence decays with distance.

## Gate and execution boundary

The following remain unresolved and require an authoritative source/build
record or version-matched implementation documentation:

1. kernel/basis and its formula;
2. control-point generation and `controlStride` semantics;
3. fixed/far-field point selection and constraints;
4. `supportRadius` units, normalization, and influence semantics;
5. evidence that the near-cylinder boundary-layer mesh remains stable under
   the intended deformation.

No `dynamicMeshDict` or other production file was modified. No OpenFOAM
solver, mesh-motion test, ALE test, or FSI run was started. The current
Laplacian configuration remains unchanged.

**Final classification: `RBF_SOURCE_STILL_REQUIRED`.**
