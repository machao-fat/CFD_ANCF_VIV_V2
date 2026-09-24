// HH06 / Duanmu-style single-strip structured mesh, enlarged O-grid edition.
//
// Purpose:
//   Single-slice HH06 CFD/FSI mesh prepared for large-motion ALE with an
//   RBF mesh-motion method configured separately in OpenFOAM.
//
// Source-grounded geometry / resolution:
//   D = 0.028 m
//   Duanmu domain convention: x/D = [-10, 20], y/D = [-15, 15]
//   Duanmu Ch.6 Mesh-I controls: 50 cells / quadrant, 120 radial layers.
//
// Engineering changes in this file:
//   - O-grid outer radius enlarged from 3D to 6D (user-selected design).
//   - Near-wall first radial cell is preserved at ~6.2294e-5 m by retuning
//     radial progression from 1.03 to 1.038865884.
//   - Outer-block progressions are retuned to preserve the original
//     interface-spacing philosophy after the O-grid enlargement.
//   - External domain, topology, node counts, physical patch names and the
//     one-cell spanwise extrusion remain unchanged.
//
// Important source boundary:
//   Duanmu Ch.6 publishes the structured-mesh strategy and Mesh-I counts
//   (46,820 cells, 50/quadrant, 120 radial), but not the exact internal
//   O-grid radius or grading factors. R_OGRID=6D and the grading below are
//   therefore deliberate engineering choices, not claimed thesis values.
//   The present 15-block topology has 46,826 cells with one z layer.
//   RBF motion settings are NOT encoded in a Gmsh .geo file; configure the
//   RBF motion solver/control radii separately in the OpenFOAM case.
//
// Case-1 CFD parameters (not used by Gmsh itself):
//   U = 0.31 m/s, Re = 7622
//   nu = U*D/Re = 1.1388087116e-6 m^2/s
//
// Physical patches retained for gmshToFoam:
//   inlet, outlet, upper, lower, cylinder, front, back, fluid
//
SetFactory("Built-in");
Mesh.MshFileVersion = 2.2;
Mesh.ElementOrder = 1;
Mesh.RecombineAll = 1;

// ---------- Frozen physical geometry (metres) ----------
D = 0.028;
R = D/2.0;
R_OGRID = 6.0*D;          // Enlarged rigid/near-field buffer for RBF ALE; thesis radius is unpublished.
X_MIN = -10.0*D;
X_WAKE = 12.5*D;         // High-resolution wake block ends at x/D=10.
X_MAX = 20.0*D;
Y_MIN = -12.5*D;
Y_MAX = 12.5*D;
Z_SPAN = 1.0*D;           // One cell in z; front/back become empty in OpenFOAM.
SQRT2_INV = 0.7071067811865475;

// ---------- Structured-node controls (N means nodes, cells=N-1) ----------
N_CIRC = 51;               // 50 cells per quadrant, exactly Duanmu Ch.6 Mesh-I.
N_RADIAL = 121;           // 120 O-grid radial layers, exactly Duanmu Ch.6 Mesh-I.
N_INLET = 29;              // 28 cells from O-grid to upstream boundary.
N_VERTICAL = 43;         // 42 cells from O-grid/wake centre to y=±15D.
N_WAKE = 78;                // 77 cells over x~4.24D..10D at the diagonal wake interface.
N_OUTLET = 35;             // 34 cells over x=10D..20D.
P_RADIAL = 1.038865884045; // Wall->6D O-grid; preserves ~6.2294e-5 m first cell; outer radial cell ~5.821e-3 m.
P_INLET = 1.003800350572; // 6D O-grid->inlet; near-interface cell ~0.1953D, almost uniform to avoid a grading jump.
P_VERTICAL = 1.036598093668; // 6D O-grid/wake->y=+/-15D; smooth far-field coarsening with preserved interface scale ratio.
P_WAKE = 1.002022846638; // O-grid/wake connector; nearly uniform ~0.069D->0.081D for smooth x/D~4.24..10 resolution.
P_OUTLET = 1.06;         // Stronger growth only in far wake.

R45 = R*SQRT2_INV;
O45 = R_OGRID*SQRT2_INV;

// ---------- Geometric anchors ----------
pC = newp; Point(pC) = {0, 0, 0};
// Cylinder anchors: NE, NW, SW, SE.
pCNE = newp; Point(pCNE) = { R45,  R45, 0};
pCNW = newp; Point(pCNW) = {-R45,  R45, 0};
pCSW = newp; Point(pCSW) = {-R45, -R45, 0};
pCSE = newp; Point(pCSE) = { R45, -R45, 0};
// O-grid outer-circle anchors: NE, NW, SW, SE.
pONE = newp; Point(pONE) = { O45,  O45, 0};
pONW = newp; Point(pONW) = {-O45,  O45, 0};
pOSW = newp; Point(pOSW) = {-O45, -O45, 0};
pOSE = newp; Point(pOSE) = { O45, -O45, 0};
// Far-field and x/D=10 wake-interface anchors.
pLT = newp; Point(pLT) = {X_MIN, Y_MAX, 0};
pLB = newp; Point(pLB) = {X_MIN, Y_MIN, 0};
pRT = newp; Point(pRT) = {X_MAX, Y_MAX, 0};
pRB = newp; Point(pRB) = {X_MAX, Y_MIN, 0};
pInN = newp; Point(pInN) = {X_MIN,  O45, 0};
pInS = newp; Point(pInS) = {X_MIN, -O45, 0};
pTopNW = newp; Point(pTopNW) = {-O45, Y_MAX, 0};
pTopNE = newp; Point(pTopNE) = { O45, Y_MAX, 0};
pBottomNW = newp; Point(pBottomNW) = {-O45, Y_MIN, 0};
pBottomNE = newp; Point(pBottomNE) = { O45, Y_MIN, 0};
pWakeTop = newp; Point(pWakeTop) = {X_WAKE, Y_MAX, 0};
pWakeN = newp; Point(pWakeN) = {X_WAKE,  O45, 0};
pWakeS = newp; Point(pWakeS) = {X_WAKE, -O45, 0};
pWakeBottom = newp; Point(pWakeBottom) = {X_WAKE, Y_MIN, 0};
pOutN = newp; Point(pOutN) = {X_MAX,  O45, 0};
pOutS = newp; Point(pOutS) = {X_MAX, -O45, 0};

// ---------- Curves: circles and cylinder-to-O-grid normal lines ----------
aOTop = newc; Circle(aOTop) = {pONE, pC, pONW};
aOLeft = newc; Circle(aOLeft) = {pONW, pC, pOSW};
aOBottom = newc; Circle(aOBottom) = {pOSW, pC, pOSE};
aORight = newc; Circle(aORight) = {pOSE, pC, pONE};
aCTop = newc; Circle(aCTop) = {pCNE, pC, pCNW};
aCLeft = newc; Circle(aCLeft) = {pCNW, pC, pCSW};
aCBottom = newc; Circle(aCBottom) = {pCSW, pC, pCSE};
aCRight = newc; Circle(aCRight) = {pCSE, pC, pCNE};
rNE = newc; Line(rNE) = {pCNE, pONE};
rNW = newc; Line(rNW) = {pCNW, pONW};
rSW = newc; Line(rSW) = {pCSW, pOSW};
rSE = newc; Line(rSE) = {pCSE, pOSE};

// ---------- Curves: outer structured connectors ----------
// Upstream side and its upper/lower corners; O-grid → inlet directions are explicit.
cInUpper = newc; Line(cInUpper) = {pONW, pInN};
cInCentre = newc; Line(cInCentre) = {pInN, pInS};
cInLower = newc; Line(cInLower) = {pOSW, pInS};
cInTop = newc; Line(cInTop) = {pInN, pLT};
cInBottom = newc; Line(cInBottom) = {pInS, pLB};
cTopLeft = newc; Line(cTopLeft) = {pLT, pTopNW};
cBottomLeft = newc; Line(cBottomLeft) = {pLB, pBottomNW};
cTopNW = newc; Line(cTopNW) = {pONW, pTopNW};
cTopCentre = newc; Line(cTopCentre) = {pTopNW, pTopNE};
cTopNE = newc; Line(cTopNE) = {pONE, pTopNE};
cBottomNW = newc; Line(cBottomNW) = {pOSW, pBottomNW};
cBottomCentre = newc; Line(cBottomCentre) = {pBottomNW, pBottomNE};
cBottomNE = newc; Line(cBottomNE) = {pOSE, pBottomNE};

// Near wake: x~4.24D to x=10D at the diagonal interface; these blocks preserve dense streamwise cells.
cTopWake = newc; Line(cTopWake) = {pTopNE, pWakeTop};
cWakeTop = newc; Line(cWakeTop) = {pWakeN, pWakeTop};
cWakeN = newc; Line(cWakeN) = {pONE, pWakeN};
cWakeS = newc; Line(cWakeS) = {pOSE, pWakeS};
cWakeCentre = newc; Line(cWakeCentre) = {pWakeS, pWakeN};
cBottomWake = newc; Line(cBottomWake) = {pBottomNE, pWakeBottom};
cWakeBottom = newc; Line(cWakeBottom) = {pWakeS, pWakeBottom};

// Far wake / outlet: x=10 to x=20; coarser, but conformal to the near wake.
cTopOut = newc; Line(cTopOut) = {pWakeTop, pRT};
cOutTop = newc; Line(cOutTop) = {pOutN, pRT};
cOutN = newc; Line(cOutN) = {pWakeN, pOutN};
cOutS = newc; Line(cOutS) = {pWakeS, pOutS};
cOutCentre = newc; Line(cOutCentre) = {pOutS, pOutN};
cBottomOut = newc; Line(cBottomOut) = {pWakeBottom, pRB};
cOutBottom = newc; Line(cOutBottom) = {pOutS, pRB};

// ---------- Fifteen conformal 2-D structured surfaces ----------
// Four inner, genuinely body-fitted O-grid sectors.
llRingTop = newll; Curve Loop(llRingTop) = {aOTop, -rNW, -aCTop, rNE};
sRingTop = news; Plane Surface(sRingTop) = {llRingTop};
llRingLeft = newll; Curve Loop(llRingLeft) = {aOLeft, -rSW, -aCLeft, rNW};
sRingLeft = news; Plane Surface(sRingLeft) = {llRingLeft};
llRingBottom = newll; Curve Loop(llRingBottom) = {aOBottom, -rSE, -aCBottom, rSW};
sRingBottom = news; Plane Surface(sRingBottom) = {llRingBottom};
llRingRight = newll; Curve Loop(llRingRight) = {aORight, -rNE, -aCRight, rSE};
sRingRight = news; Plane Surface(sRingRight) = {llRingRight};
// Upstream, upper and lower connectors.
llNW = newll; Curve Loop(llNW) = {cInUpper, cInTop, cTopLeft, -cTopNW};
sNW = news; Plane Surface(sNW) = {llNW};
llWest = newll; Curve Loop(llWest) = {cInUpper, cInCentre, -cInLower, -aOLeft};
sWest = news; Plane Surface(sWest) = {llWest};
llSW = newll; Curve Loop(llSW) = {cInLower, cInBottom, cBottomLeft, -cBottomNW};
sSW = news; Plane Surface(sSW) = {llSW};
llTopCentre = newll; Curve Loop(llTopCentre) = {cTopNW, cTopCentre, -cTopNE, aOTop};
sTopCentre = news; Plane Surface(sTopCentre) = {llTopCentre};
llBottomCentre = newll; Curve Loop(llBottomCentre) = {cBottomNW, cBottomCentre, -cBottomNE, -aOBottom};
sBottomCentre = news; Plane Surface(sBottomCentre) = {llBottomCentre};
// Three near-wake blocks connect the enlarged 6D O-grid to the fixed far-field blocks.
llUpperWake = newll; Curve Loop(llUpperWake) = {cTopNE, cTopWake, -cWakeTop, -cWakeN};
sUpperWake = news; Plane Surface(sUpperWake) = {llUpperWake};
llCentreWake = newll; Curve Loop(llCentreWake) = {cWakeS, cWakeCentre, -cWakeN, -aORight};
sCentreWake = news; Plane Surface(sCentreWake) = {llCentreWake};
llLowerWake = newll; Curve Loop(llLowerWake) = {cBottomNE, cBottomWake, -cWakeBottom, -cWakeS};
sLowerWake = news; Plane Surface(sLowerWake) = {llLowerWake};
// Three far-outlet blocks complete the rectangular domain.
llUpperOut = newll; Curve Loop(llUpperOut) = {cWakeTop, cTopOut, -cOutTop, -cOutN};
sUpperOut = news; Plane Surface(sUpperOut) = {llUpperOut};
llCentreOut = newll; Curve Loop(llCentreOut) = {cOutS, cOutCentre, -cOutN, -cWakeCentre};
sCentreOut = news; Plane Surface(sCentreOut) = {llCentreOut};
llLowerOut = newll; Curve Loop(llLowerOut) = {cWakeBottom, cBottomOut, -cOutBottom, -cOutS};
sLowerOut = news; Plane Surface(sLowerOut) = {llLowerOut};

// ---------- Transfinite controls; no curve is assigned twice ----------
Transfinite Curve {aOTop, aOLeft, aOBottom, aORight, aCTop, aCLeft, aCBottom, aCRight,
                   cInCentre, cTopCentre, cBottomCentre, cWakeCentre, cOutCentre} = N_CIRC;
Transfinite Curve {rNE, rNW, rSW, rSE} = N_RADIAL Using Progression P_RADIAL;
Transfinite Curve {cInTop, cInBottom, cTopNW, cTopNE, cBottomNW, cBottomNE,
                   cWakeTop, cWakeBottom, cOutTop, cOutBottom} = N_VERTICAL Using Progression P_VERTICAL;
// The negative tags orient these two far-field top/bottom lines from O-grid outward.
Transfinite Curve {cInUpper, cInLower, -cTopLeft, -cBottomLeft} = N_INLET Using Progression P_INLET;
Transfinite Curve {cTopWake, cWakeN, cWakeS, cBottomWake} = N_WAKE Using Progression P_WAKE;
Transfinite Curve {cTopOut, cOutN, cOutS, cBottomOut} = N_OUTLET Using Progression P_OUTLET;

Transfinite Surface {sRingTop, sRingLeft, sRingBottom, sRingRight,
                     sNW, sWest, sSW, sTopCentre, sBottomCentre,
                     sUpperWake, sCentreWake, sLowerWake,
                     sUpperOut, sCentreOut, sLowerOut};
Recombine Surface {sRingTop, sRingLeft, sRingBottom, sRingRight,
                   sNW, sWest, sSW, sTopCentre, sBottomCentre,
                   sUpperWake, sCentreWake, sLowerWake,
                   sUpperOut, sCentreOut, sLowerOut};

// ---------- One-layer extrusion; lists capture created entities dynamically ----------
// Each list is {top face, volume, lateral faces in the preceding Curve Loop order}.
// This deliberately avoids hard-coded post-Extrude surface/volume IDs.
eRingTop[] = Extrude {0, 0, Z_SPAN} { Surface{sRingTop}; Layers{1}; Recombine; };
eRingLeft[] = Extrude {0, 0, Z_SPAN} { Surface{sRingLeft}; Layers{1}; Recombine; };
eRingBottom[] = Extrude {0, 0, Z_SPAN} { Surface{sRingBottom}; Layers{1}; Recombine; };
eRingRight[] = Extrude {0, 0, Z_SPAN} { Surface{sRingRight}; Layers{1}; Recombine; };
eNW[] = Extrude {0, 0, Z_SPAN} { Surface{sNW}; Layers{1}; Recombine; };
eWest[] = Extrude {0, 0, Z_SPAN} { Surface{sWest}; Layers{1}; Recombine; };
eSW[] = Extrude {0, 0, Z_SPAN} { Surface{sSW}; Layers{1}; Recombine; };
eTopCentre[] = Extrude {0, 0, Z_SPAN} { Surface{sTopCentre}; Layers{1}; Recombine; };
eBottomCentre[] = Extrude {0, 0, Z_SPAN} { Surface{sBottomCentre}; Layers{1}; Recombine; };
eUpperWake[] = Extrude {0, 0, Z_SPAN} { Surface{sUpperWake}; Layers{1}; Recombine; };
eCentreWake[] = Extrude {0, 0, Z_SPAN} { Surface{sCentreWake}; Layers{1}; Recombine; };
eLowerWake[] = Extrude {0, 0, Z_SPAN} { Surface{sLowerWake}; Layers{1}; Recombine; };
eUpperOut[] = Extrude {0, 0, Z_SPAN} { Surface{sUpperOut}; Layers{1}; Recombine; };
eCentreOut[] = Extrude {0, 0, Z_SPAN} { Surface{sCentreOut}; Layers{1}; Recombine; };
eLowerOut[] = Extrude {0, 0, Z_SPAN} { Surface{sLowerOut}; Layers{1}; Recombine; };

// ---------- Stable physical names consumed by gmshToFoam ----------
// z=0 and z=1 planes are separate 2-D patches, not a combined group.
Physical Surface("front") = {sRingTop, sRingLeft, sRingBottom, sRingRight,
                              sNW, sWest, sSW, sTopCentre, sBottomCentre,
                              sUpperWake, sCentreWake, sLowerWake,
                              sUpperOut, sCentreOut, sLowerOut};
Physical Surface("back") = {eRingTop[0], eRingLeft[0], eRingBottom[0], eRingRight[0],
                             eNW[0], eWest[0], eSW[0], eTopCentre[0], eBottomCentre[0],
                             eUpperWake[0], eCentreWake[0], eLowerWake[0],
                             eUpperOut[0], eCentreOut[0], eLowerOut[0]};
// Lateral indices are derived from each Curve Loop order above, never global IDs.
Physical Surface("cylinder") = {eRingTop[4], eRingLeft[4], eRingBottom[4], eRingRight[4]};
Physical Surface("inlet") = {eNW[3], eWest[3], eSW[3]};
Physical Surface("upper") = {eNW[4], eTopCentre[3], eUpperWake[3], eUpperOut[3]};
Physical Surface("lower") = {eSW[4], eBottomCentre[3], eLowerWake[3], eLowerOut[3]};
Physical Surface("outlet") = {eUpperOut[4], eCentreOut[3], eLowerOut[4]};
Physical Volume("fluid") = {eRingTop[1], eRingLeft[1], eRingBottom[1], eRingRight[1],
                             eNW[1], eWest[1], eSW[1], eTopCentre[1], eBottomCentre[1],
                             eUpperWake[1], eCentreWake[1], eLowerWake[1],
                             eUpperOut[1], eCentreOut[1], eLowerOut[1]};
