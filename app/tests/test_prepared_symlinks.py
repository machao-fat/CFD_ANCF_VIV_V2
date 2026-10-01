"""Prepared identity regressions. Only tiny Python fixtures execute."""
import importlib.util
import json
import os
import shutil
import sys

import pytest

from viv_app.generator.production_baseline import PROFILE, PROFILE_ROOT, LABELS, FIELDS, MESH_FIELDS, file_identity
from viv_app.runner.contract import load_contract, check_decomposition, prepared_identity, digest
from viv_app.runner.manager import RunManager, write
from viv_app.runner.state import RunState
from viv_app.runner.prepared_symlinks import qualified_uniform_symlink_identity, METADATA_FILES, MAX_METADATA_BYTES
from viv_app.utils.paths import APP_ROOT, CASES_ROOT


@pytest.fixture
def prepared_case(tmp_path):
    root = tmp_path / 'prepared'; root.mkdir(); (root / 'runtime').mkdir(); (root / 'Structure').mkdir()
    initial = json.loads((PROFILE_ROOT / 'app_baseline.json').read_text())['initial_time_default']
    fixture = APP_ROOT / 'app/tests/fixtures/fake_n5_decomposition.py'
    module_spec = importlib.util.spec_from_file_location('fake_n5_decomposition', fixture)
    module = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(module)
    rows = []
    for i, label in enumerate(LABELS, 1):
        fluid = root / f'fluid_{label}'
        (fluid / 'system').mkdir(parents=True); (fluid / 'system/controlDict').write_text('SYNTHETIC CONFIG')
        uniform = fluid / initial / 'uniform'
        (uniform / 'functionObjects').mkdir(parents=True)
        for name in METADATA_FILES:
            (uniform / name).write_text('SYNTHETIC METADATA ' + name)
        module.prepare(fluid, initial)
        rows.append({'participant': f'Fluid-S{i}', 'cwd': fluid.name, 'cpu_set': f'{4*(i-1)}-{4*i-1}', 'mpi_ranks': 4,
                     'command': [sys.executable, '-c', "from pathlib import Path; Path('actor_ran').touch(); raise SystemExit(99)"],
                     'prepare_command': [sys.executable, str(fixture), initial],
                     'environment': {'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}})
    structure = {'participant': 'Structure', 'cwd': 'Structure', 'cpu_set': '20', 'mpi_ranks': 1,
                 'command': rows[0]['command'], 'environment': rows[0]['environment']}
    write(root / 'launch_manifest.json', {'schema': 'viv-app-production-launch-v1', 'structure': structure, 'fluid': rows,
                                         'expected_participant_count': 6, 'total_cfd_ranks': 20,
                                         'startup_order': ['manual: decompose all five selected initial states', 'Structure',
                                                           *[row['participant'] for row in rows]]})
    write(root / 'generation_manifest.json', {'contract_profile': PROFILE, 'generation_status': 'PASS', 'slice_count': 5,
                                             'deltaT': .0004, 'mpi_ranks': [4]*5, 'max_time_windows': 5, 'coupled_duration_s': .002})
    write(root / 'baseline_contract_snapshot.json', {'contract_profile': PROFILE, 'initial_time_default': initial})
    for name in ('precice-config.xml', 'production_xml_template.xml', 'simulation_spec.yaml', 'slice_manifest.json',
                 'Structure/initial_state.raw', 'Structure/structure_config.json', 'Structure/compiled_kernel_model.json'):
        (root / name).write_text('SYNTHETIC CONFIG')
    return load_contract(root)


def link_path(c, rank=0, fluid=0):
    return c.root / c.launch['fluid'][fluid]['cwd'] / f'processor{rank}' / c.baseline['initial_time_default'] / 'uniform'


def replace_link(path, target):
    path.unlink(); path.symlink_to(target)


@pytest.mark.smoke
def test_t1_twenty_qualified_uniform_links_and_stable_identity(prepared_case):
    c = prepared_case
    assert len(check_decomposition(c)) == 5
    before = prepared_identity(c)
    assert before == prepared_identity(c)
    assert len(before['qualified_uniform_symlinks']) == 20
    for identity in before['qualified_uniform_symlinks'].values():
        assert identity['kind'] == 'qualified_case_local_symlink'
        assert identity['link_target'] == f"../../{c.baseline['initial_time_default']}/uniform"
        assert identity['resolved_target'] == f"{c.baseline['initial_time_default']}/uniform"
        assert identity['target_type'] == 'directory'
        assert set(identity['target_identity']['files']) == set(METADATA_FILES)


@pytest.mark.smoke
@pytest.mark.parametrize('kind', ['absolute', 'escape', 'other_fluid', 'broken', 'U', 'wrong_time', 'points', 'controlDict'])
def test_t2_to_t9_unqualified_links_fail_closed(kind, prepared_case):
    c = prepared_case; p = link_path(c); initial = c.baseline['initial_time_default']
    fluid = c.root / c.launch['fluid'][0]['cwd']
    if kind == 'absolute': replace_link(p, str(fluid / initial / 'uniform'))
    if kind == 'escape':
        outside = (p.parent / '../../../../outside').resolve()
        outside.mkdir()
        replace_link(p, '../../../../outside')
    if kind == 'other_fluid': replace_link(p, f'../../../{c.launch["fluid"][1]["cwd"]}/{initial}/uniform')
    if kind == 'broken': replace_link(p, f'../../{initial}/absent')
    if kind == 'U':
        p = p.parent / 'U'; replace_link(p, f'../../{initial}/uniform/time')
    if kind == 'wrong_time':
        p = fluid / 'processor0/30.5/uniform'; p.parent.mkdir(); p.symlink_to(f'../../{initial}/uniform')
    if kind == 'points':
        p = fluid / 'processor0/constant/polyMesh/points'; replace_link(p, '../../../system/controlDict')
    if kind == 'controlDict':
        p = fluid / 'system/controlDict'; replace_link(p, f'../{initial}/uniform/time')
    with pytest.raises(ValueError): prepared_identity(c)
    if kind != 'controlDict':
        with pytest.raises(ValueError): check_decomposition(c)
    with pytest.raises(ValueError): qualified_uniform_symlink_identity(c.root, c.launch['fluid'], c.baseline, p)


@pytest.mark.smoke
def test_t10_post_prepare_retarget_is_rejected(prepared_case):
    c = prepared_case; before = prepared_identity(c)
    replace_link(link_path(c), f'../.././{c.baseline["initial_time_default"]}/uniform')
    # Even a semantically equivalent destination with unexpected link text is refused.
    with pytest.raises(ValueError, match='link text'): prepared_identity(c)
    assert before['qualified_uniform_symlinks']


@pytest.mark.smoke
def test_t11_target_content_drift_is_observable(prepared_case):
    c = prepared_case; before = prepared_identity(c)
    target = link_path(c).resolve() / 'functionObjects/functionObjectProperties'
    target.write_text(target.read_text() + '\nCHANGED')
    after = prepared_identity(c)
    assert before != after
    assert before['qualified_uniform_symlinks'][str(link_path(c).relative_to(c.root))] != after['qualified_uniform_symlinks'][str(link_path(c).relative_to(c.root))]


@pytest.mark.smoke
def test_t12_ordinary_inputs_keep_existing_bounded_identity(prepared_case):
    c = prepared_case
    for row in c.launch['fluid']:
        for rank in range(4):
            p = c.root / row['cwd'] / f'processor{rank}' / c.baseline['initial_time_default'] / 'uniform'
            target = p.resolve(); p.unlink(); shutil.copytree(target, p)
    assert len(check_decomposition(c)) == 5
    identity = prepared_identity(c)
    assert identity['qualified_uniform_symlinks'] == {}
    for row in c.launch['fluid']:
        for rank in range(4):
            for relative in [*[f'{c.baseline["initial_time_default"]}/{f}' for f in FIELDS], *[f'constant/polyMesh/{f}' for f in MESH_FIELDS]]:
                p = c.root / row['cwd'] / f'processor{rank}' / relative
                assert identity['prepared_initial_bounded_identities'][str(p.relative_to(c.root))] == file_identity(p)


@pytest.mark.smoke
@pytest.mark.parametrize('kind', ['nested_link', 'unknown_metadata', 'oversized', 'system_parent', 'processor_parent', 'wrong_rank', 'wrong_profile', 'wrong_initial', 'wrong_enrollment', 'broken_config'])
def test_additional_fail_closed_boundaries(kind, prepared_case):
    c = prepared_case; link = link_path(c); target = link.resolve(); fluid = link.parents[2]
    if kind == 'nested_link': replace_link(target / 'time', 'cumulativeContErr')
    if kind == 'unknown_metadata': (target / 'extra').write_text('unqualified')
    if kind == 'oversized': (target / 'time').write_bytes(b'x'*(MAX_METADATA_BYTES+1))
    if kind == 'system_parent':
        (fluid / 'system').rename(fluid / 'system_original'); (fluid / 'system').symlink_to('system_original')
    if kind == 'processor_parent':
        (fluid / 'processor0').rename(fluid / 'original'); (fluid / 'processor0').symlink_to('original')
    if kind == 'wrong_rank':
        path = fluid / 'processor4' / c.baseline['initial_time_default'] / 'uniform'; path.parent.mkdir(parents=True); path.symlink_to(os.readlink(link))
    if kind == 'wrong_profile': c.baseline['contract_profile'] = 'other'
    if kind == 'wrong_initial': c.baseline['initial_time_default'] = '30'
    if kind == 'wrong_enrollment': c.launch['fluid'][0]['participant'] = 'other'
    if kind == 'broken_config': replace_link(fluid / 'system/controlDict', 'absent')
    with pytest.raises(ValueError):
        if kind == 'wrong_rank': check_decomposition(c)
        else: prepared_identity(c)


class OfflineIdentityGate:
    """No production validation/process command may execute in these fixtures."""
    def contract(self, root): return load_contract(root)
    def validate(self, root, prepared=False): return {'status': 'PASS', 'scope': 'SYNTHETIC_ONLY'}
    def preflight(self, root, prepared=False): return {'status': 'PASS', 'production_launch_ready': True, 'scope': 'SYNTHETIC_ONLY'}
    def fresh(self, c):
        from viv_app.runner.contract import fresh_execution
        fresh_execution(c)
    def decomposition(self, c): return check_decomposition(c)
    def identity(self, c): return prepared_identity(c)
    def app_identity(self): return {'commit': 'SYNTHETIC_ONLY', 'source_hashes': {'fake': 'fixed'}}


@pytest.mark.smoke
@pytest.mark.parametrize('drift', ['retarget', 'content'])
def test_real_manager_gate_rejects_drift_without_participant_launch(drift, prepared_case):
    c = prepared_case
    # Remove only tiny fixture processors. Prepare creates them via tiny Python children.
    for row in c.launch['fluid']:
        for rank in range(4): shutil.rmtree(c.root / row['cwd'] / f'processor{rank}')
    manager = RunManager(c.root, gate=OfflineIdentityGate()); manager.prepare(); manager.thread.join(45)
    assert not manager.busy and manager.state == RunState.PREPARED
    assert len(manager.preparation['input_identity']['qualified_uniform_symlinks']) == 20
    assert all(row['exit_code'] == 0 for row in manager.preparation['decomposition_results'])
    if drift == 'retarget': replace_link(link_path(c), '../../../../outside')
    else: (link_path(c).resolve() / 'time').write_text('drifted metadata')
    manager.run(); manager.thread.join(45)
    assert not manager.busy and manager.state == RunState.FAILED
    assert not manager.records and manager.run_dir is None
    assert not list(c.root.rglob('actor_ran'))
    if drift == 'content': assert 'Prepared inputs changed after Prepare' in manager.first_failure['reason']


@pytest.mark.production_integration
@pytest.mark.parametrize('case_name', ['production_N5_gui_smoke5_v1', 'production_N5_app_smoke5'])
def test_t13_t14_real_case_witnesses_read_only(case_name):
    root = CASES_ROOT / case_name
    if not root.is_dir(): pytest.skip('Local host witness unavailable')
    c = load_contract(root); links = [link_path(c, r, f) for f in range(5) for r in range(4)]
    watched = [root / n for n in ('launch_manifest.json', 'generation_manifest.json', 'preparation_result.json', 'generation_validation.json') if (root / n).is_file()]
    watched += list({p.resolve() / name for p in links for name in METADATA_FILES})
    def snapshot():
        return ({str(p): (os.readlink(p), p.lstat().st_mtime_ns) for p in links},
                {str(p): (digest(p), p.stat().st_mtime_ns) for p in watched})
    before = snapshot()
    identities = [qualified_uniform_symlink_identity(root, c.launch['fluid'], c.baseline, p) for p in links]
    assert len(identities) == 20
    if case_name.endswith('gui_smoke5_v1'):
        assert len(check_decomposition(c)) == 5
        assert len(prepared_identity(c)['qualified_uniform_symlinks']) == 20
        from viv_app.generator.production_validation import validate_production_case
        assert validate_production_case(root, write_report=False, prepared=True)['status'] == 'PASS'
        # Ordinary generation still rejects decomposed cases; neither mode writes.
        assert validate_production_case(root, write_report=False)['status'] == 'FAIL'
    assert snapshot() == before
