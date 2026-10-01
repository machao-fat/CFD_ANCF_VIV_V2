"""OpenFOAM v2606 Info output grammar, independent of GUI."""
import math
import re
from .models import MonitorEvent
from .structure_parser import ANSI,NUMBER,HANDSHAKE


class FluidParser:
    def __init__(self, participant):
        self.participant=participant
        self.time=None

    def parse(self,line):
        line=ANSI.sub('',line).strip();events=[]
        def event(kind,value=None):events.append(MonitorEvent(kind,self.participant,self.time,value=value))
        if HANDSHAKE.fullmatch(line):event('participant_connected')
        if 'FOAM FATAL' in line or re.search(r'sigFpe::sigHandler|negative (?:cell )?volume|Floating point exception|\b(?:nan|[-+]?inf)\b',line,re.I):event('fatal',line)
        if 'FOAM Warning' in line or line.startswith('APP_MONITOR_'):event('warning',line)
        m=re.fullmatch(r'Time = ('+NUMBER+r')',line)
        if m:
            self.time=float(m[1]);event('fluid_time',self.time)
        m=re.fullmatch(r'(Mesh )?Courant Number mean: ('+NUMBER+r') max: ('+NUMBER+r')',line)
        if m:
            values={'mean':float(m[2]),'max':float(m[3])}
            if not all(math.isfinite(v) for v in values.values()):event('fatal','Nonfinite Courant number')
            else:
                event('mesh_courant' if m[1] else 'courant',values)
                if values['max']>1:event('warning',('Mesh 'if m[1]else '')+'Co exceeds 1: '+m[3])
        m=re.fullmatch(r'time step continuity errors : sum local = ('+NUMBER+r'), global = ('+NUMBER+r'), cumulative = ('+NUMBER+r')',line)
        if m:event('continuity',dict(zip(['sum_local','global','cumulative'],map(float,m.groups()))))
        m=re.fullmatch(r'([^:]+):\s+Solving for ([^,]+), Initial residual = ('+NUMBER+r'), Final residual = ('+NUMBER+r'), No Iterations (\d+)',line)
        if m:event('solver_residual',{'solver':m[1],'field':m[2],'initial':float(m[3]),'final':float(m[4]),'iterations':int(m[5])})
        return events
