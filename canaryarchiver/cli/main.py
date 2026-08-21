"""CanaryArchiver CLI.

Modern interface:
    canaryarchiver issue  --root ./proj [--targets "CLAUDE.md,AGENTS.md,*.md"]
                          --user @user [--fp "фраза"|--auto] [--dry-run]
    canaryarchiver leak   ./leaked.zip
    canaryarchiver rebuild ./dist/<copy> --fp "новая" --user @user
    canaryarchiver rotate [--from 2.4]
    canaryarchiver store
    canaryarchiver who "фраза"
    canaryarchiver watermark [--check|--stats]

Legacy interface (guard.py) is routed automatically.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from canaryarchiver.config.defaults import Config, load, with_overrides
from canaryarchiver.engine import leak as leak_engine
from canaryarchiver.engine import watermark as wm_engine
from canaryarchiver.state import resolve_state_dir

SUBCOMMANDS = {"issue", "leak", "rebuild", "rotate", "store", "who", "watermark"}

# legacy flag -> subcommand
LEGACY_ROUTE = {
    "--rebuild": "rebuild",
    "--leak": "leak",
    "--who": "who",
    "--rotate": "rotate",
    "--store": "store",
    "--watermark": "watermark",
}


def route_legacy(argv: list[str]) -> list[str]:
    """Map old guard.py flags onto modern subcommands."""
    if not argv or argv[0] in SUBCOMMANDS:
        return argv
    for flag, sub in LEGACY_ROUTE.items():
        if flag in argv:
            rest = [a for a in argv if a != flag]
            return [sub] + rest
    return ["issue"] + argv


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=None, help="workspace root")
    common.add_argument("--state-dir", default=None,
                        help="registry state dir (env: CANARYARCHIVER_STATE_DIR)")
    common.add_argument("--config", default=None, help="path to config.py")
    common.add_argument("--dry-run", action="store_true",
                        help="plan without changes")

    p = argparse.ArgumentParser(
        prog="canaryarchiver",
        description="Universal fingerprint + watermark + controlled archival.",
        parents=[common],
    )

    sub = p.add_subparsers(dest="command")

    # issue ---------------------------------------------------------------
    i = sub.add_parser("issue", help="mark + build a copy for a recipient",
                       parents=[common])
    i.add_argument("--fp", default="", help="canary phrase (unique)")
    i.add_argument("--user", default="", help="recipient handle")
    i.add_argument("--id", default="", help="recipient account id")
    i.add_argument("--auto", action="store_true",
                   help="auto phrase copy-YYYYMMDDHHMMSS")
    i.add_argument("--force", action="store_true",
                   help="allow reusing an already-issued phrase")
    i.add_argument("--targets", default=None,
                   help="comma-separated files/globs (e.g. CLAUDE.md,AGENTS.md,*.md)")
    i.add_argument("--version", default="", dest="explicit_version",
                   help="explicit version (default: file:VERSION)")

    # leak -----------------------------------------------------------------
    lk = sub.add_parser("leak", help="whose copy leaked?", parents=[common])
    lk.add_argument("path")

    # rebuild ---------------------------------------------------------------
    r = sub.add_parser("rebuild", help="re-issue from an existing build",
                       parents=[common])
    r.add_argument("path")
    r.add_argument("--fp", default="", help="new phrase")
    r.add_argument("--user", default="", help="recipient handle")
    r.add_argument("--id", default="", help="recipient account id")
    r.add_argument("--force", action="store_true")
    r.add_argument("--targets", default=None)
    r.add_argument("--version", default="", dest="explicit_version")

    # rotate ---------------------------------------------------------------
    rt = sub.add_parser("rotate", help="archive previous version epoch",
                        parents=[common])
    rt.add_argument("--from", dest="from_ver", default="",
                    help="version to archive (default: marker/registry)")

    # store / who -----------------------------------------------------------
    sub.add_parser("store", help="show issuance storage", parents=[common])
    w = sub.add_parser("who", help="phrase -> owner", parents=[common])
    w.add_argument("phrase")

    # watermark --------------------------------------------------------------
    wm = sub.add_parser("watermark", help="watermark files under --root",
                        parents=[common])
    wm.add_argument("--check", action="store_true", help="report only")
    wm.add_argument("--stats", action="store_true", help="count marks")
    wm.add_argument("--extensions", default=None,
                    help="comma-separated extra suffixes (e.g. .rs,.go)")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = route_legacy(argv)

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    cfg = load(config_py=args.config)
    state_dir = resolve_state_dir(cfg)

    # CLI overrides (highest priority)
    if getattr(args, "root", None):
        cfg.root = args.root
    if getattr(args, "state_dir", None):
        cfg.state_dir = args.state_dir
        state_dir = Path(args.state_dir)
    if getattr(args, "targets", None):
        cfg.targets = tuple(t.strip() for t in args.targets.split(",") if t.strip())
    cfg.state_dir = str(state_dir)

    from canaryarchiver.adapters.workspace import build_workspace
    ws, reg = build_workspace(cfg)

    if args.command == "issue":
        phrase = args.fp.strip()
        if args.auto and not phrase:
            phrase = f"copy-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
        ws.issue(phrase, args.user, args.id, dry=args.dry_run,
                 force=args.force, explicit_version=args.explicit_version)
        return 0

    if args.command == "leak":
        phrases = reg.known_phrases()
        if not phrases:
            print("[—] реестр пуст — нечего искать")
            return 0
        leak_engine.check_leak(args.path, phrases, cfg)
        return 0

    if args.command == "rebuild":
        ws.rebuild(args.path, args.fp, args.user, args.id,
                   dry=args.dry_run, force=args.force,
                   explicit_version=args.explicit_version)
        return 0

    if args.command == "rotate":
        if not cfg.root:
            sys.exit("[✗] rotate требует --root (корень воркспейса)")
        from canaryarchiver.engine.registry import now_z  # noqa: F401
        current = ws.version()
        old = args.from_ver or (
            reg.marker.read_text(encoding="utf-8").strip()
            if reg.marker.is_file() else reg.infer_version())
        if not old:
            sys.exit("[✗] нечего архивировать: ни marker (version.txt), "
                     "ни версий в реестре")
        reg.rotate(old, current, dry=args.dry_run)
        return 0

    if args.command == "store":
        reg.store_listing()
        return 0

    if args.command == "who":
        reg.who_is(args.phrase)
        return 0

    if args.command == "watermark":
        if not cfg.root:
            sys.exit("[✗] watermark требует --root (корень воркспейса)")
        if getattr(args, "extensions", None):
            extra = tuple(e.strip().lower() for e in args.extensions.split(",")
                          if e.strip())
            cfg.text_suffixes = tuple(
                dict.fromkeys(list(cfg.text_suffixes) + list(extra)))
        wm_engine.run_watermark(Path(cfg.root), cfg, check=args.check,
                                stats=args.stats)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
