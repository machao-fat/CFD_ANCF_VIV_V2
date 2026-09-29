#!/usr/bin/env python3
"""Read-only finite-value audit of OpenFOAM binary final fields."""
from __future__ import annotations
import json, math, re, struct
from pathlib import Path

E=Path(__file__).resolve().parent
LABELS=('s0594','s1782','s2970','s4158','s5346')
FIELDS=('U','p','phi','k','omega','nut','pointDisplacement')
LIST=re.compile(rb'nonuniform\s+List<(scalar|vector)>\s+(\d+)\s*\(')
ASCII_NONFINITE=re.compile(rb'(?<![A-Za-z])(?:nan|[-+]?inf)(?![A-Za-z])',re.I)

def audit(path):
    data=path.read_bytes();masked=bytearray(data);pos=0;lists=[];finite=True;parse_ok=True
    while True:
        m=LIST.search(data,pos)
        if not m:break
        kind=m.group(1).decode();count=int(m.group(2));components=1 if kind=='scalar' else 3
        begin=m.end();end=begin+count*components*8
        if end>len(data) or data[end:end+1]!=b')':
            parse_ok=False;lists.append({'kind':kind,'count':count,'parse_ok':False,'payload_offset':begin});break
        payload=memoryview(data)[begin:end]
        local_finite=all(math.isfinite(x) for (x,) in struct.iter_unpack('<d',payload))
        finite &= local_finite
        masked[begin:end]=b' '*(end-begin)
        lists.append({'kind':kind,'count':count,'finite':local_finite,'parse_ok':True})
        pos=end+1
    ascii_matches=[{'token':m.group().decode(errors='replace'),'offset':m.start()}
                   for m in ASCII_NONFINITE.finditer(masked)]
    if b'format      binary;' in data and b'nonuniform' in data and not lists:parse_ok=False
    finite &= not ascii_matches
    return {'file':str(path),'format_binary':b'binary;' in data[:1000],
            'binary_lists':lists,'binary_values_checked':sum(x['count']*(1 if x['kind']=='scalar' else 3) for x in lists),
            'ascii_nonfinite_tokens_outside_payload':ascii_matches,'parse_ok':parse_ok,'finite':finite}

def main():
    report={};good=True
    for label in LABELS:
        rank={}
        for r in range(4):
            root=E/'launch'/f'fluid_{label}'/f'processor{r}'
            t=max((p for p in root.iterdir() if p.is_dir() and p.name.replace('.','',1).isdigit()),key=lambda p:float(p.name))
            f={name:audit(t/name) for name in FIELDS}
            rank[str(r)]={'final_time_s':float(t.name),'fields':f,'pass':all(x['parse_ok'] and x['finite'] for x in f.values())}
            good &= rank[str(r)]['pass']
        report[label]=rank
    out={'status':'PASS' if good else 'FAIL','method':'Parse OpenFOAM binary scalar/vector lists as little-endian float64 and scan only remaining ASCII for nan/inf',
         'slices':report}
    p=E/'analysis/final_field_binary_finiteness.json';p.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({'status':out['status'],'per_slice':{k:[v[str(r)]['pass'] for r in range(4)] for k,v in report.items()},
                      'values_checked':sum(x['binary_values_checked'] for v in report.values() for r in v.values() for x in r['fields'].values())},indent=2))
    return 0 if good else 1
if __name__=='__main__':raise SystemExit(main())
