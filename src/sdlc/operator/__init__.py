"""Operator-facing verbs over the channel contract (E-86).

The tool layer every operator surface shares. tools.py, render.py, deps.py
and errors.py import no web framework and no LLM library -- agent.py is the
only pydantic_ai consumer, and E-11's MCP server is its sibling. The
layering is asserted by tests/test_operator_layering.py, not merely
documented here.
"""
