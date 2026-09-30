from pathlib import Path
import json
import os
import subprocess
import base64
import shutil
from datetime import datetime,timezone
import yaml
from .baseline import inspect_baseline,digest,prefix_identity
from .foam_dict import FoamDict,velocity_boundary
from .errors import GenerationError
from .precice_generator import build_manifest,write_xml
from .structure_generator import write_structure,structure_payload
from .fluid_generator import write_fluid,RULES_PATH
from .native import generate_openfoam_launch_plan
from viv_app.utils.paths import local_path,APP_ROOT


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def app_identity():
    def git(*args):
        return subprocess.check_output(['git','-C',str(APP_ROOT),*args],text=True,timeout=10).strip()
    # Git only, never a solver. Source hashes identify uncommitted APP versions.
    return {'commit':git('rev-parse','HEAD'),'branch':git('branch','--show-current'),
            'dirty':bool(git('status','--porcelain','--','app','APP_BASELINE_AUDIT.md')),
            'source_hashes':{str(p.relative_to(APP_ROOT)):digest(p.read_bytes())
                             for p in sorted((APP_ROOT/'app/viv_app').rglob('*'))
                             if p.suffix in ('.py','.qss') and p.is_file()}}


def generate_case(spec,progress=lambda percent,message:None):
    from .validation import validate_case,CONTROL_MASK,PRECICE_MASK
    progress(2,'Validating specification')
    spec.validate()
    output=local_path(spec.output_root)
    final=output/spec.case_name
    if final.exists() or final.is_symlink():
        raise GenerationError('TARGET_CASE_ALREADY_EXISTS',str(final))
    progress(5,'Auditing baseline (read only)')
    baseline=inspect_baseline(spec.baseline_path)
    baseline.validate_time(spec.initial_state_time)
    manifest=build_manifest(spec,baseline)
    structure_payload(spec,baseline,manifest)  # Fail before copying.
    if baseline.controls.scalar('writeControl')=='timeStep' and not float(spec.write_interval).is_integer():
        raise GenerationError('INVALID_NUMERICS','writeInterval must be an integer for timeStep')
    initial_hashes=baseline.key_hashes(spec.initial_state_time)
    velocities=[spec.flow.velocity(x) for x in spec.positions_over_l]
    output.mkdir(parents=True,exist_ok=True)
    # A concurrent second APP process cannot regenerate/publish this target.
    lock=output/f'.{spec.case_name}.generation-lock'
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise GenerationError('TARGET_CASE_GENERATION_IN_PROGRESS',str(lock)) from exc
    stage=output/f'.{spec.case_name}.staging'
    stage_created=False
    try:
        if final.exists() or final.is_symlink():
            raise GenerationError('TARGET_CASE_ALREADY_EXISTS',str(final))
        if stage.exists() or stage.is_symlink():
            raise GenerationError('TARGET_CASE_STAGING_ALREADY_EXISTS',f'{stage}; failed staging retained, no automatic regenerate')
        stage.mkdir()
        stage_created=True
        for i,(row,rank,velocity) in enumerate(zip(manifest.slices,spec.mpi_ranks,velocities)):
            progress(10+int(60*i/manifest.ns),f'Copying {row.fluid_participant}')
            write_fluid(stage,spec,baseline,row,rank,velocity)
        progress(73,'Writing native structure and preCICE configuration')
        write_json(stage/'slice_manifest.json',manifest.to_dict())
        model=write_structure(stage,spec,baseline,manifest)
        xml=write_xml(stage,spec,manifest)
        (stage/'simulation_spec.yaml').write_text(yaml.safe_dump(spec.to_dict(),sort_keys=False),encoding='utf-8')
        # Snapshot for independent validation; only relative operational paths.
        write_json(stage/'baseline_contract_snapshot.json',baseline.descriptor)
        (stage/'baseline_kernel_model.json').write_bytes(baseline.relative(baseline.descriptor['kernel_model']).read_bytes())
        (stage/'baseline_initial_state.json').write_bytes(baseline.relative(baseline.descriptor['structure_initial_state']).read_bytes())
        (stage/'baseline_slice_manifest.json').write_bytes(baseline.relative(baseline.descriptor['slice_manifest']).read_bytes())
        launch=[]
        # Reuse native descriptors; output_root='.' keeps working dirs portable.
        for desc,rank in zip(generate_openfoam_launch_plan(manifest,template_source='baseline-provenance-only',output_root='.'),spec.mpi_ranks):
            row=desc.to_dict()
            row['command']=['pimpleFoam'] if rank==1 else ['mpirun','-np',str(rank),'pimpleFoam','-parallel']
            row['prepare_command']=['decomposePar','-force'] if rank>1 else []
            row['mpi_ranks']=rank
            launch.append(row)
        write_json(stage/'launch_manifest.json',{
            'schema':'viv-app-launch-descriptors-v1','execution':'MANUAL_ONLY',
            'production_launch_ready':False,'reason':'origin/main generic structural runner not wired; review required',
            'working_directory_rule':'relative to case root; all participants must run from their own directory',
            'fluid':launch,'structure':{'participant':'Structure_0000','working_directory':'Structure_0000',
                                       'config':'structure_config.json','command':None,'mpi_ranks':1,
                                       'status':'NOT_YET_WIRED_IN_ORIGIN_MAIN'},
        })
        preserved={}
        # Byte identity from copy, not full hashing of huge meshes/fields.
        # Small selected dictionaries are hashed for later independent tamper checks.
        excluded={'controlDict','preciceDict','decomposeParDict'}
        for p in (baseline.fluid/'system').rglob('*'):
            if p.is_file() and p.name not in excluded and p.stat().st_size<=2*1024*1024:
                preserved[str(p.relative_to(baseline.fluid))]=digest(p.read_bytes())
        write_json(stage/'generation_manifest.json',{
            'schema':'viv-app-generation-v1','case_name':spec.case_name,
            'generation_time':datetime.now(timezone.utc).isoformat(),
            'app':app_identity(),'baseline_path':str(baseline.root),'baseline_key_hashes':initial_hashes,
            'baseline_evidence_status':baseline.descriptor['evidence_status'],
            'contract_profile':baseline.descriptor['contract_profile'],
            'baseline_immutability':'key-config-hashes-verified; generator opens baseline read-only',
            'copy_rules_sha256':digest(RULES_PATH.read_bytes()),'selected_initial_time':spec.initial_state_time,
            'slice_count':manifest.ns,'slice_positions_m':[x.s_ref_m for x in manifest.slices],
            'positions_over_l':list(spec.positions_over_l),'flow_profile':spec.to_dict()['flow'],
            'U_i':velocities,'structure_parameters':spec.to_dict()['structure'],
            'deltaT':spec.delta_t,'endTime':spec.end_time,'writeInterval':spec.write_interval,
            'mpi_ranks':list(spec.mpi_ranks),'precice_sha256':digest((stage/'precice-config.xml').read_bytes()),
            'preserved_config_hashes':preserved,
            'editable_config_inheritance':{
                'controlDict':digest(baseline.controls.edit(CONTROL_MASK)),
                'preciceDict':digest(FoamDict((baseline.fluid/'system/preciceDict').read_bytes()).edit(PRECICE_MASK)),
                'decomposeParDict':digest(FoamDict((baseline.fluid/'system/decomposeParDict').read_bytes()).edit({('numberOfSubdomains',):1})),
            },
            'initial_U_prefix_identity':prefix_identity(velocity_boundary((baseline.fluid/spec.initial_state_time/'U').read_bytes())[0]),
            'generation_status':'STATIC_VALIDATION_PENDING',
            'production_launch_ready':False,
        })
        progress(85,'Static validation; no solver will start')
        result=validate_case(stage,write_report=True)
        if result['status']!='PASS':
            raise GenerationError('STATIC_VALIDATION_FAILED',result['first_failure'])
        if baseline.key_hashes(spec.initial_state_time)!=initial_hashes:
            raise GenerationError('BASELINE_CHANGED_DURING_GENERATION','key configuration hashes changed')
        data=json.loads((stage/'generation_manifest.json').read_text(encoding='utf-8'))
        data['generation_status']='PASS'
        write_json(stage/'generation_manifest.json',data)
        if final.exists() or final.is_symlink():
            raise GenerationError('TARGET_CASE_ALREADY_EXISTS',str(final))
        # Same-filesystem directory rename; completed staging becomes visible at once.
        # Refuse a raced existing target even when empty (Linux rename would replace it).
        publish_no_replace(stage,final)
        progress(100,'CASE GENERATION PASS — configuration only')
        return final
    except Exception as exc:
        # Keep reviewable failure evidence in the SAME staging folder. Never
        # retry automatically in a new folder; never delete a user's target.
        if stage_created and stage.exists():
            write_json(stage/'generation_failure.json',{'status':'FAIL','first_failure':str(exc)})
        raise
    finally:
        lock.rmdir()


def publish_no_replace(stage,final):
    if os.name=='posix':
        import ctypes
        lib=ctypes.CDLL(None,use_errno=True)
        # renameat2(RENAME_NOREPLACE), Linux/WSL; fail closed if unavailable.
        func=getattr(lib,'renameat2',None)
        if func is None:
            raise GenerationError('ATOMIC_PUBLISH_UNSUPPORTED','renameat2 unavailable')
        func.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        if func(-100,os.fsencode(stage),-100,os.fsencode(final),1)!=0:
            error=ctypes.get_errno()
            if error==17:
                raise GenerationError('TARGET_CASE_ALREADY_EXISTS',str(final))
            if error in (22,38,95) and str(final).startswith('/mnt/'):
                return publish_drvfs_no_replace(stage,final)
            raise OSError(error,os.strerror(error),str(final))
    else:
        # Windows rename refuses an existing destination.
        stage.rename(final)


def publish_drvfs_no_replace(stage,final):
    """DrvFS lacks renameat2 flags. .NET Directory.Move never replaces a target.

    Paths are passed as single-quoted literals in a UTF-16 encoded command;
    no shell interpolation, no user-supplied executable or launcher command.
    """
    powershell=shutil.which('powershell.exe')
    converter=shutil.which('wslpath')
    if not powershell or not converter:
        raise GenerationError('ATOMIC_PUBLISH_UNSUPPORTED','DrvFS requires existing Windows PowerShell/wslpath interop')
    windows_paths=[subprocess.check_output([converter,'-w',str(p)],text=True,timeout=10).strip() for p in (stage,final)]
    literals=["'"+p.replace("'","''")+"'" for p in windows_paths]
    command="$ErrorActionPreference='Stop'; try { [System.IO.Directory]::Move("+','.join(literals)+"); } catch { Write-Error $_; exit 1 }"
    encoded=base64.b64encode(command.encode('utf-16le')).decode('ascii')
    result=subprocess.run([powershell,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=30)
    if result.returncode:
        if final.exists() or final.is_symlink():
            raise GenerationError('TARGET_CASE_ALREADY_EXISTS',str(final))
        raise GenerationError('ATOMIC_PUBLISH_FAILED','Windows Directory.Move failed; staging retained')
