"""FR-902: committed credentials, including the ones reachable from a client
bundle -- the highest-yield vibe-code finding, and the one no generic secret
scanner looks for.

Fix classes follow spec D7: removing a committed .env is MECHANICAL, but the
leaked credential itself is JUDGEMENT, because rotation is a human act. A PR
that deletes .env while the key stays live has produced the appearance of
remediation, which is worse than an open finding.

Stated bound (spec §7): client-bundle reachability is decided by CONVENTION --
build-time-inlined env prefixes -- not by dataflow. We do no taint tracking, so
a secret imported into a client component from a non-prefixed source is a false
negative. Naming that surface is what keeps the finding trustworthy.
"""
from __future__ import annotations

import posixpath
import re
from collections.abc import Sequence

from ..models import FixClass, TriageFinding

SIGNAL_ID = "secrets"
VERSION = 1

# Blobs larger than this are skipped: a minified bundle or a checked-in asset
# costs more to regex than the finding is worth, and E-41d owns size outliers.
MAX_BLOB_BYTES = 1_000_000


def is_over_size_limit(text: str) -> bool:
    """True when the blob's UTF-8 byte length exceeds MAX_BLOB_BYTES. Compares
    bytes, not ``len(str)`` characters, so multibyte content is bounded honestly
    (a minified CJK bundle is far larger in bytes than in characters)."""
    return len(text.encode("utf-8")) > MAX_BLOB_BYTES

_ENV_EXAMPLES = (".env.example", ".env.sample", ".env.template")

# (rule, pattern, detail). All critical, all JUDGEMENT: a matched provider
# credential must be rotated, and rotation is not something a PR can do.
_PROVIDER_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}"),
     "AWS access key id committed to the repository."),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),
     "GitHub token committed to the repository."),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
     "GitHub fine-grained PAT committed to the repository."),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
     "Google API key committed to the repository."),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
     "Slack token committed to the repository."),
    ("private_key",
     re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
     "Private key material committed to the repository."),
)

# Prefixes whose values frameworks INLINE INTO THE CLIENT BUNDLE at build time.
# The name is the whole signal: a service-role JWT is byte-indistinguishable
# from any other JWT, so only the variable's name says it must never ship.
_CLIENT_BUNDLE_VAR = re.compile(
    r"\b((?:NEXT_PUBLIC|VITE|REACT_APP|NUXT_PUBLIC|EXPO_PUBLIC|PUBLIC|GATSBY)"
    r"_[A-Z0-9_]*(?:SECRET|SERVICE_ROLE|PRIVATE_KEY)[A-Z0-9_]*)\b")

# What counts as a secret-shaped name. The two rules MUST agree: the
# client-bundle rule recognises SECRET|SERVICE_ROLE|PRIVATE_KEY, so the generic
# rule recognises the same three plus token/password/passwd/api_key. service_role
# and private_key are included so a leaked service-role JWT or private key in a
# NON-.env file (compose, CI, shell) is also caught -- inside a .env the
# file-level secret_committed rule already covers them.
#
# Segment-delimited, not a substring: the keyword must sit between separators
# (_/$/-) or the identifier edge. This drops `token` inside TOKENIZER (a real
# false positive in every ML repo) at the cost of camelCase jwtSecret (no
# separator before Secret) -- a deliberate precision/recall trade for a rule
# that is low severity by design.
_SECRET_KEYWORD = (
    r"secret|token|password|passwd|api[_-]?key"
    r"|service[_-]?role|private[_-]?key")
_SECRET_KEYWORD_RE = re.compile(
    rf"(?:^|[_$-])(?:{_SECRET_KEYWORD})(?:[_$-]|$)", re.IGNORECASE)

# Captures an identifier and its assignment value (double-quoted, single-quoted
# or unquoted .env KEY=value). The secret-shape decision is _SECRET_KEYWORD_RE
# applied to the captured identifier, keeping this regex a plain capture.
_GENERIC_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b ( [A-Za-z_$][\w$-]* ) \s* [:=] \s*
    (?: " ([^"\n]{8,}) "
      | ' ([^'\n]{8,}) '
      | ([^\s"']{8,})
    )
    """)


def _looks_random(value: str) -> bool:
    """Entropy gate for the generic rule. Without it, `password = "changeme"`
    floods every report and the signal stops being read; with it the rule
    keeps its narrow job of catching a real-looking literal. Deliberately
    crude -- charset diversity and length, not a Shannon threshold, because an
    arbitrary bit-count is no more defensible and much harder to explain in a
    finding."""
    return len(value) >= 16 and len(set(value)) >= 10


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "", line: int | None = None,
             evidence: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path,
                         line=line, evidence=evidence)


def scan_text(path: str, text: str) -> list[TriageFinding]:
    """Every rule against one file's bytes. `evidence` is the matched line,
    which is verbatim in `text` by construction -- verified in the activity
    against the pinned commit as a drift guard (spec D5)."""
    findings: list[TriageFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        quote = line.strip()[:400]
        for rule, pattern, detail in _PROVIDER_RULES:
            if pattern.search(line):
                findings.append(_finding(
                    rule, "critical",
                    f"{detail} Rotate the credential; deleting the file does "
                    f"not revoke it.",
                    FixClass.JUDGEMENT, path, lineno, quote))
        for match in _CLIENT_BUNDLE_VAR.finditer(line):
            var = match.group(1)
            findings.append(_finding(
                "client_bundle_secret", "critical",
                f"{var} is a build-time-inlined public variable whose name "
                f"says it holds a secret. Frameworks embed these in the "
                f"client bundle, so the value ships to every browser.",
                FixClass.JUDGEMENT, path, lineno, quote))
        for match in _GENERIC_ASSIGNMENT.finditer(line):
            ident = match.group(1)
            # value is group 2 (double-quoted), 3 (single-quoted) or 4 (unquoted)
            value = match.group(2) or match.group(3) or match.group(4)
            if (value and _looks_random(value)
                    and _SECRET_KEYWORD_RE.search(ident)):
                findings.append(_finding(
                    "generic_secret_assignment", "low",
                    f"{ident} is assigned a high-entropy literal. "
                    f"Verify whether it is a live credential.",
                    FixClass.JUDGEMENT, path, lineno, quote))
    return findings


def _is_env_file(path: str) -> bool:
    """A committed .env at any depth -- the common monorepo shape keeps them
    nested (backend/.env, apps/web/.env.local), and spec D7 says ".env present
    in the tracked tree", not ".env at the root". Examples are excluded by
    basename so apps/web/.env.example does not count."""
    base = posixpath.basename(path)
    return base == ".env" or (
        base.startswith(".env.") and base not in _ENV_EXAMPLES)


def env_file_findings(paths: Sequence[str]) -> list[TriageFinding]:
    """A tracked .env (root or nested), split into the two halves of spec D7."""
    tracked = set(paths)
    env_files = sorted(p for p in tracked if _is_env_file(p))
    if not env_files:
        return []
    listed = ", ".join(env_files)
    return [
        _finding(
            "secret_committed", "critical",
            f"{listed} is committed. Every value in it must be treated as "
            f"disclosed and rotated -- removing the file does not revoke "
            f"anything.",
            FixClass.JUDGEMENT, path=env_files[0]),
        # NOT "gitignore_missing_env" -- baseline owns that name for a
        # different condition (.gitignore exists but does not cover .env).
        # One rule id must mean one thing across the whole tier.
        _finding(
            "env_file_tracked", "high",
            f"{listed} is tracked; add it to .gitignore and remove it from "
            f"the index so the next secret does not follow it in.",
            FixClass.MECHANICAL, path=".gitignore"),
    ]
