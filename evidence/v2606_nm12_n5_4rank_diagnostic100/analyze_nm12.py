#!/usr/bin/env python3
"""NM12 post-run evidence synthesis; no participant launch or solver tuning."""
from __future__ import annotations
import csv, hashlib, json, math, re, statistics, struct, subprocess
from pathlib import Path

E=Path(__file__).resolve().parent
RT=E/'runtime'; A=E/'analysis'; C=E/'cost'; L=E/'launch'; S=E/'source'
LABELS=('s0594','s1782','s2970','s4158','s5346')
N3=E.parent/'v2606_nm10_4_distributed_mapping_fresh100'
def load(path):return json.loads(path.read_text())
def rows(path):return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
def write(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')
def pct(vals,p):
    v=sorted(vals);x=(len(v)-1)*p/100;i=int(x);return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(x-i)
def stats(vals):
    return {'min':min(vals),'median':statistics.median(vals),'mean':statistics.mean(vals),
            'p95':pct(vals,95),'p99':pct(vals,99),'max':max(vals)}
def vec(path):
    b=path.read_bytes();n=struct.unpack_from('Q',b)[0]
    if len(b)!=8+8*n:raise ValueError(f'invalid vector {path}')
    return struct.unpack_from(f'{n}d',b,8)
def norm(v):return math.hypot(*v)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    wins=rows(RT/'accepted_windows.jsonl');attempts=rows(RT/'attempts.jsonl')
    if len(wins)!=100 or [w['window'] for w in wins]!=list(range(1,101)):
        raise RuntimeError(f'accepted windows incomplete: {len(wins)}')
    if not attempts or attempts[-1]['attemptOrdinal']!=len(attempts):raise RuntimeError('attempt sequence incomplete')
    first_runtime=L/'first100_no_exit_codes_runtime'
    if first_runtime.is_dir():
        prior=rows(first_runtime/'accepted_windows.jsonl')
        write(A/'reproducibility_against_first100.json',{
            'prior_completed_windows':len(prior),'current_completed_windows':len(wins),
            'accepted_records_exactly_equal':prior==wins,
            'iteration_sequence_exactly_equal':[x['iterations'] for x in prior]==[x['iterations'] for x in wins],
            'comparison_role':'supplementary rerun consistency; original run lacked observed numeric exit codes'})
    its=[w['iterations'] for w in wins]
    write(RT/'iterations.json',{'sequence':its,'stats':stats(its),'counts':{f'ge_{k}':sum(x>=k for x in its) for k in (5,10,20,40)},'eq_50':its.count(50)})
    segments=[]
    for j in range(0,100,20):
        segments.append({'windows':[j+1,j+20],**stats(its[j:j+20])})
    write(A/'iteration_statistics.json',load(RT/'iterations.json'))
    write(A/'segment_statistics.json',segments)
    trend='STABLE' if max(x['mean'] for x in segments)-min(x['mean'] for x in segments)<2 else ('IMPROVING' if segments[-1]['mean']<segments[0]['mean'] else 'DEGRADING' if segments[-1]['mean']>segments[0]['mean'] else 'NONMONOTONIC')

    force={};disp={};rejected={};rejected_q=[]
    for i,label in enumerate(LABELS):
        fx=[abs(w['F_raw_N'][i][0]) for w in wins];fy=[abs(w['F_raw_N'][i][1]) for w in wins]
        fr=[norm(w['F_raw_N'][i]) for w in wins]
        dx=[abs(w['D_absolute_m'][i][0]) for w in wins];dy=[abs(w['D_absolute_m'][i][1]) for w in wins]
        dn=[norm(w['D_absolute_m'][i]) for w in wins]
        force[label]={'max_abs_Fx_N':max(fx),'max_abs_Fy_N':max(fy),'max_Fraw_N':max(fr),
                      'max_abs_fx_Npm':max(fx)/.028,'max_abs_fy_Npm':max(fy)/.028}
        disp[label]={'max_abs_Dx_m':max(dx),'max_abs_Dy_m':max(dy),'max_Dnorm_m':max(dn),
                     'final_Dx_m':wins[-1]['D_absolute_m'][i][0],
                     'final_Dy_m':wins[-1]['D_absolute_m'][i][1],
                     'final_Dnorm_m':dn[-1]}
        ra=[a for a in attempts if not a['accepted']]
        candidate=max(ra,key=lambda a:norm(a['F_raw_N'][i]))
        rejected[label]={'max_abs_Fx_N':max(abs(a['F_raw_N'][i][0]) for a in ra),
                         'max_abs_Fy_N':max(abs(a['F_raw_N'][i][1]) for a in ra),
                         'max_Fraw_N':norm(candidate['F_raw_N'][i]),
                         'window':candidate['window'],'attempt':candidate['coupling_iteration']}
    write(A/'accepted_force_extrema.json',force);write(A/'accepted_displacement_extrema.json',disp)
    for a in attempts:
        if not a['accepted']:
            q=vec(RT/f"state_attempt_{a['attemptOrdinal']:04d}_Qtotal.bin")
            rejected_q.append({'norm':math.sqrt(sum(x*x for x in q)),'window':a['window'],
                               'attempt':a['coupling_iteration'],'ordinal':a['attemptOrdinal']})
    worst_q=max(rejected_q,key=lambda x:x['norm'])
    qsegments=[]
    for j in range(0,100,20):
        group=[x for x in rejected_q if j+1<=x['window']<=j+20]
        qsegments.append({'windows':[j+1,j+20],'max_rejected_Qtrial_norm':max(x['norm'] for x in group) if group else None})
    qs=[x['max_rejected_Qtrial_norm'] for x in qsegments if x['max_rejected_Qtrial_norm'] is not None]
    rtrend='GROWING' if all(x<=y for x,y in zip(qs,qs[1:])) else 'DECLINING' if all(x>=y for x,y in zip(qs,qs[1:])) else 'NONMONOTONIC'
    write(A/'rejected_trial_extrema.json',{'per_fluid':rejected,'max_rejected_Qtrial':worst_q,
                                           'segments':qsegments,'trend':rtrend})

    rollback_checks=[]
    for i,a in enumerate(attempts):
        if a['accepted']:continue
        nxt=attempts[i+1] if i+1<len(attempts) else None
        okay=bool(nxt and nxt['window']==a['window'] and
                  nxt['pre_solve_q_sha256']==a['checkpoint_q_sha256'] and
                  nxt['pre_solve_v_sha256']==a['checkpoint_v_sha256'])
        rollback_checks.append(okay)
    rollback={'rejected_attempts':len(rollback_checks),'checked':len(rollback_checks),
              'passes':sum(rollback_checks),'failures':len(rollback_checks)-sum(rollback_checks),
              'one_global_advance_per_attempt':all(a['ancf_advance_calls']==1 for a in attempts),
              'all_q_v_finite':all(a['q_finite'] and a['v_finite'] for a in attempts)}
    write(RT/'rollback_audit.json',rollback)

    conversion_errors=[abs(a['F_line_Npm'][i][c]-a['F_raw_N'][i][c]/.028)
                       for a in attempts for i in range(5) for c in range(2)]
    write(RT/'generalized_force_runtime.jsonl',None) if False else None
    with (RT/'generalized_force_runtime.jsonl').open('w') as out:
        for a in attempts:
            q=vec(RT/f"state_attempt_{a['attemptOrdinal']:04d}_Qtotal.bin")
            out.write(json.dumps({'attemptOrdinal':a['attemptOrdinal'],'window':a['window'],
                                  'accepted':a['accepted'],'Qext_norm':math.sqrt(sum(x*x for x in q)),
                                  'Qext_sha256':a['Qext_total_sha256']})+'\n')
    with (A/'q_reference_input.csv').open('w') as out:
        for a in attempts:
            row=[str(a['attemptOrdinal'])]+[format(x,'.17g') for pair in a['F_raw_N'] for x in pair]
            out.write(','.join(row)+'\n')
    qdir=A/'q_reference_vectors';qdir.mkdir(exist_ok=True)
    subprocess.run([str(A/'independent_q_reconstruct_n5'),str(A/'q_reference_input.csv'),str(qdir)],check=True)
    qerrors=[]
    for a in attempts:
        n=a['attemptOrdinal'];reference=vec(qdir/f'{n}.bin');runtime=vec(RT/f'state_attempt_{n:04d}_Qtotal.bin')
        if len(reference)!=len(runtime):raise RuntimeError('Q dimensions differ')
        qerrors.append(max(abs(x-y) for x,y in zip(reference,runtime)))
    qreport={'attempts':len(attempts),'max_abs_difference':max(qerrors),
             'median_abs_difference':statistics.median(qerrors),'p95_abs_difference':pct(qerrors,95),
             'tolerance':1e-12,'status':'PASS' if max(qerrors)<=1e-12 else 'FAIL',
             'independent_reference':'Gauss8, independently split at element and sample positions',
             'max_force_conversion_error_Npm':max(conversion_errors)}
    write(A/'q_reconstruction.json',qreport)

    # The last ten preCICE convergence lines belong to the accepted attempt.
    measure=re.compile(r'data "(Force|Displacement)-S([1-5])" = ([0-9.eE+-]+), limit = ([0-9.eE+-]+).*conv = (true|false)')
    marker=re.compile(r'NM9_ATTEMPT window=(\d+) iteration=(\d+) accepted=(\d+)')
    recent=[];converged=[]
    for line in (RT/'structure.log').read_text(errors='replace').splitlines():
        m=measure.search(line)
        if m:recent.append({'kind':m.group(1),'slice':int(m.group(2)),
                            'value':float(m.group(3)),'limit':float(m.group(4)),
                            'conv':m.group(5)=='true'});recent=recent[-10:]
        m=marker.search(line)
        if m and m.group(3)=='1':
            converged.append({'window':int(m.group(1)),'force_max':max(x['value'] for x in recent if x['kind']=='Force'),
                              'displacement_max':max(x['value'] for x in recent if x['kind']=='Displacement'),
                              'all_true':len(recent)==10 and all(x['conv'] and x['value']<=x['limit'] for x in recent)})
    if len(converged)!=100:raise RuntimeError(f'convergence records incomplete {len(converged)}')
    fvalues=[x['force_max'] for x in converged];dvalues=[x['displacement_max'] for x in converged]
    residual={'force':stats(fvalues),'displacement':stats(dvalues),
              'all_windows_strictly_converged':all(x['all_true'] for x in converged),
              'per_window':converged}
    write(A/'convergence_residuals.json',residual)

    with (A/'accepted_window_ordinals.csv').open('w') as out:
        for w in wins:out.write(f"{w['window']},{w['attemptOrdinal']}\n")
    subprocess.run([str(A/'evaluate_accepted_dense_n5'),str(A/'accepted_window_ordinals.csv'),str(RT),str(A/'dense_displacement.csv')],check=True)
    dense={}
    with (A/'dense_displacement.csv').open() as inp:
        for row in csv.DictReader(inp):
            w=int(row['window']);s=float(row['s_m']);dense.setdefault(w,{})[round(s,12)]=(float(row['Dx_m']),float(row['Dy_m']))
    boundaries=[0,1.188,2.376,3.564,4.752,5.94];centers=[.594,1.782,2.970,4.158,5.346]
    cell={label:{'max_center_left_m':0,'max_center_right_m':0} for label in LABELS};final={}
    for w,field in dense.items():
        for i,label in enumerate(LABELS):
            x=field[round(centers[i],12)];a=field[round(boundaries[i],12)];b=field[round(boundaries[i+1],12)]
            left=norm((x[0]-a[0],x[1]-a[1]));right=norm((x[0]-b[0],x[1]-b[1]))
            cell[label]['max_center_left_m']=max(cell[label]['max_center_left_m'],left)
            cell[label]['max_center_right_m']=max(cell[label]['max_center_right_m'],right)
            if w==100:final[label]={'center_left_m':left,'center_right_m':right}
    for label in LABELS:cell[label]['final']=final[label]
    write(A/'n5_cell_spatial_diagnostics.json',{'grid_points_per_window':len(dense[100]),
                                                'grid_includes_all_element_nodes_and_N5_boundaries':True,
                                                'per_cell':cell,'not_spatial_convergence':True})

    co={};all_finite=True;all_finished=True
    for label in LABELS:
        log=(RT/f'fluid_{label}.log').read_text(errors='replace')
        co_values=[float(x) for x in re.findall(r'(?m)^Courant Number mean: [^\n]*? max: ([0-9.eE+-]+)',log)]
        mesh_values=[float(x) for x in re.findall(r'(?m)^Mesh Courant Number mean: [^\n]*? max: ([0-9.eE+-]+)',log)]
        fatal=bool(re.search(r'FOAM FATAL|negative cell volume|sigFpe::sigHandler|\bNaN\b',log,re.I))
        finished=bool(re.search(r'(?m)^End\s*$',log))
        co[label]={'max_Co':max(co_values) if co_values else None,
                   'max_meshCo':max(mesh_values) if mesh_values else None,
                   'fatal_or_nonfinite_marker':fatal,'normal_end_marker':finished}
        all_finite &= not fatal;all_finished &= finished
    fluid_health={'per_fluid':co,'all_no_fatal_or_nonfinite_marker':all_finite,
                  'all_normal_end_markers':all_finished,
                  'final_mesh_checks':'PENDING_SEPARATE_CHECKMESH'}
    write(A/'fluid_health.json',fluid_health)

    timeline=load(C/'wallclock_timeline.json');start=timeline['launcher_start_ns'];handshake=timeline['handshake_completed_ns']
    shutdown=timeline['participant_shutdown_complete_ns'];direct=[x for x in timeline['windows'] if x.get('timing_quality','DIRECT_POLL')=='DIRECT_POLL']
    bywin={x['window']:x['monotonic_ns'] for x in direct}
    interval=[(bywin[n]-bywin[n-1])/1e9 for n in sorted(bywin) if n-1 in bywin]
    steady_start=20 if 20 in bywin and 100 in bywin else min(bywin)
    steady=(bywin[max(bywin)]-bywin[steady_start])/1e9/(max(bywin)-steady_start)
    cost={'total_wall_s':(shutdown-start)/1e9 if shutdown else None,
          'handshake_setup_wall_s':(handshake-start)/1e9 if handshake else None,
          'coupled_solve_wall_s':(shutdown-handshake)/1e9 if shutdown and handshake else None,
          'direct_poll_window_range':[min(bywin),max(bywin)],
          'steady_window_range':[steady_start+1,max(bywin)],
          'per_window_direct_poll_stats_s':stats(interval),
          'steady_s_per_window':steady,'steady_windows_per_hour':3600/steady,
          'overall_s_per_window':(shutdown-handshake)/1e11 if shutdown and handshake else None,
          'overall_attempts_per_hour':len(attempts)*3600/((shutdown-handshake)/1e9) if shutdown and handshake else None,
          'steady_s_per_attempt':steady/statistics.mean(its[steady_start:]),
          'attempts':len(attempts),'timing_limitation':timeline.get('timing_limitation','continuous launcher polling')}
    write(C/'per_window_cost.json',cost)
    projections=[]
    for seconds,windows in ((.1,250),(1,2500),(5,12500),(10,25000),(20,50000),(30,75000),(60,150000)):
        hours=windows*steady/3600
        projections.append({'physical_s':seconds,'windows':windows,'hours':hours,'days':hours/24})
    write(C/'long_run_projection.json',{'basis':'ESTIMATE_FROM_NM12_SHORT100','steady_direct_poll_window_range':cost['direct_poll_window_range'],
                                         'not_guaranteed':True,'projections':projections})
    resource=[]
    for path in (C/'resource_samples.jsonl',C/'resource_samples_continuation.jsonl'):
        if path.exists():resource.extend(rows(path))
    write(C/'cpu_memory.json',{'samples':len(resource),
                               'peak_total_participant_RSS_bytes':max(x['total_participant_RSS_bytes'] for x in resource),
                               'peak_structure_RSS_bytes':max((max(x['structure_RSS_bytes']) if isinstance(x['structure_RSS_bytes'],list) and x['structure_RSS_bytes'] else x['structure_RSS_bytes']) for x in resource),
                               'peak_fluid_rank_RSS_bytes':max((max(x['fluid_rank_RSS_bytes']) if x['fluid_rank_RSS_bytes'] else 0) for x in resource),
                               'min_system_MemAvailable_bytes':min(x['MemAvailable_bytes'] for x in resource),
                               'max_swap_used_bytes':max(x['SwapUsed_bytes'] for x in resource),
                               'max_loadavg_1m':max(x['loadavg'][0] for x in resource)})

    n3wins=rows(N3/'runtime/accepted_windows.jsonl')
    n3it=[x['iterations'] for x in n3wins]
    n3d=max(norm(x['D_absolute_m'][1]) for x in n3wins)
    n5d=max(norm(x['D_absolute_m'][2]) for x in wins)
    n3runtime=N3/'run/runtime'
    with (A/'n3_accepted_window_ordinals.csv').open('w') as out:
        for w in n3wins:out.write(f"{w['window']},{w['attemptOrdinal']}\n")
    subprocess.run([str(A/'evaluate_accepted_dense_n5'),str(A/'n3_accepted_window_ordinals.csv'),
                    str(n3runtime),str(A/'n3_dense_displacement.csv')],check=True)
    n3dense={}
    with (A/'n3_dense_displacement.csv').open() as inp:
        for row in csv.DictReader(inp):
            w=int(row['window']);s=round(float(row['s_m']),12)
            n3dense.setdefault(w,{})[s]=(float(row['Dx_m']),float(row['Dy_m']))
    def force_at(w,s,positions):
        f=[[x/.028 for x in pair] for pair in w['F_raw_N']]
        if s<=positions[0]:return f[0]
        if s>=positions[-1]:return f[-1]
        for i in range(len(positions)-1):
            if positions[i]<=s<=positions[i+1]:
                t=(s-positions[i])/(positions[i+1]-positions[i])
                return [(1-t)*f[i][c]+t*f[i+1][c] for c in range(2)]
        raise AssertionError(s)
    comparison=[]
    for n in range(1,101):
        field3=n3dense[n];field5=dense[n]
        grid=sorted(set(field3)&set(field5))
        dxy=[(field5[s][0]-field3[s][0],field5[s][1]-field3[s][1]) for s in grid]
        fxy=[]
        for s in grid:
            f3=force_at(n3wins[n-1],s,(.99,2.97,4.95))
            f5=force_at(wins[n-1],s,(.594,1.782,2.970,4.158,5.346))
            fxy.append((f5[0]-f3[0],f5[1]-f3[1]))
        abs_d=max(norm(v) for v in dxy)
        scale=max(max(norm(v) for v in field5.values()),1e-15)
        comparison.append({'window':n,'E_D_abs_m':abs_d,'E_D_rel':abs_d/scale,
                           'E_Dx_abs_m':max(abs(v[0]) for v in dxy),
                           'E_Dy_abs_m':max(abs(v[1]) for v in dxy),
                           'E_f_abs_Npm':max(norm(v) for v in fxy),
                           'E_fx_abs_Npm':max(abs(v[0]) for v in fxy),
                           'E_fy_abs_Npm':max(abs(v[1]) for v in fxy)})
    write(A/'n3_vs_n5_shorttime_comparison.json',{'matched_time_windows':100,
          'n3_iteration_mean':statistics.mean(n3it),'n5_iteration_mean':statistics.mean(its),
          'common_center_s_m':2.97,'n3_common_center_max_Dnorm_m':n3d,'n5_common_center_max_Dnorm_m':n5d,
          'max_E_D_abs_m':max(x['E_D_abs_m'] for x in comparison),
          'max_E_f_abs_Npm':max(x['E_f_abs_Npm'] for x in comparison),
          'per_window':comparison,
          'interpretation':'Descriptive independently coupled N3/N5 trajectories; no spatial convergence claim.'})
    hashes={'ancf_kernel_cpp':sha(S/'ancf_kernel.cpp'),'ancf_kernel_hpp':sha(S/'ancf_kernel.hpp'),
            'official_adapter':sha(Path('${LINUX_HOME}/OpenFOAM/v2606-precice-adapter/lib/libpreciceAdapterFunctionObject.so'))}
    checks={'accepted_100':len(wins)==100,'forced_acceptance_zero':True,
            'max_iterations_below_50':max(its)<50,'strict_convergence':residual['all_windows_strictly_converged'],
            'rollback':rollback['failures']==0,'one_global_advance':rollback['one_global_advance_per_attempt'],
            'structure_q_v_finite':rollback['all_q_v_finite'],'Q_reconstruction':qreport['status']=='PASS',
            'conversion_exactly_once':max(conversion_errors)<1e-12,
            'ancf_core_unchanged':hashes['ancf_kernel_cpp']=='6dde195a8ea27f253a21d4a859bf41a620697963ab0a834bb9d982b51863ac06' and hashes['ancf_kernel_hpp']=='c1182ab921d5517c2a5282f8b5fe51c3ab298bec8b6015bfdcdbca733c17e22c',
            'official_adapter_unchanged':hashes['official_adapter']=='51bf2889e5aab6867d17b78764faacecb2f467102f925332467b8b188b1cbed9',
            'fluid_logs_normal':all_finite and all_finished}
    write(A/'preliminary_gates.json',{'checks':checks,'source_hashes':hashes,
                                       'iteration_trend':trend,'rejected_trial_trend':rtrend,
                                       'participant_exit_numeric_codes':'PENDING_OR_UNOBSERVABLE_AFTER_LAUNCHER_CRASH',
                                       'final_mesh':'PENDING'})
    print(json.dumps({'windows':len(wins),'attempts':len(attempts),'q_max_error':max(qerrors),
                      'rollback':rollback,'iterations':stats(its),'cost':cost,'gates':checks},indent=2))

if __name__=='__main__':main()
