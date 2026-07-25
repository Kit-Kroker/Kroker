"""E-17: grants are single-use by construction, and a declined escalation is
distinguishable from an ordinary denial."""
import json

from sdlc.harness.containment import (
    ESCALATION_UNAVAILABLE, digest_tool_input, is_declined_reason,
    load_grants, match_grant,
)
from sdlc.models import ToolGrant

INPUT = {"file_path": "/etc/passwd", "content": "x"}


def _grant(**over) -> ToolGrant:
    base = dict(tool_use_id="toolu_1", tool="Write",
                input_digest=digest_tool_input(INPUT),
                rule_id="no-out-of-worktree-write", approved=True,
                reason="ok")
    return ToolGrant(**{**base, **over})


def test_digest_is_stable_across_key_order():
    a = digest_tool_input({"a": 1, "b": [1, 2]})
    b = digest_tool_input({"b": [1, 2], "a": 1})
    assert a == b


def test_digest_changes_with_content():
    assert (digest_tool_input({"file_path": "/a"})
            != digest_tool_input({"file_path": "/b"}))


def test_matching_grant_is_returned():
    g = _grant()
    assert match_grant([g], "Write", "toolu_1", INPUT) is g


def test_a_different_tool_use_id_never_matches():
    """This is what makes the grant single-use: the replay reuses the id, a
    genuinely new call gets a fresh one."""
    assert match_grant([_grant()], "Write", "toolu_2", INPUT) is None


def test_a_mutated_input_never_matches():
    """Belt to tool_use_id's suspenders: the same id must not carry a
    different payload through."""
    other = {**INPUT, "content": "rm -rf /"}
    assert match_grant([_grant()], "Write", "toolu_1", other) is None


def test_a_different_tool_never_matches():
    assert match_grant([_grant()], "Bash", "toolu_1", INPUT) is None


def test_rejecting_grants_match_too():
    """A rejection must be DELIVERED, not merely recorded."""
    g = _grant(approved=False, reason="no")
    assert match_grant([g], "Write", "toolu_1", INPUT) is g


def test_load_grants_reads_a_json_array(tmp_path):
    p = tmp_path / "g.json"
    p.write_text(json.dumps([_grant().model_dump()]), encoding="utf-8")
    loaded = load_grants(p)
    assert len(loaded) == 1
    assert loaded[0].tool_use_id == "toolu_1"


def test_load_grants_is_empty_without_a_path():
    assert load_grants(None) == []


def test_load_grants_is_empty_for_a_missing_file(tmp_path):
    """A missing grants file means 'no decisions yet', never a crash — and
    an escalate rule with no grant escalates, which is the safe direction."""
    assert load_grants(tmp_path / "absent.json") == []


def test_declined_marker_round_trips():
    text = f"{ESCALATION_UNAVAILABLE} (batched): Writes are scoped."
    assert is_declined_reason(text) is True
    assert is_declined_reason("Writes are scoped.") is False
