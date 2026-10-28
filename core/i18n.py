"""Минимальная локализация: английский и русский.

Язык выбирается при первом запуске и хранится в prefs.toml (поле language).
Строки ищутся по ключу; если перевода нет, возвращается английский.
"""

from core.ru_en import RU_EN

LANGUAGES = {"en": "English", "ru": "Русский"}

_LANG = "en"

_STRINGS: dict[str, dict[str, str]] = {
    # tray
    "tray.active": {"en": "AutoUtil: running", "ru": "AutoUtil: работает"},
    "tray.paused": {"en": "AutoUtil: paused", "ru": "AutoUtil: пауза"},
    "tray.dnd": {"en": "AutoUtil: do not disturb", "ru": "AutoUtil: не беспокоить"},
    "tray.pause_hour": {"en": "Pause for 1 hour", "ru": "Пауза на час"},
    "tray.dnd_action": {"en": "Do not disturb", "ru": "Не беспокоить"},
    "tray.open": {"en": "Open AutoUtil", "ru": "Открыть AutoUtil"},
    "tray.journal": {"en": "Journal", "ru": "Журнал"},
    "tray.settings": {"en": "Settings", "ru": "Настройки"},
    "tray.quit": {"en": "Exit", "ru": "Выход"},
    # language dialog
    "lang.title": {"en": "AutoUtil", "ru": "AutoUtil"},
    "lang.prompt": {"en": "Choose your language\nВыберите язык", "ru": "Choose your language\nВыберите язык"},
    # wizard
    "wizard.title": {"en": "AutoUtil: first run", "ru": "AutoUtil: первый запуск"},
    "wizard.folder.title": {"en": "Folder to watch", "ru": "Папка для отслеживания"},
    "wizard.folder.subtitle": {
        "en": "AutoUtil will watch this folder and sort new files.",
        "ru": "AutoUtil будет следить за этой папкой и раскладывать новые файлы.",
    },
    "wizard.folder.label": {"en": "Folder path:", "ru": "Путь к папке:"},
    "wizard.options.title": {"en": "Settings", "ru": "Настройки"},
    "wizard.options.dry": {
        "en": "Show the plan first, without moving files (recommended)",
        "ru": "Сначала только показывать план, без переносов (рекомендуется)",
    },
    "wizard.options.autostart": {"en": "Start with Windows", "ru": "Запускать вместе с Windows"},
    # journal
    "journal.title": {"en": "AutoUtil: action journal", "ru": "AutoUtil: журнал действий"},
    "journal.refresh": {"en": "Refresh", "ru": "Обновить"},
    "journal.undo": {"en": "Restore selected", "ru": "Вернуть выбранное"},
    "journal.returned": {"en": "[restored] ", "ru": "[возвращён] "},
    "journal.select": {"en": "Select an entry.", "ru": "Выберите запись."},
    "journal.undo_ok": {"en": "File restored to its original place.", "ru": "Файл возвращён на место."},
    "journal.undo_fail": {
        "en": "Could not restore: the file was already moved or deleted.",
        "ru": "Вернуть не удалось: файл уже перемещён или удалён.",
    },
    # notifications
    "notify.title": {"en": "AutoUtil", "ru": "AutoUtil"},
    "notify.batch": {
        "en": "Events: {n}. Open the journal to see them.",
        "ru": "Событий: {n}. Откройте журнал, чтобы посмотреть.",
    },
    "notify.failure": {
        "en": "Could not process {name}. Details are in the log.",
        "ru": "Не удалось обработать файл {name}. Подробности в логе.",
    },
    "notify.ask_title": {"en": "Decision needed", "ru": "Нужно решение"},
    "notify.ask_body": {
        "en": "{name}: open the “Ask” section in AutoUtil.",
        "ru": "{name}: откройте раздел «Спросить» в AutoUtil.",
    },
    "notify.plan_title": {"en": "Planned: move", "ru": "План: перенос"},
    "notify.plan_move_body": {
        "en": "{name} → {folder} (rule: {rule})",
        "ru": "{name} → {folder} (правило: {rule})",
    },
    "notify.plan_bin_title": {"en": "Planned: Recycle Bin", "ru": "План: в корзину"},
    "notify.plan_bin_body": {
        "en": "{name} → Recycle Bin (rule: {rule})",
        "ru": "{name} → Корзина (правило: {rule})",
    },
    "notify.plan_delay_title": {"en": "Planned: after {days} days", "ru": "План: через {days} дн."},
    "notify.plan_delay_body": {
        "en": "{name} → {place} after {days} days (rule: {rule})",
        "ru": "{name} → {place} через {days} дн. (правило: {rule})",
    },
    "notify.deferred_title": {"en": "Postponed", "ru": "Отложено"},
    "notify.deferred_body": {
        "en": "{name} will be handled in {days} days (rule: {rule}).",
        "ru": "{name} будет обработан через {days} дн. (правило: {rule}).",
    },
    "notify.deferred_fail": {
        "en": "Could not run the postponed action for {name}. It will be retried.",
        "ru": "Отложенное действие для {name} не сработало. Попытка повторится.",
    },
    "notify.dup_title": {"en": "Duplicate skipped", "ru": "Дубликат пропущен"},
    "notify.dup_body": {
        "en": "{name} is already in {folder}",
        "ru": "{name} уже есть в {folder}",
    },
    "notify.moved_title": {"en": "File moved", "ru": "Файл перенесён"},
    "notify.moved_body": {
        "en": "{name} → {folder}. Undo it in the tray journal.",
        "ru": "{name} → {folder}. Откат: журнал в трее.",
    },
    "notify.bin_title": {"en": "Sent to Recycle Bin", "ru": "Убрано в корзину"},
    "notify.bin_body": {
        "en": "{name} went to the Recycle Bin (rule: {rule}). Restore it from there if needed.",
        "ru": "{name} убран в корзину (правило: {rule}). При необходимости верни из неё вручную.",
    },
    "notify.bin_fail_title": {"en": "Could not delete", "ru": "Не удалось убрать в корзину"},
    "notify.bin_fail_body": {
        "en": "{name} was not sent to the Recycle Bin. Details are in the log.",
        "ru": "{name} не отправлен в корзину. Подробности в логе.",
    },
    "notify.quarantine_title": {"en": "Moved to quarantine", "ru": "Убрано в карантин"},
    "journal.bin_row": {
        "en": "moved to Recycle Bin: {name}",
        "ru": "убрано в корзину: {name}",
    },
    "journal.bin_undone": {
        "en": "The file is in the Recycle Bin. Restore it from there manually.",
        "ru": "Файл в корзине. Верни его из корзины вручную.",
    },
    # cache cleaning
    "cache.title": {"en": "Cache cleaned", "ru": "Кэш очищен"},
    "cache.body": {
        "en": "Freed {size} ({files} files). Next cleanup in {days} days.",
        "ru": "Освобождено {size} (файлов: {files}). Следующая очистка через {days} дн.",
    },
    # journal: имя файла, убранного с пути при откате
    "journal.old_copy": {"en": "old {stamp}", "ru": "старый {stamp}"},
    "journal.old_copy_n": {"en": "old {stamp}, {i}", "ru": "старый {stamp}, {i}"},
    # naming: поставщик не распознан ({vendor} в имени файла)
    "naming.unknown_vendor": {"en": "unknown", "ru": "неизвестно"},
    # импорт чужой схемы: цель вне домашней папки
    "schema.rejected_target": {
        "en": "Scheme rejected: a target outside the home folder: {path}",
        "ru": "Схема отклонена: цель вне домашней папки: {path}",
    },
    # предпросмотр правила (страница «Правила»)
    "preview.folder": {"en": "Folder:", "ru": "Папка:"},
    "preview.pick": {"en": "Choose a folder to preview", "ru": "Выбери папку для предпросмотра"},
    "preview.show": {"en": "Preview", "ru": "Предпросмотр"},
    "preview.select_rule": {
        "en": "Select a rule in the list first.",
        "ru": "Сначала выбери правило в списке.",
    },
    "preview.folder_missing": {
        "en": "Folder not found: {path}",
        "ru": "Папка не найдена: {path}",
    },
    "preview.running": {"en": "Scanning folder…", "ru": "Сканирую папку…"},
    "preview.result": {
        "en": "{hits} of {total} files will be matched",
        "ru": "Под правило попадут {hits} из {total} файлов",
    },
    "preview.empty": {
        "en": "No files match this rule (checked {total}).",
        "ru": "Под правило не попадёт ни один файл (проверено {total}).",
    },
    "preview.bin": {"en": "Recycle Bin", "ru": "Корзина"},
    "preview.dedupe_bin": {
        "en": "Recycle Bin (duplicate: one copy stays)",
        "ru": "Корзина (дубликат: одна копия остаётся)",
    },
    "preview.truncated": {"en": " (showing first {n})", "ru": " (показаны первые {n})"},
    "preview.ocr_capped": {
        "en": " (text recognition limited to {n} files)",
        "ru": " (распознавание текста ограничено {n} файлами)",
    },
    # предпросмотр сортировки: окно с анимацией файлов по всей схеме
    "flow.open": {"en": "Sorting preview", "ru": "Предпросмотр сортировки"},
    "flow.open_tip": {
        "en": "Shows a window where files from the folder will fly to their destinations.",
        "ru": "Покажет окно: куда полетят файлы из папки по текущей схеме.",
    },
    "flow.title": {"en": "Sorting preview", "ru": "Предпросмотр сортировки"},
    "flow.replay": {"en": "Replay", "ru": "Повторить"},
    "flow.close": {"en": "Close", "ru": "Закрыть"},
    "flow.summary": {
        "en": "{moves} of {total} files will be sorted",
        "ru": "Будут разложены {moves} из {total} файлов",
    },
    "flow.unmatched": {
        "en": ". Files left in place, no rule: {n}",
        "ru": ". Останутся на месте, правила нет: {n}",
    },
    "flow.no_moves": {
        "en": "The rules match no files here (checked {total}).",
        "ru": "Под правила здесь не попадёт ни один файл (проверено {total}).",
    },
    "flow.delay": {"en": "in {days} d.", "ru": "через {days} дн."},
    "flow.ask": {"en": "decision needed", "ru": "нужно решение"},
    "flow.rule": {"en": "rule", "ru": "правило"},
    "flow.nav_tip": {
        "en": "Drag with the mouse or use arrows to pan the diagram, mouse wheel — zoom.",
        "ru": "Двигай карту перетаскиванием мышью или стрелками; колесо мыши — приблизить.",
    },
    "flow.open_fail": {
        "en": "Could not open the sorting preview window. Details are in the log.",
        "ru": "Не удалось открыть окно предпросмотра сортировки. Подробности в логе.",
    },
    # возврат из паузы: разбираем то, что накопилось
    "notify.resume_body": {
        "en": "Sorting {n} files that arrived while paused.",
        "ru": "Разбираю файлы, пришедшие во время паузы: {n}.",
    },
    # узел «Дубликаты»: убрали копию в карантин, оригинал остался
    "notify.dedupe_body": {
        "en": "Duplicate {name} moved to quarantine ({rule}). The other copy stays in place.",
        "ru": "Дубликат {name} убран в карантин ({rule}). Другая копия осталась на месте.",
    },
    # настройки: что теперь делает сортировка после смены dry-run
    "settings.dry_note_on": {
        "en": "Dry-run is ON: files are not moved, only plan notifications are shown.",
        "ru": "Режим «только план» включён: файлы не переносятся, показываются только уведомления.",
    },
    "settings.dry_note_off": {
        "en": "Dry-run is OFF: files are moved automatically.",
        "ru": "Режим «только план» выключен: файлы переносятся автоматически.",
    },
    # main window
    "section.schema": {"en": "Scheme", "ru": "Схема"},
    "section.pending": {"en": "Ask", "ru": "Спросить"},
    "section.journal": {"en": "Journal", "ru": "Журнал"},
    "section.report": {"en": "Report", "ru": "Отчёт"},
    "section.rules": {"en": "Rules", "ru": "Правила"},
    "section.settings": {"en": "Settings", "ru": "Настройки"},
    # настройки: плашка языка, меняется на месте
    "settings.language": {"en": "Language", "ru": "Язык"},
    "settings.language.hint": {
        "en": "Applied right away, no restart needed (the tray menu updates after a restart).",
        "ru": "Применяется сразу, без перезапуска (меню значка в трее обновится после перезапуска).",
    },
    "settings.language_applied": {"en": "Language: {lang}", "ru": "Язык: {lang}"},
    # настройки: автозапуск
    "settings.autostart.on": {"en": "Autostart is currently ON (Windows launch)", "ru": "Автозапуск включён (запуск с Windows)"},
    "settings.autostart.off": {"en": "Autostart is currently OFF", "ru": "Автозапуск выключен"},
    "settings.autostart.fail": {"en": "Could not change autostart — details in the log: {hint}", "ru": "Не удалось изменить автозапуск — подробности в логе: {hint}"},
    "settings.deferred_background": {"en": "Run deferred actions even when the app is closed", "ru": "Выполнять отложенные действия, даже когда приложение закрыто"},
    "settings.deferred_install_fail": {"en": "Failed to install scheduled task.", "ru": "Не удалось установить задачу планировщика."},
    "settings.deferred_remove_fail": {"en": "Failed to remove scheduled task.", "ru": "Не удалось удалить задачу планировщика."},
    # настройки: срок хранения журнала и поиск
    "settings.journal_retention_label": {"en": "Keep journal:", "ru": "Хранить журнал:"},
    "settings.journal_retention_hint": {
        "en": "How many days to keep journal entries. Older entries are deleted automatically (1–3650 days).",
        "ru": "Сколько дней хранить записи журнала. Старые записи удаляются автоматически (от 1 до 3650 дней).",
    },
    "settings.journal_retention_suffix": {"en": " days", "ru": " дн."},
    "settings.journal_search_hint": {"en": "Search by file name", "ru": "Поиск по имени файла"},
    "settings.journal_next": {"en": "Next", "ru": "Далее"},
    "settings.journal_from": {"en": "from", "ru": "с"},
    "settings.journal_to": {"en": "to", "ru": "по"},
    "settings.journal_empty_page": {"en": "No entries on this page.", "ru": "На этой странице записей нет."},
    # дубликаты: окно предпросмотра и подтверждение
    "dup.preview.title": {"en": "Duplicates: preview", "ru": "Дубликаты: предпросмотр"},
    "dup.preview.file": {"en": "File", "ru": "Файл"},
    "dup.preview.size": {"en": "Size", "ru": "Размер"},
    "dup.preview.mtime": {"en": "Modified", "ru": "Дата изменения"},
    "dup.preview.action": {"en": "Action", "ru": "Действие"},
    "dup.preview.action_keep": {"en": "keep", "ru": "оставить"},
    "dup.preview.action_quarantine": {"en": "to quarantine", "ru": "в карантин"},
    "dup.preview.group": {"en": "Group {digest} · {count} file(s)", "ru": "Группа {digest} · файлов: {count}"},
    "dup.preview.summary": {
        "en": "Will be moved to quarantine: {n} files, {size} MB",
        "ru": "Будет перемещено в карантин: {n} файлов, {size} МБ",
    },
    "dup.preview.export": {"en": "Export to CSV", "ru": "Экспорт в CSV"},
    "dup.preview.confirm": {
        "en": "I understand the duplicates will be moved to quarantine",
        "ru": "Понимаю, что дубликаты будут перемещены в карантин",
    },
    "dup.preview.run": {"en": "Run", "ru": "Выполнить"},
    "dup.preview.mb": {"en": "MB", "ru": "МБ"},
    "dup.preview.button": {"en": "Duplicates preview…", "ru": "Дубликаты: предпросмотр…"},
    "dup.preview.button_tip": {
        "en": "Shows duplicate groups before anything is moved",
        "ru": "Показывает группы дубликатов до перемещения",
    },
    "dup.preview.empty": {"en": "No duplicates found.", "ru": "Дубликатов не найдено."},
    "notify.dedupe_confirm_title": {
        "en": "Duplicates: confirmation required",
        "ru": "Дубликаты: нужно подтверждение",
    },
    "notify.dedupe_confirm_body": {
        "en": "“{name}” looks like a copy. Open the duplicates preview and confirm the action.",
        "ru": "«{name}» похож на копию. Открой предпросмотр дубликатов и подтверди действие.",
    },
    "failed.page": {
        "en": "Section \"{name}\" failed to load.\n\n{err}\n\nDetails in the log: {hint}",
        "ru": "Раздел «{name}» не загрузился.\n\n{err}\n\nПодробности в логе: {hint}",
    },
}


def set_language(lang: str) -> None:
    global _LANG
    _LANG = lang if lang in LANGUAGES else "en"


def current_language() -> str:
    return _LANG


def t(key: str, **kwargs) -> str:
    entry = _STRINGS.get(key)
    if entry is not None:
        text = entry.get(_LANG) or entry["en"]
    elif key in RU_EN:
        text = key if _LANG == "ru" else RU_EN[key]
    else:
        return key
    return text.format(**kwargs) if kwargs else text
