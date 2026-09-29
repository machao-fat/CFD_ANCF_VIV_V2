#!/usr/bin/env python3
"""Offline NM14.2 modal-family and distributed-lift correction.

Reads completed NM13/NM14 artifacts; writes derived evidence only here.
"""
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get('V2606_EVIDENCE_ROOT', Path(__file__).resolve().parents[1]))
OUT = ROOT / 'v2606_nm14_2_modal_cl_correction'
OLD = ROOT / 'v2606_nm14_1_long10s_correction'
BASE = ROOT / 'v2606_nm14_n5_long10s_postprocessing'
RT = ROOT / 'v2606_nm13_n5_long10s_configuration/runtime'
WINDOWS = {'0-10s': (0., 10.), '2-10s': (2., 10.),
           '5-10s': (5., 10.), '7.5-10s': (7.5, 10.)}
CENTERS = np.array([.594, 1.782, 2.970, 4.158, 5.346])
L_ACTIVE = 5.94
UNIT_SPAN = .028
RHO, U, DIAMETER = 1000., .31, .028
DENOM = .5 * RHO * U**2 * DIAMETER
REFERENCE_FREQ = np.array([.80865, 1.6211, 2.4411, 3.2722, 4.1181, 4.9822])


def write(relative, value):
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def read_matrix(path):
    n = int(np.fromfile(path, dtype='<u8', count=1)[0])
    return np.fromfile(path, dtype='<f8', count=n*n, offset=8).reshape(n, n)


def spatial_square_mean(c):
    """Exact axial integral of squared NearestConstant/PiecewiseLinear field.

    The last dimension contains five center values. Any leading axes survive.
    """
    h = np.diff(CENTERS)
    segment = h * (c[..., :-1]**2 + c[..., :-1]*c[..., 1:] + c[..., 1:]**2) / 3.
    return ((CENTERS[0] * c[..., 0]**2 + segment.sum(axis=-1)
             + (L_ACTIVE-CENTERS[-1]) * c[..., -1]**2) / L_ACTIVE)


def spatial_integral(c):
    h = np.diff(CENTERS)
    return (CENTERS[0]*c[..., 0] + np.sum(h*(c[..., :-1]+c[..., 1:])/2., axis=-1)
            + (L_ACTIVE-CENTERS[-1])*c[..., -1])


def main():
    old_stats = json.loads((OLD/'analysis/windowed_dynamic_statistics.json').read_text())
    old_hydro = json.loads((OLD/'analysis/hydrodynamic_window_statistics.json').read_text())
    old_freq = json.loads((OLD/'analysis/windowed_frequency_peaks.json').read_text())
    t = np.load(BASE/'structure/full_riser_reconstruction.npz')['elapsed_s']
    dtype = np.dtype([('window','<u8'),('elapsed','<f8'),('q','<f8',(198,)),
                      ('v','<f8',(198,)),('a','<f8',(198,))])
    states = np.memmap(RT/'state_accepted_states.bin', dtype=dtype, mode='r')
    assert len(states) == len(t) == 25000
    assert np.max(np.abs(states['elapsed']-t)) < 1e-8

    M = read_matrix(OLD/'modal/M.bin')
    K = read_matrix(OLD/'modal/M.bin.K')
    fixed = {0,1,2,192,193}
    free = np.array([i for i in range(198) if i not in fixed])
    Mf, Kf = M[np.ix_(free,free)], K[np.ix_(free,free)]
    chol = np.linalg.cholesky((Mf+Mf.T)/2.)
    inv_chol = np.linalg.inv(chol)
    standard = inv_chol @ ((Kf+Kf.T)/2.) @ inv_chol.T
    values, vectors = np.linalg.eigh((standard+standard.T)/2.)
    order = np.argsort(values)
    values = values[order]
    phi = inv_chol.T @ vectors[:,order[:12]]
    eig_freq = np.sqrt(np.maximum(values[:12],0))/(2*np.pi)
    gram = phi.T @ Mf @ phi
    assert np.max(np.abs(gram-np.eye(12))) < 1e-8
    assert np.all(eig_freq > 0)
    # A 2D eigenspace may rotate without changing the physical family result.
    theta = .713
    rotation = np.array([[np.cos(theta),-np.sin(theta)],
                         [np.sin(theta), np.cos(theta)]])
    rotated = phi[:,2:4] @ rotation
    test_displacement = np.arange(len(free),dtype=float)/(len(free)**2)
    original_pair = test_displacement @ Mf @ phi[:,2:4]
    rotated_pair = test_displacement @ Mf @ rotated
    rotation_error = abs(np.linalg.norm(original_pair)-np.linalg.norm(rotated_pair))
    assert rotation_error < 1e-12
    pair_freq = eig_freq.reshape(6,2).mean(axis=1)
    (OUT/'modal').mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT/'modal/generated_basis_12.npz',free=free,
                        frequencies_Hz=eig_freq,phi_M_normalized=phi)
    freq_report = {
      'model':'frozen current ANCF mass and q0 tangent; 32 elements; 198 DOF',
      'basis_origin':str(Path('v2606_nm14_1_long10s_correction/modal/M.bin')),
      'source_kernel_modified':False,
      'constraint_dofs_zero_based':sorted(fixed),
      'eigenvector_frequencies_Hz':eig_freq.tolist(),
      'M_orthonormality_max_abs_error':float(np.max(np.abs(gram-np.eye(12)))),
      'families':[
        {'physical_family':i+1,'eigenvector_ordinals':[2*i+1,2*i+2],
         'frequency_Hz':float(pair_freq[i]),
         'reference_Hz':float(REFERENCE_FREQ[i]),
         'absolute_difference_Hz':float(abs(pair_freq[i]-REFERENCE_FREQ[i])),
         'relative_difference':float(abs(pair_freq[i]-REFERENCE_FREQ[i])/REFERENCE_FREQ[i]),
         'pair_split_Hz':float(abs(eig_freq[2*i+1]-eig_freq[2*i]))}
        for i in range(6)],
      'reference_status':'Huera-Huarte 2006 thesis Table 5.2, C001 May19 FEM frequencies at mean top tension 1188.28 N; simulation uses nominal 1175 N, so this is a near-tension rather than exact-state comparison',
    }
    write('modal/family_frequency_audit.json',freq_report)

    # Physical-axis restriction is made before projecting, but each family is
    # evaluated as the norm of both M-normalized subspace coordinates.
    is_x = np.isin(free%6, [0,3])
    is_y = np.isin(free%6, [1,4])
    family_windows = {}
    for label,(lo,hi) in WINDOWS.items():
        if label not in ('5-10s','7.5-10s'):
            continue
        mask = (t>=lo)&(t<=hi)
        q = np.asarray(states['q'][mask])
        dq = q-q.mean(axis=0)
        component_results = {}
        for axis,restriction in [('inline',is_x),('crossflow',is_y)]:
            component = np.array(dq[:,free],copy=True)
            component[:,~restriction]=0.
            coord = component @ Mf @ phi
            paired = coord.reshape(len(coord),6,2)
            pair_rms = np.sqrt(np.mean(np.sum(paired**2,axis=2),axis=0))
            pair_peak = np.max(np.sqrt(np.sum(paired**2,axis=2)),axis=0)
            component_results[axis] = {
              'pair_invariant_M_normalized_RMS':pair_rms.tolist(),
              'pair_invariant_M_normalized_peak':pair_peak.tolist(),
              'dominant_physical_family_by_RMS':int(np.argmax(pair_rms)+1),
              'note':'M-normalized coordinates have sqrt(kg)*m units, not displacement metres',
            }
        family_windows[label]={'sample_count':int(mask.sum()),**component_results}
    write('analysis/modal_family_projection.json',{
      'former_ny_4_and_nx_1':'raw eigenvector ordinals; ny=4 must be renamed physical family 2',
      'subspace_measure':'sqrt(time_mean(a_(2m-1)^2 + a_(2m)^2))',
      'mean_removal':'separate q mean in each window',
      'windows':family_windows})

    # Accepted direct force rows, never rejected trials or adapter coefficients.
    accepted_indices = []
    with (RT/'attempts.jsonl').open() as stream:
        for idx,line in enumerate(stream):
            if json.loads(line)['accepted']:
                accepted_indices.append(idx)
    assert len(accepted_indices)==len(t)
    direct = np.load(BASE/'forces/native_force_coefficients.npz')['direct']
    fy_raw = direct[:,accepted_indices,2].T
    fx_raw = direct[:,accepted_indices,1].T
    assert fy_raw.shape==(len(t),5)
    assert direct.shape[1] >= accepted_indices[-1]+1
    cy = (fy_raw/UNIT_SPAN)/DENOM
    cx = (fx_raw/UNIT_SPAN)/DENOM
    all_integrated_cl = spatial_integral(cy)/L_ACTIVE
    all_integrated_cd = spatial_integral(cx)/L_ACTIVE
    # Independent dense-grid trapz check of one actual accepted force profile.
    dense_s = np.linspace(0.,L_ACTIVE,200001)
    dense_profile = np.interp(dense_s,CENTERS,cy[12345])
    dense_mean_square = np.trapezoid(dense_profile**2,dense_s)/L_ACTIVE
    square_integral_difference = abs(dense_mean_square-spatial_square_mean(cy[12345]))
    assert square_integral_difference < 1e-9
    cl_report={}
    for label,(lo,hi) in WINDOWS.items():
        mask=(t>=lo)&(t<=hi)
        c=cy[mask]
        cprime=c-c.mean(axis=0,keepdims=True)
        local_rms=np.sqrt(np.mean(spatial_square_mean(cprime)))
        raw_local_rms=np.sqrt(np.mean(spatial_square_mean(c)))
        total=all_integrated_cl[mask]
        total_rms=np.std(total)
        assert abs(total_rms-old_hydro[label]['integrated_total_Cl_RMS'])<1e-12
        assert abs(all_integrated_cd[mask].mean()-old_hydro[label]['mean_Cd'])<1e-12
        cl_report[label]={
          'samples':int(mask.sum()),
          'ACTIVE_REGION_DISTRIBUTED_LOCAL_CL_RMS':float(local_rms),
          'FULL_RISER_ZERO_EXTENDED_CL_RMS_DIAGNOSTIC':float(local_rms*np.sqrt(L_ACTIVE/13.12)),
          'LOCAL_CL_RMS_INCLUDING_MEAN_diagnostic':float(raw_local_rms),
          'RMS_INTEGRATED_TOTAL_CL':float(total_rms),
          'mean_Cd':float(all_integrated_cd[mask].mean()),
          'mean_integrated_total_Cl':float(total.mean()),
          'local_Cl_mean_at_five_centers':c.mean(axis=0).tolist(),
          'local_Cl_fluctuation_RMS_at_five_centers':np.std(c,axis=0).tolist(),
        }
    write('analysis/distributed_huera_cl.json',{
      'physical_force_source':'accepted direct OpenFOAM Fy for five slices',
      'conversion':'Fy[N] / 0.028[m] once, then / (0.5*rho*U^2*D)',
      'rho_kg_m3':RHO,'U_m_s':U,'D_m':DIAMETER,'active_m':[0,L_ACTIVE],
      'mapping':'PiecewiseLinearDistributed + NearestConstant',
      'primary_formula':'sqrt((1/(L_active*T)) integral_time integral_0^L_active (Cl(s,t)-time_mean_Cl(s))^2 ds dt)',
      'axial_quadrature':'analytically exact integral of square of each linear segment, including constant end segments',
      'thesis_definition':'Huera-Huarte 2006 PDF p110, Eq 5.18 temporal standard deviation and Eq 5.20 spatial-first/time-second RMS form; PDF pp171-172 section 6.4.2 says transverse-force-coefficient RMS along riser model and in time, using Eq 5.18',
      'comparison_caveat':'Thesis Case 1 Table 6.1 uses full riser and whole riser was water-immersed; production CFD force reconstruction is exactly zero outside [0,5.94] m. Active-region RMS is not strictly commensurate with thesis full-riser 1.93; full-length zero extension is diagnostic and omits still-water hydrodynamic forces. Integrated-total Cl RMS is different by definition.',
      'windows':cl_report})
    write('analysis/numerical_self_checks.json',{
      'M_orthonormality_max_abs_error':float(np.max(np.abs(gram-np.eye(12)))),
      'family_2_subspace_rotation_norm_error':float(rotation_error),
      'analytical_vs_independent_dense_trapezoid_square_integral_error':float(square_integral_difference),
      'accepted_force_count':int(len(accepted_indices)),
      'state_count':int(len(states)),
      'direct_force_alignment_to_NM14_1_integrated_RMS':'PASS <=1e-12 for all four windows',
    })

    table=[]
    for label in ('5-10s','7.5-10s'):
        freq=old_freq[label]
        table.append({
          'window':label,
          'fy_Hz':freq['crossflow_peaks'][0]['frequency_Hz'],
          'physical_ny_by_modal_RMS':family_windows[label]['crossflow']['dominant_physical_family_by_RMS'],
          'fx_candidate_Hz':freq['inline_detrended_peaks'][0]['frequency_Hz'],
          'physical_nx_by_modal_RMS':family_windows[label]['inline']['dominant_physical_family_by_RMS'],
          'sigma_y_over_D':old_stats[label]['sigma_y_over_D_max'],
          'sigma_x_over_D':old_stats[label]['sigma_x_over_D_max'],
          'mean_Cd':cl_report[label]['mean_Cd'],
          'ACTIVE_REGION_DISTRIBUTED_LOCAL_CL_RMS':cl_report[label]['ACTIVE_REGION_DISTRIBUTED_LOCAL_CL_RMS'],
          'FULL_RISER_ZERO_EXTENDED_CL_RMS_DIAGNOSTIC':cl_report[label]['FULL_RISER_ZERO_EXTENDED_CL_RMS_DIAGNOSTIC'],
          'RMS_INTEGRATED_TOTAL_CL':cl_report[label]['RMS_INTEGRATED_TOTAL_CL'],
        })
    experimental={'physical_ny':2,'fy_Hz':1.66,'physical_nx':4,'fx_Hz':3.40,
                  'mean_Cd':1.86,'HUERA_RMS_Cl':1.93}
    write('comparison/late_window_comparison.json',{'simulation':table,'Huera_Case_1':experimental,
      'sigma_definition':'spanwise maximum temporal standard deviation / D, from NM14.1',
      'frequency_definition':'peak of representative s=2.97 m signal, finite-window resolution; not necessarily exact modal coordinate frequency'})
    freq_consistency={
      'CF':{'late_observed_Hz':[r['fy_Hz'] for r in table],
            'physical_family_2_natural_Hz':float(pair_freq[1]),
            'late_dominant_family_by_RMS':[r['physical_ny_by_modal_RMS'] for r in table],
            'supports_family_2':all(r['physical_ny_by_modal_RMS']==2 for r in table)},
      'IL':{'late_observed_candidate_Hz':[r['fx_candidate_Hz'] for r in table],
            'family_4_natural_Hz':float(pair_freq[3]),
            'family_5_natural_Hz':float(pair_freq[4]),
            'closer_natural_frequency_family':[4 if abs(r['fx_candidate_Hz']-pair_freq[3])<abs(r['fx_candidate_Hz']-pair_freq[4]) else 5 for r in table],
            'dominant_family_by_total_modal_RMS':[r['physical_nx_by_modal_RMS'] for r in table],
            'interpretation':'Spectral proximity does not relabel the dominant whole-window modal-energy family; assess 4-Hz band separately if needed.'},
    }
    write('analysis/frequency_mode_consistency.json',freq_consistency)
    decision={
      'classification':'V2606_NM14_2_MODAL_AND_CL_CORRECTED',
      'physical_ny_late':[r['physical_ny_by_modal_RMS'] for r in table],
      'physical_nx_late':[r['physical_nx_by_modal_RMS'] for r in table],
      'former_ny_4_nx_1':'raw eigenvector ordinals; prior ny=4 corrected to physical family 2',
      'CF_family_2_supported':freq_consistency['CF']['supports_family_2'],
      'IL_4Hz_frequency_closest_family':freq_consistency['IL']['closer_natural_frequency_family'],
      'HUERA_Cl_status':'THESIS_DEFINITION_VERIFIED; ACTIVE_REGION_VALUE_NOT_STRICTLY_COMPARABLE_TO_FULL_RISER_CASE_1',
      '10_TO_15_EXTENSION':'RECOMMENDED',
      'extension_reason':'The distributed local Cl RMS is nearly unchanged across late windows, but integrated-total Cl RMS changes and the 5 s/2.5 s spectral windows have coarse 0.2/0.4 Hz resolution; stationarity and a robust inline VIV frequency remain unestablished',
      'real_simulation_started':False,
      'production_data_modified':False,
    }
    write('comparison/final_classification.json',decision)
    print(json.dumps({'family_frequencies_Hz':pair_freq.tolist(),
                      'windows':table,'decision':decision},indent=2))


if __name__=='__main__':
    main()
