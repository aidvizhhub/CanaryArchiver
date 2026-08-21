# CanaryArchiver — конфигурация.
# Скопируй этот файл в config.py и заполни своими значениями.
# config.py в .gitignore — НЕ коммить его!

# Пароль ZIP-архивов. Обязателен для сборки/чтения архивов.
# Можно задать через переменную окружения GUARD_ZIP_PASSWORD —
# тогда config.py не нужен.
GUARD_ZIP_PASSWORD = ""

# Тексты водяных знаков (add_watermarks.py). Если не заданы —
# используются нейтральные значения по умолчанию.
WATERMARK_NOTICE = "Проприетарный воркспейс — распространение без разрешения запрещено"
WATERMARK_LINKS = ("your-handle", "your-channel", "your-hub")
