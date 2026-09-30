from pathlib import Path
import json
import math
import yaml
from dataclasses import asdict
from datetime import datetime,timezone
from .baseline import (read_json,digest,prefix_identity,normalized_xml,operational_absolute_paths,
                       REQUIRED_DESCRIPTOR,PROFILE,NAMING)
from .foam_dict import FoamDict,inlet_vector,velocity_boundary
from .native import load_manifest,load_kernel,generate_precice_xml,inspect_precice_xml
from .errors import GenerationError
from viv_app.models.simulation_spec import SimulationSpec,StructureParameters,FlowProfile
from viv_app.utils.paths import local_path,within,CASES_ROOT

CONTROL_MASK={('startFrom',):'startTime',('startTime',):'0',('deltaT',):'1',('endTime',):'1',('writeInterval',):'1'}
PRECICE_MASK={('participant',):'Fluid_0000',('preciceConfig',):'"precice-config.xml"',('interfaces','Interface1','mesh'):'Fluid-Mesh-placeholder'}


def spec_from_mapping(raw):
    raw=dict(raw)
    raw['structure']=StructureParameters(**raw['structure'])
    raw['flow']=FlowProfile(**raw['flow'])
    for name in ('positions_over_l','mpi_ranks','enabled'):
        if name in raw:
            raw[name]=tuple(raw[name])
    return SimulationSpec(**raw)


def validate_case(path,write_report=True):
    root=local_path(path)
    checks=[]
    def check(name,condition,detail):
        checks.append({'check':name,'status':'PASS' if condition else 'FAIL','detail':detail})
        if not condition:
            raise GenerationError(name,detail)
    result={'status':'FAIL','first_failure':None,'checks':checks,
            'validation_time':datetime.now(timezone.utc).isoformat(),
            'scope':'OFFLINE_CONFIGURATION_ONLY','production_launch_ready':False}
    try:
        check('CASE_DIRECTORY',root.is_dir() and within(root,CASES_ROOT),'generated case must exist under APP/workspace/cases')
        for required in ('simulation_spec.yaml','generation_manifest.json','precice-config.xml','slice_manifest.json','launch_manifest.json','baseline_contract_snapshot.json'):
            check('REQUIRED_ARTIFACT',(root/required).is_file(),required)
        spec=spec_from_mapping(yaml.safe_load((root/'simulation_spec.yaml').read_text(encoding='utf-8')))
        spec.validate()
        meta=read_json(root/'generation_manifest.json')
        descriptor=read_json(root/'baseline_contract_snapshot.json')
        check('CONTRACT_PROFILE',set(descriptor)==REQUIRED_DESCRIPTOR and descriptor['contract_profile']==PROFILE and descriptor['naming']==NAMING,'audited explicit import profile')
        manifest=load_manifest(read_json(root/'slice_manifest.json'))
        n=len(spec.positions_over_l)
        check('SLICE_COUNT',n==manifest.ns==meta['slice_count'],'N matches spec, manifest and metadata')
        check('CASE_IDENTITY',meta['case_name']==manifest.case_id==spec.case_name,'case_name')
        check('SLICE_POSITIONS',all(math.isclose(row.s_ref_m,x*spec.structure.length_m,abs_tol=1e-12) for row,x in zip(manifest.slices,spec.positions_over_l)) and meta['slice_positions_m']==[r.s_ref_m for r in manifest.slices],'structure positions agree')
        velocities=[spec.flow.velocity(x) for x in spec.positions_over_l]
        check('FLOW_COUNT',len(meta['U_i'])==n and meta['U_i']==velocities,'per-slice U_i')
        check('PROVENANCE_PARAMETERS',meta['positions_over_l']==list(spec.positions_over_l) and meta['mpi_ranks']==list(spec.mpi_ranks) and meta['flow_profile']==asdict(spec.flow) and meta['structure_parameters']==asdict(spec.structure) and meta['deltaT']==spec.delta_t and meta['endTime']==spec.end_time and meta['writeInterval']==spec.write_interval and meta['selected_initial_time']==spec.initial_state_time,'manifest/spec agree')
        check('GENERATION_STATUS',meta['generation_status'] in ('STATIC_VALIDATION_PENDING','PASS'),'not a failed generation')
        check('APP_PROVENANCE',bool(meta['app']['commit']) and meta['app']['branch']=='app/mvp-case-generator-v1' and bool(meta['app']['source_hashes']) and bool(meta['baseline_key_hashes']),'app identity and selected baseline hashes')
        xml=(root/'precice-config.xml').read_text(encoding='utf-8')
        xml_status=inspect_precice_xml(xml,manifest)
        check('XML_PARTICIPANTS',xml_status['fluid_participant_count']==n and xml_status['unique_participants'] and xml_status['structure_participant_count']==1,'parser/native inspector')
        expected=generate_precice_xml(manifest,time_window_s=spec.delta_t,max_time_s=spec.end_time-float(spec.initial_state_time),exchange_directory='../precice-sockets')
        check('XML_CONTRACT',normalized_xml(xml,False)==normalized_xml(expected,False),'data, meshes, maps, schemes, exchange paths and timing')
        check('XML_IDENTITY',digest((root/'precice-config.xml').read_bytes())==meta['precice_sha256'],'preCICE file hash')
        names=[row.fluid_participant for row in manifest.slices]
        check('PARTICIPANT_NAMES',names==[f'Fluid_{i:04d}' for i in range(n)] and manifest.structure_participant=='Structure_0000','production naming')
        cases=[p.name for p in root.iterdir() if p.is_dir() and p.name.startswith('slice')]
        check('FLUID_DIRECTORIES',sorted(cases)==sorted(row.openfoam_case_id for row in manifest.slices),'case dirs match participants, no old slice count')
        structure=root/'Structure_0000'
        for file in ('kernel_model.json','initial_state.json','structure_config.json'):
            check('STRUCTURE_CONFIGURATION',(structure/file).is_file(),file)
        model_raw=read_json(structure/'kernel_model.json')
        model=load_kernel(model_raw)
        model.validate(spec.delta_t)
        check('STRUCTURE_POSITIONS',model.slices==n and model.slice_positions_m==tuple(row.s_ref_m for row in manifest.slices),'native KernelModel Ns/positions')
        original_model=load_kernel(read_json(root/'baseline_kernel_model.json'))
        allowed_model=asdict(original_model)
        allowed_model['slices']=n
        allowed_model['slice_positions_m']=tuple(row.s_ref_m for row in manifest.slices)
        allowed_model['damping_alpha']=spec.structure.damping_alpha
        check('STRUCTURE_INHERITANCE',asdict(model)==allowed_model,'only slice count/positions and Rayleigh alpha may change; SHM1/physics retained')
        expected_struct=StructureParameters(model.diameter_m,model.length_m,model.explicit_EA_N,model.explicit_EI_Nm2,model.explicit_mass_per_length_kg_m,model.top_tension_N,model.damping_alpha,model.elements)
        check('STRUCTURE_PARAMETERS',spec.structure==expected_struct,'native SPX1 values')
        state=read_json(structure/'initial_state.json')
        check('STRUCTURE_INITIAL_STATE',set(state)=={'q','qdot','qddot'} and all(len(v)==model.ndof and all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in v) for v in state.values()),'native initial state dimensions')
        check('INITIAL_STATE_INHERITANCE',(structure/'initial_state.json').read_bytes()==(root/'baseline_initial_state.json').read_bytes(),'q state byte-identical')
        check('MODEL_BASELINE_IDENTITY',digest((root/'baseline_kernel_model.json').read_bytes())==meta['baseline_key_hashes'][descriptor['kernel_model']] and digest((root/'baseline_initial_state.json').read_bytes())==meta['baseline_key_hashes'][descriptor['structure_initial_state']],'snapshot identities')
        cfg=read_json(structure/'structure_config.json')
        check('STRUCTURE_REFERENCES',cfg['participant']=='Structure_0000' and cfg['kernel_model']=='kernel_model.json' and cfg['initial_state']=='initial_state.json' and cfg['slice_manifest']=='../slice_manifest.json' and cfg['precice_config']=='../precice-config.xml','references confined to generated case')
        launch=read_json(root/'launch_manifest.json')
        check('LAUNCH_BOUNDARY',launch['execution']=='MANUAL_ONLY' and launch['production_launch_ready'] is False and launch['structure']['command'] is None and meta['production_launch_ready'] is False,'no solver launcher; structural runner gap explicit')
        check('LAUNCH_COUNT',len(launch['fluid'])==n,'one descriptor per fluid')
        for i,(row,rank,velocity) in enumerate(zip(manifest.slices,spec.mpi_ranks,velocities)):
            case=root/row.openfoam_case_id
            for sub in ('system','constant',spec.initial_state_time):
                check('OPENFOAM_DIRECTORY',(case/sub).is_dir(),f'{row.openfoam_case_id}/{sub}')
            for mesh_file in ('points','faces','owner','neighbour','boundary'):
                check('BASELINE_MESH',(case/'constant/polyMesh'/mesh_file).is_file(),f'{row.openfoam_case_id}/constant/polyMesh/{mesh_file}')
            for field in descriptor['required_initial_fields']:
                check('INITIAL_FIELD',(case/spec.initial_state_time/field).is_file(),f'{row.openfoam_case_id}/{spec.initial_state_time}/{field}')
            control=FoamDict((case/'system/controlDict').read_bytes())
            check('CONTROL_NUMERICS',control.scalar('startFrom')=='startTime' and float(control.scalar('startTime'))==float(spec.initial_state_time) and float(control.scalar('deltaT'))==spec.delta_t and float(control.scalar('endTime'))==spec.end_time and float(control.scalar('writeInterval'))==spec.write_interval,'explicit time selection and user numerics')
            check('CONTROL_INHERITANCE',digest(control.edit(CONTROL_MASK))==meta['editable_config_inheritance']['controlDict'],'other solver settings unchanged')
            decomp=FoamDict((case/'system/decomposeParDict').read_bytes())
            check('MPI_DECOMPOSITION',int(decomp.scalar('numberOfSubdomains'))==rank and decomp.scalar('method')=='scotch','per-slice ranks')
            check('DECOMPOSITION_INHERITANCE',digest(decomp.edit({('numberOfSubdomains',):1}))==meta['editable_config_inheritance']['decomposeParDict'],'decomposition settings unchanged')
            pd=FoamDict((case/'system/preciceDict').read_bytes())
            check('ADAPTER_INTERFACE',pd.scalar('participant')==row.fluid_participant and pd.scalar('interfaces','Interface1','mesh')==row.fluid_mesh and pd.scalar('preciceConfig')=='../precice-config.xml','adapter participant/mesh/XML binding')
            check('ADAPTER_INHERITANCE',digest(pd.edit(PRECICE_MASK))==meta['editable_config_inheritance']['preciceDict'],'adapter FSI/scaling unchanged')
            vec=inlet_vector((case/spec.initial_state_time/'U').read_bytes(),descriptor['flow']['inlet_patch'])
            check('INLET_VELOCITY',all(math.isclose(a,velocity*b,abs_tol=1e-12) for a,b in zip(vec,descriptor['flow']['direction'])),f'{row.fluid_participant} U={velocity}')
            prefix,_=velocity_boundary((case/spec.initial_state_time/'U').read_bytes())
            check('INTERNAL_VELOCITY_INHERITANCE',prefix_identity(prefix)==meta['initial_U_prefix_identity'],'developed internal U preserved')
            for relative,identity in meta['preserved_config_hashes'].items():
                check('INHERITED_CONFIG',within((case/relative).resolve(),case) and (case/relative).is_file() and digest((case/relative).read_bytes())==identity,relative)
            desc=launch['fluid'][i]
            expected_command=['pimpleFoam'] if rank==1 else ['mpirun','-np',str(rank),'pimpleFoam','-parallel']
            check('MPI_LAUNCH_DESCRIPTOR',desc['participant']==row.fluid_participant and desc['working_directory']==row.openfoam_case_id and desc['mpi_ranks']==rank and desc['command']==expected_command,'manual MPI participant command')
            for p in (case/'system').rglob('*'):
                if p.is_file():
                    check('NO_OLD_ABSOLUTE_PATHS',not operational_absolute_paths(p.read_bytes()),str(p.relative_to(root)))
            time_dirs=[p.name for p in case.iterdir() if p.is_dir() and p.name[0].isdigit()]
            check('SELECTED_INITIAL_TIME_ONLY',time_dirs==[spec.initial_state_time],'no unselected restart/runtime times')
        for p in root.rglob('*'):
            check('NO_BASELINE_LINKS',not p.is_symlink(),str(p.relative_to(root)))
        result['status']='PASS'
    except Exception as exc:
        result['first_failure']=str(exc)
        if not checks or checks[-1]['status']!='FAIL':
            checks.append({'check':'PARSE_OR_CONTRACT','status':'FAIL','detail':str(exc)})
    if write_report and root.is_dir() and within(root,CASES_ROOT):
        (root/'generation_validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result
