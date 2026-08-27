"""
Unit & Integration Tests for Audit Admissibility Verification API.
"""

from datetime import datetime, timezone
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient

import sys
sys.path.insert(0, "apps/central-gateway/src")
from main import app
from db.session import init_db
from ibvap_core_types import compute_merkle_leaf_hash


@pytest.mark.anyio
async def test_audit_verification_endpoint():
    await init_db()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        alert_id = uuid4()
        sensor_id = uuid4()
        now = datetime.now(timezone.utc)
        cid = "bafybeiczsscdsbs7ffqz55asqdf32gvwlsdp4s8gshd"
        bop_id = "BOP-ALPHA-01"

        # Correctly compute canonical leaf hash
        expected_leaf = compute_merkle_leaf_hash(
            alert_id=alert_id,
            sensor_id=sensor_id,
            timestamp=now,
            target_type="PERSON",
            threat_level="HIGH",
            evidence_cid=cid
        )

        alert_payload = {
            "alert_id": str(alert_id),
            "bop_id": bop_id,
            "sensor_id": str(sensor_id),
            "timestamp": now.isoformat(),
            "target_type": "PERSON",
            "threat_level": "HIGH",
            "centroid": {"latitude": 34.052, "longitude": 74.885, "altitude_m": 1620.0},
            "cot_xml_string": "<event/>",
            "evidence_cid": cid,
            "merkle_leaf_hash": expected_leaf,
            "confidence": 0.96,
            "description": "Perimeter breach near sector Alpha"
        }

        # 1. Post Alert
        post_resp = await client.post("/api/v1/alerts", json=alert_payload)
        assert post_resp.status_code == 201

        # 2. Ingest Merkle Batch Receipt that includes this leaf
        receipt_payload = {
            "batch_id": f"BATCH-{uuid4().hex[:6]}",
            "root_hash": "a" * 64,
            "leaf_count": 1,
            "leaves": [expected_leaf],
            "timestamp_start": now.isoformat(),
            "timestamp_end": now.isoformat()
        }
        rcpt_resp = await client.post("/api/v1/merkle/receipts", json=receipt_payload)
        assert rcpt_resp.status_code == 201

        # 3. Verify Admissibility
        verify_resp = await client.get(f"/api/v1/audit/verify/{alert_id}")
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["is_admissible"] is True
        assert data["leaf_hash_valid"] is True
        assert data["merkle_root_verified"] is True
        assert data["stored_leaf_hash"] == expected_leaf
        assert data["batch_id"] == receipt_payload["batch_id"]
