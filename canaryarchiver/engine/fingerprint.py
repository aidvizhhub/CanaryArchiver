"""Canary fingerprint engine: embed/verify/strip phrases in text files.

Algorithm preserved from the original tool (v3):
  A: standalone line at position 60 (outside tables)
  B: standalone line in the second half, position derived from phrase hash
     (no predictable pattern from outside)
"""
from __future__ import annotations

import hashlib


def insert_canary(text: str, phrase: str) -> str:
    """Insert phrase at two positions WITHOUT marker — indistinguishable from content."""
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
            pos_b = min(n - 1, pos_a + 3)
            break
    lines = lines[:pos_b] + [phrase] + lines[pos_b:]
    lines = lines[:pos_a] + [phrase] + lines[pos_a:]
    return "\n".join(lines)


def strip_canaries(text: str, known_phrases: set[str], new_phrase: str = "") -> tuple[str, int]:
    """Remove canary lines: old known phrases + legacy 'GUARD fp' markers.

    Returns (cleaned_text, removed_lines_count).
    """
    lines = text.split("\n")
    stripped = [l for l in lines
                if "GUARD fp" not in l
                and l.strip() not in known_phrases
                and l.strip() != new_phrase]
    return "\n".join(stripped), len(lines) - len(stripped)


def verify(text: str, phrase: str) -> int:
    """How many times the phrase appears as a FULL line (expect 2 per target).

    Uses exact line matching, not substring: a new phrase containing an old
    one (e.g. 'фраза X' inside 'новая фраза X') must not count as a hit.
    """
    return sum(1 for ln in text.split("\n") if ln.strip() == phrase)
