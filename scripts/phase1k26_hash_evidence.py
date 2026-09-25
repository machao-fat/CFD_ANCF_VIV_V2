#!/usr/bin/env python3
"""Create a deterministic SHA256 index for a Phase 1K.26 evidence tree."""

import hashlib
from pathlib import Path
import sys


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: phase1k26_hash_evidence.py EVIDENCE_DIRECTORY")
    root = Path(sys.argv[1]).resolve(strict=True)
    manifest = root / "sha256_manifest.txt"
    if manifest.exists():
        raise SystemExit(f"refusing to overwrite existing manifest: {manifest}")
    files = sorted(path for path in root.rglob("*") if path.is_file() and path != manifest)
    lines = [f"{sha256(path)}  {path.relative_to(root).as_posix()}" for path in files]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"files={len(files)} manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
