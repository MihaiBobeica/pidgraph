"""Input path resolution.

Drawings live under ``data/pid/`` (or ``data/PID/``). Procedures live under ``data/sop/``
(or ``data/SOP/``). Callers get :class:`Path` objects; storage keys are derived from a content
hash (see :func:`storage_key`), never from the on-disk name.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

# Probed in order. The first directory that exists and contains a readable file wins.
PID_DIR_CANDIDATES: tuple[str, ...] = ("pid", "PID")
SOP_DIR_CANDIDATES: tuple[str, ...] = ("sop", "SOP")

PID_SUFFIXES: tuple[str, ...] = (".pdf",)
SOP_SUFFIXES: tuple[str, ...] = (".docx", ".doc", ".pdf", ".txt", ".md")


class InputNotFound(FileNotFoundError):
    """Raised when no candidate directory yields a usable input.

    Carries the directories actually probed so the failure names what was looked for rather
    than leaving the caller to guess.
    """

    def __init__(self, what: str, probed: Iterable[Path]) -> None:
        probed = list(probed)
        listing = "\n  ".join(str(p) for p in probed) or "(none)"
        super().__init__(f"no {what} input found. Probed:\n  {listing}")
        self.probed = probed


def data_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Root of the input tree: an explicit argument, then ``PIDGRAPH_INPUT_DIR``, then ``data``."""
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("PIDGRAPH_INPUT_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "data").resolve()


def _first_file(
    root: Path, dir_names: Iterable[str], suffixes: Iterable[str]
) -> tuple[Path | None, list[Path]]:
    """Return the first matching file across candidate directories, plus everything probed."""
    suffixes = tuple(s.lower() for s in suffixes)
    probed: list[Path] = []
    for name in dir_names:
        directory = root / name
        probed.append(directory)
        if not directory.is_dir():
            continue
        # Sorted for determinism: directory iteration order is not guaranteed.
        for candidate in sorted(directory.iterdir()):
            if candidate.is_file() and candidate.suffix.lower() in suffixes:
                return candidate, probed
    return None, probed


def find_pid(root: str | os.PathLike[str] | None = None) -> Path:
    """Locate the P&ID drawing. Raises :class:`InputNotFound` naming every directory probed."""
    base = data_root(root)
    found, probed = _first_file(base, PID_DIR_CANDIDATES, PID_SUFFIXES)
    if found is None:
        raise InputNotFound("P&ID drawing", probed)
    return found


def find_sop(root: str | os.PathLike[str] | None = None) -> Path:
    """Locate the SOP document. Raises :class:`InputNotFound` naming every directory probed."""
    base = data_root(root)
    found, probed = _first_file(base, SOP_DIR_CANDIDATES, SOP_SUFFIXES)
    if found is None:
        raise InputNotFound("SOP document", probed)
    return found


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    """Content hash of a file. Identity for storage and for cache keys."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def storage_key(path: Path, prefix: str = "raw") -> str:
    """Object-storage key for a file.

    Derived from the content hash and the suffix -- never from the on-disk name, so Windows
    backslashes and spaces stay out of storage keys and signed URLs. Built with
    :class:`PurePosixPath` so the separator is ``/`` regardless of host platform.
    """
    return str(PurePosixPath(prefix) / f"{sha256(path)}{path.suffix.lower()}")
