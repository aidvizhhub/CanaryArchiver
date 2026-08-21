"""Ротация логов и dist по версиям воркспейса (паттерн logrotate + Artifactory).

Когда версия воркспейса меняется (VERSION), выдачи прошлой эры переезжают
в archive/<старая-версия>/: log.md и dist/ — move-only, ничего не
удаляется (chain of custody: реестр копий полон всегда, канарейки
уникальны навсегда). Текущая эра хранится в version.txt.

Индустрия: артефакты по версиям (JFrog/Artifactory `repo/app/1.2.3/`,
Nexus/Maven layout), logrotate (старый файл — в архив с меткой, свежий
начинается заново), keepachangelog discussion #565 (старые записи — в
отдельный архивный файл, текущий файл начинается заново).
"""
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "log.md"
DIST = HERE / "dist"
ARCHIVE = HERE / "archive"
MARKER = HERE / "version.txt"

LOG_HEADER = ("| когда | фраза | юзер | id | архив | размер | sha256 |\n"
              "|---|---|---|---|---|---|---|\n")

VER_RE = re.compile(r"workspace-([\w.-]+)\.zip")


def slug(s):
    return re.sub(r"[^0-9A-Za-z._-]+", "-", str(s)).strip("-") or "unknown"


def all_logs():
    """Текущий log.md + все архивные — реестр копий полон всегда."""
    logs = [LOG] if LOG.is_file() else []
    if ARCHIVE.is_dir():
        logs += sorted(ARCHIVE.glob("*/log.md"))
    return logs


def read_entries(path):
    """Строки реестра из одного log.md: (когда, фраза, юзер, id, архив,
    размер, sha) — по 7 полей на запись."""
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


def infer_version():
    """Версия эпохи из имён архивов в реестре (workspace-2.4.zip -> 2.4)."""
    seen = ""
    for path in all_logs():
        for row in read_entries(path):
            m = VER_RE.search(row[4])
            if m:
                seen = m.group(1)
    return seen


def rotate(old_ver, new_ver, dry=False):
    """Эпоху old_ver — в archive/<old_ver>/; начать новую эпоху new_ver.

    Move-only: log.md переносится (при повторной ротации той же версии
    строки дописываются в конец архивного журнала — реестр append-only),
    папки dist/ переносятся целиком. Ничего не удаляется."""
    target = ARCHIVE / slug(old_ver)

    if dry:
        n_rows = sum(len(read_entries(p)) for p in all_logs() if p == LOG)
        n_dist = len(list(DIST.iterdir())) if DIST.is_dir() else 0
        print(f"[dry-run] ротация эпохи {old_ver} → {target}/:")
        print(f"          log.md ({n_rows} записей) + dist/ ({n_dist} выдач) "
              f"→ архив; version.txt = {new_ver}")
        return

    target.mkdir(parents=True, exist_ok=True)

    # log.md: если архивный журнал этой версии уже есть — дописать строки данных
    note_log = "нет"
    if LOG.is_file():
        rows = [ln for ln in LOG.read_text(encoding="utf-8").splitlines()
                if ln.startswith("|") and not ln.startswith("|---")
                and not ln.startswith("| когд")]
        arch_log = target / "log.md"
        if rows and arch_log.is_file():
            old_lines = arch_log.read_text(encoding="utf-8").splitlines()
            arch_log.write_text("\n".join(old_lines + rows) + "\n",
                                encoding="utf-8")
            note_log = f"+{len(rows)} записей"
        elif rows:
            shutil.move(str(LOG), str(arch_log))
            note_log = f"{len(rows)} записей"
        else:
            note_log = "0 записей (журнал пуст — архив не трогаем)"

    # dist/: переносим содержимое целиком (имена папок-улик уникальны)
    moved = 0
    if DIST.is_dir():
        for item in list(DIST.iterdir()):
            dst = target / "dist" / item.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                print(f"[!] {dst} уже существует — пропущен {item.name}")
                continue
            shutil.move(str(item), str(dst))
            moved += 1

    # свежая эпоха
    LOG.write_text(LOG_HEADER, encoding="utf-8")
    DIST.mkdir(exist_ok=True)
    MARKER.write_text(str(new_ver).strip(), encoding="utf-8")
    print(f"[✓] эпоха {old_ver} → {target}/ (log.md {note_log}, "
          f"dist {moved} выдач); новая эпоха: {new_ver}")


def ensure_rotated(current, dry=False, forced_from=""):
    """Авто-ротация перед выдачей: marker/реестр не совпал с VERSION —
    эпоху в архив. forced_from — принудительная версия (легаси-переход:
    архивировать под этой версией, даже если она равна текущей)."""
    old = forced_from or (
        MARKER.read_text(encoding="utf-8").strip() if MARKER.is_file()
        else infer_version())
    if not old:
        MARKER.write_text(str(current).strip(), encoding="utf-8")
        return
    if old == current and not forced_from:
        return
    rotate(old, current, dry=dry)
