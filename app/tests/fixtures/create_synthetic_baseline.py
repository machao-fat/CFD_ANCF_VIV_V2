"""Tiny OFFLINE ONLY fixture. Never a CFD or FSI qualification baseline."""
from pathlib import Path
from dataclasses import asdict,replace
import json
from viv_app.generator.native import build_slice_manifest,generate_precice_xml,KernelModel,SpanwiseHydrodynamicRegion
from viv_app.generator.baseline import NAMING
from viv_app.utils.paths import APP_ROOT,within,local_path


def make_baseline(directory,distributed=True,developed=False):
    root=local_path(directory)
    if not within(root,APP_ROOT): raise ValueError('fixtures must stay inside APP')
    root.mkdir(parents=True,exist_ok=False)
    fluid=root/'fluid'; system=fluid/'system'; constant=fluid/'constant'
    time='30' if developed else '0'
    field=fluid/time
    for p in (system,constant/'polyMesh',field/'uniform'): p.mkdir(parents=True,exist_ok=True)
    def write(path,text): path.write_text(text,encoding='utf-8')
    def js(path,value): write(path,json.dumps(value,indent=2)+'\n')
    mode='PiecewiseLinearDistributed' if distributed else 'LegacyPointLumped'
    n=3 if distributed else 1
    manifest=build_slice_manifest({'case_id':'synthetic_baseline','length_m':10.,
        'interfaces':{'structure_participant':'Structure_0000'},
        'coupling':{'mode':mode,'placement':'uniform_centers','count':n,
                    'active_start_m':0.,'active_end_m':10.,'unit_span_m':0.028}})
    manifest=replace(manifest,slices=tuple(replace(row,fluid_participant=f'Fluid_{i:04d}',openfoam_case_id=f'slice{i:04d}') for i,row in enumerate(manifest.slices)),manifest_sha256=None)
    js(root/'slice_manifest.json',manifest.to_dict())
    model=KernelModel(length_m=10.,diameter_m=.028,inner_diameter_m=.024,elements=4,slices=n,
        top_tension_N=1175.,slice_positions_m=tuple(row.s_ref_m for row in manifest.slices),
        section_property_mode='explicit',explicit_EA_N=7470000.,explicit_EI_Nm2=29.88,
        explicit_mass_per_length_kg_m=1.845,explicit_displaced_area_m2=.00061575216,
        base_load_source='model_static',
        spanwise_load_reconstruction='piecewise_linear_distributed' if distributed else 'legacy_point_lumped',
        spanwise_active_s_min_m=0.,spanwise_active_s_max_m=10. if distributed else None,
        hydrodynamic_regions=(SpanwiseHydrodynamicRegion(0.,10.,(.616,.616,0.),(0.,0.,0.)),))
    model.validate(.0002)
    js(root/'kernel_model.json',asdict(model))
    q=[]
    for i in range(model.elements+1): q.extend([0.,0.,i*10/model.elements,0.,0.,1.])
    js(root/'initial_state.json',{'q':q,'qdot':[0.]*model.ndof,'qddot':[0.]*model.ndof})
    control=f'''FoamFile {{ format ascii; class dictionary; object controlDict; }}
application pimpleFoam;
startFrom startTime;
startTime {time};
stopAt endTime;
endTime {float(time)+.2:.10g};
deltaT 0.0002;
writeControl adjustableRunTime;
writeInterval 0.01;
adjustTimeStep no;
writeFormat ascii;
functions
{{
    adapter {{ type preciceAdapterFunctionObject; libs ("libpreciceAdapterFunctionObject.so"); }}
    exampleDiagnostic {{ writeControl timeStep; writeInterval 5; }}
}}
'''
    write(system/'controlDict',control)
    write(system/'decomposeParDict','FoamFile { format ascii; class dictionary; object decomposeParDict; }\nnumberOfSubdomains 4;\nmethod scotch;\n')
    write(system/'fvSchemes','FoamFile { format ascii; class dictionary; object fvSchemes; }\nddtSchemes { default Euler; }\n')
    write(system/'fvSolution','FoamFile { format ascii; class dictionary; object fvSolution; }\nPIMPLE { nCorrectors 2; }\n')
    write(system/'preciceDict',f'''FoamFile {{ format ascii; class dictionary; object preciceDict; }}
preciceConfig "precice-config.xml";
participant {manifest.slices[0].fluid_participant};
modules (FSI);
FSI {{ solverType incompressible; rho rho [1 -3 0 0 0 0 0] 1000; namePointDisplacement pointDisplacement; nameCellDisplacement cellDisplacement; nameForce Force; }}
interfaces {{ Interface1 {{ mesh {manifest.slices[0].fluid_mesh}; patches (cylinder); locations faceCenters; readData (Displacement); writeData (Force); }} }}
''')
    write(constant/'physicalProperties','FoamFile { format ascii; class dictionary; object physicalProperties; }\nnu [0 2 -1 0 0 0 0] 1.13881e-6;\n')
    write(constant/'momentumTransport','FoamFile { format ascii; class dictionary; object momentumTransport; }\nsimulationType laminar;\n')
    write(constant/'dynamicMeshDict','FoamFile { format ascii; class dictionary; object dynamicMeshDict; }\ndynamicFvMesh dynamicMotionSolverFvMesh;\nmotionSolver displacementLaplacian;\n')
    # Deliberately minimal synthetic mesh; it is not a cylinder CFD mesh.
    header=lambda obj,cls:f'FoamFile {{ format ascii; class {cls}; object {obj}; }}\n'
    write(constant/'polyMesh/points',header('points','vectorField')+'8\n(\n(0 0 0) (1 0 0) (1 1 0) (0 1 0) (0 0 .028) (1 0 .028) (1 1 .028) (0 1 .028)\n)\n')
    write(constant/'polyMesh/faces',header('faces','faceList')+'6\n(4(0 4 7 3) 4(1 2 6 5) 4(0 1 5 4) 4(3 7 6 2) 4(0 3 2 1) 4(4 5 6 7))\n')
    write(constant/'polyMesh/owner',header('owner','labelList')+'6\n(0 0 0 0 0 0)\n')
    write(constant/'polyMesh/neighbour',header('neighbour','labelList')+'0\n()\n')
    write(constant/'polyMesh/boundary',header('boundary','polyBoundaryMesh')+'5\n( inlet { type patch; nFaces 1; startFace 0; } outlet { type patch; nFaces 1; startFace 1; } cylinder { type wall; nFaces 2; startFace 2; } front { type empty; nFaces 1; startFace 4; } back { type empty; nFaces 1; startFace 5; } )\n')
    u=f'''FoamFile {{ format ascii; class volVectorField; location "{time}"; object U; }}
dimensions [0 1 -1 0 0 0 0];
internalField uniform (0.31 0 0);
boundaryField
{{
    inlet {{ type fixedValue; value uniform (0.31 0 0); }}
    outlet {{ type zeroGradient; }}
    cylinder {{ type movingWallVelocity; value uniform (0 0 0); }}
    front {{ type empty; }}
    back {{ type empty; }}
}}
'''
    write(field/'U',u)
    required=['U','p','pointDisplacement','cellDisplacement','phi','Uf','meshPhi']
    for name in required[1:]:
        cls='volScalarField' if name=='p' else 'volVectorField'
        write(field/name,f'FoamFile {{ format ascii; class {cls}; location "{time}"; object {name}; }}\ninternalField uniform 0;\nboundaryField {{ inlet {{ type zeroGradient; }} }}\n')
    write(field/'U_0','OPAQUE_SYNTHETIC_OLD_TIME_STATE\n')
    write(field/'uniform/time',f'value {time};\nindex 0;\ndeltaT 0.0002;\n')
    write(fluid/'precice-config.xml',generate_precice_xml(manifest,time_window_s=.0002,max_time_s=float(f'{float(time)+.2:.10g}')-float(time),exchange_directory='/old/runtime/precice-sockets')+'\n')
    js(root/'app_baseline.json',{
        'schema':'viv-app-baseline-v1','contract_profile':'arbitrary-n-live-explicit-v1',
        'evidence_status':'SYNTHETIC_OFFLINE_ONLY','fluid_case':'fluid',
        'slice_manifest':'slice_manifest.json','kernel_model':'kernel_model.json',
        'structure_initial_state':'initial_state.json','initial_time_default':time,
        'flow':{'field':'U','inlet_patch':'inlet','direction':[1.,0.,0.],'preserve_internal_field':True},
        'required_initial_fields':required,'time_window_equals_delta_t':True,'naming':NAMING,
    })
    write(root/'README.md','SYNTHETIC_OFFLINE_ONLY. Tiny configuration fixture. Not a qualified OpenFOAM mesh or FSI baseline. Do not run it.\n')
    return root


if __name__=='__main__':
    for name,distributed in [('synthetic_distributed',True),('synthetic_legacy_n1',False)]:
        path=APP_ROOT/'workspace/baselines'/name
        if path.exists(): print('REFUSED EXISTING FIXTURE:',path)
        else: print(make_baseline(path,distributed))
