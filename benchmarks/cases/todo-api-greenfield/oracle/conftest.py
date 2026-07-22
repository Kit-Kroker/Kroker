"""Held-out oracle fixtures for todo-api-greenfield (E-31). Never seen by the
run: copied into the produced worktree only at grade time. Drives the frozen
ASGI contract (app:app) via httpx, so it stays framework-agnostic within ASGI."""
import os
import sys

import httpx
import pytest_asyncio

# The produced repo root is the parent of this oracle/ dir once copied in.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest_asyncio.fixture
async def client():
    import app as produced          # contract: module app.py exposes `app`
    transport = httpx.ASGITransport(app=produced.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://testserver") as c:
        yield c
