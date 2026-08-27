"""
Cryptographic Evidence Vault & IPFS Packaging Engine.
Direct module export from src.security.vault.
"""

from src.security.vault import (
    EvidenceVault,
    MAGIC_HEADER,
)

__all__ = ["EvidenceVault", "MAGIC_HEADER"]
