"""
Multi-Channel WebSocket Event Hub with Asynchronous Bounded Queues & Backpressure.
Protects the central event loop from lagging clients via drop-oldest backpressure queues.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import secrets
from typing import Any, Dict, List, Optional, Set
from uuid import UUID
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_core_types import TacticalAlert
from db.models import AlertModel

logger = logging.getLogger("gateway.ws_hub")

MAX_CLIENT_QUEUE_SIZE = 100


class ClientConnection:
    """Represents a connected client with its own bounded egress queue and sender task."""
    def __init__(self, websocket: WebSocket, role: str = "operator"):
        self.websocket = websocket
        self.role = role
        self.queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=MAX_CLIENT_QUEUE_SIZE)
        self.task: Optional[asyncio.Task] = None
        self.is_alive = True

    async def sender_loop(self):
        try:
            while self.is_alive:
                payload = await self.queue.get()
                await self.websocket.send_json(payload)
                self.queue.task_done()
        except Exception as exc:
            logger.debug(f"Client sender terminated: {exc}")
        finally:
            self.is_alive = False

    def enqueue(self, payload: Dict[str, Any]) -> bool:
        """Enqueues message. Drops oldest if full to avoid event loop backpressure."""
        if not self.is_alive:
            return False

        if self.queue.full():
            try:
                # Drop oldest non-critical message
                self.queue.get_nowait()
                self.queue.task_done()
                logger.warning(f"Backpressure: Dropped oldest message for slow {self.role} client.")
            except asyncio.QueueEmpty:
                pass

        try:
            self.queue.put_nowait(payload)
            return True
        except asyncio.QueueFull:
            return False


class WebSocketEventHub:
    """
    High-Throughput WebSocket Multiplexer with Bounded Queues & Backpressure.
    """

    def __init__(self):
        self.operators: Dict[WebSocket, ClientConnection] = {}
        self.edge_nodes: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    @property
    def c2_operators(self) -> Set[WebSocket]:
        return set(self.operators.keys())

    # --- Operator Registration with Dedicated Worker ---

    async def register_operator(self, websocket: WebSocket) -> None:
        await websocket.accept()
        client = ClientConnection(websocket, role="c2_operator")
        client.task = asyncio.create_task(client.sender_loop())
        async with self._lock:
            self.operators[websocket] = client
        logger.info(f"C2 Tactical Operator connected. Active operators: {len(self.operators)}")

    async def unregister_operator(self, websocket: WebSocket) -> None:
        async with self._lock:
            client = self.operators.pop(websocket, None)
        if client:
            client.is_alive = False
            if client.task:
                client.task.cancel()
        logger.info(f"C2 Tactical Operator disconnected. Remaining: {len(self.operators)}")

    # --- Edge Node Authentication & Connection Handlers ---

    async def authenticate_edge_connection(
        self,
        websocket: WebSocket,
        token: Optional[str] = None
    ) -> bool:
        """
        Validates edge client authentication prior to accepting telemetry.
        Inspects query parameter `token` or headers `x-edge-token` / `authorization`.
        Uses constant-time comparison (secrets.compare_digest) to prevent timing side-channels.
        Closes socket with policy violation (1008) if unauthenticated.
        """
        expected_token = os.getenv("EDGE_API_TOKEN", "REDACTED_HISTORICAL_SECRET")

        # Extract token from query params or headers
        presented_token = token
        if not presented_token:
            presented_token = websocket.headers.get("x-edge-token")
        if not presented_token:
            auth_header = websocket.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                presented_token = auth_header[7:].strip()

        if not presented_token or not secrets.compare_digest(presented_token, expected_token):
            logger.warning("Rejected unauthenticated Edge Node WebSocket connection attempt.")
            try:
                await websocket.close(code=1008, reason="Authentication failed: invalid or missing edge token")
            except Exception:
                pass
            return False

        return True

    async def register_edge_node(self, node_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.edge_nodes[node_id] = websocket
        logger.info(f"Edge Engine Node '{node_id}' linked. Active edge nodes: {len(self.edge_nodes)}")

    async def unregister_edge_node(self, node_id: str) -> None:
        async with self._lock:
            self.edge_nodes.pop(node_id, None)
        logger.info(f"Edge Engine Node '{node_id}' unlinked. Remaining: {len(self.edge_nodes)}")

    # --- Non-Blocking Broadcasting with Backpressure Protection ---

    async def broadcast_to_c2(self, event_type: str, data: Any) -> None:
        """
        Pushes payload to operator bounded queues without blocking event loop.
        """
        if not self.operators:
            return

        payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }

        dead_sockets: List[WebSocket] = []
        for ws, client in list(self.operators.items()):
            if not client.is_alive or not client.enqueue(payload):
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                for dead_ws in dead_sockets:
                    c = self.operators.pop(dead_ws, None)
                    if c and c.task:
                        c.task.cancel()

    async def handle_incoming_edge_alert(
        self,
        alert_payload: Dict[str, Any],
        db: Optional[AsyncSession] = None,
        tak_bridge: Optional[Any] = None
    ) -> TacticalAlert:
        """
        Deserializes TacticalAlert contract, dispatches to C2 bounded queues, relays to TAK, and persists.
        """
        alert = TacticalAlert.model_validate(alert_payload)

        # 1. Non-blocking push to C2 operator queues (<50ms)
        await self.broadcast_to_c2("TACTICAL_ALERT", alert.model_dump(mode="json"))

        # 2. Forward to TAK Server mesh if active
        if tak_bridge is not None:
            try:
                await tak_bridge.broadcast_alert(alert)
            except Exception as err:
                logger.error(f"PyTAK relay failed: {err}")

        # 3. Persist to Database if session provided
        if db is not None:
            try:
                db_record = AlertModel(
                    alert_id=str(alert.alert_id),
                    bop_id=alert.bop_id,
                    sensor_id=str(alert.sensor_id),
                    timestamp=alert.timestamp,
                    target_type=alert.target_type.value,
                    threat_level=alert.threat_level.value,
                    latitude=alert.centroid.latitude,
                    longitude=alert.centroid.longitude,
                    altitude_m=alert.centroid.altitude_m,
                    cot_xml_string=alert.cot_xml_string,
                    evidence_cid=alert.evidence_cid,
                    merkle_leaf_hash=alert.merkle_leaf_hash,
                    bounding_box=alert.bounding_box.model_dump() if alert.bounding_box else None,
                    confidence=alert.confidence,
                    description=alert.description
                )
                db.add(db_record)
                await db.commit()
            except Exception as dberr:
                logger.error(f"Failed to persist alert {alert.alert_id}: {dberr}")

        return alert
