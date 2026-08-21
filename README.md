# CanaryArchiver 🐤

> **Know which copy leaked.**

CanaryArchiver — инструмент для создания **персональных, отслеживаемых копий архивов, AI-workspace и документации**.

Каждому получателю выдаётся своя уникальная копия с индивидуальным fingerprint — скрытой фразой-канарейкой. Если эта копия позже окажется в открытом доступе, CanaryArchiver позволяет определить, **из какой именно выдачи произошла утечка**.

```text
Исходный workspace
        │
        ▼
   CanaryArchiver
        │
        ├── 🐤 уникальная канарейка
        ├── 🏷️ водяные знаки
        ├── 📦 персональный архив
        ├── 🗂️ запись в реестр
        └── 🔍 сохранение доказательств
        │
        ▼
   Получатель @username
```

---

## Зачем это нужно?

Допустим, вы распространяете:

* AI-workspace;
* инструкции для AI-агентов;
* документацию;
* закрытый проект;
* набор промптов;
* внутренние материалы;
* персональные сборки.

Обычный архив выглядит так:

```text
project.zip
```

Выдали его десяти людям — и если он утёк, вы знаете только одно:

> Архив кто-то слил. 🗿

CanaryArchiver работает иначе.

```text
@alice → уникальная копия A
@bob   → уникальная копия B
@charlie → уникальная копия C
```

Каждая выдача получает **свой уникальный fingerprint**.

Если найден утёкший архив:

```bash
canaryarchiver leak leaked.zip
```

CanaryArchiver ищет канарейку и сопоставляет её с реестром выдач.

```text
🐤 Canary found

Recipient: @alice
Copy ID: 123456789
Fingerprint: ...
Version: ...
```

---

# ✨ Возможности

## 🐤 Unique Canary Fingerprints

Каждая копия получает уникальную фразу-канарейку.

Она используется как скрытый идентификатор конкретной выдачи:

```text
Copy #001 → fingerprint A
Copy #002 → fingerprint B
Copy #003 → fingerprint C
```

Одна и та же канарейка не может быть случайно выдана повторно.

---

## 📦 Персональные архивы

CanaryArchiver создаёт отдельную копию для каждого получателя.

```text
workspace/
        │
        ├── issue → @alice
        │         └── personal archive + fingerprint A
        │
        ├── issue → @bob
        │         └── personal archive + fingerprint B
        │
        └── issue → @charlie
                  └── personal archive + fingerprint C
```

---

## 🔍 Leak Detection

Нашли подозрительную копию?

Проверьте её:

```bash
canaryarchiver leak leaked.zip
```

Инструмент сканирует содержимое и ищет известные канарейки (в любых
текстовых файлах — `.md`, `.txt`, `.py`, `.json`, `.yaml`, `.toml` и т.д.).

Если fingerprint найден:

```text
MATCH FOUND

Recipient: @username
Copy ID: ...
Fingerprint: ...
```

---

## 🔄 Rebuild / Reissue

Можно перевыпустить уже подготовленную копию.

Старый fingerprint снимается, после чего создаётся новая персональная метка:

```bash
canaryarchiver rebuild dist/<issued-copy> \
  --fp "new fingerprint" \
  --user @username
```

Полезно, если нужно:

* перевыдать доступ;
* заменить получателя;
* создать новую версию персональной копии;
* отозвать старую выдачу и выпустить новую.

---

## 🗂️ Registry

Каждая выдача фиксируется в реестре.

```text
log.md
```

Реестр хранит информацию о созданных персональных копиях и используется для поиска владельца найденного fingerprint.

---

## 🕒 Version Rotation

Выдачи можно разделять по версиям.

При ротации старая эпоха переносится в архив:

```bash
canaryarchiver rotate --root ./my-project
```

Структура постепенно выглядит примерно так:

```text
current/
├── active registry
└── current version

archive/
├── version-1/
├── version-2/
└── version-3/
```

При этом история старых fingerprint сохраняется.

---

## 🏷️ Watermarks

Кроме канареек, CanaryArchiver поддерживает водяные знаки принадлежности.

```bash
canaryarchiver watermark --root ./my-project --stats
```

Водяные знаки могут размещаться в нескольких местах файла и использовать разные варианты размещения.

Идея простая:

```text
Canary → помогает идентифицировать конкретную копию

Watermark → показывает принадлежность материалов
```

Оба механизма работают вместе.

---

# 🧠 Как это работает?

### 1. Вы выбираете получателя

```text
@username
```

### 2. Создаёте уникальный fingerprint

Например:

```text
copy-202608210001
```

### 3. CanaryArchiver создаёт персональную копию

```text
Original workspace
        ↓
Insert unique canary (into each target file)
        ↓
Build archive
        ↓
Save evidence
        ↓
Register issuance
        ↓
Restore original files
```

### 4. Исходные файлы восстанавливаются

После сборки CanaryArchiver проверяет восстановление через SHA-256.

Цель — после создания персональной выдачи вернуть исходный workspace в первоначальное состояние.

---

# 🚀 Быстрый старт

## 1. Клонируйте репозиторий

```bash
git clone <repository-url>
cd CanaryArchiver
```

## 2. Создайте конфигурацию

```bash
cp config.example.py config.py
```

Добавьте пароль архива:

```text
GUARD_ZIP_PASSWORD=your-password
```

Также пароль можно передавать через окружение:

```bash
export GUARD_ZIP_PASSWORD="your-password"
```

> Не добавляйте `config.py` и реальные секреты в Git.

---

## 3. Выдайте персональную копию

```bash
canaryarchiver issue --root ./my-project \
  --targets "CLAUDE.md,AGENTS.md,README.md" \
  --fp "copy-for-user-001" \
  --user @username \
  --id 123456789
```

Или создайте автоматический идентификатор:

```bash
canaryarchiver issue --root ./my-project --auto
```

> Файлы-цели (`--targets`) — любые: канарейка вшивается в каждый.
> Никакой привязки к конкретной структуре проекта.

---

# 🔍 Проверка утечки

Допустим, вы нашли файл:

```text
leaked.zip
```

Запускаем:

```bash
canaryarchiver leak leaked.zip
```

CanaryArchiver проверит содержимое и попытается найти fingerprint в реестре.

---

# 📂 Структура проекта

```text
CanaryArchiver/
│
├── canaryarchiver/
│   ├── engine/
│   │   ├── fingerprint.py   # канарейки: вставка/проверка/снятие
│   │   ├── watermark.py     # водяные знаки (адаптеры под типы файлов)
│   │   ├── scanner.py       # targets/globs, exclude rules
│   │   ├── archiver.py      # бэкенды: system zip / python zipfile
│   │   ├── registry.py      # реестр, ротация версий
│   │   └── leak.py          # поиск утечки
│   ├── adapters/
│   │   └── workspace.py     # адаптер проекта: root, targets, version
│   ├── cli/
│   │   └── main.py          # issue / leak / rebuild / rotate / store / who / watermark
│   └── config/
│       └── defaults.py      # дефолты + загрузка config.py / env
│
├── guard.py                 # legacy-обёртка (старые команды работают)
├── add_watermarks.py        # legacy-обёртка водяных знаков
├── archive.py               # совместимый модуль реестра
├── cli.py                   # entry point без установки
├── config.example.py        # пример конфигурации
├── skills/
│   └── build-engine/        # инструкции для AI-агентов
└── pyproject.toml           # устанавливаемый пакет (`pip install -e .`)
```

---

# ⚙️ Конфигурация

Корень workspace задаётся через:

```bash
--root /path/to/workspace
```

или:

```bash
export WORKSPACE_ROOT="/path/to/workspace"
```

Всё project-specific — через `config.py` / переменные окружения / флаги:

| Что настраивается | Где |
|---|---|
| Файлы-цели для канарейки | `--targets` (файлы/глобы) |
| Имя архива | `archive_name` / `CANARYARCHIVER_ARCHIVE_NAME` |
| Источник версии | `file` (VERSION) / `git` tags / `--version` |
| Бэкенд архива | `system` (zip, шифрует) / `python` (stdlib) |
| Расширения сканирования | `text_suffixes` |
| Исключения | `exclude_dirs` / `exclude_names` / `exclude_parts` |
| Тексты водяных знаков | `WATERMARK_NOTICE` / `WATERMARK_LINKS` |
| Директория state | `--state-dir` / `CANARYARCHIVER_STATE_DIR` |

---

# 🔐 Безопасность

CanaryArchiver старается разделять:

### Публичный код

```text
Git repository
```

и:

### Приватные данные

```text
passwords
registry
issued copies
archives
evidence
local configuration
```

В Git **не должны попадать**:

```text
config.py
.env
passwords
log.md
dist/
archive/
version.txt
issued copies
```

---

## ⚠️ Важно

CanaryArchiver — это инструмент для **контроля распространения и идентификации конкретных копий**.

Fingerprint позволяет установить соответствие:

```text
найденная копия
        ↓
уникальная канарейка
        ↓
реестр выдач
        ↓
конкретная выдача
```

Это не заменяет полноценную систему DRM, криптографическую защиту или юридические меры.

Если вы используете ZIP-пароль, учитывайте уровень защиты используемого ZIP-формата: парольный архив полезен для ограничения случайного доступа, но не должен рассматриваться как абсолютная защита от целенаправленного анализа.

---

# 📋 Требования

* Python 3.9+
* `zip` (опционально: system-бэкенд с шифрованием; без него работает python-бэкенд)

---

# 🗺️ Workflow

Типичный процесс:

```text
1. Подготовить workspace
          ↓
2. Добавить watermark
          ↓
3. Создать fingerprint
          ↓
4. Выпустить персональную копию
          ↓
5. CanaryArchiver сохраняет запись
          ↓
6. Передать архив получателю
          ↓
7. При необходимости проверить утечку
          ↓
8. Найти соответствующую выдачу
```

---

# 🐤 Philosophy

**Одна общая копия — одна неизвестная утечка.**

**Персональные копии — возможность установить источник конкретной выдачи.**

CanaryArchiver создан вокруг простой идеи:

> **If every copy is unique, a leaked copy can tell its own story.**

---

## 🛣️ Roadmap

Уже сделано:

* [x] Универсальные target files вместо жёсткой привязки к одному workspace
* [x] Настраиваемые glob patterns для fingerprint scanning
* [x] Конфигурируемые exclude rules
* [x] Универсальные archive backends (system zip / python)
* [x] Настраиваемый state directory
* [x] CLI как устанавливаемый пакет (`pyproject.toml`)

В планах:

* [ ] Несколько форматов архивов (tar.gz, 7z...)
* [ ] Более сильные варианты шифрования
* [ ] Tests и CI
* [ ] Плагины для новых типов файлов

---

## ⭐ Если проект оказался полезным

Star репозиторию помогает проекту развиваться.

**CanaryArchiver — every issued copy leaves a unique trace. 🐤**
