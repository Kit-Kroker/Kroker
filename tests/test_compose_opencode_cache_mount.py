"""Compose-lint regression for opencode-bootstrap-ebusy-models-json.

opencode's bootstrap replaces its models.dev cache by an atomic rename onto
/root/.cache/opencode/models.json. A single-file bind mount (host
models.json -> that exact path, e.g. `- C:/...models.json:/root/.cache/
opencode/models.json:ro`) makes the path a mount point inside the container,
and rename(2) onto a mount point fails EBUSY deterministically — every coding
attempt in the pinned run died ~5 s in, 15/15
(`.specify/bugs/opencode-bootstrap-ebusy-models-json`). Neither override may
declare an ACTIVE volume entry whose container-side target is that path; the
worker fetches models.dev itself on first bootstrap. Commented-out lines are
inert documentation and are ignored. The auth.json single-file ro mount is
deliberately allowed to stay: opencode only reads it, never replaces it.
"""

from __future__ import annotations

import pathlib
import re
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The forbidden container-side target. Anchored on the colon that precedes
# the container path in compose short syntax (`- <host>:<container>[:mode]`)
# so Windows drive colons on the host side (`C:/...`) cannot false-positive,
# and on a trailing `:`/whitespace/EOL so only the exact path matches (the
# auth.json mount targets .../auth.json — a different path, not flagged).
_SHORT_SYNTAX_TARGET = re.compile(r":/root/\.cache/opencode/models\.json(?=:|\s|$)")
# Same declaration in compose long syntax (`- type: bind` + `target: <path>`).
_LONG_SYNTAX_TARGET = re.compile(r"target:\s*/root/\.cache/opencode/models\.json\s*$")


def _offending_mounts(text: str) -> list[str]:
    """Return `line N: <text>` for every ACTIVE volume entry (under any
    service's `volumes:`, or the top-level one) whose container-side target
    is the opencode models.json cache path.

    Commented-out lines and lines outside `volumes:` blocks are ignored —
    the example override keeps commented blocks as documentation.
    """
    offenders: list[str] = []
    volumes_indent: int | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if volumes_indent is not None and indent <= volumes_indent:
            volumes_indent = None  # A sibling/parent key ended the block.
        if volumes_indent is not None and (
            _SHORT_SYNTAX_TARGET.search(stripped) or _LONG_SYNTAX_TARGET.search(stripped)
        ):
            offenders.append(f"line {lineno}: {stripped}")
        if stripped == "volumes:":
            volumes_indent = indent
    return offenders


def test_example_override_does_not_mount_opencode_models_json():
    path = ROOT / "docker-compose.override.example.yml"
    assert path.is_file(), "tracked docker-compose.override.example.yml must exist"
    offenders = _offending_mounts(path.read_text(encoding="utf-8"))
    assert not offenders, (
        "docker-compose.override.example.yml documents a mount of the host "
        "models.json onto /root/.cache/opencode/models.json; that single-file "
        "mount makes the path a mount point, so opencode's bootstrap rename "
        "onto it fails EBUSY and kills every coding attempt. Drop the mount: "
        f"{offenders}"
    )


def test_local_override_does_not_mount_opencode_models_json():
    path = ROOT / "docker-compose.override.yml"
    if not path.is_file():
        pytest.skip("machine-local docker-compose.override.yml not present")
    offenders = _offending_mounts(path.read_text(encoding="utf-8"))
    assert not offenders, (
        "docker-compose.override.yml mounts the host models.json onto "
        "/root/.cache/opencode/models.json; that single-file mount makes the "
        "path a mount point, so opencode's bootstrap rename onto it fails "
        "EBUSY and kills every coding attempt. Drop the mount — the worker "
        f"fetches models.dev itself on first bootstrap: {offenders}"
    )


def test_parser_flags_active_mounts_but_not_comments_or_auth_json():
    """Parser self-check: an active short-syntax or long-syntax declaration
    of the cache target is flagged on any service; the auth.json single-file
    mount (opencode only reads it — that mount stays) and commented-out
    lines are not."""
    compose = textwrap.dedent(
        """\
        services:
          worker:
            volumes:
              # - C:/Users/x/.cache/opencode/models.json:/root/.cache/opencode/models.json:ro
              - ~/.local/share/opencode/auth.json:/root/.local/share/opencode/auth.json:ro
              - D:/host/repos:/srv/scratch-repos
          other:
            volumes:
              - type: bind
                source: ~/.cache/opencode/models.json
                target: /root/.cache/opencode/models.json
                read_only: true
        volumes:
          named:
        """
    )
    assert _offending_mounts(compose) == ["line 11: target: /root/.cache/opencode/models.json"]
