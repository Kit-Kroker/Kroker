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
import shutil
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


ATTRIBUTION = """\
# Attribution

This benchmark case is derived from **DevEval**.

> Bowen Li, Wenhan Wu, Ziwei Tang, Lin Shi, John Yang, Jinyang Li, Shunyu
> Yao, Chen Qian, Binyuan Hui, Qicheng Zhang, Zhiyin Yu, He Du, Ping Yang,
> Dahua Lin, Chao Peng, Kai Chen. "Prompting Large Language Models to Tackle
> the Full Software Development Lifecycle: A Case Study." COLING 2025,
> pages 7511-7531.

Source: https://github.com/open-compass/DevEval
Source repository: `benchmark_data/{language}/{repo_name}`
Dataset licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)

Converted by `sdlc benchmark import-deveval` (E-79). The PRD, UML diagrams,
architecture design, reference implementation, and test suites are the
original authors' work, reorganised into this repository's case layout.
"""

# Never copied into reference/: docs are inputs, tests are the oracle, and
# DevEval's own scaffolding is not part of the gold implementation.
_REFERENCE_EXCLUDES = {
    "docs", "examples", "repo_config.json", "setup_shell_script.sh",
    "README.md", "__pycache__", ".git", ".gitignore",
}


class ImportReport(BaseModel):
    case_id: str
    source_repo: str
    network_required: bool
    network_evidence: list[str] = Field(default_factory=list)
    n_tasks: int
    n_oracle_tests: int
    reference_files: int


def _copy_tree(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def convert_repo(src: Path, dest_root: Path, *,
                 judge_model: str) -> ImportReport:
    """Convert one DevEval repository into a Kroker case directory.

    Fails loud: a missing declared path, a malformed manifest, or an existing
    destination raises rather than emitting a half-built case.
    """
    src = Path(src)
    cfg = load_repo_config(src)
    repo_name = src.name
    case_id = case_id_for(repo_name)
    case_dir = Path(dest_root) / case_id
    if case_dir.exists():
        raise FileExistsError(
            f"{case_dir} already exists; delete it to re-import")

    unit_src = src / cfg.unit_tests
    accept_src = src / cfg.acceptance_tests
    for required in (src / cfg.prd, src / cfg.uml_class,
                     src / cfg.uml_sequence, src / cfg.architecture_design,
                     src / cfg.dependencies, unit_src, accept_src):
        if not required.exists():
            raise FileNotFoundError(f"{repo_name}: declared path missing: "
                                    f"{required}")

    case_dir.mkdir(parents=True)

    # oracle/ -- both tiers, subdirs preserved so node-ids stay stable
    _copy_tree(unit_src, case_dir / "oracle" / cfg.unit_tests)
    _copy_tree(accept_src, case_dir / "oracle" / cfg.acceptance_tests)

    # reference_artifacts/ -- E-80's pinning input
    ra = case_dir / "reference_artifacts"
    ra.mkdir()
    for label, rel in (("UML_class.md", cfg.uml_class),
                       ("UML_sequence.md", cfg.uml_sequence),
                       ("architecture_design.md", cfg.architecture_design)):
        shutil.copyfile(src / rel, ra / label)

    # reference_env/ -- imported now, consumed by a future env-setup metric
    re_dir = case_dir / "reference_env"
    re_dir.mkdir()
    shutil.copyfile(src / cfg.dependencies, re_dir / "requirements.txt")
    if cfg.usage_examples and (src / cfg.usage_examples).is_dir():
        _copy_tree(src / cfg.usage_examples, re_dir / "examples")

    # reference/ -- E-81's gold implementation
    ref = case_dir / "reference"
    ref.mkdir()
    reference_files = 0
    skip = _REFERENCE_EXCLUDES | {cfg.unit_tests, cfg.acceptance_tests,
                                  cfg.usage_examples or ""}
    for entry in sorted(src.iterdir()):
        if entry.name in skip:
            continue
        if entry.is_dir():
            _copy_tree(entry, ref / entry.name)
            reference_files += sum(1 for p in (ref / entry.name).rglob("*")
                                   if p.is_file())
        else:
            shutil.copyfile(entry, ref / entry.name)
            reference_files += 1

    node_ids = (collect_node_ids(case_dir / "oracle" / cfg.unit_tests,
                                 cfg.unit_tests)
                + collect_node_ids(case_dir / "oracle" / cfg.acceptance_tests,
                                   cfg.acceptance_tests))
    suite = draft_task_suite(sorted(node_ids))
    (case_dir / "tasks.yaml").write_text(
        render_tasks_yaml(suite), encoding="utf-8")

    scanned = (sorted((case_dir / "oracle").rglob("*.py"))
               + sorted(ref.rglob("*.py")))
    network_required, evidence = detect_network(scanned)

    contract = frozen_contract(
        (ra / "architecture_design.md").read_text(encoding="utf-8"),
        (ra / "UML_class.md").read_text(encoding="utf-8"))
    case = build_case_dict(
        case_id=case_id, prd=(src / cfg.prd).read_text(encoding="utf-8"),
        contract=contract, language=cfg.language, judge_model=judge_model,
        network_required=network_required,
        repo_url=f"/srv/scratch-repos/{case_id}")
    (case_dir / "case.yaml").write_text(
        render_case_yaml(case), encoding="utf-8")
    (case_dir / "ATTRIBUTION.md").write_text(
        ATTRIBUTION.format(language=cfg.language, repo_name=repo_name),
        encoding="utf-8")

    return ImportReport(
        case_id=case_id, source_repo=repo_name,
        network_required=network_required, network_evidence=evidence,
        n_tasks=len(suite["tasks"]), n_oracle_tests=len(node_ids),
        reference_files=reference_files)
