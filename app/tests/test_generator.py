from pathlib import Path
from dataclasses import replace
import hashlib
import json
import pytest
from viv_app.generator.baseline import inspect_baseline
from viv_app.generator.case_generator import generate_case
from viv_app.generator.validation import validate_case
from viv_app.generator.errors import GenerationError
from viv_app.generator.foam_dict import FoamDict,inlet_vector
from viv_app.models.simulation_spec import SimulationSpec,FlowProfile,uniform_positions


def make_spec(baseline,n,tmp_path,flow=None,positions=None):
    b=inspect_baseline(baseline)
    positions=positions if positions is not None else uniform_positions(n,b.model.length_m,b.manifest.active_start_m,b.manifest.active_end_m)
    return SimulationSpec('test_case',str(baseline),str(tmp_path/'output'),b.descriptor['initial_time_default'],
                          positions,(4,)*n,b.structure,flow or FlowProfile(),.0002,float(b.descriptor['initial_time_default'])+.2,.01,
                          'custom' if positions else 'uniform')


def all_hashes(root):
    # Tiny fixture only, deliberately never applied to real runtime.
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('n',[1,3,5])
def test_n_generation_and_baseline_immutability(n,baseline_factory,tmp_path):
    baseline=baseline_factory(distributed=n!=1)
    # Simulate a previously run case; these trees must never be copied.
    for name in ('processor0','postProcessing','precice-run','logs','100','checkpoint'):
        (baseline/'fluid'/name).mkdir()
        (baseline/'fluid'/name/'runtime_data').write_text('do not copy')
    (baseline/'fluid/log.pimpleFoam').write_text('runtime')
    before=all_hashes(baseline)
    output=generate_case(make_spec(baseline,n,tmp_path))
    assert all_hashes(baseline)==before
    assert validate_case(output)['status']=='PASS'
    m=json.loads((output/'generation_manifest.json').read_text())
    assert m['slice_count']==n
    assert m['generation_status']=='PASS'
    assert len(list(output.glob('slice[0-9][0-9][0-9][0-9]')))==n
    for case in output.glob('slice[0-9]*'):
        assert not any((case/x).exists() for x in ('processor0','postProcessing','precice-run','logs','100','checkpoint'))
        assert (case/'0/U_0').read_bytes()==(baseline/'fluid/0/U_0').read_bytes()
        assert (case/'0/phi').read_bytes()==(baseline/'fluid/0/phi').read_bytes()


@pytest.mark.parametrize('kind,expected',[
    ('Uniform',[.6]*5),('Linear Shear',[.06,.18,.3,.42,.54]),('Step Current',[.6,.6,0,0,0])])
def test_flow_profiles(kind,expected,baseline_factory,tmp_path):
    baseline=baseline_factory()
    flow=FlowProfile(kind=kind,u0=.6,u_bottom=0,u_top=.6,transition=.45,u_active=.6,u_inactive=0)
    output=generate_case(make_spec(baseline,5,tmp_path,flow,positions=(.1,.3,.5,.7,.9)))
    actual=[]
    for i in range(5): actual.append(inlet_vector((output/f'slice{i:04d}/0/U').read_bytes(),'inlet')[0])
    assert actual==pytest.approx(expected)
    assert validate_case(output)['status']=='PASS'


def test_uniform_native_positions(baseline_factory,tmp_path):
    spec=replace(make_spec(baseline_factory(),5,tmp_path),placement='uniform')
    output=generate_case(spec)
    m=json.loads((output/'slice_manifest.json').read_text())
    assert [r['s_ref_m'] for r in m['slices']]==[1,3,5,7,9]
    assert len({r['fluid_participant'] for r in m['slices']})==5
    assert [r['fluid_participant'] for r in m['slices']]==[f'Fluid_{i:04d}' for i in range(5)]


@pytest.mark.parametrize('positions',[(-.1,.3,.5),(.1,.3,1.1),(.1,.1,.5),(.5,.3,.1),(float('nan'),.3,.5)])
def test_invalid_positions_rejected(positions,baseline_factory,tmp_path):
    spec=replace(make_spec(baseline_factory(),3,tmp_path),positions_over_l=positions)
    with pytest.raises(GenerationError): generate_case(spec)
    assert not (tmp_path/'output/test_case').exists()


def test_existing_target_refused(baseline_factory,tmp_path):
    spec=make_spec(baseline_factory(),3,tmp_path)
    target=Path(spec.output_root)/spec.case_name
    target.mkdir(parents=True); (target/'sentinel').write_text('keep')
    with pytest.raises(GenerationError,match='TARGET_CASE_ALREADY_EXISTS'): generate_case(spec)
    assert (target/'sentinel').read_text()=='keep'


def test_sld1_n1_does_not_silently_switch_mode(baseline_factory,tmp_path):
    with pytest.raises(ValueError,match='count >= 2'):
        generate_case(make_spec(baseline_factory(),1,tmp_path))


def test_legacy_n3_is_blocked(baseline_factory,tmp_path):
    with pytest.raises(GenerationError,match='LegacyPointLumped'):
        generate_case(make_spec(baseline_factory(False),3,tmp_path))


def test_unknown_baseline_fails_closed(tmp_path):
    with pytest.raises(GenerationError,match='GENERATION_BLOCKED_BY_UNKNOWN_CONTRACT'): inspect_baseline(tmp_path)


def test_unsupported_flow_not_string_replaced(baseline_factory):
    baseline=baseline_factory()
    path=baseline/'fluid/0/U'
    path.write_text(path.read_text().replace('type fixedValue','type codedFixedValue'))
    with pytest.raises(GenerationError,match='UNSUPPORTED_BASELINE_FLOW_CONFIGURATION'): inspect_baseline(baseline)


def test_implicit_xml_is_not_converted(baseline_factory):
    baseline=baseline_factory()
    path=baseline/'fluid/precice-config.xml'
    path.write_text(path.read_text().replace('parallel-explicit','parallel-implicit'))
    with pytest.raises(GenerationError,match='implicit/retry/mapping'): inspect_baseline(baseline)


def test_locked_structure_edits_rejected(baseline_factory,tmp_path):
    spec=make_spec(baseline_factory(),3,tmp_path)
    spec=replace(spec,structure=replace(spec.structure,ea_n=100))
    with pytest.raises(GenerationError,match='NOT YET WIRED'): generate_case(spec)


def test_alpha_mapping_and_per_slice_ranks(baseline_factory,tmp_path):
    spec=make_spec(baseline_factory(),3,tmp_path)
    spec=replace(spec,structure=replace(spec.structure,damping_alpha=.01),mpi_ranks=(1,2,3))
    output=generate_case(spec)
    assert json.loads((output/'Structure_0000/kernel_model.json').read_text())['damping_alpha']==.01
    for i,rank in enumerate(spec.mpi_ranks):
        assert int(FoamDict((output/f'slice{i:04d}/system/decomposeParDict').read_bytes()).scalar('numberOfSubdomains'))==rank


def test_developed_initial_state_selected_only(baseline_factory,tmp_path):
    baseline=baseline_factory(developed=True)
    source=baseline/'fluid/30'
    other=baseline/'fluid/0'; other.mkdir(); (other/'U').write_text('not selected')
    before=all_hashes(baseline)
    output=generate_case(make_spec(baseline,3,tmp_path))
    for case in output.glob('slice[0-9]*'):
        assert (case/'30/phi').read_bytes()==(source/'phi').read_bytes()
        assert (case/'30/uniform/time').read_bytes()==(source/'uniform/time').read_bytes()
        assert not (case/'0').exists()
    assert all_hashes(baseline)==before


@pytest.mark.parametrize('field,replacement',[
    ('precice-config.xml',lambda s:s.replace('Force','WrongForce')),
    ('slice0000/system/fvSolution',lambda s:s.replace('nCorrectors 2','nCorrectors 99')),
    ('slice0000/system/controlDict',lambda s:s.replace('writeInterval 5','writeInterval 999')),
    ('slice0000/system/preciceDict',lambda s:s.replace('rho rho','rho wrongRho')),
])
def test_static_validation_detects_tampering(field,replacement,baseline_factory,tmp_path):
    output=generate_case(make_spec(baseline_factory(),3,tmp_path))
    path=output/field
    old=path.read_text(); new=replacement(old); assert old!=new
    path.write_text(new)
    result=validate_case(output)
    assert result['status']=='FAIL' and result['first_failure']


def test_binary_velocity_payload_preserved(baseline_factory,tmp_path):
    baseline=baseline_factory()
    path=baseline/'fluid/0/U'
    data=path.read_bytes().replace(b'format ascii',b'format binary')
    opaque=b'\x00\xff\xf1\x87BINARY_INTERNAL_VELOCITY\x00'
    data=data.replace(b'internalField uniform (0.31 0 0);',b'internalField nonuniform List<vector>\n1\n('+opaque+b')\n;')
    path.write_bytes(data)
    output=generate_case(make_spec(baseline,3,tmp_path,FlowProfile(u0=.6)))
    for case in output.glob('slice[0-9]*'):
        assert opaque in (case/'0/U').read_bytes()
        assert inlet_vector((case/'0/U').read_bytes(),'inlet')==(0.6,0,0)


def test_symlink_and_absolute_config_refusal(baseline_factory):
    baseline=baseline_factory()
    path=baseline/'fluid/system/fvSolution'
    path.write_text(path.read_text()+'\npath "/old/runtime/config";\n')
    with pytest.raises(GenerationError,match='absolute operational'): inspect_baseline(baseline)


@pytest.mark.parametrize('value',[0,-1,1.5,True])
def test_invalid_mpi_ranks(value,baseline_factory,tmp_path):
    spec=replace(make_spec(baseline_factory(),3,tmp_path),mpi_ranks=(value,4,4))
    with pytest.raises(GenerationError,match='INVALID_MPI_RANKS'): spec.validate()


def test_path_traversal_and_outside_root_rejected(baseline_factory,tmp_path):
    spec=make_spec(baseline_factory(),3,tmp_path)
    with pytest.raises(GenerationError,match='INVALID_CASE_NAME'): replace(spec,case_name='../escaped').validate()
    with pytest.raises(GenerationError,match='OUTPUT_OUTSIDE_APP'): replace(spec,output_root='/tmp').validate()


def test_disabled_slice_is_explicitly_rejected(baseline_factory,tmp_path):
    spec=replace(make_spec(baseline_factory(),3,tmp_path),enabled=(True,False,True))
    with pytest.raises(GenerationError,match='DISABLED_SLICE_NOT_SUPPORTED'): spec.validate()


def test_missing_phi_not_fabricated(baseline_factory,tmp_path):
    baseline=baseline_factory(); (baseline/'fluid/0/phi').unlink()
    with pytest.raises(GenerationError,match='required initial field missing'): generate_case(make_spec(baseline,3,tmp_path))


def test_missing_mesh_validation_fails(baseline_factory,tmp_path):
    output=generate_case(make_spec(baseline_factory(),3,tmp_path))
    (output/'slice0000/constant/polyMesh/points').unlink()
    assert validate_case(output)['status']=='FAIL'


def test_atomic_publish_refuses_raced_existing_directory(tmp_path):
    from viv_app.generator.case_generator import publish_no_replace
    stage=tmp_path/'stage'; stage.mkdir(); (stage/'new').write_text('new')
    target=tmp_path/'target'; target.mkdir(); (target/'sentinel').write_text('preserve')
    with pytest.raises(GenerationError,match='TARGET_CASE_ALREADY_EXISTS'): publish_no_replace(stage,target)
    assert (target/'sentinel').read_text()=='preserve' and (stage/'new').exists()


def test_staging_retained_and_retry_refused(baseline_factory,tmp_path,monkeypatch):
    from viv_app.generator import validation
    spec=make_spec(baseline_factory(),3,tmp_path)
    original=validation.validate_case
    monkeypatch.setattr(validation,'validate_case',lambda *a,**k:{'status':'FAIL','first_failure':'injected offline validation failure'})
    with pytest.raises(GenerationError,match='STATIC_VALIDATION_FAILED'): generate_case(spec)
    stage=Path(spec.output_root)/'.test_case.staging'
    evidence=(stage/'generation_failure.json').read_bytes()
    assert not (Path(spec.output_root)/spec.case_name).exists()
    monkeypatch.setattr(validation,'validate_case',original)
    with pytest.raises(GenerationError,match='TARGET_CASE_STAGING_ALREADY_EXISTS'): generate_case(spec)
    assert (stage/'generation_failure.json').read_bytes()==evidence


def test_n32_native_generator(baseline_factory,tmp_path):
    # Lightweight topology/model test: avoids 32 mesh copies on the user's disk.
    from viv_app.generator.precice_generator import build_manifest
    from viv_app.generator.native import generate_precice_xml,inspect_precice_xml
    spec=make_spec(baseline_factory(),32,tmp_path)
    b=inspect_baseline(spec.baseline_path)
    manifest=build_manifest(spec,b)
    assert inspect_precice_xml(generate_precice_xml(manifest),manifest)['fluid_participant_count']==32
