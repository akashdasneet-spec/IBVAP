# Intelligent Border Video Analytics Platform (IBVAP)
### Modular Monolith Architecture for Defense & Border Security Operations

IBVAP is an edge-to-tactical C2 (Command and Control) platform engineered for Border Outpost (BOP) security, automated target recognition, intrusion detection across restricted polygons, and low-latency Cursor-on-Target (CoT) integration with ATAK/WinTAK tactical networks.

---

## 1. System Architecture

```
                                  [ Tactical Perimeter Sensors ]
                                                │
                                    (RTSP / H.264 Stream)
                                                ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ apps/edge-engine (NVIDIA TensorRT + GStreamer)                                         │
  │  ├── Ingestion : Hardware-accelerated NVDEC / RTSP                                     │
  │  ├── Inference : YOLO FP16 Detection + OSNet 512-d ReID Extractor                      │
  │  ├── Analytics : Ray-casting polygon intersection & tripwire detection                 │
  │  └── Security  : SHA-256 Merkle leaf computation & IPFS snapshot hashing               │
  └────────────────────────────────────────┬───────────────────────────────────────────────┘
                                           │ (HTTP REST / WebSocket Telemetry)
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ apps/central-gateway (FastAPI + SQLAlchemy + PyTAK Bridge)                             │
  │  ├── C2 REST API       : Sensor registry, Alert triage, ReID watchlist lookup           │
  │  ├── Database Engine   : PostgreSQL 16 + pgvector (512-d HNSW) + PostGIS               │
  │  ├── PyTAK Broadcaster : CoT (MIL-STD-2525) XML generator & UDP/TLS multicast mesh     │
  │  └── Event Bus         : Real-time WebSocket multiplexer                               │
  └─────────────┬──────────────────────────────────────────────────────────┬───────────────┘
                │                                                          │
                ▼ (WebSocket Telemetry)                                    ▼ (PyTAK CoT Stream)
  ┌──────────────────────────────────────────────┐        ┌────────────────────────────────┐
  │ apps/web-dashboard (Next.js 14 + MapLibre GL)│        │ ATAK / WinTAK Tactical EUDs    │
  │  ├── Tactical Geospatial Map                 │        │  ├── MIL-STD-2525 Map Markers  │
  │  ├── Real-time Optical Stream HUD            │        │  ├── Drone / Target Tracks     │
  │  └── Tamper-proof Merkle Audit Feed          │        │  └── Situational Geo-Fencing   │
  └──────────────────────────────────────────────┘        └────────────────────────────────┘
```

---

## 2. Directory Layout

```
.
├── .dockerignore
├── .gitignore
├── README.md
├── package.json                       # Monorepo NPM/pnpm workspace
├── pnpm-workspace.yaml                # pnpm workspaces definition
├── pyproject.toml                     # Python workspace (uv / hatch / ruff)
├── turbo.json                         # Turborepo build orchestration
│
├── apps/
│   ├── edge-engine/                   # Edge AI Node
│   │   ├── Dockerfile.edge
│   │   ├── pyproject.toml
│   │   └── src/
│   │       ├── analytics/             # Polygon collision & intrusion logic
│   │       ├── crypto/                # Merkle leaf hashing & IPFS client
│   │       ├── inference/             # TensorRT FP16 execution & 512-d ReID
│   │       ├── pipeline/              # GStreamer hardware-accelerated ingestion
│   │       └── main.py                # Edge orchestration loop
│   │
│   ├── central-gateway/               # Central C2 Hub & TAK Bridge
│   │   ├── Dockerfile.gateway
│   │   ├── pyproject.toml
│   │   └── src/
│   │       ├── api/                   # REST routes & WebSocket manager
│   │       ├── cot/                   # PyTAK tactical CoT broadcaster
│   │       ├── db/                    # SQLAlchemy 2.0 async models & pgvector
│   │       └── main.py                # Gateway API entrypoint
│   │
│   └── web-dashboard/                 # Tactical C2 Web Dashboard
│       ├── Dockerfile.web
│       ├── package.json
│       ├── tsconfig.json
│       ├── tailwind.config.ts
│       └── src/
│           ├── app/                   # Next.js 14 App Router
│           └── components/            # TacticalMap (MapLibre), StreamHUD, AlertFeed
│
├── packages/
│   └── core-types/                    # Single Source of Truth Contracts
│       ├── package.json               # TypeScript bindings package
│       ├── pyproject.toml             # Pydantic v2 schema package
│       └── src/
│           ├── python/                # SensorConfig, BoundingBox, TacticalAlert, etc.
│           └── typescript/            # Mirrored TypeScript interfaces
│
└── deploy/
    ├── docker-compose.yml             # Full stack with NVIDIA GPU runtime passthrough
    ├── .env.example                   # Environment configuration
    └── init-db.sql                    # Postgres schema init with pgvector & PostGIS
```

---

## 3. Core Data Contracts (`packages/core-types`)

All telemetry and contracts are strongly typed using **Pydantic v2** with mirrored **TypeScript** definitions:

### `SensorConfig`
```python
from ibvap_core_types import SensorConfig, GeoPoint, PolygonCoordinate

config = SensorConfig(
    id="a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    name="CAM-NORTH-TOWER-01",
    rtsp_url="rtsps://camera.sector-alpha.internal:554/live",
    gps=GeoPoint(latitude=34.052235, longitude=74.885628, altitude_m=1620.0),
    bop_sector_id="BOP-SECTOR-ALPHA-01",
    active_polygon_coordinates=[
        PolygonCoordinate(x=0.2, y=0.3),
        PolygonCoordinate(x=0.8, y=0.3),
        PolygonCoordinate(x=0.85, y=0.9),
        PolygonCoordinate(x=0.15, y=0.9),
    ],
    fps_limit=30
)
```

### `TacticalAlert`
Includes automatic generation of **MIL-STD-2525 Cursor-on-Target XML** and **SHA-256 Merkle Leaf Hash**:
```python
from ibvap_core_types import TacticalAlert, TargetType, ThreatLevel, GeoCentroid

alert = TacticalAlert.create(
    bop_id="BOP-SECTOR-ALPHA-01",
    sensor_id=config.id,
    target_type=TargetType.PERSON,
    threat_level=ThreatLevel.HIGH,
    centroid=GeoCentroid(latitude=34.0528, longitude=74.8862, altitude_m=1622.0),
    evidence_cid="bafybeiczsscdsbs7ffqz55asqdf32gvwlsdp4s8gshd",
    confidence=0.94,
    description="Intruder breached northern perimeter restricted polygon."
)
```

---

## 4. Quickstart & Deployment

### Prerequisites
- Docker Engine & Docker Compose v2+
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) (for TensorRT hardware acceleration on edge node)

### Launching the Full Stack
```bash
# 1. Enter deployment directory
cd deploy

# 2. Configure environment
cp .env.example .env

# 3. Start unified stack with GPU passthrough, IPFS, Postgres/pgvector, Gateway, Edge & Dashboard
docker compose up --build -d
```

### Service Endpoints
| Component | Endpoint | Description |
|---|---|---|
| **Web Dashboard** | `http://localhost:3000` | Tactical Geospatial Map & Video C2 |
| **Central Gateway API** | `http://localhost:8000/docs` | OpenAPI / Swagger Interactive Docs |
| **Gateway WebSocket** | `ws://localhost:8000/ws/telemetry` | Real-time C2 Telemetry Stream |
| **PyTAK Multicast** | `udp://239.2.3.1:6969` | Cursor-on-Target feed for ATAK |
| **Local IPFS Gateway** | `http://localhost:8080/ipfs/<CID>` | Tamper-proof Cryptographic Evidence |
| **PostgreSQL (pgvector)** | `localhost:5432` | PostGIS + 512-d Vector Watchlist |
