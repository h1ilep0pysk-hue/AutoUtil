"""Схема сортировки: узлы и связи, компиляция в правила.

Узлы: source (папка), filter (фильтр), ask (спросить), exclude (исключить), target (цель).
Связи: branch "yes" (обычная) и "no" (ветка «нет», только из фильтра).
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

from modules.organizer.rules import Rule

SCHEMA_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "schema.json"

KIND_TITLES = {
    "source": "Папка",
    "filter": "Фильтр",
    "ask": "Спросить",
    "exclude": "Исключить",
    "target": "Цель",
}

ALLOWED_LINKS = {
    ("source", "filter"), ("source", "exclude"), ("source", "target"),
    ("exclude", "filter"), ("exclude", "ask"), ("exclude", "target"),
    ("filter", "filter"), ("filter", "ask"), ("filter", "target"),
    ("ask", "filter"), ("ask", "target"),
}
NO_BRANCH_FROM = {"filter"}

MAX_RULES = 500
MAX_STEPS = 200_000


@dataclass
class Node:
    id: str
    kind: str
    title: str
    x: float = 0.0
    y: float = 0.0
    params: dict = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    branch: str = "yes"


@dataclass
class Schema:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def to_rules(self) -> list[Rule]:
        by_id = {n.id: n for n in self.nodes}
        children: dict[str, list[Edge]] = {}
        for e in self.edges:
            children.setdefault(e.src, []).append(e)

        out: list[Rule] = []
        steps = [0]

        def emit(spec: Spec, target: Node) -> None:
            if spec.dead or len(out) >= MAX_RULES:
                return
            out.append(_make_rule(spec, target))

        def visit(nid: str, spec: Spec, seen: frozenset[str]) -> None:
            steps[0] += 1
            if steps[0] > MAX_STEPS or len(out) >= MAX_RULES or spec.dead:
                return
            node = by_id[nid]
            if node.kind == "target":
                emit(spec, node)
                return
            outs = children.get(nid, [])
            if node.kind == "filter":
                yes_spec = apply_filter(spec, node)
                no_specs = negations(spec, node)
                for e in outs:
                    if e.dst in seen or e.dst not in by_id:
                        continue
                    if e.branch == "no":
                        for s in no_specs:
                            visit(e.dst, s, seen | {e.dst})
                    else:
                        visit(e.dst, yes_spec, seen | {e.dst})
                return
            # for source, ask, exclude, etc.
            next_spec = apply_pass(spec, node)
            for e in outs:
                if e.branch == "no" or e.dst in seen or e.dst not in by_id:
                    continue
                visit(e.dst, next_spec, seen | {e.dst})

        for node in self.nodes:
            if node.kind == "source":
                visit(node.id, Spec(), frozenset({node.id}))
        return out

    def source_folders(self) -> list[str]:
        return [n.params.get("folder", "") for n in self.nodes if n.kind == "source" and n.params.get("folder")]


@dataclass
class Spec:
    exts: list[str] | None = None
    not_exts: list[str] = field(default_factory=list)
    kw_groups: list[list[str]] = field(default_factory=list)
    not_kw: list[str] = field(default_factory=list)
    globs: list[str] = field(default_factory=list)
    not_globs: list[str] = field(default_factory=list)
    regexes: list[str] = field(default_factory=list)
    not_regexes: list[str] = field(default_factory=list)
    min_mb: float = 0.0
    max_mb: float = 0.0
    min_age: int = 0
    max_age: int = 0
    gps: bool | None = None
    masks: list[str] = field(default_factory=list)
    ask: bool = False
    dead: bool = False

    def copy(self) -> "Spec":
        return copy.deepcopy(self)


def _ext(e: str) -> str:
    e = e.strip().lower()
    return e if e.startswith(".") else "." + e


def _atoms(node: Node) -> list[tuple[str, object]]:
    p = node.params
    atoms: list[tuple[str, object]] = []
    if p.get("exts"):
        atoms.append(("exts", [_ext(e) for e in p["exts"]]))
    if p.get("keywords"):
        atoms.append(("kw", list(p["keywords"])) )
    if p.get("name_glob"):
        atoms.append(("glob", p["name_glob"]))
    if p.get("name_regex"):
        atoms.append(("regex", p["name_regex"]))
    if float(p.get("min_mb") or 0) > 0:
        atoms.append(("min_mb", float(p["min_mb"])))
    if float(p.get("max_mb") or 0) > 0:
        atoms.append(("max_mb", float(p["max_mb"])))
    if int(p.get("min_age_days") or 0) > 0:
        atoms.append(("min_age", int(p["min_age_days"])))
    if int(p.get("max_age_days") or 0) > 0:
        atoms.append(("max_age", int(p["max_age_days"])))
    if p.get("requires_gps"):
        atoms.append(("gps", True))
    return atoms


def _apply(spec: Spec, kind: str, value, negate: bool) -> Spec:
    s = spec.copy()
    if kind == "exts":
        if not negate:
            s.exts = list(value) if s.exts is None else [e for e in s.exts if e in value]
            if not s.exts:
                s.dead = True
        else:
            s.not_exts += list(value)
    elif kind == "kw":
        if not negate:
            s.kw_groups.append(list(value))
        else:
            s.not_kw += list(value)
    elif kind == "glob":
        (s.not_globs if negate else s.globs).append(value)
    elif kind == "regex":
        (s.not_regexes if negate else s.regexes).append(value)
    elif kind == "min_mb":
        if not negate:
            s.min_mb = max(s.min_mb, value)
        else:
            s.max_mb = value if s.max_mb == 0 else min(s.max_mb, value)
    elif kind == "max_mb":
        if not negate:
            s.max_mb = value if s.max_mb == 0 else min(s.max_mb, value)
        else:
            s.min_mb = max(s.min_mb, value)
    elif kind == "min_age":
        if not negate:
            s.min_age = max(s.min_age, value)
        else:
            s.max_age = value if s.max_age == 0 else min(s.max_age, value)
    elif kind == "max_age":
        if not negate:
            s.max_age = value if s.max_age == 0 else min(s.max_age, value)
        else:
            s.min_age = max(s.min_age, value)
    elif kind == "gps":
        want = (not value) if negate else value
        if s.gps is not None and s.gps != want:
            s.dead = True
        s.gps = want
    return s


def apply_filter(spec: Spec, node: Node) -> Spec:
    s = spec
    for kind, value in _atoms(node):
        s = _apply(s, kind, value, negate=False)
    return s


def negations(spec: Spec, node: Node) -> list[Spec]:
    atoms = _atoms(node)
    out: list[Spec] = []
    for i, (kind, value) in enumerate(atoms):
        s = spec
        for k2, v2 in atoms[:i]:
            s = _apply(s, k2, v2, negate=False)
        out.append(_apply(s, kind, value, negate=True))
    return out


def apply_pass(spec: Spec, node: Node) -> Spec:
    s = spec.copy()
    if node.kind == "ask":
        s.ask = True
    elif node.kind == "exclude":
        s.masks += [m.strip() for m in node.params.get("masks", []) if m.strip()]
    return s


def _make_rule(spec: Spec, target: Node) -> Rule:
    return Rule(
        name=target.title,
        exts=spec.exts or [],
        exclude_exts=list(spec.not_exts),
        keyword_groups=[list(g) for g in spec.kw_groups],
        exclude_keywords=list(spec.not_kw),
        name_globs=list(spec.globs),
        exclude_globs=list(spec.masks) + list(spec.not_globs),
        name_regexes=list(spec.regexes),
        exclude_regexes=list(spec.not_regexes),
        min_mb=spec.min_mb,
        max_mb=spec.max_mb,
        min_age_days=spec.min_age,
        max_age_days=spec.max_age,
        requires_gps=spec.gps is True,
        forbid_gps=spec.gps is False,
        ask=spec.ask,
        rename=target.params.get("rename", ""),
        target=target.params.get("folder", ""),
    )


def load_schema(path: Path = SCHEMA_PATH) -> Schema:
    if not path.exists():
        return Schema()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Schema(
        nodes=[Node(**n) for n in data.get("nodes", [])],
        edges=[Edge(**e) for e in data.get("edges", [])],
    )


def save_schema(schema: Schema, path: Path = SCHEMA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"nodes": [asdict(n) for n in schema.nodes], "edges": [asdict(e) for e in schema.edges]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
