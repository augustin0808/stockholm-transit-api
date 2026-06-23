import pytest
from httpx import AsyncClient, ASGITransport
from app import app

@pytest.mark.asyncio
async def test_health():
    # Workplace Update: HTTPX 0.28+ requires an explicit ASGITransport wrapper for ASGI apps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}
