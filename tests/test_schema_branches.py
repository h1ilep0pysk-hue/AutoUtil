from pathlib import Path

from core.schema import Edge, Node, Schema
from modules.organizer.analyzer import Features
from modules.organizer.rules import Rule


def test_yes_and_no_branches_produce_targets():
    s = Schema(
        nodes=[
            Node("s", "source", "S", params={"folder": "x"}),
            Node("f", "filter", "F", params={"exts": ["pdf"], "keywords": ["итого"]}),
            Node("c", "target", "Чеки", params={"folder": "Чеки"}),
            Node("d", "target", "Документы", params={"folder": "Док"}),
        ],
        edges=[Edge("s", "f"), Edge("f", "c", "yes"), Edge("f", "d", "no")],
    )
    rules = s.to_rules()
    targets = [r.target for r in rules]
    assert targets[0] == "Чеки"
    # NOT(pdf AND итого) = (NOT pdf) OR (pdf AND NOT итого): two rules for "Док"
    assert targets[1:] == ["Док", "Док"]


def test_ask_marks_rule():
    s = Schema(
        nodes=[
            Node("s", "source", "S", params={"folder": "x"}),
            Node("a", "ask", "A"),
            Node("t", "target", "T", params={"folder": "y"}),
        ],
        edges=[Edge("s", "a"), Edge("a", "t")],
    )
    rules = s.to_rules()
    assert len(rules) == 1 and rules[0].ask


def test_exclude_adds_masks():
    s = Schema(
        nodes=[
            Node("s", "source", "S", params={"folder": "x"}),
            Node("e", "exclude", "E", params={"masks": ["*.tmp", "node_modules"]}),
            Node("t", "target", "T", params={"folder": "y"}),
        ],
        edges=[Edge("s", "e"), Edge("e", "t")],
    )
    rule = s.to_rules()[0]
    assert "*.tmp" in rule.exclude_globs
    assert "node_modules" in rule.exclude_globs


def test_size_and_age_and_glob(tmp_path: Path):
    p = tmp_path / "invoice_1.pdf"
    p.write_bytes(b"x" * 10)
    f = Features(path=p, ext=".pdf", size=10)
    assert Rule(name="a", name_globs=["invoice_*.pdf"], target="T").match(f) == "T"
    assert Rule(name="a", name_globs=["report*"], target="T").match(f) is None
    assert Rule(name="a", min_mb=1, target="T").match(f) is None
    assert Rule(name="a", min_age_days=30, target="T").match(f) is None
    assert Rule(name="a", exclude_globs=["*.pdf"], target="T").match(f) is None


def test_invalid_regex_does_not_crash(tmp_path: Path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"x")
    f = Features(path=p, ext=".pdf", size=1)
    assert Rule(name="a", name_regexes=["(["], target="T").match(f) is None
