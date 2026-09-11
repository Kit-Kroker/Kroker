"""F2 doctor: placeholder classification (spec section 7).

Detection is scoped to the keys rows 7 and 10 resolve -- NEVER the whole
environment. .env.example ships working defaults beside its placeholders
(TEMPORAL_HOST=localhost:7233, SDLC_MEMORY_BACKEND=hindsight), and a blanket
"equals the shipped value" rule would flag every one of them.
"""

from sdlc.doctor.env import classify_key, parse_env_example


def _write(tmp_path, text):
    (tmp_path / ".env.example").write_text(text, encoding="utf-8")
    return tmp_path


def test_parses_key_value_pairs_ignoring_comments_and_blanks(tmp_path):
    root = _write(
        tmp_path,
        "# a comment\n\nANTHROPIC_API_KEY=your-zai-api-key\nGH_TOKEN=your-github-token\n",
    )
    assert parse_env_example(root) == {
        "ANTHROPIC_API_KEY": "your-zai-api-key",
        "GH_TOKEN": "your-github-token",
    }


def test_strips_surrounding_quotes(tmp_path):
    root = _write(tmp_path, "GH_TOKEN='your-github-token'\n")
    assert parse_env_example(root)["GH_TOKEN"] == "your-github-token"


def test_missing_file_yields_an_empty_map_rather_than_raising(tmp_path):
    """A wheel install or worker image may carry no .env.example. Tier 1
    degrades to nothing; tier 2 still applies."""
    assert parse_env_example(tmp_path) == {}


def test_unset_key_is_not_usable():
    ok, reason = classify_key("GH_TOKEN", shipped={}, environ={})
    assert ok is False
    assert "not set" in reason


def test_empty_and_whitespace_only_values_are_not_usable():
    ok, reason = classify_key("GH_TOKEN", shipped={}, environ={"GH_TOKEN": "   "})
    assert ok is False
    assert "empty" in reason


def test_tier_one_flags_a_value_copied_from_env_example():
    ok, reason = classify_key(
        "GH_TOKEN",
        shipped={"GH_TOKEN": "your-github-token"},
        environ={"GH_TOKEN": "your-github-token"},
    )
    assert ok is False
    assert ".env.example" in reason
    assert "your-github-token" in reason


def test_tier_two_floor_catches_a_stub_env_example_does_not_ship():
    """tests/conftest.py:21-23 sets ANTHROPIC_API_KEY=test-dummy, which
    .env.example never ships -- tier 1 alone would call it a real key."""
    ok, reason = classify_key(
        "ANTHROPIC_API_KEY", shipped={}, environ={"ANTHROPIC_API_KEY": "test-dummy"}
    )
    assert ok is False
    assert "placeholder" in reason


def test_tier_two_floor_catches_any_your_prefixed_value():
    ok, reason = classify_key(
        "TAVILY_API_KEY", shipped={}, environ={"TAVILY_API_KEY": "your-new-service-key"}
    )
    assert ok is False
    assert "placeholder" in reason


def test_a_real_looking_value_is_usable():
    ok, reason = classify_key(
        "GH_TOKEN",
        shipped={"GH_TOKEN": "your-github-token"},
        environ={"GH_TOKEN": "ghp_realtokenvalue123"},
    )
    assert ok is True
    assert reason == ""


def test_a_working_default_shipped_by_env_example_is_not_a_placeholder():
    """THE false-positive this scoping exists to prevent: TEMPORAL_HOST's
    shipped value is the correct value. classify_key is only ever called on
    the credential keys rows 7 and 10 resolve, but if it were called here it
    must still not fire on the tier-2 floor."""
    ok, _ = classify_key(
        "TEMPORAL_HOST",
        shipped={},
        environ={"TEMPORAL_HOST": "localhost:7233"},
    )
    assert ok is True
