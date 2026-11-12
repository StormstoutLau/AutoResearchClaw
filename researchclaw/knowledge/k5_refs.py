"""G3 M5: K5 reference grammar, resolution and checks.

K5 references use ``tb:<key>`` (knowledge-base node) and ``paper:<key>``
(literature/BibTeX key). The check is read-only; unresolved refs are returned
with file/line provenance so Stage 22/23 can block with a precise report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

E_K5_UNRESOLVED_REF = "E_K5_UNRESOLVED_REF"

K5_REF_RE = re.compile(
    r"\b(tb|paper):([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9_-])?)"
)


@dataclass(frozen=True)
class K5Ref:
    kind: str
    key: str
    line: int
    raw: str

    def as_ref(self) -> str:
        return f"{self.kind}:{self.key}"


def parse_refs(text: str) -> list[K5Ref]:
    """Parse K5 refs with 1-based line numbers (duplicates kept)."""
    refs: list[K5Ref] = []
    for line_no, line in enumerate((text or "").splitlines(), 1):
        for match in K5_REF_RE.finditer(line):
            refs.append(
                K5Ref(
                    kind=match.group(1),
                    key=match.group(2),
                    line=line_no,
                    raw=match.group(0),
                )
            )
    return refs


def _kb_has(kb_root: Path, key: str) -> bool:
    if not kb_root.is_dir():
        return False
    return any(
        path.is_file() and path.stem == key
        for path in kb_root.rglob(f"{key}.md")
    )


def resolve_refs(
    refs: Iterable[K5Ref],
    *,
    kb_root: Path | None = None,
    bib_keys: Iterable[str] = (),
) -> list[K5Ref]:
    """Return refs that cannot be resolved against the KB and BibTeX keys."""
    keys = {str(item) for item in bib_keys}
    root = Path(kb_root) if kb_root is not None else None
    unresolved: list[K5Ref] = []
    for ref in refs:
        if ref.kind == "paper":
            if ref.key not in keys:
                unresolved.append(ref)
        elif ref.kind == "tb":
            if root is None or not _kb_has(root, ref.key):
                unresolved.append(ref)
        else:
            unresolved.append(ref)
    return unresolved


def check_k5_refs(
    text: str,
    *,
    kb_root: Path | None = None,
    bib_keys: Iterable[str] = (),
    file: str = "",
) -> list[dict]:
    """Return ``[{file, line, ref}]`` for unresolved K5 refs (empty = ok)."""
    unresolved = resolve_refs(
        parse_refs(text), kb_root=kb_root, bib_keys=bib_keys
    )
    return [
        {"file": file, "line": ref.line, "ref": ref.raw}
        for ref in unresolved
    ]


def bib_keys_from_text(bib_text: str) -> set[str]:
    """Extract BibTeX keys without importing the literature layer at module load."""
    from researchclaw.literature.verify import parse_bibtex_entries

    return {
        str(entry.get("key", "")).strip()
        for entry in parse_bibtex_entries(bib_text or "")
        if str(entry.get("key", "")).strip()
    }
