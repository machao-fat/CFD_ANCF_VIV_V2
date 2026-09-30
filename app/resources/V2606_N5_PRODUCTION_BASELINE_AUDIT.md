# V2606 N5 production baseline audit

Task: VIV_APP_PRODUCTION_BASELINE_BRIDGE_V1. Base APP commit 333cbb8f0defce230c5d881bcb008779ba00b972. Audit is read only; no production launcher, participant, decomposition, reconstruction or solver was executed.

## Authority and evidence

Source: `/mnt/d/CFD_Work/projects/CFD_ANCF_VIV_V2_of2606/evidence/v2606_nm12_n5_4rank_diagnostic100`.
`comparison/final_classification.json`: **V2606_NM12_N5_4RANK_DISTRIBUTED_MAPPING_DIAGNOSTIC100_PASS**. 100 accepted windows, six successful participant exits, no forced acceptance, strict convergence, rollback verification, exactly-once conversion. Qualification is short100 only; Huera validation and spatial adequacy are not established.

NM13 `comparison/final_classification.json` is **V2606_NM13_N5_LONG10S_CONFIGURATION_READY**, REAL_LONG_RUN_STARTED=NO. NM13.1 is **V2606_NM13_1_LONG10S_POSTPROCESS_DATA_READY**, also REAL_LONG_RUN_STARTED=NO. Runtime directories now exist, but these records alone cannot certify their subsequent long run. They are not used as successful-run evidence. APP chooses NM12, not the long-run output. NM13's explicit disjoint CPU launch description supplies a portable command layout; it does not change physics.

OpenFOAM.com v2606; preCICE 3.4.1; official adapter v1.4.0 at `/home/machao/OpenFOAM/v2606-precice-adapter/lib/libpreciceAdapterFunctionObject.so`, SHA256 `51bf2889e5aab6867d17b78764faacecb2f467102f925332467b8b188b1cbed9`.
Structure: NM12 `source/structure_n5`, SHA256 `a97c82657fb99ba838c3966e5bd0bc2bd943af9741278662ddaf0109fc08df33`; C++ source SHA256 `4e466f0333772899c4092173edbf058b5af5392f4b02e9358a286ee72f0719d4`. Descriptor pins actual selected artifacts/configurations; importing checks the PASS classification and all enrolled identities, not an evidence label alone.

## A–L: actual contract

A. `run_nm12.py` invokes `structure_n5 XML Q0 attempts.jsonl accepted_windows.jsonl state_attempt_PREFIX -1.2923689896027213e-18 1.235990476633475e-18`, cwd `launch/structure`. Seven positional arguments after executable. External immutable executable, local XML/state/logs. No null command and no new structural runner.

B. This executable fixes NSLICES=5, S_M and make_model() in source. It does **not** read arbitrary-N manifest/config input. APP's structure_config and KernelModel witness are descriptive provenance, not physics inputs to this binary. All these parameters are locked.

C. N3 and N5 are separate compiled coordinators. NM10.4 identity points to NM10.1 `source/clean_structure_candidate.cpp` (NSLICES=3, positions .99/2.97/4.95) and binary SHA256 `35e6fb29f5365f2ac9e4ba75d9ed977837218221466133845ad30e760b0e517a`, different from NM12 N5. The NM12 preparation uses NM10.4 N3 fluid dictionaries as lineage, but derives a new N5 structural source/binary; changing a manifest cannot turn this executable into N3. No N3/arbitrary-N bridge is exposed.

D. `prepare_nm12.py::xml_text()` constructed the production XML, then `precice-config-validate` verified it. APP reads that existing template and structurally changes only max-time-windows and socket exchange paths. Namespace declarations are added for genuine standard XML parsing; prefixed element names are retained. Semantic comparison masks only horizon/path, retaining every mathematical attribute and child.

E/F. Actual names: **Fluid-S1…Fluid-S5**, **Structure**. Not Fluid_0000/Structure_0000. Fluid meshes Fluid-Mesh-S1…S5; structural meshes Solid-S1…S5; data Force-Si/Displacement-Si.

G. `system/preciceDict`: `participant Fluid-Si`, `preciceConfig` local XML; `interfaces/Interface1/mesh Fluid-Mesh-Si`, patches `(cylinder)`, locations faceCenters, readData `(Displacement-Si)`, writeData `(Force-Si)`. Incompressible rho=1000 and nu inherited. APP uses exact dictionary paths for all edits.

H. Five cases x four MPI ranks, plus one Structure process (20 CFD ranks). v2606 bashrc must be sourced for every MPI child; pimpleFoam -parallel -case CASE. NM13 launch records explicitly bind Fluid CPU sets 0–3,4–7,8–11,12–15,16–19 and Structure 20, with hwloc_base_cpu_list/use-hwthread-cpus/bind-to hwthread; one thread for OMP/OpenBLAS/MKL. APP locks ranks=4. Serial initial fields and mesh are generated; `decomposePar -time INITIAL_TIME` is an explicit **manual preparation** command. No processor directories are copied, and APP does not execute this command. Launch-ready means all manual preparation/launch commands and input artifacts pass preflight, not that decomposition or a solver ran.

I/J. Actual structural S_M = 0.594,1.782,2.970,4.158,5.346 m in clean_structure_n5.cpp, copied into Model and MappingManifest. Active interval [0,5.94] m; PiecewiseLinearDistributed/NearestConstant enter `assemble()` through MappingConfig. APP locks these and mirrors them in its manifest/witness. XML vertices are runtime mesh coordinates, not structural arc lengths, so no invented XML slice-position field is added.

K. `distributed_force_mapping.cpp::assemble` calls `raw_force_to_line_force`; that function divides Fraw by unit_span_m=0.028. Structural assemble feeds raw integrated force into this layer once. APP never scales force or applies tributary multipliers. Legacy tributary length=1.188 remains unused in distributed path. ANCF core and adapter are external and unchanged.

L. One implicit `coupling-scheme:multi`; Structure controls; dt/window=0.0004 s; max-time-windows=100; max-iterations=50; ten relative convergence measures (both data for all five slices), limit=5e-3, strict=true. IQN-ILS, residual-sum preconditioner, QR2 filter limit=1e-2, initial relaxation=0.5, max-used-iterations=100, time-windows-reused=15. Fluid↔Solid nearest-neighbor conservative write/consistent read; ten exchanges. No generic explicit helper is used.

## Initial state, copying, safe changes

Fluid fresh release uses `29.9999999999834372` from frozen30 reconstruction. Selected time contains U,U_0,p,phi,k,k_0,omega,omega_0,nut,pointDisplacement,uniform and ancillary fields. APP copies this selected directory byte-for-byte except U's exact inlet vector and cylinder type. NM12 prepare changed cylinder fixedValue→movingWallVelocity on processor initial U, but its reconstructed serial U retains fixedValue. APP applies the **same established preparation** to the serial U before the user's manual decomposition; internalField, U_0, phi/phi_0 and other old-time files remain unchanged. It does not create Uf,meshPhi,cellDisplacement or deformed restart fields. This is fresh frozen30 release, not cross-process restart. Required startup fields follow production START_FIELDS, not generic ALE restart requirements.

Structure reads P1_REF_NE32 CASE/Q from ancf_static.raw (198 DOFs). APP extracts the original CASE/Q text unchanged into case-local initial_state.raw; binary initializes zero velocities/accelerations and static base load according to its existing code. No regenerated equilibrium. L=13.12,D=.028,EA=7470000,EI=29.88,line mass=1.845,pretension=1175,Ne=32,damping=0; full-span SHM1 added mass(.616,.616,0), zero linear damping; locked.

NM12 write policy: binary fields, timeStep/20, purge2; force diagnostics inherited, including forceCoeffs interval5 and yPlus writeTime. GUI endTime, writeInterval/purgeWrite and per-slice inlet U are editable; dt fixed. Coefficient magUInf is updated at its exact dictionary path to U_i; at U_i=0, forceCoeffs is disabled via enabled=false to avoid division by zero while retaining native forces and FSI. This change affects diagnostics only. Observer outputDir paths are moved to case-local runtime folders; observer shared libraries remain pinned external dependencies. Solvers, schemes, PIMPLE, turbulence, dynamic mesh, mapping and coupling semantics are inherited.

Excluded: processor*, runtime, logs, postProcessing, other times, checkpoints and communication directories. No production mesh or baseline is tracked in Git. The descriptor records external locations and selected key hashes only. Mesh/large-field identity uses bounded samples and sizes, not a whole historical-runtime SHA256 scan.

## Accepted-state logging and environment repair

NM12 source records attempted checkpoint/trial q/v state binaries per iteration (`state_attempt_...`); accepted_windows.jsonl is written only when requiresReadingCheckpoint=false, with window/attemptOrdinal/iterations/physical_time_s/F_raw_N/F_line_Npm/displacements/q_norm/v_norm. Its physical clock is 30+elapsed. APP preserves this native CLI/logging contract and relocates outputs to its own runtime folder. It does not implement an accepted-state recorder. NM13's observational source instead adds fixed-width accepted q[198],v[198],qddot[198] records (4768 bytes/record, flush each accepted window; checkpoint every250). NM13.1 audit describes these fields and projected25000 records; this describes a prepared contract rather than proving a completed long run. NM12 logging/I/O can be large at long duration; no restart guarantee is claimed.

OpenFOAM `etc/bashrc` line204 forwards inherited `$@` into config.sh/setup. Passing the environment pathname as inherited positional argument recursively re-initializes it. The APP saves the intended command args, clears `$@` before sourcing, then execs the saved argv. A regression verifies zero inherited setup args and literal command arguments; the same generated case launch descriptors were repaired, not regenerated. Local OpenFOAM functionObjectList.C lines1047–1108 explicitly honors `enabled=false`, supporting the zero-flow coefficient diagnostic guard.

Observer portability was checked against local `diagnostics/nm8_2WallObserver/WallObserver.C`, `nm8_3InputObserver/InputObserver.C`, and `nm8_3_1ForceResultObserver/ForceResultObserver.C`: WallObserver only emits Info; other observers open the configured outputDir directly with std::ofstream. The generated launch cwd is each fluid root and runtime folders are created there. v2606 argList::setCasePaths uses cwd for `-case .` and records processor paths without chdir; therefore relative observer outputDir resolves into the new fluid case. No observer source/library is modified.
