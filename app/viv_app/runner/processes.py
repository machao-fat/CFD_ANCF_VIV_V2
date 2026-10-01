"""New-process ownership only. Never searches processes by name or system PID list."""
from pathlib import Path
import os
import signal
import subprocess
import time
import psutil


class OwnedProcesses:
    def __init__(self):
        self.roots={};self.identities={};self.groups={};self.handles=[];self.signaled=[]

    def launch(self,name,argv,cwd,environment,stdout,stderr):
        out=Path(stdout).open('wb');err=Path(stderr).open('wb');self.handles.extend([out,err])
        proc=subprocess.Popen(argv,cwd=cwd,env={**os.environ,**environment},stdout=out,stderr=err,start_new_session=True)
        self.roots[name]=proc;self.groups[proc.pid]=proc.pid
        try:self.identities[proc.pid]=psutil.Process(proc.pid).create_time()
        except psutil.NoSuchProcess:pass
        return proc

    def alive_owned(self):
        # Linux children() in psutil builds a global PPID map. Instead read
        # only authenticated own task directories; never enumerate /proc PIDs.
        alive={};pending=list(self.identities);seen=set()
        while pending:
            pid=pending.pop()
            if pid in seen:continue
            seen.add(pid);created=self.identities[pid]
            try:
                p=psutil.Process(pid)
                if p.create_time()!=created or p.status()==psutil.STATUS_ZOMBIE:continue
                alive[pid]=p
                for file in Path(f'/proc/{pid}/task').glob('*/children'):
                    try:children=file.read_text().split()
                    except (FileNotFoundError,ProcessLookupError):continue
                    for child_id in children:
                        child=psutil.Process(int(child_id));child_time=child.create_time()
                        if child.ppid()!=pid or child_time<created:continue
                        self.identities[child.pid]=child_time;pending.append(child.pid)
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        return alive

    def stop(self,grace):
        alive=self.alive_owned()
        # Group signals are allowed only while an authenticated own member is
        # present in the group. A recycled root PID can never authenticate it.
        def send(sig):
            current=self.alive_owned();sent_groups=set()
            for pid,p in current.items():
                try:
                    group=os.getpgid(pid)
                    if group in self.groups and group not in sent_groups:
                        os.killpg(group,sig);sent_groups.add(group);self.signaled.append({'group':group,'signal':sig,'authenticated_member':pid})
                    elif group not in self.groups:
                        if p.create_time()==self.identities[pid]:p.send_signal(sig);self.signaled.append({'pid':pid,'signal':sig})
                except (ProcessLookupError,psutil.NoSuchProcess):pass
        send(signal.SIGTERM)
        deadline=time.monotonic()+grace
        while time.monotonic()<deadline:
            for p in self.roots.values():p.poll()
            if not self.alive_owned():break
            time.sleep(.05)
        if self.alive_owned():send(signal.SIGKILL)
        for p in self.roots.values():
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
        remaining=self.alive_owned()
        pending={p.pid for p in self.roots.values()if p.poll()is None}
        if remaining or pending:raise RuntimeError('Own processes remain after abort: '+str(sorted(set(remaining)|pending)))

    def close(self):
        for handle in self.handles:handle.close()
        self.handles=[]


class ResourceSampler:
    def __init__(self,owner,path,clock=time.monotonic):
        self.owner=owner;self.path=path;self.clock=clock;self.last=clock();self.cpu={}
        psutil.cpu_percent(None)

    def sample(self):
        now=self.clock();elapsed=now-self.last;rss=0;cpu=0;current={}
        for pid,p in self.owner.alive_owned().items():
            try:
                t=p.cpu_times();key=(pid,p.create_time());total=t.user+t.system
                current[key]=total;rss+=p.memory_info().rss
                if key in self.cpu and elapsed>0:cpu+=max(0,total-self.cpu[key])/elapsed*100
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        self.cpu=current;self.last=now;ram=psutil.virtual_memory()
        return {'system_cpu_percent':psutil.cpu_percent(None),'solver_cpu_percent':cpu,'solver_rss_bytes':rss,
            'system_ram_percent':ram.percent,'disk_free_bytes':psutil.disk_usage(str(self.path)).free,
            'cpu_scope':'own PID tree, percent may exceed 100 across cores','ram_scope':'sum RSS includes shared pages'}
