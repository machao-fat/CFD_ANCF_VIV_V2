#!/usr/bin/env python3
"""Post-run read-only verification of preserved frozen30 start in all N5 cases."""
import hashlib,json
from pathlib import Path
from prepare_nm12 import E,T
LABELS=('s0594','s1782','s2970','s4158','s5346')
FIELDS=('U','p','phi','k','omega','nut','pointDisplacement')
MESH=('points','faces','owner','neighbour','boundary')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def signature(case,r):
    root=case/f'processor{r}'
    return {'fields':{f:sha(root/T/f) for f in FIELDS},
            'mesh':{f:sha(root/'constant/polyMesh'/f) for f in MESH}}
def main():
    template=E/'launch/frozen30_four_rank_template'
    baseline=[signature(template,r) for r in range(4)]
    cases={}
    for label in LABELS:
        case=E/'launch'/f'fluid_{label}'
        actual=[signature(case,r) for r in range(4)]
        cases[label]={'ranks':4,'same_frozen30_fields_and_mesh_each_rank':actual==baseline,
                      'frozen_time_directory':T}
    passed=all(x['same_frozen30_fields_and_mesh_each_rank'] for x in cases.values())
    out={'status':'PASS' if passed else 'FAIL','scope':'second fresh run preserved initial processor field and mesh files',
         'template':str(template),'not_continuation':True,'cases':cases}
    (E/'identity/second_fresh_five_slice_identity.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({'status':out['status'],'per_slice':{k:v['same_frozen30_fields_and_mesh_each_rank'] for k,v in cases.items()}},indent=2))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
