from sdlc.memory.models import MemoryKind
from sdlc.memory.promote import GOTCHA_QUERY, promotions


def test_same_gotcha_in_two_banks_promotes_once():
    items = promotions(
        {"project:a": ["uv run pytest, not pytest"], "project:b": ["uv run pytest, not pytest"]},
        org_bank="org",
    )
    assert len(items) == 1
    assert items[0].bank == "org"
    assert items[0].kind is MemoryKind.GOTCHA
    assert items[0].metadata == {"promoted_from": "project:a,project:b"}


def test_one_bank_twice_does_not_promote():
    assert promotions({"project:a": ["x", "x"]}, org_bank="org") == []


def test_normalization_groups_case_and_punctuation_variants():
    items = promotions(
        {"project:a": ["UV run pytest!"], "project:b": ["uv run pytest"]}, org_bank="org"
    )
    assert len(items) == 1
    assert items[0].text == "UV run pytest!"  # lexicographically smallest RAW text


def test_single_project_never_promotes():
    assert promotions({"project:a": ["x"], "project:b": []}, org_bank="org") == []


def test_min_projects_three_requires_three_banks():
    two = {"project:a": ["x"], "project:b": ["x"]}
    assert promotions(two, org_bank="org", min_projects=3) == []


def test_identical_input_yields_identical_output():
    src = {"project:b": ["zeta", "alpha"], "project:a": ["alpha", "zeta"]}
    assert promotions(src, org_bank="org") == promotions(src, org_bank="org")


def test_result_is_sorted_by_text():
    items = promotions(
        {"project:a": ["b-item", "a-item"], "project:b": ["a-item", "b-item"]}, org_bank="org"
    )
    assert [i.text for i in items] == ["a-item", "b-item"]


def test_gotcha_query_is_pinned():
    assert GOTCHA_QUERY == "recurring cross-project gotchas and stack knowledge"
