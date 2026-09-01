from sdlc.memory.query_hash import recall_query_hash


def test_hash_is_stable_across_filter_ordering():
    a = recall_query_hash("b", "q", {"stage": "clarify", "gate": "g"}, "5")
    b = recall_query_hash("b", "q", {"gate": "g", "stage": "clarify"}, "5")
    assert a == b


def test_watermark_changes_the_hash():
    assert recall_query_hash("b", "q", {}, "5") != recall_query_hash("b", "q", {}, "6")


def test_absent_watermark_is_distinct_from_a_literal_none_string():
    assert recall_query_hash("b", "q", {}, None) != recall_query_hash("b", "q", {}, "none")


def test_bank_and_query_are_separated_unambiguously():
    # "a|b" + "c" must not collide with "a" + "b|c".
    assert recall_query_hash("a|b", "c", {}, None) != recall_query_hash("a", "b|c", {}, None)
