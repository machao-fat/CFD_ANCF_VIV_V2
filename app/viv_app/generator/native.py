"""Thin read-only bridge to the project's authoritative offline primitives.

Never import an OpenFOAM adapter, start a worker, or initialize preCICE.
The APP is deliberately installed inside its source worktree.
"""
import sys
from viv_app.utils.paths import APP_ROOT

source = APP_ROOT / "src"
if str(source) not in sys.path:
    sys.path.insert(0, str(source))

from coupling.arbitrary_n_live_orchestration_v1.manifest import (  # noqa: E402
    SliceManifest, OrchestrationSlice, build_slice_manifest,
)
from coupling.arbitrary_n_live_orchestration_v1.topology import (  # noqa: E402
    generate_precice_xml, inspect_precice_xml, generate_openfoam_launch_plan,
)
from ancf.kernel_protocol import KernelModel, SpanwiseHydrodynamicRegion  # noqa: E402


def load_manifest(raw):
    raw = dict(raw)
    raw['slices'] = tuple(OrchestrationSlice(**row) for row in raw['slices'])
    return SliceManifest(**raw)


def load_kernel(raw):
    raw = dict(raw)
    for name in ('slice_positions_m', 'fixed_dof', 'prescribed_values'):
        if name in raw:
            raw[name] = tuple(raw[name])
    raw['hydrodynamic_regions'] = tuple(
        SpanwiseHydrodynamicRegion(**{
            **region,
            'added_mass_per_length_kg_m': tuple(region['added_mass_per_length_kg_m']),
            'linear_damping_per_length_Ns_m2': tuple(region['linear_damping_per_length_Ns_m2']),
        }) for region in raw.get('hydrodynamic_regions', [])
    )
    return KernelModel(**raw)
