import importlib.util
from pathlib import Path
import pytest
import os
from viv_app.utils.paths import APP_ROOT

spec=importlib.util.spec_from_file_location('fixture_builder',APP_ROOT/'app/tests/fixtures/create_synthetic_baseline.py')
fixture_builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_builder)


@pytest.fixture
def baseline_factory(tmp_path):
    def create(distributed=True,developed=False):
        return fixture_builder.make_baseline(tmp_path/('baseline_distributed' if distributed else 'baseline_legacy'),distributed,developed)
    return create


def pytest_configure(config):
    # Keep every test artifact under APP, also when tests are invoked from app/.
    parent=APP_ROOT/'workspace/cases/.tests'
    parent.mkdir(parents=True,exist_ok=True)
    # A second pytest must not let pytest's basetemp cleanup remove active cases.
    lock=parent/'.pytest-session-lock'
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:
        raise pytest.UsageError('APP pytest session already active; do not share its temporary workspace') from exc
    with os.fdopen(fd,'w') as stream:stream.write(str(os.getpid()))
    config._viv_test_lock=lock
    if not config.option.basetemp:
        config.option.basetemp=str(parent/'pytest')


def pytest_unconfigure(config):
    lock=getattr(config,"_viv_test_lock",None)
    if lock is not None and lock.exists():lock.unlink()
