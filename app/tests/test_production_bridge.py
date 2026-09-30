"""Offline bridge checks. Nothing in this module executes a participant."""
from dataclasses import replace
from pathlib import Path
import json
import math
import pytest
from viv_app.models.simulation_spec import SimulationSpec,FlowProfile
from viv_app.generator.production_baseline import (POSITIONS,STRUCTURE,PROFILE_ROOT,validate_production_spec,
    selected_state,inspect_production_baseline)
from viv_app.generator.production_xml import V2606ImplicitTopologyBuilder,parse_production_xml
from viv_app.generator.production_generator import (slice_manifest,launch_manifest,initial_velocity,fluid_control)
from viv_app.generator.production_validation import validate_production_case
from viv_app.generator.production_preflight import production_preflight
from viv_app.generator.foam_dict import FoamDict,velocity_boundary,inlet_vector
from viv_app.generator.errors import GenerationError
from viv_app.utils.paths import CASES_ROOT


def spec():
    return SimulationSpec('production_test',str(PROFILE_ROOT),str(CASES_ROOT),
        '29.9999999999834372',tuple(x/13.12 for x in POSITIONS),(4,)*5,STRUCTURE,FlowProfile(),.0004,30.04,20,purge_write=2)


def xml_fixture():
    # Tiny TEST ONLY topology, never an enrolled baseline or qualification.
    fluid=''.join(f'<participant name="Fluid-S{i}" />' for i in range(1,6))
    exchanges=''.join(f'<exchange data="TEST-{i}" />' for i in range(10))
    return ('<precice-configuration>'+fluid+'<participant name="Structure" />'
        '<m2n:sockets acceptor="Structure" connector="Fluid-S1" exchange-directory="/old/runtime" />'
        '<coupling-scheme:multi><time-window-size value="0.0004"/><max-time-windows value="100"/>'
        '<max-iterations value="50"/>'+exchanges+'<acceleration:IQN-ILS><initial-relaxation value="0.5"/></acceleration:IQN-ILS>'
        '</coupling-scheme:multi></precice-configuration>')


@pytest.mark.smoke
@pytest.mark.parametrize('kind,kwargs,expected',[
    ('Uniform',{'u0':.31},[.31]*5),
    ('Linear Shear',{'u_bottom':0.,'u_top':1.},[x/13.12 for x in POSITIONS]),
    ('Step Current',{'transition':.2,'u_active':.6,'u_inactive':0.},[.6,.6,0.,0.,0.])])
def test_n5_flow_manifest(kind,kwargs,expected):
    s=replace(spec(),flow=FlowProfile(kind=kind,**kwargs))
    assert validate_production_spec(s)==100
    manifest=slice_manifest(s)
    assert [r['U_i'] for r in manifest['slices']]==pytest.approx(expected)
    assert len({r['participant'] for r in manifest['slices']})==5
    assert [r['s_ref_m'] for r in manifest['slices']]==list(POSITIONS)
    assert manifest['active_region_m']==[0.,5.94]


@pytest.mark.smoke
@pytest.mark.parametrize('change,code',[
    ({'mpi_ranks':(8,)*5},'PRODUCTION_MPI_LOCKED'),
    ({'positions_over_l':(.1,.2,.3,.4,.5)},'PRODUCTION_POSITIONS_LOCKED'),
    ({'structure':replace(STRUCTURE,elements=40)},'PRODUCTION_STRUCTURE_LOCKED'),
    ({'structure':replace(STRUCTURE,damping_alpha=.1)},'PRODUCTION_STRUCTURE_LOCKED'),
    ({'delta_t':.0002},'PRODUCTION_DELTA_T_LOCKED'),
    ({'positions_over_l':(.1,.2,.3),'mpi_ranks':(4,)*3},'PRODUCTION_N_LOCKED'),
    ({'end_time':30.0401},'INVALID_COUPLED_DURATION'),
    ({'purge_write':-1},'INVALID_PURGE_WRITE')])
def test_production_locks(change,code):
    with pytest.raises(GenerationError,match=code):validate_production_spec(replace(spec(),**change))


@pytest.mark.smoke
def test_implicit_xml_whitelist_and_tamper_rejection():
    builder=V2606ImplicitTopologyBuilder(xml_fixture());xml=builder.build(25000)
    root=builder.validate(xml,25000)
    assert root.find('{urn:precice:m2n}sockets').get('exchange-directory')=='..'
    modified=xml.replace(b'value="50"',b'value="51"')
    with pytest.raises(GenerationError,match='IMPLICIT_SEMANTICS_CHANGED'):builder.validate(modified,25000)
    with pytest.raises(GenerationError):builder.validate(xml,100)
    with pytest.raises(GenerationError):V2606ImplicitTopologyBuilder(xml_fixture().replace('Fluid-S5','Fluid-S4'))


@pytest.mark.smoke
def test_structure_native_argv_and_manual_decomposition():
    d=json.loads((PROFILE_ROOT/'app_baseline.json').read_text())
    launch=launch_manifest(spec(),d)
    assert launch['expected_participant_count']==6 and launch['total_cfd_ranks']==20
    assert launch['real_fsi_started'] is False and launch['production_launch_ready'] is False
    command=launch['structure']['command']
    assert len(command)==11 and command[3]==d['structure_executable']
    assert command[4:9]==['../precice-config.xml','initial_state.raw','../runtime/attempts.jsonl','../runtime/accepted_windows.jsonl','../runtime/state_attempt_']
    for row in launch['fluid']:
        assert 'decomposePar' in Path(row['prepare_command'][5]).name
        assert row['mpi_ranks']==4
        assert row['command'][-4:]==[d['openfoam_bin']+'/pimpleFoam','-parallel','-case','.']
        assert all('/launch/' not in x for x in row['command'])


@pytest.mark.smoke
def test_literal_p1_record_selection():
    q=b'Q 198 '+b' '.join([b'0']*198)+b'\n'
    record=b'CASE REF_NE32 32 7470000 metadata\n'+q
    assert selected_state(b'CASE OTHER\nQ 1 1\n'+record)==record
    with pytest.raises(GenerationError):selected_state(record+record)
    with pytest.raises(GenerationError):selected_state(record.replace(b'Q 198',b'Q 197'))


@pytest.mark.smoke
def test_exact_binary_u_boundary_edit():
    # Opaque binary data remains identical, only exact boundary dictionary paths change.
    prefix=b'FoamFile { format binary; class volVectorField; object U; }\ninternalField nonuniform List<vector>\n1\n('+bytes(range(32))+b')\n'
    u=prefix+b'boundaryField\n{ inlet { type fixedValue; value uniform (.31 0 0); } cylinder { type fixedValue; value uniform (0 0 0); } }\n'
    out=initial_velocity(u,0.)
    assert velocity_boundary(out)[0]==prefix
    assert inlet_vector(out,'inlet')==(0.,0.,0.)
    assert velocity_boundary(out)[1].scalar('boundaryField','cylinder','type')=='movingWallVelocity'
    with pytest.raises(GenerationError):initial_velocity(u.replace(b'type fixedValue;',b'type zeroGradient;',1),.5)


@pytest.mark.smoke
def test_preflight_fails_closed_on_missing_case(tmp_path,monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('must not run environment utilities before static failure')
    monkeypatch.setattr('viv_app.generator.production_preflight.subprocess.run',forbidden)
    root=tmp_path/'missing_case';root.mkdir()
    result=production_preflight(root)
    assert result['status']=='FAIL' and result['production_launch_ready'] is False
    assert result['real_fsi_started'] is False


@pytest.mark.production_integration
def test_readonly_qualified_import_and_gui_locks():
    d=json.loads((PROFILE_ROOT/'app_baseline.json').read_text())
    if not Path(d['qualification_record']).is_file():pytest.skip('local external NM12 evidence unavailable')
    before={p:Path(p).stat().st_mtime_ns for p in d['identities']}
    b=inspect_production_baseline(PROFILE_ROOT)
    assert b.descriptor['evidence_status']=='USER_PROJECT_QUALIFIED'
    from PySide6.QtWidgets import QApplication
    from viv_app.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow();window.baseline_path.setText(str(PROFILE_ROOT));window.baseline_loaded(b)
    assert window.count.value()==5 and not window.count.isEnabled()
    assert not window.dt.isEnabled() and not window.damping.isEnabled()
    assert not window.ranks.isEnabled() and all(not window.table.cellWidget(i,4).isEnabled() for i in range(5))
    assert window.positions()==pytest.approx(tuple(x/13.12 for x in POSITIONS))
    window.flow_type.setCurrentText('Step Current')
    assert window.simulation_spec().mpi_ranks==(4,)*5
    window.close();app.processEvents()
    assert before=={p:Path(p).stat().st_mtime_ns for p in d['identities']}


@pytest.mark.smoke
def test_foam_environment_has_no_inherited_configuration_args(tmp_path):
    import subprocess
    from viv_app.generator.production_generator import foam_command
    env=tmp_path/'test environment.sh'
    env.write_text('[[ $# -eq 0 ]] || return 71\nexport VIV_TEST_ENV=loaded\n')
    literal='path with spaces; $(should_never_execute)'
    command=foam_command(str(env),['bash','-c','printf "%s:%s" "$VIV_TEST_ENV" "$1"','viv-test',literal])
    result=subprocess.run(command,capture_output=True,text=True,timeout=5)
    assert result.returncode==0 and result.stdout=='loaded:'+literal


@pytest.mark.smoke
def test_zero_flow_disables_only_coefficient_diagnostic():
    source=b'''startFrom latestTime; startTime 0; endTime 30.04; writeInterval 20; purgeWrite 2;
    functions {
      nm84InputObserver { outputDir "/old/runtime/in"; }
      nm84ForceObserver { outputDir "/old/runtime/force"; }
      cylinderForceCoeffs { magUInf .31; writeInterval 5; }
      cylinderForces { writeInterval 1; }
      preCICE_Adapter { errors strict; }
    }'''
    zero=FoamDict(fluid_control(source,spec(),0.))
    assert zero.scalar('functions','cylinderForceCoeffs','enabled')=='false'
    assert zero.scalar('functions','cylinderForceCoeffs','magUInf')=='0'
    assert zero.scalar('functions','cylinderForces','writeInterval')=='1'
    assert zero.scalar('functions','preCICE_Adapter','errors')=='strict'
    assert zero.scalar('functions','nm84ForceObserver','outputDir')=='runtime/force_observer'
    nonzero=FoamDict(fluid_control(source,spec(),.6))
    assert ('functions','cylinderForceCoeffs','enabled') not in nonzero.entries
    assert float(nonzero.scalar('functions','cylinderForceCoeffs','magUInf'))==.6
