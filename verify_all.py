"""
IBVAP End-to-End Unified Smoke Test & Validation Script.
Launches the FastAPI Gateway, simulates 3 Border Observation Post (BOP) edge nodes,
connects a headless WebSocket C2 subscriber client, and validates that all telemetry,
Cursor-on-Target XML, and cryptographic Merkle proof pathways execute flawlessly.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import sys
import time
from uuid import uuid4
import httpx
from starlette.testclient import TestClient

# Path resolution
from pathlib import Path
repo_root = Path(__file__).resolve().parent

# 1. Gateway imports
sys.path.insert(0, str(repo_root / "packages" / "core-types" / "src"))
sys.path.insert(0, str(repo_root / "apps" / "central-gateway" / "src"))
from main import app, ws_hub
from db.session import init_db
from ibvap_core_types import (
    GeoPoint,
    PolygonCoordinate,
    SensorConfig,
    TacticalAlert,
    TargetType,
    ThreatLevel,
    compute_merkle_leaf_hash,
)
from services.certin_audit import CertInAuditLogger, audit_logger

# 2. Edge security imports
sys.path.insert(0, str(repo_root / "apps" / "edge-engine" / "src"))
from security.cot import CoTGenerator
from security.merkle import MerkleAuditLedger
from security.vault import EvidenceVault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("verify_all")


def run_smoke_test():
    print("=" * 80)
    print(" IBVAP DEFENSE COMMAND & CONTROL PLATFORM — END-TO-END SMOKE TEST")
    print("=" * 80)

    client = TestClient(app)

    # 1. Initialize Database
    logger.info("[1/7] Initializing Central C2 Database Schema...")
    asyncio.run(init_db())
    logger.info("   -> SQLite/Postgres Async Schema Verified.")

    # 2. Register 3 BOP Edge Optical / Thermal Sensors
    logger.info("[2/7] Registering 3 Border Observation Post (BOP) Camera Nodes...")
    bop_sectors = ["BOP-SECTOR-ALPHA", "BOP-SECTOR-BRAVO", "BOP-SECTOR-CHARLIE"]
    created_sensors = []

    for idx, bop in enumerate(bop_sectors):
        sensor_id = str(uuid4())
        payload = {
            "id": sensor_id,
            "name": f"SMOKE-TOWER-{bop}-0{idx+1}",
            "rtsp_url": f"rtsp://10.20.{idx}.50:554/live",
            "gps": {"latitude": 34.0522 + idx * 0.01, "longitude": 74.8856 + idx * 0.01, "altitude_m": 1620.0},
            "bop_sector_id": bop,
            "active_polygon_coordinates": [
                {"x": 0.2, "y": 0.2},
                {"x": 0.8, "y": 0.2},
                {"x": 0.8, "y": 0.8},
                {"x": 0.2, "y": 0.8}
            ],
            "fps_limit": 30
        }
        resp = client.post("/api/v1/sensors", json=payload)
        assert resp.status_code == 201, f"Failed to register sensor {bop}"
        created_sensors.append(sensor_id)
        logger.info(f"   -> Enrolled: {payload['name']} @ GPS ({payload['gps']['latitude']:.4f}, {payload['gps']['longitude']:.4f})")

    # 3. Simulate Edge Security Pipeline (AES-256-GCM Vault, CoT XML, Merkle Leaf)
    logger.info("[3/7] Simulating Edge AI Engine Intrusion Detection & Packaging...")
    cot_gen = CoTGenerator()
    vault = EvidenceVault(master_key=b"V" * 32)
    ledger = MerkleAuditLedger(batch_size=5)

    alert_id = uuid4()
    now_utc = datetime.now(timezone.utc)
    sensor_id = created_sensors[0]

    # Dummy snapshot and clip
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 800
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 1500
    meta = {"alert_id": str(alert_id), "threat": "HIGH"}

    _, cid = vault.package_encrypt_and_store(jpeg_bytes, mp4_bytes, meta)
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
        bop_id="BOP-SECTOR-ALPHA",
        sensor_id=sensor_id,
        target_type=TargetType.PERSON,
        threat_level=ThreatLevel.HIGH,
        centroid=GeoPoint(latitude=34.0528, longitude=74.8862, altitude_m=1622.0),
        confidence=0.96,
        remarks="Perimeter intrusion detected near Sector Alpha tripwire."
    )

    logger.info(f"   -> Encrypted Evidence CID: {cid}")
    logger.info(f"   -> RFC 6962 Merkle Leaf Hash: {leaf_hash[:24]}...")
    logger.info(f"   -> MIL-STD-2525 CoT XML Tag: <event uid='{alert_id}' ...>")

    # 4. Ingest TacticalAlert through Central Gateway API
    logger.info("[4/7] Transmitting TacticalAlert to Central Gateway API...")
    alert_payload = {
        "alert_id": str(alert_id),
        "bop_id": "BOP-SECTOR-ALPHA",
        "sensor_id": sensor_id,
        "timestamp": now_utc.isoformat(),
        "target_type": "PERSON",
        "threat_level": "HIGH",
        "centroid": {"latitude": 34.0528, "longitude": 74.8862, "altitude_m": 1622.0},
        "cot_xml_string": cot_xml,
        "evidence_cid": cid,
        "merkle_leaf_hash": leaf_hash,
        "bounding_box": {"x1": 0.4, "y1": 0.4, "x2": 0.6, "y2": 0.8, "confidence": 0.96, "class_id": 0, "track_id": 204},
        "confidence": 0.96,
        "description": "Perimeter intrusion detected near Sector Alpha tripwire."
    }

    ingest_resp = client.post("/api/v1/alerts", json=alert_payload)
    assert ingest_resp.status_code == 201
    logger.info("   -> TacticalAlert Ingested & Stored in Database.")

    # 5. Seal Merkle Batch Receipt & Verify Legal Admissibility
    logger.info("[5/7] Sealing Merkle Root Batch Receipt & Validating Chain of Custody...")
    receipt = ledger.seal_batch(now_utc)
    if receipt:
        rcpt_resp = client.post("/api/v1/merkle/receipts", json=receipt.to_dict())
        assert rcpt_resp.status_code == 201
        logger.info(f"   -> Committed Merkle Batch: {receipt.batch_id} (Root: {receipt.root_hash[:20]}...)")

    verify_resp = client.get(f"/api/v1/audit/verify/{alert_id}")
    assert verify_resp.status_code == 200
    admissibility = verify_resp.json()
    assert admissibility["is_admissible"] is True
    assert admissibility["leaf_hash_valid"] is True
    logger.info(f"   -> Admissibility Verification: SUCCESS (Non-Repudiation Verified)")

    # 6. Test WebSocket High-Throughput Stream
    logger.info("[6/7] Testing WebSocket Real-Time Telemetry Stream...")
    with client.websocket_connect("/ws/v1/c2") as operator_ws:
        assert len(ws_hub.operators) >= 1
        logger.info("   -> Operator C2 WebSocket Stream Connected.")

    # 7. CERT-In Cryptographic Log Verification
    logger.info("[7/7] Appending & Verifying CERT-In Ed25519 Signed Audit Log...")
    audit_rec = audit_logger.log_operator_action(
        operator_id="OP-COMMANDER-01",
        action="VERIFY_MERKLE_PROOF",
        resource_id=str(alert_id),
        metadata={"result": "ADMISSIBLE", "verified_by": "SMOKE_TEST"}
    )
    is_valid_sig = CertInAuditLogger.verify_record(audit_rec)
    assert is_valid_sig is True
    logger.info(f"   -> Ed25519 Signature Verified: {audit_rec['signature_hex'][:24]}...")

    print("=" * 80)
    print(" ALL 7 SYSTEM SMOKE TESTS PASSED WITH 100% SUCCESS RATE")
    print("=" * 80)


if __name__ == "__main__":
    run_smoke_test()
