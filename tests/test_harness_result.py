from sdlc.models import HarnessKind, HarnessRunResult


def _res(**kw):
    base = dict(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="x")
    base.update(kw)
    return HarnessRunResult(**base)


def test_near_ceiling_true_when_input_exceeds_fraction():
    r = _res(input_tokens=160_000, context_window=200_000)
    assert r.near_context_ceiling(0.75) is True


def test_near_ceiling_false_below_fraction():
    r = _res(input_tokens=100_000, context_window=200_000)
    assert r.near_context_ceiling(0.75) is False


def test_compacted_always_ceiling():
    assert _res(compacted=True).near_context_ceiling() is True


def test_unknown_tokens_not_ceiling():
    assert _res().near_context_ceiling() is False
