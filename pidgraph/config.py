"""Configuration and secret resolution.

Secrets are referenced, not stored. A configuration file here holds entries like::

    DATABASE_URL=op://Private/pidgraph/DATABASE_URL

which name a location in a password manager rather than carrying the value. The file is then
inert: it can be read, copied or accidentally shared without disclosing anything, and there is no
plaintext credential on disk to forget about. The secret is fetched at the moment it is needed and
kept in memory only.

Resolution order is deliberate:

1. **A real environment variable wins.** Containers and continuous integration inject secrets that
   way, and they must not be overridden by a developer's local file.
2. **A ``op://`` reference is resolved** through the password-manager CLI.
3. **A literal value is used as-is**, so the plain-file workflow still works for anyone who
   prefers it.

Resolved values are cached for the life of the process, because each resolution is a subprocess
call and a pipeline touches its configuration repeatedly.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ENV_FILE = Path(".env")

SECRET_REFERENCE = re.compile(r"^op://[^/]+/[^/]+/.+$")
"""A reference of the form ``op://<vault>/<item>/<field>``."""

# The CLI is frequently installed without being added to PATH.
_CLI_CANDIDATES = (
    r"C:\Program Files\1Password CLI\op.exe",
    r"C:\Program Files (x86)\1Password CLI\op.exe",
    "/usr/local/bin/op",
    "/opt/homebrew/bin/op",
    "/usr/bin/op",
)


class SecretUnavailable(RuntimeError):
    """A referenced secret could not be resolved.

    Raised rather than falling back to an empty value: a missing credential that surfaces as an
    empty string produces an authentication failure far from its cause, and the message that
    reaches the user says nothing about the password manager.
    """


def find_cli() -> str | None:
    """Locate the password-manager CLI, on PATH or in a standard install location."""
    found = shutil.which("op")
    if found:
        return found
    return next((c for c in _CLI_CANDIDATES if Path(c).exists()), None)


def parse_env_file(path: str | Path = ENV_FILE) -> dict[str, str]:
    """Read a ``KEY=value`` file. Values are not interpreted here, only collected."""
    file = Path(path)
    if not file.exists():
        return {}
    out: dict[str, str] = {}
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Strip one layer of surrounding quotes, which shells and editors add freely.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


@dataclass
class Config:
    """Resolved configuration. Values are fetched lazily and cached in memory."""

    entries: dict[str, str] = field(default_factory=dict)
    _cache: dict[str, str] = field(default_factory=dict, repr=False)
    cli: str | None = field(default_factory=find_cli)

    @classmethod
    def load(cls, path: str | Path = ENV_FILE) -> Config:
        return cls(entries=parse_env_file(path))

    def _resolve_reference(self, reference: str, key: str) -> str:
        if self.cli is None:
            raise SecretUnavailable(
                f"{key} is a secret reference ({reference.split('/')[2]}) but the 1Password CLI "
                "was not found. Install it, or replace the reference with a literal value."
            )
        try:
            # An argument list, never a shell string. The reference names a vault and item, and
            # must not be exposed to shell interpretation.
            result = subprocess.run(
                [self.cli, "read", reference],
                capture_output=True, text=True, timeout=60, check=False,
            )
        except Exception as exc:
            raise SecretUnavailable(f"failed to invoke the 1Password CLI for {key}: {exc}") from exc

        if result.returncode != 0:
            # The CLI's own message is the useful one -- it distinguishes "not signed in" from
            # "no such item" -- so it is passed through rather than replaced.
            detail = (result.stderr or "").strip() or f"exit code {result.returncode}"
            raise SecretUnavailable(f"could not read {key} from 1Password: {detail}")

        value = result.stdout.strip()
        if not value:
            raise SecretUnavailable(f"1Password returned an empty value for {key}")
        return value

    def get(self, key: str, default: str | None = None) -> str | None:
        """Resolve one key. A real environment variable always wins."""
        live = os.environ.get(key)
        if live:
            return live
        if key in self._cache:
            return self._cache[key]

        raw = self.entries.get(key)
        if raw is None or not raw:
            return default

        value = self._resolve_reference(raw, key) if SECRET_REFERENCE.match(raw) else raw
        self._cache[key] = value
        return value

    def require(self, key: str) -> str:
        value = self.get(key)
        if not value:
            raise SecretUnavailable(
                f"{key} is not configured. Set it in the environment, or add it to {ENV_FILE} "
                "as a literal value or an op:// reference."
            )
        return value

    def apply_to_environ(self, keys: list[str]) -> list[str]:
        """Resolve the given keys into the process environment.

        Used once at start-up so that libraries reading configuration directly from the
        environment see resolved values. Returns the keys that were successfully resolved, so a
        caller can report what is missing without the values themselves ever being logged.
        """
        applied: list[str] = []
        for key in keys:
            try:
                value = self.get(key)
            except SecretUnavailable:
                continue
            if value:
                os.environ[key] = value
                applied.append(key)
        return applied

    def describe(self) -> list[tuple[str, str]]:
        """Report configuration status without disclosing any value."""
        rows: list[tuple[str, str]] = []
        for key in sorted(set(self.entries) | {"DATABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"}):
            raw = self.entries.get(key, "")
            if os.environ.get(key):
                rows.append((key, "set in the environment"))
            elif not raw:
                rows.append((key, "not configured"))
            elif SECRET_REFERENCE.match(raw):
                vault = raw.split("/")[2]
                try:
                    self.get(key)
                    rows.append((key, f"resolved from 1Password ({vault})"))
                except SecretUnavailable as exc:
                    rows.append((key, f"reference present but unresolved - {exc}"))
            else:
                rows.append((key, "literal value in the configuration file"))
        return rows


SECRET_KEYS = ["DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "OPENAI_API_KEY"]
PUBLIC_KEYS = ["NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"]


def bootstrap(path: str | Path = ENV_FILE) -> Config:
    """Load configuration and resolve it into the environment. Safe to call more than once."""
    config = Config.load(path)
    config.apply_to_environ(SECRET_KEYS + PUBLIC_KEYS)
    return config
