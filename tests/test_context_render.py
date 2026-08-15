"""E-84 D12: the map is persisted complete and rendered bounded."""
from __future__ import annotations

from sdlc.assessment.scan.models import Confidence, MemberKind
from sdlc.context.models import CodebaseMap, HotSpot, MapContract, MapModule
from sdlc.context.render import render_for_prompt
from sdlc.measurement import Measurement


def _map(modules=(), contracts=(), hot_spots=(), collected=None) -> CodebaseMap:
    ok = collected or Measurement.measured(float(len(modules)))
    return CodebaseMap(
        tree_hash="t", commit_sha="c" * 40, modules=tuple(modules),
        contracts=tuple(contracts), hot_spots=tuple(hot_spots),
        modules_collected=ok, contracts_collected=ok,
        hot_spots_collected=ok, collected=ok)


def _module(n: int) -> MapModule:
    return MapModule(name=f"cap{n:03d}", member_paths=(f"src/{n}.py",),
                     confidence=Confidence.LOW)


def test_a_small_map_renders_whole_with_no_marker():
    out = render_for_prompt(_map(modules=[_module(1), _module(2)]))
    assert "cap001" in out and "cap002" in out
    assert "more" not in out


def test_truncation_announces_itself():
    """The model must be told it is seeing a subset; silence would let it
    conclude the repository has exactly max_modules modules."""
    out = render_for_prompt(_map(modules=[_module(i) for i in range(50)]),
                            max_modules=10)
    assert "cap000" in out
    assert "… 40 more" in out


def test_a_not_collected_section_says_so_rather_than_showing_nothing():
    m = _map(collected=Measurement.not_collected("S5 could not run"))
    out = render_for_prompt(m)
    assert "not_collected" in out
    assert "S5 could not run" in out


def test_rendering_is_deterministic():
    modules = [_module(i) for i in range(50)]
    first = render_for_prompt(_map(modules=modules), max_modules=10)
    for _ in range(5):
        assert render_for_prompt(_map(modules=modules),
                                 max_modules=10) == first


def test_contracts_and_hot_spots_truncate_independently():
    contracts = [MapContract(kind=MemberKind.HTTP_ROUTE, value=f"GET /{i}",
                             path=f"src/{i}.py") for i in range(30)]
    spots = [HotSpot(path=f"src/{i}.py", source="testability", reason="r",
                     metric=Measurement.measured(1.0)) for i in range(30)]
    out = render_for_prompt(_map(contracts=contracts, hot_spots=spots),
                            max_contracts=5, max_hot_spots=3)
    assert "… 25 more" in out
    assert "… 27 more" in out
