import os
from datetime import datetime, timedelta
from pathlib import Path

from core.i18n import t
from modules.organizer.learning import Learned
from modules.organizer.preview import preview_rule
from modules.organizer.rules import Rule


def make_file(folder: Path, name: str, age_days: int = 0, content: bytes = b"x") -> Path:
    p = folder / name
    p.write_bytes(content)
    if age_days:
        mtime = datetime.now().timestamp() - age_days * 86400
        os.utime(p, (mtime, mtime))
    return p


def test_preview_matches_by_ext_and_age(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    old = make_file(folder, "old.log", 10)
    fresh = make_file(folder, "fresh.log", 1)
    make_file(folder, "photo.png")
    rule = Rule(name="Мусор", exts=[".log"], min_age_days=7, to_bin=True)
    result = preview_rule(rule, folder, tmp_path)
    names = [p.name for p, _ in result.matches]
    assert names == ["old.log"]  # свежий .log и .png не подходят
    # У bin-правила папки-цели нет, поэтому метка — «Корзина», а не путь.
    # Сравниваем через t(), а не с русским литералом: литерал делал тест
    # зависимым от глобального языка, который выставляют другие тесты.
    assert result.matches[0][1] == t("preview.bin")
    assert result.total_files == 3


def test_preview_move_target_resolved(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "doc.pdf")
    make_file(folder, "movie.mp4")
    rule = Rule(name="PDF", exts=[".pdf"], target="Документы/PDF/{year}")
    result = preview_rule(rule, folder, tmp_path)
    assert len(result.matches) == 1
    path, where = result.matches[0]
    assert path.name == "doc.pdf"
    year = datetime.now().year
    assert where == str((tmp_path / "Документы" / "PDF" / str(year)).resolve())


def test_preview_unsafe_target_hides_files(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "a.txt")
    rule = Rule(name="плохое", exts=[".txt"], target="../../Windows")
    result = preview_rule(rule, folder, tmp_path)
    assert result.matches == []  # правило не исполнится — файлов не показываем


def test_preview_keywords_second_pass(tmp_path, monkeypatch):
    # Текст извлекается только на втором проходе и только у кандидатов.
    from modules.organizer import analyzer

    monkeypatch.setattr(
        analyzer, "_pdf_text",
        lambda p: "ИТОГО к оплате 100" if "check" in p.name else "просто текст",
    )
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "check.pdf")
    make_file(folder, "blank.pdf")
    make_file(folder, "movie.mp4")
    rule = Rule(name="Чеки", exts=[".pdf"], keywords=["итого", "total"], target="Чеки")
    result = preview_rule(rule, folder, tmp_path)
    assert [p.name for p, _ in result.matches] == ["check.pdf"]
    assert result.total_files == 3


def test_preview_exclude_keywords_drops_false_positive(tmp_path, monkeypatch):
    from modules.organizer import analyzer

    monkeypatch.setattr(
        analyzer, "_pdf_text",
        lambda p: "password inside" if "secret" in p.name else "hello",
    )
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "secret.pdf")
    make_file(folder, "note.pdf")
    rule = Rule(name="Тексты", exts=[".pdf"], exclude_keywords=["password"], target="Тексты")
    result = preview_rule(rule, folder, tmp_path)
    assert [p.name for p, _ in result.matches] == ["note.pdf"]


def test_preview_learned_override(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "a.txt")
    learned = Learned(path=tmp_path / "learned.json")
    learned.record("Правило|.txt", "Изображения/Избранное")
    learned.accept("Правило|.txt")
    rule = Rule(name="Правило", exts=[".txt"], target="Документы/Прочее")
    result = preview_rule(rule, folder, tmp_path, learned=learned)
    assert result.matches[0][1] == str((tmp_path / "Изображения" / "Избранное").resolve())


def test_preview_ocr_limit_flag(tmp_path, monkeypatch):
    from modules.organizer import analyzer

    monkeypatch.setattr(analyzer, "_pdf_text", lambda p: "check total 1")
    folder = tmp_path / "src"
    folder.mkdir()
    for i in range(3):
        make_file(folder, f"c{i}.pdf")
    rule = Rule(name="Чеки", exts=[".pdf"], keywords=["total"], target="Чеки")
    result = preview_rule(rule, folder, tmp_path, ocr_limit=1)
    assert result.ocr_capped is True
    assert len(result.matches) == 1  # проверен только один кандидат


def test_preview_missing_folder(tmp_path):
    rule = Rule(name="x", exts=[".txt"], target="X")
    result = preview_rule(rule, tmp_path / "нет-такой", tmp_path)
    assert result.matches == [] and result.total_files == 0


# --- предпросмотр всей сортировки -----------------------------------------

from modules.organizer.preview import preview_folder  # noqa: E402


def _fresh(tmp_path):
    return Learned(path=tmp_path / "learned.json")


def test_preview_folder_first_match_wins(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "doc.pdf")
    make_file(folder, "clip.mp4")
    rules = [
        Rule(name="PDF", exts=[".pdf"], target="Документы/{year}"),
        Rule(name="Видео", exts=[".mp4"], target="Видео"),
        Rule(name="PDF-дубль", exts=[".pdf"], target="Другое"),
    ]
    result = preview_folder(folder, tmp_path, rules=rules, learned=_fresh(tmp_path))
    got = {m.src.name: (m.rule, m.dst) for m in result.moves}
    assert got["doc.pdf"][0] == "PDF"
    assert got["doc.pdf"][1] == str((tmp_path / "Документы" / str(datetime.now().year)).resolve())
    assert got["clip.mp4"][0] == "Видео"
    assert result.total_files == 2
    assert result.ocr_capped is False


def test_preview_folder_bin_and_delay(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "old.log", 10)
    make_file(folder, "new.log", 1)
    rules = [
        Rule(name="Мусор", exts=[".log"], min_age_days=7, to_bin=True),
        Rule(name="Ждём", exts=[".log"], delay_days=30, target="Позже"),
    ]
    result = preview_folder(folder, tmp_path, rules=rules, learned=_fresh(tmp_path))
    got = {m.src.name: m for m in result.moves}
    assert got["old.log"].to_bin is True
    assert got["old.log"].dst == t("preview.bin")
    assert got["new.log"].to_bin is False
    assert got["new.log"].delay_days == 30
    assert got["new.log"].dst == str((tmp_path / "Позже").resolve())


def test_preview_folder_text_candidate_matched_on_second_pass(tmp_path, monkeypatch):
    from modules.organizer import analyzer

    monkeypatch.setattr(
        analyzer, "_pdf_text",
        lambda p: "ИТОГО к оплате 100" if "check" in p.name else "",
    )
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "check.pdf")
    make_file(folder, "plain.pdf")
    rules = [Rule(name="Чеки", exts=[".pdf"], keywords=["итого"], target="Чеки")]
    result = preview_folder(folder, tmp_path, rules=rules, learned=_fresh(tmp_path))
    assert [m.src.name for m in result.moves] == ["check.pdf"]
    assert result.total_files == 2


def test_preview_folder_earlier_text_rule_beats_later_plain(tmp_path, monkeypatch):
    """Совпадение с правилом «Докон» посреди текстового должно перепроверяться."""
    from modules.organizer import analyzer

    monkeypatch.setattr(analyzer, "_pdf_text", lambda p: "ИТОГО")
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "a.pdf")
    rules = [
        Rule(name="Чеки", exts=[".pdf"], keywords=["итого"], target="Чеки"),
        Rule(name="Доки", exts=[".pdf"], target="Документы"),
    ]
    result = preview_folder(folder, tmp_path, rules=rules, learned=_fresh(tmp_path))
    assert [m.rule for m in result.moves] == ["Чеки"]


def test_preview_folder_exclude_keywords_drops_false_positive(tmp_path, monkeypatch):
    from modules.organizer import analyzer

    monkeypatch.setattr(
        analyzer, "_pdf_text",
        lambda p: "password inside" if "secret" in p.name else "hello",
    )
    folder = tmp_path / "src"
    folder.mkdir()
    make_file(folder, "secret.pdf")
    make_file(folder, "note.pdf")
    rules = [Rule(name="Тексты", exts=[".pdf"], exclude_keywords=["password"], target="Тексты")]
    result = preview_folder(folder, tmp_path, rules=rules, learned=_fresh(tmp_path))
    assert [m.src.name for m in result.moves] == ["note.pdf"]


def test_preview_folder_missing_folder(tmp_path):
    result = preview_folder(tmp_path / "нет-такой", tmp_path, rules=[])
    assert result.moves == [] and result.total_files == 0
