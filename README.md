AutoUtil

A Windows tray app that tidies up your Downloads folder. You draw a sorting scheme as a node graph, similar to n8n: a folder, filters, conditions, and targets. The app moves new files according to that scheme, keeps a journal, and can undo everything.

Sorting scheme

The app never deletes files. Every move is recorded in the journal, and undo puts the file back where it was. If another file is already in that spot, it goes to the Windows Recycle Bin instead of being overwritten.

Features

Sorting scheme. A canvas with nodes and connections. Node types: folder, filter, ask, exclude, target. Filters have “yes” and “no” connections. Pan with the middle mouse button, zoom with the scroll wheel.

Filters by extension, keywords (text from PDFs and images via OCR), filename pattern (e.g. invoice_*.pdf), regular expression, size in MB, file age in days, and whether a photo contains GPS data.

Ask queue. Files that aren’t moved automatically. You choose: “Move”, “Move to…”, or “Skip”.

Exclusions. An “Exclude” node with masks (e.g. .tmp, node_modules) stops matching files from being touched.

Rename templates. The “Target” node has a “File name” field, e.g. {date}{name}.{ext} or {year}-{month}{vendor}. Available fields: {date}, {year}, {month}, {name}, {ext}, {vendor}.

Learning. If you manually move files of the same type from the same rule into the same folder three times, the app offers to remember that. Nothing changes automatically until you click “Remember”.

Journal and undo. Every move is recorded. Undo returns the file, and any file in the way goes to the Recycle Bin.

Report. A “Report” tab for a chosen period: number of files moved, total size, and a breakdown by rule, folder, and type. Export to Markdown.

Import and export of schemes as .json. You can share a scheme with someone else.

Plan-only mode. The app shows what it would move without touching anything. Enabled by default.

Requirements
Windows 10 or 11
Python 3.12 or 3.13 (only when running from source)
About 1 GB of free disk space for dependencies (PySide6, OCR models)

The ready-made AutoUtil.exe does not require Python.

Installing from source
powershell
git clone https://github.com/h1ilep0pysk-hue/AutoUtil.git
cd AutoUtil
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

If Activate.ps1 fails with an execution policy error, run this once in the same window:

powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Running
powershell
python main.py

On first launch, a setup wizard asks for the folder to watch and whether to start in plan-only mode. After that, the window opens and the icon appears in the tray.

Tray: double-click opens the window. Right-click opens the menu: pause for one hour, Do Not Disturb, journal, settings, exit.

Using the scheme
Click + Folder, select the node, and enter the full path in the Folder field, e.g. C:\Users\you\Downloads.
Add a filter, e.g. “Video” with extensions mp4, mkv.
Add a target, e.g. “Video” with folder Media/Video/{year}.
Connect the nodes: select the source, click Connect, then click the next node. For the “no” branch, select the filter, click Connect “no”, then click the target. Files that don’t pass the filter go there.
Click Run scheme. The app saves the rules, starts watching the folder, and moves new files.

New features can be found by name in the right panel. Hover over a feature to see a tooltip, or drag it onto the canvas.

The scheme is saved to %LOCALAPPDATA%\AutoUtil\schema.json. Use the buttons in the header to export and import.

Example: receipts and other PDFs

Downloads folder → Filter "PDF" → Filter "Total" → Target "Receipts/{year}"
                                              └ no → Target "Documents/{year}"

PDFs containing the word “total” go to “Receipts”. Other PDFs go to “Documents”.

Important: folder watching

The app reacts to new files. Files already in the folder before the scheme started are not moved. Watching is not recursive, so subfolders are not tracked.

Known limitation: while paused or in Do Not Disturb mode, new files are not processed and are lost until the next start. A fix is in progress.

Undo

Open the Journal tab or the tray menu item. Select an entry and click Restore selected. If the original location already has a file, it is sent to the Recycle Bin. (This requires the send2trash package. Without it, the existing file is renamed to “… (old date)”.)

Project structure
Path	Contents
main.py	Entry point
core/	Config, journal, queue, scheme, report, modes, events
modules/organizer/	Folder watching, file analysis, rules, moving, learning
modules/organizer/ocr.py	OCR for text in images and PDFs
ui/	Tray, wizard, journal, main window
ui/explorer/	Main window: scheme, ask queue, report, journal, rules, settings
win/	Windows integration: autostart, folders, notifications
tests/	Tests
tools/make_icons.py	Tray icon generator
Tests
powershell
python -m pytest -q
Building the exe
powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name AutoUtil --icon ui\assets\autoutil.ico --add-data "ui\assets;ui\assets" main.py

The result is dist\AutoUtil.exe. OCR models are pulled from the rapidocr package. If OCR doesn’t work in the built version, add --collect-data rapidocr.AutoUtil
![Uploading image.png…]()

Утилита для Windows, которая живёт в системном трее и наводит порядок в папке «Загрузки». Вы рисуете схему сортировки, как в n8n: папка, фильтры, условия, цель. Программа по этой схеме переносит новые файлы, ведёт журнал и умеет всё откатить.

Схема сортировки

Программа никогда не удаляет файлы. Перенос всегда записывается в журнал, а откат возвращает файл на место. Если на месте уже лежит другой файл, он уходит в корзину Windows, а не затирается.

Возможности
Схема сортировки. Холст с узлами и связями. Узлы: папка, фильтр, спросить, исключить, цель. Связь «да» и связь «нет» от фильтра. Панорамирование средней кнопкой мыши, масштаб колесом.
Фильтры по расширению, ключевым словам (текст из PDF и картинок через OCR), маске имени (invoice_*.pdf), регулярному выражению, размеру в МБ, возрасту файла в днях, наличию GPS в фото.
Очередь «Спросить». Файлы, которые не переносятся сами. Ты решаешь: «Перенести», «Перенести в…» или «Пропустить».
Исключения. Узел «Исключить» с масками (*.tmp, node_modules) не даёт трогать подходящие файлы.
Переименование по шаблону. В узле «Цель» поле «Имя файла»: {date}_{name}.{ext}, {year}-{month}_{vendor}. Доступные поля: {date}, {year}, {month}, {name}, {ext}, {vendor}.
Обучение. Если ты трижды вручную кладёшь файлы одного типа от одного правила в одну папку, программа предлагает запомнить. Автоматически ничего не меняется, пока ты не нажмёшь «Запомнить».
Журнал и откат. Каждый перенос записан. Откат возвращает файл, а мешающий файл уходит в корзину.
Отчёт. Вкладка «Отчёт» за выбранный период: сколько файлов перенесено, общий размер, разбивка по правилам, папкам и типам. Экспорт в Markdown.
Импорт и экспорт схем в .json. Схему можно передать другому человеку.
Режим «только план». Программа покажет, что бы переместила, и ничего не тронет. Включён по умолчанию.
Требования
Windows 10 или 11
Python 3.12 или 3.13 (для запуска из исходников)
Около 1 ГБ свободного места для зависимостей (PySide6, модели OCR)

Готовый AutoUtil.exe не требует Python.

Установка из исходников
powershell
git clone https://github.com/h1ilep0pysk-hue/AutoUtil.git
cd AutoUtil
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

Если Activate.ps1 не запускается с ошибкой о политике выполнения, выполни один раз в этом окне:

powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Запуск
powershell
python main.py

При первом запуске откроется мастер: папка для отслеживания, и режим «только план». После него окно откроется сразу, иконка появится в трее.

Работа с трея: двойной клик открывает окно, правый клик открывает меню (пауза на час, «не беспокоить», журнал, настройки, выход).

Как пользоваться схемой
Нажми «+ Папка», выбери узел и укажи полный путь в поле «Папка», например C:\Users\you\Downloads.
Добавь фильтр, например «Видео» с расширениями mp4, mkv.
Добавь цель, например «Видео» с папкой Медиа/Видео/{year}.
Соедини узлы: выдели источник, нажми «Связать», кликни следующий узел.
Для ветки «нет»: выдели фильтр, нажми «Связать «нет»», кликни цель. Сюда попадут файлы, которые не прошли фильтр.
Нажми «Запустить схему». Программа сохранит правила, начнёт следить за папкой и переносить новые файлы.

Новые функции можно искать по названию в правой панели. Наведи курсор на функцию, чтобы увидеть подсказку, или перетащи её на холст.

Схема сохраняется в %LOCALAPPDATA%\AutoUtil\schema.json. Экспорт и импорт через кнопки в шапке.

Пример: чеки и остальное PDF
Папка «Загрузки» → Фильтр «PDF» → Фильтр «Итого» → Цель «Чеки/{year}»
                                       └ нет → Цель «Документы/{year}»

Файлы PDF со словом «итого» уйдут в «Чеки», остальные PDF в «Документы».

Важно про наблюдение за папками
Программа реагирует на новые файлы. Файлы, которые уже лежали в папке до запуска схемы, сами не переносятся.
Наблюдение не рекурсивное: подпапки не отслеживаются.
При паузе или режиме «не беспокоить» новые файлы не обрабатываются, и сейчас они теряются до следующего запуска. Это известное ограничение.
Откат

Вкладка «Журнал» или пункт «Журнал» в трее. Выбери запись и нажми «Вернуть выбранное». Если на исходном месте уже есть файл, он отправляется в корзину (нужен пакет send2trash, без него переименовывается в «… (старый дата)»).

Структура проекта
main.py                 точка входа
core/                   конфиг, журнал, очередь, схема, отчёт, режимы, события
modules/organizer/      наблюдение за папками, анализ файлов, правила, перенос, обучение
modules/organizer/ocr.py  OCR для текста в картинках и PDF
ui/                     трей, мастер, журнал, главное окно
ui/explorer/            главное окно: схема, спросить, отчёт, журнал, правила, настройки
win/                    работа с Windows: автозапуск, папки, уведомления
tests/                  тесты
tools/make_icons.py     генерация иконок трея
Тесты
powershell
python -m pytest -q
Сборка exe
powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name AutoUtil --icon ui\assets\autoutil.ico --add-data "ui\assets;ui\assets" main.py

Результат: dist\AutoUtil.exe. Модели OCR подтягиваются из пакета rapidocr. Если OCR не работает в собранной версии, добавь --collect-data rapidocr.
