from pathlib import Path

from modules.organizer.analyzer import Features
from modules.organizer.rules import Rule


def _f(name, text="", gps=False):
    p = Path(name)
    return Features(path=p, ext=p.suffix.lower(), size=1, text=text, exif_has_gps=gps)


def test_first_match_wins():
    rules = [
        Rule(name="a", exts=[".pdf"], target="A"),
        Rule(name="b", exts=[".pdf"], target="B"),
    ]
    f = _f("x.pdf")
    folder = next(r.match(f) for r in rules if r.match(f))
    assert folder == "A"


def test_keyword_required():
    r = Rule(name="чек", exts=[".pdf"], keywords=["итого"], target="Чеки")
    assert r.match(_f("x.pdf", text="ИТОГО 100")) == "Чеки"
    assert r.match(_f("x.pdf", text="статья")) is None


def test_gps_required():
    r = Rule(name="поездки", exts=[".jpg"], requires_gps=True, target="П")
    assert r.match(_f("a.jpg", gps=False)) is None
    assert r.match(_f("a.jpg", gps=True)) == "П"


def test_no_match_returns_none():
    r = Rule(name="x", exts=[".exe"], target="Y")
    assert r.match(_f("a.pdf")) is None
