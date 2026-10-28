"""Периодическая очистка безопасных кэшей (раз в N дней).

Удаляется СОДЕРЖИМОЕ кэш-папок — сами папки остаются на месте.
Занятые системой файлы пропускаются без ошибок (браузер открыт —
его занятые файлы подождут следующей чистки).

Не трогаем принципиально: Prefetch (влияет на скорость запуска программ),
Docker (образы и контейнеры), CapCut (черновики проектов), профили
браузеров (пароли, история, cookie) — только папки вида Cache.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from platformdirs import user_data_dir

log = logging.getLogger("autoutil.cacheclean")

STATE_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "cache_clean.json"

# Имена внутри временной папки Windows, которые нельзя трогать
# (opencode — рабочие файлы ассистента).
TEMP_PROTECT = frozenset({"opencode"})

# Кэш-подпапки внутри профиля браузера на движке Chromium.
_BROWSER_SUBDIRS = (
    "Cache", "Code Cache", "GPUCache", "ShaderCache",
    "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
)


@dataclass(frozen=True)
class CacheTarget:
    path: Path
    title: str
    min_age_days: int = 0
    protect: frozenset[str] = frozenset()


@dataclass
class CleanStats:
    files: int = 0
    bytes: int = 0
    failed: int = 0
    places: list[tuple[str, int, int]] = field(default_factory=list)  # (title, files, bytes)


def human_bytes(n: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if abs(n) < 1024:
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def _home() -> Path:
    return Path.home()


def _local() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (_home() / "AppData" / "Local"))


def _roaming() -> Path:
    return Path(os.environ.get("APPDATA") or (_home() / "AppData" / "Roaming"))


def build_targets() -> list[CacheTarget]:
    """Список кэш-папок для очистки (только существующие)."""
    local, roam = _local(), _roaming()
    out: list[CacheTarget] = []

    def add(p: Path, title: str, age: int = 0,
            protect: frozenset[str] = frozenset()) -> None:
        if p.is_dir():
            out.append(CacheTarget(p, title, age, protect))

    # Временные файлы Windows: только старше суток, служебное не трогаем.
    add(local / "Temp", "Временные файлы", 1, TEMP_PROTECT)

    # Шейдерные и системные кэши (перегенерируются сами).
    add(local / "NVIDIA" / "DXCache", "NVIDIA DXCache")
    add(local / "NVIDIA" / "GLCache", "NVIDIA GLCache")
    add(local / "D3DSCache", "DirectX D3DSCache")
    add(local / "CrashDumps", "Дампы сбоев")
    add(local / "Microsoft" / "Windows" / "INetCache", "INetCache", 7)
    add(local / "Microsoft" / "Windows" / "WebCache", "WebCache", 7)
    add(local / "Microsoft" / "Windows" / "Explorer", "Кэш значков и миниатюр")
    for sub in ("ReportArchive", "ReportQueue"):
        add(local / "Microsoft" / "Windows" / "WER" / sub, f"Отчёты об ошибках/{sub}", 7)
    add(local / "Steam" / "htmlcache", "Steam htmlcache")

    # Кэши пакетных менеджеров.
    add(local / "pip" / "cache", "pip cache")
    add(local / "npm-cache", "npm cache")
    add(local / "go-build", "go-build cache")

    # Браузеры на движке Chromium (все профили).
    for root_name, brand in (
        ("Google/Chrome", "Chrome"),
        ("Microsoft/Edge", "Edge"),
        ("Yandex/YandexBrowser", "Яндекс"),
    ):
        base = local / root_name / "User Data"
        if base.is_dir():
            try:
                profiles = list(base.iterdir())
            except OSError:
                profiles = []
            for prof in profiles:
                if not prof.is_dir() or prof.name.startswith("."):
                    continue
                for sub in _BROWSER_SUBDIRS:
                    add(prof / sub, f"{brand}: {prof.name}/{sub}")

    # Opera: структура без User Data.
    for base_root in (roam / "Opera Software" / "Opera Stable",
                      local / "Opera Software" / "Opera Stable"):
        for sub in ("Cache", "Code Cache", "GPUCache"):
            add(base_root / sub, f"Opera: {sub}")

    # Discord: кэш в Roaming и Local.
    for base_root in (roam / "discord", local / "Discord"):
        for sub in ("Cache", "Code Cache", "GPUCache"):
            add(base_root / sub, f"Discord: {sub}")

    return out


def _file_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def _tree_bytes(p: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(p, onerror=lambda e: None):
        for name in files:
            total += _file_size(Path(root) / name)
    return total


def _rmtree_lenient(p: Path) -> tuple[int, int]:
    """Удаляет файлы и подпапки, пропуская занятые. -> (файлы, байты)."""
    files, total = 0, 0
    for root, _dirs, names in os.walk(p, onerror=lambda e: None):
        for name in names:
            fp = Path(root) / name
            try:
                size = fp.stat().st_size
                fp.unlink()
            except OSError:
                continue
            files += 1
            total += size
    for root, dirs, _names in os.walk(p, topdown=False, onerror=lambda e: None):
        for d in dirs:
            try:
                (Path(root) / d).rmdir()
            except OSError:
                pass
    try:
        p.rmdir()
    except OSError:
        pass
    return files, total


def _clean_target(t: CacheTarget, stats: CleanStats) -> None:
    if not t.path.is_dir():
        return
    min_age = t.min_age_days * 86400
    now = time.time()
    files = total = 0
    for entry in list(t.path.iterdir()):
        try:
            if entry.name in t.protect:
                continue
            if min_age:
                try:
                    if now - entry.stat().st_mtime < min_age:
                        continue
                except OSError:
                    continue
            if entry.is_file():
                size = entry.stat().st_size
                entry.unlink()
                files += 1
                total += size
            elif entry.is_dir():
                f2, b2 = _rmtree_lenient(entry)
                files += f2
                total += b2
        except OSError:
            stats.failed += 1
    if files or total:
        stats.files += files
        stats.bytes += total
        stats.places.append((t.title, files, total))


_LOCK = threading.Lock()


def _read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def last_run() -> float:
    return float(_read_state().get("ts", 0.0))


def due(days: int) -> bool:
    return time.time() - last_run() >= days * 86400


def _write_state(ts: float, stats: CleanStats | None) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": ts,
        "freed_bytes": stats.bytes if stats else 0,
        "files": stats.files if stats else 0,
    }
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_PATH)


def run_clean(days: int, *, force: bool = False,
              targets: list[CacheTarget] | None = None) -> CleanStats | None:
    """Чистит кэши, если подошёл срок (или по force). None — чистка не требуется."""
    with _LOCK:
        if not force and not due(days):
            return None
        stats = CleanStats()
        for t in (targets if targets is not None else build_targets()):
            try:
                _clean_target(t, stats)
            except Exception:
                log.exception("Ошибка очистки %s", t.path)
        _write_state(time.time(), stats)
        log.info(
            "Кэш очищен: %s, файлов %d, папок затронуто %d, пропущено занятых %d",
            human_bytes(stats.bytes), stats.files, len(stats.places), stats.failed,
        )
        return stats
