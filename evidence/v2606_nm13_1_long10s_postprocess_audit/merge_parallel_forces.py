#!/usr/bin/env python3
"""Sum rank-local OpenFOAM forces into one per-slice direct-force stream."""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path
def rows(path):
 out=[]
 for line in Path(path).read_text(errors='replace').splitlines():
  if not line or line.lstrip().startswith('#'): continue
  c=line.split()
  if len(c)<10: continue
  try: out.append(list(map(float,c[:10])))
  except ValueError: pass
 return out
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--rank-file',action='append',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
 nr=len(a.rank_file); per_rank=[]
 for path in a.rank_file:
  counters=defaultdict(int); keyed=[]
  for r in rows(path):
   t=round(r[0],12); k=counters[t]; counters[t]+=1; keyed.append((t,k,r))
  per_rank.append(keyed)
 if not per_rank or not per_rank[0]: raise SystemExit('no native force rows')
 keys=[(t,k) for t,k,_ in per_rank[0]]
 if any([(t,k) for t,k,_ in rank] != keys for rank in per_rank[1:]):
  raise SystemExit('rank-local force time/duplicate ordinal mismatch')
 out=[]
 for index,(t,k,_) in enumerate(per_rank[0]):
  group=[rank[index][2] for rank in per_rank]
  s=[sum(r[i] for r in group) for i in range(1,10)]
  out.append([t]+s)
 p=Path(a.out); p.write_text('# merged rank-local direct force: time total_xyz pressure_xyz viscous_xyz\n'+'\n'.join(' '.join(f'{v:.17g}' for v in r) for r in out)+'\n')
 print(json.dumps({'status':'PASS','records':len(out),'ranks':nr,'out':str(p)}))
if __name__=='__main__': main()
