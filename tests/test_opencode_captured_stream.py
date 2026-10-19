"""FR-041 chaos/robustness seat: the scrubbed REAL capture must parse
identically despite every redaction -- the parser is indifferent to the
placeholders, not dependent on their absence.

Fixture: tests/fixtures/opencode/bench-todo-api-greenfield-1792335476-
T-001-a1.jsonl -- round-016 R0 smoke, todo-api T-001 attempt 1, opencode
1.18.35 --format json; scrubbed (paths -> <worktrees>/..., user value ->
<user>, session ids -> <session-id>, part.time "start" keys -> "<user>").

These are PINNING tests: spec FR-3 expects no parser change, so
GREEN is the expected outcome. A genuinely RED test is a parser-gap
finding: leave it failing, report it, never weaken it.
"""

from collections import Counter
from pathlib import Path

from sdlc.harness.opencode import OpenCodeHarness
from sdlc.harness.session import digest_of

CAPTURED = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "opencode"
    / "bench-todo-api-greenfield-1792335476-T-001-a1.jsonl"
).read_text(encoding="utf-8")


def test_scrubbed_session_id_survives_with_every_counted_event():
    # Every event carries sessionID "<session-id>"; the parser must return
    # it verbatim and still count the whole vocabulary: 5 model_turn +
    # 3 file_write + 4 command = 12 events (re-derived from the fixture:
    # lines 5/11/15/19/23 text, 6/7/8 write, 2/12/16/20 bash).
    s = OpenCodeHarness().normalise_session(CAPTURED)
    assert s.session_id == "<session-id>"
    assert len(s.events) == 12
    assert Counter(e.kind for e in s.events) == Counter(
        {"model_turn": 5, "file_write": 3, "command": 4}
    )


def test_part_time_redaction_is_not_load_bearing():
    # The scrub replaced each part.time "start" key with the user-value
    # placeholder. Restore the original key IN MEMORY (the fixture file is
    # never edited) and prove the parse is identical either way -- the
    # placeholder spelling is provably not load-bearing.
    restored = CAPTURED.replace('"time":{"<user>":', '"time":{"start":')
    assert restored != CAPTURED  # premise: the redacted spelling is present
    d_redacted = digest_of(OpenCodeHarness().normalise_session(CAPTURED))
    d_restored = digest_of(OpenCodeHarness().normalise_session(restored))
    assert d_redacted == d_restored


def test_scrubbed_path_prefixes_parse_as_write_targets():
    # file_write targets carry the <worktrees> placeholder prefix; assert
    # with startswith/basename, never full-path equality -- the parser must
    # be indifferent to the placeholder.
    s = OpenCodeHarness().normalise_session(CAPTURED)
    writes = [e for e in s.events if e.kind == "file_write"]
    assert len(writes) == 3
    assert all(
        (e.target or "").startswith("<worktrees>/bench-todo-api-greenfield-1792335476/")
        for e in writes
    )
    assert {(e.target or "").rsplit("/", 1)[-1] for e in writes} == {
        "requirements.txt",
        "requirements-dev.txt",
        ".gitignore",
    }


def test_real_exit_code_spelling_yields_zero_failed_commands():
    # The real 1.18.x spelling: state.status "completed" with the code in
    # state.metadata.exit -- all four bash calls exited 0, so every command
    # event carries exit_code 0 and the digest counts no failures.
    s = OpenCodeHarness().normalise_session(CAPTURED)
    commands = [e for e in s.events if e.kind == "command"]
    assert [e.exit_code for e in commands] == [0, 0, 0, 0]
    assert digest_of(s).failed_commands == 0


def test_normalise_and_digest_are_pure_over_the_same_text():
    # No hidden state: two full passes over the same captured text yield
    # identical sessions and identical digests.
    s1 = OpenCodeHarness().normalise_session(CAPTURED)
    s2 = OpenCodeHarness().normalise_session(CAPTURED)
    assert s1 == s2
    assert digest_of(s1) == digest_of(s2)
