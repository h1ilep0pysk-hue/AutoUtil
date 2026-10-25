import logging
from pathlib import Path

from core.config import OrganizerSettings
from core.events import FileMoved, PendingAdded, PlanReady, bus
from core.journal import Journal
from core.notifier import Notice, Notifier
from core.pending import PendingStore
from core.state import state
from modules.organizer.actions import apply_move, prepare_target
from modules.organizer.analyzer import analyze
from modules.organizer.dedupe import find_duplicate
from modules.organizer.exclusions import is_excluded
from modules.organizer.learning import Learned
from modules.organizer.planner import plan
from modules.organizer.rules_store import load_rules
from modules.organizer.watcher import FolderWatcher, wait_stable
from win.paths import documents_dir

log = logging.getLogger("autoutil.organizer")


class OrganizerService:
    def __init__(self, settings: OrganizerSettings, journal: Journal, notifier: Notifier) -> None:
        self.settings = settings
        self.journal = journal
        self.notifier = notifier
        self.learned = Learned()
        self.pending = PendingStore()
        self.base = documents_dir().parent
        self.watcher: FolderWatcher | None = None

    def start(self) -> None:
        self.watcher = FolderWatcher(self.settings.watch_dirs, self.handle)
        self.watcher.start()

    def stop(self) -> None:
        if self.watcher:
            self.watcher.stop()
            self.watcher = None

    def restart(self) -> None:
        self.stop()
        if self.settings.watch_dirs:
            self.start()

    def handle(self, path: Path) -> None:
        try:
            self._handle(path)
        except Exception:
            log.exception("Ошибка обработки файла %s", path)
            self.notifier.notify(Notice(
                title="AutoUtil",
                body=f"Не удалось обработать файл {path.name}. Подробности в логе.",
            ))

    def _handle(self, path: Path) -> None:
        if not state.is_active():
            return
        if is_excluded(path, self.settings.excluded_dirs):
            return
        if not wait_stable(path):
            return
        rules = [r for r in load_rules() if r.enabled]
        need_text = any(r.needs_text for r in rules)
        feats = analyze(path, need_text=need_text)
        move = plan(feats, rules, self.base, self.learned)
        if move is None:
            return
        bus.publish(PlanReady(src=str(move.src), dst=str(move.dst), rule=move.rule))

        if move.ask:
            self.pending.add(str(move.src), str(move.dst), move.rule)
            bus.publish(PendingAdded(src=str(move.src), rule=move.rule))
            self.notifier.notify(Notice(
                title="Нужно решение",
                body=f"{move.src.name}: откройте раздел «Спросить» в AutoUtil.",
            ))
            return

        if self.settings.dry_run:
            self.notifier.notify(Notice(
                title="План: перенос",
                body=f"{move.src.name} → {move.dst.parent.name} (правило: {move.rule})",
            ))
            return

        dup = find_duplicate(move.src, move.dst.parent, feats.size)
        if dup is not None:
            self.notifier.notify(Notice(
                title="Дубликат пропущен",
                body=f"{move.src.name} уже есть в {move.dst.parent.name}",
            ))
            return

        final_dst = prepare_target(move.dst)
        entry = self.journal.record_move(move.src, final_dst, move.rule)
        apply_move(move.src, final_dst)
        bus.publish(FileMoved(src=str(move.src), dst=str(final_dst), rule=move.rule))
        self.notifier.notify(Notice(
            title="Файл перенесён",
            body=f"{final_dst.name} → {final_dst.parent.name}. Откат: журнал в трее.",
        ))
        log.info("Перенос записан в журнал: %s", entry.id)
