"""Offline presentation fixtures. No real manager, solver argv or processes."""
from pathlib import Path
from types import SimpleNamespace
import json
import threading
from viv_app.generator.foam_dict import FoamDict
from viv_app.generator.production_baseline import PROFILE_ROOT, STRUCTURE
from viv_app.runner.contract import digest
from viv_app.runner.state import RunState
from viv_app.monitor.models import MonitorEvent
from viv_app.monitor.run_monitor import RunMonitor


def production_view(root):
    root = Path(root); fluid = root/'reference_fluid'; (fluid/'system').mkdir(parents=True, exist_ok=True)
    (fluid/'system/decomposeParDict').write_text('numberOfSubdomains 4;')
    descriptor = json.loads((PROFILE_ROOT/'app_baseline.json').read_text())
    return SimpleNamespace(root=PROFILE_ROOT, fluid=fluid, descriptor=descriptor,
        times=[descriptor['initial_time_default']], structure=STRUCTURE,
        model=SimpleNamespace(length_m=STRUCTURE.length_m, elements=STRUCTURE.elements),
        manifest=SimpleNamespace(ns=5, active_start_m=0., active_end_m=5.94, reconstruction_mode='PiecewiseLinearDistributed'),
        controls=FoamDict(b'deltaT 0.0004; endTime 30.002; writeInterval 5; writeControl timeStep; purgeWrite 1;'), inlet_speed=.31)


class PreviewManager:
    """State-only UI fixture; any action is recorded, never starts a process."""
    def __init__(self, root, state=RunState.PREPARED, busy=False):
        self.root = Path(root)/'offline_view_case'; self.root.mkdir(exist_ok=True)
        (self.root/'launch_manifest.json').write_text('{"OFFLINE_PRESENTATION_ONLY":true}')
        self.preparation = {'launch_manifest_sha256': digest(self.root/'launch_manifest.json')}
        self.state = state; self.busy = busy; self.abort_requested = threading.Event(); self.calls = []

    def prepare(self): self.calls.append('prepare')
    def run(self): self.calls.append('run')
    def abort(self): self.calls.append('abort'); self.abort_requested.set()
    def invalidate(self, reason): self.calls.append(('invalidate', reason)); self.state = RunState.FAILED
    def deleteLater(self): pass


def snapshot(accepted=3, state='RUNNING'):
    clock = [0.]; monitor = RunMonitor(5, .0004, 30., clock=lambda: clock[0])
    for i in range(1, 6):
        monitor.consume(MonitorEvent('courant', f'Fluid-S{i}', value={'max': .58+.06*i}))
        monitor.consume(MonitorEvent('mesh_courant', f'Fluid-S{i}', value={'max': .002+.001*i}))
    for w in range(1, accepted+1):
        for attempt in range(3): monitor.consume(MonitorEvent('rejected_attempt', 'Structure', window=w, iteration=attempt+1))
        clock[0] += 14
        monitor.consume(MonitorEvent('accepted_window', 'Structure', 30+w*.0004, w, 7,
            {'force_residual': .0036/w, 'displacement_residual': .0018/w}))
    if 0 < accepted < 5:
        monitor.consume(MonitorEvent('coupling_iteration', 'Structure', window=accepted+1, iteration=2))
    data = monitor.snapshot(); data['state'] = state
    data['participants'] = {name: {'status': 'RUNNING' if state=='RUNNING' else 'WAITING',
        'PID': 'OFFLINE', 'exit_code': None, 'stdout_log': f'/offline-preview/{name}.log',
        'command': ['OFFLINE_ONLY_NO_SOLVER'], 'cwd': '/offline-preview'} for name in ['Structure', *[f'Fluid-S{i}' for i in range(1, 6)]]}
    data['resources'] = {'solver_cpu_percent': 1260., 'solver_rss_bytes': 920*2**20,
        'system_cpu_percent': 52.8, 'system_ram_percent': 43.2, 'disk_free_bytes': 248*2**30}
    if accepted == 0:
        data['max_Co'] = None; data['max_Co_slice'] = None
        data['max_mesh_Co'] = None; data['max_mesh_Co_slice'] = None; data['resources'] = None
    return data
