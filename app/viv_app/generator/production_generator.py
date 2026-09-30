"""N5 configuration generation only; no participant/decomposition execution."""
from pathlib import Path
from datetime import datetime,timezone
import json
import shlex
import yaml
from .production_baseline import (inspect_production_baseline,validate_production_spec,
    selected_state,POSITIONS,LABELS,require)
from .production_xml import V2606ImplicitTopologyBuilder
from .foam_dict import FoamDict,set_inlet,velocity_boundary,add_entry
from .fluid_generator import copy_configuration
from .baseline import digest
from .errors import GenerationError
from viv_app.utils.paths import local_path


def fluid_control(source,spec,velocity):
    changes={('startFrom',):'startTime',('startTime',):spec.initial_state_time,
             ('endTime',):f'{spec.end_time:.17g}',('writeInterval',):str(int(spec.write_interval)),
             ('purgeWrite',):str(spec.purge_write),
             ('functions','nm84InputObserver','outputDir'):'"runtime/input_observer"',
             ('functions','nm84ForceObserver','outputDir'):'"runtime/force_observer"',
             ('functions','cylinderForceCoeffs','magUInf'):f'{velocity:.17g}'}
    output=FoamDict(source).edit(changes)
    # Zero inflow has no finite normalization for coefficients; disable this
    # diagnostic, preserve native integrated forces and coupling configuration.
    if velocity==0:
        output=add_entry(output,('functions','cylinderForceCoeffs'),'enabled','false')
    return output


def fluid_precice(source,i):
    return FoamDict(source).edit({('preciceConfig',):'"../precice-config.xml"',
        ('participant',):f'Fluid-S{i}',('interfaces','Interface1','mesh'):f'Fluid-Mesh-S{i}',
        ('interfaces','Interface1','readData'):f'(Displacement-S{i})',
        ('interfaces','Interface1','writeData'):f'(Force-S{i})'})


def initial_velocity(source,velocity):
    data=set_inlet(source,'inlet',(velocity,0.,0.))
    prefix,boundary=velocity_boundary(data)
    wall=boundary.scalar('boundaryField','cylinder','type')
    require(wall in ('fixedValue','movingWallVelocity'),'UNSUPPORTED_MOVING_WALL_CONFIGURATION',wall)
    return prefix+boundary.edit({('boundaryField','cylinder','type'):'movingWallVelocity'})


def model_witness(d):
    return {'role':'OBSERVATIONAL_COMPILED_MODEL_WITNESS_NOT_SOLVER_INPUT',
        'source':d['structure_source'],'source_sha256':d['identities'][d['structure_source']],
        'slice_count':5,'slice_positions_m':list(POSITIONS),'parameters':d['structure_parameters'],
        'mapping':{'mode':'PiecewiseLinearDistributed','endpoint':'NearestConstant','active_region_m':[0.,5.94],
                   'unit_span_m':.028,'scaling_owner':'external Structure distributed_force_mapping.cpp; APP applies no scaling'},
        'SHM1':{'region_m':[0.,13.12],'added_mass_kg_m':[.616,.616,0.],'linear_damping_Ns_m2':[0.,0.,0.]},
        'dt_s':.0004,'nodes':33,'DOFs':198,'initial_state':'P1_REF_NE32','initial_velocity':'binary zero initialization',
        'initial_acceleration':'binary zero initialization','base_load':'binary static_base_load(q0)'}


def slice_manifest(spec):
    return {'schema':'viv-app-fixed-n5-production-manifest-v1','role':'MIRROR_OF_COMPILED_STRUCTURE_CONTRACT',
        'case_name':spec.case_name,'structure_participant':'Structure','active_region_m':[0.,5.94],
        'mapping':'PiecewiseLinearDistributed','endpoint':'NearestConstant','unit_span_m':.028,
        'slices':[{'slice_id':f'S{i}','participant':f'Fluid-S{i}','case_path':f'fluid_{label}',
            's_ref_m':position,'s_over_l':spec.positions_over_l[i-1],'U_i':spec.flow.velocity(spec.positions_over_l[i-1]),
            'mpi_ranks':4,'fluid_mesh':f'Fluid-Mesh-S{i}','structure_mesh':f'Solid-S{i}',
            'read_data':f'Displacement-S{i}','write_data':f'Force-S{i}'}
            for i,(label,position) in enumerate(zip(LABELS,POSITIONS),1)]}


def foam_command(environment,args):
    # Argument vector passed through positional shell args: no path interpolation.
    return ['bash','-lc','viv_foam_env=$1; shift; viv_foam_args=("$@"); set --; source "$viv_foam_env" >/dev/null 2>&1 && exec "${viv_foam_args[@]}"','viv-openfoam',environment,*map(str,args)]


def launch_manifest(spec,d):
    threads={'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    fluids=[]
    for i,label in enumerate(LABELS):
        cpus=f'{4*i}-{4*i+3}'
        fluids.append({'participant':f'Fluid-S{i+1}','case_path':f'fluid_{label}','cwd':f'fluid_{label}',
            'mpi_ranks':4,'cpu_set':cpus,'environment':threads,
            'prepare_command':foam_command(d['openfoam_environment'],[d['openfoam_bin']+'/decomposePar','-time',spec.initial_state_time,'-case','.']),
            'command':foam_command(d['openfoam_environment'],['mpirun','--mca','hwloc_base_cpu_list',cpus,
                '--use-hwthread-cpus','--bind-to','hwthread','-np','4',d['openfoam_bin']+'/pimpleFoam','-parallel','-case','.']),
            'log_path':f'runtime/fluid_{label}.log'})
    return {'schema':'viv-app-production-launch-v1','execution':'MANUAL_ONLY','real_fsi_started':False,
        'production_launch_ready':False,'readiness_scope':'INPUTS_AND_MANUAL_COMMANDS_VALIDATED_DECOMPOSITION_NOT_EXECUTED',
        'openfoam_environment_source_command':['source',d['openfoam_environment']],
        'precice_config_path':'precice-config.xml','expected_participant_count':6,'total_cfd_ranks':20,
        'startup_order':['manual: decompose all five selected initial states','Structure',*[f'Fluid-S{i}' for i in range(1,6)]],
        'fluid':fluids,'structure':{'participant':'Structure','cwd':'Structure','mpi_ranks':1,'cpu_set':'20',
            'environment':threads,'dependency':'EXTERNAL_SOLVER_DEPENDENCY','executable':d['structure_executable'],
            'config':'Structure/structure_config.json','config_role':'LAUNCH_DESCRIPTOR_NOT_PHYSICS_INPUT',
            'state':'Structure/initial_state.raw','log_path':'runtime/structure.log',
            'command':['taskset','-c','20',d['structure_executable'],'../precice-config.xml','initial_state.raw',
                '../runtime/attempts.jsonl','../runtime/accepted_windows.jsonl','../runtime/state_attempt_',*d['structure_mesh_xy']]}}


def write_manual_instructions(root,final,launch):
    lines=['# Manual production commands','',
        'APP did not execute any of these commands. Review the generated case first.',
        'Preflight validates serial inputs and command availability. Run all five decomposition commands before starting participants.',
        'Use separate terminals for Structure and each Fluid; start Structure first, then the five Fluids. No automatic launcher is included.',
        'Commands below target the final case directory. Logs are case-local.','']
    for row in launch['fluid']:
        lines += [f"## Prepare {row['participant']}",'```bash',f"cd {shlex.quote(str(final/row['cwd']))}",shlex.join(row['prepare_command']),'```','']
    for row in [launch['structure'],*launch['fluid']]:
        env=['env',*[f'{k}={v}' for k,v in row['environment'].items()]]
        lines += [f"## Start {row['participant']} (manual only)",'```bash',f"cd {shlex.quote(str(final/row['cwd']))}",
                  shlex.join(env+row['command'])+' > '+shlex.quote(str(final/row['log_path']))+' 2>&1','```','']
    (root/'MANUAL_LAUNCH.md').write_text('\n'.join(lines),encoding='utf-8')


def generate_production_case(spec,progress=lambda percent,message:None):
    from .case_generator import write_json,app_identity,publish_no_replace
    from .production_validation import validate_production_case
    windows=validate_production_spec(spec)
    output=local_path(spec.output_root);final=output/spec.case_name
    require(not final.exists() and not final.is_symlink(),'TARGET_CASE_ALREADY_EXISTS',str(final))
    progress(4,'Importing qualified NM12 baseline (read only)')
    baseline=inspect_production_baseline(spec.baseline_path);d=baseline.descriptor
    baseline.validate_time(spec.initial_state_time)
    key_before=baseline.key_hashes(spec.initial_state_time)
    initial_before=baseline.initial_identity()
    output.mkdir(parents=True,exist_ok=True)
    lock=output/f'.{spec.case_name}.generation-lock'
    try: lock.mkdir()
    except FileExistsError as exc: raise GenerationError('TARGET_CASE_GENERATION_IN_PROGRESS',str(lock)) from exc
    stage=output/f'.{spec.case_name}.staging'
    created=False
    try:
        require(not stage.exists() and not stage.is_symlink(),'TARGET_CASE_STAGING_ALREADY_EXISTS',str(stage))
        require(not final.exists(),'TARGET_CASE_ALREADY_EXISTS',str(final))
        stage.mkdir();created=True
        for i,(source,label,x) in enumerate(zip(baseline.fluids,LABELS,spec.positions_over_l),1):
            progress(10+10*i,f'Copying Fluid-S{i} configuration and selected initial state')
            target=stage/f'fluid_{label}';copy_tree=copy_configuration(source,target)
            copy_tree(source/spec.initial_state_time,target/spec.initial_state_time)
            velocity=spec.flow.velocity(x)
            (target/'system/controlDict').write_bytes(fluid_control((source/'system/controlDict').read_bytes(),spec,velocity))
            (target/'system/preciceDict').write_bytes(fluid_precice((source/'system/preciceDict').read_bytes(),i))
            (target/spec.initial_state_time/'U').write_bytes(initial_velocity((source/spec.initial_state_time/'U').read_bytes(),velocity))
            for folder in ('runtime/input_observer','runtime/force_observer'):(target/folder).mkdir(parents=True)
        progress(72,'Preserving implicit XML and external Structure command')
        template=Path(d['xml_template']).read_bytes()
        xml=V2606ImplicitTopologyBuilder(template).build(windows)
        (stage/'precice-config.xml').write_bytes(xml)
        (stage/'production_xml_template.xml').write_bytes(template)
        structure=stage/'Structure';structure.mkdir()
        state=selected_state(Path(d['structure_state']).read_bytes())
        (structure/'initial_state.raw').write_bytes(state)
        write_json(structure/'compiled_kernel_model.json',model_witness(d))
        write_json(structure/'structure_config.json',{'participant':'Structure','slice_count':5,
            'slice_positions_m':list(POSITIONS),'precice_config':'../precice-config.xml','initial_state':'initial_state.raw',
            'slice_manifest':'../slice_manifest.json','compiled_model':'compiled_kernel_model.json',
            'executable':d['structure_executable'],'physics_input_role':'NONE_COMPILED_MODEL_IS_AUTHORITATIVE'})
        write_json(stage/'slice_manifest.json',slice_manifest(spec))
        launch=launch_manifest(spec,d);write_json(stage/'launch_manifest.json',launch)
        (stage/'runtime').mkdir()
        write_manual_instructions(stage,final,launch)
        (stage/'simulation_spec.yaml').write_text(yaml.safe_dump(spec.to_dict(),sort_keys=False),encoding='utf-8')
        write_json(stage/'baseline_contract_snapshot.json',d)
        write_json(stage/'generation_manifest.json',{
            'schema':'viv-app-production-generation-v1','case_name':spec.case_name,'contract_profile':d['contract_profile'],
            'generation_time':datetime.now(timezone.utc).isoformat(),'app':app_identity(),'baseline_path':str(baseline.root),
            'baseline_key_hashes':key_before,'baseline_initial_sample_identities':initial_before,
            'baseline_evidence_status':d['evidence_status'],'source_qualification':d['qualification_classification'],
            'baseline_immutability':'selected key SHA256 and bounded selected initial/mesh identities verified before/after',
            'slice_count':5,'slice_positions_m':list(POSITIONS),'U_i':[spec.flow.velocity(x) for x in spec.positions_over_l],
            'flow_profile':spec.to_dict()['flow'],'structure_parameters':spec.to_dict()['structure'],
            'deltaT':spec.delta_t,'endTime':spec.end_time,'coupled_duration_s':windows*.0004,'max_time_windows':windows,
            'writeInterval':spec.write_interval,'purgeWrite':spec.purge_write,'mpi_ranks':list(spec.mpi_ranks),
            'precice_sha256':digest(xml),'initial_structure_selected_record_sha256':digest(state),
            'external_dependency_status':'EXTERNAL_SOLVER_DEPENDENCY','generation_status':'STATIC_VALIDATION_PENDING',
            'production_launch_ready':False,'real_fsi_started':False,'manual_decomposition_required':True})
        progress(85,'Production static validation; no solver execution')
        result=validate_production_case(stage)
        require(result['status']=='PASS','STATIC_VALIDATION_FAILED',result['first_failure'])
        require(baseline.key_hashes(spec.initial_state_time)==key_before and baseline.initial_identity()==initial_before,
                'BASELINE_CHANGED_DURING_GENERATION','selected baseline identities changed')
        meta=json.loads((stage/'generation_manifest.json').read_text());meta['generation_status']='PASS'
        write_json(stage/'generation_manifest.json',meta)
        publish_no_replace(stage,final)
        progress(100,'Production N5 case generated; no FSI started')
        return final
    except Exception as exc:
        if created and stage.exists():write_json(stage/'generation_failure.json',{'status':'FAIL','first_failure':str(exc)})
        raise
    finally:lock.rmdir()
