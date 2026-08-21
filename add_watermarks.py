#!/usr/bin/env python3
"""Legacy CLI wrapper: `python3 add_watermarks.py --check` ==
`canaryarchiver watermark --check`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canaryarchiver.cli.main import main  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    # route: add_watermarks.py [--check|--stats|--root X] → watermark ...
    sys.exit(main(["watermark"] + args))
