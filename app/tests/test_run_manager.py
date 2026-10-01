"""Only fake child processes are launched. No OpenFOAM/preCICE/ANCF/MPI."""
from pathlib import Path
import json
import math
import os
import subprocess
import sys
import time
import pytest
import psutil
from PySide6.QtCore import QTimer,QEventLoop
from PySide6.QtWidgets import QApplication
from viv_app.runner.manager import RunManager,write
from viv_app.runner.config import RunOptions
from viv_app.runner.state import StateMachine,RunState
from viv_app.runner.contract import ExecutionContract,load_contract,check_decomposition,prepared_identity
from viv_app.runner.processes import OwnedProcesses,ResourceSampler
from viv_app.generator.production_baseline import PROFILE,PROFILE_ROOT
from viv_app.monitor.models import LineBuffer,MonitorEvent
from viv_app.monitor.structure_parser import StructureParser
from viv_app.monitor.fluid_parser import FluidParser
from viv_app.monitor.run_monitor import RunMonitor
from viv_app.utils.paths import APP_ROOT



class FakeGate:
    def contract(self,root):return ExecutionContract(root,json.loads((root/'launch_manifest.json').read_text()),json.loads((root/'generation_manifest.json').read_text()),json.loads((root/'baseline_contract_snapshot.json').read_text()))
    def validate(self,root,prepared=False):return {'status':'PASS','scope':'TEST_ONLY'}
    def preflight(self,root,prepared=False):return {'status':'PASS','production_launch_ready':True,'scope':'TEST_ONLY'}
    def decomposition(self,c):return check_decomposition(c)
    def identity(self,c):
        # Lifecycle fixtures avoid repeatedly hashing 260 fake fields.
        # ProductionGate retains the complete bounded prepared identity gate.
        from viv_app.runner.contract import digest
        names=['launch_manifest.json','generation_manifest.json','baseline_contract_snapshot.json','Structure/initial_state.raw']
        return {n:digest(c.root/n)for n in names}
    def fresh(self,c):
        from viv_app.runner.contract import fresh_execution
        fresh_execution(c)
    def app_identity(self):return {'commit':'FAKE_ONLY','source_hashes':{'fake':'identity'}}


@pytest.fixture
def fake_case(tmp_path):
    def create(mode='normal',delay=.01):
        root=tmp_path/mode;root.mkdir();(root/'runtime').mkdir();rows=[]
        fixture=APP_ROOT/'app/tests/fixtures/fake_participant.py'
        env={'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
        for i,name in enumerate(['Structure',*[f'Fluid-S{s}'for s in range(1,6)]]):
            cwd=name;(root/cwd).mkdir()
            command=[sys.executable,str(fixture),'--name',name,'--mode',mode,'--delay',str(delay)]
            row={'participant':name,'cwd':cwd,'case_path':cwd,'command':command,'mpi_ranks':1 if i==0 else 4,
                 'cpu_set':'20'if i==0 else f'{4*(i-1)}-{4*i-1}','environment':env}
            if i:row['prepare_command']=[sys.executable,str(fixture),'--prepare','--delay',str(delay)]
            rows.append(row)
            if i:
                (root/cwd/'runtime').mkdir();(root/cwd/'system').mkdir();(root/cwd/'system/controlDict').write_text('FAKE ONLY')
        launch={'schema':'viv-app-production-launch-v1','structure':rows[0],'fluid':rows[1:],'expected_participant_count':6,'total_cfd_ranks':20,
                'startup_order':['manual: decompose all five selected initial states',*[r['participant']for r in rows]]}
        generation={'contract_profile':PROFILE,'generation_status':'PASS','slice_count':5,'deltaT':.0004,'mpi_ranks':[4]*5,'max_time_windows':5,'coupled_duration_s':.002}
        descriptor={'contract_profile':PROFILE,'initial_time_default':'30'}
        write(root/'launch_manifest.json',launch);write(root/'generation_manifest.json',generation);write(root/'baseline_contract_snapshot.json',descriptor)
        for n in ['precice-config.xml','production_xml_template.xml','simulation_spec.yaml','slice_manifest.json','Structure/initial_state.raw','Structure/structure_config.json','Structure/compiled_kernel_model.json']:
            (root/n).write_text('FAKE ONLY')
        return root
    return create


def finish(manager,timeout=45):
    manager.thread.join(timeout);assert not manager.busy,'offline fake supervisor hung'


def manager_for(root,startup=2):
    return RunManager(root,RunOptions(startup,.15,30,.01,.05),gate=FakeGate())


def prepared(root):
    m=manager_for(root);m.prepare();finish(m);assert m.state==RunState.PREPARED;return m


@pytest.mark.smoke
def test_state_machine_rejects_skips_and_terminal_reuse():
    s=StateMachine()
    with pytest.raises(ValueError):s.transition(RunState.RUNNING)
    for state in ['VALIDATED','PREFLIGHT_PASSED','PREPARING','PREPARED','STARTING','HANDSHAKING','RUNNING','COMPLETED']:s.transition(state)
    with pytest.raises(ValueError):s.transition('STARTING')


@pytest.mark.smoke
@pytest.mark.parametrize('tamper',['names','cpus','argv','cwd','startup','profile','dt'])
def test_manifest_structural_parser_rejects(tamper,fake_case):
    root=fake_case();g=json.loads((root/'generation_manifest.json').read_text());l=json.loads((root/'launch_manifest.json').read_text())
    assert load_contract(root).target_windows==5
    if tamper=='names':l['fluid'][0]['participant']='Structure'
    if tamper=='cpus':l['fluid'][0]['cpu_set']='21-25'
    if tamper=='argv':l['fluid'][0]['command']='shell command string'
    if tamper=='cwd':l['fluid'][0]['cwd']='../external'
    if tamper=='startup':l['startup_order'].reverse()
    if tamper=='profile':g['contract_profile']='arbitrary-n-live-explicit-v1'
    if tamper=='dt':g['deltaT']=.0002
    write(root/'launch_manifest.json',l);write(root/'generation_manifest.json',g)
    with pytest.raises(ValueError):load_contract(root)


@pytest.mark.parametrize('mode',[pytest.param('normal',marks=pytest.mark.smoke),'partial','co_warning'])
def test_fake_five_window_success_and_persistent_monitor(mode,fake_case):
    m=prepared(fake_case(mode));m.run();finish(m)
    assert m.state==RunState.COMPLETED
    result=json.loads((m.root/'run_result.json').read_text());assert result['real_fsi_started']is False
    assert all(r['exit_code']==0 and r['handshake'] for r in result['participants'].values())
    assert result['monitor']['accepted_windows']==5 and result['monitor']['rollback_count']==5
    assert result['monitor']['progress']==1
    events=[json.loads(l)for l in (m.run_dir/'runtime_monitor.jsonl').read_text().splitlines()]
    assert sum(e['event_type']=='accepted_window' for e in events)==5
    assert any(e['event_type']=='resources'for e in events)
    if mode=='co_warning':assert result['monitor']['max_Co']==1.4 and result['monitor']['warning_count']>0
    with pytest.raises(ValueError):m.run()


@pytest.mark.parametrize('mode,reason',[('nonzero',''),('stderr','fake stderr failure'),('incomplete','target accepted windows'),('slow','STARTUP_TIMEOUT')])
def test_failure_closed(mode,reason,fake_case):
    m=prepared(fake_case(mode));m.options=RunOptions(.2,.1,30,.01,.05);m.run();finish(m)
    assert m.state==RunState.FAILED
    r=json.loads((m.root/'run_result.json').read_text());assert reason in str(r['first_failure'])
    assert all(v['exit_code'] is not None for v in r['participants'].values())


def test_changed_prepared_inputs_never_start_participants(fake_case):
    m=prepared(fake_case());(m.root/'Structure/initial_state.raw').write_text('changed')
    m.run();finish(m);assert m.state==RunState.FAILED and not m.records


def test_production_prepared_field_fingerprint_detects_drift(fake_case):
    m=prepared(fake_case());before=prepared_identity(m.contract)
    p=m.root/'Fluid-S1/processor0/30/U';p.write_text('altered prepared field')
    assert prepared_identity(m.contract)!=before


@pytest.mark.parametrize('mode',[pytest.param('child',marks=pytest.mark.smoke),'stubborn'])
def test_abort_only_own_created_process_tree(mode,fake_case,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Global process enumeration / psutil.children is forbidden')
    monkeypatch.setattr(psutil.Process,'children',forbidden)
    monkeypatch.setattr(psutil,'process_iter',forbidden)
    monkeypatch.setattr(psutil,'pids',forbidden)
    unrelated=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'],start_new_session=True)
    m=None
    try:
        m=prepared(fake_case(mode));m.run()
        deadline=time.monotonic()+45
        while m.state!=RunState.RUNNING and time.monotonic()<deadline:time.sleep(.01)
        assert m.state==RunState.RUNNING
        sampler=ResourceSampler(m.owner,m.root);time.sleep(.06);stats=sampler.sample()
        assert stats['solver_rss_bytes']>0 and 0<=stats['system_ram_percent']<=100
        assert unrelated.pid not in m.owner.identities
        owned_ids=dict(m.owner.identities)
        m.abort();finish(m);assert m.state==RunState.ABORTED
        assert unrelated.poll() is None,'Unrelated process was affected'
        r=json.loads((m.root/'run_result.json').read_text());assert r['process_control_actions']
        assert r['abort_message']=='ABORTED RUN MAY NOT BE RESTARTABLE'
        for row in m.records.values():assert row['status']=='ABORTED'
        for pid,created in owned_ids.items():
            try:
                process=psutil.Process(pid)
                assert process.create_time()!=created or process.status()==psutil.STATUS_ZOMBIE,'Own child left alive'
            except psutil.NoSuchProcess:pass
    finally:
        # On an assertion failure, still clean up this fixture's own manager.
        # Input revalidation is background IO, not the participant startup gate.
        if m is not None and m.busy:
            deadline=time.monotonic()+45
            from viv_app.runner.state import ACTIVE
            while m.busy and m.state not in ACTIVE and time.monotonic()<deadline:time.sleep(.01)
            if m.busy and m.state in ACTIVE and m.state!=RunState.ABORTING:m.abort()
            finish(m,timeout=45)
        unrelated.terminate();unrelated.wait(timeout=5) # fixture controls only its own dummy


@pytest.mark.smoke
def test_log_parsers_partial_malformed_and_real_smoke_grammar():
    b=LineBuffer();assert b.feed(b'NM9_ATT')==[]
    assert b.feed(b'EMPT window=1 iteration=2 accepted=0 physical_time=30\n')==['NM9_ATTEMPT window=1 iteration=2 accepted=0 physical_time=30']
    s=StructureParser();assert s.parse('unrecognized malformed line')==[]
    assert s.parse('NM9_ATTEMPT broken')[0].event_type=='fatal'
    assert s.parse('NM9_ATTEMPT window=1 iteration=2 accepted=0 physical_time=30')[1].event_type=='rejected_attempt'
    following=s.parse('relative convergence measure: relative two-norm diff of data "Force-S1" = 0.1, limit = 5e-3, normalization = 1, conv = false')[0]
    assert following.window==1 and following.iteration==3
    f=FluidParser('Fluid-S2');events=f.parse('Courant Number mean: 0.1 max: 1.2');assert [e.event_type for e in events]==['courant','warning']
    assert f.parse('Mesh Courant Number mean: 0.01 max: 0.02')[0].event_type=='mesh_courant'
    assert f.parse('GAMG:  Solving for p, Initial residual = 0.1, Final residual = 0.001, No Iterations 7')[0].value['field']=='p'
    assert f.parse('FOAM FATAL ERROR')[0].event_type=='fatal'
    tiny=LineBuffer(limit=10);assert 'OVERSIZED_LINE' in tiny.feed(b'a'*100+b'\n')[0]


@pytest.mark.smoke
def test_replay_qualified_smoke_output_excerpt():
    fixture=APP_ROOT/'app/tests/fixtures/run_monitor'
    parser=StructureParser();events=[]
    for line in (fixture/'structure_excerpt.txt').read_text().splitlines():events.extend(parser.parse(line))
    assert sum(e.event_type=='participant_connected'for e in events)==1
    accepted=[e for e in events if e.event_type=='accepted_window']
    assert len(accepted)==1 and accepted[0].window==1 and accepted[0].iteration==7
    assert accepted[0].physical_time==pytest.approx(30.0004) and accepted[0].value['residuals_complete']
    assert any(e.event_type=='rejected_attempt'for e in events)
    parser=FluidParser('Fluid-S1');events=[]
    for line in (fixture/'fluid_excerpt.txt').read_text().splitlines():events.extend(parser.parse(line))
    assert any(e.event_type=='participant_connected'for e in events)
    assert max(e.value['max']for e in events if e.event_type=='courant')==pytest.approx(.8822924897)
    assert any(e.event_type=='mesh_courant'for e in events)


def test_prepare_preflight_fail_never_launches(fake_case):
    class BlockedGate(FakeGate):
        def preflight(self,root,prepared=False):raise ValueError('Preflight FAIL')
    m=RunManager(fake_case(),RunOptions(),gate=BlockedGate());m.prepare();finish(m)
    assert m.state==RunState.FAILED and m.owner is None and not m.records
    assert not list(m.root.rglob('processor0'))


def test_case_lock_and_foreign_paths_fail_closed(fake_case,tmp_path):
    root=fake_case();lock=root/'runtime/.run-manager-lock';lock.write_text('owned by another manager')
    m=manager_for(root);m.prepare();finish(m)
    assert m.state==RunState.FAILED and lock.read_text()=='owned by another manager'
    assert not (root/'preparation_result.json').exists(),'Must not write another manager’s case result'
    outside=APP_ROOT/'app/tests/fixtures'
    with pytest.raises(ValueError):RunManager(outside)


def test_executed_case_refusal_is_readonly(fake_case):
    root=fake_case();(root/'runtime/attempts.jsonl').write_text('old runtime must stay unchanged')
    before={str(p.relative_to(root)):p.read_bytes()for p in root.rglob('*')if p.is_file()}
    m=manager_for(root);m.prepare();finish(m);assert m.state==RunState.FAILED
    assert before=={str(p.relative_to(root)):p.read_bytes()for p in root.rglob('*')if p.is_file()}


@pytest.mark.smoke
def test_recycled_pid_identity_never_signaled():
    dummy=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'],start_new_session=True)
    try:
        owner=OwnedProcesses();owner.identities[dummy.pid]=psutil.Process(dummy.pid).create_time()+1
        owner.groups[dummy.pid]=dummy.pid
        owner.stop(.05)
        assert dummy.poll()is None and owner.signaled==[]
    finally:dummy.terminate();dummy.wait(timeout=5)


@pytest.mark.smoke
def test_abort_cleanup_failure_never_claims_aborted(fake_case):
    m=manager_for(fake_case())
    for state in ['VALIDATED','PREFLIGHT_PASSED','PREPARING','PREPARED','STARTING','HANDSHAKING','RUNNING']:m.machine.transition(state)
    class UnstoppableFakeOwner:
        def stop(self,grace):raise RuntimeError('Own processes remain after abort: TEST_ONLY')
    m.owner=UnstoppableFakeOwner();m._cleanup_abort()
    assert m.state==RunState.FAILED and m.first_failure['phase']=='abort_cleanup'


def test_failed_prepare_missing_fields_never_enables_run(fake_case):
    root=fake_case();launch=json.loads((root/'launch_manifest.json').read_text())
    launch['fluid'][0]['prepare_command']=[sys.executable,'-c','print("fake zero exit, missing fields")']
    write(root/'launch_manifest.json',launch);m=manager_for(root);m.prepare();finish(m)
    assert m.state==RunState.FAILED
    with pytest.raises(ValueError):m.run()


def test_manifest_changed_after_prepare_refuses_launch(fake_case):
    m=prepared(fake_case());launch=json.loads((m.root/'launch_manifest.json').read_text());launch['fluid'][0]['command'].append('changed')
    write(m.root/'launch_manifest.json',launch);m.run();finish(m)
    assert m.state==RunState.FAILED and not m.records


@pytest.mark.smoke
def test_progress_trial_attempts_eta_and_ring_bounds():
    clock=[0.];m=RunMonitor(100,.0004,30,history_limit=10,clock=lambda:clock[0])
    m.consume(MonitorEvent('rejected_attempt','Structure',window=1,iteration=1));assert m.snapshot()['progress']==0
    for w in range(1,26):
        clock[0]+=2;m.consume(MonitorEvent('accepted_window','Structure',30+w*.0004,w,2,{'force_residual':.001,'displacement_residual':.002}))
        if w<20:assert m.snapshot()['eta_estimate_s']is None
    assert m.snapshot()['eta_estimate_s']==pytest.approx(150)
    assert len(m.history)==10 and m.snapshot()['progress']==.25
    with pytest.raises(ValueError):m.consume(MonitorEvent('accepted_window','Structure',30.001,25,2,{'force_residual':0,'displacement_residual':0}))


@pytest.mark.smoke
def test_log_tail_transient_storage_error_preserves_offset(fake_case,monkeypatch):
    import errno
    root=fake_case();m=manager_for(root);m.monitor=RunMonitor(5,.0004,30)
    m.records={'Fluid-S1':{'handshake':False,'status':'STARTING'}}
    p=root/'runtime/test-tail.txt';p.write_text('Primary ranks are connected\nCourant Number mean: .1 max: .8\n')
    stream={'file':p.open('rb',buffering=0),'offset':0,'buffer':LineBuffer(),'parser':FluidParser('Fluid-S1'),'final':False,'read_warning':False}
    original=os.pread;calls=[0]
    def interrupted(*args):
        calls[0]+=1
        if calls[0]==1:raise OSError(errno.ENODATA,'No data available')
        return original(*args)
    monkeypatch.setattr(os,'pread',interrupted)
    try:
        m._tail('Fluid-S1',stream);assert stream['offset']==0 and not m.records['Fluid-S1']['handshake']
        m._tail('Fluid-S1',stream,final=True)
        assert m.records['Fluid-S1']['handshake'] and m.monitor.co['Fluid-S1']==.8
        assert stream['offset']==p.stat().st_size
    finally:stream['file'].close()


def test_gui_event_loop_responsive_and_close_aborts_owned(fake_case):
    from viv_app.ui.main_window import MainWindow
    app=QApplication.instance()or QApplication([]);window=MainWindow();window.show()
    root=fake_case('hang',.03);window.generated=root;window.attach_run_manager(root)
    window.run_manager.gate=FakeGate();window.run_manager.options=RunOptions(2,.1,30,.01,.05)
    beats=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:beats.append(1));timer.start()
    def await_condition(condition,timeout=45000):
        loop=QEventLoop();poll=QTimer();poll.setInterval(10);deadline=time.monotonic()+timeout/1000
        poll.timeout.connect(lambda:loop.quit()if condition()or time.monotonic()>deadline else None);poll.start();loop.exec();poll.stop();assert condition()
    try:
        assert not window.run_page.run.isEnabled()
        window.start_prepare();await_condition(lambda:not window.run_manager.busy)
        window.refresh_run_controls();assert window.run_page.run.isEnabled() and len(beats)>5
        window.start_run();await_condition(lambda:window.run_manager.state==RunState.RUNNING)
        assert window.run_page.abort.isEnabled()
        window.close();await_condition(lambda:not window.run_manager.busy)
        window.refresh_run_controls();assert window.run_manager.state==RunState.ABORTED and not window.isVisible()
        assert len(beats)>10
    finally:
        timer.stop()
        if window.run_manager.busy:window.run_manager.abort();finish(window.run_manager)
        window.close();app.processEvents()
