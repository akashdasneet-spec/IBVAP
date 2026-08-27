# IBVAP Security Architecture & Threat Model

## 1. Zero Trust Network Boundaries
- **Edge-to-Gateway**: Authenticated via shared token or mutual TLS (mTLS). Unauthenticated edge connections are dropped immediately with code 1008.
- **Operator-to-Gateway**: Authenticated WebSockets with strict CORS restrictions and role-based access control.
- **Port Exposure**: Relational databases (PostgreSQL) and storage daemons (IPFS Kubo RPC) are bound strictly to `127.0.0.1` and internal docker network `ibvap-tactical-net`.

## 2. Cryptographic Custody
- **Evidence Vault**: Packaged with AES-256-GCM using 32-byte master keys (`EVIDENCE_MASTER_KEY`). Missing keys in production cause immediate fail-fast.
- **Non-Repudiation**: Merkle tree proofs generated using RFC 6962 binary structures.
- **Audit Logging**: CERT-In compliant audit log signing using persistent Ed25519 asymmetric keys.
