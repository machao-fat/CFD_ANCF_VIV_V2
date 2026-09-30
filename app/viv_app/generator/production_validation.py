"""Independent static validation of fixed N5 production cases."""
from pathlib import Path
from datetime import datetime,timezone
import json
import math
import os
import yaml
from .baseline import read_json,digest
from .production_baseline import (inspect_production_baseline,validate_production_spec,PROFILE_ROOT,PROFILE,
    FIELDS,MESH_FIELDS,POSITIONS,LABELS,selected_state,file_identity,require)
from .production_xml import V2606ImplicitTopologyBuilder
from .production_generator import (fluid_control,fluid_precice,initial_velocity,model_witness,slice_manifest,launch_manifest)
from .errors import GenerationError
from viv_app.utils.paths import local_path,within,CASES_ROOT


def validate_production_case(path,write_report=True):
    from .case_generator import write_json
    from .validation import spec_from_mapping
    root=local_path(path);checks=[]
    result={'status':'FAIL','first_failure':None,'checks':checks,'scope':'PRODUCTION_CONFIGURATION_STATIC',
            'validation_time':datetime.now(timezone.utc).isoformat(),'real_fsi_started':False}
    def check(name,condition,detail):
        checks.append({'check':name,'status':'PASS' if condition else 'FAIL','detail':detail})
        require(condition,name,detail)
    try:
        check('CASE_DIRECTORY',root.is_dir() and within(root,CASES_ROOT),'case under APP/workspace/cases')
        for name in ('simulation_spec.yaml','generation_manifest.json','baseline_contract_snapshot.json','production_xml_template.xml',
                     'precice-config.xml','slice_manifest.json','launch_manifest.json','Structure/structure_config.json',
                     'Structure/compiled_kernel_model.json','Structure/initial_state.raw','MANUAL_LAUNCH.md'):
            check('REQUIRED_ARTIFACT',(root/name).is_file() and not (root/name).is_symlink(),name)
        spec=spec_from_mapping(yaml.safe_load((root/'simulation_spec.yaml').read_text()))
        windows=validate_production_spec(spec)
        meta=read_json(root/'generation_manifest.json');d=read_json(root/'baseline_contract_snapshot.json')
        b=inspect_production_baseline(spec.baseline_path)
        check('ENROLLED_QUALIFIED_PROFILE',d==b.descriptor and d==read_json(PROFILE_ROOT/'app_baseline.json'),'NM12 enrolled identities and actual PASS evidence')
        check('APP_PROVENANCE',len(meta['app']['commit'])==40 and meta['app']['branch'] in ('app/mvp-case-generator-v1','app/production-baseline-bridge-v1') and bool(meta['app']['source_hashes']),'APP commit/branch/source identities')
        check('PROVENANCE',meta['contract_profile']==PROFILE and meta['case_name']==spec.case_name and meta['baseline_path']==str(b.root) and
              meta['baseline_key_hashes']==b.key_hashes(spec.initial_state_time) and
              meta['baseline_initial_sample_identities']==b.initial_identity() and meta['source_qualification']==d['qualification_classification'],
              'baseline key and bounded initial/mesh identities agree')
        expected_meta={'slice_count':5,'slice_positions_m':list(POSITIONS),'U_i':[spec.flow.velocity(x) for x in spec.positions_over_l],
            'flow_profile':spec.to_dict()['flow'],'structure_parameters':spec.to_dict()['structure'],'deltaT':spec.delta_t,
            'endTime':spec.end_time,'coupled_duration_s':windows*.0004,'max_time_windows':windows,'writeInterval':spec.write_interval,
            'purgeWrite':spec.purge_write,'mpi_ranks':list(spec.mpi_ranks),'real_fsi_started':False,'manual_decomposition_required':True}
        check('SPEC_MANIFEST_CONSISTENCY',all(meta[k]==v for k,v in expected_meta.items()),'flow, positions, numerics, MPI and physical locks')
        check('GENERATION_STATUS',meta['generation_status'] in ('STATIC_VALIDATION_PENDING','PASS'),'generation has not failed')
        xml=(root/'precice-config.xml').read_bytes();template=Path(d['xml_template']).read_bytes()
        check('XML_TEMPLATE_IDENTITY',(root/'production_xml_template.xml').read_bytes()==template,'actual NM12 template')
        parsed=V2606ImplicitTopologyBuilder(template).validate(xml,windows)
        check('IMPLICIT_XML_SEMANTIC_IDENTITY',True,'parser comparison: only horizon/socket path change')
        check('XML_IDENTITY',digest(xml)==meta['precice_sha256'],'generated XML hash')
        check('XML_PARTICIPANTS',[p.get('name') for p in parsed.findall('participant')]==[f'Fluid-S{i}' for i in range(1,6)]+['Structure'],'five unique fluids plus one Structure')
        expected_slice=slice_manifest(spec)
        check('SLICE_MANIFEST',read_json(root/'slice_manifest.json')==expected_slice,'compiled positions, U_i, MPI, mesh/data names and directories')
        check('KERNEL_MODEL_WITNESS',read_json(root/'Structure/compiled_kernel_model.json')==model_witness(d),'compiled model observer, not an invented solver input')
        cfg=read_json(root/'Structure/structure_config.json')
        expected_cfg={'participant':'Structure','slice_count':5,'slice_positions_m':list(POSITIONS),'precice_config':'../precice-config.xml',
            'initial_state':'initial_state.raw','slice_manifest':'../slice_manifest.json','compiled_model':'compiled_kernel_model.json',
            'executable':d['structure_executable'],'physics_input_role':'NONE_COMPILED_MODEL_IS_AUTHORITATIVE'}
        check('STRUCTURE_CONFIGURATION',cfg==expected_cfg,'native command/local paths and locked topology')
        state=selected_state(Path(d['structure_state']).read_bytes())
        check('INITIAL_STRUCTURE_IDENTITY',(root/'Structure/initial_state.raw').read_bytes()==state and digest(state)==meta['initial_structure_selected_record_sha256'],
              'literal P1_REF_NE32 CASE/Q, no reconstructed equilibrium')
        launch=read_json(root/'launch_manifest.json');expected_launch=launch_manifest(spec,d)
        expected_launch['production_launch_ready']=launch.get('production_launch_ready')
        check('MANUAL_LAUNCH_CONTRACT',launch==expected_launch and isinstance(launch['production_launch_ready'],bool) and
              meta['production_launch_ready']==launch['production_launch_ready'],'exact native argv, relative local inputs, 20 ranks, manual only')
        expected_dirs={f'fluid_{x}' for x in LABELS}
        actual_dirs={p.name for p in root.iterdir() if p.is_dir() and p.name.startswith('fluid_')}
        check('FLUID_CASE_COUNT',actual_dirs==expected_dirs,'five case directories')
        for i,(source,label,x) in enumerate(zip(b.fluids,LABELS,spec.positions_over_l),1):
            fluid=root/f'fluid_{label}';v=spec.flow.velocity(x)
            for name in (*[f'constant/polyMesh/{n}' for n in MESH_FIELDS],*[f'{spec.initial_state_time}/{n}' for n in FIELDS],
                         'system/controlDict','system/preciceDict','system/decomposeParDict','system/fvSolution','system/fvSchemes','constant/dynamicMeshDict'):
                check('COMPLETE_FLUID_CASE',(fluid/name).is_file(),f'{label}/{name}')
            check('PRECISE_CONTROL_INHERITANCE',(fluid/'system/controlDict').read_bytes()==fluid_control((source/'system/controlDict').read_bytes(),spec,v),label)
            check('PRECISE_ADAPTER_INHERITANCE',(fluid/'system/preciceDict').read_bytes()==fluid_precice((source/'system/preciceDict').read_bytes(),i),label)
            check('INITIAL_U_CONTRACT',(fluid/spec.initial_state_time/'U').read_bytes()==initial_velocity((source/spec.initial_state_time/'U').read_bytes(),v),
                  f'{label}: opaque internal bytes, inlet vector and proven moving wall preparation')
            # Configuration byte identity is checked independently of generator metadata.
            for folder in ('system','constant',spec.initial_state_time):
                src=source/folder;dst=fluid/folder
                source_files={p.relative_to(src) for p in src.rglob('*') if p.is_file()}
                target_files={p.relative_to(dst) for p in dst.rglob('*') if p.is_file()}
                check('COPY_COMPLETENESS',source_files==target_files,f'{label}/{folder}: selected files only')
                for relative in source_files:
                    if folder=='system' and str(relative) in ('controlDict','preciceDict'):continue
                    if folder==spec.initial_state_time and str(relative)=='U':continue
                    check('INHERITED_FILE_IDENTITY',file_identity(src/relative)==file_identity(dst/relative),f'{label}/{folder}/{relative}')
            check('CASE_LOCAL_OUTPUT_PATHS',str(source).encode() not in (fluid/'system/controlDict').read_bytes() and
                  str(Path(d['source_root'])/'runtime').encode() not in (fluid/'system/controlDict').read_bytes(),label)
            check('NO_RUNTIME_COPY',not any(p.name.startswith('processor') or p.name in ('postProcessing','precice-run') or p.name.startswith('log.') for p in fluid.iterdir()),label)
        for p in root.rglob('*'):
            check('NO_SYMLINKS',not p.is_symlink(),str(p.relative_to(root)))
        check('OUTPUT_DIRECTORY_WRITABLE',os.access(root,os.W_OK),'current user write access')
        result['status']='PASS'
    except Exception as exc:
        result['first_failure']=str(exc)
        if not checks or checks[-1]['status']!='FAIL':checks.append({'check':'CONTRACT_VALIDATION','status':'FAIL','detail':str(exc)})
    if write_report and root.is_dir():
        write_json(root/'generation_validation.json',result)
        if result['status']=='FAIL':
            for name in ('launch_manifest.json','generation_manifest.json'):
                if (root/name).is_file():
                    try:
                        data=read_json(root/name);data['production_launch_ready']=False
                        write_json(root/name,data)
                    except (ValueError,OSError):pass
            if (root/'production_preflight.json').is_file():
                previous=read_json(root/'production_preflight.json')
                previous.update(status='FAIL',production_launch_ready=False,first_failure=result['first_failure'])
                write_json(root/'production_preflight.json',previous)
    return result
