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
        if size > 0 and size == last:
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


class _Handler(FileSystemEventHandler):
    def __init__(self, on_file: Callable[[Path], None]) -> None:
        self.on_file = on_file

    def on_created(self, event):
        if not event.is_directory:
            self._dispatch(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            self._dispatch(Path(event.dest_path))

    def _dispatch(self, path: Path) -> None:
        if path.suffix.lower() in IGNORED_SUFFIXES:
            return
        threading.Thread(target=self.on_file, args=(path,), daemon=True).start()


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
