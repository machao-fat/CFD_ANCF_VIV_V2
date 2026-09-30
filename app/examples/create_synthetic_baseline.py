"""Compatibility entry for the tiny offline fixture builder."""
from pathlib import Path
import runpy
from viv_app.utils.paths import APP_ROOT
_fixture=runpy.run_path(str(APP_ROOT/"app/tests/fixtures/create_synthetic_baseline.py"))
make_baseline=_fixture["make_baseline"]
if __name__=="__main__":
    runpy.run_path(str(APP_ROOT/"app/tests/fixtures/create_synthetic_baseline.py"),run_name="__main__")
