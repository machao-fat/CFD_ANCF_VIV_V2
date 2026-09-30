"""Generate and preflight only. Absolutely no production solver is launched."""
from viv_app.generator.production_baseline import PROFILE_ROOT,POSITIONS,STRUCTURE
from viv_app.models.simulation_spec import SimulationSpec,FlowProfile
from viv_app.generator.case_generator import generate_case
from viv_app.generator.production_preflight import production_preflight
from viv_app.utils.paths import CASES_ROOT


def main():
    spec=SimulationSpec('production_N5_bridge_dryrun',str(PROFILE_ROOT),str(CASES_ROOT),
        '29.9999999999834372',tuple(p/STRUCTURE.length_m for p in POSITIONS),(4,)*5,
        STRUCTURE,FlowProfile(kind='Uniform',u0=.31),.0004,30.04,20,purge_write=2)
    root=generate_case(spec,lambda percent,message:print(percent,message,flush=True))
    result=production_preflight(root,lambda percent,message:print(percent,message,flush=True))
    print('CASE',root,'PRODUCTION_PREFLIGHT',result['status'],'PRODUCTION_LAUNCH_READY',result['production_launch_ready'],
          'REAL_FSI_STARTED',result['real_fsi_started'],flush=True)
    if result['status']!='PASS':raise SystemExit(result['first_failure'])


if __name__=='__main__':main()
