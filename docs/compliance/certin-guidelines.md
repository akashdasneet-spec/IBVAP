# CERT-In Compliance & Cryptographic Audit Trails

## Requirements
1. **Immutable Log Integrity**: All C2 operator actions (alert dismissals, verification requests, boundary configuration updates) must be recorded chronologically.
2. **Ed25519 Digital Signatures**: Every audit record payload is signed with an Ed25519 private key.
3. **Key Persistence**: Private keys must be stored in secure filesystem locations (file permissions `0600`) or dedicated HSMs, never generated as ephemeral keys in production.
4. **Non-Repudiation**: Merkle tree roots allow verifying that specific event records existed at specific audit timestamps.
