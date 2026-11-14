"""Path containment helpers (H-7).

``safe_join`` resolves the candidate path (including symlinks) and rejects
anything that escapes ``base``.  This covers the four escape classes:
``..`` traversal, absolute paths, symlink escape and nested traversal.

TOCTOU boundary: containment is checked at a point in time.  A concurrent
actor that swaps a parent directory (or creates a symlink) after this call
can still redirect the returned path.  Callers that write must therefore keep
the base directory under their own control; this helper deliberately does not
open files with ``O_NOFOLLOW`` and is not a substitute for such a check.
"""

from __future__ import annotations

from pathlib import Path


def safe_join(base: str | Path, *parts: str | Path) -> Path:
    """Join ``parts`` onto ``base`` and guarantee the result stays inside it.

    Raises:
        ValueError: if the resolved target is outside ``base``.
    """
    base_path = Path(base).resolve()
    target = base_path.joinpath(*(str(part) for part in parts)).resolve()
    try:
        target.relative_to(base_path)
    except ValueError as exc:
        raise ValueError(f"path escapes base directory: {target}") from exc
    return target
