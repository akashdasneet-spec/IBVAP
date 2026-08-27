# IBVAP System Architecture & Boundaries

## Overview
The Intelligent Border Video Analytics Platform (IBVAP) operates across three distinct topological zones:

1. **Tactical Edge (`apps/edge-engine`)**
   - Runs independently on local edge nodes at Border Observation Posts (BOPs).
   - Ingests camera streams, performs local CV inference, virtual fence evaluation, and evidence packaging.
   - Communicates outbound with the Central Gateway over an authenticated transport interface (WebSocket/REST).
   - **Boundary Rule**: `apps/edge-engine` NEVER depends on `apps/web-dashboard` or direct database connections.

2. **Central Gateway (`apps/central-gateway`)**
   - High-throughput ingestion hub and API orchestrator built with FastAPI.
   - Manages relational state (PostgreSQL/SQLite), relays real-time incident broadcasts to authenticated C2 operators, and anchors cryptographic evidence.
   - **Boundary Rule**: Gateway acts as the single source of truth for all persisted state and C2 telemetry.

3. **Tactical Situation Room (`apps/web-dashboard`)**
   - Operator C2 tactical dashboard built with Next.js App Router, Tailwind CSS, and MapLibre GL.
   - **Boundary Rule**: The dashboard communicates ONLY with the Central Gateway via REST and WebSocket. It NEVER makes direct connections to PostgreSQL, IPFS, or edge cameras.

4. **Shared Data Contracts (`packages/core-types`)**
   - Houses the canonical Pydantic v2 schemas and TypeScript contracts.
   - Serves as the single domain contract specification across all applications.
