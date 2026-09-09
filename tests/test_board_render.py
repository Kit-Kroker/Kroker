"""Board artifact -> Markdown renderer (F4)."""

from datetime import UTC, datetime

import pytest

from sdlc.board.models import ArtifactVersion
from sdlc.board.render import (
    MAX_RENDER_BYTES,
    RENDER_VERSION,
    ArtifactTooLarge,
    ArtifactUnreadable,
    UnknownArtifactKey,
    render_version_markdown,
)
from sdlc.core.models import ClarificationDimension
from sdlc.stages.clarify.models import ClarifiedRequirements, OpenQuestion


def version(n: int = 3, vid: int = 41) -> ArtifactVersion:
    return ArtifactVersion(
        id=vid,
        project="acme",
        key="requirements",
        n=n,
        run_id="run-xyz",
        sha256="9f2c" + "0" * 60,
        uri="file:///tmp/x.json",
        created_at=datetime(2026, 9, 9, 8, 14, 2, tzinfo=UTC),
    )


def full_requirements() -> ClarifiedRequirements:
    return ClarifiedRequirements(
        summary="SENTINEL_SUMMARY",
        functional_requirements=["SENTINEL_FR"],
        non_functional_requirements=["SENTINEL_NFR"],
        out_of_scope=["SENTINEL_OOS"],
        dimensions_probed=[ClarificationDimension.FUNCTIONAL_INTENT],
        open_questions=[
            OpenQuestion(
                id="SENTINEL_QID",
                question="SENTINEL_QUESTION",
                why_it_matters="SENTINEL_WHY",
                suggested_answer="SENTINEL_SUGGESTED",
                answer="SENTINEL_ANSWER",
                dimension=ClarificationDimension.BUSINESS_SEMANTICS,
                asked_by="SENTINEL_ASKEDBY",
                materiality=0.75,
                evidence="SENTINEL_EVIDENCE",
            )
        ],
        dropped=[
            OpenQuestion(
                id="SENTINEL_DROPPED_ID",
                question="SENTINEL_DROPPED_Q",
                why_it_matters="SENTINEL_DROPPED_WHY",
            )
        ],
    )


def render_requirements(model: ClarifiedRequirements) -> str:
    return render_version_markdown(
        "requirements",
        model.model_dump_json().encode("utf-8"),
        project="acme",
        version=version(),
    )


def test_banner_carries_provenance():
    out = render_requirements(full_requirements())
    assert out.startswith("# Requirements -- acme")
    assert "| artifact | requirements |" in out
    assert "| version | 3 (id 41) |" in out
    assert "| run | run-xyz |" in out
    assert "2026-09-09T08:14:02" in out
    assert "9f2c" in out


def test_requirements_body_renders_every_section():
    out = render_requirements(full_requirements())
    for sentinel in (
        "SENTINEL_SUMMARY",
        "SENTINEL_FR",
        "SENTINEL_NFR",
        "SENTINEL_OOS",
        "SENTINEL_QUESTION",
        "SENTINEL_WHY",
        "SENTINEL_SUGGESTED",
        "SENTINEL_ANSWER",
        "SENTINEL_ASKEDBY",
        "SENTINEL_EVIDENCE",
    ):
        assert sentinel in out, sentinel


def test_dropped_questions_render_under_their_own_heading():
    out = render_requirements(full_requirements())
    assert "SENTINEL_DROPPED_Q" in out
    head = out.index("Dropped")
    assert out.index("SENTINEL_DROPPED_Q") > head


def test_answered_and_unanswered_questions_are_distinguishable():
    # Anchored on the "-- " separator deliberately: "ANSWERED" is a
    # substring of "UNANSWERED", so a bare check would pass even if every
    # question rendered as unanswered.
    out = render_requirements(full_requirements())
    assert "-- ANSWERED" in out
    assert "-- UNANSWERED" in out


def test_renderer_scaffolding_is_ascii():
    # ASCII fixtures in, ASCII out: this pins the renderer's own literals.
    out = render_requirements(full_requirements())
    assert out.isascii()


def test_artifact_content_is_not_transliterated():
    model = full_requirements()
    model.summary = "café naïve"
    out = render_requirements(model)
    assert "café naïve" in out


def test_empty_collections_do_not_produce_dangling_headings():
    model = ClarifiedRequirements(
        summary="s",
        functional_requirements=[],
        non_functional_requirements=[],
        out_of_scope=[],
        open_questions=[],
    )
    out = render_requirements(model)
    assert "(none)" in out
    assert "\n\n\n\n" not in out


def test_unknown_key_is_refused():
    with pytest.raises(UnknownArtifactKey) as e:
        render_version_markdown("nope", b"{}", project="acme", version=version())
    assert "requirements" in str(e.value)


def test_oversize_blob_is_refused_before_parsing():
    with pytest.raises(ArtifactTooLarge):
        render_version_markdown(
            "requirements",
            b"x" * (MAX_RENDER_BYTES + 1),
            project="acme",
            version=version(),
        )


@pytest.mark.parametrize("raw", [b"not json at all", b'{"summary": "a", "trunc', b"\xff\xfe{}"])
def test_unparseable_bytes_raise_one_error_type(raw):
    # model_validate_json collapses malformed JSON and bad UTF-8 into
    # ValidationError; nothing else may escape.
    with pytest.raises(ArtifactUnreadable):
        render_version_markdown("requirements", raw, project="acme", version=version())


def test_schema_drift_raises_the_same_error():
    with pytest.raises(ArtifactUnreadable) as e:
        render_version_markdown(
            "requirements",
            b'{"summary": "only this"}',
            project="acme",
            version=version(),
        )
    assert "ClarifiedRequirements" in str(e.value)


def test_render_version_is_an_int():
    assert isinstance(RENDER_VERSION, int)


def test_render_cap_matches_the_json_route_cap():
    # Pinned deliberately: board/api.py defines its own MAX_CONTENT_BYTES and
    # render.py cannot import it without a cycle.
    from sdlc.board import api as api_mod

    assert MAX_RENDER_BYTES == api_mod.MAX_CONTENT_BYTES


from sdlc.stages.architecture.models import ArchitectureDecision, ArchitectureSpec
from sdlc.stages.context.models import BrownfieldDelta


def full_architecture() -> ArchitectureSpec:
    return ArchitectureSpec(
        overview="SENTINEL_OVERVIEW",
        confidence=0.82,
        decisions=[
            ArchitectureDecision(
                id="SENTINEL_DID",
                decision="SENTINEL_DECISION",
                rationale="SENTINEL_RATIONALE",
                alternatives_considered=["SENTINEL_ALT"],
            )
        ],
        new_components=["SENTINEL_NEWCOMP"],
        risks=["SENTINEL_RISK"],
        delta=BrownfieldDelta(
            added=["SENTINEL_ADDED"],
            modified=["SENTINEL_MODIFIED"],
            removed=["SENTINEL_REMOVED"],
        ),
    )


def render_architecture(model: ArchitectureSpec) -> str:
    v = version()
    v.key = "architecture"
    return render_version_markdown(
        "architecture",
        model.model_dump_json().encode("utf-8"),
        project="acme",
        version=v,
    )


def test_architecture_body_renders_every_section():
    out = render_architecture(full_architecture())
    for sentinel in (
        "SENTINEL_OVERVIEW",
        "SENTINEL_DID",
        "SENTINEL_DECISION",
        "SENTINEL_RATIONALE",
        "SENTINEL_ALT",
        "SENTINEL_NEWCOMP",
        "SENTINEL_RISK",
        "SENTINEL_ADDED",
        "SENTINEL_MODIFIED",
        "SENTINEL_REMOVED",
    ):
        assert sentinel in out, sentinel


def test_architecture_confidence_renders_as_a_percentage():
    assert "82%" in render_architecture(full_architecture())


def test_architecture_delta_separates_added_modified_removed():
    # Delta-scoped probes, not bare index(): the validator derives
    # affected_modules from delta.modified | delta.removed
    # (architecture/models.py:38-42) and the Affected modules section
    # renders BEFORE the delta, so SENTINEL_MODIFIED's first occurrence
    # would otherwise precede SENTINEL_ADDED and a bare ordering check
    # can never pass. Same anchoring as _EXPECTED below.
    out = render_architecture(full_architecture())
    assert "added:\n- SENTINEL_ADDED" in out
    assert "modified:\n- SENTINEL_MODIFIED" in out
    assert "removed:\n- SENTINEL_REMOVED" in out
    assert out.index("added:") < out.index("modified:") < out.index("removed:")


def test_architecture_without_delta_says_so():
    model = ArchitectureSpec(overview="o", decisions=[])
    out = render_architecture(model)
    assert "greenfield" in out
    assert "not recorded" in out  # confidence is None


from sdlc.stages.architecture.models import ValidationContract
from sdlc.stages.plan.models import DevTask, ImplementationPlan


def full_plan() -> ImplementationPlan:
    return ImplementationPlan(
        confidence=0.5,
        tasks=[
            DevTask(
                id="SENTINEL_TID",
                title="SENTINEL_TITLE",
                description="SENTINEL_DESC",
                depends_on=["SENTINEL_DEP"],
                acceptance_criteria=["SENTINEL_AC"],
                files_hint=["SENTINEL_HINT"],
                overlaps=["SENTINEL_OVERLAP"],
                role="devops",
                contract=ValidationContract(
                    task_id="SENTINEL_TID",
                    assertions=["SENTINEL_ASSERTION"],
                    test_commands=["SENTINEL_TESTCMD"],
                    lint_commands=["SENTINEL_LINTCMD"],
                    stack="SENTINEL_STACK",
                ),
            )
        ],
    )


def render_plan(model: ImplementationPlan) -> str:
    v = version()
    v.key = "plan"
    return render_version_markdown(
        "plan", model.model_dump_json().encode("utf-8"), project="acme", version=v
    )


def test_plan_body_renders_every_section():
    out = render_plan(full_plan())
    for sentinel in (
        "SENTINEL_TID",
        "SENTINEL_TITLE",
        "SENTINEL_DESC",
        "SENTINEL_DEP",
        "SENTINEL_AC",
        "SENTINEL_HINT",
        "SENTINEL_OVERLAP",
        "SENTINEL_ASSERTION",
        "SENTINEL_TESTCMD",
        "SENTINEL_LINTCMD",
        "SENTINEL_STACK",
    ):
        assert sentinel in out, sentinel


def test_plan_role_renders_under_a_label():
    # role has a closed vocabulary, so a bare substring check would pass
    # even if the field were dropped. The label is the anchor.
    assert "role: devops" in render_plan(full_plan())


def test_plan_reports_its_task_count():
    assert "1 task(s)" in render_plan(full_plan())


def test_plan_without_tasks_renders_cleanly():
    out = render_plan(ImplementationPlan(tasks=[]))
    assert "0 task(s)" in out
    assert "(none)" in out


def test_task_without_a_contract_says_so():
    plan = full_plan()
    plan.tasks[0].contract = None
    assert "validation contract: (none)" in render_plan(plan)
