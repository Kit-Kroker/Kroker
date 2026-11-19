"""Edge/pin tests for load_diff's bounded read-back (FR-702).

The T3 marker semantics moved here from get_task_diff with the cut itself:
get_task_diff stores the FULL untruncated patch, and truncation survives
only as this read-back budget for prompts. Oracle parity (benchmarks/
oracle.py ``_truncate_diff``): ``<= max_chars`` passes through unchanged;
longer text keeps its exact first ``max_chars`` characters and gains a
terminal marker naming the omitted count. A cut at exactly max_chars is no
cut. Char semantics throughout — the omitted count is characters, and a
stored byte stream that is not valid UTF-8 decodes with U+FFFD, never an
exception.
"""

from __future__ import annotations

import pytest

from sdlc.artifacts.read import LoadDiffInput, load_diff
from sdlc.artifacts.store import LocalFileStore
from sdlc.benchmarks.oracle import _truncate_diff


def _stored(tmp_path, text: str, name: str = "t.patch"):
    store = LocalFileStore(root=tmp_path)
    return store.put("diff", "run-1", name, text.encode("utf-8"))


@pytest.mark.asyncio
async def test_at_exactly_max_chars_the_text_passes_through_uncut(tmp_path):
    """PIN: the cut boundary is EXCLUSIVE, oracle semantics — len == max
    returns the whole text with no marker. An inclusive boundary would cut
    the final character and mark a complete diff as truncated."""
    text = "".join(f"payload line {i:03d} of the change\n" for i in range(12))
    assert len(text) > 100, "fixture guard: boundary tests would be vacuous"
    ref = _stored(tmp_path, text)
    out = await load_diff(LoadDiffInput(ref=ref, max_chars=len(text)))
    assert out.text == text
    assert not out.truncated
    assert "truncated" not in out.text


@pytest.mark.asyncio
async def test_one_char_over_max_carries_a_marker_naming_exactly_one(tmp_path):
    text = "y" * 251
    ref = _stored(tmp_path, text)
    out = await load_diff(LoadDiffInput(ref=ref, max_chars=250))
    assert out.truncated
    assert out.text.endswith("\n...[diff truncated, 1 chars omitted]")


@pytest.mark.asyncio
async def test_cut_matches_the_oracle_truncation_shape(tmp_path):
    """The cut read-back equals the oracle's own ``_truncate_diff`` over the
    stored text — exact first max_chars characters, then the oracle-shaped
    marker, terminal and solitary."""
    text = "".join(f"payload line {i:03d} of the change\n" for i in range(40))
    ref = _stored(tmp_path, text)
    max_chars = len(text) // 2
    out = await load_diff(LoadDiffInput(ref=ref, max_chars=max_chars))
    assert out.text == _truncate_diff(text, max_chars)
    lines = out.text.splitlines()
    assert sum("truncated" in ln for ln in lines) == 1
    assert "truncated" in lines[-1]


@pytest.mark.asyncio
async def test_default_max_chars_is_60k_and_passes_a_typical_patch(tmp_path):
    text = "diff --git a/app/x.py b/app/x.py\n+ok\n"
    ref = _stored(tmp_path, text)
    out = await load_diff(LoadDiffInput(ref=ref))
    assert out.text == text
    assert not out.truncated


@pytest.mark.asyncio
async def test_foreign_kind_is_refused(tmp_path):
    store = LocalFileStore(root=tmp_path)
    ref = store.put("harness_session", "run-1", "s.jsonl", b"{}")
    with pytest.raises(AssertionError, match="load_diff reads only diffs"):
        await load_diff(LoadDiffInput(ref=ref))


@pytest.mark.asyncio
async def test_multibyte_bytes_cut_mid_codepoint_decode_never_raises(tmp_path):
    """Stored bytes are not guaranteed valid UTF-8 at a boundary; the
    read-back decodes with errors='replace' so a cut codepoint becomes
    U+FFFD in the prompt instead of an exception on the workflow path."""
    raw = ("é" * 100).encode("utf-8")[:-1]  # drops the final continuation byte
    store = LocalFileStore(root=tmp_path)
    ref = store.put("diff", "run-1", "mb.patch", raw)
    out = await load_diff(LoadDiffInput(ref=ref, max_chars=10_000))
    assert not out.truncated
    assert "\ufffd" in out.text
    assert out.text.count("é") == 99
