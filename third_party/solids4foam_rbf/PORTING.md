# solids4foam RBF mesh-motion solver: OpenFOAM Foundation 10 port

## Upstream provenance

- Repository: <https://github.com/solids4foam/solids4foam>
- Release/tag: `v2.4`
- Commit: `1341312f951caf4d8fcc69499c6ce1a588826156`
- License: GNU GPL v3 or later; see [`LICENSE`](LICENSE).
- `upstream/` preserves the upstream `src/RBFMeshMotionSolver/` subtree at
  that commit. The separate `of10/` directory is the locally ported build
  source; it is not represented as byte-identical upstream code.

The upstream tutorial documents TPS and the patch-list semantics. Its RBF
README describes a short test with OpenFOAM.com v2312, not Foundation 10. This
repository therefore carries an explicit Foundation 10 API/input port rather
than claiming native upstream ABI compatibility.

## Foundation 10 port boundary

The port keeps the upstream RBF interpolation, TPS/Wendland functions,
coarsening, and two-dimensional point handling. It changes the solver-facing
contract to match OpenFOAM Foundation 10:

- registers an OF10 `motionSolver` constructor and derives from
  `displacementMotionSolver`;
- consumes the moving patch's `pointDisplacement` point-patch values;
- requires `faceCellCenters no` (point controls, not face-centre controls);
- interpolates absolute displacement on `points0` and returns
  `points0 + displacement`, avoiding accumulation on already moved points;
- uses OF10's `typeIOobject` addressing-file check.

The compatibility port does not change the upstream RBF kernel formulas. The
TPS source evaluates `r*r*log(r)` for positive Euclidean distance `r` and zero
at `r=0`; TPS has no support-radius parameter.

## Build

Requires OpenFOAM Foundation 10, GCC, Eigen 3 headers, and `wmake`.
`FieldSumOp.H` is also retained from the pinned upstream commit.

```bash
source /opt/openfoam10/etc/bashrc
export EIGEN3_INCLUDE_DIR=/usr/include/eigen3
cd third_party/solids4foam_rbf/of10
wmake libso
```

`Make/files` writes `libRBFMeshMotionSolver.so` into `FOAM_USER_LIBBIN`.
The build is intentionally not committed as a binary.

## HH06 mesh-motion limits

The solver's `movingPatches`, `staticPatches`, and `fixedPatches` are boundary
patch lists. The 6D O-grid perimeter in the HH06 Gmsh mesh is internal, not a
boundary patch, so it cannot be pinned independently through this interface.
Do not claim that it is fixed or moves rigidly with the cylinder. For
large-motion preservation of the near-wall block, a separate, tested internal
point-zone control feature may be needed. No such extension is included here.

The integration is qualified only by compilation and an offline prescribed
mesh-motion test. No OpenFOAM flow solver, preCICE participant, ANCF worker, or
FSI runtime is qualified by this port.
