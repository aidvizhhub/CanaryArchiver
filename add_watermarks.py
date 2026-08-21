#!/usr/bin/env python3
"""Водяные знаки принадлежности — v2: в НЕСКОЛЬКИХ местах каждого файла.

Зачем v2: знак только в конце файла предсказуем — срезать последние строки
скриптом = снять всё сразу (замечание владельца 13.08). Паттерн защиты из
ресёрча (arXiv 2412.12511 «Invisible Watermarks: Attacks and Robustness»,
canary-tokens thinkst): ИЗБЫТОЧНОСТЬ — несколько знаков в разных позициях,
удаление всех требует понимания структуры файла, а не одной команды.

Как работает v2:
- каждый файл получает ДО 3 знаков: верх (после shebang/докстринга/
  frontmatter), середина (перед top-level оператором/по пустой строке —
  позиция детерминирована хешем пути+размера, снаружи непредсказуема),
  конец;
- каждая позиция — СВОЯ вариация из 6 + в md скрытый HTML-комментарий
  чередуется с видимой строкой;
- безопасность вставки: python — позиции из ast (перед top-level
  операторами), bash — проверка `bash -n` после вставки (при падении
  средняя позиция откатывается), js — `node --check`; не прошло — знак
  только в безопасных местах (верх/конец);
- идемпотентно и само-докачивает: файл с 1 старым знаком (только конец)
  получает недостающие позиции — до 3 на файл.

Запуск:
    python3 scripts/add_watermarks.py            # применить (докачать до 3)
    python3 scripts/add_watermarks.py --check    # отчёт без записи
    python3 scripts/add_watermarks.py --stats    # сколько знаков/файлов
"""
import argparse
import ast
import hashlib
import os
import shutil
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

with suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = None  # определяется в main(): --root или $WORKSPACE_ROOT

# --- настройки принадлежности (можно переопределить в config.py) ---
try:
    from config import (WATERMARK_NOTICE as _cfg_notice,
                        WATERMARK_LINKS as _cfg_links)
except ImportError:
    _cfg_notice = _cfg_links = None

MARKER = "CanaryArchiver-WM"

NOTICE = _cfg_notice or ("Проприетарный воркспейс — распространение без "
                         "разрешения запрещено")

_L = _cfg_links or ("your-handle", "your-channel", "your-hub")
_L0, _L1, _L2 = _L[0], _L[1], _L[2]

# 6 вариаций. В каждой — хотя бы одна обычная ссылка + обфускации.
VARIANTS = [
    (f"Принадлежит: {_L0} · {_L1} · {_L2} — ищи в Телеграме"),
    (f"Принадлежит каналу {_L0} · админ {_L1} · гиг {_L2}"),
    (f"{_L0} · {_L1} · {_L2} — все в Телеграме: {_L0}"),
    (f"Принадлежит сообществу · канал: {_L0} · админ: {_L1} · гиг: {_L2}"),
    (f"Источник: тг {_L0} | {_L1} | {_L2} — канал и гиг в ТГ"),
    (f"wm: {_L0} | {_L1} | {_L2}"),
]

HIDDEN = [
    f"wm: {_L0} · {_L1} · {_L2}",
    f"wm: {_L1} · {_L0} · {_L2}",
    f"wm: {_L0} · {_L2} · {_L1}",
]

COMMENT = {  # расширение -> (открывашка, закрывашка)
    ".py": ("# ", ""),
    ".sh": ("# ", ""),
    ".ps1": ("# ", ""),
    ".js": ("// ", ""),
    ".jsonc": ("// ", ""),
    ".toml": ("# ", ""),
    ".yml": ("# ", ""),
    ".yaml": ("# ", ""),
    ".md": ("", ""),
    ".txt": ("", ""),
}

SKIP_DIRS = {"db", "venv", ".git", ".github", "node_modules", "__pycache__",
             "models", ".reasonix", ".ruff_cache", ".code-review-graph",
             ".pytest_cache"}
SKIP_NAMES = {"CHANGELOG.md", "LICENSE", "index.md", "log.md"}
SKIP_PARTS = ("/eval/",)  # вендор-артефакты fable eval


def hnum(rel: str, salt: str, mod: int) -> int:
    h = hashlib.sha1(f"{rel}|{salt}".encode()).hexdigest()
    return int(h[:8], 16) % mod


def block_for(rel: str, pos: int, ext: str) -> str:
    """Блок знака для позиции pos (0=верх, 1=середина, 2=конец)."""
    v = VARIANTS[hnum(rel, f"v{pos}", len(VARIANTS))]
    open_c, close_c = COMMENT[ext]
    lines = [f"{open_c}{v}{close_c}", f"{open_c}{NOTICE}{close_c}"]
    if ext == ".md" and pos % 2 == 0:  # в md скрытый знак чередуется с видимым
        lines.append(f"<!-- {HIDDEN[hnum(rel, f'h{pos}', len(HIDDEN))]} -->")
    return "\n".join(lines)


def insert_at(lines, idx, block, nl):
    """Вставляет блок строкой по индексу idx (0..len)."""
    return lines[:idx] + [block + nl] + lines[idx:]


# --- безопасные точки вставки ---

def top_point(ext, text, lines):
    """Верх: после shebang/докстринга/frontmatter. None — если не нашли."""
    if lines and lines[0].startswith("#!"):
        return 1
    if ext == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None
        if (tree.body and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant)
                and isinstance(tree.body[0].value.value, str)):
            return tree.body[0].end_lineno  # после модульного докстринга
        return 1
    if ext == ".md":
        if lines and lines[0].strip() == "---":
            for i in range(1, min(len(lines), 15)):
                if lines[i].strip() == "---":
                    return i + 1
            return None
        return 1
    return 1 if lines else 0


def mid_point(ext, text, lines, rel):
    """Середина: безопасная позиция, детерминированная хешем (непредсказуема)."""
    if len(lines) < 8:
        return None
    frac = 0.30 + hnum(rel, "frac", 41) / 100.0  # 30-70% файла
    if ext == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None
        # импорты — не кандидаты: знак между импортами ломает isort/ruff
        # (I001, грабля 13.08 — 11 файлов после разметки)
        nodes = [n for n in tree.body if hasattr(n, "lineno")
                 and not isinstance(n, (ast.Import, ast.ImportFrom))]
        if len(nodes) < 2:
            return None
        target = nodes[max(0, int(len(nodes) * frac) - 1)].lineno - 1
        return target if target > (top_point(ext, text, lines) or 0) else None
    if ext in (".sh", ".js"):
        cand = int(len(lines) * frac)
        for step in range(len(lines) // 2):
            for i in (cand + step, cand - step):
                if 0 < i < len(lines) and not lines[i].strip():
                    return i
        return None
    # md/txt/yml/toml/jsonc: комментарий в любое место безопасен — по пустой
    cand = int(len(lines) * frac)
    for step in range(len(lines) // 2):
        for i in (cand + step, cand - step):
            if 0 < i < len(lines) and not lines[i].strip():
                return i
    return cand


# --- верификация вставки ---

def verify(ext, text):
    if ext == ".py":
        try:
            ast.parse(text)
            return True
        except SyntaxError:
            return False
    if ext == ".sh":
        return shutil.which("bash") is not None and subprocess.run(
            ["bash", "-n", "/dev/stdin"], input=text, text=True,
            capture_output=True, check=False).returncode == 0
    if ext == ".js":
        node = shutil.which("node")
        return node is not None and subprocess.run(
            [node, "--check", "--stdin"], input=text, text=True,
            capture_output=True, check=False).returncode == 0
    return True


def ensure_marks(text, rel, ext):
    """Докачивает знаки до 3 позиций. Возвращает (текст, сколько добавлено)."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split("\n")
    # пересобираем линии без \r-хвостов, хвост вернём при джойне
    crlf = nl == "\r\n"
    lines = [ln.rstrip("\r") for ln in lines]
    current = text.count(MARKER)
    target = 3
    added = 0
    for pos in range(3):
        if current + added >= target:
            break
        idx = None
        if pos == 0:
            idx = top_point(ext, text, lines)
        elif pos == 1:
            idx = mid_point(ext, text, lines, rel)
        else:
            idx = len(lines)
        if idx is None:
            continue
        block = block_for(rel, pos, ext)
        candidate = insert_at(lines, idx, block, "\n")
        if not verify(ext, "\n".join(candidate)) and pos == 1:
            continue  # середина не прошла проверку — пропускаем, не ломаем
        lines = candidate
        added += 1
    out = "\n".join(lines)
    return out.replace("\n", "\r\n") if crlf else out, added


def iter_targets():
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if set(rel.parts) & SKIP_DIRS or p.name in SKIP_NAMES:
            continue
        if p.name.endswith(".bak") or p.name.endswith(".pyc"):
            continue
        if any(s in str(rel) for s in SKIP_PARTS):
            continue
        if p.suffix.lower() not in COMMENT:
            continue
        yield rel


def main():
    ap = argparse.ArgumentParser(description="Водяные знаки v2 (2-3 позиции на файл)")
    ap.add_argument("--check", action="store_true", help="только отчёт, без записи")
    ap.add_argument("--stats", action="store_true", help="сколько знаков/файлов")
    ap.add_argument("--root", default="", help="корень воркспейса (по умолчанию $WORKSPACE_ROOT)")
    args = ap.parse_args()

    global ROOT
    ROOT = Path(args.root) if args.root else Path(os.environ.get("WORKSPACE_ROOT", ""))
    if not ROOT or not (ROOT / "VERSION").is_file():
        sys.exit("[✗] корень воркспейса не найден: --root или $WORKSPACE_ROOT "
                 "(нужен маркер VERSION)")

    total = added_files = added_marks = 0
    for rel in iter_targets():
        total += 1
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        marks = text.count(MARKER)
        if args.stats:
            if marks:
                added_files += 1
                added_marks += marks
            continue
        if marks >= 3:
            continue
        new_text, n = ensure_marks(text, str(rel), p.suffix.lower())
        if n == 0:
            continue
        if args.check:
            print(f"[ ] {rel}  (+{n} знаков)")
        else:
            p.write_text(new_text, encoding="utf-8")
        added_files += 1
        added_marks += n

    if args.stats:
        print(f"размечено файлов: {added_files}, знаков всего: {added_marks}")
    else:
        print(f"итого: целей {total}, файлов докачано {added_files}, "
              f"знаков добавлено {added_marks} "
              f"({'было бы ' if args.check else ''})")


if __name__ == "__main__":
    main()
