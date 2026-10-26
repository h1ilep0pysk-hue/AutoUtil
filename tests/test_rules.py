import os
from datetime import datetime

from modules.organizer.analyzer import Features
from modules.organizer.rules import Rule


def make_file(tmp_path, name="f.txt", age_days=0):
    p = tmp_path / name
    p.write_bytes(b"x")
    if age_days:
        mtime = datetime.now().timestamp() - age_days * 86400
        os.utime(p, (mtime, mtime))
    return p


def feats(p):
    return Features(path=p, ext=p.suffix.lower(), size=p.stat().st_size)


# --- критичный регресс: правило без target -------------------------------

def test_rule_without_target_is_safe(tmp_path):
    """Раньше target по умолчанию был кортежем из-за запятой — match падал."""
    r = Rule(name="x", exts=[".txt"])
    assert isinstance(r.target, str) and r.target == ""
    assert r.match(feats(make_file(tmp_path))) is None


# --- match: расширения, маски, возраст ----------------------------------

def test_exts_filter(tmp_path):
    r = Rule(name="t", exts=[".png"], target="Фото/{year}")
    assert r.match(feats(make_file(tmp_path, "a.png"))) == "Фото/" + str(datetime.now().year)
    assert r.match(feats(make_file(tmp_path, "b.jpg"))) is None


def test_exclude_exts(tmp_path):
    r = Rule(name="t", exts=[".png", ".jpg"], exclude_exts=[".jpg"], target="X")
    assert r.match(feats(make_file(tmp_path, "a.png"))) == "X"
    assert r.match(feats(make_file(tmp_path, "b.jpg"))) is None


def test_min_max_age(tmp_path):
    r = Rule(name="t", exts=[".log"], min_age_days=7, max_age_days=100, target="Корзина")
    assert r.match(feats(make_file(tmp_path, "a.log", 10))) == "Корзина"
    assert r.match(feats(make_file(tmp_path, "b.log", 2))) is None
    assert r.match(feats(make_file(tmp_path, "c.log", 200))) is None


def test_name_globs_and_regexes(tmp_path):
    g = Rule(name="g", exts=[".png"], name_globs=["Снимок экрана*"], target="Скрин")
    assert g.match(feats(make_file(tmp_path, "Снимок экрана 2026-01-01.png"))) == "Скрин"
    assert g.match(feats(make_file(tmp_path, "фото.png"))) is None
    rx = Rule(name="r", exts=[".png"], name_regexes=[r"^\d{14}_\d+"], target="Скрин")
    assert rx.match(feats(make_file(tmp_path, "20261026094152_1.png"))) == "Скрин"
    assert rx.match(feats(make_file(tmp_path, "не цифры.png"))) is None


def test_exclude_regexes(tmp_path):
    r = Rule(name="t", exts=[".txt"], exclude_regexes=["пароль"], target="X")
    assert r.match(feats(make_file(tmp_path, "заметки.txt"))) == "X"
    assert r.match(feats(make_file(tmp_path, "пароль.txt"))) is None


def test_size_limits(tmp_path):
    p = tmp_path / "big.bin"
    p.write_bytes(b"x" * (3 * 1024 * 1024))
    r = Rule(name="t", exts=[".bin"], min_mb=2, max_mb=5, target="X")
    assert r.match(feats(p)) == "X"
    small = tmp_path / "small.bin"
    small.write_bytes(b"x" * 10)
    assert r.match(feats(small)) is None


def test_keywords_need_text(tmp_path):
    r = Rule(name="t", exts=[".pdf"], keywords=["итого"], target="Чеки/{year}")
    f = feats(make_file(tmp_path, "check.pdf"))
    f.text = "ИТОГО к оплате: 100"
    assert r.match(f) == "Чеки/" + str(datetime.now().year)
    f.text = "просто текст"
    assert r.match(f) is None


def test_exclude_globs_match_path_parts(tmp_path):
    r = Rule(name="t", exts=[".txt"], exclude_globs=["node_modules"], target="X")
    p = tmp_path / "node_modules" / "lib.txt"
    p.parent.mkdir()
    p.write_bytes(b"x")
    assert r.match(feats(p)) is None


def test_gps_requirements(tmp_path):
    r = Rule(name="t", exts=[".jpg"], requires_gps=True, target="Поездки")
    assert r.match(feats(make_file(tmp_path, "a.jpg"))) is None  # gps нет по умолчанию
    f = feats(make_file(tmp_path, "a.jpg"))
    f.exif_has_gps = True
    assert r.match(f) == "Поездки"


def test_disabled_and_bin_rules(tmp_path):
    off = Rule(name="off", exts=[".txt"], target="X", enabled=False)
    assert off.match(feats(make_file(tmp_path))) is None
    bin_rule = Rule(name="bin", exts=[".log"], min_age_days=7, to_bin=True)
    assert bin_rule.match(feats(make_file(tmp_path, "a.log", 10))) == ""


def test_needs_text():
    assert not Rule(name="n", exts=[".txt"]).needs_text
    assert Rule(name="n", exts=[".txt"], keywords=["чек"]).needs_text
    assert not Rule(name="n", exts=[".txt"], keywords=["чек"], enabled=False).needs_text
