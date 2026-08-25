"""Test-wide determinism guards.

Output ordering must not depend on hash seeding. Setting this in ``conftest`` rather than in
``pyproject.toml`` avoids a dependency on the pytest-env plugin, and re-execs once if the
interpreter started without the seed pinned.
"""

from __future__ import annotations

import os
import sys


def pytest_configure(config):
    if os.environ.get("PYTHONHASHSEED") not in ("0",):
        os.environ["PYTHONHASHSEED"] = "0"
        if not os.environ.get("_PIDGRAPH_REEXEC"):
            os.environ["_PIDGRAPH_REEXEC"] = "1"
            os.execv(sys.executable, [sys.executable, "-m", "pytest", *sys.argv[1:]])
