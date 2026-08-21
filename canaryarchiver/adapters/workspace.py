"""Workspace adapter: connects the universal engine to a concrete project.

Holds: root, fingerprint targets, version resolution, artifact naming.
No hardcoded file requirements: targets are config/CLI-driven.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from canaryarchiver.config.defaults import Config
from canaryarchiver.engine import fingerprint
from canaryarchiver.engine.archiver import ArchiveBackend, make_backend
from canaryarchiver.engine.registry import Registry
from canaryarchiver.engine.scanner import resolve_targets
from canaryarchiver.state import resolve_state_dir


def sha256_short(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()[:12]


class Workspace:
    """Adapter over a concrete workspace tree."""

    def __init__(self, cfg: Config, reg: Registry, backend: ArchiveBackend):
        self.cfg = cfg
        self.reg = reg
        self.backend = backend
        self.root = Path()
        self._targets: list[Path] | None = None

    # ---- resolution ------------------------------------------------------
    def _root_or_none(self) -> Path | None:
        raw = self.cfg.root
        if not raw:
            return None
        p = Path(raw).expanduser().resolve()
        return p if p.is_dir() else None

    def resolve_root(self) -> Path:
        root = self._root_or_none()
        if root is None:
            sys.exit("[✗] корень воркспейса не найден: задай --root или "
                     "WORKSPACE_ROOT / CANARYARCHIVER_ROOT")
        self.root = root
        return root

    def targets(self) -> list[Path]:
        if self._targets is None:
            self._targets = resolve_targets(self.resolve_root(), self.cfg)
            if not self._targets:
                sys.exit("[✗] не найдено ни одного файла-цели для канарейки "
                         "(--targets / default_targets / любой текст)")
        return self._targets

    def version(self, explicit: str = "") -> str:
        """Version source: explicit > config > file:VERSION > git describe."""
        if explicit:
            return explicit.strip()
        root = self._root_or_none()
        if self.cfg.version_source == "git" and root is not None:
            try:
                out = subprocess.run(
                    ["git", "-C", str(root), "describe",
                     "--tags", "--abbrev=0"],
                    capture_output=True, text=True, check=False).stdout.strip()
                if out:
                    return out
            except Exception:  # noqa: BLE001
                pass
            return "git"
        if root is not None:
            vf = root / self.cfg.version_file
            if vf.is_file():
                return vf.read_text(encoding="utf-8").strip()
        return "?"

    def artifact_path(self, version: str) -> Path:
        name = f"{self.cfg.archive_name}-{version}.zip"
        return self.resolve_root().parent / name

    def archive_inner(self, extracted_root: Path) -> Path:
        """Locate workspace dir inside an extracted archive."""
        cand = extracted_root / self.cfg.archive_inner_dir
        if cand.is_dir():
            return cand
        dirs = [d for d in extracted_root.iterdir() if d.is_dir()]
        return dirs[0] if dirs else extracted_root

    # ---- fingerprint ------------------------------------------------------
    def embed(self, phrase: str) -> list[tuple[Path, bytes]]:
        """Insert canary into every target. Returns originals for restore."""
        originals = []
        for t in self.targets():
            orig = t.read_bytes()
            originals.append((t, orig))
            t.write_text(fingerprint.insert_canary(
                orig.decode("utf-8"), phrase), encoding="utf-8")
        return originals

    @staticmethod
    def restore(originals: list[tuple[Path, bytes]]) -> None:
        for p, data in originals:
            p.write_bytes(data)
        ok = all(p.read_bytes() == data for p, data in originals)
        print(f"[✓] файлы восстановлены"
              f"{' (сверка sha256)' if ok else ' — СВЕРКА НЕ СОШЛАСЬ!'}")

    # ---- archive -----------------------------------------------------------
    def build_archive(self, staging_root: Path, version: str) -> Path:
        """staging_root contains <archive_inner_dir>/ tree; zip goes next to
        the workspace root (artifact naming from config)."""
        out = self.artifact_path(version)
        self.backend.build(staging_root, self.cfg.archive_inner_dir, out,
                           self.cfg.password)
        return out

    def make_staging(self) -> tuple[Path, Path]:
        """Copy workspace tree into a temp staging dir with inner dir prefix.

        Independent of the workspace layout: the zip always contains
        <archive_inner_dir>/... (same shape as the original tool).
        """
        import tempfile
        root = self.resolve_root()
        staging = Path(tempfile.mkdtemp(prefix="canary-issue-"))
        inner = staging / self.cfg.archive_inner_dir
        shutil.copytree(root, inner,
                        ignore=shutil.ignore_patterns(*self.cfg.archive_excludes))
        return staging, inner

    # ---- store copy --------------------------------------------------------
    def store_copy(self, archive: Path, version: str, phrase: str,
                   user: str, ident: str) -> Path:
        dist = self.reg.dist
        dist.mkdir(exist_ok=True)
        slug = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_-]+", "-", phrase)[:24].strip("-") \
            or "copy"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        sha = sha256_short(archive)
        full_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        folder = dist / f"{ts}_{slug}_{sha}"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, folder / archive.name)
        size_mb = archive.stat().st_size / 1048576
        info = (f"# Копия воркспейса — сопроводиловка\n\n"
                f"- Фраза (канарейка): {phrase}\n"
                f"- Юзер: {user or '—'}\n"
                f"- ID: {ident or '—'}\n"
                f"- Выдана: {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z\n"
                f"- Версия: {version}\n"
                f"- Архив: {archive.name}\n"
                f"- SHA256: {full_sha}\n"
                f"- Размер: {size_mb:.1f}M\n")
        (folder / "info.md").write_text(info, encoding="utf-8")
        return folder

    # ---- high-level operations ----------------------------------------------
    def issue(self, phrase: str, user: str, ident: str, dry: bool = False,
              force: bool = False, explicit_version: str = "") -> None:
        root = self.resolve_root()
        version = self.version(explicit_version)
        self.reg.ensure_rotated(version, dry=dry)

        phrase = phrase.strip()
        if not phrase:
            sys.exit("[✗] дай --fp \"фраза\" (любая) или --auto")
        if self.reg.phrase_used(phrase) and not force:
            sys.exit(f"[✗] фраза «{phrase}» уже выдавалась (см. log.md) — "
                     "возьми другую или --force")

        targets = self.targets()
        originals = []
        staging: Path | None = None
        try:
            if dry:
                print(f"[dry-run] канарейка «{phrase}» → {len(targets)} целей:")
                for t in targets:
                    print(f"          {t.relative_to(root)}")
                print(f"          потом: сборка {self.artifact_path(version)}")
                print(f"          выдача: dist/ + строка в log.md")
                return

            originals = self.embed(phrase)
            staging, _inner = self.make_staging()
            out = self.build_archive(staging, version)

            # verify canary inside archive for EVERY target
            z = self.backend
            if z.name == "system" or True:
                names = z.namelist(out)
                missing = []
                for t in targets:
                    rel = t.relative_to(root)
                    member = f"{self.cfg.archive_inner_dir}/{rel.as_posix()}"
                    if member not in names:
                        missing.append((rel, member))
                        continue
                    inner = z.read(out, member, self.cfg.password).decode("utf-8")
                    if fingerprint.verify(inner, phrase) != 2:
                        missing.append((rel, "фраза ×2 не найдена"))
                if missing:
                    print(f"[✗] канарейка не подтверждена в архиве: {missing}")
                else:
                    print(f"[✓] канарейка «{phrase}» вшита и проверена в архиве "
                          f"({len(targets)} целей ×2)")

            size_mb = out.stat().st_size / 1048576
            dist = self.store_copy(out, version, phrase, user, ident)
            self.reg.append_log(
                f"| {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z | {phrase} | "
                f"{user} | {ident} | {out.name} | {size_mb:.1f}M | "
                f"{sha256_short(out)} |\n")
            print(f"[✓] архив: {out} ({size_mb:.1f} МБ)")
            print(f"[✓] выдача: {dist}/  (архив + info.md)")
        finally:
            if originals:
                self.restore(originals)
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)

    def rebuild(self, src_path: str, phrase: str, user: str, ident: str,
                dry: bool = False, force: bool = False,
                explicit_version: str = "") -> None:
        if not self.cfg.password:
            sys.exit("[✗] пароль архивов не задан: export GUARD_ZIP_PASSWORD=... "
                     "или создай config.py из config.example.py")
        src = Path(src_path)
        if src.is_dir():
            zips = sorted(src.glob(f"{self.cfg.archive_name}-*.zip"))
            if not zips:
                zips = sorted(src.glob("*.zip"))
            if not zips:
                sys.exit(f"[✗] в папке {src} нет архивов — дай путь к zip "
                         "или папке dist/")
            src = zips[-1]
        if not src.is_file() or src.suffix.lower() != ".zip":
            sys.exit(f"[✗] --rebuild: нужен zip или папка dist/, дано: {src}")

        phrase = phrase.strip()
        if not phrase:
            sys.exit("[✗] дай --fp \"новая фраза\" вместе с --rebuild")
        if self.reg.phrase_used(phrase) and not force:
            sys.exit(f"[✗] фраза «{phrase}» уже выдавалась (см. log.md) — "
                     "возьми другую или --force")

        known = {p for p, _, _ in self.reg.known_phrases()}
        tmp = Path(tempfile.mkdtemp(prefix="guard-rebuild-"))
        try:
            work = tmp / "work"
            work.mkdir()
            self.backend.extractall(src, work, self.cfg.password)
            ws = self.archive_inner(work)
            version = self.version(explicit_version)
            if version == "?":
                vf = ws / self.cfg.version_file
                version = vf.read_text(encoding="utf-8").strip() \
                    if vf.is_file() else "?"

            # strip old marks from every target inside the archive
            saved_cfg_root = self.cfg.root
            saved_targets = self._targets
            self._targets = None
            self.cfg.root = str(ws)
            try:
                targets = self.targets()
                removed_total = 0
                for t in targets:
                    text = t.read_text(encoding="utf-8")
                    cleaned, removed = fingerprint.strip_canaries(
                        text, known, phrase)
                    t.write_text(fingerprint.insert_canary(cleaned, phrase),
                                 encoding="utf-8")
                    removed_total += removed
            finally:
                self.cfg.root = saved_cfg_root
                self._targets = saved_targets

            out = tmp / f"{self.cfg.archive_name}-{version}.zip"
            self.backend.build(work, ws.name, out, self.cfg.password)

            # verification: canary x2 per target, no leftovers
            dirty = []
            names = self.backend.namelist(out)
            for t in targets:
                member = f"{ws.name}/{t.relative_to(ws).as_posix()}"
                inner = self.backend.read(out, member,
                                          self.cfg.password).decode("utf-8")
                if fingerprint.verify(inner, phrase) != 2:
                    dirty.append((member, "фраза ×2 не найдена"))
            for name in names:
                if not name.endswith(self.cfg.text_suffixes):
                    continue
                try:
                    txt = self.backend.read(out, name,
                                            self.cfg.password).decode("utf-8")
                except Exception:  # noqa: BLE001
                    continue
                # exact full-line matches only (no substring false positives)
                for ln in txt.split("\n"):
                    ls = ln.strip()
                    if ls in known:
                        dirty.append((name, ls))
                if "GUARD fp" in txt:
                    dirty.append((name, "GUARD fp"))
            if dirty:
                sys.exit(f"[✗] в новом архиве осталось палево: {dirty}")

            if dry:
                print(f"[dry-run] база: {src.name} · снято меток: "
                      f"{removed_total} строк · канарейка «{phrase}» "
                      f"готова · палево: нет")
                print("[dry-run] было бы: папка-улика в dist/ + строка в log.md")
                return

            size_mb = out.stat().st_size / 1048576
            dist = self.store_copy(out, version, phrase, user, ident)
            self.reg.append_log(
                f"| {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z | {phrase} | "
                f"{user} | {ident} | {out.name} | {size_mb:.1f}M | "
                f"{sha256_short(out)} |\n")
            print(f"[✓] база: {src.name} · снято старых меток: {removed_total} строк")
            print(f"[✓] канарейка «{phrase}» вшита и проверена в архиве")
            print("[✓] палево в архиве: нет (GUARD fp и старые фразы сняты)")
            print(f"[✓] архив: {out} ({size_mb:.1f} МБ)")
            print(f"[✓] выдача: {dist}/  (архив + info.md)")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def build_workspace(cfg: Config) -> tuple[Workspace, Registry]:
    reg = Registry(cfg)
    backend = make_backend(cfg.archive_backend)
    return Workspace(cfg, reg, backend), reg
