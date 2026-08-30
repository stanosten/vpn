import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.storage.repository import repository


@pytest.mark.asyncio
async def test_api_status():
    await repository.init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"
        assert "app_name" in data


@pytest.mark.asyncio
async def test_api_stats():
    await repository.init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_nodes" in data
        assert "live_nodes" in data


@pytest.mark.asyncio
async def test_api_nodes_empty_or_list():
    await repository.init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/nodes")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "count" in data


@pytest.mark.asyncio
async def test_api_check_single():
    await repository.init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/check/single", json={"target": "1.1.1.1:53"})
        assert resp.status_code == 200
        data = resp.json()
        assert "is_alive" in data
        assert data["node"]["host"] == "1.1.1.1"
