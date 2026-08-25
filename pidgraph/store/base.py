"""Storage protocol and a local implementation.

Two implementations behind one interface, so tests and continuous integration need no network and
no credentials, while the same code path writes to the real database.

Writes go through a single transaction. A partially written graph that reads as complete is worse
than a failed run: everything downstream inherits it silently, and the run status flag alone cannot
protect a reader who queries the tables directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class RunRecord:
    """Everything about one extraction, ready to persist."""

    document_sha256: str
    document_kind: str
    filename: str
    storage_key: str
    extractor_version: str
    isa_edition: str
    page_count: int
    title: str = ""
    strategies: dict[str, Any] = field(default_factory=dict)
    scale: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    requirements: list[dict] = field(default_factory=list)
    sop_sha256: str = ""
    sop_filename: str = ""
    sop_storage_key: str = ""


class GraphStore(Protocol):
    """Where a run is persisted."""

    name: str

    def available(self) -> bool: ...
    def write_run(self, record: RunRecord) -> str: ...


@dataclass
class LocalJsonStore:
    """Filesystem store. The default, and what tests and CI use.

    Deliberately the same shape as the database store so a run is exercised identically whether or
    not credentials exist -- a storage path only tested against a live service is one discovered
    broken in production.
    """

    directory: Path = Path("outputs/store")
    name: str = "local-json"

    def available(self) -> bool:
        return True

    def write_run(self, record: RunRecord) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        run_id = record.document_sha256[:16]
        payload = {
            "document": {
                "sha256": record.document_sha256,
                "kind": record.document_kind,
                "filename": record.filename,
                "storage_key": record.storage_key,
                "page_count": record.page_count,
                "title": record.title,
            },
            "run": {
                "id": run_id,
                "extractor_version": record.extractor_version,
                "isa_edition": record.isa_edition,
                "strategies": record.strategies,
                "scale": record.scale,
                "stats": record.stats,
                "status": "succeeded",
            },
            "nodes": record.nodes,
            "edges": record.edges,
            "findings": record.findings,
            "requirements": record.requirements,
        }
        path = self.directory / f"run_{run_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return run_id
