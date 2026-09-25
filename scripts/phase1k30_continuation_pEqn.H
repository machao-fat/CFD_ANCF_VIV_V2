// Diagnostic pressure-correction path used only after the production prefix.
// It keeps the current case's nCorrectors and schemes, while explicitly
// retaining the final solver/relaxation lifecycle for every diagnostic solve.

volScalarField rAU(1.0/UEqn.A());
volVectorField HbyA(constrainHbyA(rAU*UEqn.H(), U, p));
surfaceScalarField phiHbyA
(
    "phiHbyA",
    fvc::flux(HbyA)
  + MRF.zeroFilter(fvc::interpolate(rAU)*fvc::ddtCorr(U, phi, Uf))
);

MRF.makeRelative(phiHbyA);

if (p.needReference())
{
    fvc::makeRelative(phiHbyA, U);
    adjustPhi(phiHbyA, U, p);
    fvc::makeAbsolute(phiHbyA, U);
}

tmp<volScalarField> rAtU(rAU);

if (pimple.consistent())
{
    rAtU = 1.0/max(1.0/rAU - UEqn.H1(), 0.1/rAU);
    phiHbyA +=
        fvc::interpolate(rAtU() - rAU)*fvc::snGrad(p)*mesh.magSf();
    HbyA -= (rAU - rAtU())*fvc::grad(p);
}

if (pimple.nCorrPiso() <= 1)
{
    tUEqn.clear();
}

constrainPressure(p, U, phiHbyA, rAtU(), MRF);

for (Foam::label phase1k30Piso = 0; phase1k30Piso < pimple.nCorrPiso(); ++phase1k30Piso)
{
    fvScalarMatrix pEqn
    (
        fvm::laplacian(rAtU(), p) == fvc::div(phiHbyA)
    );

    pEqn.setReference
    (
        pressureReference.refCell(),
        pressureReference.refValue()
    );

    // The continuation is intentionally a final-path diagnostic.  Keep the
    // same final dictionary and relaxation selection for every cycle solve.
    mesh.data::remove("finalIteration");
    mesh.data::add("finalIteration", true);
    pEqn.solve();

    if (phase1k30Piso + 1 == pimple.nCorrPiso())
    {
        phi = phiHbyA - pEqn.flux();
    }
}

#include "continuityErrs.H"

mesh.data::remove("finalIteration");
mesh.data::add("finalIteration", true);
p.relax();

U = HbyA - rAtU*fvc::grad(p);
U.correctBoundaryConditions();
fvConstraints.constrain(U);

fvc::correctUf(Uf, U, phi, MRF);
fvc::makeRelative(phi, U);
