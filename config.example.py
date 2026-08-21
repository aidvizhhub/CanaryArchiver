# CanaryArchiver — конфигурация (user policy).
# Скопируй в config.py и заполни. config.py в .gitignore — НЕ коммить его!
# Приоритет: CLI-флаги > CANARYARCHIVER_* env > config.py > defaults.

# --- секреты ---
# Пароль ZIP-архивов (обязателен для сборки/чтения).
GUARD_ZIP_PASSWORD = ""

# --- workspace policy ---
# root = ""                     # корень проекта (или --root / $WORKSPACE_ROOT)
# targets = ("CLAUDE.md",)      # файлы/глобы для канарейки (или --targets)
# default_targets = ("CLAUDE.md", "AGENTS.md", "README.md")
# require_all_defaults = False  # True: все default_targets обязаны существовать

# --- артефакты ---
# archive_name = "workspace"    # префикс: {archive_name}-{version}.zip
# archive_inner_dir = "workspace"  # папка внутри архива

# --- версия ---
# version_source = "file"       # file (VERSION) | git | config | explicit
# version_file = "VERSION"

# --- архивный бэкенд ---
# archive_backend = "auto"      # auto | system (zip -P, шифрует) | python (stdlib, не шифрует)

# --- watermark policy (нейтрально по умолчанию — движок не несёт идеологию) ---
WATERMARK_NOTICE = "Проприетарный воркспейс — распространение без разрешения запрещено"
WATERMARK_LINKS = ("your-handle", "your-channel", "your-hub")

# --- сканирование ---
# text_suffixes = (".md", ".txt", ".py", ".sh", ".ps1", ".js", ".json",
#                  ".jsonc", ".yaml", ".yml", ".toml", ".cfg", ".ini",
#                  ".html", ".css", ".svg")
# exclude_dirs = (".git", "__pycache__", "node_modules", "venv", "dist", ...)
# exclude_names = ("LICENSE", "CHANGELOG.md", "log.md", ...)
# exclude_parts = ("/.git/",)

# --- state ---
# state_dir = ""                # или env CANARYARCHIVER_STATE_DIR
