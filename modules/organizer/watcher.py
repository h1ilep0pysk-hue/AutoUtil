import logging
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from modules.organizer.exclusions import IGNORED_SUFFIXES

log = logging.getLogger("autoutil.watcher")


def wait_stable(path: Path, polls: int = 3, interval: float = 0.5, timeout: float = 600) -> bool:
    """Ждёт, пока размер файла перестанет меняться и файл можно открыть на чтение."""
    last = -1
    stable = 0
    waited = 0.0
    while waited < timeout:
        if not path.exists():
            return False
        size = path.stat().st_size
        if size == last:  # FIX: пустые файлы тоже считаем устоявшимися (раньше ждали весь таймаут)
            stable += 1
        else:
            stable = 0
        last = size
        if stable >= polls:
            try:
                with path.open("rb"):
                    return True
            except OSError:
                pass
        time.sleep(interval)
        waited += interval
    return False


_DEDUPE_WINDOW = 10.0  # сек: один и тот же путь не обрабатываем чаще


class _Handler(FileSystemEventHandler):
    def __init__(self, on_file: Callable[[Path], None]) -> None:
        self.on_file = on_file
        self._recent: dict[Path, float] = {}
        self._lock = threading.Lock()

    def on_created(self, event):
        if not event.is_directory:
            self._dispatch(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            self._dispatch(Path(event.dest_path))

    def _dispatch(self, path: Path) -> None:
        if path.suffix.lower() in IGNORED_SUFFIXES:
            return
        # FIX: on_created и on_moved могут прилететь на один и тот же файл
        # (браузеры создают файл и сразу переименовывают) — дедуп на окно.
        now = time.monotonic()
        with self._lock:
            last = self._recent.get(path)
            if last is not None and now - last < _DEDUPE_WINDOW:
                return
            self._recent[path] = now
            if len(self._recent) > 4096:
                cutoff = now - _DEDUPE_WINDOW
                self._recent = {p: t for p, t in self._recent.items() if t >= cutoff}
        threading.Thread(target=self._run, args=(path,), daemon=True).start()

    def _run(self, path: Path) -> None:
        existed = path.exists()
        try:
            self.on_file(path)
        finally:
            # «created → moved» для одного файла допускаются один раз в окно,
            # НО когда файл уехал со своего места (отсортирован или возвращён
            # из отката), тот же путь — снова честное новое событие. FIX: иначе
            # докачка/пересоздание файла с тем же именем внутри 10 с
            # терялось навсегда.
            with self._lock:
                if existed and not path.exists():
                    self._recent.pop(path, None)


class FolderWatcher:
    def __init__(self, dirs: list[str], on_file: Callable[[Path], None]) -> None:
        self.observer = Observer()
        handler = _Handler(on_file)
        for d in dirs:
            p = Path(d)
            if p.is_dir():
                self.observer.schedule(handler, str(p), recursive=False)
                log.info("Слежу за папкой: %s", p)
            else:
                log.warning("Папка не найдена: %s", p)

    def start(self) -> None:
        self.observer.start()

    def stop(self) -> None:
        self.observer.stop()
        self.observer.join(timeout=5)
