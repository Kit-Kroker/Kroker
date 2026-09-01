"""FR-913 (E-48): the proposer's output type and its code-stamped form."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.map import (
    CandidateDisposition,
    DiscoverAction,
    DiscoverProposal,
    DispositionSource,
    ProposedDisposition,
    SplitPartition,
)


def _disp(**kw):
    base = dict(
        candidate_id="C-01",
        action=DiscoverAction.CONFIRM,
        source=DispositionSource.BASELINE,
        rule="baseline_confirm",
    )
    return CandidateDisposition(**(base | kw))


def test_proposed_disposition_cannot_declare_its_own_source():
    """DD1/DD7: provenance is code's to stamp. A model that could set
    `source` could claim a hallucinated verdict was a computed baseline."""
    assert "source" not in ProposedDisposition.model_fields


def test_merge_names_a_target_and_nothing_else_does():
    _disp(action=DiscoverAction.MERGE, merge_into="C-02", rule="r")
    with pytest.raises(ValidationError, match="merge_into"):
        _disp(action=DiscoverAction.MERGE)
    with pytest.raises(ValidationError, match="merge_into"):
        _disp(action=DiscoverAction.CONFIRM, merge_into="C-02")


def test_split_needs_two_partitions_and_nothing_else_carries_any():
    _disp(
        action=DiscoverAction.SPLIT,
        partitions=(
            SplitPartition(name="a", member_values=("x",)),
            SplitPartition(name="b", member_values=("y",)),
        ),
    )
    with pytest.raises(ValidationError, match="two partitions"):
        _disp(
            action=DiscoverAction.SPLIT,
            partitions=(SplitPartition(name="a", member_values=("x",)),),
        )
    with pytest.raises(ValidationError, match="partitions"):
        _disp(
            action=DiscoverAction.CONFIRM,
            partitions=(
                SplitPartition(name="a", member_values=("x",)),
                SplitPartition(name="b", member_values=("y",)),
            ),
        )


def test_a_proposer_disposition_must_carry_a_rationale():
    """A baseline needs none -- its rule IS its rationale. A model verdict
    with no reasoning is unreviewable."""
    _disp(source=DispositionSource.BASELINE, rule="baseline_confirm")
    with pytest.raises(ValidationError, match="rationale"):
        _disp(source=DispositionSource.PROPOSER, rule="proposer", rationale="")


def test_split_partition_member_values_are_sorted_and_deduped():
    SplitPartition(name="a", member_values=("x", "y"))
    with pytest.raises(ValidationError, match="not sorted"):
        SplitPartition(name="a", member_values=("y", "x"))
    with pytest.raises(ValidationError, match="not sorted"):
        SplitPartition(name="a", member_values=("x", "x"))


def test_proposal_holds_dispositions_and_nothing_else():
    """DD1: the model returns dispositions. It does not return a map, a
    capability, a metric, or a file."""
    assert set(DiscoverProposal.model_fields) == {"dispositions"}
    p = DiscoverProposal(
        dispositions=[
            ProposedDisposition(
                candidate_id="C-01",
                action=DiscoverAction.CONFIRM,
                rationale="four routes and a table, one owner",
            )
        ]
    )
    assert p.dispositions[0].candidate_id == "C-01"
