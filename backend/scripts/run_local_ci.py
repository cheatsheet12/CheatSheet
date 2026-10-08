"""Launcher: `python backend/scripts/run_local_ci.py [--only STEP ...]`.

Python puts this file's directory on sys.path, which is what makes `local_ci` importable.
See docs/adr/0015-local-ci-verification.md and backend/scripts/local_ci/README.md.
"""

from __future__ import annotations

import sys

from local_ci.cli import main

if __name__ == "__main__":
    sys.exit(main())
