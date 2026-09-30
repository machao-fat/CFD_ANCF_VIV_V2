"""Generate small offline examples. Refuses any existing target; never runs CFD."""
from viv_app.generator.baseline import inspect_baseline
from viv_app.generator.case_generator import generate_case
from viv_app.models.simulation_spec import SimulationSpec,FlowProfile,uniform_positions
from viv_app.utils.paths import APP_ROOT,CASES_ROOT


def main():
    for n in (1,3,5):
        name='synthetic_legacy_n1' if n==1 else 'synthetic_distributed'
        baseline=inspect_baseline(APP_ROOT/'workspace/baselines'/name)
        profile=FlowProfile(kind='Step Current' if n==5 else 'Uniform')
        case_name=f'synthetic_N{n}_step' if n==5 else f'synthetic_N{n}_uniform'
        spec=SimulationSpec(case_name,str(baseline.root),str(CASES_ROOT),'0',
            uniform_positions(n,baseline.model.length_m,baseline.manifest.active_start_m,baseline.manifest.active_end_m),
            (4,)*n,baseline.structure,profile,.0002,.2,.01,placement='uniform')
        print(generate_case(spec),flush=True)


if __name__=='__main__': main()
