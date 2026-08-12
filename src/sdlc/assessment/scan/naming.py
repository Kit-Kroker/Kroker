"""Name normalization shared by S1's classification, S3's grouping and S5's
merge (D9, P2-D2).

Sited once because all three need the same rules -- S3 groups
PaymentController + PaymentSettlementJob + PaymentEventConsumer into one
candidate, S5 merges that candidate with S1's payments/ package, and S1 asks
of a directory name the same "is this a technical layer word?" question S3
asks of a file stem. Two copies would agree only by coincidence.

VERSION is decorative here: this module is a `rule_modules` entry, so
rules_sha hashes its BYTES (D10). Editing a table below moves S1's, S3's and
S5's memo keys by construction, which is the property test_scan_rules_sha
asserts.

Known limitation, recorded as OQ-12: suffix stripping and singularization
assume English identifiers. A non-English codebase degrades to
LOW-confidence single-source candidates rather than to wrong ones.
"""
from __future__ import annotations

VERSION = 1

# Suffixes that describe a technical layer rather than a capability (D9).
# Declared capitalized because that is how they appear in source; matching is
# case-insensitive and picks the LONGEST match, so this tuple's order carries
# no meaning ("Utils" must beat "Util" whichever is declared first).
LAYER_SUFFIXES: tuple[str, ...] = (
    "Controller", "Service", "Repository", "Handler", "Manager", "Resource",
    "Router", "Route", "Consumer", "Listener", "Subscriber", "Publisher",
    "Job", "Worker", "Task", "Scheduler", "Client", "Gateway", "Provider",
    "Factory", "Builder", "Helper", "Helpers", "Utils", "Util", "Impl",
    "Dao", "Dto", "Mapper", "Middleware", "ViewSet", "View", "Serializer",
    "Schema", "Model", "Entity", "Repo", "Api", "Endpoint",
)

# Directory / module names that name no business capability. LOW contribution
# and `s1_generic_name` (BrownKit's own list, extended with the container
# directories a monorepo adds).
GENERIC_NAMES: frozenset[str] = frozenset({
    "util", "utils", "common", "core", "lib", "libs", "helper", "helpers",
    "shared", "misc", "base", "internal", "pkg", "src", "app", "apps",
    "packages", "modules", "code", "scripts", "tools", "vendor", "third_party",
})

# Names that describe a technical layer. Also LOW, but a DIFFERENT rule
# (`s1_layer_name`), because E-48's guardrail -- "delivery channels and
# deployment boundaries are not capabilities" -- needs the distinction, not
# just its outcome (SourceCandidate's docstring).
LAYER_NAMES: frozenset[str] = frozenset({
    "controller", "controllers", "service", "services", "repository",
    "repositories", "model", "models", "dto", "dtos", "api", "apis",
    "handler", "handlers", "route", "routes", "router", "routers", "view",
    "views", "serializer", "serializers", "middleware", "adapter", "adapters",
    "interface", "interfaces", "schema", "schemas", "entity", "entities",
    "config", "configs", "migration", "migrations", "test", "tests",
    "mapper", "mappers", "dao", "daos", "resource", "resources",
    # Delivery channels. E-48's guardrail names them explicitly: "delivery
    # channels and deployment boundaries are not capabilities", so a file
    # called cli.py or server.js names the channel, not the operation, and
    # S3 falls back to its parent directory.
    "cli", "server", "index", "main", "worker", "consumer", "job", "jobs",
})


def singularize(word: str) -> str:
    """English singularization, deliberately small: the rules that fire on
    real identifiers and nothing more. Over-reaching here would collapse
    unrelated names into one merge key, which is worse than missing a merge
    (D9 rule 2 -- S5 never has to be right, only never silently wrong)."""
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    for group in ("sses", "shes", "ches", "xes", "zes"):
        if len(word) > len(group) and word.endswith(group):
            return word[:-2]
    # 'ss' (address, class) and 'us' (status, virus, census) are not plural
    # markers: the first is already singular, the second is a Latin singular
    # whose trailing 's' is part of the stem. Stripping either invents a key
    # no source ever wrote (D9 rule 2).
    if (len(word) > 2 and word.endswith("s")
            and not word.endswith("ss") and not word.endswith("us")):
        return word[:-1]
    return word


def head_token(name: str) -> str:
    """The leading camelCase / snake_case token of an identifier.

    S3 groups on this, because suffix-stripping alone does not reach D9's
    worked example: 'PaymentSettlementJob' loses only 'Job' and lands on
    'PaymentSettlement', which shares no key with 'PaymentController'. The
    head token is what those three names actually agree on.

    An acronym run counts as one token ('HTTPServer' -> 'HTTP'), so a name
    is never split mid-initialism.
    """
    first = name.strip().replace("-", "_").split("_")[0]
    if not first:
        return name.strip()
    out = [first[0]]
    for index, char in enumerate(first[1:], start=1):
        previous = first[index - 1]
        starts_word = char.isupper() and (
            previous.islower()                       # payMent
            or (index + 1 < len(first) and first[index + 1].islower()))
        if starts_word:                              # HTTPServer -> HTTP
            break
        out.append(char)
    return "".join(out)


def _strip_layer_suffix(name: str) -> str:
    """Strip the LONGEST matching layer suffix, never the first declared.

    Longest-match rather than first-match so the tuple's order cannot change
    behaviour: 'StringUtils' stripped of 'Util' leaves a trailing 's' that
    singularize would then eat, reaching the same answer by luck rather than
    by rule.
    """
    lowered = name.lower()
    matches = [s for s in LAYER_SUFFIXES
               if lowered.endswith(s.lower()) and len(name) > len(s)]
    if not matches:
        return name
    return name[: -len(max(matches, key=len))]


def normalize(name: str) -> str:
    """The normalized form two candidates must share to be merged."""
    out = _strip_layer_suffix(name.strip())
    out = out.strip("_-").lower()
    return singularize(out)
