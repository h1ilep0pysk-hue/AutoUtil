import logging
import threading
from pathlib import Path

from core.config import OrganizerSettings
from core.deferred import DeferredStore
from core.events import FileMoved, FileTrashed, PendingAdded, PlanReady, bus
from core.i18n import t
from core.journal import Journal
from core.notifier import Notice, Notifier
from core.pending import PendingStore
from core.state import state
from modules.organizer import cacheclean
from modules.organizer.actions import apply_move, prepare_target, recycle
from modules.organizer.analyzer import analyze
from modules.organizer.dedupe import find_duplicate
from modules.organizer.exclusions import is_excluded
from modules.organizer.learning import Learned
from modules.organizer.planner import PlannedMove, plan
from modules.organizer.rules import age_days
from modules.organizer.rules_store import load_rules
from modules.organizer.watcher import FolderWatcher, wait_stable
from win.paths import documents_dir

log = logging.getLogger("autoutil.organizer")

CHECK_INTERVAL_SECONDS = 900  # планировщик просыпается раз в 15 минут


class OrganizerService:
    def __init__(self, settings: OrganizerSettings, journal: Journal, notifier: Notifier) -> None:
        self.settings = settings
        self.journal = journal
        self.notifier = notifier
        self.learned = Learned()
        self.pending = PendingStore()
        self.deferred = DeferredStore()
        self.base = documents_dir().parent
        self.watcher: FolderWatcher | None = None
        self._sched_stop = threading.Event()
        self._sched_thread: threading.Thread | None = None

    def start(self) -> None:
        self.watcher = FolderWatcher(self.settings.watch_dirs, self.handle)
        self.watcher.start()
        self._start_scheduler()
        self._initial_scan()

    def stop(self) -> None:
        self._sched_stop.set()
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        if self._sched_thread is not None:
            self._sched_thread.join(timeout=5)
            self._sched_thread = None

    def restart(self) -> None:
        self.stop()
        if self.settings.watch_dirs:
            self.start()

    # --- приём файла -----------------------------------------------------

    def handle(self, path: Path) -> None:
        try:
            self._handle(path)
        except Exception:
            log.exception("Ошибка обработки файла %s", path)
            self.notifier.notify(Notice(
                title=t("notify.title"),
                body=t("notify.failure", name=path.name),
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

        # «Через N дней»: файл должен ещё полежать — откладываем действие.
        if move.delay_days and age_days(path) < move.delay_days:
            self._schedule(move)
            return

        self._execute(move)

    def _schedule(self, move: PlannedMove) -> None:
        """Откладывает действие на срок из узла «Через N дней»."""
        if self.deferred.get_for_src(str(move.src)) is not None:
            return  # уже отложен
        self.deferred.add(
            str(move.src), str(move.dst), move.rule,
            days=move.delay_days, ask=move.ask, bin=move.to_bin,
        )
        self.notifier.notify(Notice(
            title=t("notify.deferred_title"),
            body=t("notify.deferred_body", name=move.src.name, days=move.delay_days, rule=move.rule),
        ))

    def _execute(self, move: PlannedMove) -> None:
        if move.ask:
            self.pending.add(str(move.src), str(move.dst), move.rule, bin=move.to_bin)
            bus.publish(PendingAdded(src=str(move.src), rule=move.rule))
            self.notifier.notify(Notice(
                title=t("notify.ask_title"),
                body=t("notify.ask_body", name=move.src.name),
            ))
            return

        if self.settings.dry_run:
            if move.to_bin:
                self.notifier.notify(Notice(
                    title=t("notify.plan_bin_title"),
                    body=t("notify.plan_bin_body", name=move.src.name, rule=move.rule),
                ))
            else:
                self.notifier.notify(Notice(
                    title=t("notify.plan_title"),
                    body=t("notify.plan_move_body", name=move.src.name,
                           folder=move.dst.parent.name, rule=move.rule),
                ))
            return

        if move.to_bin:
            self._to_bin(move.src, move.rule)
            return

        self._move_now(move.src, move.dst, move.rule)

    # --- исполнение ------------------------------------------------------

    def _to_bin(self, src: Path, rule: str) -> None:
        if not recycle(src):
            log.warning("Не удалось отправить в корзину: %s", src)
            self.notifier.notify(Notice(
                title=t("notify.bin_fail_title"),
                body=t("notify.bin_fail_body", name=src.name),
            ))
            return
        try:
            self.journal.record_bin(src, rule)
        except Exception:
            log.exception("Не удалось записать в журнал отправку в корзину: %s", src)
        bus.publish(FileTrashed(src=str(src), rule=rule))
        self.notifier.notify(Notice(
            title=t("notify.bin_title"),
            body=t("notify.bin_body", name=src.name, rule=rule),
        ))
        log.info("Убрано в корзину: %s (правило: %s)", src, rule)

    def _move_now(self, src: Path, dst: Path, rule: str) -> None:
        try:
            size = src.stat().st_size
        except OSError:
            return
        dup = find_duplicate(src, dst.parent, size)
        if dup is not None:
            self.notifier.notify(Notice(
                title=t("notify.dup_title"),
                body=t("notify.dup_body", name=src.name, folder=dst.parent.name),
            ))
            return
        final_dst = prepare_target(dst)
        try:
            apply_move(src, final_dst)  # FIX: перенос первым
        except OSError:
            log.exception("Не удалось перенести %s", src)
            self.notifier.notify(Notice(
                title=t("notify.title"),
                body=t("notify.failure", name=src.name),
            ))
            return
        entry = None
        try:
            entry = self.journal.record_move(src, final_dst, rule)  # FIX: запись после успеха
        except Exception:
            log.exception("Не удалось записать перенос в журнал: %s", src)
        bus.publish(FileMoved(src=str(src), dst=str(final_dst), rule=rule))
        self.notifier.notify(Notice(
            title=t("notify.moved_title"),
            body=t("notify.moved_body", name=final_dst.name, folder=final_dst.parent.name),
        ))
        if entry is not None:
            log.info("Перенос записан в журнал: %s", entry.id)

    # --- планировщик -----------------------------------------------------

    def _start_scheduler(self) -> None:
        self._sched_stop.clear()
        self._sched_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True, name="autoutil-scheduler",
        )
        self._sched_thread.start()

    def _scheduler_loop(self) -> None:
        first = True
        ticks = 0
        while True:
            delay = 2.0 if first else CHECK_INTERVAL_SECONDS
            first = False
            if self._sched_stop.wait(delay):
                return
            self._safe_check_due()
            ticks += 1
            # Очистку кэша запускаем со второй проверки (~15 мин после старта),
            # чтобы она не мешала стартовому скану папок.
            if ticks >= 2:
                self._safe_cache_clean()

    def _safe_check_due(self) -> None:
        try:
            self._check_due()
        except Exception:
            log.exception("Ошибка проверки отложенных файлов")

    def _check_due(self) -> None:
        """Запускает отложенные действия, чей срок наступил."""
        for item in self.deferred.all_items():
            src = Path(item.src)
            if not src.exists():
                self.deferred.remove(item.id)
                continue
            if age_days(src) < item.days:
                continue
            self.deferred.remove(item.id)
            if item.ask:
                self.pending.add(item.src, item.dst, item.rule, bin=item.bin)
                bus.publish(PendingAdded(src=item.src, rule=item.rule))
                self.notifier.notify(Notice(
                    title=t("notify.ask_title"),
                    body=t("notify.ask_body", name=src.name),
                ))
            elif item.bin:
                self._to_bin(src, item.rule)
            else:
                self._move_now(src, Path(item.dst), item.rule)

    def _safe_cache_clean(self) -> None:
        """Раз в cache_clean_days чистит безопасные кэши и сообщает об итоге."""
        if not self.settings.cache_clean:
            return
        try:
            stats = cacheclean.run_clean(self.settings.cache_clean_days)
        except Exception:
            log.exception("Ошибка очистки кэша")
            return
        if stats and stats.bytes >= 1024 * 1024:
            self.notifier.notify(Notice(
                title=t("cache.title"),
                body=t(
                    "cache.body",
                    size=cacheclean.human_bytes(stats.bytes),
                    files=stats.files,
                    days=self.settings.cache_clean_days,
                ),
            ))

    # --- стартовый скан --------------------------------------------------

    def _initial_scan(self) -> None:
        """Разовый проход по наблюдаемым папкам: сортирует то, что появилось,
        пока приложение не работало. В фоне, чтобы не тормозить запуск."""

        def scan() -> None:
            for d in list(self.settings.watch_dirs):
                root = Path(d)
                if not root.is_dir():
                    continue
                try:
                    entries = list(root.iterdir())
                except OSError:
                    continue
                for p in entries:
                    if p.is_file():
                        self.handle(p)
            log.info("Стартовый скан завершён")

        threading.Thread(target=scan, daemon=True, name="autoutil-initial-scan").start()
