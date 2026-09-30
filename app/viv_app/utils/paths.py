from pathlib import Path
import re

APP_ROOT = Path(__file__).resolve().parents[3]
CASES_ROOT = APP_ROOT / "workspace" / "cases"


def local_path(value: str | Path) -> Path:
    """Accept a Windows drive path when running the APP in WSL."""
    value = str(value)
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", value)
    if match and Path('/mnt').exists():
        value = f"/mnt/{match[1].lower()}/{match[2].replace(chr(92), '/')}"
    return Path(value).expanduser().resolve()


def within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents
