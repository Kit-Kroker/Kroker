"""F2 doctor: is this environment variable a real credential or a template
value someone copied and never filled in? (spec section 7)

Two tiers. Tier 1 parses .env.example and treats "the value shipped for this
same key" as a placeholder -- self-maintaining, and it cannot false-positive
on a real credential. Tier 2 is a static floor for the case where
.env.example is not on disk (wheel install, worker image) and for stubs it
does not ship.

SCOPING IS LOAD-BEARING. classify_key is called only on the credential keys
rows 7 and 10 resolve, never over the whole environment: .env.example ships
working defaults beside its placeholders (TEMPORAL_HOST=localhost:7233 :11,
SDLC_MEMORY_BACKEND=hindsight :25, ANTHROPIC_BASE_URL :8) and a blanket
equals-shipped-value rule would flag every one.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

# Marker files that identify a repo checkout -- the same pair
# sdlc.agents.loader and sdlc.harness.containment walk up for.
_ROOT_MARKERS = ("pyproject.toml", "agents/registry.yaml")

# The floor. Reachable when .env.example is absent, and for stubs it does not
# ship -- tests/conftest.py:21-23 sets test-dummy, which tier 1 cannot see.
# A deliberate superset of the four the spec names (test-dummy, test-key,
# dummy, changeme): the extras are unambiguous stubs that cannot collide with
# a real credential, and each costs one set member. Widening this set is safe;
# widening _PLACEHOLDER_PREFIX is not.
STATIC_PLACEHOLDERS = frozenset(
    {"test-dummy", "test-key", "dummy", "changeme", "change-me", "placeholder", "xxx"}
)
_PLACEHOLDER_PREFIX = "your-"


def _discover_root() -> Path | None:
    for d in (Path.cwd(), *Path.cwd().parents):
        if all((d / m).is_file() for m in _ROOT_MARKERS):
            return d
    return None


def parse_env_example(root: Path | None = None) -> dict[str, str]:
    """{KEY: shipped_value} from .env.example, or {} when it is not on disk.

    Never raises: a missing template degrades tier 1 to nothing and leaves
    tier 2 doing the work, which is exactly the wheel-install case.
    """
    base = root if root is not None else _discover_root()
    if base is None:
        return {}
    path = Path(base) / ".env.example"
    if not path.is_file():
        return {}
    shipped: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        value = value.strip().strip("'\"")
        if value:
            shipped[key.strip()] = value
    return shipped


def classify_key(
    key: str, *, shipped: dict[str, str], environ: Mapping[str, str] | None = None
) -> tuple[bool, str]:
    """(is_usable, reason). reason is "" when usable.

    Call this ONLY on a credential key a check has resolved -- see the module
    docstring on scoping.
    """
    env = os.environ if environ is None else environ
    raw = env.get(key)
    if raw is None:
        return False, f"{key} is not set"
    value = raw.strip()
    if not value:
        return False, f"{key} is set but empty"
    if key in shipped and value == shipped[key]:
        return False, f"{key} still equals the .env.example placeholder {value!r}"
    if value.lower() in STATIC_PLACEHOLDERS or value.lower().startswith(_PLACEHOLDER_PREFIX):
        return False, f"{key} looks like a placeholder ({value!r}), not a credential"
    return True, ""
