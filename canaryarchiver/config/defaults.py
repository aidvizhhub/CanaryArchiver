"""Configuration defaults + loading.

Order (lowest -> highest priority):
    1. built-in defaults (this module)
    2. user config.py (see config.example.py; looked up in CWD)
    3. environment variables CANARYARCHIVER_*
    4. CLI flags (passed by caller)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

# ---- defaults (engine policy, not project policy) ----

DEFAULT_EXCLUDE_DIRS = (
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".ruff_cache",
    "node_modules", "venv", ".venv", "dist", "build", ".tox", ".mypy_cache",
)
DEFAULT_EXCLUDE_NAMES = (
    "LICENSE", "CHANGELOG.md", "log.md", "version.txt", "config.py",
)
DEFAULT_EXCLUDE_PARTS = ("/.git/",)

# text-like suffixes scanned for canaries / watermarked
DEFAULT_TEXT_SUFFIXES = (
    ".md", ".txt", ".py", ".sh", ".ps1", ".js", ".json", ".jsonc",
    ".yaml", ".yml", ".toml", ".cfg", ".ini", ".html", ".css", ".svg",
)

# comment syntax per suffix: (open, close)
DEFAULT_COMMENT_SYNTAX = {
    ".py": ("# ", ""), ".sh": ("# ", ""), ".ps1": ("# ", ""),
    ".js": ("// ", ""), ".jsonc": ("// ", ""), ".toml": ("# ", ""),
    ".yml": ("# ", ""), ".yaml": ("# ", ""), ".md": ("", ""),
    ".txt": ("", ""), ".html": ("<!-- ", " -->"), ".css": ("/* ", " */"),
}


@dataclass
class Config:
    # ---- workspace policy ----
    root: str = ""                       # workspace root (default: $WORKSPACE_ROOT)
    targets: tuple[str, ...] = ()        # files/globs to fingerprint (default: manifest list)
    default_targets: tuple[str, ...] = ("CLAUDE.md", "AGENTS.md", "README.md")
    require_all_defaults: bool = False   # False: use first existing default target

    # ---- artifact naming ----
    archive_name: str = "workspace"      # artifact prefix: {archive_name}-{version}.zip
    archive_inner_dir: str = "workspace" # dir name inside the zip

    # ---- version ----
    version_source: str = "file"         # file | explicit | config | git
    version_file: str = "VERSION"        # marker file inside root

    # ---- archive backend ----
    archive_backend: str = "auto"        # auto | system | python
    zip_command: str = "zip"
    # glob patterns excluded from the built archive (staging copy)
    archive_excludes: tuple[str, ...] = (
        ".git", "__pycache__", "*.pyc", ".ruff_cache", ".pytest_cache",
        "node_modules", "venv", ".venv", "dist", "archive", "log.md",
        "version.txt", "config.py", "config.example.py", "*.zip", "*.bak",
    )

    # ---- scanning / watermark ----
    text_suffixes: tuple[str, ...] = DEFAULT_TEXT_SUFFIXES
    exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDE_DIRS
    exclude_names: tuple[str, ...] = DEFAULT_EXCLUDE_NAMES
    exclude_parts: tuple[str, ...] = DEFAULT_EXCLUDE_PARTS
    comment_syntax: dict = field(default_factory=lambda: dict(DEFAULT_COMMENT_SYNTAX))

    # ---- watermark policy (neutral by default; owner sets via config.py) ----
    watermark_marker: str = "CanaryArchiver-WM"
    watermark_notice: str = ""
    watermark_links: tuple[str, ...] = ()
    watermark_positions: int = 3

    # ---- registry / state ----
    state_dir: str = ""                  # default: package dir (backward compat)
    log_file: str = "log.md"
    dist_dir: str = "dist"
    archive_dir: str = "archive"
    version_marker: str = "version.txt"

    # ---- secrets ----
    password: str = ""                   # from env GUARD_ZIP_PASSWORD or config.py


def _bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


def load(config_py: str | Path | None = None) -> Config:
    """Build Config: defaults <- config.py <- CANARYARCHIVER_* env."""
    cfg = Config()

    # 1) user config.py (explicit path or CWD)
    candidates: list[Path] = []
    if config_py:
        candidates.append(Path(config_py))
    else:
        candidates.append(Path.cwd() / "config.py")
    for path in candidates:
        if not path.is_file():
            continue
        ns: dict = {}
        try:
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)
        except Exception as e:  # noqa: BLE001 — config must never kill the engine
            raise SystemExit(f"[✗] config.py не читается: {e}")
        for k in dir(cfg):
            if k in ns and ns[k] is not None:
                setattr(cfg, k, ns[k])

    # 2) environment CANARYARCHIVER_*
    env_map = {
        "CANARYARCHIVER_STATE_DIR": "state_dir",
        "CANARYARCHIVER_ROOT": "root",
        "CANARYARCHIVER_ARCHIVE_NAME": "archive_name",
        "CANARYARCHIVER_ARCHIVE_INNER_DIR": "archive_inner_dir",
        "CANARYARCHIVER_BACKEND": "archive_backend",
        "CANARYARCHIVER_VERSION_SOURCE": "version_source",
        "CANARYARCHIVER_TARGETS": "targets",
    }
    for env_key, attr in env_map.items():
        val = os.getenv(env_key)
        if val is None:
            continue
        if attr == "targets":
            setattr(cfg, attr, tuple(t.strip() for t in val.split(",") if t.strip()))
        else:
            setattr(cfg, attr, val)

    # 3) secrets from env (always wins over config.py)
    if os.getenv("GUARD_ZIP_PASSWORD"):
        cfg.password = os.getenv("GUARD_ZIP_PASSWORD", "")

    # normalize
    cfg.targets = tuple(t for t in cfg.targets if t.strip())
    return cfg


def with_overrides(cfg: Config, **kw) -> Config:
    """CLI overrides (highest priority). None values are ignored."""
    clean = {k: v for k, v in kw.items() if v is not None}
    return replace(cfg, **clean)
