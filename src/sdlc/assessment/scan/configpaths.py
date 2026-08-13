"""Which paths are CONFIGURATION / INFRASTRUCTURE paths -- shared by SS3 and
by discover/attribution.py's infrastructure bucket (E-47b D10).

A scan-level constant belonging to no single signal, sited here for the reason
sources.py and testpaths.py are: two consumers now read it, so SS3 declares it
as a `rule_module` and rules_sha hashes it into SS3's memo key. Without that,
adding a pattern would move SS3's output while its key stood still -- the
E-3 / D10 hazard.
"""
from __future__ import annotations

import re

CONFIG_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)Dockerfile[\w.-]*$"),
    re.compile(r"(^|/)docker-compose[\w.-]*\.ya?ml$"),
    re.compile(r"(^|/)\.env[\w.-]*$"),
    re.compile(r"(^|/)appsettings(\.\w+)?\.json$"),
    re.compile(r"(^|/)application(-[\w]+)?\.(ya?ml|properties)$"),
    re.compile(r"(^|/)(k8s|kubernetes|deploy|deployment|helm|charts)/.*"
               r"\.(ya?ml|tpl)$"),
    re.compile(r"\.tf$|\.tfvars$|\.bicep$"),
    re.compile(r"(^|/)(nginx|haproxy)[\w.-]*\.conf$"),
)


def is_config_path(path: str) -> bool:
    """Whether configuration and infrastructure rules apply to a path."""
    return any(pattern.search(path) for pattern in CONFIG_PATTERNS)
