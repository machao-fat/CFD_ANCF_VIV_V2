"""Offline-only tiny filesystem fixture; never invokes OpenFOAM or MPI."""
from pathlib import Path
import sys


def prepare(fluid, initial):
    for rank in range(4):
        processor = fluid / f'processor{rank}'
        for name in ('U', 'U_0', 'p', 'phi', 'k', 'omega', 'nut', 'pointDisplacement'):
            path = processor / initial / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('SYNTHETIC INITIAL FIELD ' + name)
        for name in ('points', 'faces', 'owner', 'neighbour', 'boundary'):
            path = processor / 'constant/polyMesh' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('SYNTHETIC MESH ' + name)
        (processor / initial / 'uniform').symlink_to(f'../../{initial}/uniform', target_is_directory=True)


if __name__ == '__main__':
    prepare(Path.cwd(), sys.argv[1])
