"""The file-size ratchet (B0 §2.3).

Every test here drives the pure core -- physical_lines, is_checked,
evaluate -- so none of them touch git or write to the tree.
"""

from __future__ import annotations

from scripts.check_file_size import CEILING, evaluate, is_checked, physical_lines


def test_physical_lines_counts_a_final_unterminated_line():
    # The reason `wc -l` is not an implementation of the spec's definition:
    # it counts newlines, so it reports 1 for the second case, not 2.
    assert physical_lines(b"a\nb\n") == 2
    assert physical_lines(b"a\nb") == 2


def test_physical_lines_of_empty_file_is_zero():
    assert physical_lines(b"") == 0


def test_physical_lines_returns_none_for_binary():
    assert physical_lines(b"pre\x00post") is None


def test_in_scope_paths_are_checked():
    assert is_checked("src/sdlc/workflows/feature.py")
    assert is_checked("tests/test_something.py")
    assert is_checked("scripts/check_file_size.py")
    assert is_checked("docs/features/clarify.md")
    assert is_checked("ROADMAP.md")


def test_write_once_records_are_exempt():
    assert not is_checked("docs/superpowers/plans/2026-08-31-crew-step-2.md")
    assert not is_checked("docs/superpowers/specs/2026-09-01-e50-design.md")


def test_verbatim_vendored_data_is_exempt():
    assert not is_checked("tests/fixtures/hindsight-openapi.json")
    assert not is_checked(
        "benchmarks/cases/deveval-geotext/reference/geotext/data_file/cities15000.txt"
    )


def test_generated_and_machine_managed_files_are_exempt():
    assert not is_checked("docs/roadmap.html")
    assert not is_checked("docs/schemas/roadmap.html")
    assert not is_checked("records/2026-07-12-factory-console/support.js")
    assert not is_checked("uv.lock")
    assert not is_checked("interfaces/dashboard/frontend/package-lock.json")


def test_benchmark_corpus_is_out_but_its_reader_is_in():
    assert not is_checked("benchmarks/cases/cat-cafe-monitoring/oracle/test_risk.py")
    assert is_checked("src/sdlc/benchmarks/importers/deveval.py")


def test_new_file_over_the_ceiling_is_rejected():
    errors, baseline = evaluate({"src/new.py": CEILING + 1}, {}, prune=False)
    assert errors and "src/new.py" in errors[0]
    assert baseline == {}


def test_new_file_under_the_ceiling_passes():
    errors, baseline = evaluate({"src/new.py": CEILING}, {}, prune=False)
    assert errors == []
    assert baseline == {}


def test_baselined_file_that_grew_is_rejected():
    errors, baseline = evaluate(
        {"src/sdlc/activities.py": 1431}, {"src/sdlc/activities.py": 1430}, prune=False
    )
    assert errors and "grew" in errors[0]
    assert baseline == {"src/sdlc/activities.py": 1430}


def test_baselined_file_held_at_its_size_passes():
    errors, baseline = evaluate(
        {"src/sdlc/activities.py": 1430}, {"src/sdlc/activities.py": 1430}, prune=False
    )
    assert errors == []
    assert baseline == {"src/sdlc/activities.py": 1430}


def test_baselined_file_that_shrank_tightens_its_entry():
    errors, baseline = evaluate(
        {"src/sdlc/activities.py": 1200}, {"src/sdlc/activities.py": 1430}, prune=False
    )
    assert errors == []
    assert baseline == {"src/sdlc/activities.py": 1200}


def test_baselined_file_that_dropped_under_the_ceiling_leaves_the_baseline():
    errors, baseline = evaluate({"ROADMAP.md": 500}, {"ROADMAP.md": 1647}, prune=False)
    assert errors == []
    assert baseline == {}


def test_prune_drops_entries_for_files_that_are_gone():
    errors, baseline = evaluate(
        {"src/sdlc/activities.py": 1430},
        {"src/sdlc/activities.py": 1430, "src/sdlc/deleted.py": 1100},
        prune=True,
    )
    assert errors == []
    assert baseline == {"src/sdlc/activities.py": 1430}


def test_without_prune_an_unseen_entry_survives():
    # The hook only sees staged files, so absence is not evidence of deletion.
    errors, baseline = evaluate({}, {"src/sdlc/activities.py": 1430}, prune=False)
    assert errors == []
    assert baseline == {"src/sdlc/activities.py": 1430}
