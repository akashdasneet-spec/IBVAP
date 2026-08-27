# IBVAP Production Deployment Architecture

## 1. System Architecture

```
[ Next.js 14 Dashboard ] (Vercel Edge / Serverless)
          │
          │ HTTPS REST / WSS WebSockets
          ▼
[ Central Gateway ] (Persistent Container: Render / Railway / Fly.io / VPS)
     ├── PostgreSQL 16 + pgvector (Managed DB: Neon / Supabase / Render Postgres)
     ├── IPFS Kubo Node (Evidence Blob Storage)
     └── PyTAK C4ISR Mesh (UDP Tactical Broadcaster)
          ▲
          │ Authenticated WSS / CoT XML
[ Edge Engine Nodes ] (Physical NVIDIA Jetson / Edge Devices at BOPs)
```

### Why WebSockets Are Not Hosted on Vercel Serverless
The Central Gateway orchestrates persistent, bidirectional WebSocket channels (`/ws/v1/c2` for operator situation room feeds and `/ws/v1/edge` for edge node telemetry streams) with in-memory bounded queues, backpressure handling, background tasks, and UDP PyTAK relays. 

Serverless environments (like Vercel Functions) have short execution timeouts (10–60s), lack persistent TCP/UDP connection state, and cannot maintain long-lived in-memory client rosters. Therefore, the FastAPI Gateway must run in a persistent container/web service environment.

---

## 2. Component Deployment Breakdown

| Subsystem | Host / Provider | Requirements / Configuration |
|---|---|---|
| **Web Dashboard** | **Vercel** | Next.js 14 App Router. Root Directory: `apps/web-dashboard`. Build: `pnpm --filter @ibvap/web-dashboard build`. |
| **Central Gateway** | **Persistent Container** (Render / Railway / Fly.io / Docker VPS) | Python 3.11+, Uvicorn. Startup command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`. |
| **Database** | **Managed PostgreSQL 16** (Neon / Supabase / Render / Docker) | PostgreSQL 16 with `pgvector` and `uuid-ossp` extensions enabled. Schema auto-initialized on gateway lifespan startup. |
| **IPFS Node** | **Dedicated Node / Container** (Local or RPC) | IPFS Kubo (`v0.28.0`). RPC port `5001` restricted to internal network / gateway. |
| **Edge Node** | **Physical Edge PC / NVIDIA Jetson** | Runs on-premise at Border Outposts. Connects upstream via authenticated WebSocket. |

---

## 3. Environment Variables & Secret Management

### Frontend (Vercel — Public Environment Variables)
*Never put secrets or private keys in frontend environment variables.*
- `NEXT_PUBLIC_GATEWAY_URL`: Base HTTP/HTTPS URL of the deployed Central Gateway (e.g. `https://gateway.example.com`).
- `NEXT_PUBLIC_WS_URL`: WebSocket WSS URL for real-time telemetry (e.g. `wss://gateway.example.com/ws/v1/c2`).

### Backend Gateway (Persistent Service — Private Secrets)
- `PORT`: Service listen port (default `8000`, set automatically by cloud runtimes).
- `IBVAP_ENV`: `production` (enforces strict key checking and fail-closed auth).
- `DATABASE_URL`: Async PostgreSQL connection string (`postgresql+asyncpg://user:pass@host:5432/dbname`).
- `EDGE_API_TOKEN`: Cryptographically secure shared secret for authenticating edge nodes.
- `CORS_ALLOWED_ORIGINS`: Comma-separated list of allowed dashboard origins (e.g. `https://ibvap-dashboard.vercel.app`).
- `CERTIN_SIGNING_KEY_PATH` or `CERTIN_SIGNING_KEY_HEX`: Ed25519 private key for signing audit records.
- `IPFS_API_URL`: URL to IPFS RPC API (`http://ipfs:5001/api/v0`).
- `TAK_SERVER_URL`: UDP multicast address for PyTAK bridge (`udp://239.2.3.1:6969`).

---

## 4. Deployment Order

1. **Database**: Provision PostgreSQL 16 database with `vector` and `uuid-ossp` extensions enabled.
2. **Central Gateway**: Deploy persistent container service with `DATABASE_URL`, `EDGE_API_TOKEN`, and `CORS_ALLOWED_ORIGINS`.
3. **Health Check Validation**: Verify `GET /health/liveness` and `GET /health/readiness` respond with HTTP 200.
4. **Web Dashboard**: Deploy to Vercel setting `NEXT_PUBLIC_GATEWAY_URL` and `NEXT_PUBLIC_WS_URL` to the deployed gateway endpoint.
5. **Edge Nodes**: Configure physical nodes with gateway WSS URL and matching `EDGE_API_TOKEN`.
