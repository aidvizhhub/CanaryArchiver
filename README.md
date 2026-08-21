# CanaryArchiver

Universal engine for **fingerprinting + watermarking + controlled archival**
of any project or workspace. Every distributed copy gets an invisible
canary phrase — if a copy leaks, one command tells you whose copy it was.

The engine is **workspace-agnostic**: no hardcoded file names, no required
project layout, no built-in ideology. Everything project-specific is
configuration (`config.py` / env / CLI flags).

## Architecture

```
canaryarchiver/
├── engine/            # universal logic (no project assumptions)
│   ├── fingerprint.py # canary embed/verify/strip (2 positions, no marker)
│   ├── watermark.py   # multi-position ownership marks (comment-syntax adapters)
│   ├── scanner.py     # target resolution (files/globs) + text-file iteration
│   ├── archiver.py    # archive backends: system zip | python zipfile
│   ├── registry.py    # issuance ledger, version rotation, phrase lookup
│   └── leak.py        # leak scanner (any text suffix, exact-line matching)
├── adapters/
│   └── workspace.py   # project adapter: root, targets, version, artifacts
├── cli/
│   └── main.py        # issue / leak / rebuild / rotate / store / who / watermark
└── config/
    └── defaults.py    # engine defaults + config.py/env loading
```

Engine vs policy is separated: the engine knows how to fingerprint,
watermark, archive, rotate and scan; **your** project is described in
`config.py` (targets, excludes, names, policy texts).

## Install

```bash
git clone https://github.com/aidvizhhub/CanaryArchiver.git
cd CanaryArchiver
pip install -e .            # optional: adds `canaryarchiver` command
cp config.example.py config.py   # and set GUARD_ZIP_PASSWORD
```

No install needed to try: `python3 cli.py ...` works from the repo dir.
`guard.py` and `add_watermarks.py` remain as legacy-compatible wrappers.

## Usage

```bash
export GUARD_ZIP_PASSWORD=...        # or via config.py

# 1) mark a copy for a recipient and build the archive.
#    Targets: any files/globs — no CLAUDE.md/make_archive.sh required.
canaryarchiver issue --root ./my-project \
    --targets "CLAUDE.md,AGENTS.md,README.md,*.md" \
    --fp "фраза для @vasya" --user @vasya --id 123456789

# 2) automatic phrase, dry-run first
canaryarchiver issue --root ./my-project --targets "*.md" --auto --dry-run

# 3) a copy leaked — whose?
canaryarchiver leak ./leaked.zip

# 4) re-issue from an existing build (old marks stripped, new phrase embedded)
canaryarchiver rebuild dist/<copy-folder> --fp "новая фраза" --user @ник

# 5) version epoch rotation (registry + dist → archive/<version>/)
canaryarchiver rotate --root ./my-project [--from 2.4] [--dry-run]

# 6) show storage / phrase lookup
canaryarchiver store
canaryarchiver who "фраза"

# 7) watermarking (multi-position marks, comment syntax per file type)
canaryarchiver watermark --root ./my-project [--check|--stats]
```

## What is configurable (all with sane defaults)

| Concern | Default | Override |
|---|---|---|
| Fingerprint targets | `CLAUDE.md, AGENTS.md, README.md` (first existing) | `--targets`, `targets` in config.py, globs allowed |
| Artifact name | `workspace-{version}.zip` | `archive_name` / `CANARYARCHIVER_ARCHIVE_NAME` |
| Inner dir in zip | `workspace` | `archive_inner_dir` |
| Version source | `file` (`VERSION`) | `git` tags / `--version` explicit / config |
| Archive backend | `auto` (system `zip` if present) | `CANARYARCHIVER_BACKEND=python` |
| Scan suffixes | `.md .txt .py .sh .js .json .yaml .toml ...` | `text_suffixes` in config.py |
| Excluded dirs/files | `.git, __pycache__, node_modules, venv, dist, LICENSE...` | `exclude_dirs/names/parts` in config.py |
| Watermark text | **empty** (neutral engine) | `WATERMARK_NOTICE`, `WATERMARK_LINKS` in config.py |
| State location | package dir (backward compat) | `--state-dir`, `CANARYARCHIVER_STATE_DIR` |

Archive exclusions (what never goes into the zip): `.git`, caches,
`dist/`, `archive/`, `log.md`, `version.txt`, `config.py`, `*.zip`, `*.bak`
— override via `archive_excludes` in config.py.

## Security model

- Canary phrase: embedded **without any marker** at two deterministic
  positions (line 60 + position derived from the phrase hash). A recipient
  with one copy cannot tell it is a mark.
- Registry (`log.md`): full chain of custody — phrase, user, id, date,
  artifact, sha256. Phrases are unique forever; duplicates rejected.
- Leak scan: exact **full-line** matching (no substring false positives
  when a new phrase contains an old one).
- Watermarks: up to 3 positions per file, syntax-verified insertion
  (ast / `bash -n` / `node --check`), safe defaults.
- ZipCrypto (system backend) protects against casual curious eyes, not
  cryptanalysis — README-level honesty: archive ≠ encryption. The python
  backend cannot write encrypted zips (stdlib limitation) and says so.

## Legacy interface

The original flags still work through the wrappers:

```bash
python3 guard.py --fp "фраза" --user @vasya --id 123   # issue
python3 guard.py --auto --dry-run
python3 guard.py --leak утёкший.zip
python3 guard.py --rebuild dist/<папка> --fp "новая" --user @ник
python3 guard.py --rotate --from 2.4
python3 guard.py --store
python3 guard.py --who "фраза"
python3 add_watermarks.py --check --root ./project
```

## Requirements

- Python 3.9+
- `zip` command (optional; system backend, enables encryption)
