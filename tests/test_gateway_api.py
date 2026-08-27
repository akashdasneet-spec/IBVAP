"""
Integration Tests for FastAPI Central Gateway REST API.
"""

from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from uuid import uuid4

import sys
sys.path.insert(0, "apps/central-gateway/src")
from main import app
from db.session import init_db


@pytest.mark.anyio
async def test_sensors_crud_api():
    await init_db()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Sensor
        sensor_id = str(uuid4())
        payload = {
            "id": sensor_id,
            "name": "TEST-OPTICAL-CAM-01",
            "rtsp_url": "rtsp://10.0.0.50:554/live",
            "gps": {"latitude": 34.0522, "longitude": 74.8856, "altitude_m": 1620.0},
            "bop_sector_id": "BOP-SECTOR-ALPHA-01",
            "active_polygon_coordinates": [
                {"x": 0.2, "y": 0.2},
                {"x": 0.8, "y": 0.2},
                {"x": 0.8, "y": 0.8},
                {"x": 0.2, "y": 0.8}
            ],
            "fps_limit": 30
        }

        resp = await client.post("/api/v1/sensors", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "TEST-OPTICAL-CAM-01"

        # 2. List Sensors
        list_resp = await client.get("/api/v1/sensors?bop_sector_id=BOP-SECTOR-ALPHA-01")
        assert list_resp.status_code == 200
        sensors = list_resp.json()
        assert len(sensors) >= 1
        assert any(s["id"] == sensor_id for s in sensors)


@pytest.mark.anyio
async def test_alerts_feed_pagination():
    await init_db()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest test alert
        sensor_id = str(uuid4())
        alert_id = str(uuid4())
        unique_leaf = uuid4().hex + uuid4().hex
        alert_payload = {
            "alert_id": alert_id,
            "bop_id": "BOP-TEST-FEED",
            "sensor_id": sensor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_type": "PERSON",
            "threat_level": "HIGH",
            "centroid": {"latitude": 34.05, "longitude": 74.88, "altitude_m": 1600.0},
            "cot_xml_string": "<event/>",
            "evidence_cid": "bafybeiczsscdsbs7ffqz55asqdf32gvwlsdp4s8gshd",
            "merkle_leaf_hash": unique_leaf,
            "confidence": 0.95,
            "description": "Feed pagination test alert"
        }

        post_resp = await client.post("/api/v1/alerts", json=alert_payload)
        assert post_resp.status_code == 201

        # Query Paginated Feed
        feed_resp = await client.get("/api/v1/alerts/feed?bop_id=BOP-TEST-FEED&limit=10&offset=0")
        assert feed_resp.status_code == 200
        feed = feed_resp.json()
        assert feed["total"] >= 1
        assert len(feed["results"]) >= 1
        assert feed["results"][0]["bop_id"] == "BOP-TEST-FEED"


@pytest.mark.anyio
async def test_watchlist_face_enrollment_and_search():
    await init_db()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        poi_id = f"POI-{uuid4().hex[:8]}"
        enroll_payload = {
            "poi_id": poi_id,
            "name": "Classified Target Bravo",
            "threat_category": "INTRUDER",
            "notes": "Border watchlist target"
        }

        # 1. Enroll
        enroll_resp = await client.post("/api/v1/watchlist/faces", json=enroll_payload)
        assert enroll_resp.status_code == 201
        assert enroll_resp.json()["poi_id"] == poi_id

        # 2. Extract vector and search
        from services.face_service import FaceWatchlistService
        probe_vector = FaceWatchlistService.extract_embedding(seed_str=poi_id + "Classified Target Bravo")

        search_payload = {
            "probe_embedding_512d": probe_vector,
            "top_k": 5,
            "threshold": 0.90
        }

        search_resp = await client.post("/api/v1/watchlist/search", json=search_payload)
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert search_data["matched"] is True
        assert search_data["results"][0]["poi_id"] == poi_id
        assert search_data["results"][0]["similarity_score"] > 0.98
