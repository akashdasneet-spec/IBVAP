"""
C4ISR Security Proxy Shim.
Allows direct imports from /apps/edge-engine/security.
"""

from src.security.cot import CoTGenerator, MIL_STD_2525_MAP
from src.security.vault import EvidenceVault
from src.security.merkle import (
    BinaryMerkleTree,
    MerkleAuditLedger,
    MerkleReceipt,
    compute_alert_leaf_hash,
    hash_pair,
)

__all__ = [
    "CoTGenerator",
    "MIL_STD_2525_MAP",
    "EvidenceVault",
    "BinaryMerkleTree",
    "MerkleAuditLedger",
    "MerkleReceipt",
    "compute_alert_leaf_hash",
    "hash_pair",
]
