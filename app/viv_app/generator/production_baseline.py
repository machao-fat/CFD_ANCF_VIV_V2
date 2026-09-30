"""Read-only, evidence-gated production import. No solver executable is invoked."""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import math
import re
from .baseline import read_json,digest,prefix_identity
from .foam_dict import FoamDict,inlet_vector,velocity_boundary
from .errors import GenerationError
from .production_xml import V2606ImplicitTopologyBuilder
from viv_app.models.simulation_spec import StructureParameters
from viv_app.utils.paths import local_path,APP_ROOT

PROFILE='v2606-n5-implicit-production-v1'
PROFILE_ROOT=APP_ROOT/'app/resources/baseline_profiles/v2606_n5'
POSITIONS=(.594,1.782,2.970,4.158,5.346)
STRUCTURE=StructureParameters(.028,13.12,7470000.,29.88,1.845,1175.,0.,32)
FIELDS=('U','U_0','p','phi','k','omega','nut','pointDisplacement')
MESH_FIELDS=('points','faces','owner','neighbour','boundary')
LABELS=('s0594','s1782','s2970','s4158','s5346')


def require(value,code,detail):
    if not value: raise GenerationError(code,detail)


def file_identity(path):
    """Bounded file identity; no historical runtime traversal/hash."""
    p=Path(path)
    with p.open('rb') as f:
        size=p.stat().st_size
        first=f.read(4096)
        f.seek(max(4096,size-4096))
        last=f.read(4096) if size>4096 else b''
    return {'size_bytes':size,'sample_sha256':digest(first+last),'scope':'first-and-last-4KiB'}


def selected_state(data):
    """Extract literal native CASE/Q record; never synthesize an equilibrium."""
    lines=data.splitlines(keepends=True)
    matches=[]
    for i,line in enumerate(lines):
        if line.startswith(b'CASE REF_NE32 32 7470000'):
            for row in lines[i+1:]:
                if row.startswith(b'CASE '): break
                if row.startswith(b'Q '):
                    values=row.split()[1:]
                    # Native Q line starts with DOF count.
                    require(values and int(values[0])==198 and len(values)==199,'INVALID_P1_STATE','198 Q coordinates required')
                    require(all(math.isfinite(float(x)) for x in values[1:]),'INVALID_P1_STATE','finite Q required')
                    matches.append(line+row)
                    break
    require(len(matches)==1,'INVALID_P1_STATE','unique P1_REF_NE32 CASE/Q required')
    return matches[0]


@dataclass
class ProductionBaseline:
    root:Path
    descriptor:dict
    fluids:tuple
    controls:FoamDict
    inlet_speed:float
    @property
    def fluid(self): return self.fluids[0]
    @property
    def structure(self): return STRUCTURE
    @property
    def model(self): return SimpleNamespace(length_m=STRUCTURE.length_m,elements=32)
    @property
    def times(self): return (self.descriptor['initial_time_default'],)
    @property
    def manifest(self):
        return SimpleNamespace(ns=5,active_start_m=0.,active_end_m=5.94,reconstruction_mode='PiecewiseLinearDistributed')
    def validate_time(self,time):
        require(time==self.times[0],'PRODUCTION_INITIAL_STATE_LOCKED',str(time))
    def key_hashes(self,time):
        self.validate_time(time)
        result={str(self.root/'app_baseline.json'):digest((self.root/'app_baseline.json').read_bytes())}
        for name in self.descriptor['identities']:
            p=Path(name)
            require(p.is_file() and not p.is_symlink(),'MISSING_PRODUCTION_ARTIFACT',str(p))
            require(p.stat().st_size<=8*1024*1024,'OVERSIZED_PRODUCTION_IDENTITY',str(p))
            result[name]=digest(p.read_bytes())
        return result
    def initial_identity(self):
        result={}
        for fluid in self.fluids:
            # Only configuration mesh and explicitly selected initial state.
            for folder in (fluid/'constant/polyMesh',fluid/self.times[0]):
                for p in sorted(folder.rglob('*')):
                    if p.is_file():
                        require(not p.is_symlink(),'UNSUPPORTED_BASELINE_SYMLINK',str(p))
                        result[str(p)]=file_identity(p)
        return result


def validate_production_spec(spec):
    spec.validate()
    require(len(spec.positions_over_l)==5,'PRODUCTION_N_LOCKED','N5 only')
    require(all(math.isclose(x*STRUCTURE.length_m,y,abs_tol=1e-12) for x,y in zip(spec.positions_over_l,POSITIONS)),
            'PRODUCTION_POSITIONS_LOCKED','positions are compiled into Structure')
    require(spec.structure==STRUCTURE,'PRODUCTION_STRUCTURE_LOCKED','P1_REF_NE32 physical parameters must remain identical')
    require(spec.mpi_ranks==(4,)*5,'PRODUCTION_MPI_LOCKED','5 x 4 ranks required')
    require(spec.delta_t==.0004,'PRODUCTION_DELTA_T_LOCKED','compiled dt 0.0004')
    require(spec.initial_state_time=='29.9999999999834372','PRODUCTION_INITIAL_STATE_LOCKED','fresh frozen30 release only')
    windows=(spec.end_time-float(spec.initial_state_time))/.0004
    require(windows>=1 and math.isclose(windows,round(windows),abs_tol=1e-6,rel_tol=0),
            'INVALID_COUPLED_DURATION','endTime minus initial time must be an integral number of 0.0004 s windows')
    require(float(spec.write_interval).is_integer(),'INVALID_WRITE_INTERVAL','timeStep interval must be an integer')
    return round(windows)


def inspect_production_baseline(path):
    root=local_path(path)
    d=read_json(root/'app_baseline.json')
    # Current V1 has one enrolled evidence lineage; no arbitrary USER_VERIFIED shortcut.
    enrolled=read_json(PROFILE_ROOT/'app_baseline.json')
    require(d==enrolled,'UNENROLLED_PRODUCTION_PROFILE','descriptor must match the audited NM12 enrollment')
    require(d['contract_profile']==PROFILE and d['slice_positions_m']==list(POSITIONS) and d['structure_parameters']==STRUCTURE.__dict__,
            'INVALID_PRODUCTION_CONTRACT','compiled model/profile differ')
    b=ProductionBaseline(root,d,tuple(Path(p) for p in d['fluid_cases']),None,0.)
    hashes=b.key_hashes(d['initial_time_default'])
    require(all(hashes[k]==v for k,v in d['identities'].items()),'PRODUCTION_IDENTITY_MISMATCH','selected source/config/binary identity drift')
    evidence=read_json(Path(d['qualification_record']))
    require(evidence['classification']==d['qualification_classification'] and evidence['accepted_windows']==100 and
            evidence['forced_acceptance']==0 and all(evidence['gates'].values()) and all(x==0 for x in evidence['participant_exits'].values()),
            'PRODUCTION_QUALIFICATION_MISSING','NM12 short100 PASS gates/exit codes required')
    source=read_json(Path(d['source_root'])/'identity/source_identity.json')
    software=read_json(Path(d['source_root'])/'identity/software_identity.json')
    mapping=read_json(Path(d['source_root'])/'identity/mapping_contract.json')
    require(hashes[d['structure_executable']]==source['structure_binary_sha256'] and
            hashes[d['structure_source']]==source['structure_source_sha256'] and
            hashes[d['adapter_library']]==source['official_adapter_sha256']==software['adapter_sha256'],
            'PRODUCTION_RECORDED_IDENTITY_MISMATCH','artifact identities must match successful evidence, not only enrollment')
    require(software['preCICE']=='3.4.1' and software['OpenFOAM']=='OpenFOAM.com v2606' and
            software['dt_s']==.0004 and software['fluid_ranks_each']==4 and
            mapping['mapping_mode']=='PiecewiseLinearDistributed' and mapping['endpoint_policy']=='NearestConstant' and
            mapping['active_region_m']==[0,5.94] and mapping['unit_span_m']==.028 and
            [r['s_ref_m'] for r in mapping['slices']]==list(POSITIONS) and mapping['tributary_multiplier_in_distributed_path'] is False,
            'PRODUCTION_RECORDED_CONTRACT_MISMATCH','successful software/mapping record differs')
    V2606ImplicitTopologyBuilder(Path(d['xml_template']).read_bytes())
    selected_state(Path(d['structure_state']).read_bytes())
    b.controls=FoamDict((b.fluid/'system/controlDict').read_bytes())
    for i,fluid in enumerate(b.fluids,1):
        for field in FIELDS:
            require((fluid/b.times[0]/field).is_file(),'MISSING_INITIAL_FIELD',str(fluid/b.times[0]/field))
        for name in MESH_FIELDS:
            require((fluid/'constant/polyMesh'/name).is_file(),'MISSING_MESH',str(fluid/name))
        pd=FoamDict((fluid/'system/preciceDict').read_bytes())
        require(pd.scalar('participant')==f'Fluid-S{i}' and pd.scalar('interfaces','Interface1','mesh')==f'Fluid-Mesh-S{i}' and
                pd.get('interfaces','Interface1','readData')==(b'(',f'Displacement-S{i}'.encode(),b')') and
                pd.get('interfaces','Interface1','writeData')==(b'(',f'Force-S{i}'.encode(),b')'),
                'PRODUCTION_PARTICIPANT_MISMATCH',str(fluid))
        inlet_vector((fluid/b.times[0]/'U').read_bytes(),'inlet')
        control=FoamDict((fluid/'system/controlDict').read_bytes())
        require(control.scalar('writeControl')=='timeStep' and float(control.scalar('deltaT'))==.0004 and
                control.scalar('adjustTimeStep')=='false','UNSUPPORTED_PRODUCTION_NUMERICS',str(fluid))
        dec=FoamDict((fluid/'system/decomposeParDict').read_bytes())
        require(dec.scalar('method')=='scotch' and int(dec.scalar('numberOfSubdomains'))==4,'UNSUPPORTED_MPI_CONTRACT',str(fluid))
    b.inlet_speed=inlet_vector((b.fluid/b.times[0]/'U').read_bytes(),'inlet')[0]
    return b
