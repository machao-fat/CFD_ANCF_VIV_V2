# Bao thick-strip terminology: bounded source check

This note uses the accessible publisher abstract/preview text for the two
specified primary papers. Their complete equations were not available from
the publisher pages in this audit; no unverified equation, strip count, or
parameter is attributed to them.

- Bao, Palacios, Graham & Sherwin (2016), *Generalized thick strip modelling
  for vortex-induced vibration of long flexible cylinders*, Journal of
  Computational Physics 321, 1079–1097,
  [publisher page](https://www.sciencedirect.com/science/article/pii/S0021999116302236),
  DOI 10.1016/j.jcp.2016.05.062. The accessible abstract describes
  **independent, locally three-dimensional fluid strip domains** with a
  finite axial/spanwise extent, coupled to one another through the structural
  model. The thick local fluid span permits local turbulence and three-
  dimensional wake dynamics missing from a conventional 2D strip.
- Bao et al. (2019), *Numerical prediction of vortex-induced vibration of
  flexible riser with thick strip method*, Journal of Fluids and Structures
  89, 166–173,
  [publisher page](https://www.sciencedirect.com/science/article/pii/S0889974618308454),
  DOI 10.1016/j.jfluidstructs.2019.02.010. The accessible abstract and
  introduction describe applying that thick-strip, high-order spectral/hp
  fluid method to a tensioned riser, comparing motion, fluid forces, and wake
  patterns; local 3D flow is distinguished from 2D strip theory.

Two different lengths must not be conflated:

1. **Local CFD fluid-span thickness**, often denoted `Lz`: extent of each
   solved three-dimensional fluid domain along the cylinder. It governs how
   much local three-dimensional near-wake structure a strip can contain.
2. **Tributary structural interval**, here `DeltaL = 1.98 m`: length of the
   global ANCF structure represented by one local CFD force. The current
   CFD wall-force span used for conversion is `0.028 m`; it is **not** the
   `1.98 m` tributary interval. The two lengths play different roles.

Within-strip constant hydrodynamic force density and center kinematics are
*zeroth-order structural/force reconstruction assumptions* in the present
diagnostic. The available Bao text does not establish that its actual
fluid-to-structure virtual-work mapping is either this report's midpoint
`H(center)^T Fstrip` or its diagnostic distributed
`integral H(s)^T (Fstrip/DeltaL) ds`. Neither paper supplies a transferable
value for this project's `DeltaL`, `Lz`, strip count, or mapping correction
from the accessible text. No parameter has been copied.

The distributed mapping in NM10 is a **counterfactual application of the
same accepted NM9-B forces**, not a new CFD computation and not a computed
structural response. A difference between the two maps cannot by itself
prove which map is physically correct or that a particular CFD strip count
is converged.
