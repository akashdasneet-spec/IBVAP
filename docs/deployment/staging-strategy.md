# IBVAP Deployment Strategy

## Local Development vs. Staging Environments

### 1. Local Development (No Docker Required)
- Edge Engine: Independent Python virtualenv running local processing pipeline.
- Central Gateway: FastAPI running on SQLite (`sqlite+aiosqlite:///ibvap_gateway.db`) or local PostgreSQL.
- Web Dashboard: Next.js dev server (`pnpm --filter @ibvap/web-dashboard dev`) connected to `localhost:8000`.

### 2. Staging Deployment (Docker Compose)
- Multi-container architecture with PostgreSQL 16 (`pgvector`), IPFS Kubo daemon, FastAPI Gateway, and Next.js static/standalone container.
- Configurable environment arguments (`ARG NEXT_PUBLIC_GATEWAY_URL`, `ARG NEXT_PUBLIC_WS_URL`) injected at build time.
- All internal storage and DB ports isolated to `127.0.0.1` and container bridge networks.
