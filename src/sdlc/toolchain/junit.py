"""pytest legacy-family JUnit -> {node id: passed} (diff-scoped gates DS6).

Node ids must be re-runnable, so the class segment is rebuilt from
`classname` minus the module path, and a collection error (classname="")
keys on its module file. `file` is normalized to POSIX: on Windows pytest
writes `\\` for ordinary cases and `/` for collection errors. Parsed with
defusedxml, because the report comes from untrusted code under test.
Returns None, never {}, for a missing or unparseable report, so the caller
fails closed instead of reading "no failures".
"""

from __future__ import annotations

import re

import defusedxml.ElementTree as DET
from defusedxml.common import DefusedXmlException

from ..change_scope import normalize_path

_SHELL_SAFE = re.compile(r"^[A-Za-z0-9_./:\-\[\]]+$")


def shell_safe(node_id: str) -> bool:
    """A node id may be interpolated into a shell command only if it matches a
    strict allowlist. Callers treat an unsafe id as unattributable -- which,
    for the merge gate, means introduced (fail toward blocking)."""
    return bool(_SHELL_SAFE.fullmatch(node_id))


def _node_id(tc) -> str:
    file_attr = normalize_path(tc.get("file") or "")
    name = tc.get("name", "")
    classname = tc.get("classname", "")
    if not classname:
        return file_attr or name.replace(".", "/") + ".py"
    module = file_attr[:-3].replace("/", ".") if file_attr.endswith(".py") else ""
    head = file_attr or classname.replace(".", "/") + ".py"
    parts = [head]
    if module and classname.startswith(module + "."):
        parts.extend(classname[len(module) + 1 :].split("."))
    parts.append(name)
    return "::".join(parts)


def testcase_outcomes(xml_text: str) -> dict[str, bool] | None:
    if not xml_text.strip():
        return None
    try:
        root = DET.fromstring(xml_text)
    except (DefusedXmlException, DET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    out: dict[str, bool] = {}
    for suite in suites:
        for tc in suite.iter("testcase"):
            if tc.find("skipped") is not None:
                continue
            node = _node_id(tc)
            failed = tc.find("failure") is not None or tc.find("error") is not None
            out[node] = out.get(node, True) and not failed
    return out


testcase_outcomes.__test__ = False  # type: ignore[attr-defined]
