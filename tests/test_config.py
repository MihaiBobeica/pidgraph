"""Configuration and secret-resolution tests.

The property worth protecting here is that a secret value never reaches a log, a report or a
status line. A credential that leaks into output is a credential that has to be rotated, and the
leak is usually discovered long after the output was shared.
"""

from __future__ import annotations

import pytest

from pidgraph.config import SECRET_REFERENCE, Config, SecretUnavailable, parse_env_file


class TestParsing:
    def test_reads_key_value_pairs_and_ignores_comments(self, tmp_path):
        file = tmp_path / ".env"
        file.write_text(
            "# a comment\n\nKEY=value\nQUOTED=\"quoted value\"\nSINGLE='single'\nBAD LINE\n",
            encoding="utf-8",
        )
        parsed = parse_env_file(file)
        assert parsed == {"KEY": "value", "QUOTED": "quoted value", "SINGLE": "single"}

    def test_a_missing_file_is_not_an_error(self, tmp_path):
        assert parse_env_file(tmp_path / "absent") == {}

    def test_values_containing_equals_are_kept_whole(self, tmp_path):
        """Connection strings and encoded keys routinely contain '='."""
        file = tmp_path / ".env"
        file.write_text("DSN=postgresql://u:p==@host:5432/db\n", encoding="utf-8")
        assert parse_env_file(file)["DSN"] == "postgresql://u:p==@host:5432/db"


class TestReferenceRecognition:
    @pytest.mark.parametrize(
        "value", ["op://Private/pidgraph/DATABASE_URL", "op://Shared/item/field/sub"]
    )
    def test_references_are_recognised(self, value):
        assert SECRET_REFERENCE.match(value)

    @pytest.mark.parametrize(
        "value",
        ["postgresql://user:pass@host/db", "op://incomplete", "sk-literal-key", ""],
    )
    def test_literals_are_not_mistaken_for_references(self, value):
        assert not SECRET_REFERENCE.match(value)


class TestResolution:
    def test_a_real_environment_variable_wins(self, monkeypatch):
        """Containers and CI inject secrets this way; a local file must not override them."""
        monkeypatch.setenv("DATABASE_URL", "from-environment")
        config = Config(entries={"DATABASE_URL": "op://Private/x/y"})
        assert config.get("DATABASE_URL") == "from-environment"

    def test_a_literal_value_is_used_directly(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        config = Config(entries={"DATABASE_URL": "postgresql://literal"})
        assert config.get("DATABASE_URL") == "postgresql://literal"

    def test_an_unresolvable_reference_raises_rather_than_returning_empty(self, monkeypatch):
        """An empty credential fails authentication far from its cause, and the error that
        reaches the user says nothing about the password manager."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        config = Config(entries={"DATABASE_URL": "op://Private/x/y"}, cli=None)
        with pytest.raises(SecretUnavailable, match="1Password CLI"):
            config.get("DATABASE_URL")

    def test_resolution_is_cached(self, monkeypatch):
        monkeypatch.delenv("SECRET", raising=False)
        calls = []

        class Counting(Config):
            def _resolve_reference(self, reference, key):
                calls.append(reference)
                return "resolved"

        config = Counting(entries={"SECRET": "op://Private/x/y"}, cli="/fake/op")
        assert config.get("SECRET") == "resolved"
        assert config.get("SECRET") == "resolved"
        assert len(calls) == 1, "each resolution is a subprocess call and must not repeat"

    def test_require_names_the_missing_key(self, monkeypatch):
        monkeypatch.delenv("ABSENT", raising=False)
        with pytest.raises(SecretUnavailable, match="ABSENT"):
            Config(entries={}).require("ABSENT")


class TestNoLeakage:
    def test_status_reporting_never_includes_a_value(self, monkeypatch):
        """The whole point of the status view is that it can be pasted into a bug report."""
        secret = "postgresql://user:hunter2@host:5432/db"
        monkeypatch.delenv("DATABASE_URL", raising=False)
        config = Config(entries={"DATABASE_URL": secret})
        rendered = " ".join(f"{k} {v}" for k, v in config.describe())
        assert secret not in rendered
        assert "hunter2" not in rendered
        assert "literal value" in rendered

    def test_status_shows_the_vault_but_not_the_secret(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)

        class Resolving(Config):
            def _resolve_reference(self, reference, key):
                return "super-secret-value"

        config = Resolving(entries={"DATABASE_URL": "op://Private/pidgraph/DSN"}, cli="/fake/op")
        rendered = " ".join(f"{k} {v}" for k, v in config.describe())
        assert "super-secret-value" not in rendered
        assert "Private" in rendered

    def test_applying_to_the_environment_reports_names_only(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        config = Config(entries={"OPENAI_API_KEY": "sk-do-not-log-me"})
        applied = config.apply_to_environ(["OPENAI_API_KEY"])
        assert applied == ["OPENAI_API_KEY"]
        assert "sk-do-not-log-me" not in " ".join(applied)
