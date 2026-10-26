from datetime import datetime

from modules.organizer.learning import Learned
from modules.organizer.planner import learn_key, plan
from modules.organizer.rules import Rule


def make_file(tmp_path, name="f.txt", age_days=0):
    import os

    p = tmp_path / name
    p.write_bytes(b"x")
    if age_days:
        mtime = datetime.now().timestamp() - age_days * 86400
        os.utime(p, (mtime, mtime))
    return p


def feats(p):
    from modules.organizer.analyzer import Features
    return Features(path=p, ext=p.suffix.lower(), size=p.stat().st_size)


def test_first_match_wins(tmp_path):
    rules = [
        Rule(name="A", exts=[".txt"], target="ПапкаA"),
        Rule(name="B", exts=[".txt"], target="ПапкаB"),
    ]
    mv = plan(feats(make_file(tmp_path)), rules, tmp_path, Learned(path=tmp_path / "l.json"))
    assert mv.rule == "A"
    assert mv.dst.parent == (tmp_path / "ПапкаA").resolve()


def test_to_bin_move(tmp_path):
    rules = [Rule(name="Корзина", exts=[".log"], to_bin=True)]
    mv = plan(feats(make_file(tmp_path, "a.log")), rules, tmp_path, Learned(path=tmp_path / "l.json"))
    assert mv.to_bin is True
    assert mv.dst == mv.src  # у корзины нет папки-цели
    assert mv.delay_days == 0


def test_to_bin_with_ask_and_delay(tmp_path):
    rules = [Rule(name="Спросить", to_bin=True, ask=True, delay_days=30)]
    mv = plan(feats(make_file(tmp_path)), rules, tmp_path, Learned(path=tmp_path / "l.json"))
    assert mv.ask and mv.to_bin and mv.delay_days == 30


def test_delay_passthrough(tmp_path):
    rules = [Rule(name="Через N дней", exts=[".log"], delay_days=7, to_bin=True)]
    mv = plan(feats(make_file(tmp_path, "a.log")), rules, tmp_path, Learned(path=tmp_path / "l.json"))
    assert mv.delay_days == 7 and mv.to_bin


def test_unsafe_rule_skipped_next_matches(tmp_path):
    rules = [
        Rule(name="плохая", exts=[".txt"], target="../../Windows"),
        Rule(name="хорошая", exts=[".txt"], target="Документы/TXT"),
    ]
    mv = plan(feats(make_file(tmp_path)), rules, tmp_path, Learned(path=tmp_path / "l.json"))
    assert mv.rule == "хорошая"
    assert mv.dst.parent == (tmp_path / "Документы" / "TXT").resolve()


def test_learned_override(tmp_path):
    learned = Learned(path=tmp_path / "learned.json")
    learned.record(learn_key("Правило", ".txt"), "Изображения/Избранное")
    learned.accept(learn_key("Правило", ".txt"))
    rules = [Rule(name="Правило", exts=[".txt"], target="Документы/Прочее")]
    mv = plan(feats(make_file(tmp_path)), rules, tmp_path, learned)
    assert mv.dst.parent == (tmp_path / "Изображения" / "Избранное").resolve()


def test_no_rule_no_move(tmp_path):
    assert plan(feats(make_file(tmp_path)), [], tmp_path, Learned(path=tmp_path / "l.json")) is None


def test_broken_rule_does_not_kill_file(tmp_path):
    class BadRule:
        name = "сломанное"

        def match(self, f):
            raise RuntimeError("boom")

    rules = [BadRule(), Rule(name="good", exts=[".txt"], target="OK")]
    mv = plan(feats(make_file(tmp_path)), rules, tmp_path, Learned(path=tmp_path / "l.json"))
    assert mv.rule == "good"
