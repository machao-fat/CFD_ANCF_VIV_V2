#!/usr/bin/env python3
"""NM14.1 read-only definition and plotting correction."""
import csv, json, math, re, os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(os.environ.get("V2606_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
BASE=ROOT/"evidence/v2606_nm14_n5_long10s_postprocessing"; OUT=ROOT/"evidence/v2606_nm14_1_long10s_correction"; RT=ROOT/"evidence/v2606_nm13_n5_long10s_configuration/runtime"
(OUT/"figures").mkdir(parents=True,exist_ok=True); (OUT/"modal").mkdir(parents=True,exist_ok=True); (OUT/"analysis").mkdir(parents=True,exist_ok=True)
def dump(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,indent=2,allow_nan=False),encoding="utf-8")
def stats(a):
 a=np.asarray(a,float); a=a[np.isfinite(a)]; return {"n":int(len(a)),"min":float(a.min()),"median":float(np.median(a)),"mean":float(a.mean()),"p95":float(np.percentile(a,95)),"max":float(a.max())} if len(a) else {"n":0}
def classify(a):
 a=np.asarray(a,float); a=a[np.isfinite(a)]
 if len(a)==0:return "NOT_ESTABLISHED"
 r=(a.max()-a.min())/max(abs(a.mean()),1e-12); return "STABLE" if r<=.10 else ("WEAK_DRIFT" if r<=.25 else "STRONG_DRIFT")
R=np.load(BASE/"structure/full_riser_reconstruction.npz"); t=R["elapsed_s"]; s=R["s_m"]; D=R["D"]; n=len(t); Ddia=.028; interface=5.94/13.12
centers=[.594,1.782,2.970,4.158,5.346]; ci=[int(np.argmin(abs(s-x))) for x in centers]; i297=ci[2]; i594=int(np.argmin(abs(s-5.94)))
win_defs={"0-10s":(0,10),"2-10s":(2,10),"5-10s":(5,10),"7.5-10s":(7.5,10)}
def detrend(y,linear=False):
 y=np.asarray(y,float); x=np.arange(len(y)); return y-np.polyval(np.polyfit(x,y,1),x) if linear else y-y.mean()
def spectrum(y,linear=False):
 z=detrend(y,linear); f=np.fft.rfftfreq(len(z),.0004); p=(2*.0004/len(z))*(abs(np.fft.rfft(z))**2); p[0]*=.5; return f,p
def peaks(f,p,max_hz=10):
 m=(f>0)&(f<max_hz); ii=np.flatnonzero(m); cand=[]
 for k in ii[1:-1]:
  if p[k]>=p[k-1] and p[k]>=p[k+1]: cand.append(k)
 cand=sorted(cand,key=lambda k:p[k],reverse=True); chosen=[]
 for k in cand:
  if all(abs(f[k]-f[j])>=.2 for j in chosen): chosen.append(k)
  if len(chosen)>=5: break
 total=float(np.sum(p[m])) or 1.; return [{"frequency_Hz":float(f[k]),"PSD":float(p[k]),"relative_peak_power":float(p[k]/total)} for k in chosen]

window_out={}; spectral={}
for name,(lo,hi) in win_defs.items():
 m=(t>=lo)&(t<=hi); x=D[m,:,0]; y=D[m,:,1]; xb=x.mean(axis=0); xp=x-xb[None,:]; ymean=y.mean(axis=0); yp=y-ymean[None,:]; sx=np.std(xp,axis=0); sy=np.std(yp,axis=0)
 window_out[name]={"sample_count":int(m.sum()),"xbar_m":xb.tolist(),"ybar_m":ymean.tolist(),"sigma_x_over_D_max":float(sx.max()/Ddia),"sigma_y_over_D_max":float(sy.max()/Ddia),"sigma_x_m_max":float(sx.max()),"sigma_y_m_max":float(sy.max()),"dynamic_x_over_D_min":float(xp.min()/Ddia),"dynamic_x_over_D_max":float(xp.max()/Ddia),"dynamic_y_over_D_min":float(yp.min()/Ddia),"dynamic_y_over_D_max":float(yp.max()/Ddia),"dynamic_x_rms_m_at_2.97":float(np.std(x[:,i297])),"crossflow_rms_m_at_2.97":float(np.std(y[:,i297])),"crossflow_mean_max_m":float(np.max(abs(ymean)))}
 fx,px=spectrum(x[:,i297],False); fxdt,pxdt=spectrum(x[:,i297],True); fy,py=spectrum(y[:,i297],False)
 spectral[name]={"record_length_s":float(hi-lo),"bin_resolution_Hz":float(1/(hi-lo)),"inline_detrended_peaks":peaks(fxdt,pxdt),"inline_window_mean_removed_peaks":peaks(fx,px),"crossflow_peaks":peaks(fy,py),"inline_linear_detrend_sensitivity":peaks(fxdt,pxdt)}
dump(OUT/"analysis/windowed_dynamic_statistics.json",window_out); dump(OUT/"analysis/windowed_frequency_peaks.json",spectral)

attempts=[json.loads(x) for x in (RT/"attempts.jsonl").read_text().splitlines() if x.strip()]; am=np.array([a["accepted"] for a in attempts],bool); native=np.load(BASE/"forces/native_force_coefficients.npz")["direct"]; A=native[:,np.flatnonzero(am),1:3]; f=A/.028
Fint=(.594*f[0]+1.188*.5*(f[0]+f[1])+1.188*.5*(f[1]+f[2])+1.188*.5*(f[2]+f[3])+1.188*.5*(f[3]+f[4])+.594*f[4]); Cd=Fint[:,0]/(.5*1000*.31**2*.028*5.94); Cl=Fint[:,1]/(.5*1000*.31**2*.028*5.94)
hydro={}
for name,(lo,hi) in win_defs.items():
 m=(t>=lo)&(t<=hi); hydro[name]={"mean_Cd":float(np.mean(Cd[m])),"std_Cd":float(np.std(Cd[m])),"integrated_total_Cl_RMS":float(np.sqrt(np.mean((Cl[m]-Cl[m].mean())**2))),"integrated_total_Cl_mean":float(np.mean(Cl[m]))}
dump(OUT/"analysis/hydrodynamic_window_statistics.json",hydro)

def readmat(path):
 n=int(np.fromfile(path,dtype=np.uint64,count=1)[0]); return np.fromfile(path,dtype=np.float64,count=n*n,offset=8).reshape(n,n)
M=readmat(OUT/"modal/M.bin"); K=readmat(OUT/"modal/M.bin.K"); fixed=[0,1,2,6*32,6*32+1]; free=np.array([i for i in range(198) if i not in fixed]); Mf=M[np.ix_(free,free)]; Kf=K[np.ix_(free,free)]
Lchol=np.linalg.cholesky((Mf+Mf.T)/2); Linv=np.linalg.inv(Lchol); Astd=Linv@((Kf+Kf.T)/2)@Linv.T; lam,U=np.linalg.eigh((Astd+Astd.T)/2); lam=np.maximum(lam,0); Phi=Linv.T@U; order=np.argsort(lam); lam=lam[order]; Phi=Phi[:,order]; freq=np.sqrt(lam)/(2*np.pi)
np.savez_compressed(OUT/"modal/generated_basis.npz",free=free,frequencies_Hz=freq,Phi=Phi)
qrec=np.fromfile(RT/"state_accepted_states.bin",dtype=np.dtype([("window","<u8"),("elapsed","<f8"),("q","<f8",(198,)),("v","<f8",(198,)),("a","<f8",(198,))])); q=np.asarray(qrec["q"]); modal={}
for name,(lo,hi) in win_defs.items():
 m=(t>=lo)&(t<=hi); qd=q[m]-q[m].mean(axis=0); xf=np.zeros_like(qd[:,free]); yf=np.zeros_like(qd[:,free])
 for j,g in enumerate(free):
  if g%6 in (0,3): xf[:,j]=qd[:,g]
  if g%6 in (1,4): yf[:,j]=qd[:,g]
 ax=xf@Mf@Phi[:,:6]; ay=yf@Mf@Phi[:,:6]; modal[name]={"inline_modes_1_6_rms":np.sqrt(np.mean(ax**2,axis=0)).tolist(),"crossflow_modes_1_6_rms":np.sqrt(np.mean(ay**2,axis=0)).tolist(),"inline_modes_1_6_peak":np.max(abs(ax),axis=0).tolist(),"crossflow_modes_1_6_peak":np.max(abs(ay),axis=0).tolist(),"frequencies_Hz_1_6":freq[:6].tolist(),"inline_dominant_mode_diagnostic":int(np.argmax(np.sqrt(np.mean(ax**2,axis=0)))+1),"crossflow_dominant_mode_diagnostic":int(np.argmax(np.sqrt(np.mean(ay**2,axis=0)))+1)}
dump(OUT/"analysis/modal_projection_late_windows.json",{"basis_status":"LIMITED_UNVERIFIED_CROSSCHECK","basis_generation":"current frozen kernel mass and q0 tangent; fixed DOFs 0,1,2,198,199 removed; M-normalized","frequency_crosscheck":"NO_COMPATIBLE_CURRENT_ARTIFACT_FOUND","windows":modal})

plt.rcParams.update({"font.family":"sans-serif","font.size":7,"axes.titlesize":8,"svg.fonttype":"none","pdf.fonttype":42})
def save(fig,name):
 b=OUT/"figures"/name
 fig.savefig(str(b)+".svg",bbox_inches="tight"); fig.savefig(str(b)+".pdf",bbox_inches="tight"); fig.savefig(str(b)+".png",dpi=300,bbox_inches="tight"); fig.savefig(str(b)+".tiff",dpi=600,bbox_inches="tight")
 plt.close(fig)
sl=s/13.12
def profile_plot(y,xlabel,title,name):
 fig,ax=plt.subplots(figsize=(4.6,3.4)); ax.plot(y,sl,color="#1f4e79"); ax.axhspan(0,interface,color="#d9eaf7",alpha=.65); ax.axhline(interface,color="#5b9bd5",ls="--",lw=.8); ax.set(xlabel=xlabel,ylabel="s/L",title=title,ylim=(0,1)); ax.text(.98,interface/2,"current",ha="right",va="center",transform=ax.get_yaxis_transform(),fontsize=6); save(fig,name)
for name,(lo,hi) in win_defs.items():
 m=(t>=lo)&(t<=hi); xb=D[m,:,0].mean(axis=0); xp=D[m,:,0]-xb[None,:]; yp=D[m,:,1]-D[m,:,1].mean(axis=0)
 profile_plot(xb/.028,"mean x/D",f"Mean inline shape ({name})","mean_inline_shape_"+name.replace("-","_").replace(".","p")); profile_plot(np.std(xp,axis=0)/.028,"sigma_x/D",f"Inline RMS ({name})","sigma_x_over_D_"+name.replace("-","_").replace(".","p")); profile_plot(np.std(yp,axis=0)/.028,"sigma_y/D",f"Cross-flow RMS ({name})","sigma_y_over_D_"+name.replace("-","_").replace(".","p"))

m=(t>=7.5)&(t<=10); xb=D[m,:,0].mean(axis=0); xp=D[m,:,0]-xb[None,:]; fy_l=spectral["7.5-10s"]["crossflow_peaks"][0]["frequency_Hz"]; period=1/fy_l if fy_l else .625; late_t=t[m]; endpoint=late_t[-1]; phase_times=np.linspace(max(late_t[0],endpoint-period),endpoint,30); ii=np.array([np.argmin(abs(t-z)) for z in phase_times])
fig,axs=plt.subplots(1,3,figsize=(8.2,4.2),sharey=True); axs[0].plot(xb/.028,sl,color="#1f4e79"); axs[0].set_xlabel("mean x/D"); axs[1].plot((D[ii,:,0]-xb[None,:]).T/.028,sl,color="#4472c4",alpha=.45); axs[1].plot(xp.min(axis=0)/.028,sl,"--",color="#1f4e79"); axs[1].plot(xp.max(axis=0)/.028,sl,"--",color="#1f4e79"); axs[1].set_xlabel("dynamic (x-xbar)/D"); axs[2].plot(D[ii,:,1].T/.028,sl,color="#c00000",alpha=.45); axs[2].plot(D[m,:,1].min(axis=0)/.028,sl,":",color="#8b0000"); axs[2].plot(D[m,:,1].max(axis=0)/.028,sl,":",color="#8b0000"); axs[2].set_xlabel("y/D")
for ax in axs: ax.axhspan(0,interface,color="#d9eaf7",alpha=.65); ax.axhline(interface,color="#5b9bd5",ls="--",lw=.8); ax.set_ylim(0,1); ax.grid(alpha=.15)
axs[0].set_ylabel("s/L"); fig.suptitle("Chaplin-style simulated response; late representative CF period"); save(fig,"chaplin_fig8_style_simulation_corrected")

for name,(lo,hi) in [("5-10s",(5,10)),("7.5-10s",(7.5,10))]:
 m=(t>=lo)&(t<=hi); xb=D[m,:,0].mean(axis=0); late=np.flatnonzero(m); end=late[-1]
 for periods in [1,3]:
  ii=np.arange(max(late[0],end-int(periods*period/.0004)),end+1); fig,ax=plt.subplots(figsize=(4.8,3.8))
  for k in [0,2,3,4]: ax.plot((D[ii,ci[k],0]-xb[ci[k]])/.028,D[ii,ci[k],1]/.028,lw=.65,label=f"s={centers[k]:.3g} m")
  ax.set(xlabel="(x-xbar)/D",ylabel="y/D",title=f"Late XY trajectories: {name}, {periods} CF period(s)"); ax.legend(frameon=False,fontsize=6); save(fig,"xy_trajectories_"+name.replace("-","_")+f"_{periods}period")

dump(OUT/"analysis/axis_and_window_audit.json",{"interface_s_over_L":interface,"axis_contract":"all corrected full-riser figures use vertical s/L in [0,1]","window_specific_mean_subtraction":True,"startup_contamination":"quantified by comparing 0-10 against 2-10, 5-10, 7.5-10","representative_late_cf_frequency_Hz":float(fy_l),"representative_period_s":float(period),"figure_marker_audit":"corrected figures use shaded current-region bar; no misplaced s/L marker"})
fx_candidates={k:(v["inline_detrended_peaks"][0]["frequency_Hz"] if v["inline_detrended_peaks"] else None) for k,v in spectral.items()}; fy_candidates={k:(v["crossflow_peaks"][0]["frequency_Hz"] if v["crossflow_peaks"] else None) for k,v in spectral.items()}; latefx=[fx_candidates["5-10s"],fx_candidates["7.5-10s"]]; latefy=[fy_candidates["5-10s"],fy_candidates["7.5-10s"]]; fxstable=latefx[0] is not None and latefx[1] is not None and abs(latefx[0]-latefx[1])<=.2; late_modal=modal["7.5-10s"]
table={}
for metric,vals in [("sigma_x_over_D",[v["sigma_x_over_D_max"] for v in window_out.values()]),("sigma_y_over_D",[v["sigma_y_over_D_max"] for v in window_out.values()]),("fy",[fy_candidates[k] for k in win_defs]),("candidate_fx",[fx_candidates[k] for k in win_defs]),("mean_Cd",[hydro[k]["mean_Cd"] for k in win_defs]),("integrated_lift_RMS",[hydro[k]["integrated_total_Cl_RMS"] for k in win_defs])]: table[metric]={"windows":list(win_defs),"values":vals,"classification":"NOT_ESTABLISHED" if metric=="candidate_fx" and not fxstable else classify(np.array(vals,float))}
dump(OUT/"analysis/stationarity_table.json",table)
dump(OUT/"comparison/final_classification.json",{"classification":"V2606_NM14_1_LONG10S_POSTPROCESS_CORRECTED","s_over_L_plotting_bug":"FIXED","startup_contamination_of_inline_metrics":"QUANTIFIED","late_time_fy_Hz":latefy,"late_time_candidate_fx_Hz":latefx if fxstable else "NOT_ESTABLISHED","fx_over_fy_candidates":[latefx[i]/latefy[i] for i in range(2)] if fxstable else "NOT_ESTABLISHED","current_late_candidate_pair_labels":["5-10s","7.5-10s"],"late_time_sigma_x_over_D":window_out["7.5-10s"]["sigma_x_over_D_max"],"late_time_sigma_y_over_D":window_out["7.5-10s"]["sigma_y_over_D_max"],"current_modal_basis":"LIMITED","ny_diagnostic":late_modal["crossflow_dominant_mode_diagnostic"],"nx_diagnostic":late_modal["inline_dominant_mode_diagnostic"],"modal_frequency_crosscheck":"NO_COMPATIBLE_CURRENT_ARTIFACT_FOUND","ten_second_status":"EXTENSION_RECOMMENDED","extension_basis":["window-specific inline RMS/frequency changes materially from 0-10 to late windows","modal basis remains unverified against a retained current-model frequency artifact","Huera distributed RMS Cl definition remains source-definition-limited"],"recommended_extension":"10_to_15_s_first; reassess before 20 s","real_simulation_started":False})
print(json.dumps({"classification":"V2606_NM14_1_LONG10S_POSTPROCESS_CORRECTED","late_fx":latefx if fxstable else None,"late_fy":latefy,"nx":late_modal["inline_dominant_mode_diagnostic"],"ny":late_modal["crossflow_dominant_mode_diagnostic"]},indent=2))
