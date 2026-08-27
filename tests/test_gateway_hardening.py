"""
Integration & Hardening Tests for IBVAP Central Gateway (P1-2 & P1-5).
Validates Liveness/Readiness health probes and CORS origin restriction.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

import sys
sys.path.insert(0, "apps/central-gateway/src")
from main import app
from db.session import init_db


@pytest.mark.anyio
async def test_health_liveness_probe():
    """
    P1-5: Verifies /health/liveness always returns 200 ALIVE as long as the process is up.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/liveness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ALIVE"
        assert data["system"] == "IBVAP Central Gateway C2"


@pytest.mark.anyio
async def test_health_readiness_probe():
    """
    P1-5: Verifies /health/readiness returns 200 READY when database is healthy.
    """
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "READY"
        assert data["database"] == "CONNECTED"


def test_cors_origin_headers():
    """
    P1-2: Verifies CORS headers allow configured origins.
    """
    client = TestClient(app)
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    }
    resp = client.options("/api/v1/sensors", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
