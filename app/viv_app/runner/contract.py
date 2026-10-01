"""Strict manifest parsing and bounded prepared-input identity gates."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import os
from viv_app.generator.production_baseline import PROFILE,FIELDS,MESH_FIELDS,file_identity
from viv_app.utils.paths import CASES_ROOT,local_path,within
from .prepared_symlinks import (plain_path,input_tree,processor_inputs,qualified_uniform_symlink_identity)


def read(path):return json.loads(Path(path).read_text())
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)


@dataclass(frozen=True)
class ExecutionContract:
    root: Path
    launch: dict
    generation: dict
    baseline: dict

    @property
    def participants(self):return [self.launch['structure'],*self.launch['fluid']]
    @property
    def target_windows(self):return self.generation['max_time_windows']


def load_contract(path):
    root=local_path(path)
    require(within(root,CASES_ROOT) and root!=CASES_ROOT and root.is_dir(),'Run case must be inside APP workspace/cases')
    require(os.name=='posix','Production Run Manager V1 requires the qualified WSL/Linux environment')
    for relative in ('runtime','runtime/logs'):
        p=root/relative
        require(not p.is_symlink() and within(p.resolve(),root),'Runtime/log path must be inside this case')
    launch=read(root/'launch_manifest.json');g=read(root/'generation_manifest.json');d=read(root/'baseline_contract_snapshot.json')
    require(g['contract_profile']==d['contract_profile']==PROFILE,'Only qualified fixed N5 production profile is executable')
    require(g['generation_status']=='PASS' and g['slice_count']==5 and g['deltaT']==.0004 and g['mpi_ranks']==[4]*5,'Generation / fixed dt / N5 ranks contract failed')
    require(isinstance(g['max_time_windows'],int) and g['max_time_windows']>0 and math.isclose(g['coupled_duration_s'],g['max_time_windows']*.0004,abs_tol=1e-12),'Invalid coupling horizon')
    names=['Structure',*[f'Fluid-S{i}'for i in range(1,6)]]
    rows=[launch['structure'],*launch['fluid']]
    require(launch['schema']=='viv-app-production-launch-v1' and launch['expected_participant_count']==6 and launch['total_cfd_ranks']==20,'Manifest topology')
    require([r['participant']for r in rows]==names,'Manifest participant order / uniqueness')
    require(launch['startup_order']==['manual: decompose all five selected initial states',*names],'Qualified startup order')
    for i,row in enumerate(rows):
        require(isinstance(row['cwd'],str) and not Path(row['cwd']).is_absolute() and '..'not in Path(row['cwd']).parts,'Participant cwd must be case local')
        cwd=(root/row['cwd']).resolve();require(within(cwd,root) and cwd.is_dir(),'Missing / external participant cwd')
        cpus='20'if i==0 else f'{4*(i-1)}-{4*i-1}'
        require(row['cpu_set']==cpus and row['mpi_ranks']==(1 if i==0 else 4),'Qualified CPU / MPI topology changed')
        for field in ['command']+(['prepare_command']if i else []):
            require(isinstance(row[field],list) and bool(row[field]) and all(isinstance(v,str)and v and '\0'not in v for v in row[field]),'Command must be a nonempty argv array')
        require(row['environment']=={'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'},'Qualified thread environment changed')
    # Full argv/math identity is checked by existing production validation,
    # not reconstructed by the GUI or this structural parser.
    return ExecutionContract(root,launch,g,d)


def fresh_execution(contract):
    root=contract.root
    for p in [root/'precice-run',root/'runtime/attempts.jsonl',root/'runtime/accepted_windows.jsonl']:
        require(not p.exists(),f'CASE_ALREADY_EXECUTED_OR_STALE: {p}; restart is unsupported')
    require(not list((root/'runtime').glob('run_*')),'CASE_ALREADY_EXECUTED: runtime run record exists; no implicit restart')
    for row in contract.launch['fluid']:
        fluid=root/row['cwd']
        require(not (fluid/'precice-run').exists() and not (fluid/'postProcessing').exists(),'Stale Fluid runtime output')
        for p in (fluid/'runtime').rglob('*'):
            require(not p.is_file(),'Stale Fluid observer output; no restart')


def check_decomposition(contract):
    initial=contract.baseline['initial_time_default'];rows=[]
    for row in contract.launch['fluid']:
        fluid=contract.root/row['cwd'];processors=sorted(p.name for p in fluid.glob('processor*'))
        require(processors==[f'processor{r}'for r in range(4)],'Wrong processor count: '+row['participant'])
        for r in range(4):
            for relative in [*[f'{initial}/{f}'for f in FIELDS],*[f'constant/polyMesh/{f}'for f in MESH_FIELDS]]:
                p=fluid/f'processor{r}'/relative
                plain_path(contract.root,p)
                require(p.is_file() and not p.is_symlink(),'Missing prepared initial field / mesh: '+str(p))
        for p in processor_inputs(contract.root,fluid,initial):
            if p.is_symlink():
                qualified_uniform_symlink_identity(contract.root,contract.launch['fluid'],contract.baseline,p)
            else:
                plain_path(contract.root,p)
        rows.append({'participant':row['participant'],'processor_count':4,'initial_time':initial,'required_initial_fields':'PASS'})
    return rows


def prepared_identity(contract):
    """Hash small configs; bounded samples for new initial fields/mesh only."""
    root=contract.root;small={};large={};links={}
    for n in ['launch_manifest.json','generation_manifest.json','precice-config.xml','production_xml_template.xml',
              'simulation_spec.yaml','slice_manifest.json','baseline_contract_snapshot.json','Structure/initial_state.raw',
              'Structure/structure_config.json','Structure/compiled_kernel_model.json']:
        small[n]=digest(plain_path(root,root/n))
    for row in contract.launch['fluid']:
        fluid=root/row['cwd']
        for p in input_tree(root,fluid/'system'):
            plain_path(root,p)
            if p.is_file():
                require(not p.is_symlink() and p.stat().st_size<=2*1024*1024,'Unsupported configuration file')
                small[str(p.relative_to(root))]=digest(p)
        for p in processor_inputs(root,fluid,contract.baseline['initial_time_default']):
            if p.is_symlink():
                links[str(p.relative_to(root))]=qualified_uniform_symlink_identity(root,contract.launch['fluid'],contract.baseline,p)
            else:
                plain_path(root,p)
                if p.is_file():large[str(p.relative_to(root))]=file_identity(p)
    return {'configuration_sha256':small,'prepared_initial_bounded_identities':large,
            'qualified_uniform_symlinks':links}
