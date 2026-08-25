"""Schema application.

Applying a schema to someone's live project is a real change to their infrastructure, so this
reports what it is about to do, applies the migration in a single transaction, and verifies the
result rather than assuming it. A half-applied schema is worse than none: the failure surfaces
later as a missing table during a write, far from the cause.

Migrations are idempotent by construction -- tables use ``if not exists`` and policies are dropped
before being recreated -- so re-running is safe and is the normal way to pick up a change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MIGRATIONS = Path("supabase/migrations")

EXPECTED_TABLES = (
    "dexpi_class", "isa_edition", "documents", "extraction_runs", "nodes", "edges",
    "node_attributes", "sop_requirements", "findings", "review_actions",
)
EXPECTED_FUNCTIONS = ("trace_downstream", "graph_snapshot")


@dataclass
class MigrationReport:
    applied: list[str] = field(default_factory=list)
    existing_tables: list[str] = field(default_factory=list)
    created_tables: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.missing


def _split_statements(sql: str) -> list[str]:
    """Split a script on statement boundaries, respecting dollar-quoted bodies.

    Function bodies contain semicolons, so a naive split truncates them mid-definition and the
    resulting error points at the wrong place entirely.
    """
    statements: list[str] = []
    buffer: list[str] = []
    tag: str | None = None
    for line in sql.splitlines():
        if tag is None:
            match = re.search(r"\$([A-Za-z_]*)\$", line)
            if match and line.count(f"${match.group(1)}$") % 2 == 1:
                tag = match.group(1)
        elif f"${tag}$" in line:
            tag = None
        buffer.append(line)
        if tag is None and line.rstrip().endswith(";"):
            statement = "\n".join(buffer).strip()
            # Keep the statement unless it is comments all the way down. Testing only the first
            # line is a trap: a statement preceded by its explanatory comment starts with "--",
            # and dropping on that basis silently discards most of a well-commented migration
            # while the runner reports success.
            if any(
                stripped_line.strip() and not stripped_line.strip().startswith("--")
                for stripped_line in statement.splitlines()
            ):
                statements.append(statement)
            buffer = []
    tail = "\n".join(buffer).strip()
    if tail and any(
        line.strip() and not line.strip().startswith("--") for line in tail.splitlines()
    ):
        statements.append(tail)
    return statements


def inspect(dsn: str) -> tuple[list[str], list[str]]:
    """Report which expected tables and functions already exist."""
    import psycopg2

    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' and table_name = any(%s)",
            (list(EXPECTED_TABLES),),
        )
        tables = sorted(row[0] for row in cursor.fetchall())
        cursor.execute(
            "select routine_name from information_schema.routines "
            "where routine_schema = 'public' and routine_name = any(%s)",
            (list(EXPECTED_FUNCTIONS),),
        )
        functions = sorted(row[0] for row in cursor.fetchall())
    return tables, functions


def apply(dsn: str, directory: str | Path = MIGRATIONS, dry_run: bool = False) -> MigrationReport:
    """Apply every migration in order, in one transaction.

    ``dry_run`` inspects and reports without changing anything, which is the right default when
    pointing at a database you do not own.
    """
    import psycopg2

    report = MigrationReport()
    files = sorted(Path(directory).glob("*.sql"))
    if not files:
        report.error = f"no migrations found in {directory}"
        return report

    try:
        before, _ = inspect(dsn)
    except Exception as exc:
        report.error = f"could not connect: {exc}"
        return report
    report.existing_tables = before

    if dry_run:
        report.applied = [f.name for f in files]
        report.missing = [t for t in EXPECTED_TABLES if t not in before]
        return report

    try:
        with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
            for file in files:
                sql = file.read_text(encoding="utf-8")
                for statement in _split_statements(sql):
                    # A savepoint per statement, not a transaction rollback on failure. Policies
                    # have no "if not exists" form, so re-running hits duplicates -- and a full
                    # rollback there silently discards every statement already executed (the
                    # seed inserts, in practice) while the runner goes on to report success.
                    cursor.execute("savepoint migration_step")
                    try:
                        cursor.execute(statement)
                        cursor.execute("release savepoint migration_step")
                    except psycopg2.errors.DuplicateObject:
                        cursor.execute("rollback to savepoint migration_step")
                    except Exception as exc:
                        raise RuntimeError(
                            f"{file.name}: {exc}\nstatement began: {statement[:120]}"
                        ) from exc
                report.applied.append(file.name)
    except Exception as exc:
        report.error = str(exc)
        return report

    after, functions = inspect(dsn)
    report.created_tables = [t for t in after if t not in before]
    report.functions = functions
    # Verify rather than assume: a migration that reported success but left a table missing would
    # otherwise fail much later, during a write.
    report.missing = [t for t in EXPECTED_TABLES if t not in after]
    return report
