"""Background supervisor + Qt signals. Manifest argv is never assembled by UI.

No restart, continuation, physics changes, or automatic retry. A case is one-shot.
"""
from pathlib import Path
from datetime import datetime,timezone
import json
import threading
import time
import uuid
import math
import traceback
import os
import errno
from PySide6.QtCore import QObject,Signal
from viv_app.generator.case_generator import app_identity
from viv_app.generator.production_preflight import production_preflight
from viv_app.generator.production_validation import validate_production_case
from viv_app.monitor.models import MonitorEvent,LineBuffer,json_value
from viv_app.monitor.structure_parser import StructureParser
from viv_app.monitor.fluid_parser import FluidParser
from viv_app.monitor.run_monitor import RunMonitor
from .state import StateMachine,RunState,ACTIVE
from .contract import load_contract,read,digest,require,fresh_execution,check_decomposition,prepared_identity
from .processes import OwnedProcesses,ResourceSampler
from .config import RunOptions
from viv_app.utils.paths import CASES_ROOT,within


def utc():return datetime.now(timezone.utc).isoformat()
def write(path,value):
    """Atomic case-local JSON record; monitor JSONL itself is append+flush."""
    p=Path(path);temporary=p.with_suffix(p.suffix+'.tmp')
    temporary.write_text(json.dumps(json_value(value),indent=2,allow_nan=False)+'\n');temporary.replace(p)


class Aborted(Exception):pass


class ProductionGate:
    """The only production entry gate. Tests inject an explicit fake gate."""
    def validate(self,root,prepared=False):
        result=validate_production_case(root,write_report=False,prepared=prepared)
        require(result['status']=='PASS',result['first_failure']);return result

    def preflight(self,root,prepared=False):
        result=production_preflight(root,write_report=not prepared,prepared=prepared)
        require(result['status']=='PASS' and result['production_launch_ready'],result['first_failure']);return result

    def contract(self,root):return load_contract(root)
    def decomposition(self,c):return check_decomposition(c)
    def identity(self,c):return prepared_identity(c)
    def fresh(self,c):fresh_execution(c)
    def app_identity(self):return app_identity()


class RunManager(QObject):
    state_changed=Signal(str)
    event=Signal(object)
    snapshot=Signal(object)
    finished=Signal(object)

    def __init__(self,root,options=None,parent=None,*,gate=None):
        super().__init__(parent)
        require(not Path(root).is_symlink(),'Case root symlinks are unsupported')
        self.root=Path(root).resolve()
        require(self.root!=CASES_ROOT and within(self.root,CASES_ROOT) and self.root.is_dir(),'Run Manager case must be inside APP workspace/cases')
        self.options=options or RunOptions.load();self.gate=gate or ProductionGate()
        self.machine=StateMachine();self.thread=None;self.abort_requested=threading.Event()
        self.owner=None;self.monitor=None;self.records={};self.preparation=None
        self.run_dir=None;self.event_file=None;self.first_failure=None;self._lock=threading.Lock();self._final_attempts=None

    @property
    def state(self):return self.machine.state
    @property
    def busy(self):return self.thread is not None and self.thread.is_alive()

    def _state(self,value):
        self.machine.transition(value);self.state_changed.emit(self.state.value)
        self._event(MonitorEvent('run_state',value=self.state.value))

    def _event(self,event):
        data=json_value(event.to_dict())
        if self.event_file:
            self.event_file.write(json.dumps(data,allow_nan=False)+'\n');self.event_file.flush()
        if event.event_type in {'accepted_window','warning','fatal','participant_started','participant_connected',
                                'participant_exit','run_state','prepared_slice','preflight_passed'}:
            self.event.emit(data)

    def _begin(self,action):
        with self._lock:
            require(not self.busy,'Run Manager operation already active')
            self.thread=threading.Thread(target=action,name='viv-case-supervisor',daemon=False)
            self.thread.start()

    def prepare(self):
        require(self.state==RunState.CREATED,'Prepare only from CREATED; failed/aborted handles are never reused')
        self._begin(self._prepare)

    def run(self):
        require(self.state==RunState.PREPARED,'Run requires PREPARED')
        self._begin(self._run)

    def abort(self):
        require(self.state in ACTIVE and self.state!=RunState.ABORTING,'No active run to abort')
        self.abort_requested.set()  # Process control happens only in the supervisor.

    def invalidate(self,reason):
        require(not self.busy,'Cannot invalidate an active operation')
        self._failure(ValueError(reason),'external_validation')

    def _cancelled(self):
        if self.abort_requested.is_set():raise Aborted('ABORTED RUN MAY NOT BE RESTARTABLE')

    def _failure(self,exc,phase):
        if self.first_failure is None:self.first_failure={'phase':phase,'reason':str(exc),'time':utc(),'traceback':traceback.format_exc()}
        self._event(MonitorEvent('fatal',value=self.first_failure))
        if self.state not in (RunState.FAILED,RunState.ABORTED):self._state(RunState.FAILED)

    def _cleanup_abort(self):
        if self.state!=RunState.ABORTING:self._state(RunState.ABORTING)
        try:
            if self.owner:self.owner.stop(self.options.abort_grace_s)
        except Exception as exc:
            self._failure(exc,'abort_cleanup');return
        self._state(RunState.ABORTED)

    def _prepare(self):
        results=[];lock=None
        try:
            self.contract=self.gate.contract(self.root);self.gate.fresh(self.contract)
            lock=self._case_lock()
            static=self.gate.validate(self.root);self._state(RunState.VALIDATED)
            preflight=self.gate.preflight(self.root);self.contract=self.gate.contract(self.root)
            self._state(RunState.PREFLIGHT_PASSED);self._event(MonitorEvent('preflight_passed',value='PASS'))
            for warning in preflight.get('warnings',[]):self._event(MonitorEvent('warning',value=warning))
            self._state(RunState.PREPARING);self.owner=OwnedProcesses()
            logdir=self.root/'runtime/logs';logdir.mkdir(exist_ok=True)
            for row in self.contract.launch['fluid']:
                self._cancelled();name=row['participant'];cwd=self.root/row['cwd']
                require(not list(cwd.glob('processor*')),'Existing processors refused; no hidden re-decomposition')
                stdout=logdir/f'{name}.decompose.log';stderr=logdir/f'{name}.decompose.stderr.log'
                proc=self.owner.launch(name,row['prepare_command'],cwd,row['environment'],stdout,stderr)
                start=time.monotonic()
                while proc.poll() is None:
                    self.owner.alive_owned();self._cancelled()
                    require(time.monotonic()-start<self.options.prepare_timeout_s,'Decomposition timeout: '+name)
                    time.sleep(self.options.poll_interval_s)
                result={'participant':name,'pid':proc.pid,'exit_code':proc.returncode,'command':row['prepare_command'],
                        'cwd':str(cwd),'environment':row['environment'],'stdout_log':str(stdout),'stderr_log':str(stderr)}
                results.append(result);require(proc.returncode==0,'Decomposition failed: '+name)
                self._event(MonitorEvent('prepared_slice',name,value='exit=0'))
            self._cancelled()
            topology=self.gate.decomposition(self.contract)
            identity=self.gate.identity(self.contract)
            self.preparation={'status':'PASS','time':utc(),'static_validation':static,'production_preflight':preflight,
                              'decomposition_results':results,'processor_checks':topology,'input_identity':identity,
                              'launch_manifest_sha256':digest(self.root/'launch_manifest.json'),'app':self.gate.app_identity()}
            write(self.root/'preparation_result.json',self.preparation);self._state(RunState.PREPARED)
        except Aborted:
            self._cleanup_abort();write(self.root/'preparation_result.json',{'status':'ABORTED'if self.state==RunState.ABORTED else'FAIL','first_failure':self.first_failure,'decomposition_results':results})
        except Exception as exc:
            self._failure(exc,'prepare')
            if self.owner:self.owner.stop(self.options.abort_grace_s)
            if lock:write(self.root/'preparation_result.json',{'status':'FAIL','first_failure':self.first_failure,'decomposition_results':results})
        finally:
            if self.owner:self.owner.close()
            self.owner=None
            if lock:lock.unlink(missing_ok=True)
            self.finished.emit({'operation':'prepare','state':self.state.value,'first_failure':self.first_failure})

    def _case_lock(self):
        # Atomic and no stale-lock recovery: never seize another manager's case.
        require(not (self.root/'runtime').is_symlink() and within((self.root/'runtime').resolve(),self.root),'Runtime must be case local')
        p=self.root/'runtime/.run-manager-lock'
        with p.open('x') as out:out.write(json.dumps({'APP':'VIV_RUN_MANAGER','time':utc()}))
        return p

    def _run(self):
        lock=None;streams={};sampler=None;started=None;provenance={}
        try:
            lock=self._case_lock()
            c=self.gate.contract(self.root);self.gate.fresh(c)
            self.gate.validate(self.root,prepared=True)
            preflight=self.gate.preflight(self.root,prepared=True)
            self.gate.decomposition(c)
            prep=read(self.root/'preparation_result.json')
            require(prep['status']=='PASS' and prep==self.preparation,'Preparation record changed / not owned by this manager')
            require(prep['launch_manifest_sha256']==digest(self.root/'launch_manifest.json'),'Launch manifest changed after Prepare')
            require(prep['input_identity']==self.gate.identity(c),'Prepared inputs changed after Prepare')
            require(prep['app']['source_hashes']==self.gate.app_identity()['source_hashes'],'APP source changed after Prepare')
            self._cancelled();self._state(RunState.STARTING)
            self.contract=c;run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')+'_'+uuid.uuid4().hex[:8]
            self.run_dir=self.root/'runtime'/('run_'+run_id);self.run_dir.mkdir()
            self.event_file=(self.run_dir/'runtime_monitor.jsonl').open('a',encoding='utf-8')
            started=utc();self.owner=OwnedProcesses();self.monitor=RunMonitor(c.target_windows,c.generation['deltaT'],float(c.baseline['initial_time_default']))
            provenance={'run_id':run_id,'start_time':started,'APP':self.gate.app_identity(),'profile_sha256':digest(Path(c.baseline['profile_descriptor'])) if 'profile_descriptor'in c.baseline else digest(self.root/'baseline_contract_snapshot.json'),
                        'profile':c.generation['contract_profile'],'case_generation_manifest':c.generation,'preflight_result':preflight,
                        'decomposition_result':prep,'launch_manifest':c.launch,'launch_manifest_sha256':digest(self.root/'launch_manifest.json')}
            provenance['run_options']=self.options.__dict__
            # Enrolled profile identity is the file originally imported by APP.
            from viv_app.generator.production_baseline import PROFILE_ROOT
            provenance['profile_sha256']=digest(PROFILE_ROOT/'app_baseline.json')
            write(self.run_dir/'run_manifest.json',provenance)
            self._event(MonitorEvent('run_state',value=RunState.STARTING.value))
            logdir=self.root/'runtime/logs';logdir.mkdir(exist_ok=True)
            for row in c.participants:
                self._cancelled();name=row['participant'];stdout=logdir/f'{name}.log';stderr=logdir/f'{name}.stderr.log'
                require(not stdout.exists() and not stderr.exists(),'Participant logs already exist; no overwrite / restart')
                proc=self.owner.launch(name,row['command'],self.root/row['cwd'],row['environment'],stdout,stderr)
                self.records[name]={'name':name,'PID':proc.pid,'command':row['command'],'cwd':str(self.root/row['cwd']),
                    'environment':row['environment'],'cpu_affinity_contract':row['cpu_set'],'start_time':utc(),'status':'STARTING',
                    'exit_code':None,'stdout_log':str(stdout),'stderr_log':str(stderr),'handshake':False}
                parser=StructureParser() if name=='Structure'else FluidParser(name)
                for file in (stdout,stderr):streams[(name,str(file))]={'file':file.open('rb',buffering=0),'offset':0,'buffer':LineBuffer(),'parser':parser,'final':False,'read_warning':False}
                self._event(MonitorEvent('participant_started',name,value=self.records[name]))
                write(self.run_dir/'participants.json',self.records)
            self._state(RunState.HANDSHAKING)
            deadline=time.monotonic()+self.options.startup_timeout_s
            sampler=ResourceSampler(self.owner,self.root);last_sample=0
            while True:
                self._cancelled()
                for (name,_),stream in streams.items():self._tail(name,stream)
                # Reap and fully drain completed stdout/stderr before judging
                # handshake or target windows: final lines can arrive with exit.
                for name,proc in self.owner.roots.items():
                    code=proc.poll()
                    if code is not None and self.records[name]['exit_code'] is None:
                        for (participant,_),s in streams.items():
                            if participant==name:self._tail(name,s,final=True)
                        self.records[name].update(exit_code=code,end_time=utc(),status='EXITED'if code==0 else'FAILED')
                        self._event(MonitorEvent('participant_exit',name,value={'exit_code':code}))
                        if code!=0:self.first_failure=self.first_failure or {'participant':name,'reason':'Nonzero participant exit','exit_code':code,'time':utc()}
                if self.first_failure:raise RuntimeError(self.first_failure['reason'])
                if self.state==RunState.HANDSHAKING:
                    if all(r['handshake']for r in self.records.values()):
                        self._state(RunState.RUNNING)
                        for r in self.records.values():
                            if r['exit_code'] is None:r['status']='RUNNING'
                    else:require(time.monotonic()<deadline,'STARTUP_TIMEOUT: six-participant handshake incomplete')
                now=time.monotonic()
                if now-last_sample>=self.options.sample_interval_s:
                    resources=sampler.sample();self._event(MonitorEvent('resources',value=resources))
                    self.snapshot.emit(json_value({**self.monitor.snapshot(),'resources':resources,'participants':self.records.copy(),'state':self.state.value}))
                    write(self.run_dir/'participants.json',self.records);last_sample=now
                if all(r['exit_code'] is not None for r in self.records.values()):
                    require(all(r['handshake']for r in self.records.values()),'FAILED_STARTUP: participants exited before handshake')
                    require(self.monitor.accepted==c.target_windows,'FAILED_INCOMPLETE: target accepted windows not reached')
                    journal=self.root/'runtime/accepted_windows.jsonl'
                    # Cross-check committed journal; never infer success solely
                    # from GUI progress or six zero process exit codes.
                    count=0
                    with journal.open() as source:
                        for line in source:
                            if not line.strip():continue
                            count+=1;record=json.loads(line)
                            require(record['window']==count and abs(record['physical_time_s']-(self.monitor.start_time+count*self.monitor.dt))<1e-8,'Committed journal order / clock mismatch')
                    require(count==c.target_windows,'FAILED_INCOMPLETE: committed accepted journal differs')
                    require(self.monitor.rejected+self.monitor.accepted==self._final_attempts,'Structure final attempt count / monitor disagreement')
                    require(not self.owner.alive_owned(),'Own child processes remain after participant exits')
                    self._state(RunState.COMPLETED);break
                time.sleep(self.options.poll_interval_s)
        except Aborted:
            self._cleanup_abort()
        except Exception as exc:
            self._failure(exc,'run')
            if self.owner:self.owner.stop(self.options.abort_grace_s)
        finally:
            if self.owner:
                for n,p in self.owner.roots.items():
                    if n in self.records:
                        self.records[n]['exit_code']=p.poll()
                        if self.state==RunState.ABORTED:self.records[n]['status']='ABORTED'
                        elif p.poll() is not None:self.records[n]['status']='EXITED'if p.returncode==0 else'FAILED'
                        self.records[n].setdefault('end_time',utc())
                self.owner.close()
            for stream in streams.values():stream['file'].close()
            if self.run_dir:
                result={'final_state':self.state.value,'start_time':started,'end_time':utc(),'case_path':str(self.root),
                    'abort_requested':self.abort_requested.is_set(),
                    'abort_status':self.state==RunState.ABORTED,'abort_message':'ABORTED RUN MAY NOT BE RESTARTABLE'if self.state==RunState.ABORTED else None,
                    'first_failure':self.first_failure,'participants':self.records,'monitor':self.monitor.snapshot()if self.monitor else None,
                    'owned_pid_creation_times':dict(self.owner.identities)if self.owner else {},
                    'process_control_actions':self.owner.signaled if self.owner else [],'real_fsi_started':isinstance(self.gate,ProductionGate) and bool(self.records)}
                write(self.run_dir/'participants.json',self.records);write(self.run_dir/'run_result.json',result)
                if self.monitor:
                    provenance.update(end_time=result['end_time'],final_state=self.state.value,participants=self.records,
                        accepted_windows=self.monitor.accepted,target_windows=self.contract.target_windows,
                        rollback_count=self.monitor.rejected,abort_status=result['abort_status'],warnings=list(self.monitor.warnings),
                        max_Co=result['monitor']['max_Co'],max_mesh_Co=result['monitor']['max_mesh_Co'],exit_codes={n:r['exit_code']for n,r in self.records.items()})
                write(self.run_dir/'run_manifest.json',provenance)
                write(self.root/'run_result.json',result)
            elif lock:
                write(self.root/'run_result.json',{'final_state':self.state.value,'first_failure':self.first_failure,'real_fsi_started':False})
            if self.event_file:self.event_file.close();self.event_file=None
            self.owner=None
            if lock:lock.unlink(missing_ok=True)
            if self.monitor:self.snapshot.emit(json_value({**self.monitor.snapshot(),'participants':self.records,'state':self.state.value}))
            self.finished.emit({'operation':'run','state':self.state.value,'first_failure':self.first_failure})

    def _tail(self,name,stream,final=False):
        if stream['final']:return
        deadline=time.monotonic()+self.options.log_drain_timeout_s
        while True:
            try:
                size=os.fstat(stream['file'].fileno()).st_size
                require(size>=stream['offset'],'Participant log was truncated during observation')
                # Explicit offsets avoid buffered read-ahead beyond an actively
                # appended DrvFS file. Never advance the cursor on a failed read.
                available=size-stream['offset']
                data=os.pread(stream['file'].fileno(),min(65536,available),stream['offset']) if available else b''
            except OSError as exc:
                if exc.errno!=errno.ENODATA:raise
                if not stream['read_warning']:
                    self._event(MonitorEvent('warning',name,value='Transient ENODATA while tailing appended log; unchanged offset, awaiting data'))
                    stream['read_warning']=True
                if not final:return
                require(time.monotonic()<deadline,'LOG_DRAIN_FAILED: ENODATA persists after participant exit')
                time.sleep(.025);continue
            stream['offset']+=len(data)
            if data:stream['read_warning']=False
            for line in stream['buffer'].feed(data,final=final and not data):
                for event in stream['parser'].parse(line):self._observe(event)
            if not final or not data:break
        if final:stream['final']=True

    def _observe(self,event):
        if event.event_type=='accepted_window':
            require(event.value['residuals_complete'] and event.value['qualified_residuals_converged'],
                    'Accepted marker without ten qualified converged residuals')
        if event.event_type=='participant_connected':
            self.records[event.participant].update(handshake=True,status='CONNECTED')
        if event.event_type=='structure_final':
            require(event.value['accepted_windows']==self.contract.target_windows,'FAILED_INCOMPLETE: target accepted windows not reached (Structure final)')
            self._final_attempts=event.value['attempts']
        if event.event_type=='fatal':
            self.first_failure=self.first_failure or {'participant':event.participant,'window':event.window,'iteration':event.iteration,'reason':str(event.value),'time':utc()}
        self.monitor.consume(event);self._event(event)
