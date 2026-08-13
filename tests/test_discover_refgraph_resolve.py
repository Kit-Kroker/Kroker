"""D6 resolution: an edge only exists when exactly one path matches."""
from __future__ import annotations

from sdlc.assessment.discover.refgraph import build
from sdlc.measurement import CollectionState


def test_relative_import_resolves_to_a_sibling():
    graph = build({
        "src/app.py": "from . import helper\n",
        "src/helper.py": "x = 1\n",
    })
    assert ("src/app.py", "src/helper.py") in graph.edges


def test_dotted_import_resolves_by_suffix():
    graph = build({
        "src/app.py": "from pkg.helper import thing\n",
        "src/pkg/helper.py": "thing = 1\n",
    })
    assert ("src/app.py", "src/pkg/helper.py") in graph.edges


def test_js_relative_import_resolves_through_index():
    graph = build({
        "web/app.ts": "import x from './widgets'\n",
        "web/widgets/index.ts": "export const x = 1\n",
    })
    assert ("web/app.ts", "web/widgets/index.ts") in graph.edges


def test_package_import_resolves_through_init():
    graph = build({
        "src/app.py": "from pkg import thing\n",
        "src/pkg/__init__.py": "thing = 1\n",
    })
    assert ("src/app.py", "src/pkg/__init__.py") in graph.edges


def test_ambiguous_suffix_yields_no_edge():
    graph = build({
        "src/app.py": "from pkg.helper import thing\n",
        "a/pkg/helper.py": "thing = 1\n",
        "b/pkg/helper.py": "thing = 1\n",
    })
    assert graph.edges == ()
    assert [u.reason for u in graph.unresolved] == ["ambiguous_suffix"]


def test_external_package_is_not_recorded_as_failure():
    graph = build({"src/app.py": "import requests\nimport os\n"})
    assert graph.unresolved == ()
    assert graph.unresolved_relative_rate.state is \
        CollectionState.NOT_COLLECTED


def test_unresolved_relative_import_is_extractor_failure():
    graph = build({
        "src/app.py": "from . import missing\n",
        "src/other.py": "from . import app\n",
    })
    reasons = {u.reason for u in graph.unresolved}
    assert reasons == {"no_matching_path"}
    assert graph.unresolved_relative_rate.state is CollectionState.MEASURED
    assert graph.unresolved_relative_rate.value == 0.5


def test_parsed_and_unparsed_are_split_by_extension():
    graph = build({"a.py": "", "notes.md": "", "b.go": ""})
    assert graph.parsed == ("a.py", "b.go")
    assert graph.unparsed == ("notes.md",)


def test_build_is_byte_identical_across_input_orderings():
    import random
    tree = {
        "src/app.py": "from . import helper\nimport requests\n",
        "src/helper.py": "x = 1\n",
        "web/a.ts": "import b from './b'\n",
        "web/b.ts": "export const b = 1\n",
    }
    reference = build(tree).model_dump_json()
    for seed in range(3):
        items = list(tree.items())
        random.Random(seed).shuffle(items)
        assert build(dict(items)).model_dump_json() == reference
