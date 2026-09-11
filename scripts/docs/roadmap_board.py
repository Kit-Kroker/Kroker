"""Parse ROADMAP.md + docs/roadmap/*.md checkboxes into a status board.

The rule is the one the retired hand page documented (spec §3.1):
`[x]` → done, `[ ] ⚠️` → partial, `[ ]` → notstarted, `—` → notmeasurable,
keyed by the bold id. The repo also writes `[ ] — **NFR-3** …` (a bracket
marker plus a governing dash = notmeasurable) and decorates done items with
`✅`; both are classified. A status line with a KNOWN marker but no bold id
(e.g. ROADMAP §14's `[ ] ⚠️ Layered src/factory/ tree …`) is commentary,
not a board item, and is skipped. An UNKNOWN bracket marker raises, so a
malformed checkbox fails the build instead of silently disappearing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Status = Literal["done", "partial", "notstarted", "notmeasurable"]

_LIST_RE = re.compile(r"^\s*[-*]\s+(?P<tok>\[[^]\n]*\]|—)\s*(?P<rest>.*)$")
_DECO_RE = re.compile("^(?:[⚠️✅❌–—-]\s*)*")
_ID_RE = re.compile(r"^\*\*(?P<id>[^*]+?)\*\*(?P<tail>.*)$")
_HEADING_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")


@dataclass(frozen=True)
class Item:
    id: str
    status: Status
    title: str
    source: str
    line: int


@dataclass(frozen=True)
class Section:
    title: str
    items: list[Item] = field(default_factory=list)


class UnparseableStatusLine(Exception):
    def __init__(self, source: str, line: int, text: str) -> None:
        super().__init__(f"{source}:{line}: unrecognized status marker: {text!r}")
        self.source = source
        self.line = line
        self.text = text


def _marker_kind(tok: str) -> str | None:
    """'done' | 'box' | 'dash' for known markers, None for unknown ones."""
    if tok == "—":
        return "dash"
    inner = tok[1:-1].strip()
    if inner.lower() == "x":
        return "done"
    if inner == "":
        return "box"
    return None


def _status(kind: str, deco: str) -> Status:
    if kind == "done":
        return "done"
    if kind == "dash" or "—" in deco or "–" in deco:
        return "notmeasurable"
    if "⚠️" in deco:
        return "partial"
    return "notstarted"


def parse_board(sources: dict[str, str]) -> list[Section]:
    sections: list[Section] = []
    current_title = ""
    current: list[Item] = []

    def flush() -> None:
        nonlocal current
        if current:
            sections.append(Section(current_title, current))
        current = []

    for source in sorted(sources):
        current_title = source
        for lineno, text in enumerate(sources[source].splitlines(), start=1):
            heading = _HEADING_RE.match(text)
            if heading:
                flush()
                current_title = heading.group("title")
                continue
            m = _LIST_RE.match(text)
            if not m:
                continue
            kind = _marker_kind(m.group("tok"))
            if kind is None:
                raise UnparseableStatusLine(source, lineno, text)
            deco_m = _DECO_RE.match(m.group("rest"))
            deco = deco_m.group(0)
            rest = m.group("rest")[deco_m.end() :]
            idm = _ID_RE.match(rest)
            if idm is None:
                continue  # known marker, no bold id: commentary, not a board item
            title = idm.group("tail").lstrip(" –-—").strip()
            current.append(
                Item(
                    id=idm.group("id").strip(),
                    status=_status(kind, deco),
                    title=title,
                    source=source,
                    line=lineno,
                )
            )
        flush()
    return sections


BOARD_PAGE = "generated/roadmap-board.md"

BLOB_BASE = "https://github.com/Kit-Kroker/Kroker/blob/main/"


def board_sources(repo_root: Path) -> dict[str, str]:
    """ROADMAP.md + docs/roadmap/*.md at their repo-relative paths."""
    paths = ["ROADMAP.md"] + sorted(
        f"docs/roadmap/{p.name}" for p in (repo_root / "docs" / "roadmap").glob("*.md")
    )
    return {p: (repo_root / p).read_text(encoding="utf-8") for p in paths}


def render_board(sections: list[Section]) -> str:
    counts: dict[str, int] = {}
    lines = [
        "# Roadmap status board",
        "",
        "Generated from `ROADMAP.md` + `docs/roadmap/*.md` on every build.",
        "Status rule: `[x]` done · `[ ] ⚠️` partial · `[ ]` not started · `—` not measurable.",
        "",
    ]
    for section in sections:
        lines += [
            f"## {section.title}",
            "",
            "| Id | Status | Title | Source |",
            "| --- | --- | --- | --- |",
        ]
        for it in section.items:
            counts[it.status] = counts.get(it.status, 0) + 1
            title = it.title.replace("|", "\|")[:80]
            lines.append(
                f"| **{it.id}** | {it.status} | {title} "
                f"| [{it.source}:{it.line}]({BLOB_BASE}{it.source}#L{it.line}) |"
            )
        lines.append("")
    lines += ["## Totals", "", "| Status | Items |", "| --- | --- |"]
    for status in ("done", "partial", "notstarted", "notmeasurable"):
        lines.append(f"| {status} | {counts.get(status, 0)} |")
    lines.append("")
    return "\n".join(lines)
