"""Token-free dry run: `python -m sdlc.demo`.

Runs the REAL GraphWorkflow against a Temporal server, with every seam that
costs money or touches a repository replaced by a scripted stand-in: the
proposer agents answer from canned artifacts, and the git, harness, QA and
deploy activities return fixed results. Nothing reaches a model provider, a
coding CLI or a working tree, so it needs no API key and no login -- only a
reachable Temporal.

What it proves is the orchestration: stage order, the human gates and the
signals that answer them, the deterministic merge gate, and the retro
export. What it does not prove is that any provider key, CLI or repository
on this machine works -- that is `python -m sdlc.cli doctor`.

Import nothing from this package's submodules before `env.use_placeholder_keys()`
has run: `run` and `fakes` import the agent registry, which refuses to load
without provider keys.
"""
