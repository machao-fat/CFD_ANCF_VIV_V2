#!/usr/bin/env python3
"""Offline alignment helper for native OpenFOAM force.dat records.

It intentionally refuses to call a timestamp-only match sufficient.  The
caller supplies a Structure attempts JSONL stream containing attemptOrdinal,
window, physical_time_before_s/after_s, and accepted.
"""
from __future__ import annotations
import argparse, json, re
from collections import defaultdict
from pathlib import Path
def native(path):
 rows=[]
 for ordinal,line in enumerate(Path(path).read_text(errors='replace').splitlines()):
  if not line or line.lstrip().startswith('#'): continue
  cols=line.split()
  if len(cols)<10: continue
  try: vals=list(map(float,cols[:10]))
  except ValueError: continue
  rows.append({'native_ordinal':ordinal,'physical_time':vals[0],'total_x':vals[1],'total_y':vals[2],
               'pressure_x':vals[4],'pressure_y':vals[5],'viscous_x':vals[7],'viscous_y':vals[8]})
 return rows
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--native',required=True); ap.add_argument('--attempts',required=True); ap.add_argument('--slice-id',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
 n=native(a.native); attempts=[]
 for line in Path(a.attempts).read_text(errors='replace').splitlines():
  try:
   x=json.loads(line)
   if x.get('F_raw_N') is not None: attempts.append(x)
  except json.JSONDecodeError: pass
 if not n or not attempts: raise SystemExit('alignment blocked: native or accepted attempts empty')
 by_time=defaultdict(list)
 for x in n: by_time[round(x['physical_time'],12)].append(x)
 out=[]; missing=[]; groups=defaultdict(list)
 for x in attempts:
  groups[round(float(x.get('physical_time_after_s',0.0))+30.0,12)].append(x)
 for t,group in groups.items():
  group.sort(key=lambda x:int(x.get('attemptOrdinal',0)))
  choices=by_time.get(t,[])
  if len(choices)<len(group): missing.extend(x.get('attemptOrdinal') for x in group); continue
  for index,x in enumerate(group):
   chosen=choices[index]
   out.append({'slice_id':a.slice_id,'window':x.get('window'),'attemptOrdinal':x.get('attemptOrdinal'),
               'physical_time':chosen['physical_time'],'native_ordinal':chosen['native_ordinal'],
               'pressure_x':chosen['pressure_x'],'pressure_y':chosen['pressure_y'],
               'viscous_x':chosen['viscous_x'],'viscous_y':chosen['viscous_y'],
               'total_x':chosen['total_x'],'total_y':chosen['total_y'],'accepted':bool(x.get('accepted')),
               'alignment_basis':'time+all-attempt ordinal within repeated physical time; not timestamp-only'})
 if missing: raise SystemExit(f'alignment blocked: {len(missing)} attempts unmatched')
 Path(a.out).write_text('\n'.join(json.dumps(x,sort_keys=True) for x in out)+'\n')
 print(json.dumps({'status':'PASS','records':len(out),'slice_id':a.slice_id,'accepted_direct_stream':a.out if False else str(a.out)}))
if __name__=='__main__': main()
