"""Read-only environment/config preflight. Never executes launch/prepare argv."""
from pathlib import Path
from datetime import datetime,timezone
import os
import shutil
import subprocess
from .baseline import read_json,digest
from .production_baseline import require
from .production_validation import validate_production_case
from .production_generator import foam_command
from viv_app.utils.paths import local_path


def production_preflight(path,progress=lambda percent,message:None,write_report=True):
    from .case_generator import write_json,app_identity
    root=local_path(path);checks=[];warnings=[]
    result={'status':'FAIL','production_launch_ready':False,'real_fsi_started':False,'checks':checks,
        'warnings':warnings,'first_failure':None,'time':datetime.now(timezone.utc).isoformat(),
        'scope':'SERIAL_INPUTS_AND_MANUAL_COMMANDS; DECOMPOSITION_NOT_EXECUTED'}
    def check(name,value,detail):
        checks.append({'check':name,'status':'PASS' if value else 'FAIL','detail':detail})
        require(value,name,detail)
    try:
        progress(5,'Static production contract and selected identity checks')
        static=validate_production_case(root,write_report)
        check('STATIC_VALIDATION',static['status']=='PASS',static['first_failure'] or 'all N5 contracts pass')
        d=read_json(root/'baseline_contract_snapshot.json');launch=read_json(root/'launch_manifest.json')
        check('OPENFOAM_ENVIRONMENT',Path(d['openfoam_environment']).is_file(),d['openfoam_environment'])
        # Only source the known environment and print its version; no solver run.
        probe=subprocess.run(['bash','-lc','viv_foam_env=$1; set --; source "$viv_foam_env" >/dev/null 2>&1 && printf "%s" "$WM_PROJECT_VERSION"',
                              'viv-env-check',d['openfoam_environment']],capture_output=True,text=True,timeout=20)
        check('OPENFOAM_VERSION',probe.returncode==0 and probe.stdout.strip().lstrip('v')=='2606',probe.stdout.strip())
        version=shutil.which('precice-version');validator=shutil.which('precice-config-validate')
        check('PRECICE_UTILITIES',bool(version and validator),'precice-version and precice-config-validate discoverable')
        p=subprocess.run([version],capture_output=True,text=True,timeout=15)
        check('PRECICE_VERSION',p.returncode==0 and p.stdout.split(';')[0].strip()==d['precice_version'],p.stdout.split(';')[0].strip())
        progress(60,'preCICE configuration utility; no participants')
        # preCICE utility validates configuration only, creates no Participant.
        p=subprocess.run([validator,str(root/'precice-config.xml')],cwd=root,capture_output=True,text=True,timeout=30)
        check('PRECICE_NATIVE_CONFIG_VALIDATION',p.returncode==0,(p.stdout+p.stderr)[-3000:])
        for name in d['identities']:
            if name.endswith('.so') or name==d['structure_executable']:
                file=Path(name)
                check('EXTERNAL_DEPENDENCY_IDENTITY',file.is_file() and digest(file.read_bytes())==d['identities'][name],name)
        check('STRUCTURE_EXECUTABLE',os.access(d['structure_executable'],os.X_OK),'external binary executable, never invoked by APP')
        for name in ('mpirun','taskset','bash','ldd'):
            check('COMMAND_RESOLVABLE',shutil.which(name) is not None,name)
        binaries=[Path(d['structure_executable']),Path(d['adapter_library'])]
        binaries += [Path(d['openfoam_bin'])/name for name in ('pimpleFoam','decomposePar')]
        binaries += [Path(name) for name in d['identities'] if name.endswith('.so') and name!=d['adapter_library']]
        for binary in binaries:
            check('BINARY_PRESENT',binary.is_file(),str(binary))
            # Dynamic linker listing; no participant executable main is run.
            command=foam_command(d['openfoam_environment'],['ldd',str(binary)])
            p=subprocess.run(command,capture_output=True,text=True,timeout=15)
            check('SHARED_LIBRARIES_RESOLVABLE',p.returncode==0 and 'not found' not in p.stdout+p.stderr,str(binary))
        allowed=os.sched_getaffinity(0)
        check('CPU_BINDINGS_AVAILABLE',set(range(21))<=allowed,'five disjoint four-rank CPU sets plus CPU20 for Structure')
        check('MPI_TOTAL',sum(x['mpi_ranks'] for x in launch['fluid'])==20 and launch['expected_participant_count']==6,'20 CFD ranks + one Structure')
        check('FRESH_COMMUNICATION_DIRECTORY',not (root/'precice-run').exists(),'shared exchange-directory=.. contains no prior communication state')
        check('OUTPUT_WRITABLE',os.access(root,os.W_OK),'case output writable')
        free=shutil.disk_usage(root).free;result['disk_free_bytes']=free
        if free<15_000_000_000:warnings.append('LOW_DISK_FREE_SPACE: less than 15 GB; user must budget actual run duration')
        warnings.append('MANUAL_DECOMPOSITION_REQUIRED: serial initial state only; use the five generated prepare commands before launch')
        warnings.append('EXTERNAL_SOLVER_DEPENDENCY: immutable Structure, adapter and observer libraries are referenced, not copied')
        warnings.append('PHYSICS_QUALIFICATION: only original NM12 short100 is qualified; new flow/duration is not run or physically validated')
        result.update(status='PASS',production_launch_ready=True,app=app_identity())
        progress(100,'Production preflight PASS; real FSI started = NO')
    except Exception as exc:
        result['first_failure']=str(exc)
    if write_report:
        write_json(root/'production_preflight.json',result)
        for name in ('launch_manifest.json','generation_manifest.json'):
            if (root/name).is_file():
                meta=read_json(root/name);meta['production_launch_ready']=result['production_launch_ready']
                if name=='generation_manifest.json' and result['status']=='PASS':meta['preflight_app_identity']=result['app']
                write_json(root/name,meta)
    return result
