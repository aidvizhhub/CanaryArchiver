"""Backward-compat module: re-exports the registry API for external scripts.

Old code doing `from archive import LOG, DIST, ARCHIVE, rotate, ...`
keeps working. State paths follow the same resolution as the engine.
"""
import re
from pathlib import Path

from canaryarchiver.config.defaults import load
from canaryarchiver.engine.registry import LOG_HEADER, Registry
from canaryarchiver.state import resolve_state_dir

cfg = load()
_REG = Registry(cfg)
_REG.log = resolve_state_dir(cfg) / cfg.log_file
_REG.dist = resolve_state_dir(cfg) / cfg.dist_dir
_REG.archive = resolve_state_dir(cfg) / cfg.archive_dir
_REG.marker = resolve_state_dir(cfg) / cfg.version_marker

HERE = Path(__file__).resolve().parent
LOG = _REG.log
DIST = _REG.dist
ARCHIVE = _REG.archive
MARKER = _REG.marker

VER_RE = _REG.ver_re

slug = _REG.slug
all_logs = _REG.all_logs
read_entries = _REG.read_entries
infer_version = _REG.infer_version
rotate = _REG.rotate
ensure_rotated = _REG.ensure_rotated
