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


from typing import get_args

from pydantic import BaseModel

from sdlc.board.render import _OMITTED, RENDERERS

# Every (model, field) that IS rendered, mapped to a string that must appear
# in the rendered output of the fully-populated fixture. Adding a field to
# any artifact model fails test_no_field_is_silently_dropped until it is
# either listed here or added to _OMITTED.
#
# Free-text fields use their sentinel. Closed-vocabulary fields (role,
# dimension) must use a LABELLED anchor: "dev" and "test" occur incidentally
# in other output, so a bare value would pass even if the field were dropped.
_EXPECTED: dict[tuple[str, str], str] = {
    ("ClarifiedRequirements", "summary"): "SENTINEL_SUMMARY",
    ("ClarifiedRequirements", "functional_requirements"): "SENTINEL_FR",
    ("ClarifiedRequirements", "non_functional_requirements"): "SENTINEL_NFR",
    ("ClarifiedRequirements", "out_of_scope"): "SENTINEL_OOS",
    ("ClarifiedRequirements", "open_questions"): "SENTINEL_QUESTION",
    ("ClarifiedRequirements", "dimensions_probed"): "dimensions probed: C1",
    ("ClarifiedRequirements", "dropped"): "SENTINEL_DROPPED_Q",
    ("OpenQuestion", "id"): "SENTINEL_QID",
    ("OpenQuestion", "question"): "SENTINEL_QUESTION",
    ("OpenQuestion", "why_it_matters"): "SENTINEL_WHY",
    ("OpenQuestion", "suggested_answer"): "SENTINEL_SUGGESTED",
    ("OpenQuestion", "answer"): "SENTINEL_ANSWER",
    ("OpenQuestion", "dimension"): "dimension: C2",
    ("OpenQuestion", "asked_by"): "SENTINEL_ASKEDBY",
    ("OpenQuestion", "materiality"): "materiality: 0.75",
    ("OpenQuestion", "evidence"): "SENTINEL_EVIDENCE",
    ("ArchitectureSpec", "overview"): "SENTINEL_OVERVIEW",
    ("ArchitectureSpec", "decisions"): "SENTINEL_DECISION",
    # affected_modules is DERIVED from delta by ArchitectureSpec's validator
    # (architecture/models.py:28-42), so its sentinels also appear in the
    # delta section. Anchor on the heading or dropping either field would
    # still pass -- the same collision trap as `role` and `dimension`.
    ("ArchitectureSpec", "affected_modules"): "## Affected modules\n\n- SENTINEL_MODIFIED",
    ("ArchitectureSpec", "new_components"): "SENTINEL_NEWCOMP",
    ("ArchitectureSpec", "risks"): "SENTINEL_RISK",
    ("ArchitectureSpec", "confidence"): "82%",
    ("ArchitectureSpec", "delta"): "## Brownfield delta\n\nadded:",
    ("ArchitectureDecision", "id"): "SENTINEL_DID",
    ("ArchitectureDecision", "decision"): "SENTINEL_DECISION",
    ("ArchitectureDecision", "rationale"): "SENTINEL_RATIONALE",
    ("ArchitectureDecision", "alternatives_considered"): "SENTINEL_ALT",
    ("BrownfieldDelta", "added"): "added:\n- SENTINEL_ADDED",
    ("BrownfieldDelta", "modified"): "modified:\n- SENTINEL_MODIFIED",
    ("BrownfieldDelta", "removed"): "removed:\n- SENTINEL_REMOVED",
    ("ImplementationPlan", "tasks"): "SENTINEL_TID",
    ("ImplementationPlan", "confidence"): "50%",
    ("DevTask", "id"): "SENTINEL_TID",
    ("DevTask", "title"): "SENTINEL_TITLE",
    ("DevTask", "description"): "SENTINEL_DESC",
    ("DevTask", "depends_on"): "SENTINEL_DEP",
    ("DevTask", "acceptance_criteria"): "SENTINEL_AC",
    ("DevTask", "files_hint"): "SENTINEL_HINT",
    ("DevTask", "overlaps"): "SENTINEL_OVERLAP",
    ("DevTask", "contract"): "SENTINEL_ASSERTION",
    ("DevTask", "role"): "role: devops",
    ("ValidationContract", "assertions"): "SENTINEL_ASSERTION",
    ("ValidationContract", "test_commands"): "SENTINEL_TESTCMD",
    ("ValidationContract", "lint_commands"): "SENTINEL_LINTCMD",
    ("ValidationContract", "stack"): "SENTINEL_STACK",
}


def _model_types(anno) -> set[type[BaseModel]]:
    """Every BaseModel reachable through an annotation (list[X], X | None)."""
    found: set[type[BaseModel]] = set()
    if isinstance(anno, type) and issubclass(anno, BaseModel):
        found.add(anno)
    for arg in get_args(anno):
        found |= _model_types(arg)
    return found


def _walk(cls: type[BaseModel], seen: set[type[BaseModel]] | None = None):
    """cls plus every artifact model reachable through a RENDERED field.

    Omitted fields' subtrees are deliberately NOT walked. An omitted field's
    type is not part of the rendered surface, so its own fields cannot be
    "silently dropped" -- the whole field is dropped, on purpose, and that
    decision is already recorded in _OMITTED.

    Without this skip the walk reaches ArtifactRef through spec_ref and
    plan_ref, and then demands that ArtifactRef.kind/.uri/.sha256 be either
    rendered or omitted. Both ways out are wrong: rendering them contradicts
    section 4.3, and adding an "ArtifactRef" entry to _OMITTED breaks the
    pinned count of five. Skipping is the only correct answer, and it makes
    the walk return exactly the eight artifact models the spec names.
    """
    seen = seen if seen is not None else set()
    if cls in seen:
        return seen
    seen.add(cls)
    omitted = _OMITTED.get(cls.__name__, set())
    for name, f in cls.model_fields.items():
        if name in omitted:
            continue
        for nested in _model_types(f.annotation):
            _walk(nested, seen)
    return seen


def all_artifact_models() -> set[type[BaseModel]]:
    models: set[type[BaseModel]] = set()
    for model_cls, _ in RENDERERS.values():
        models |= _walk(model_cls)
    return models


def test_no_field_is_silently_dropped():
    """Every field of every artifact model is rendered or explicitly omitted.

    Recursion is what gives this teeth: DevTask's nine fields and
    OpenQuestion's nine are only reachable through nesting, and two of the
    three omissions sit two levels down in ValidationContract.
    """
    undeclared = []
    for model_cls in all_artifact_models():
        name = model_cls.__name__
        omitted = _OMITTED.get(name, set())
        for field in model_cls.model_fields:
            if field in omitted:
                continue
            if (name, field) not in _EXPECTED:
                undeclared.append(f"{name}.{field}")
    assert not undeclared, (
        "these artifact model fields are neither rendered nor in _OMITTED: "
        + ", ".join(sorted(undeclared))
        + " -- render them in board/render.py or record the omission"
    )


def test_every_declared_field_actually_reaches_the_output():
    rendered = "\n".join(
        [
            render_requirements(full_requirements()),
            render_architecture(full_architecture()),
            render_plan(full_plan()),
        ]
    )
    missing = [f"{m}.{f}" for (m, f), probe in _EXPECTED.items() if probe not in rendered]
    assert not missing, f"declared as rendered but absent from output: {missing}"


def test_omission_set_names_only_real_fields():
    by_name = {m.__name__: m for m in all_artifact_models()}
    for model_name, fields in _OMITTED.items():
        assert model_name in by_name, f"_OMITTED names unknown model {model_name}"
        for field in fields:
            assert field in by_name[model_name].model_fields, (
                f"_OMITTED names unknown field {model_name}.{field}"
            )


def test_the_omission_set_is_exactly_the_five_documented_entries():
    # Spec section 4.3. Growing this is a decision that belongs in the spec,
    # so it is pinned here rather than left to drift.
    assert sum(len(v) for v in _OMITTED.values()) == 5


def test_the_walk_reaches_exactly_the_eight_artifact_models():
    # Spec section 4.3 says eight. If ArtifactRef appears here, _walk has
    # stopped skipping omitted fields' subtrees and is walking into
    # claim-check plumbing.
    assert {m.__name__ for m in all_artifact_models()} == {
        "ClarifiedRequirements",
        "OpenQuestion",
        "ArchitectureSpec",
        "ArchitectureDecision",
        "BrownfieldDelta",
        "ImplementationPlan",
        "DevTask",
        "ValidationContract",
    }
