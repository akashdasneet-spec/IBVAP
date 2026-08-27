"""
Comprehensive End-to-End Staging Test Suite for IBVAP Platform.
Validates the complete chain:
Edge Simulator -> Authenticated /ws/v1/edge -> Central Gateway -> Database -> C2 WebSocket Hub -> Dashboard Client.
"""

from datetime import datetime, timezone
import json
from uuid import uuid4
import pytest
from starlette.testclient import TestClient

import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "packages" / "core-types" / "src"))
sys.path.insert(0, str(repo_root / "apps" / "central-gateway" / "src"))
sys.path.insert(0, str(repo_root / "apps" / "edge-engine" / "src"))

from main import app, ws_hub
from db.session import init_db
from ibvap_core_types import (
    BoundingBox,
    GeoPoint,
    PolygonCoordinate,
    SensorConfig,
    TacticalAlert,
    TargetType,
    ThreatLevel,
    compute_merkle_leaf_hash,
)
from security.cot import CoTGenerator
from security.merkle import MerkleAuditLedger
from security.vault import EvidenceVault
from services.certin_audit import CertInAuditLogger


@pytest.mark.anyio
async def test_complete_e2e_tactical_alert_chain(monkeypatch, tmp_path):
    """
    E2E Staging Pipeline:
    Edge Simulator -> Authenticated WebSocket Ingest -> Gateway DB & PyTAK -> C2 Broadcast -> Operator Verification.
    """
    test_token = "TacticalDefenseSharedSecret2026!"
    master_key = b"E" * 32
    monkeypatch.setenv("EDGE_API_TOKEN", test_token)
    monkeypatch.setenv("IBVAP_ALLOW_EPHEMERAL_KEY", "true")

    await init_db()
    client = TestClient(app)

    alert_id = uuid4()
    sensor_id = uuid4()
    bop_id = "BOP-SILIGURI-CORRIDOR"
    now_utc = datetime.now(timezone.utc)

    cot_gen = CoTGenerator()
    vault = EvidenceVault(master_key=master_key, cache_dir=str(tmp_path / "edge_cache"))
    ledger = MerkleAuditLedger(batch_size=5)

    dummy_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 400
    dummy_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 1000
    meta = {"alert_id": str(alert_id), "threat": "HIGH"}

    _, cid = vault.package_encrypt_and_store(dummy_jpeg, dummy_mp4, meta)
    leaf_hash = compute_merkle_leaf_hash(
        alert_id=alert_id,
        sensor_id=sensor_id,
        timestamp=now_utc,
        target_type="PERSON",
        threat_level="HIGH",
        evidence_cid=cid
    )
    ledger._current_batch.append(leaf_hash)
    cot_xml = cot_gen.generate_xml(
        alert_id=str(alert_id),
        bop_id=bop_id,
        sensor_id=str(sensor_id),
        target_type=TargetType.PERSON,
        threat_level=ThreatLevel.HIGH,
        centroid=GeoPoint(latitude=26.7271, longitude=88.3953, altitude_m=130.0),
        confidence=0.98,
        remarks="Incursion detected near Siliguri choke point."
    )

    alert_payload = {
        "alert_id": str(alert_id),
        "bop_id": bop_id,
        "sensor_id": str(sensor_id),
        "timestamp": now_utc.isoformat(),
        "target_type": "PERSON",
        "threat_level": "HIGH",
        "centroid": {"latitude": 26.7271, "longitude": 88.3953, "altitude_m": 130.0},
        "cot_xml_string": cot_xml,
        "evidence_cid": cid,
        "merkle_leaf_hash": leaf_hash,
        "bounding_box": {"x1": 0.3, "y1": 0.4, "x2": 0.5, "y2": 0.8, "confidence": 0.98, "class_id": 0, "track_id": 88},
        "confidence": 0.98,
        "description": "Incursion detected near Siliguri choke point."
    }

    # 1. Enroll Sensor in C2 Registry
    sensor_payload = {
        "id": str(sensor_id),
        "name": "SILIGURI-OPTICAL-TOWER-01",
        "rtsp_url": "videotestsrc",
        "gps": {"latitude": 26.7271, "longitude": 88.3953, "altitude_m": 130.0},
        "bop_sector_id": bop_id,
        "active_polygon_coordinates": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}],
        "fps_limit": 30
    }
    sensor_resp = client.post("/api/v1/sensors", json=sensor_payload)
    assert sensor_resp.status_code == 201

    # 2. Ingest Tactical Alert to Central Gateway API
    post_resp = client.post("/api/v1/alerts", json=alert_payload)
    assert post_resp.status_code == 201

    # 3. Start Operator WebSocket session (Situation Room C2)
    with client.websocket_connect("/ws/v1/c2") as operator_ws:
        assert len(ws_hub.c2_operators) >= 1

        # 4. Connect Authenticated Edge WebSocket to verify live telemetry stream
        with client.websocket_connect(f"/ws/v1/edge?node_id=EDGE-SILIGURI-01&token={test_token}") as edge_ws:
            edge_ws.send_text(json.dumps(alert_payload))
            msg_text = operator_ws.receive_text()
            msg = json.loads(msg_text)
            assert msg["event"] == "TACTICAL_ALERT"
            assert msg["data"]["alert_id"] == str(alert_id)
            assert msg["data"]["bop_id"] == bop_id

    # 5. Seal Merkle Batch Receipt & Validate Court Admissibility
    receipt = ledger.seal_batch(now_utc)
    rcpt_resp = client.post("/api/v1/merkle/receipts", json=receipt.to_dict())
    assert rcpt_resp.status_code == 201

    verify_resp = client.get(f"/api/v1/audit/verify/{alert_id}")
    assert verify_resp.status_code == 200
    admissibility = verify_resp.json()
    assert admissibility["is_admissible"] is True
    assert admissibility["leaf_hash_valid"] is True

    # 6. Append & Verify CERT-In Ed25519 Signed Audit Log
    audit_log_path = tmp_path / "certin_audit.jsonl"
    monkeypatch.setenv("CERTIN_AUDIT_LOG_PATH", str(audit_log_path))
    priv_key_path = tmp_path / "audit_key.pem"
    audit_logger = CertInAuditLogger(key_path=str(priv_key_path), allow_ephemeral_key=True)
    rec = audit_logger.log_operator_action(
        operator_id="COMMANDER-SILIGURI",
        action="VERIFY_ADMISSIBILITY",
        resource_id=str(alert_id),
        metadata={"status": "VERIFIED"}
    )
    assert CertInAuditLogger.verify_record(rec) is True
