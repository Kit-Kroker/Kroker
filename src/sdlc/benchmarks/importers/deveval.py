"""DevEval (COLING 2025, CC BY 4.0) -> Kroker benchmark cases (E-79).

Every DevEval repository ships a repo_config.json naming each artifact by
path, so conversion is a manifest read rather than a scrape. This module is
pure where it can be and confines its I/O to convert_repo.

Fails loud on every error path: the importer is offline, human-run, and
one-shot, so a malformed manifest should stop it rather than silently emit
a half-built case (the opposite of the graders' fail-safe discipline).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RepoConfig(BaseModel):
    """The subset of repo_config.json the import consumes. Unknown keys
    (DevEval's per-test prompt blobs) are ignored on purpose."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    prd: str = Field(alias="PRD")
    uml_class: str = Field(alias="UML_class")
    uml_sequence: str = Field(alias="UML_sequence")
    architecture_design: str
    dependencies: str
    language: str
    unit_tests: str
    acceptance_tests: str
    usage_examples: str | None = None
    unit_test_linking: dict[str, list[str]] = Field(default_factory=dict)
    code_file_dag: dict[str, list[str]] = Field(
        default_factory=dict, alias="code_file_DAG")


def load_repo_config(repo_dir: Path) -> RepoConfig:
    """Read <repo_dir>/repo_config.json. Raises FileNotFoundError if absent
    and pydantic.ValidationError if a consumed key is missing."""
    path = Path(repo_dir) / "repo_config.json"
    if not path.is_file():
        raise FileNotFoundError(f"no repo_config.json in {repo_dir}")
    return RepoConfig(**json.loads(path.read_text(encoding="utf-8")))


def collect_node_ids(test_root: Path, prefix: str) -> list[str]:
    """Every `test_*` function and method under test_root, as JUnit node-ids
    relative to the oracle dir: "<prefix>/<relpath>::<name>".

    Parsed with ast rather than imported: these are third-party test files
    and importing them would execute module-level code. The prefix/separator
    shape must match grade_oracle's normalization (oracle.py:231), which
    strips the "oracle/" prefix and converts to forward slashes.

    Raises SyntaxError on an unparseable test file -- fail loud.
    """
    root = Path(test_root)
    out: list[str] = []
    for path in sorted(root.rglob("test_*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    names.append(node.name)
        out.extend(f"{prefix}/{rel}::{n}" for n in sorted(set(names)))
    return sorted(out)


DRAFT_BANNER = (
    "# DRAFT -- REVIEW BEFORE USE (E-79, spec 3.4).\n"
    "# Generated at test-FILE granularity from DevEval's unit_test_linking.\n"
    "# Functional completeness is requirement-weighted, so a human must\n"
    "# regroup these into real requirements and set each error_class.\n"
    "# Valid error_class values: functional, security, performance,\n"
    "# data_integrity, error_handling, api_contract.\n")


def _task_id(rel_file: str) -> str:
    """"unit_tests/test_check_date.py" -> "check_date"; a directory prefix is
    kept only when it is needed to keep ids unique (TaskSuite rejects dupes).
    """
    stem = Path(rel_file).stem
    return stem[len("test_"):] if stem.startswith("test_") else stem


def draft_task_suite(node_ids: list[str]) -> dict:
    """Group node-ids by test file into a draft tasks.yaml structure.

    Every task is emitted as error_class "functional" -- guessing a richer
    classification from a filename would produce confident, wrong error-class
    matrices. The human review pass sets these.
    """
    if not node_ids:
        raise ValueError("no oracle test node-ids; refusing to draft an "
                         "empty task suite")
    by_file: dict[str, list[str]] = {}
    for nid in node_ids:
        by_file.setdefault(nid.split("::", 1)[0], []).append(nid)

    stems = [_task_id(f) for f in sorted(by_file)]
    collide = {s for s in stems if stems.count(s) > 1}

    tasks = []
    for rel_file in sorted(by_file):
        base = _task_id(rel_file)
        if base in collide:
            parent = Path(rel_file).parent.as_posix().replace("/", "-")
            base = f"{parent}-{base}" if parent not in ("", ".") else base
        tasks.append({"id": base, "error_class": "functional",
                      "oracle_tests": sorted(by_file[rel_file])})
    return {"tasks": tasks}


def render_tasks_yaml(suite: dict) -> str:
    return DRAFT_BANNER + yaml.safe_dump(suite, sort_keys=False)


# Deliberately over-broad. A false positive quarantines a usable case; a
# false negative lets a benchmark cell make live egress under NFR-5. The
# asymmetry justifies the noise.
_NETWORK_MARKERS = re.compile(
    r"\b(urllib|requests|httpx|aiohttp|socket|urlopen|wget|curl)\b"
    r"|https?://",
    re.IGNORECASE)


def detect_network(paths: list[Path]) -> tuple[bool, list[str]]:
    """Scan files for signs the code reaches the network.

    Returns (required, evidence) where each evidence line is
    "<name>:<lineno>: <stripped source line>". Scans only the files given --
    callers pass oracle tests and reference sources, never docs, whose prose
    URLs would flag every case.
    """
    evidence: list[str] = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _NETWORK_MARKERS.search(line):
                evidence.append(f"{Path(path).name}:{i}: {line.strip()}")
    return bool(evidence), evidence


CONTRACT_TEMPLATE = """\
Interface contract (frozen -- graded through it; not a functional
requirement, and it changes none of the requirements above). The held-out
oracle imports these modules and calls these functions by name, so the
produced repository MUST match this file tree and these class and function
names exactly. Anything not named here is your choice.

Architecture (file tree):
{architecture}

Class structure:
{uml_class}
"""


def case_id_for(repo_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", repo_name.lower()).strip("-")
    return f"deveval-{slug}"


def frozen_contract(architecture_md: str, uml_class_md: str) -> str:
    return CONTRACT_TEMPLATE.format(
        architecture=architecture_md.strip(), uml_class=uml_class_md.strip())


def build_case_dict(*, case_id: str, prd: str, contract: str, language: str,
                    judge_model: str, network_required: bool,
                    repo_url: str) -> dict:
    """A CaseSpec-shaped dict. research_enabled is False: DevEval PRDs are
    already document-level, so a research stage would spend tokens
    re-deriving what the case already states."""
    summary = next(
        (ln.strip() for ln in prd.splitlines()
         if ln.strip() and not ln.startswith("#")),
        f"DevEval case {case_id}")
    return {
        "case_id": case_id,
        "idea_summary": summary[:200],
        "description": f"{prd.strip()}\n\n{contract}",
        "mode": "greenfield",
        "language": language,
        "repo_url": repo_url,
        "research_enabled": False,
        "network_required": network_required,
        "harnesses": ["opencode"],
        "models": ["zai-coding-plan/glm-5.2"],
        "judge_model": judge_model,
        "rubrics": {},
    }


def render_case_yaml(case: dict) -> str:
    return ("# Generated by `sdlc benchmark import-deveval` (E-79).\n"
            "# Source: open-compass/DevEval, dataset CC BY 4.0.\n"
            "# See ATTRIBUTION.md in this directory.\n"
            + yaml.safe_dump(case, sort_keys=False, allow_unicode=True))
