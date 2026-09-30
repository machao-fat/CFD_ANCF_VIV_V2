from dataclasses import replace
from .native import build_slice_manifest, generate_precice_xml, inspect_precice_xml
from .errors import blocked
from .baseline import NAMING


def build_manifest(spec, baseline):
    native = baseline.manifest
    n = len(spec.positions_over_l)
    if native.reconstruction_mode == 'LegacyPointLumped' and n != 1:
        blocked('LegacyPointLumped: V1 retains its single-slice tributary; cannot infer multi-slice integrated-force intervals')
    spans = {row.unit_span_m for row in native.slices}
    if len(spans) != 1:
        blocked('slice_manifest.unit_span_m: non-uniform template extrusion cannot be inferred for new slices')
    coupling = {
        'mode': native.reconstruction_mode,
        'active_start_m': native.active_start_m,
        'active_end_m': native.active_end_m,
        'endpoint_policy': native.endpoint_policy,
        'placement': 'uniform_centers', 'count': n,
        'unit_span_m': next(iter(spans)),
    }
    if native.reconstruction_mode == 'LegacyPointLumped':
        coupling['slice_length_m'] = native.slices[0].slice_length_m
    root = {'case_id':spec.case_name, 'length_m':spec.structure.length_m,
            'interfaces':{'structure_participant':'Structure_0000'}, 'coupling':coupling}
    uniform = build_slice_manifest(root)
    positions = tuple(x*spec.structure.length_m for x in spec.positions_over_l)
    if spec.placement == 'uniform' and any(abs(a-b.s_ref_m)>1e-10 for a,b in zip(positions,uniform.slices)):
        blocked('uniform placement table differs from native uniform-centers helper')
    # Lengths/endpoint policy come from the native helper, never a new force rule.
    coupling['placement']='explicit'
    coupling['slices']=[dict(slice_id=row.slice_id,s_ref_m=position,
                            slice_length_m=row.slice_length_m,unit_span_m=row.unit_span_m)
                        for row,position in zip(uniform.slices,positions)]
    result = build_slice_manifest(root)
    rows = tuple(replace(row,fluid_participant=NAMING['fluid_participant_pattern'].format(index=i),
                         openfoam_case_id=NAMING['case_pattern'].format(index=i))
                 for i,row in enumerate(result.slices))
    return replace(result,slices=rows,manifest_sha256=None)


def write_xml(root,spec,manifest):
    xml = generate_precice_xml(manifest,time_window_s=spec.delta_t,
                               max_time_s=spec.end_time-float(spec.initial_state_time),
                               exchange_directory='../precice-sockets')
    inspect_precice_xml(xml,manifest)
    (root/'precice-config.xml').write_text(xml+'\n',encoding='utf-8')
    return xml
