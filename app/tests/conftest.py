import importlib.util
from pathlib import Path
import pytest
from viv_app.utils.paths import APP_ROOT

spec=importlib.util.spec_from_file_location('fixture_builder',APP_ROOT/'app/examples/create_synthetic_baseline.py')
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
    if not config.option.basetemp:
        config.option.basetemp=str(parent/'pytest')
