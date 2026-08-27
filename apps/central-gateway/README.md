# IBVAP Central Gateway

Command & Control (C2) Tactical Hub and PyTAK Bridge for the Intelligent Border Video Analytics Platform.

## Key Endpoints
- `GET /health/liveness`: Container liveness probe
- `GET /health/readiness`: Database & dependency readiness probe
- `WS /ws/v1/c2`: Operator telemetry feed
- `WS /ws/v1/edge`: Edge node alert ingestion stream
