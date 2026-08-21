"""Leak scanner: find known canary phrases in any file/zip/dir.

Scans ALL text-like files (configurable suffixes), not just .md —
canaries may live in .py/.json/.yaml/etc.
"""
from __future__ import annotations

import zipfile
from contextlib import suppress
from pathlib import Path

from canaryarchiver.config.defaults import Config
from canaryarchiver.engine.scanner import iter_text_files


def _iter_candidates(p: Path, cfg: Config):
    """Yield (label, text) text candidates from file/zip/dir."""
    pwd = cfg.password.encode("utf-8") if cfg.password else None
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if name.endswith(cfg.text_suffixes):
                    yield name, z.read(name, pwd=pwd)
        return
    if p.is_dir():
        for f in iter_text_files(p, cfg):
            with suppress(Exception):
                yield str(f), f.read_text(encoding="utf-8").encode("utf-8")
        return
    # single file: try as text regardless of suffix
    with suppress(Exception):
        yield str(p), p.read_bytes()


def check_leak(path: str, phrases: list[tuple[str, str, str]],
               cfg: Config) -> None:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"[✗] нет такого пути: {p}")

    hits = []
    for name, data in _iter_candidates(p, cfg):
        with suppress(Exception):
            text = data.decode("utf-8")
        for phrase, user, ident in phrases:
            if not phrase:
                continue
            # exact full-line matches only (no substring false positives)
            n = sum(1 for ln in text.split("\n") if ln.strip() == phrase)
            if n:
                hits.append((phrase, user, ident, name, n))

    if not hits:
        print("[—] известных фраз в копии нет: либо не наша выдача, "
              "либо метки сняты")
        return
    for phrase, user, ident, name, n in hits:
        print(f"[!] НАЙДЕНА фраза «{phrase}» (×{n}) в {name}")
        print(f"    юзер: {user or '—'} · id: {ident or '—'}")
        if user or ident:
            print(f"    → это копия для {user or ident}")
