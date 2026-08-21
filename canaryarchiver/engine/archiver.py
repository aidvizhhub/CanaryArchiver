"""Archive backends: build/read zips.

- system backend: external `zip` command (supports ZipCrypto password)
- python backend: stdlib zipfile — READ side supports ZipCrypto;
  WRITE side cannot encrypt (stdlib limitation), so a password is
  ignored with a warning.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


class ArchiveBackend:
    name = "base"

    def build(self, work_dir: Path, inner_dir: str, out_path: Path,
              password: str = "") -> None:
        raise NotImplementedError

    def namelist(self, path: Path, password: str = "") -> list[str]:
        raise NotImplementedError

    def read(self, path: Path, member: str, password: str = "") -> bytes:
        raise NotImplementedError

    def extractall(self, path: Path, dest: Path, password: str = "") -> None:
        raise NotImplementedError

    # -- shared helpers -------------------------------------------------
    @staticmethod
    def _open(path: Path, password: str) -> zipfile.ZipFile:
        pwd = password.encode("utf-8") if password else None
        return zipfile.ZipFile(path)

    @classmethod
    def available(cls) -> bool:
        return True


class SystemZipBackend(ArchiveBackend):
    name = "system"

    def build(self, work_dir: Path, inner_dir: str, out_path: Path,
              password: str = "") -> None:
        cmd = ["zip", "-q", "-r", "-P", password, str(out_path), inner_dir]
        rc = subprocess.run(cmd, cwd=work_dir, check=False).returncode
        if rc != 0 or not out_path.is_file():
            sys.exit("[✗] сборка архива не удалась (команда zip)")

    # reading is done via stdlib zipfile (supports ZipCrypto passwords)
    def namelist(self, path: Path, password: str = "") -> list[str]:
        with zipfile.ZipFile(path) as z:
            return z.namelist()

    def read(self, path: Path, member: str, password: str = "") -> bytes:
        pwd = password.encode("utf-8") if password else None
        with zipfile.ZipFile(path) as z:
            return z.read(member, pwd=pwd)

    def extractall(self, path: Path, dest: Path, password: str = "") -> None:
        pwd = password.encode("utf-8") if password else None
        with zipfile.ZipFile(path) as z:
            z.extractall(dest, pwd=pwd)

    @classmethod
    def available(cls) -> bool:
        return shutil.which("zip") is not None


class PythonZipBackend(ArchiveBackend):
    name = "python"

    def build(self, work_dir: Path, inner_dir: str, out_path: Path,
              password: str = "") -> None:
        if password:
            print("[!] python-бэкенд не шифрует архивы (stdlib zipfile не умеет "
                  "писать ZipCrypto). Пароль ИГНОРИРУЕТСЯ — поставь backend=system, "
                  "чтобы получить зашифрованный архив.")
        src = work_dir / inner_dir
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            if not src.exists():
                sys.exit(f"[✗] нечего архивировать: {src}")
            for p in sorted(src.rglob("*")):
                if p.is_dir():
                    continue
                z.write(p, p.relative_to(work_dir).as_posix())

    def namelist(self, path: Path, password: str = "") -> list[str]:
        with zipfile.ZipFile(path) as z:
            return z.namelist()

    def read(self, path: Path, member: str, password: str = "") -> bytes:
        pwd = password.encode("utf-8") if password else None
        with zipfile.ZipFile(path) as z:
            return z.read(member, pwd=pwd)

    def extractall(self, path: Path, dest: Path, password: str = "") -> None:
        pwd = password.encode("utf-8") if password else None
        with zipfile.ZipFile(path) as z:
            z.extractall(dest, pwd=pwd)


def make_backend(kind: str) -> ArchiveBackend:
    """kind: auto | system | python"""
    if kind == "system":
        if not SystemZipBackend.available():
            sys.exit("[✗] backend=system, но команда zip не найдена")
        return SystemZipBackend()
    if kind == "python":
        return PythonZipBackend()
    # auto: prefer system (encryption support), fall back to python
    return SystemZipBackend() if SystemZipBackend.available() else PythonZipBackend()
