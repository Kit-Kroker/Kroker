"""Adversarial RED regression for opencode-bootstrap-ebusy-models-json.

Bug: the compose overrides bind-mount the host's models.json as a single
file at exactly /root/.cache/opencode/models.json. A single-file bind mount
makes that container path a mount point, so opencode's bootstrap cache
refresh — fetch models.dev, write a sibling tmp file, atomic rename onto
models.json — deterministically fails EBUSY and every coding attempt dies
(assessment: .specify/bugs/opencode-bootstrap-ebusy-models-json).

Cleared fix: DROP the models.json mount from both override files (the
worker fetches models.dev itself); auth.json single-file :ro stays.

This chaos file pins the bug via a dependency-free checker,
``_active_single_file_models_mounts``, driven by hostile variants of every
mount shape it must catch and the neighbours it must NOT flag. The
real-file tests at the bottom are the RED driver: they fail while either
override still carries an active single-file models.json mount and pass
once the mount lines are dropped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# opencode REPLACES this file by rename; any active volume entry mounting a
# single file onto exactly this container path makes it a mount point -> EBUSY.
_TARGET = "/root/.cache/opencode/models.json"

# Short syntax `- HOST:TARGET[:MODE]`: mode tokens (ro/rw/cached/z,...) never
# contain a slash, so a longer container path cannot sneak past the anchor.
# Windows host paths (C:/...) survive because only the tail is anchored; the
# optional quote tolerates `- "HOST:TARGET:MODE"` entries.
_SHORT_ENTRY = re.compile(r":" + re.escape(_TARGET) + r"(?::[A-Za-z][\w,=.-]*)?[\"']?\s*$")
# Long syntax volume block: `target: /root/.cache/opencode/models.json`.
_LONG_TARGET = re.compile(r"^\s*target:\s*[\"']?" + re.escape(_TARGET) + r"[\"']?\s*$")


def _active_single_file_models_mounts(compose_text: str) -> list[str]:
    """Active volume entries whose container path is exactly ``_TARGET``.

    Returns the offending entry text per hit (short-syntax line, or the
    long-syntax ``target:`` line). Commented-out lines, blanks and
    directory-level mounts (``/root/.cache/opencode`` without the file
    name) are not active single-file mounts and must not be reported.
    Env-style mapping values are ignored: only list items (short) and
    ``target:`` keys (long) are volume shapes.
    """
    offenders: list[str] = []
    for raw in compose_text.splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue  # blanks and comments are never active entries
        if re.match(r"^-\s+\S", entry) and _SHORT_ENTRY.search(entry):
            offenders.append(entry)
        elif _LONG_TARGET.match(raw):
            offenders.append(entry)
    return offenders


def _compose(*volume_lines: str) -> str:
    """Minimal compose skeleton; the lines land under worker.volumes."""
    return "services:\n  worker:\n    volumes:\n" + "\n".join(volume_lines) + "\n"


# ---- the checker must catch every single-file mount shape --------------------


@pytest.mark.parametrize(
    "compose_text",
    [
        pytest.param(
            _compose(
                "      - C:/Users/x/.cache/opencode/models.json:"
                "/root/.cache/opencode/models.json:ro"
            ),
            id="windows-host-colon-ro",
        ),
        pytest.param(
            _compose("      - ~/.cache/opencode/models.json:/root/.cache/opencode/models.json:ro"),
            id="posix-tilde-host-ro",
        ),
        pytest.param(
            _compose("      - /host/models.json:/root/.cache/opencode/models.json"),
            id="no-access-mode",
        ),
        pytest.param(
            _compose("      - /host/models.json:/root/.cache/opencode/models.json:rw"),
            id="rw-mode",
        ),
        pytest.param(
            _compose("      - /host/models.json:/root/.cache/opencode/models.json:cached"),
            id="cached-mode",
        ),
        pytest.param(
            _compose(
                "      - type: bind",
                "        source: /host/models.json",
                "        target: /root/.cache/opencode/models.json",
                "        read_only: true",
            ),
            id="long-syntax-bind-readonly",
        ),
        pytest.param(
            _compose("        -   /host/models.json:/root/.cache/opencode/models.json:ro" + "   "),
            id="extra-whitespace-trailing-spaces",
        ),
        pytest.param(
            _compose('      - "/host/models.json:/root/.cache/opencode/models.json:ro"'),
            id="quoted-short-entry",
        ),
        pytest.param(
            _compose(
                "      - type: bind",
                '        target: "/root/.cache/opencode/models.json"',
            ),
            id="long-syntax-quoted-target",
        ),
    ],
)
def test_checker_flags_single_file_models_json_mount(compose_text: str):
    offenders = _active_single_file_models_mounts(compose_text)
    assert offenders, "active single-file models.json mount must be flagged"
    assert all(_TARGET in entry for entry in offenders)


# ---- the checker must not flag the neighbours --------------------------------


@pytest.mark.parametrize(
    "compose_text",
    [
        pytest.param(
            _compose(
                "      - C:/Users/start/.local/share/opencode/auth.json:"
                "/root/.local/share/opencode/auth.json:ro"
            ),
            id="auth-json-single-file-ro-stays",
        ),
        pytest.param(
            _compose(
                "      # - ~/.cache/opencode/models.json:/root/.cache/opencode/models.json:ro"
            ),
            id="commented-out-entry",
        ),
        pytest.param(
            _compose("      - /host/opencode-cache:/root/.cache/opencode:rw"),
            id="directory-level-mount",
        ),
        pytest.param("", id="empty-text"),
        pytest.param(
            _compose(
                "      - /path/to/your/repos:/srv/scratch-repos",
                "      - ~/.local/share/opencode/auth.json:"
                "/root/.local/share/opencode/auth.json:ro",
            ),
            id="volumes-without-such-entry",
        ),
        pytest.param(
            "services:\n"
            "  worker:\n"
            "    environment:\n"
            "      SOME_VAR: /root/.cache/opencode/models.json\n",
            id="env-mapping-value-is-not-a-volume",
        ),
        pytest.param(
            _compose(
                "      - type: bind",
                "        source: /root/.cache/opencode/models.json",
                "        target: /elsewhere/models.json",
            ),
            id="long-syntax-host-side-source",
        ),
    ],
)
def test_checker_ignores_non_offending_neighbours(compose_text: str):
    assert _active_single_file_models_mounts(compose_text) == []


# ---- missing-file robustness: the caller owns absence ------------------------


def test_absent_override_file_is_handled_by_caller_not_error(tmp_path):
    # The machine-local override is gitignored and may not exist; the caller
    # treats absence as "nothing to check" rather than an error.
    missing = tmp_path / "docker-compose.override.yml"
    text = missing.read_text(encoding="utf-8") if missing.exists() else ""
    assert _active_single_file_models_mounts(text) == []


def test_present_override_file_under_tmp_path_is_checked(tmp_path):
    override = tmp_path / "docker-compose.override.yml"
    override.write_text(_compose("      - /host/models.json" + f":{_TARGET}:ro"), encoding="utf-8")
    assert _active_single_file_models_mounts(override.read_text(encoding="utf-8"))


# ---- RED driver: the real files (fails while the mount lines exist) ----------


def test_example_override_has_no_active_single_file_models_json_mount():
    path = REPO_ROOT / "docker-compose.override.example.yml"
    assert path.is_file(), "docker-compose.override.example.yml must exist"
    offenders = _active_single_file_models_mounts(path.read_text(encoding="utf-8"))
    assert not offenders, (
        "opencode-bootstrap-ebusy-models-json: drop the single-file models.json "
        f"mount from docker-compose.override.example.yml (found: {offenders})"
    )


def test_machine_local_override_has_no_active_single_file_models_json_mount():
    path = REPO_ROOT / "docker-compose.override.yml"
    if not path.exists():
        pytest.skip("machine-local docker-compose.override.yml not present")
    offenders = _active_single_file_models_mounts(path.read_text(encoding="utf-8"))
    assert not offenders, (
        "opencode-bootstrap-ebusy-models-json: drop the single-file models.json "
        f"mount from docker-compose.override.yml (found: {offenders})"
    )
