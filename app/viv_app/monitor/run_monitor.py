from collections import deque
import math
import time


class RunMonitor:
    """Committed progress only. UI history is bounded; disk events are complete."""
    def __init__(self,target_windows,dt,start_time,history_limit=500,clock=time.monotonic):
        self.target=target_windows;self.dt=dt;self.start_time=start_time;self.clock=clock
        self.started=clock();self.accepted=0;self.iteration=0;self.window=1;self.rejected=0
        self.physical_time=start_time;self.force=None;self.displacement=None
        self.co={};self.mesh_co={};self.warnings=deque(maxlen=100);self.warning_count=0
        self.history=deque(maxlen=history_limit);self.acceptance_times=deque(maxlen=50)

    def consume(self,event):
        kind=event.event_type;v=event.value
        if kind in ('coupling_iteration','coupling_attempt'):
            self.iteration=event.iteration;self.window=event.window
        elif kind=='accepted_window':
            if event.window!=self.accepted+1 or event.window>self.target:raise ValueError('Out-of-order / excessive accepted window')
            expected=self.start_time+event.window*self.dt
            if not math.isfinite(event.physical_time) or abs(event.physical_time-expected)>1e-8:raise ValueError('Accepted physical time disagrees with fixed dt')
            self.accepted=event.window;self.physical_time=event.physical_time
            self.iteration=event.iteration;self.window=event.window
            self.force=v['force_residual'];self.displacement=v['displacement_residual']
            self.acceptance_times.append((self.accepted,self.clock()))
            self.history.append((self.accepted,self.force,self.displacement,max(self.co.values(),default=0)))
        elif kind=='rejected_attempt':self.rejected+=1
        elif kind in ('force_residual','displacement_residual'):
            if kind=='force_residual':self.force=v['residual']
            else:self.displacement=v['residual']
            self.window=event.window;self.iteration=event.iteration
        elif kind=='courant':self.co[event.participant]=max(v['max'],self.co.get(event.participant,0))
        elif kind=='mesh_courant':self.mesh_co[event.participant]=max(v['max'],self.mesh_co.get(event.participant,0))
        elif kind=='warning':self.warning_count+=1;self.warnings.append(str(v))

    def snapshot(self):
        eta=None
        if self.accepted>=20 and len(self.acceptance_times)>1:
            a,b=self.acceptance_times[0],self.acceptance_times[-1]
            eta=max(0,(b[1]-a[1])/(b[0]-a[0])*(self.target-self.accepted))
        co_slice=max(self.co,key=self.co.get,default=None);mesh_slice=max(self.mesh_co,key=self.mesh_co.get,default=None)
        return {'accepted_windows':self.accepted,'target_windows':self.target,'physical_time':self.physical_time,
            'target_physical_time':self.start_time+self.target*self.dt,'coupled_elapsed':self.accepted*self.dt,
            'target_duration':self.target*self.dt,'progress':min(1,self.accepted/self.target),'iteration':self.iteration,
            'window':self.window,'force_residual':self.force,'displacement_residual':self.displacement,'rollback_count':self.rejected,
            'elapsed_wall_s':self.clock()-self.started,'eta_estimate_s':eta,'eta_status':'ESTIMATE' if eta is not None else 'warming up',
            'max_Co':self.co.get(co_slice),'max_Co_slice':co_slice,'max_mesh_Co':self.mesh_co.get(mesh_slice),'max_mesh_Co_slice':mesh_slice,
            'warning_count':self.warning_count,'warnings':list(self.warnings),'history':list(self.history)}
