"""State directory resolution.

Priority: --state-dir (CLI) > $CANARYARCHIVER_STATE_DIR > default.
Default: the package directory (backward compat: registry lived next to
the source), unless a state dir is configured explicitly.
"""
from __future__ import annotations

import os
from pathlib import Path

from canaryarchiver.config.defaults import Config


def resolve_state_dir(cfg: Config) -> Path:
    env = os.getenv("CANARYARCHIVER_STATE_DIR")
    if env:
        return Path(env).expanduser()
    if cfg.state_dir:
        return Path(cfg.state_dir).expanduser()
    return Path(__file__).resolve().parent.parent  # package dir (backward compat)
