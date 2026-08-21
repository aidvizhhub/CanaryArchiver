#!/usr/bin/env python3
"""CanaryArchiver — canary-фингерпринт + сборка и учёт архивов воркспейса.

Перед каждой раздачей воркспейса вшивает в CLAUDE.md уникальную фразу
(фингерпринт копии) БЕЗ маркера — двумя обычными строками текста (canary
trap: метка неотличима от контента, получатель с одной копией не знает,
что она есть) — и собирает архив (ZIP с паролем из окружения
GUARD_ZIP_PASSWORD или config.py). Если копия утечёт наружу — по фразе
видно, с чьей копии: `guard.py --leak <файл|архив|папка>` ищет известные
фразы из log.md. После сборки CLAUDE.md возвращается к исходному состоянию
(байт-в-байт, сверка sha256).

Фраза может быть ЛЮБОЙ; к ней добавляются --user (юзернейм получателя)
и --id (номер/ID аккаунта) — реестр копий ведётся в log.md, и повтор
уже выданной фразы отклоняется (защита от переиспользования метки;
--force — если осознанно). Уникальность на копию = супер-метрика:
каждая копия отслеживается отдельно (паттерн honeytokens / canarytokens:
уникальный токен на выдачу + реестр + мониторинг).

Использование:
    python3 guard.py --fp "любая фраза"                    # метка копии
    python3 guard.py --fp "копия Васи" --user @vasya --id 12345
    python3 guard.py --auto                                # авто-серийник
    python3 guard.py --fp "..." --force                    # повтор фразы осознанно
    python3 guard.py --fp "..." --dry-run                  # план без сборки
    python3 guard.py --rebuild dist/<папка> --fp "новая" --user @ник  # перевыдача из готового билда
    python3 guard.py --leak путь/к/копии.zip               # чья копия?
    python3 guard.py --rotate [--from 2.4] [--dry-run]     # эпоху прошлой версии — в archive/<версия>/

Корень воркспейса: $WORKSPACE_ROOT или --root.
Журнал сборок — log.md рядом. Смена версии — авто-ротация: log.md и
dist/ прошлой эпохи уезжают в archive/<версия>/ (move-only, реестр
полон всегда) — паттерн logrotate + Artifactory (см. archive.py).
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from archive import (
    ARCHIVE,
    DIST,
    LOG,
    LOG_HEADER,
    MARKER,
    all_logs,
    ensure_rotated,
    infer_version,
    read_entries,
    rotate,
)

with suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Пароль ZIP-архивов: GUARD_ZIP_PASSWORD (окружение) или config.py
# (скопируй config.example.py в config.py). Пустой пароль = сборка запрещена.
with suppress(Exception):
    from config import GUARD_ZIP_PASSWORD as _cfg_password
    if _cfg_password:
        os.environ.setdefault("GUARD_ZIP_PASSWORD", _cfg_password)

PASSWORD = os.getenv("GUARD_ZIP_PASSWORD", "")


def need_password():
    """Пароль архива обязателен: без него нельзя собирать/читать архивы."""
    if not PASSWORD:
        sys.exit("[✗] пароль архивов не задан: export GUARD_ZIP_PASSWORD=... "
                 "или создай config.py из config.example.py")


def find_root(args):
    root = Path(args.root) if args.root else Path(os.environ.get("WORKSPACE_ROOT", ""))
    if not root or not (root / "CLAUDE.md").is_file() \
            or not (root / "make_archive.sh").is_file():
        sys.exit("[✗] корень воркспейса не найден: задай --root или WORKSPACE_ROOT "
                 "(нужны CLAUDE.md и make_archive.sh)")
    return root


def sha256_short(p):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()[:12]


def append_log(line):
    if not LOG.is_file():
        LOG.write_text(LOG_HEADER, encoding="utf-8")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)


def phrase_used(phrase):
    """Была ли фраза уже выдана (по столбцу «фраза» во всех реестрах —
    текущем и архивных: фраза уникальна навсегда)."""
    for path in all_logs():
        for row in read_entries(path):
            if row[1] == phrase:
                return True
    return False


def insert_canary(text, phrase):
    """Фраза в двух местах БЕЗ маркера — неотличима от контента (canary trap).

    A: отдельной строкой на 60-й позиции (вне таблиц).
    B: отдельной строкой во второй половине файла, позиция детерминирована
       хешем фразы (DERMARK-паттерн: владелец восстановит позицию, снаружи
       она непредсказуема — нет паттерна «начало + фикс. строка»).
    Никаких скобок/сносок: строка с фразой выглядит как обычный абзац.
    Получатель с одной копией не знает, что фраза — метка.
    """
    lines = text.split("\n")
    n = len(lines)
    pos_a = min(59, max(1, n - 1))
    while pos_a > 0 and "|" in lines[pos_a]:
        pos_a -= 1
    h = int(hashlib.sha256(phrase.encode("utf-8")).hexdigest()[:8], 16)
    lo = int(n * 0.55)
    span = max(1, int(n * 0.35))
    pos_b = min(n - 1, lo + h % span)
    while pos_b > 0 and ("|" in lines[pos_b] or pos_b <= pos_a + 2):
        if pos_b < n - 1:
            pos_b += 1
        else:
            pos_b = min(n - 1, pos_a + 3)  # короткий файл: кламп в границы
            break
    lines = lines[:pos_b] + [phrase] + lines[pos_b:]
    lines = lines[:pos_a] + [phrase] + lines[pos_a:]
    return "\n".join(lines)


def load_known_phrases():
    """Фразы из всех реестров (текущий + archive/*/log.md):
    [(фраза, юзер, id)] — полный реестр выданных копий."""
    return [(row[1], row[2], row[3])
            for path in all_logs() for row in read_entries(path)]


def who_is(phrase):
    """Фраза → владелец: ищет точное совпадение во всех реестрах."""
    phrase = phrase.strip()
    if not phrase:
        sys.exit("[✗] дай фразу: guard.py --who \"фраза\"")
    for path in all_logs():
        for row in read_entries(path):
            if row[1] == phrase:
                where = ("текущий log.md" if path == LOG
                         else f"архив {path.parent.name}/log.md")
                print(f"[!] фраза «{phrase}» принадлежит: {row[2] or '—'}"
                      f"{' · id: ' + row[3] if row[3] else ''}")
                print(f"    выдана: {row[0]} · архив: {row[4]}"
                      f" · {row[5]} · sha256 {row[6]}")
                print(f"    реестр: {where}")
                return
    print(f"[—] фраза «{phrase}» в реестре не найдена (не наша выдача или опечатка)")


def check_leak(path):
    """Чья копия утекла: ищет известные фразы из log.md в файле/архиве/папке."""
    import zipfile
    p = Path(path)
    texts = {}
    if not p.exists():
        sys.exit(f"[✗] нет такого пути: {p}")
    if p.suffix.lower() == ".zip":
        need_password()
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if name.endswith(".md"):
                    with suppress(Exception):
                        texts[name] = z.read(name,
                                             pwd=PASSWORD.encode()).decode("utf-8")
    elif p.is_dir():
        for f in p.rglob("*.md"):
            with suppress(Exception):
                texts[str(f)] = f.read_text(encoding="utf-8")
    else:
        with suppress(Exception):
            texts[str(p)] = p.read_text(encoding="utf-8")
    if not texts:
        sys.exit("[✗] не удалось прочитать ни одного .md (архив с паролем?)")
    hits = []
    for phrase, user, ident in load_known_phrases():
        for name, txt in texts.items():
            if phrase and phrase in txt:
                hits.append((phrase, user, ident, name, txt.count(phrase)))
    if not hits:
        print("[—] известных фраз в копии нет: либо не наша выдача, "
              "либо метки сняты")
        return
    for phrase, user, ident, name, n in hits:
        print(f"[!] НАЙДЕНА фраза «{phrase}» (×{n}) в {name}")
        print(f"    юзер: {user or '—'} · id: {ident or '—'}")
        if user or ident:
            print(f"    → это копия для {user or ident}")


def store_copy(archive, version, phrase, user, ident):
    """Выдача как «улика в пакете» (chain of custody, паттерн криминалистики +
    artifact provenance GitHub/Azure): папка на выдачу, внутри — сам архив
    и info.md со всей метой (фраза, юзер, id, дата, sha256, размер)."""
    DIST.mkdir(exist_ok=True)
    slug = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_-]+", "-", phrase)[:24].strip("-") or "copy"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sha = sha256_short(archive)
    full_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    folder = DIST / f"{ts}_{slug}_{sha}"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive, folder / f"workspace-{version}.zip")
    size_mb = archive.stat().st_size / 1048576
    info = (f"# Копия воркспейса — сопроводиловка\n\n"
            f"- Фраза (канарейка): {phrase}\n"
            f"- Юзер: {user or '—'}\n"
            f"- ID: {ident or '—'}\n"
            f"- Выдана: {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z\n"
            f"- Версия: {version}\n"
            f"- Архив: workspace-{version}.zip\n"
            f"- SHA256: {full_sha}\n"
            f"- Размер: {size_mb:.1f}M\n")
    (folder / "info.md").write_text(info, encoding="utf-8")
    return folder


def rebuild_copy(args):
    """Перевыдача из готового билда: база — архив прошлой выдачи (или папка
    dist/ с ним). Снимает старые метки (v3-строки фраз из реестра + палевные
    комментарии «GUARD fp» билдов до v3), вшивает новую фразу тем же
    v3-алгоритмом, пересобирает zip той же командой, что make_archive.sh,
    проверяет (канарейка ×2, палево снято по всем текстовым файлам) и
    сохраняет как НОВУЮ выдачу: папка-улика + строка в log.md. Старые
    дисты не переписываются."""
    import tempfile
    import zipfile

    need_password()

    src = Path(args.rebuild)
    if src.is_dir():
        zips = sorted(src.glob("workspace-*.zip"))
        if not zips:
            sys.exit(f"[✗] в папке {src} нет workspace-*.zip — дай путь к zip "
                     "или папке dist/")
        src = zips[-1]
    if not src.is_file() or src.suffix.lower() != ".zip":
        sys.exit(f"[✗] --rebuild: нужен zip или папка dist/, дано: {src}")

    phrase = args.fp.strip()
    if args.auto and not phrase:
        phrase = f"copy-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    if not phrase:
        sys.exit("[✗] дай --fp \"новая фраза\" вместе с --rebuild")
    if phrase_used(phrase) and not args.force:
        sys.exit(f"[✗] фраза «{phrase}» уже выдавалась (см. log.md) — "
                 "возьми другую или --force")

    known = {p for p, _, _ in load_known_phrases()}
    tmp = Path(tempfile.mkdtemp(prefix="guard-rebuild-"))
    try:
        work = tmp / "work"
        work.mkdir()
        with zipfile.ZipFile(src) as z:
            z.extractall(work, pwd=PASSWORD.encode("utf-8"))
        workspace = work / "workspace"
        if not workspace.is_dir():
            dirs = [d for d in work.iterdir() if d.is_dir()]
            workspace = dirs[0] if dirs else work
        claude = workspace / "CLAUDE.md"
        if not claude.is_file():
            sys.exit(f"[✗] в базовом архиве нет {workspace.name}/CLAUDE.md")

        # снять старые метки: GUARD fp-комментарии + строки известных фраз
        lines = claude.read_text(encoding="utf-8").split("\n")
        stripped = [l for l in lines
                    if "GUARD fp" not in l and l.strip() not in known
                    and l.strip() != phrase]
        removed = len(lines) - len(stripped)
        claude.write_text(insert_canary("\n".join(stripped), phrase),
                          encoding="utf-8")

        version = (workspace / "VERSION").read_text().strip() \
            if (workspace / "VERSION").is_file() else "?"
        out = tmp / f"workspace-{version}.zip"
        rc = subprocess.run(["zip", "-q", "-r", "-P", PASSWORD, str(out),
                             workspace.name], cwd=work, check=False).returncode
        if rc != 0 or not out.is_file():
            sys.exit("[✗] пересборка архива не удалась")

        # проверка: канарейка ×2 + палево снято по всем текстовым файлам
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            inner = z.read(f"{workspace.name}/CLAUDE.md",
                           pwd=PASSWORD.encode("utf-8")).decode("utf-8")
        found = inner.count(phrase) == 2
        dirty = []
        with zipfile.ZipFile(out) as z:
            for name in names:
                if not name.endswith((".md", ".txt")):
                    continue
                txt = ""
                with suppress(Exception):
                    txt = z.read(name, pwd=PASSWORD.encode("utf-8")).decode("utf-8")
                for p in known:
                    if p and p in txt:
                        dirty.append((name, p))
                if "GUARD fp" in txt:
                    dirty.append((name, "GUARD fp"))
        if dirty:
            sys.exit(f"[✗] в новом архиве осталось палево: {dirty}")

        if args.dry_run:
            print(f"[dry-run] база: {src.name} · снято меток: {removed} строк · "
                  f"канарейка «{phrase}» ×{inner.count(phrase)} · палево: нет")
            print("[dry-run] было бы: папка-улика в dist/ + строка в log.md")
            return

        size_mb = out.stat().st_size / 1048576
        dist = store_copy(out, version, phrase, args.user, args.id)
        append_log(f"| {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z | {phrase} | "
                   f"{args.user} | {args.id} | {out.name} | {size_mb:.1f}M | "
                   f"{sha256_short(out)} |\n")
        print(f"[✓] база: {src.name} · снято старых меток: {removed} строк")
        print(f"[✓] канарейка «{phrase}» вшита и проверена в архиве: "
              f"{'✓' if found else '✗ НЕ НАШЛАСЬ (2 места ожидались)'}")
        print("[✓] палево в архиве: нет (GUARD fp и старые фразы сняты)")
        print(f"[✓] архив: {out} ({size_mb:.1f} МБ)")
        print(f"[✓] выдача: {dist}/  (архив + info.md)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Canary-фингерпринт + архив воркспейса")
    ap.add_argument("--fp", default="", help="фраза-метка этой копии (любая, уникальная)")
    ap.add_argument("--user", default="", help="юзернейм получателя (например @vasya)")
    ap.add_argument("--id", default="", help="номер/ID аккаунта получателя")
    ap.add_argument("--auto", action="store_true", help="авто-серийник вместо --fp")
    ap.add_argument("--force", action="store_true", help="разрешить повтор уже выданной фразы")
    ap.add_argument("--root", default="", help="корень воркспейса (по умолчанию $WORKSPACE_ROOT)")
    ap.add_argument("--dry-run", action="store_true", help="план без изменений и сборки")
    ap.add_argument("--store", action="store_true", help="показать хранилище dist/")
    ap.add_argument("--rebuild", default="", help="перевыдача из готового билда: "
                    "путь к zip или папке dist/ (новая фраза через --fp)")
    ap.add_argument("--leak", default="", help="файл/архив/папка утёкшей копии — чья?")
    ap.add_argument("--who", default="", help="фраза → чья копия (по всем реестрам)")
    ap.add_argument("--rotate", action="store_true", help="архивировать эпоху "
                    "прошлой версии: log.md + dist/ → archive/<версия>/, "
                    "начать свежую")
    ap.add_argument("--from", dest="from_ver", default="", help="с --rotate: "
                    "из какой версии архивировать (по умолчанию — marker/реестр)")
    args = ap.parse_args()

    if args.who:
        who_is(args.who)
        return
    if args.leak:
        check_leak(args.leak)
        return

    if args.store:
        folders = sorted(DIST.iterdir()) if DIST.is_dir() else []
        cur = MARKER.read_text(encoding="utf-8").strip() \
            if MARKER.is_file() else "?"
        print(f"хранилище {DIST}: {len(folders)} выдач (эпоха {cur})")
        for f in folders:
            if not f.is_dir():
                continue
            zip_files = list(f.glob("*.zip"))
            z = zip_files[0] if zip_files else None
            print(f"  {f.name}/  ({z.stat().st_size / 1048576:.1f}M)" if z
                  else f"  {f.name}/")
        if ARCHIVE.is_dir():
            arch = sorted(a for a in ARCHIVE.iterdir() if a.is_dir())
            if arch:
                print(f"архив версий {ARCHIVE}:")
                for a in arch:
                    rows = len(read_entries(a / "log.md"))
                    dists = len(list((a / "dist").iterdir())) \
                        if (a / "dist").is_dir() else 0
                    print(f"  {a.name}/  log.md {rows} записей · "
                          f"dist {dists} выдач")
        return

    if args.rotate:
        root = find_root(args)
        current = (root / "VERSION").read_text().strip() \
            if (root / "VERSION").is_file() else "?"
        old = args.from_ver or (
            MARKER.read_text(encoding="utf-8").strip() if MARKER.is_file()
            else infer_version())
        if not old:
            sys.exit("[✗] нечего архивировать: ни marker (version.txt), "
                     "ни версий в реестре")
        rotate(old, current, dry=args.dry_run)
        return

    if args.rebuild:
        rebuild_copy(args)
        return

    root = find_root(args)
    version = (root / "VERSION").read_text().strip() \
        if (root / "VERSION").is_file() else "?"
    ensure_rotated(version, dry=args.dry_run)
    phrase = args.fp.strip()
    if args.auto and not phrase:
        phrase = f"copy-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    if not phrase:
        sys.exit("[✗] дай --fp \"фраза\" (любая) или --auto")
    if phrase_used(phrase) and not args.force:
        sys.exit(f"[✗] фраза «{phrase}» уже выдавалась (см. log.md) — "
                 "возьми другую или --force")

    canary = phrase

    need_password()

    claude = root / "CLAUDE.md"
    maker = root / "make_archive.sh"
    archive = root.parent / f"workspace-{version}.zip"

    orig = claude.read_bytes()
    marked = insert_canary(orig.decode("utf-8"), canary)
    if args.dry_run:
        print(f"[dry-run] канарейка «{canary}» → {claude.name} "
              f"(60-я строка + позиция из хеша фразы, без маркера), "
              f"потом: bash {maker.name} → {archive}")
        return

    try:
        claude.write_text(marked, encoding="utf-8")
        rc = subprocess.run(["bash", str(maker)], cwd=root, check=False).returncode
        if rc != 0 or not archive.is_file():
            sys.exit("[✗] сборка архива не удалась")
        # проверка: канарейка в архиве? (zipfile умеет ZipCrypto с паролем)
        import zipfile
        with zipfile.ZipFile(archive) as z:
            inner = z.read("workspace/CLAUDE.md",
                           pwd=PASSWORD.encode("utf-8")).decode("utf-8")
        found = inner.count(canary) == 2
        size_mb = archive.stat().st_size / 1048576
        dist = store_copy(archive, version, phrase, args.user, args.id)
        append_log(f"| {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z | {phrase} | "
                   f"{args.user} | {args.id} | {archive.name} | {size_mb:.1f}M | "
                   f"{sha256_short(archive)} |\n")
        print(f"[✓] канарейка «{canary}» вшита и проверена в архиве: "
              f"{'✓' if found else '✗ НЕ НАШЛАСЬ (2 места ожидались)'}")
        print(f"[✓] архив: {archive} ({size_mb:.1f} МБ)")
        print(f"[✓] выдача: {dist}/  (архив + info.md)")
    finally:
        claude.write_bytes(orig)  # возврат к исходному — байт-в-байт
        ok = claude.read_bytes() == orig
        print(f"[✓] CLAUDE.md восстановлен"
              f"{' (сверка sha256)' if ok else ' — СВЕРКА НЕ СОШЛАСЬ!'}")


if __name__ == "__main__":
    main()
