from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import re
from .errors import GenerationError, blocked
from .foam_dict import FoamDict, inlet_vector, velocity_boundary
from .native import load_manifest, load_kernel, generate_precice_xml
from viv_app.models.simulation_spec import StructureParameters
from viv_app.utils.paths import local_path, within, APP_ROOT
import xml.etree.ElementTree as ET

PROFILE = 'arbitrary-n-live-explicit-v1'
REQUIRED_DESCRIPTOR = {
    'schema', 'contract_profile', 'evidence_status', 'fluid_case', 'slice_manifest',
    'kernel_model', 'structure_initial_state', 'flow', 'required_initial_fields',
    'initial_time_default', 'time_window_equals_delta_t', 'naming',
}
NAMING = {
    'structure_participant': 'Structure_0000',
    'fluid_participant_pattern': 'Fluid_{index:04d}',
    'fluid_mesh_pattern': 'Fluid-Mesh-{slice_id}',
    'structure_mesh_pattern': 'Structure-Mesh-{slice_id}',
    'case_pattern': 'slice{index:04d}',
}


def read_json(path):
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f'nonfinite JSON: {v}')))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prefix_identity(data):
    # Bounded selected-field identity, no full SHA of a large developed field.
    sample=data if len(data)<=8192 else data[:4096]+data[-4096:]
    return {'size_bytes':len(data),'sample_sha256':digest(sample),
            'scope':'full-prefix-if-small-otherwise-first-and-last-4KiB'}


def normalized_xml(text, ignore_socket_path=True):
    root = ET.fromstring(text)
    def node_value(node):
        attrs = dict(node.attrib)
        if ignore_socket_path and node.tag.endswith('}sockets'):
            attrs['exchange-directory'] = '<relocated>'
        return (node.tag, tuple(sorted(attrs.items())), tuple(node_value(child) for child in node))
    return node_value(root)


@dataclass
class Baseline:
    root: Path
    descriptor: dict
    fluid: Path
    manifest: object
    model_raw: dict
    model: object
    initial_state: dict
    times: tuple[str, ...]
    controls: FoamDict
    inlet_speed: float

    def relative(self, value):
        p = Path(value)
        if p.is_absolute() or re.match(r'^[A-Za-z]:',str(value)) or '..' in p.parts:
            blocked(f'app_baseline.json: reference must be local relative path: {value}')
        candidate = self.root / p
        if not within(candidate.resolve(), self.root) or candidate.is_symlink():
            blocked(f'baseline reference escapes or is a symlink: {value}')
        # Reject symlink parents, including links staying inside baseline.
        for parent in (candidate, *candidate.parents):
            if parent == self.root:
                break
            if parent.is_symlink():
                blocked(f'baseline reference contains symlink: {value}')
        return candidate

    @property
    def structure(self):
        m = self.model
        if m.section_property_mode != 'explicit':
            blocked('kernel_model.section_property_mode: explicit SPX1 required for basic structure fields')
        return StructureParameters(m.diameter_m,m.length_m,m.explicit_EA_N,m.explicit_EI_Nm2,
                                   m.explicit_mass_per_length_kg_m,m.top_tension_N,m.damping_alpha,m.elements)

    def key_hashes(self, time):
        paths = [self.root/'app_baseline.json',
                 *(self.relative(self.descriptor[k]) for k in ('slice_manifest','kernel_model','structure_initial_state')),
                 self.fluid/'precice-config.xml']
        paths += [self.fluid/'system'/x for x in ('controlDict','preciceDict','decomposeParDict','fvSchemes','fvSolution')]
        result = {}
        for p in paths:
            if p.stat().st_size > 2*1024*1024:
                blocked(f'key configuration unexpectedly large (2 MiB limit): {p}')
            result[str(p.relative_to(self.root))] = digest(p.read_bytes())
        # Hash boundary/header only, never the large binary field body or runtime.
        p = self.fluid/time/'U'
        data = p.read_bytes()
        _, boundary = velocity_boundary(data)
        result[f'{p.relative_to(self.root)}#boundaryField'] = digest(boundary.data)
        return result

    def validate_time(self,time):
        if time not in self.times:
            blocked(f'initial state time not present: {time}')
        fields=self.descriptor['required_initial_fields']
        if not isinstance(fields,list) or not {'U','p','pointDisplacement','cellDisplacement'}.issubset(fields) or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',x) for x in fields):
            blocked('required_initial_fields must explicitly include fluid and ALE initial fields')
        directory=self.fluid/time
        for name in fields:
            if not (directory/name).is_file():
                blocked(f'{directory}/{name}: required initial field missing; not fabricated')
        for p in directory.rglob('*'):
            if p.is_symlink():
                blocked(f'symlink in selected initial state: {p}')
            if p.is_file() and p.name not in ('U',) and p.stat().st_size <= 2*1024*1024:
                data=p.read_bytes()
                header_end=data.find(b'}')+1
                binary=b'format' in data[:header_end] and b'binary' in data[:header_end]
                if binary:
                    matches=list(re.finditer(rb'(?m)^\s*boundaryField\s*\n?\s*\{',data))
                    data=data[matches[-1].start():] if matches else b''
                stripped=re.sub(rb'/\*.*?\*/|//[^\n]*',b'',data,flags=re.S)
                if b'#' in stripped or b'$' in stripped or operational_absolute_paths(data):
                    blocked(f'initial field has unresolved directive/absolute path: {p}')
        inlet_vector((directory/'U').read_bytes(), self.descriptor['flow']['inlet_patch'])


def inspect_baseline(path):
    root = local_path(path)
    if not root.is_dir():
        blocked(f'baseline directory missing: {root}')
    descriptor_path = root/'app_baseline.json'
    if not descriptor_path.is_file():
        blocked(f'{root}/app_baseline.json absent; cannot infer implicit coupling, structural initial state or force scaling')
    try:
        d = read_json(descriptor_path)
        if set(d) != REQUIRED_DESCRIPTOR:
            blocked(f'app_baseline.json: missing/unknown fields: {sorted(set(d)^REQUIRED_DESCRIPTOR)}')
        if d['schema'] != 'viv-app-baseline-v1' or d['contract_profile'] != PROFILE:
            blocked('app_baseline.json: only audited generic explicit profile is supported')
        if d['evidence_status'] not in ('SYNTHETIC_OFFLINE_ONLY','USER_VERIFIED_BASELINE'):
            blocked('app_baseline.json.evidence_status must be explicit')
        if d['naming'] != NAMING or d['time_window_equals_delta_t'] is not True:
            blocked('app_baseline.json: unrecognized naming or time-window relation')
        b = Baseline(root,d,root,None,{},None,{},(),None,0.)
        b.fluid = b.relative(d['fluid_case'])
        for sub in ('system','constant'):
            if not (b.fluid/sub).is_dir():
                blocked(f'{b.fluid}/{sub}: required OpenFOAM directory missing')
        b.manifest = load_manifest(read_json(b.relative(d['slice_manifest'])))
        b.model_raw = read_json(b.relative(d['kernel_model']))
        b.model = load_kernel(b.model_raw)
        b.initial_state = read_json(b.relative(d['structure_initial_state']))
        b.controls = FoamDict((b.fluid/'system/controlDict').read_bytes())
        dt = float(b.controls.scalar('deltaT'))
        b.model.validate(dt)
        if b.model.section_property_mode != 'explicit':
            blocked('kernel model must explicitly resolve SPX1 properties')
        if not all(k in b.initial_state for k in ('q','qdot','qddot')) or set(b.initial_state) != {'q','qdot','qddot'}:
            blocked('structure initial state: exact native q/qdot/qddot arrays required; no invented state')
        for k,v in b.initial_state.items():
            if len(v) != b.model.ndof or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in v):
                blocked(f'structure_initial_state.{k}: invalid dimensions or nonfinite values')
        positions = tuple(x.s_ref_m for x in b.manifest.slices)
        if b.manifest.reference_length_m != b.model.length_m or positions != b.model.slice_positions_m or b.manifest.ns != b.model.slices:
            blocked('slice_manifest and KernelModel dimensions/positions disagree')
        mode = {'LegacyPointLumped':'legacy_point_lumped', 'PiecewiseLinearDistributed':'piecewise_linear_distributed'}[b.manifest.reconstruction_mode]
        if b.model.spanwise_load_reconstruction != mode:
            blocked('slice_manifest mode disagrees with KernelModel SLD1 mode')
        if b.manifest.reconstruction_mode == 'LegacyPointLumped' and b.manifest.ns != 1:
            blocked('V1 supports inherited single-slice legacy only; multi-slice legacy tributaries are not inferred')
        if b.manifest.structure_participant != 'Structure_0000':
            blocked('slice_manifest: unknown structure participant')
        for i,row in enumerate(b.manifest.slices):
            if (row.slice_id != f'slice_{i:04d}' or row.fluid_participant != f'Fluid_{i:04d}'
                or row.fluid_mesh != f'Fluid-Mesh-{row.slice_id}' or row.structure_mesh != f'Structure-Mesh-{row.slice_id}'
                or row.openfoam_case_id != f'slice{i:04d}' or row.force_data != 'Force' or row.motion_data != 'Displacement'):
                blocked(f'slice_manifest.slices[{i}]: unknown participant/mesh/data naming')
        if b.manifest.reconstruction_mode == 'PiecewiseLinearDistributed' and (
            b.model.spanwise_active_s_min_m != b.manifest.active_start_m or b.model.spanwise_active_s_max_m != b.manifest.active_end_m):
            blocked('KernelModel SLD1 active interval differs from manifest')
        decomp = FoamDict((b.fluid/'system/decomposeParDict').read_bytes())
        if decomp.scalar('method') != 'scotch' or int(decomp.scalar('numberOfSubdomains')) < 1:
            blocked('decomposeParDict: only scotch with positive ranks is safely editable')
        pd = FoamDict((b.fluid/'system/preciceDict').read_bytes())
        row = b.manifest.slices[0]
        if pd.scalar('participant') != row.fluid_participant or pd.scalar('interfaces','Interface1','mesh') != row.fluid_mesh:
            blocked('preciceDict: baseline fluid template must be manifest slice zero')
        if pd.get('interfaces','Interface1','readData') != (b'(',b'Displacement',b')') or pd.get('interfaces','Interface1','writeData') != (b'(',b'Force',b')'):
            blocked('preciceDict: unknown data contract')
        if any(path[0]=='interfaces' and len(path)==2 and path[1]!='Interface1' for path in pd.blocks):
            blocked('preciceDict: multiple/unknown fluid interfaces')
        if pd.scalar('preciceConfig') != 'precice-config.xml':
            blocked('preciceDict: only local precice-config.xml baseline reference supported')
        application = b.controls.scalar('application')
        if application != 'pimpleFoam' or b.controls.scalar('stopAt') != 'endTime':
            blocked('controlDict: unknown solver/time contract')
        if b.controls.scalar('writeControl') not in ('timeStep','runTime','adjustableRunTime'):
            blocked('controlDict.writeControl: unsupported units')
        if b.controls.scalar('startFrom') not in ('startTime','latestTime'):
            blocked('controlDict.startFrom: unsupported restart selection')
        if ('adjustTimeStep',) in b.controls.entries and b.controls.scalar('adjustTimeStep') != 'no':
            blocked('controlDict.adjustTimeStep: adaptive dt incompatible with audited equal-window profile')
        time_names=[]
        for p in b.fluid.iterdir():
            if p.is_dir() and not p.is_symlink() and re.fullmatch(r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',p.name):
                if math.isfinite(float(p.name)) and float(p.name)>=0:
                    time_names.append(p.name)
        b.times = tuple(sorted(time_names,key=float))
        if d['initial_time_default'] not in b.times:
            blocked('app_baseline.json.initial_time_default: valid OpenFOAM time missing')
        if b.controls.scalar('startFrom') == 'latestTime':
            default = max(b.times,key=float)
        else:
            default = b.controls.scalar('startTime')
        if float(default) != float(d['initial_time_default']):
            blocked('default initial time conflicts with controlDict selection')
        max_time = float(b.controls.scalar('endTime')) - float(d['initial_time_default'])
        xml = (b.fluid/'precice-config.xml').read_text(encoding='utf-8')
        expected = generate_precice_xml(b.manifest,time_window_s=dt,max_time_s=max_time)
        if normalized_xml(xml) != normalized_xml(expected):
            blocked('precice-config.xml: differs from audited helper; implicit/retry/mapping settings will not be changed')
        flow=d['flow']
        if set(flow)!= {'field','inlet_patch','direction','preserve_internal_field'} or flow['field']!='U' or flow['preserve_internal_field'] is not True:
            raise GenerationError('UNSUPPORTED_BASELINE_FLOW_CONFIGURATION','app_baseline.json.flow: unsupported flow contract')
        direction=flow['direction']
        if len(direction)!=3 or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in direction) or not math.isclose(sum(x*x for x in direction),1.,abs_tol=1e-12):
            raise GenerationError('UNSUPPORTED_BASELINE_FLOW_CONFIGURATION','direction must be a finite unit vector')
        if any(path[:1]==('functions',) and path[-1]=='type' and entry.tokens==(b'forceCoeffs',)
               for path,entry in b.controls.entries.items()):
            raise GenerationError('UNSUPPORTED_BASELINE_FLOW_CONFIGURATION','controlDict forceCoeffs has a separate magUInf contract; not safely wired for variable flow in V1')
        b.validate_time(d['initial_time_default'])
        vec=inlet_vector((b.fluid/d['initial_time_default']/'U').read_bytes(),flow['inlet_patch'])
        b.inlet_speed=sum(a*c for a,c in zip(vec,direction))
        if b.inlet_speed<0 or any(not math.isclose(a,b.inlet_speed*c,abs_tol=1e-12) for a,c in zip(vec,direction)):
            raise GenerationError('UNSUPPORTED_BASELINE_FLOW_CONFIGURATION','baseline inlet is not aligned with declared direction')
        # Configuration includes are never resolved or copied from old runtimes.
        for folder in ('system','constant'):
            for p in (b.fluid/folder).rglob('*'):
                if p.is_symlink():
                    blocked(f'symlink in configuration: {p}')
                if p.is_file() and 'polyMesh' not in p.parts:
                    if p.stat().st_size > 2*1024*1024:
                        blocked(f'oversized dictionary: {p}')
                    FoamDict(p.read_bytes())
                    if operational_absolute_paths(p.read_bytes()):
                        blocked(f'absolute operational path in inherited configuration: {p}')
        b.key_hashes(d['initial_time_default'])
        return b
    except GenerationError:
        raise
    except (ValueError,TypeError,KeyError,OSError,AttributeError,ET.ParseError) as exc:
        blocked(f'baseline configuration: {exc}')


def operational_absolute_paths(data):
    # Only config text (not binary field bodies or provenance-only JSON).
    stripped = re.sub(rb'/\*.*?\*/|//[^\n]*',b'',data,flags=re.S)
    return re.search(rb'(?:"|(?<![A-Za-z0-9_.]))(?:/[A-Za-z][A-Za-z0-9_.-]*/|[A-Za-z]:[\\/]|\\\\[A-Za-z])',stripped) is not None
