"""D6: one fixture per import form. Breadth is the design choice; these
tests are what keep it from being breadth-without-evidence."""
from __future__ import annotations

import pytest

from sdlc.assessment.discover.refgraph import (
    EXTRACTOR_EXTENSIONS, extract, is_relative,
)


@pytest.mark.parametrize("path,text,expected", [
    ("a.py", "import os\n", "os"),
    ("a.py", "from pkg.mod import thing\n", "pkg.mod"),
    ("a.py", "from . import sibling\n", "."),
    ("a.py", "from ..pkg import thing\n", "..pkg"),
    ("a.ts", "import x from './rel'\n", "./rel"),
    ("a.ts", "import 'side-effect'\n", "side-effect"),
    ("a.js", "const x = require('./dep')\n", "./dep"),
    ("a.js", "const x = await import('./lazy')\n", "./lazy"),
    ("a.ts", "export { x } from './re-export'\n", "./re-export"),
    ("a.go", '\timport "example.com/pkg/svc"\n', "example.com/pkg/svc"),
    ("A.java", "import com.acme.Orders;\n", "com.acme.Orders"),
    ("A.kt", "import com.acme.Orders\n", "com.acme.Orders"),
    ("a.rb", "require_relative 'helper'\n", "helper"),
    ("a.rb", "require 'json'\n", "json"),
    ("a.php", "use Acme\\Orders\\Service;\n", "Acme\\Orders\\Service"),
    ("a.php", "require_once 'bootstrap.php';\n", "bootstrap.php"),
    ("a.cs", "using Acme.Orders;\n", "Acme.Orders"),
    ("a.rs", "use crate::orders::api;\n", "crate::orders::api"),
    ("a.rs", "mod helpers;\n", "helpers"),
    ("a.ex", "alias Acme.Orders\n", "Acme.Orders"),
    ("a.swift", "import Orders\n", "Orders"),
])
def test_each_form_extracts_its_target(path, text, expected):
    assert expected in [target for _, target in extract(path, text)]


def test_an_unknown_extension_extracts_nothing():
    assert extract("a.md", "import os\n") == []
    assert ".md" not in EXTRACTOR_EXTENSIONS


def test_extraction_is_deduped_and_sorted():
    text = "import b\nimport a\nimport b\n"
    assert extract("m.py", text) == [("python_import", "a"),
                                     ("python_import", "b")]


@pytest.mark.parametrize("form,target,expected", [
    ("python_from", ".sibling", True),
    ("python_from", "pkg.mod", False),
    ("js_from", "./rel", True),
    ("js_from", "../up", True),
    ("js_from", "react", False),
    ("ruby_require_relative", "helper", True),
    ("ruby_require", "json", False),
    ("rust_mod", "helpers", True),
    ("rust_use", "crate::a", False),
    ("jvm_import", "com.acme.X", False),
])
def test_relativeness(form, target, expected):
    assert is_relative(form, target) is expected
