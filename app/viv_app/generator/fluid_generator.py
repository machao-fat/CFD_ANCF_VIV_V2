from pathlib import Path
import fnmatch
import shutil
import yaml
from .foam_dict import FoamDict, set_inlet
from .errors import blocked
from viv_app.utils.paths import APP_ROOT

RULES_PATH=APP_ROOT/'app/resources/baseline_copy_rules.yaml'
RULES=yaml.safe_load(RULES_PATH.read_text(encoding='utf-8'))


def copy_configuration(source,destination):
    """Explicit three-tree copy; never traverse runtime or other times."""
    destination.mkdir()
    def copy_tree(src,dst):
        if src.is_symlink():
            blocked(f'symlink cannot be copied: {src}')
        if any(fnmatch.fnmatchcase(src.name,pattern) for pattern in RULES['runtime_excluded']):
            return
        if src.is_dir():
            dst.mkdir()
            for child in src.iterdir():
                copy_tree(child,dst/child.name)
        elif src.is_file():
            # No copy2/chmod/utime on source; preserve field bytes exactly.
            shutil.copyfile(src,dst)
        else:
            blocked(f'non-regular file in selected configuration: {src}')
    for name in ('system','constant'):
        copy_tree(source/name,destination/name)
    return copy_tree


def write_fluid(root,spec,baseline,row,rank,velocity):
    case=root/row.openfoam_case_id
    copy_tree=copy_configuration(baseline.fluid,case)
    copy_tree(baseline.fluid/spec.initial_state_time,case/spec.initial_state_time)
    control_path=case/'system/controlDict'
    control=FoamDict(control_path.read_bytes())
    control_path.write_bytes(control.edit({
        ('startFrom',):'startTime', ('startTime',):spec.initial_state_time,
        ('deltaT',):f'{spec.delta_t:.17g}', ('endTime',):f'{spec.end_time:.17g}',
        ('writeInterval',):f'{spec.write_interval:.17g}',
    }))
    dpath=case/'system/decomposeParDict'
    dpath.write_bytes(FoamDict(dpath.read_bytes()).edit({('numberOfSubdomains',):rank}))
    ppath=case/'system/preciceDict'
    ppath.write_bytes(FoamDict(ppath.read_bytes()).edit({
        ('participant',):row.fluid_participant, ('preciceConfig',):'"../precice-config.xml"',
        ('interfaces','Interface1','mesh'):row.fluid_mesh,
    }))
    upath=case/spec.initial_state_time/'U'
    vector=tuple(velocity*x for x in baseline.descriptor['flow']['direction'])
    upath.write_bytes(set_inlet(upath.read_bytes(),baseline.descriptor['flow']['inlet_patch'],vector))
    return case
