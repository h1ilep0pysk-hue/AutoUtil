from core.schema import Edge, Node, Schema


def test_source_filter_target_compiles_to_rule():
    s = Schema(
        nodes=[
            Node("a", "source", "Загрузки", params={"folder": "C:/Downloads"}),
            Node("b", "filter", "PDF", params={"exts": ["pdf"]}),
            Node("c", "target", "Документы", params={"folder": "Документы/{year}"}),
        ],
        edges=[Edge("a", "b"), Edge("b", "c")],
    )
    rules = s.to_rules()
    assert len(rules) == 1
    # ext normalization adds leading dot
    assert rules[0].exts == [".pdf"]
    assert rules[0].target == "Документы/{year}"


def test_cycle_does_not_hang():
    s = Schema(
        nodes=[
            Node("a", "source", "S", params={"folder": "x"}),
            Node("b", "filter", "F1"),
            Node("c", "filter", "F2"),
            Node("d", "target", "T", params={"folder": "y"}),
        ],
        edges=[Edge("a", "b"), Edge("b", "c"), Edge("c", "b"), Edge("c", "d")],
    )
    assert len(s.to_rules()) == 1


def test_no_target_gives_no_rules():
    s = Schema(nodes=[Node("a", "source", "S", params={"folder": "x"})])
    assert s.to_rules() == []
