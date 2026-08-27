"""
Integration Tests for WebSocket Event Hub (Edge Ingestion & C2 Operator Broadcast).
"""

from datetime import datetime, timezone
import json
from uuid import uuid4
import pytest
from starlette.testclient import TestClient

import sys
sys.path.insert(0, "apps/central-gateway/src")
from main import app, ws_hub


def test_websocket_event_hub_operator_broadcast(monkeypatch):
    monkeypatch.setenv("EDGE_API_TOKEN", "TEST_EDGE_TOKEN_ONLY")
    client = TestClient(app)

    # 1. Connect Operator WebSocket
    with client.websocket_connect("/ws/v1/c2") as operator_ws:
        assert len(ws_hub.c2_operators) >= 1

        # 2. Connect Edge Node WebSocket with valid token
        with client.websocket_connect("/ws/v1/edge?node_id=EDGE-TEST-01&token=TEST_EDGE_TOKEN_ONLY") as edge_ws:
            alert_id = str(uuid4())
            sensor_id = str(uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()

            alert_payload = {
                "alert_id": alert_id,
                "bop_id": "BOP-ALPHA-01",
                "sensor_id": sensor_id,
                "timestamp": now_iso,
                "target_type": "PERSON",
                "threat_level": "HIGH",
                "centroid": {"latitude": 34.05, "longitude": 74.88, "altitude_m": 1600.0},
                "cot_xml_string": "<event/>",
                "evidence_cid": "bafybeiczsscdsbs7ffqz55asqdf32gvwlsdp4s8gshd",
                "merkle_leaf_hash": "f" * 64,
                "confidence": 0.94,
                "description": "Live streaming test alert from edge"
            }

            # Edge sends JSON string
            edge_ws.send_text(json.dumps(alert_payload))

            # Operator receives broadcasted payload in real time (<50ms)
            msg_text = operator_ws.receive_text()
            msg = json.loads(msg_text)
            assert msg["event"] == "TACTICAL_ALERT"
            assert msg["data"]["alert_id"] == alert_id
            assert msg["data"]["bop_id"] == "BOP-ALPHA-01"


def test_edge_websocket_rejects_unauthenticated_connection(monkeypatch):
    """Verifies that Edge WebSocket endpoint immediately rejects missing token."""
    monkeypatch.setenv("EDGE_API_TOKEN", "StrictDefenseToken999!")
    client = TestClient(app)

    # Missing token -> Rejected with 1008 policy violation
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/v1/edge?node_id=UNAUTHORIZED-EDGE"):
            pass


def test_edge_websocket_rejects_invalid_token(monkeypatch):
    """Verifies that Edge WebSocket endpoint rejects incorrect token."""
    monkeypatch.setenv("EDGE_API_TOKEN", "StrictDefenseToken999!")
    client = TestClient(app)

    with pytest.raises(Exception):
        with client.websocket_connect("/ws/v1/edge?node_id=HACKER-EDGE&token=WrongToken"):
            pass

