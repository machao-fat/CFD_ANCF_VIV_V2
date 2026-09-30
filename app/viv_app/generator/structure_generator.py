from dataclasses import asdict
import json
from .errors import blocked
from .native import load_kernel


def structure_payload(spec,baseline,manifest):
    base=baseline.structure
    for name in ('diameter_m','length_m','ea_n','ei_nm2','mass_per_length','pretension_n','elements'):
        if getattr(spec.structure,name)!=getattr(base,name):
            blocked(f'structure.{name}: NOT YET WIRED; inherited mesh/equilibrium state cannot be safely regenerated')
    model=asdict(baseline.model)
    model['slices']=manifest.ns
    model['slice_positions_m']=[row.s_ref_m for row in manifest.slices]
    model['damping_alpha']=spec.structure.damping_alpha
    # Native SLD1 parameters agree with inherited interval; no algorithm switch.
    kernel=load_kernel(model)
    kernel.validate(spec.delta_t)
    return model


def write_structure(root,spec,baseline,manifest):
    directory=root/'Structure_0000'
    directory.mkdir()
    model=structure_payload(spec,baseline,manifest)
    (directory/'kernel_model.json').write_text(json.dumps(model,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    # No q synthesis/resampling, including for changed Ns.
    (directory/'initial_state.json').write_bytes(baseline.relative(baseline.descriptor['structure_initial_state']).read_bytes())
    config={'schema':'viv-app-structure-import-v1','participant':'Structure_0000',
            'kernel_model':'kernel_model.json','initial_state':'initial_state.json',
            'slice_manifest':'../slice_manifest.json','precice_config':'../precice-config.xml',
            'runner_status':'NOT_YET_WIRED_IN_ORIGIN_MAIN',
            'evidence_status':baseline.descriptor['evidence_status']}
    (directory/'structure_config.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    return model
