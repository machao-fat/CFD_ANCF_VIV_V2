#!/usr/bin/env python3
"""Correct a provisional ASCII-on-binary field audit; no solver launch."""
import json
from pathlib import Path

E=Path(__file__).resolve().parent
A=E/'analysis';C=E/'comparison'
def load(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')

def main():
    binary=load(A/'final_field_binary_finiteness.json')
    if binary['status']!='PASS':raise RuntimeError('binary audit did not pass')
    health=load(A/'fluid_health.json')
    for label,rankmap in binary['slices'].items():
        for r in range(4):
            record=health['final_fields'][label]['ranks'][r]
            record['provisional_ascii_scan_result']=record.pop('finite_text')
            record['finite_binary_numeric_audit']=rankmap[str(r)]['pass']
            record['finite_audit_method']='OpenFOAM binary scalar/vector float64 decode'
        health['final_fields'][label]['finite_4_of_4']=all(x['finite_binary_numeric_audit'] for x in health['final_fields'][label]['ranks'])
    health['all_final_fields_complete_finite']=all(x['complete_4_of_4'] and x['finite_4_of_4'] for x in health['final_fields'].values())
    health['provisional_ascii_scanner']='FALSE_POSITIVE_ON_BINARY_PAYLOAD'
    write(A/'fluid_health.json',health)
    final=C/'final_classification.json'
    provisional=C/'final_classification.json.provisional_ascii_scan'
    if provisional.exists():raise RuntimeError('provisional archive already exists')
    final.rename(provisional)
    decision=load(provisional)
    decision['gates']['five_final_fields_finite_complete']=health['all_final_fields_complete_finite']
    decision['field_finiteness_evidence']=str(A/'final_field_binary_finiteness.json')
    decision['provisional_ascii_scan_classification_preserved']=str(provisional)
    if all(decision['gates'].values()):
        decision['classification']='V2606_NM12_N5_4RANK_DISTRIBUTED_MAPPING_DIAGNOSTIC100_PASS'
        decision['N5_TARGET_ARCHITECTURE_RUNTIME']='QUALIFIED_SHORT100'
        decision['N5_4RANK_EXECUTION']='DEMONSTRATED_IN_TARGET_ARCHITECTURE'
        decision['authorized_next_action']='NM13_N5_LONG_DURATION_RUN_CONFIGURATION_REVIEW'
    write(final,decision)
    print(json.dumps({'classification':decision['classification'],
                      'failed_gates':[k for k,v in decision['gates'].items() if not v],
                      'participants_relaunched':False},indent=2))
if __name__=='__main__':main()
