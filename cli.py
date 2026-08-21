#!/usr/bin/env python3
"""Entry point: `python3 cli.py ...` or `canaryarchiver ...` (after install)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canaryarchiver.cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
