"""Per-case config, no fake adapter. A case opts into stage 13 explicitly --
today no benchmark case reaches it at all."""

from __future__ import annotations

from sdlc.benchmarks.models import CaseSpec


def test_cases_do_not_deploy_by_default():
    assert CaseSpec.model_fields["deploy_enabled"].default is False


def test_a_case_can_opt_in():
    assert CaseSpec.model_fields["deploy_enabled"].annotation is bool
