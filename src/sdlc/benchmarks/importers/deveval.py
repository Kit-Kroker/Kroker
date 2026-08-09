"""DevEval (COLING 2025, CC BY 4.0) -> Kroker benchmark cases (E-79).

Every DevEval repository ships a repo_config.json naming each artifact by
path, so conversion is a manifest read rather than a scrape. This module is
pure where it can be and confines its I/O to convert_repo.

Fails loud on every error path: the importer is offline, human-run, and
one-shot, so a malformed manifest should stop it rather than silently emit
a half-built case (the opposite of the graders' fail-safe discipline).
"""
from __future__ import annotations

import json
from pathlib import Path

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
