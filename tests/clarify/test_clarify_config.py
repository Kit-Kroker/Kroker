"""E-85's flag is off by default: the default pipeline must be byte-identical
to pre-E-85, so the benchmark can run both arms."""

import pytest
from pydantic import ValidationError

from sdlc.core.models import (
    PipelineConfig,
)


def test_probes_are_off_by_default():
    assert PipelineConfig().clarify_probes_enabled is False


def test_the_question_cap_defaults_to_five():
    assert PipelineConfig().clarify_question_cap == 5


def test_a_zero_cap_is_rejected():
    # A cap of 0 would silently surface nothing to the human while the
    # clarifier still burned four probe calls.
    with pytest.raises(ValidationError):
        PipelineConfig(clarify_question_cap=0)
