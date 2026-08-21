"""Registry: issuance ledger (log.md), version rotation, phrase lookup.

Markdown-table format is preserved from the original tool; storage
location is configurable (state_dir).
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from canaryarchiver.config.defaults import Config

LOG_HEADER = ("| когда | фраза | юзер | id | архив | размер | sha256 |\n"
              "|---|---|---|---|---|---|---|\n")


class Registry:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        state = Path(cfg.state_dir)
        self.log = state / cfg.log_file
        self.dist = state / cfg.dist_dir
        self.archive = state / cfg.archive_dir
        self.marker = state / cfg.version_marker
        self.ver_re = re.compile(re.escape(cfg.archive_name) + r"-([\w.-]+)\.zip")

    # ---- paths / ledger -------------------------------------------------
    @staticmethod
    def slug(s) -> str:
        return re.sub(r"[^0-9A-Za-z._-]+", "-", str(s)).strip("-") or "unknown"

    def all_logs(self) -> list[Path]:
        logs = [self.log] if self.log.is_file() else []
        if self.archive.is_dir():
            logs += sorted(self.archive.glob("*/log.md"))
        return logs

    def read_entries(self, path: Path) -> list[tuple[str, str, str, str, str, str, str]]:
        out = []
        if not path.is_file():
            return out
        for ln in path.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) >= 3 and cells[0] and not cells[0].startswith("когда") \
                    and cells[1] and cells[1] != "---":
                while len(cells) < 7:
                    cells.append("")
                out.append(tuple(cells[:7]))
        return out

    def append_log(self, line: str) -> None:
        if not self.log.is_file():
            self.log.write_text(LOG_HEADER, encoding="utf-8")
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(line)

    # ---- phrase queries -------------------------------------------------
    def known_phrases(self) -> list[tuple[str, str, str]]:
        return [(row[1], row[2], row[3])
                for path in self.all_logs() for row in self.read_entries(path)]

    def phrase_used(self, phrase: str) -> bool:
        return any(row[1] == phrase for path in self.all_logs()
                   for row in self.read_entries(path))

    def who_is(self, phrase: str) -> None:
        phrase = phrase.strip()
        if not phrase:
            raise SystemExit("[✗] дай фразу: guard.py --who \"фраза\"")
        for path in self.all_logs():
            for row in self.read_entries(path):
                if row[1] == phrase:
                    where = ("текущий log.md" if path == self.log
                             else f"архив {path.parent.name}/log.md")
                    print(f"[!] фраза «{phrase}» принадлежит: {row[2] or '—'}"
                          f"{' · id: ' + row[3] if row[3] else ''}")
                    print(f"    выдана: {row[0]} · архив: {row[4]}"
                          f" · {row[5]} · sha256 {row[6]}")
                    print(f"    реестр: {where}")
                    return
        print(f"[—] фраза «{phrase}» в реестре не найдена (не наша выдача или опечатка)")

    # ---- version / rotation ----------------------------------------------
    def infer_version(self) -> str:
        seen = ""
        for path in self.all_logs():
            for row in self.read_entries(path):
                m = self.ver_re.search(row[4])
                if m:
                    seen = m.group(1)
        return seen

    def rotate(self, old_ver: str, new_ver: str, dry: bool = False) -> None:
        target = self.archive / self.slug(old_ver)

        if dry:
            n_rows = sum(len(self.read_entries(p)) for p in self.all_logs()
                         if p == self.log)
            n_dist = len(list(self.dist.iterdir())) if self.dist.is_dir() else 0
            print(f"[dry-run] ротация эпохи {old_ver} → {target}/:")
            print(f"          log.md ({n_rows} записей) + dist/ ({n_dist} выдач) "
                  f"→ архив; version.txt = {new_ver}")
            return

        target.mkdir(parents=True, exist_ok=True)

        note_log = "нет"
        if self.log.is_file():
            rows = [ln for ln in self.log.read_text(encoding="utf-8").splitlines()
                    if ln.startswith("|") and not ln.startswith("|---")
                    and not ln.startswith("| когд")]
            arch_log = target / "log.md"
            if rows and arch_log.is_file():
                old_lines = arch_log.read_text(encoding="utf-8").splitlines()
                arch_log.write_text("\n".join(old_lines + rows) + "\n",
                                    encoding="utf-8")
                note_log = f"+{len(rows)} записей"
            elif rows:
                shutil.move(str(self.log), str(arch_log))
                note_log = f"{len(rows)} записей"
            else:
                note_log = "0 записей (журнал пуст — архив не трогаем)"

        moved = 0
        if self.dist.is_dir():
            for item in list(self.dist.iterdir()):
                dst = target / "dist" / item.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    print(f"[!] {dst} уже существует — пропущен {item.name}")
                    continue
                shutil.move(str(item), str(dst))
                moved += 1

        self.log.write_text(LOG_HEADER, encoding="utf-8")
        self.dist.mkdir(exist_ok=True)
        self.marker.write_text(str(new_ver).strip(), encoding="utf-8")
        print(f"[✓] эпоха {old_ver} → {target}/ (log.md {note_log}, "
              f"dist {moved} выдач); новая эпоха: {new_ver}")

    def ensure_rotated(self, current: str, dry: bool = False,
                       forced_from: str = "") -> None:
        old = forced_from or (
            self.marker.read_text(encoding="utf-8").strip()
            if self.marker.is_file() else self.infer_version())
        if not old:
            self.marker.write_text(str(current).strip(), encoding="utf-8")
            return
        if old == current and not forced_from:
            return
        self.rotate(old, current, dry=dry)

    # ---- store listing ---------------------------------------------------
    def store_listing(self) -> None:
        folders = sorted(self.dist.iterdir()) if self.dist.is_dir() else []
        cur = self.marker.read_text(encoding="utf-8").strip() \
            if self.marker.is_file() else "?"
        print(f"хранилище {self.dist}: {len(folders)} выдач (эпоха {cur})")
        for f in folders:
            if not f.is_dir():
                continue
            zips = list(f.glob("*.zip"))
            z = zips[0] if zips else None
            print(f"  {f.name}/  ({z.stat().st_size / 1048576:.1f}M)" if z
                  else f"  {f.name}/")
        if self.archive.is_dir():
            arch = sorted(a for a in self.archive.iterdir() if a.is_dir())
            if arch:
                print(f"архив версий {self.archive}:")
                for a in arch:
                    rows = len(self.read_entries(a / "log.md"))
                    dists = len(list((a / "dist").iterdir())) \
                        if (a / "dist").is_dir() else 0
                    print(f"  {a.name}/  log.md {rows} записей · "
                          f"dist {dists} выдач")


def now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M") + "Z"
