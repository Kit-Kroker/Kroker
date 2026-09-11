"""Parse ROADMAP.md + docs/roadmap/*.md checkboxes into a status board.

The rule is the one the retired hand page documented (spec §3.1):
`[x]` → done, `[ ] ⚠️` → partial, `[ ]` → notstarted, `—` → notmeasurable,
keyed by the bold id. A line that begins a list item with a status marker
but carries no bold id is a malformed checkbox and raises, so the build
catches it instead of silently dropping it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Status = Literal["done", "partial", "notstarted", "notmeasurable"]

_STATUS_MARK_RE = re.compile(
    r"^\s*[-*]\s+(?P<mark>\[x\]\s*|\[\s\]\s*⚠️\s*|\[\s\]\s*|—\s*)(?P<rest>.*)$"
)
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
        super().__init__(f"{source}:{line}: status marker without bold id: {text!r}")
        self.source = source
        self.line = line
        self.text = text


def _status(mark: str) -> Status:
    mark = mark.strip()
    if mark == "[x]":
        return "done"
    if mark == "—":
        return "notmeasurable"
    if "⚠️" in mark:
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
            m = _STATUS_MARK_RE.match(text)
            if not m:
                continue
            idm = _ID_RE.match(m.group("rest"))
            if idm is None:
                raise UnparseableStatusLine(source, lineno, text)
            title = idm.group("tail").lstrip(" –-—").strip()
            current.append(
                Item(
                    id=idm.group("id").strip(),
                    status=_status(m.group("mark")),
                    title=title,
                    source=source,
                    line=lineno,
                )
            )
        flush()
    return sections
