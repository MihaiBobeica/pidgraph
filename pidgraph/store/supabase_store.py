"""Supabase persistence.

Writes go over a direct Postgres connection rather than the REST client, for one reason: the REST
layer has no transactions. Without one, a failure part-way through leaves a half-written graph that
reads as complete, and every downstream consumer inherits it with nothing to notice. One
transaction, and the run either exists whole or not at all.

Connection uses the pooler host in every environment. The direct endpoint resolves over IPv6 only,
so a direct connection string works on a developer machine and fails from an IPv4-only host with a
network error that says nothing about the cause.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from pidgraph.store.base import RunRecord


@dataclass
class SupabaseStore:
    """Writes a run into Postgres in a single transaction."""

    dsn: str | None = None
    name: str = "supabase"

    def __post_init__(self) -> None:
        self.dsn = self.dsn or os.environ.get("DATABASE_URL")

    def available(self) -> bool:
        if not self.dsn:
            return False
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            return False
        return True

    def _connect(self):
        import psycopg2

        if not self.dsn:
            raise RuntimeError(
                "DATABASE_URL is not set. Use the pooler connection string: the direct endpoint "
                "is IPv6-only and will fail from an IPv4-only host."
            )
        return psycopg2.connect(self.dsn)

    def write_run(self, record: RunRecord) -> str:
        """Persist one run. Either all of it lands or none of it does."""
        from psycopg2.extras import execute_values

        connection = self._connect()
        try:
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into documents (kind, filename, storage_key, sha256, page_count, title)
                    values (%s, %s, %s, %s, %s, %s)
                    on conflict (sha256) do update set filename = excluded.filename
                    returning id
                    """,
                    (
                        record.document_kind,
                        record.filename,
                        record.storage_key,
                        record.document_sha256,
                        record.page_count,
                        record.title,
                    ),
                )
                document_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    insert into extraction_runs
                        (document_id, extractor_version, isa_edition, strategies, scale, stats,
                         status, finished_at)
                    values (%s, %s, %s, %s, %s, %s, 'succeeded', now())
                    returning id
                    """,
                    (
                        document_id,
                        record.extractor_version,
                        record.isa_edition,
                        json.dumps(record.strategies),
                        json.dumps(record.scale),
                        json.dumps(record.stats),
                    ),
                )
                run_id = cursor.fetchone()[0]

                # Classes seen on nodes are upserted into the vocabulary first, so the foreign
                # key can never fail on a class the extractor legitimately produced. New classes
                # land in the 'Other' package for a human to reclassify.
                classes = sorted({n.get("dexpi_class") or "unknown" for n in record.nodes})
                if classes:
                    execute_values(
                        cursor,
                        """
                        insert into dexpi_class (name, package) values %s
                        on conflict (name) do nothing
                        """,
                        [(c, "Other") for c in classes],
                    )

                if record.nodes:
                    execute_values(
                        cursor,
                        """
                        insert into nodes
                            (run_id, page_index, stable_key, kind, dexpi_class, tag_name,
                             label, bbox, confidence, provenance)
                        values %s
                        """,
                        [
                            (
                                run_id,
                                n["page_index"],
                                n["stable_key"],
                                n["kind"],
                                n.get("dexpi_class") or "unknown",
                                (n.get("attributes") or {}).get("tag_canonical"),
                                n.get("label"),
                                n.get("bbox"),
                                n.get("confidence", 1.0),
                                json.dumps(n.get("provenance", {})),
                            )
                            for n in record.nodes
                        ],
                    )

                # Edges reference nodes by their content-addressed key, so the mapping to surrogate
                # ids is resolved here rather than being carried through the pipeline.
                cursor.execute("select stable_key, id from nodes where run_id = %s", (run_id,))
                ids = dict(cursor.fetchall())

                rows = [
                    (
                        run_id,
                        ids[e["source"]],
                        ids[e["target"]],
                        e.get("kind", "process"),
                        e.get("style"),
                        e["evidence"],
                        e.get("confidence", 1.0),
                    )
                    for e in record.edges
                    if e["source"] in ids and e["target"] in ids
                ]
                if rows:
                    execute_values(
                        cursor,
                        """
                        insert into edges
                            (run_id, source_id, target_id, kind, style, evidence, confidence)
                        values %s
                        """,
                        rows,
                    )

                if record.findings:
                    execute_values(
                        cursor,
                        """
                        insert into findings
                            (run_id, check_name, status, severity, title, detail, subject,
                             pid_evidence, sop_evidence, confidence, graph_incomplete)
                        values %s
                        """,
                        [
                            (
                                run_id,
                                f["check"],
                                f["status"],
                                f["severity"],
                                f["title"],
                                f.get("detail"),
                                f.get("subject"),
                                f.get("pid_evidence"),
                                f.get("sop_evidence"),
                                f.get("confidence", 1.0),
                                f.get("graph_incomplete", False),
                            )
                            for f in record.findings
                        ],
                    )

                # The procedure document and its requirements, so the database holds both sides
                # of the cross-reference rather than only the drawing's.
                if record.sop_sha256:
                    cursor.execute(
                        """
                        insert into documents (kind, filename, storage_key, sha256, title)
                        values ('sop', %s, %s, %s, %s)
                        on conflict (sha256) do update set filename = excluded.filename
                        returning id
                        """,
                        (
                            record.sop_filename,
                            record.sop_storage_key,
                            record.sop_sha256,
                            record.title,
                        ),
                    )
                    sop_id = cursor.fetchone()[0]
                    if record.requirements:
                        execute_values(
                            cursor,
                            """
                            insert into sop_requirements
                                (document_id, ordinal, subject_raw, subject_tags, subject_part,
                                 quantities, evidence)
                            values %s
                            on conflict (document_id, ordinal) do update
                                set subject_raw = excluded.subject_raw,
                                    subject_tags = excluded.subject_tags,
                                    quantities = excluded.quantities
                            """,
                            [
                                (
                                    sop_id,
                                    r["ordinal"],
                                    r["subject_raw"],
                                    list(r.get("subject_tags") or []),
                                    r.get("subject_part"),
                                    json.dumps(r.get("quantities") or {}),
                                    r.get("evidence"),
                                )
                                for r in record.requirements
                            ],
                        )

                # Pointed at last, so a reader filtering on the current run never sees a partial
                # graph even while this transaction is in flight.
                cursor.execute(
                    "update documents set current_run_id = %s where id = %s", (run_id, document_id)
                )
            return str(run_id)
        finally:
            connection.close()


def choose_store():
    """The database store when it is configured, otherwise the local one.

    Falling back rather than failing is deliberate: the pipeline's job is to produce a graph, and
    a reader without credentials should still get one.
    """
    from pidgraph.store.base import LocalJsonStore

    store = SupabaseStore()
    return store if store.available() else LocalJsonStore()
