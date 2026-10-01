"""OFFLINE TEST ONLY. Emits NM12 grammar; never imports any CFD/FSI library."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

p=argparse.ArgumentParser();p.add_argument('--name');p.add_argument('--prepare',action='store_true');p.add_argument('--mode',default='normal');p.add_argument('--delay',type=float,default=.01);args=p.parse_args()
if args.prepare:
    for r in range(4):
        base=Path(f'processor{r}');(base/'constant/polyMesh').mkdir(parents=True)
        for n in ['points','faces','owner','neighbour','boundary']:(base/'constant/polyMesh'/n).write_text('FAKE ONLY')
        (base/'30').mkdir()
        for n in ['U','U_0','p','phi','k','omega','nut','pointDisplacement']:(base/'30'/n).write_text('FAKE ONLY')
    time.sleep(args.delay);print('Fake decomposition complete',flush=True);sys.exit(0)

if args.mode=='nonzero'and args.name=='Fluid-S3':print('FOAM FATAL ERROR: fake intentional failure',flush=True);sys.exit(17)
if args.mode=='stderr'and args.name=='Fluid-S3':print('FOAM FATAL ERROR: fake stderr failure',file=sys.stderr,flush=True);time.sleep(5);sys.exit(2)
if args.mode=='slow':time.sleep(5)
if args.mode=='child':
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
    Path('own_child.pid').write_text(str(child.pid))
if args.mode=='stubborn':
    import signal
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
print('Primary ranks are connected',flush=True)
if args.mode in ('hang','child','stubborn'):time.sleep(30);sys.exit(0)
if args.name!='Structure':
    print('Time = 30.0004',flush=True)
    print('Courant Number mean: 0.03 max: '+('1.4'if args.mode=='co_warning'else '0.88'),flush=True)
    print('Mesh Courant Number mean: 0.001 max: 0.007',flush=True)
    print('time step continuity errors : sum local = 1e-09, global = 2e-10, cumulative = -1.7e-05',flush=True)
    print('GAMG:  Solving for p, Initial residual = 0.15, Final residual = 0.001, No Iterations 7',flush=True)
    time.sleep(args.delay*15);sys.exit(0)

windows=3 if args.mode=='incomplete'else 5
root=Path('..');journal=root/'runtime/accepted_windows.jsonl'
print('unrecognized malformed noise: ignored',flush=True)
attempts=0
for w in range(1,windows+1):
    for iteration in range(1,3):
        attempts+=1
        print(f'it {iteration} (min: 1, max: 50), time-window {w} (max: 5), t {(w-1)*.0004}',flush=True)
        for s in range(1,6):
            for kind in ['Displacement','Force']:
                value='1e-3'if iteration==2 else '0.2'
                print(f'relative convergence measure: relative two-norm diff of data "{kind}-S{s}" = {value}, limit = 5.00e-03, normalization = 1.00e-05, conv = '+('true'if iteration==2 else'false'),flush=True)
        physical=30+w*.0004 if iteration==2 else 30+(w-1)*.0004
        if iteration==2:
            with journal.open('a') as out:out.write(json.dumps({'window':w,'iterations':iteration,'physical_time_s':physical})+'\n');out.flush()
        line=f'NM9_ATTEMPT window={w} iteration={iteration} accepted={int(iteration==2)} physical_time={physical}'
        if args.mode=='partial':
            sys.stdout.write(line[:len(line)//2]);sys.stdout.flush();time.sleep(args.delay)
            print(line[len(line)//2:],flush=True)
        else:print(line,flush=True)
        time.sleep(args.delay)
print(f'NM9_FINAL accepted_windows={windows} attempts={attempts}',flush=True)
