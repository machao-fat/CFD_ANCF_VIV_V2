"""NM12 NM9_ATTEMPT/NM9_FINAL and preCICE 3.4.1 output grammar."""
import math
import re
from .models import MonitorEvent

ANSI = re.compile(r'\x1b\[[0-9;]*m')
NUMBER = r'(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|[-+]?inf|nan)'
HANDSHAKE=re.compile(r'(?:\(0\) \d{2}:\d{2}:\d{2} \[impl::ParticipantImpl\]:\d+ in setupCommunication:\s*)?Primary ranks are connected')


class StructureParser:
    def __init__(self):
        self.window = 1
        self.iteration = 1
        self.residuals = {'Force':{}, 'Displacement':{}}

    def parse(self, line):
        line = ANSI.sub('',line).strip()
        events = []
        def event(kind, value=None, **kw):
            events.append(MonitorEvent(kind,'Structure',window=self.window,iteration=self.iteration,value=value,**kw))
        if HANDSHAKE.fullmatch(line):event('participant_connected')
        if 'WARNING:' in line or line.startswith('APP_MONITOR_'):event('warning',line)
        if 'NM9_STRUCTURE_FATAL' in line or 'ERROR:' in line:event('fatal',line)
        m = re.search(r'\bit (\d+) \(min: \d+, max: \d+\), time-window (\d+) \(max: \d+\), t ('+NUMBER+r')',line)
        if m:
            self.iteration,self.window=int(m[1]),int(m[2])
            event('coupling_iteration',{'coupled_time':float(m[3])})
        m = re.search(r'relative convergence measure: relative two-norm diff of data "(Force|Displacement)-S([1-5])" = ('+NUMBER+r'), limit = ('+NUMBER+r'), normalization = ('+NUMBER+r'), conv = (true|false)$',line)
        if m:
            kind,slice_id=m[1],int(m[2]);v=float(m[3]);limit=float(m[4]);normalization=float(m[5]);converged=m[6]=='true'
            self.residuals[kind][slice_id]={'residual':v,'valid':converged and not math.isnan(v) and
                (math.isfinite(v) and 0<=v<=limit or math.isinf(v) and v>0 and normalization==0)}
            event('force_residual' if kind=='Force' else 'displacement_residual',
                  {'slice':slice_id,'residual':v,'limit':float(m[4]),'converged':m[6]=='true'})
        m = re.fullmatch(r'NM9_ATTEMPT window=(\d+) iteration=(\d+) accepted=([01]) physical_time=('+NUMBER+r')',line)
        if m:
            self.window,self.iteration=int(m[1]),int(m[2]);physical=float(m[4])
            if not math.isfinite(physical):event('fatal','Nonfinite NM9 physical time')
            else:
                event('coupling_attempt',{'accepted':m[3]=='1'},physical_time=physical)
                if m[3]=='1':
                    complete=all(len(v)==5 for v in self.residuals.values())
                    event('accepted_window',{'iterations':self.iteration,'residuals_complete':complete,
                        'qualified_residuals_converged':complete and all(r['valid'] for values in self.residuals.values()for r in values.values()),
                        'force_residual':max((r['residual']for r in self.residuals['Force'].values()),default=None),
                        'displacement_residual':max((r['residual']for r in self.residuals['Displacement'].values()),default=None)},physical_time=physical)
                else:event('rejected_attempt',physical_time=physical)
            self.residuals={'Force':{},'Displacement':{}}
            # advance() logs the upcoming preCICE iteration before the native
            # NM9 marker logs the just-finished attempt. Subsequent residuals
            # therefore belong to the next attempt, not the closing marker.
            self.window+=1 if m[3]=='1'else 0
            self.iteration=1 if m[3]=='1'else self.iteration+1
        m=re.fullmatch(r'NM9_FINAL accepted_windows=(\d+) attempts=(\d+)',line)
        if m:event('structure_final',{'accepted_windows':int(m[1]),'attempts':int(m[2])})
        if line.startswith('NM9_ATTEMPT') and not re.fullmatch(r'NM9_ATTEMPT window=\d+ iteration=\d+ accepted=[01] physical_time='+NUMBER,line):
            event('fatal','Malformed authoritative NM9_ATTEMPT: '+line)
        return events
