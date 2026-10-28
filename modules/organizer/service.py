import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.config import OrganizerSettings
from core.deferred import DeferredStore
from core.events import FileMoved, FileTrashed, ModeChanged, PendingAdded, PlanReady, bus
from core.i18n import t
from core.journal import Journal
from core.notifier import Notice, Notifier
from core.pending import PendingStore
from core.state import Mode, state
from modules.organizer import cacheclean
from modules.organizer.actions import apply_move, prepare_target, recycle
from modules.organizer.analyzer import analyze
from modules.organizer.dedupe import find_duplicate
from modules.organizer.dedupe_groups import group_duplicates
from modules.organizer.exclusions import is_excluded
from modules.organizer.learning import Learned
from modules.organizer.planner import PlannedMove, plan
from modules.organizer.quarantine import move_to_quarantine, purge_quarantine
from modules.organizer.rules import Rule, age_days
from modules.organizer.rules_store import load_rules
from modules.organizer.watcher import FolderWatcher, wait_stable
from win.paths import documents_dir

log = logging.getLogger("autoutil.organizer")

CHECK_INTERVAL_SECONDS = 900  # планировщик просыпается раз в 15 минут
RETRY_INTERVAL_SECONDS = 30.0  # как часто перекидываются «неустоявшиеся» файлы
JOURNAL_PURGE_INTERVAL_SECONDS = 24 * 60 * 60  # журнал чистим не чаще раза в сутки


def _parse_meta_ts(value: str) -> datetime | None:
    """Разбор отметки времени из meta (ISO, возможно без зоны)."""
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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
        # Файлы, увиденные в паузу/DND. Watchdog событие приходит единожды:
        # без этого буфера файл навсегда выпадал из сортировки. FIX
        self._paused_paths: set[str] = set()
        self._paused_lock = threading.Lock()
        # Файлы, которым не удалось дождаться стабильности / прочитать их:
        # событие из watchdog одноразовое, и из-за одного неудачного момента
        # файл навсегда пропадал из сортировки. Теперь это очередь в фоне. FIX
        self._retry: set[str] = set()
        self._retry_lock = threading.Lock()
        self._retry_stop = threading.Event()
        self._retry_thread: threading.Thread | None = None
        # Подписка один раз, в конструкторе: restart() не должен плодить дубли.
        bus.subscribe(ModeChanged, self._on_mode_changed)
        # Чистка журнала по сроку хранения: при старте и далее раз в сутки.
        self._purge_journal()

    def start(self) -> None:
        self.watcher = FolderWatcher(self.settings.watch_dirs, self.handle)
        self.watcher.start()
        self._start_scheduler()
        self._start_retry()
        self._initial_scan()

    def stop(self) -> None:
        self._sched_stop.set()
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        if self._sched_thread is not None:
            self._sched_thread.join(timeout=5)
            self._sched_thread = None
        self._stop_retry()

    def restart(self) -> None:
        self.stop()
        if self.settings.watch_dirs:
            self.start()

    # --- приём файла -----------------------------------------------------

    def handle(self, path: Path) -> None:
        if not state.is_active():
            self._stash_paused(path)
            return
        try:
            self._handle(path)
        except Exception:
            log.exception("Ошибка обработки файла %s", path)
            self.notifier.notify(Notice(
                title=t("notify.title"),
                body=t("notify.failure", name=path.name),
            ))

    def _stash_paused(self, path: Path) -> None:
        """Файлы, пришедшие в паузу или «Не беспокоить», копятся и разбираются
        при возврате в активный режим, как будто только что появились. FIX"""
        with self._paused_lock:
            self._paused_paths.add(str(path))

    # --- очередь повторных попыток -----------------------------------------

    def _schedule_retry(self, path: Path) -> bool:
        """Кладёт файл в очередь попыток раз в 30 с: событие из watchdog
        одноразовое, и без этого залоченный в тот момент файл терялся
        из сортировки навсегда. True — файл добавлен впервые."""
        with self._retry_lock:
            key = str(path)
            if key in self._retry:
                return False
            self._retry.add(key)
            return True

    def _start_retry(self) -> None:
        self._retry_stop.clear()
        self._retry_thread = threading.Thread(
            target=self._retry_loop, daemon=True, name="autoutil-retry",
        )
        self._retry_thread.start()

    def _stop_retry(self) -> None:
        self._retry_stop.set()
        if self._retry_thread is not None:
            self._retry_thread.join(timeout=5)
            self._retry_thread = None

    def _retry_loop(self) -> None:
        while not self._retry_stop.wait(RETRY_INTERVAL_SECONDS):
            self._safe_pump_retries()

    def _safe_pump_retries(self) -> None:
        try:
            self._pump_retries()
        except Exception:
            log.exception("Ошибка прохода по неустоявшимся файлам")

    def _pump_retries(self) -> None:
        with self._retry_lock:
            paths, self._retry = self._retry, set()
        for raw in sorted(paths):
            p = Path(raw)
            if not p.exists():
                continue  # файл исчез — проверять больше нечего
            log.info("Повторная попытка: %s", raw)
            self.handle(p)

    def _on_mode_changed(self, event: ModeChanged) -> None:
        if event.mode != Mode.ACTIVE.value:
            return
        with self._paused_lock:
            saved, self._paused_paths = self._paused_paths, set()
        paths = [Path(p) for p in sorted(saved)]
        if not paths:
            return
        log.info("Возврат в активный режим: разбираю файлы, накопившиеся за паузу (%d)", len(paths))
        self.notifier.notify(Notice(
            title=t("notify.title"),
            body=t("notify.resume_body", n=len(paths)),
        ))
        threading.Thread(
            target=self._process_paused, args=(paths,), daemon=True, name="autoutil-resume",
        ).start()

    def _process_paused(self, paths: list[Path]) -> None:
        for p in paths:
            self.handle(p)

    def _handle(self, path: Path) -> None:
        if not state.is_active():
            self._stash_paused(path)  # FIX: файл мог прийти во время резкой смены режима
            return
        if is_excluded(path, self.settings.excluded_dirs):
            return
        if not wait_stable(path):
            # Файл исчез, залочен антивирусом или ещё пишется: событие
            # одноразовое, поэтому не теряем файл, а идём в очередь
            # повторных попыток. FIX
            self._schedule_retry(path)
            return
        rules = [r for r in load_rules() if r.enabled]
        need_text = any(r.needs_text for r in rules)
        try:
            feats = analyze(path, need_text=need_text)
        except OSError:
            # Файл в этот миг недоступен (зафиксирован фоновым процессом) —
            # временный сбой, не «правило не подходит»: повторяем позже молча. FIX
            self._schedule_retry(path)
            return
        move = plan(feats, rules, self.base, self.learned)
        if move is None:
            return
        bus.publish(PlanReady(src=str(move.src), dst=str(move.dst), rule=move.rule))

        # «Через N дней»: файл должен ещё полежать — откладываем действие.
        if move.delay_days and age_days(path) < move.delay_days:
            self._schedule(move)
            return

        self._execute(move, rules)

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

    def _execute(self, move: PlannedMove, rules: list[Rule] | None = None) -> None:
        if move.ask:
            # Повторное событие на тот же файл не должно плодить записи:
            # файл либо будет перенесён, либо остановлен до добавления. FIX
            if not any(i.src == str(move.src) for i in self.pending.all_items()):
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
            # Узел «Дубликаты» уводит копии в карантин (не в корзину):
            # файл можно вернуть, ничего не удаляется безвозвратно.
            if move.dedupe:
                self._quarantine_duplicate(move, rules)
                return
            self._to_bin(move.src, move.rule)
            return

        self._move_now(move.src, move.dst, move.rule)

    # --- исполнение ------------------------------------------------------

    def _quarantine_duplicate(self, move: PlannedMove, rules: list[Rule] | None) -> None:
        """Дубликат уходит в карантин; keep и одиночные файлы не трогаем.

        Действие выполняется над всей группой, а не только над файлом-
        триггером: копия может прийти позже и оказаться самым свежим файлом
        группы (тогда keep — это она, а уходить в карантин должен оригинал).
        """
        rule_obj = next((r for r in (rules or []) if r.name == move.rule), None)
        if rule_obj is None:
            log.warning("dedupe: rule %r not found, file kept: %s", move.rule, move.src)
            return
        groups = group_duplicates(move.src.parent, rule_obj)
        group = next((g for g in groups if move.src == g.keep or move.src in g.remove), None)
        if group is None:
            log.info("dedupe: %s is not part of a duplicate group, left in place", move.src)
            return
        if not self.settings.duplicates_confirmed:
            log.info("dedupe: confirmation required, nothing moved: %s", move.src)
            self.notifier.notify(Notice(
                title=t("notify.dedupe_confirm_title"),
                body=t("notify.dedupe_confirm_body", name=move.src.name, rule=move.rule),
            ))
            return
        pairs: list[tuple[Path, Path]] = []
        moved = move_to_quarantine(group, self.journal, move.rule, moved_pairs=pairs)
        if not moved:
            log.warning("dedupe: nothing moved to quarantine for %s", move.src)
            return
        for src, target in pairs:
            bus.publish(FileMoved(src=str(src), dst=str(target), rule=move.rule))
            self.notifier.notify(Notice(
                title=t("notify.quarantine_title"),
                body=t("notify.dedupe_body", name=target.name, rule=move.rule),
            ))
        log.info(
            "dedupe: %d file(s) moved to quarantine, kept %s (rule=%s)",
            len(moved), group.keep.name, move.rule,
        )

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
            if src.exists():  # FIX: залоченный на миг файл не должен теряться
                self._schedule_retry(src)
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
            # Повторяем по очереди, чтобы не терять файл при волне блокировок
            # антивирусом/индексатором; уведомляем только при первой неудаче.
            if self._schedule_retry(src):
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
        self._purge_journal()  # не чаще раза в сутки, см. last_journal_purge
        self._purge_quarantine()  # не чаще раза в сутки, см. last_quarantine_purge
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

    def _purge_journal(self) -> None:
        """Удаляет записи журнала старше journal_retention_days.

        Только статусы done/undone (pending не трогаем). Не чаще раза в сутки:
        отметка последней очистки хранится в meta под ключом last_journal_purge.
        """
        try:
            db = self.journal.db
            last_raw = db.get_meta("last_journal_purge")
            if last_raw:
                last = _parse_meta_ts(last_raw)
                if last is not None:
                    age = datetime.now(timezone.utc) - last
                    if age < timedelta(seconds=JOURNAL_PURGE_INTERVAL_SECONDS):
                        return
            days = self.settings.journal_retention_days
            removed = db.purge_older_than(days)
            db.set_meta("last_journal_purge", datetime.now(timezone.utc).isoformat())
            log.info("journal purge: removed=%d retention_days=%d", removed, days)
        except Exception:
            log.exception("Ошибка очистки журнала")

    def _purge_quarantine(self) -> None:
        """Удаляет папки карантина старше 30 дней — не чаще раза в сутки."""
        try:
            db = self.journal.db
            last_raw = db.get_meta("last_quarantine_purge")
            if last_raw:
                last = _parse_meta_ts(last_raw)
                if last is not None:
                    age = datetime.now(timezone.utc) - last
                    if age < timedelta(seconds=JOURNAL_PURGE_INTERVAL_SECONDS):
                        return
            removed = purge_quarantine()
            db.set_meta("last_quarantine_purge", datetime.now(timezone.utc).isoformat())
            log.info("quarantine purge: removed=%d", removed)
        except Exception:
            log.exception("Ошибка очистки карантина")

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
