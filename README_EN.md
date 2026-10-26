# AutoUtil

[🇷🇺 Русский](README.md) | **🇬🇧 English**

Automatic file organizer for Windows. It watches the folders you choose (Downloads, Desktop, etc.) and sorts new files by rules: documents into *Documents*, older screenshots into the Recycle Bin, receipts into year folders using OCR text recognition. Every move is recorded in a journal and can be undone with one click.

---

## Features

- **Visual scheme** — draw it with lines: *Folder → Filter → Target/Recycle Bin*. One button to run, works as a set of regular rules.
- **Flexible rules** — match by extension, keywords (including text extracted from PDFs and OCR-recognized text from images), file name glob/regex patterns, size, age, or photo GPS tag.
- **Journal with undo** — every move is logged; any file can be restored to its original spot. The journal is append-only and rotates at 10 MB (3 backups kept).
- **Rule preview** — on the *Rules* page: pick a folder and a rule, and see exactly which files would match and where they would go — before anything is moved.
- **Deferred actions** — "move to the Recycle Bin in N days": the file stays in place and a reminder arrives when the time comes.
- **Work modes** — Active / Paused / Do Not Disturb (tray icon). Notifications made while paused are held and delivered when you switch back to Active.
- **Dry-run (plan only)** — a "look but don't touch" mode: files are not moved, you only get plan notifications. Enabled in *Settings*, takes effect immediately.
- **App cache cleaning** — every 30 days cleans known caches (browsers, IDEs, etc.); protected subfolders are left untouched.
- **Learning** — if you manually redirect where a file type goes, AutoUtil remembers and asks for confirmation next time.
- **Two languages** — Russian and English, chosen on first launch, changeable in Settings.

Everything runs locally: text recognition (RapidOCR) and PDF parsing are fully offline, no data ever leaves your machine.

## Quick start

### Ready-made exe

Grab `dist/AutoUtil.exe` from the releases and run it. A first-run wizard asks your language and helps you build the first scheme.

### From source

You need Python **3.12+**.

```powershell
git clone <repo>
cd AutoUtil
powershell -ExecutionPolicy Bypass -File build.ps1
```

The script creates a `.venv`, installs dependencies, runs the tests, and builds `dist/AutoUtil.exe`.

To run without building:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe main.py
```

## Usage

1. **Scheme** — add a *Folder* node (e.g. `C:\Users\you\Downloads`), drag a line to a *Filter* (extensions, keywords, ...), then from the filter to a *Target* (e.g. `Documents/PDF/{year}`) or the *Recycle Bin*. Press "Run scheme".
2. **Rules** — the same rules as a plain list: enable/disable with checkboxes, drag to reorder. The "Preview" button shows which files in a chosen folder the selected rule would catch.
3. **Pending** — files waiting for their "move in N days" deadline. Run now or put back.
4. **Journal** — the history of every move. Select an entry — "Restore file", and the file returns to its original spot (a file occupying that spot is set aside first, never deleted).
5. **Settings** — theme, font size, start with Windows, and the "plan only" (dry-run) mode.

## Where data lives

Everything is in `%LOCALAPPDATA%\AutoUtil\`:

| File | What it is |
|---|---|
| `schema.json` | the visual scheme |
| `rules.json` | sorting rules |
| `settings.toml` | settings |
| `journal.jsonl` | move journal (+ up to 3 rotated copies) |
| `learned.json` | learned overrides |
| `logs\autoutil.log` | app log (1 MB × 3) |

Safety: move targets are confined to the user's home folder — an imported third-party scheme physically cannot send files to another drive or into system folders (validated at import time).

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Covered: rule matching, planner, path safety, file moves (including races and busy targets), journal (undo, corrupt lines, rotation), naming, watcher (event deduplication), cache cleaning, rule preview, and translation coverage. Currently 62 tests.

## Project layout

```
main.py                  entry point: single-instance mutex, language, wizard, tray, service
core/                    journal, i18n, events, app state, deferred items
modules/organizer/       file analysis, rules, planner, OCR, cache cleaning
ui/                      PySide6: scheme, rules, journal, reports, tray
win/                     Windows specifics: paths, toasts, autostart, DPI
tests/                   pytest suite
build.ps1                exe build script (PyInstaller --onefile --windowed)
```

## Русский (кратко)

AutoUtil следит за папками и раскладывает новые файлы по правилам: документы — в «Документы», старые скриншоты — в корзину, чеки — по папкам по распознанному тексту. Схема рисуется узлами и линиями (Папка → Фильтр → Цель), каждый перенос пишется в журнал — вернуть можно одним кликом. Режим «только план» показывает план без переносов, предпросмотр правила — кого правило зацепит. Полностью офлайн, Windows 10/11, Python 3.12+.
