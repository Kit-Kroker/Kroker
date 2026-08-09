# DevEval Import Report — E-79

| | |
|---|---|
| Date | 2026-08-09 |
| Work item | **E-79** (DevEval corpus import) |
| Spec | `docs/superpowers/specs/2026-08-09-benchmark-corpus-and-stage-isolation-design.md` |
| Source | `open-compass/DevEval` @ `bb593c1f9c535ff0dde0c9f4807d58c9566c3a6c` |
| Licence | code Apache-2.0, **dataset CC BY 4.0** (per-case `ATTRIBUTION.md`) |
| Answers | **OQ-B8** — how many of the ten Python repositories survive |

## 1. Result

**Six of ten** repositories are committed as benchmark cases. The corpus grows
from 3 hand-authored cases to **9**.

| Case | Verify | Requirements | Oracle tests | Notes |
|---|---|---|---|---|
| `deveval-geotext` | **PASS** | 5 | 9 | network flag cleared as a false positive (§4) |
| `deveval-hone` | **PASS** | 5 | 12 | needed the root data-dir fix (§3) |
| `deveval-lice` | **PASS** | 7 | 31 | needed the LF checkout (§3); flag cleared (§4) |
| `deveval-particle-swarm-optimization` | **PASS** | 3 | 6 | clean import |
| `deveval-readtime` | **PASS** | 7 | 12 | needs `lxml`, `markdown2`, `beautifulsoup4`, `pyquery` |
| `deveval-stocktrends` | **PASS** | 4 | 9 | needs `pandas` |
| `deveval-arxiv-digest` | *quarantined* | 7 draft | 42 | `network_required`: calls the live ArXiv API |
| `deveval-chakin` | *quarantined* | 2 draft | 2 | `network_required`: `urlretrieve` of word vectors |
| `deveval-hybrid-images` | *unverified* | 1 draft | 13 | needs `cv2`; not installed on the import machine |
| `deveval-textcnn` | *unverified* | 8 draft | 13 | needs `torch` (~2.5 GB); not installed |

**Six requirement-level tasks per case on average, 79 graded oracle tests.**

The four excluded cases are not deleted upstream — re-import any of them with:

```bash
python -m sdlc.cli benchmark import-deveval \
  --src <DevEval>/benchmark_data/python --repo <RepoName>
```

`arxiv-digest` and `chakin` will stay quarantined until the E-21 network tier
exists; `hybrid-images` and `textcnn` need a machine with `cv2`/`torch` to
reach a green verify before they can be committed.

## 2. Prerequisite for reproducing this import

**Clone with line-ending conversion disabled.** On Windows, a default clone
applies `core.autocrlf`, which rewrites `lice`'s licence templates to CRLF and
makes `test_package_template` fail on a whitespace diff:

```bash
git -c core.autocrlf=false clone --depth 1 --filter=blob:none --sparse \
  https://github.com/open-compass/DevEval
git -c core.autocrlf=false sparse-checkout set benchmark_data/python
```

A full clone times out; the partial + sparse form fetches only what is needed.

## 3. Conversion defects found and fixed

All three were invisible against the synthetic fixture and only appeared
against the real corpus.

1. **Test discovery missed pytest's suffix pattern.** `collect_node_ids`
   globbed `test_*.py` only. `Hybrid_Images` and `chakin` name their suites
   `unit_test.py` / `acceptance_test.py`, which pytest *does* collect via
   `*_test.py`. Their generated node-ids would never have matched the grader's
   report, so every requirement would have graded as `judge="error"`.
2. **Root-level data directories were left behind.** Upstream suites resolve
   fixtures against `dirname(dirname(__file__))` — the repo root upstream, but
   `oracle/` once the tests are nested one level deeper. Five repositories
   (`hone`, `readtime`, `stocktrends`, `lice`, `Hybrid_Images`) ship such a
   directory. `hone` went from 11 failed to 12 passed once data directories
   rode along inside `oracle/`. Directories containing `.py` deliberately do
   *not*, so the oracle can never import the gold implementation.
3. **`hone` declares `dependencies: ""`.** A real corpus property, not a
   defect. An absent dependency file is now recorded on `ImportReport` rather
   than crashing the import. Separately, a root-level `requirements.txt`
   (`TextCNN`, `chakin`, `geotext`, `lice`) is kept out of `reference/`.

A fourth defect was found earlier, while building the gate itself: the
verifier originally ran `python -m pytest`, which puts the working directory
on `sys.path`, while the real grader runs bare `pytest` (`toolchain/
adapters.py`), which does not. Making the gate faithful turned it red and
exposed that **DevEval oracles ship no path shim**, so `convert_repo` now
generates `oracle/conftest.py` inserting the produced repo root — the same
pattern cat-café's hand-authored oracle uses. Without it every imported case
would have collected zero tests regardless of the quality of the produced code.

## 4. Upstream oracle defects

- **`ArXiv_digest` acceptance test is partly vacuous.** In
  `acceptance_tests/test_query_arxiv.py`, `compare_json_output` opens
  `reference_output.txt` **twice** and compares it against itself, so the
  entire terminal-output assertion block can never fail. Recorded, not
  repaired — the case is quarantined for network anyway.
- **Network detector false positives.** The detector is deliberately
  over-broad (§3.5 of the spec). Of five flags, two were judged not to be real
  egress during this vetting pass and cleared in
  `NETWORK_VETTED_OFFLINE`:
  - `geotext` — two *comments* citing `download.geonames.org`; the city and
    country data is vendored, and the oracle passes offline.
  - `lice` — one URL inside a printed "contribute here" help string.

  Evidence lines are still recorded on the `ImportReport` in both cases, so the
  clearance is auditable. `arxiv-digest` and `chakin` are genuine.

## 5. `tasks.yaml` review (OQ-B9)

The generated drafts are test-file granularity with every `error_class` set to
`functional`. That is too coarse to compute a meaningful functional
completeness: `lice` arrived as **one task holding 31 tests**, which would
have made its FC effectively binary.

All six committed suites were regrouped by hand into PRD-level requirements —
31 requirements across 79 tests — and given real error classes
(`data_integrity` for round-trip and dataframe validation, `error_handling` for
input validation, `api_contract` for CLI help and result arithmetic). Every
node-id was checked to exist in the generated draft before rewriting, and
`tests/test_deveval_corpus.py` now asserts that each referenced test is
actually defined in the oracle.

**OQ-B9 answer: the confirmation pass is a rewrite, not a light edit.** Budget
roughly 15–30 minutes per case. The draft is still worth generating — it
supplies the exact node-id strings, which are tedious and error-prone to type
by hand — but its grouping should be treated as a starting point only.

## 6. Environment

Oracle dependencies were installed into the **project venv**
(`.venv/Scripts/python.exe`), leaving system Python untouched: `pytest`,
`pandas`, `lxml`, `six`, `markdown2`, `beautifulsoup4`, `pyquery`. Run
verification with `.venv/Scripts` ahead of `PATH` so the adapter's bare
`pytest` resolves there.

`cv2` and `torch` were deliberately not installed.
