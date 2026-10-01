"""Only the enrolled v2606 decomposePar initial/uniform link is permitted.

No generic symlink following. Metadata is an exact, bounded topology observed
in the failed GUI Prepare and the earlier successful N5 smoke.
"""
from pathlib import Path
import hashlib
import json
import os
import stat

from viv_app.generator.production_baseline import PROFILE, PROFILE_ROOT, LABELS


METADATA_FILES = ('cumulativeContErr', 'time', 'functionObjects/functionObjectProperties')
MAX_METADATA_BYTES = 2 * 1024 * 1024


def require(condition, detail):
    if not condition:
        raise ValueError('Prepared input contract: ' + detail)


def plain_path(root, path):
    """Reject links in every component, including broken links and parents."""
    root, path = Path(root), Path(path)
    require(not root.is_symlink(), 'case root is a symlink')
    require(root.is_dir(), 'case root is missing')
    relative = path.relative_to(root)
    require('..' not in relative.parts, 'input path escapes case')
    current = root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise ValueError('Prepared input contract: missing input: ' + str(current)) from exc
        require(not stat.S_ISLNK(mode), 'unexpected symlink: ' + str(current))
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), 'unsupported input type: ' + str(current))
    return path


def input_tree(root, folder):
    """Walk only the selected input subtree, yielding links without following."""
    plain_path(root, folder)
    for entry in sorted(folder.iterdir()):
        yield entry
        if stat.S_ISDIR(entry.lstat().st_mode):
            yield from input_tree(root, entry)


def metadata_children(folder, names):
    """At most expected-count + 1 entries: refuse unknown data immediately."""
    remaining = set(names)
    with os.scandir(folder) as entries:
        for entry in entries:
            require(entry.name in remaining, 'unsupported serial uniform metadata entry: ' + entry.name)
            remaining.remove(entry.name)
    require(not remaining, 'missing serial uniform metadata: ' + ', '.join(sorted(remaining)))


def qualified_uniform_symlink_identity(root, fluid_rows, baseline, link):
    """Authenticate location, enrollment, raw form, exact target and metadata."""
    root, link = Path(root), Path(link)
    enrolled = json.loads((PROFILE_ROOT / 'app_baseline.json').read_text())
    initial = enrolled['initial_time_default']
    require(baseline.get('contract_profile') == PROFILE and baseline.get('initial_time_default') == initial,
            'uniform link requires enrolled production initial time')
    expected = [(f'Fluid-S{i}', f'fluid_{label}') for i, label in enumerate(LABELS, 1)]
    require([(row['participant'], row['cwd']) for row in fluid_rows] == expected,
            'uniform link requires five enrolled Fluid cases')
    parts = link.relative_to(root).parts
    require(len(parts) == 4 and parts[0] in dict(expected).values()
            and parts[1] in {f'processor{r}' for r in range(4)}
            and parts[2:] == (initial, 'uniform'), 'unexpected symlink location: ' + str(link))
    plain_path(root, link.parent)
    require(link.is_symlink(), 'expected uniform symlink')
    raw = os.readlink(link)
    require(not Path(raw).is_absolute(), 'absolute uniform symlink')
    fluid = root / parts[0]
    target = fluid / initial / 'uniform'
    plain_path(root, target)
    require(target.is_dir(), 'serial uniform target must be an ordinary directory')
    try:
        resolved = link.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError('Prepared input contract: broken or cyclic uniform symlink') from exc
    require(resolved == target.resolve(strict=True) and resolved.is_relative_to(fluid.resolve(strict=True)),
            'uniform link must resolve exactly to the same Fluid serial uniform')
    require(raw == f'../../{initial}/uniform', 'unexpected uniform link text')
    # Fixed observed tree: no unbounded rglob, unrelated times or runtime data.
    metadata_children(target, ('cumulativeContErr', 'time', 'functionObjects'))
    nested = plain_path(root, target / 'functionObjects')
    require(nested.is_dir(), 'functionObjects metadata must be an ordinary directory')
    metadata_children(nested, ('functionObjectProperties',))
    identity = {}
    for relative in METADATA_FILES:
        path = plain_path(root, target / relative)
        require(path.is_file() and path.stat().st_size <= MAX_METADATA_BYTES,
                'unsupported/oversized uniform metadata file: ' + relative)
        # A bounded read also refuses a file that grows after the size check.
        with path.open('rb') as stream:
            content = stream.read(MAX_METADATA_BYTES + 1)
        require(len(content) <= MAX_METADATA_BYTES, 'uniform metadata exceeded size bound')
        identity[relative] = {'size_bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
    return {'kind': 'qualified_case_local_symlink', 'link_path': str(link.relative_to(root)),
            'link_target': raw, 'resolved_target': str(resolved.relative_to(fluid.resolve(strict=True))),
            'target_type': 'directory', 'target_identity': {'scope': 'exact-three-metadata-files-full-sha256',
                                                         'files': identity}}


def processor_inputs(root, fluid, initial):
    """Fresh Prepare topology only; never scan historical output time trees."""
    plain_path(root, fluid)
    for r in range(4):
        processor = plain_path(root, fluid / f'processor{r}')
        require(processor.is_dir(), 'processor must be an ordinary directory')
        for entry in sorted(processor.iterdir()):
            require(entry.name in ('constant', initial), 'unexpected prepared processor entry: ' + str(entry))
            plain_path(root, entry)
            require(entry.is_dir(), 'processor input root must be a directory')
        for name in ('constant', initial):
            yield from input_tree(root, processor / name)
