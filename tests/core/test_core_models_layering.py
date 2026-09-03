import ast
import pathlib

CORE = pathlib.Path("src/sdlc/core")
FORBIDDEN = {"stages", "harness", "memory", "board", "schedules", "measurement"}


def _relative_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            yield (node.module or "").split(".")[0]


def test_core_imports_nothing_from_stages_or_horizontal_packages():
    offenders = [
        (p.name, mod) for p in CORE.glob("*.py") for mod in _relative_imports(p) if mod in FORBIDDEN
    ]
    assert offenders == [], f"Rule 5 violated: {offenders}"


def test_pipeline_config_and_its_configs_are_all_in_core():
    from sdlc.core.models import PipelineConfig

    for field in ("gates", "benchmark", "roles", "memory", "research", "deploy", "containment"):
        anno = PipelineConfig.model_fields[field].annotation
        assert "sdlc.core.models" in str(anno) or anno.__module__ == "sdlc.core.models", field


def test_role_usage_is_core():
    # Rule 5 forces it: RunSummary.roles and RunState.roles reference it.
    from sdlc.core.models import RoleUsage, RunState, RunSummary

    assert RoleUsage.__module__ == "sdlc.core.models"
    assert RunSummary is not None and RunState is not None
