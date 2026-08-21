"""Universal file scanner: targets resolution + text-file iteration."""
from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

from canaryarchiver.config.defaults import Config


def resolve_targets(root: Path, cfg: Config) -> list[Path]:
    """Resolve fingerprint targets inside root.

    Order:
      1. cfg.targets (explicit list / globs) — CLI --targets / config
      2. cfg.default_targets — first existing literal (unless require_all_defaults)
      3. all text files under root (universal fallback)
    """
    root = root.resolve()
    if not root.is_dir():
        sys.exit(f"[✗] корень не найден: {root}")

    patterns = list(cfg.targets) or list(cfg.default_targets)

    found: list[Path] = []
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        # glob pattern?
        if any(ch in pat for ch in "*?["):
            found += sorted(root.glob(pat))
        else:
            p = root / pat
            if p.is_file():
                found.append(p)
    if found:
        return dedup(found)

    # nothing matched: fall back to all text files (universal mode)
    return sorted(p for p in iter_text_files(root, cfg) if p.is_file())


def dedup(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def iter_text_files(root: Path, cfg: Config):
    """Yield text-like files under root, honoring exclude rules."""
    exclude_dirs = {d.rstrip("/").lstrip("/") for d in cfg.exclude_dirs}
    exclude_names = set(cfg.exclude_names)
    suffixes = tuple(cfg.text_suffixes)
    parts_re = [re.compile(re.escape(s)) for s in cfg.exclude_parts]

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in exclude_dirs for part in rel.parts):
            continue
        if p.name in exclude_names:
            continue
        if any(rx.search(str(rel)) for rx in parts_re):
            continue
        if p.suffix.lower() not in suffixes:
            continue
        yield p


def is_text_like(p: Path, cfg: Config) -> bool:
    return p.suffix.lower() in cfg.text_suffixes or p.suffix.lower() == ".md"


def matches_target(p: Path, root: Path, cfg: Config) -> bool:
    """Is file a fingerprint target? (used by rebuild strip logic)"""
    targets = resolve_targets(root, cfg)
    return any(str(t.resolve()) == str(p.resolve()) for t in targets)


def glob_match(name: str, pattern: str) -> bool:
    return fnmatch.fnmatch(name, pattern)
