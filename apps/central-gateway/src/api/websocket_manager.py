import logging
from typing import Any, Dict, List
from fastapi import WebSocket

logger = logging.getLogger("gateway.ws_manager")


class WebSocketManager:
    """Manages active Web Dashboard operator sessions."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Operator connected to C2 feed. Total active operators: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Operator disconnected. Remaining active: {len(self.active_connections)}")

    async def broadcast_json(self, message: Dict[str, Any]) -> None:
        """Broadcasts tactical telemetry payload to all active C2 operators."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as exc:
                logger.warning(f"Failed to push WebSocket message: {exc}")
                disconnected.append(connection)

        for dead_conn in disconnected:
            self.disconnect(dead_conn)
