"""Watermark engine: multi-position ownership marks in text files.

Extension -> comment syntax is a configurable adapter map (defaults in
config/defaults.py); new file types can be added via config.py
(comment_syntax), without touching the algorithm.

Neutral by default: notice/links are EMPTY unless the owner configures
them (config.py / env). No project ideology is baked into defaults.
"""
from __future__ import annotations

import ast
import hashlib
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path

from canaryarchiver.config.defaults import Config
from canaryarchiver.engine.scanner import iter_text_files


def hnum(rel: str, salt: str, mod: int) -> int:
    h = hashlib.sha1(f"{rel}|{salt}".encode()).hexdigest()
    return int(h[:8], 16) % mod


class MarkupStrategy:
    """Adapter: how to open/close a comment for a file type."""
    def __init__(self, open_: str, close: str):
        self.open, self.close = open_, close

    def wrap(self, line: str) -> str:
        return f"{self.open}{line}{self.close}"


def strategy_for(suffix: str, syntax: dict) -> MarkupStrategy:
    op, cl = syntax.get(suffix.lower(), ("# ", ""))
    return MarkupStrategy(op, cl)


def watermark_variants(notice: str, links: tuple[str, ...],
                       marker: str) -> tuple[list[str], list[str]]:
    """Build visible + hidden watermark lines from policy (may be empty)."""
    l0, l1, l2 = (list(links) + ["", "", ""])[:3]
    variants: list[str] = []
    hidden: list[str] = []

    if notice:
        variants.append(notice)
    if l0 or l1 or l2:
        variants += [
            f"Принадлежит: {l0} · {l1} · {l2} — ищи в Телеграме",
            f"Принадлежит каналу {l0} · админ {l1} · гиг {l2}",
            f"{l0} · {l1} · {l2} — все в Телеграме: {l0}",
            f"Источник: тг {l0} | {l1} | {l2} — канал и гиг в ТГ",
        ]
        hidden += [
            f"wm: {l0} · {l1} · {l2}",
            f"wm: {l1} · {l0} · {l2}",
            f"wm: {l0} · {l2} · {l1}",
        ]
    if not variants:
        variants = [marker]
    return variants, hidden


def block_for(rel: str, pos: int, ext: str, cfg: Config,
              variants: list[str], hidden: list[str]) -> str:
    st = strategy_for(ext, cfg.comment_syntax)
    v = variants[hnum(rel, f"v{pos}", len(variants))]
    lines = [st.wrap(v)]
    if cfg.watermark_notice:
        lines.append(st.wrap(cfg.watermark_notice))
    if ext == ".md" and pos % 2 == 0 and hidden:
        lines.append(f"<!-- {hidden[hnum(rel, f'h{pos}', len(hidden))]} -->")
    return "\n".join(lines)


def top_point(ext: str, text: str, lines: list[str]):
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
            return tree.body[0].end_lineno
        return 1
    if ext == ".md":
        if lines and lines[0].strip() == "---":
            for i in range(1, min(len(lines), 15)):
                if lines[i].strip() == "---":
                    return i + 1
            return None
        return 1
    return 1 if lines else 0


def mid_point(ext: str, text: str, lines: list[str], rel: str):
    if len(lines) < 8:
        return None
    frac = 0.30 + hnum(rel, "frac", 41) / 100.0
    if ext == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None
        nodes = [n for n in tree.body if hasattr(n, "lineno")
                 and not isinstance(n, (ast.Import, ast.ImportFrom))]
        if len(nodes) < 2:
            return None
        target = nodes[max(0, int(len(nodes) * frac) - 1)].lineno - 1
        tp = top_point(ext, text, lines) or 0
        return target if target > tp else None
    if ext in (".sh", ".js"):
        cand = int(len(lines) * frac)
        for step in range(len(lines) // 2):
            for i in (cand + step, cand - step):
                if 0 < i < len(lines) and not lines[i].strip():
                    return i
        return None
    cand = int(len(lines) * frac)
    for step in range(len(lines) // 2):
        for i in (cand + step, cand - step):
            if 0 < i < len(lines) and not lines[i].strip():
                return i
    return cand


def verify(ext: str, text: str) -> bool:
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


def insert_at(lines, idx, block, nl):
    return lines[:idx] + [block + nl] + lines[idx:]


def ensure_marks(text: str, rel: str, ext: str, cfg: Config,
                 variants: list[str], hidden: list[str]):
    """Top up marks to cfg.watermark_positions per file. Returns (text, added)."""
    marker = cfg.watermark_marker
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split("\n")
    crlf = nl == "\r\n"
    lines = [ln.rstrip("\r") for ln in lines]
    current = text.count(marker)
    target = cfg.watermark_positions
    added = 0
    for pos in range(target):
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
        block = block_for(rel, pos, ext, cfg, variants, hidden)
        candidate = insert_at(lines, idx, block, "\n")
        if not verify(ext, "\n".join(candidate)) and pos == 1:
            continue
        lines = candidate
        added += 1
    out = "\n".join(lines)
    return out.replace("\n", "\r\n") if crlf else out, added


def run_watermark(root: Path, cfg: Config, check: bool, stats: bool) -> None:
    variants, hidden = watermark_variants(
        cfg.watermark_notice, cfg.watermark_links, cfg.watermark_marker)
    total = added_files = added_marks = 0
    for p in iter_text_files(root, cfg):
        total += 1
        rel = p.relative_to(root)
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        marks = text.count(cfg.watermark_marker)
        if stats:
            if marks:
                added_files += 1
                added_marks += marks
            continue
        if marks >= cfg.watermark_positions:
            continue
        new_text, n = ensure_marks(text, str(rel), p.suffix.lower(), cfg,
                                   variants, hidden)
        if n == 0:
            continue
        if check:
            print(f"[ ] {rel}  (+{n} знаков)")
        else:
            p.write_text(new_text, encoding="utf-8")
        added_files += 1
        added_marks += n

    if stats:
        print(f"размечено файлов: {added_files}, знаков всего: {added_marks}")
    else:
        print(f"итого: целей {total}, файлов докачано {added_files}, "
              f"знаков добавлено {added_marks} "
              f"({'было бы ' if check else ''})")
