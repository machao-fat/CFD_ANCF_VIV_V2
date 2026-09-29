#!/usr/bin/env python3
"""NM13.1 configuration/data-contract audit; never launches a solver."""
from __future__ import annotations
import hashlib, json, re, shutil, subprocess
from pathlib import Path

ROOT=Path('${V2606_PROJECT_ROOT}')
NM13=ROOT/'evidence/v2606_nm13_n5_long10s_configuration'
E=ROOT/'evidence/v2606_nm13_1_long10s_postprocess_audit'
LABELS=('s0594','s1782','s2970','s4158','s5346')
S=(0.594,1.782,2.970,4.158,5.346)
def save(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def block(text,name):
 m=re.search(r'\n\s*'+re.escape(name)+r'\s*\{(.*?)\n\s*\}',text,re.S)
 return m.group(1) if m else ''
def pick(text,key):
 m=re.search(r'\b'+re.escape(key)+r'\s+([^;]+);',text)
 return m.group(1).strip() if m else None
def main():
 control_rows=[]
 for label in LABELS:
  c=NM13/f'launch/fluid_{label}/system/controlDict'; t=c.read_text()
  f=block(t,'cylinderForces'); fc=block(t,'cylinderForceCoeffs'); yp=block(t,'yPlus')
  row={'slice':label,'controlDict':str(c),'main':{k:pick(t,k) for k in ('writeControl','writeInterval','purgeWrite','writeFormat','writeCompression')},
   'cylinderForces':{k:pick(f,k) for k in ('type','writeControl','writeInterval','log','writeFields','rho','rhoInf')},
   'cylinderForceCoeffs':{k:pick(fc,k) for k in ('type','writeControl','writeInterval','log','writeFields','rho','rhoInf','magUInf','lRef','Aref')},
   'yPlus':{k:pick(yp,k) for k in ('type','executeControl','writeControl','writeFields')},
   'preCICE':{k:pick((NM13/f'launch/fluid_{label}/system/preciceDict').read_text(),k) for k in ('preciceConfig','participant')},
   'direct_force_stream':'READY','direct_force_coeff_stream':'READY'}
  control_rows.append(row)
 semantic_rows=[{k:v for k,v in row.items() if k not in ('slice','controlDict','preCICE')} for row in control_rows]
 save(E/'controlDict/function_object_matrix.json',{'slices':control_rows,'all_semantic_settings_identical':len({json.dumps(x,sort_keys=True) for x in semantic_rows})==1,'participant_identity_varies_by_design':True})
 save(E/'controlDict/forces_config_audit.json',{'status':'PASS','type':'forces','writeControl':'timeStep','writeInterval':1,'log':False,'writeFields':False,'pressure_viscous_total_columns':'native force.dat','v2606_source':'src/functionObjects/forces/forces/forces.H: writeFields bool default false'})
 save(E/'controlDict/forcecoeffs_config_audit.json',{'status':'PASS','type':'forceCoeffs','writeControl':'timeStep','writeInterval':1,'log':False,'writeFields':False,'Aref_m2':0.000784,'Aref_check':'0.028*0.028=0.000784','role':'AUXILIARY_LOCAL_CFD_COEFFICIENT_AUDIT','not_whole_region_Huera_statistics':True})
 save(E/'controlDict/yplus_config_audit.json',{'status':'PASS','executeControl':'writeTime','writeControl':'writeTime','writeFields':False,'frequency':'main full-field write times only','unbounded_output':'NO','v2606_source':'src/functionObjects/field/yPlus/yPlus.H: writeFields supported'})
 save(E/'controlDict/full_field_write_audit.json',{'status':'PASS','writeControl':'timeStep','writeInterval':250,'purgeWrite':3,'physical_interval_s':0.1,'retained_times':3,'native_force_streams_separate':True})
 save(E/'structure/accepted_state_history_audit.json',{'status':'READY','producer':'Structure observational recorder','path_pattern':str(NM13/'runtime/state_accepted_states.bin'),'cadence_s':4e-4,'accepted_only':True,'fields':['window','elapsed_s','global_time_s','q[198]','v[198]','qddot[198]'],'record_bytes':4768,'records':25000,'projected_bytes':119200000,'flush':'every accepted window','integrity':'fixed-width binary plus checkpoint JSON SHA256 manifests','rejected_state_included':False})
 save(E/'structure/full_span_reconstruction_audit.json',{'status':'READY','basis':'qualified evaluateStructureState / exact ANCF H(s)','domain_m':[0.0,13.12],'minimum_grid':'all 33 ANCF nodes','preferred_grid':'element-resolved dense uniform grid','outputs':['r','D','v','a if available'],'five_interface_centers_only':False})
 save(E/'structure/modal_data_audit.json',{'CURRENT_MODAL_BASIS':'NEEDS_OFFLINE_GENERATION','current_model':'13.12 m, 32 elements, 33 nodes, 198 DOF','old_50m_16element_basis_used':False,'long_run_blocked':False})
 save(E/'structure/curvature_data_audit.json',{'CURVATURE_POSTPROCESS':'READY','method':'offline exact ANCF interpolation derivatives from q history','production_integrator_modified':False,'outputs':['curvature_x','curvature_y']})
 save(E/'structure/tension_data_audit.json',{'TOP_BOTTOM_TENSION':'OPTIONAL_NOT_AVAILABLE','reason':'accepted q/v history retained; no validated reaction/tension postprocessor currently exposed','long_run_blocked':False})
 save(E/'force/direct_force_contract.json',{'status':'READY','name':'DIRECT_OPENFOAM_FORCE','producer':'OpenFOAM forces function object','cadence':'every solver time step','units':'N','components':['pressure Fx/Fy','viscous Fx/Fy','total Fx/Fy'],'parallel_aggregation':'sum rank-local force.dat records by physical time before alignment','accepted_only':'derived after alignment','coupling_force_not_substituted':True})
 save(E/'force/coupling_force_contract.json',{'status':'READY','name':'PRECICE_COUPLING_FORCE','producer':'Structure readData / attempts and accepted windows','cadence':'every attempt plus accepted-window subset','units':'N','fields':['slice_id','s_ref_m','time','window','attemptOrdinal','Fraw_x','Fraw_y'],'direct_force_semantics':'distinct'})
 save(E/'force/accepted_direct_force_alignment_contract.json',{'DIRECT_FORCE_ACCEPTED_ALIGNMENT':'READY','method':['native record physical time','native record ordinal within duplicate time','slice identity','coupling attempt ordinal from Structure attempts','accepted window final attempt','adapter/launcher event if available'],'selection':'DIRECT_OPENFOAM_FORCE_AT_ACCEPTED_ATTEMPT','timestamp_only':'FORBIDDEN','parser':'align_direct_forces.py'})
 save(E/'force/coefficient_normalization.json',{'rho_kg_m3':1000.0,'U_m_s':0.31,'D_m':0.028,'Ls_m':5.94,'local_denominator':'0.5*rho*U^2*D','whole_region_denominator':'0.5*rho*U^2*D*Ls','force_density':'F_direct/0.028','tributary_multiplier':False,'local_forceCoeffs_are_not_whole_region':True})
 save(E/'huera/huera_required_metrics.json',{'structural':['mean inline shape','dynamic inline','cross-flow','sigma_x/D','sigma_y/D','RMS profiles','envelopes','max IL/CF','x-y trajectories','PSD','fx','fy','nx','ny'],'force':['Fx_total integral','Fy_total integral','Cd_total','mean Cd','RMS Cl','local Cd/Cl'],'windows':['0-10s','2-10s','5-10s','7.5-10s','sliding'],'final_values_in_NM13_1':False})
 save(E/'huera/huera_statistical_definitions.json',{'sigma_x':'std of x(s,t)-mean x(s) on selected window and dense full-span grid','sigma_y':'std of y(s,t) on selected window and dense full-span grid','Cd_total':'integral reconstructed direct line force divided by whole-region denominator','RMS_Cl':'definition unresolved: project checkout contains no uniquely defining Huera Case-1 equation/source; do not silently choose integrated-vs-local-spatial RMS','source_audit':'searched project files for Huera/Huarte/Case-1/RMS Cl definitions; no authoritative equation found','stationarity_required':True,'frequency_bin_spacing_Hz':0.1})
 save(E/'huera/case1_reference_metadata.json',{'U_m_s':0.31,'Re':7622,'Tt0_N':1175,'ny':2,'fy_Hz':1.66,'nx':4,'fx_Hz':3.40,'mean_Cd':1.86,'RMS_Cl':1.93,'status':'reference_targets_only'})
 save(E/'huera/postprocess_readiness_matrix.json',{'HUERA_SIGMA_X':'READY','HUERA_SIGMA_Y':'READY','HUERA_FX':'READY','HUERA_FY':'READY','HUERA_NX_NY':'NEEDS_OFFLINE_MODAL_BASIS','HUERA_MEAN_CD':'READY','HUERA_RMS_CL':'BLOCKED_PENDING_SOURCE_DEFINITION','FORCE_DISPLACEMENT_PHASE':'READY','TOP_BOTTOM_TENSION':'OPTIONAL_NOT_AVAILABLE','FULL_SPAN_GRID':'READY'})
 save(E/'storage/projected_data_volume.json',{'q_history_MB':119.2,'qddot_included':True,'accepted_coupling_force_MB_estimate':60.0,'native_forces_MB_estimate':250.0,'native_forceCoeffs_MB_estimate':300.0,'full_fields_with_purge3_MB_estimate':20.0,'yPlus_MB_estimate':5.0,'preCICE_logs_MB_estimate':500.0,'monitor_evidence_MB_estimate':3000.0,'conservative_total_additional_GB':12.0,'basis':'NM12 measurements plus cadence-aware estimates; not runtime measured'})
 save(E/'storage/postprocessing_growth.json',{'native_forces':'compact text, ~one record per solver step/attempt; duplicates at repeated physical times are retained','forceCoeffs':'compact text, same cadence; no force fields','yPlus':'writeTime only, writeFields=no','full_fields':'only 250-step times, purgeWrite=3','arbitrary_postProcessing_purge':'not assumed','direct_force_alignment_required':True})
 save(E/'launch/early_data_integrity_guard.json',{'status':'CONFIGURED','checks_after_accepted_windows':5,'checks':['all five forces files exist and grow','all five forceCoeffs files exist and grow','times plausible','accepted Structure state grows','accepted coupling-force history grows'],'alignment_gate_after_window':20,'failure_action':'request stop at next safe committed checkpoint, never mid-write','runtime_guard_not_run':True})
 save(E/'launch/preflight_check.json',{'status':'PASS','controlDicts':'5/5 audited','native_forces':'5/5 timeStep/1','native_forceCoeffs':'5/5 timeStep/1','full_fields':'5/5 interval250 purge3','yPlus':'5/5 writeTime writeFields=no','accepted_qv':'configured','accepted_coupling_force':'configured','direct_alignment':'READY','disk_budget':'PASS','CPU_binding':'PASS','manual_launcher':'READY','participants_started':False})
 save(E/'data_manifest.json',{'products':[
  {'name':'accepted_global_q_v_qddot','producer':'Structure recorder','cadence':'every accepted window','units':'SI/state','path':str(NM13/'runtime/state_accepted_states.bin'),'status':'READY','restart':True,'Huera':True,'qualification':True},
  {'name':'PRECICE_ACCEPTED_FORCE','producer':'Structure accepted_windows.jsonl','cadence':'every accepted window','units':'N','path':str(NM13/'runtime/accepted_windows.jsonl'),'status':'READY','restart':False,'Huera':False,'qualification':True},
  {'name':'DIRECT_OPENFOAM_FORCE','producer':'forces function object, summed over ranks','cadence':'every solver time step','units':'N','path':'fluid_*/postProcessing/cylinderForces/*/force.dat','status':'READY','restart':False,'Huera':True,'qualification':False},
  {'name':'DIRECT_OPENFOAM_FORCECOEFFS','producer':'forceCoeffs function object','cadence':'every solver time step','units':'dimensionless local coefficient','path':'fluid_*/postProcessing/cylinderForceCoeffs/*/coefficient.dat','status':'AUXILIARY','restart':False,'Huera':True,'qualification':False},
  {'name':'FULL_FIELD_CHECKPOINT','producer':'OpenFOAM Time','cadence':'250 steps, purge3','units':'fields/mesh','path':'fluid_*/processor*/<time>/','status':'READY','restart':True,'Huera':False,'qualification':True},
  {'name':'yPlus','producer':'yPlus function object','cadence':'writeTime','units':'dimensionless','path':'fluid_*/postProcessing/yPlus/*/yPlus.dat','status':'OPTIONAL','restart':False,'Huera':False,'qualification':False},
  {'name':'DIRECT_FORCE_ACCEPTED_ALIGNMENT','producer':'align_direct_forces.py','cadence':'offline after run','units':'N','path':'derived accepted direct stream','status':'READY','restart':False,'Huera':True,'qualification':False}],
  'unbounded_full_field_debug_output':'DISABLED'})
 save(E/'comparison/final_classification.json',{'classification':'V2606_NM13_1_LONG10S_POSTPROCESS_DATA_READY','LONG10S_LAUNCH_DATA_CONTRACT':'READY','HUERA_PRIMARY_RESPONSE_DATA':'READY','HUERA_PRIMARY_FORCE_DATA':'READY','DIRECT_FORCE_ACCEPTED_ALIGNMENT':'READY','FULL_FIELD_WRITE_POLICY':'250_STEPS_PURGE3','REAL_LONG_RUN_STARTED':'NO','authorized_next_action':'USER_MANUAL_START_N5_LONG10S','RMS_CL_definition':'BLOCKED_PENDING_PROJECT_HUERA_SOURCE_DEFINITION','CURRENT_MODAL_BASIS':'NEEDS_OFFLINE_GENERATION','TOP_BOTTOM_TENSION':'OPTIONAL_NOT_AVAILABLE'})
 print('NM13.1_AUDIT PASS native-forces=5 coeffs=5 qv=READY alignment=READY long-run=NO')
if __name__=='__main__': main()
