"""
Central Gateway FastAPI Application Entrypoint.
Orchestrates WebSocket Event Hub, REST Endpoints, and PyTAK C4ISR Relay.
"""

from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import sys
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Safe path bootstrap for packages and submodules
_current_file = Path(__file__).resolve()
_gateway_src = _current_file.parent

if str(_gateway_src) not in sys.path:
    sys.path.insert(0, str(_gateway_src))

# Safe fallback for core-types if not installed in environment
try:
    import ibvap_core_types
except ImportError:
    for _parent in _current_file.parents:
        _candidate = _parent / "packages" / "core-types" / "src"
        if _candidate.is_dir():
            sys.path.insert(0, str(_candidate))
            break

from api.routes import router as api_router
from api.ws_hub import WebSocketEventHub
from cot.pytak_bridge import PyTAKBridge
from db.session import async_session_factory, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("gateway.main")

# Global Singletons
ws_hub = WebSocketEventHub()
tak_bridge = PyTAKBridge()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing IBVAP Central Gateway C2 Hub...")
    
    # 1. Initialize DB Schema
    try:
        await init_db()
        logger.info("Database schema initialized successfully.")
    except Exception as exc:
        logger.warning(f"Database bootstrap warning: {exc}")

    # 2. Start PyTAK tactical broadcaster
    await tak_bridge.start()

    yield

    logger.info("Shutting down Central Gateway...")
    await tak_bridge.stop()


from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

app = FastAPI(
    title="IBVAP Central Gateway C2",
    description="Command & Control Tactical Hub for Intelligent Border Video Analytics Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration: restrict allowed origins (env CORS_ALLOWED_ORIGINS)
raw_cors = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000")
allowed_origins = [orig.strip() for orig in raw_cors.split(",") if orig.strip()]

# Prohibit wildcard "*" when credentials are true in production
if "*" in allowed_origins:
    if os.getenv("IBVAP_ENV", "development").lower() == "production":
        raise ValueError("Wildcard '*' CORS origin is strictly prohibited with allow_credentials in production.")
    else:
        logger.warning("Wildcard CORS '*' origin configured in non-production development mode.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

app.include_router(api_router)


# --- Health & Readiness Probes (P1-5) ---

@app.get("/health", tags=["System"])
@app.get("/health/liveness", tags=["System"])
@app.get("/api/v1/health/liveness", tags=["System"])
async def health_liveness():
    """
    Liveness probe: verifies process is alive and responding.
    Does not fail if external dependencies are temporarily degraded.
    """
    return {
        "status": "ALIVE",
        "system": "IBVAP Central Gateway C2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }


@app.get("/health/readiness", tags=["System"])
@app.get("/api/v1/health/readiness", tags=["System"])
async def health_readiness(response: Response):
    """
    Readiness probe: checks database connectivity and internal services.
    Returns HTTP 503 Service Unavailable if database connection is failing.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    db_ok = False
    ipfs_ok = False

    # 1. Database Connectivity Check
    try:
        async with async_session_factory() as session:
            res = await session.execute(text("SELECT 1"))
            if res.scalar() == 1:
                db_ok = True
    except Exception as exc:
        logger.warning(f"Database probe unready: {exc}")

    # 2. IPFS Daemon Check (non-fatal)
    ipfs_url = os.getenv("IPFS_API_URL", "http://localhost:5001").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.post(f"{ipfs_url}/api/v0/version")
            if resp.status_code == 200:
                ipfs_ok = True
    except Exception:
        pass

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "UNREADY",
            "system": "IBVAP Central Gateway C2",
            "database": "DISCONNECTED",
            "ipfs": "CONNECTED" if ipfs_ok else "DISCONNECTED",
            "timestamp": now_utc,
            "error": "Primary relational database is unreachable"
        }

    return {
        "status": "READY",
        "system": "IBVAP Central Gateway C2",
        "database": "CONNECTED",
        "ipfs": "CONNECTED" if ipfs_ok else "DEGRADED",
        "timestamp": now_utc,
        "active_c2_operators": len(ws_hub.operators),
        "version": "1.0.0"
    }


# --- 1. C2 Operator Dashboard WebSocket Streams ---

@app.websocket("/ws/v1/c2")
@app.websocket("/ws/telemetry")
async def websocket_c2_operator_endpoint(websocket: WebSocket):
    """
    Sub-50ms live incident and tactical telemetry broadcast stream for C2 Dashboards.
    """
    await ws_hub.register_operator(websocket)
    try:
        while True:
            # Receive operator commands / ping heartbeats
            data = await websocket.receive_text()
            logger.debug(f"Operator command received: {data}")
    except WebSocketDisconnect:
        await ws_hub.unregister_operator(websocket)
    except Exception as exc:
        logger.debug(f"Operator connection closed: {exc}")
        await ws_hub.unregister_operator(websocket)


# --- 2. Edge Node Ingestion Stream ---

@app.websocket("/ws/v1/edge")
async def websocket_edge_ingest_endpoint(
    websocket: WebSocket,
    node_id: str = "EDGE-01",
    token: Optional[str] = None
):
    """
    High-throughput authenticated ingestion channel for incoming Edge AI Node alerts and CoT XML.
    """
    # 1. Enforce authentication before accepting telemetry stream
    is_auth = await ws_hub.authenticate_edge_connection(websocket, token=token)
    if not is_auth:
        return

    await ws_hub.register_edge_node(node_id, websocket)
    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                alert_dict = json.loads(raw_text)
                async with async_session_factory() as session:
                    await ws_hub.handle_incoming_edge_alert(alert_dict, db=session, tak_bridge=tak_bridge)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON payload from edge node {node_id}")
    except WebSocketDisconnect:
        await ws_hub.unregister_edge_node(node_id)
    except Exception as exc:
        logger.debug(f"Edge node {node_id} stream closed: {exc}")
        await ws_hub.unregister_edge_node(node_id)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("GATEWAY_PORT", "8000")))
    reload = os.getenv("IBVAP_ENV", "production").lower() != "production"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
