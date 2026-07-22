"""Black-box CRUD oracle: exercises the frozen HTTP contract, not internals.
Fraction passing is the objective (Tier-A) grade."""
import pytest


@pytest.mark.asyncio
async def test_create_returns_id_and_echoes_title(client):
    r = await client.post("/todos", json={"title": "buy milk"})
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "buy milk" and "id" in body


@pytest.mark.asyncio
async def test_list_contains_created_item(client):
    await client.post("/todos", json={"title": "a"})
    r = await client.get("/todos")
    assert r.status_code == 200
    assert any(t["title"] == "a" for t in r.json())


@pytest.mark.asyncio
async def test_get_by_id_roundtrips(client):
    created = (await client.post("/todos", json={"title": "x"})).json()
    r = await client.get(f"/todos/{created['id']}")
    assert r.status_code == 200 and r.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_update_reflects_changes(client):
    created = (await client.post("/todos", json={"title": "x"})).json()
    r = await client.put(f"/todos/{created['id']}",
                         json={"title": "y", "done": True})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "y" and body["done"] is True


@pytest.mark.asyncio
async def test_delete_then_get_is_404(client):
    created = (await client.post("/todos", json={"title": "x"})).json()
    assert (await client.delete(f"/todos/{created['id']}")).status_code == 204
    assert (await client.get(f"/todos/{created['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_get_missing_is_404(client):
    r = await client.get("/todos/999999")
    assert r.status_code == 404
