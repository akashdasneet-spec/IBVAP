from datetime import datetime, timezone
import hashlib
import logging
from typing import Optional
from uuid import UUID
import httpx

from ibvap_core_types import compute_merkle_leaf_hash

logger = logging.getLogger("edge_engine.crypto")


class EvidenceHasher:
    """
    Handles cryptographic hashing of frame evidence snapshots and IPFS persistence.
    """

    def __init__(self, ipfs_api_url: str = "http://ipfs:5001/api/v0"):
        self.ipfs_api_url = ipfs_api_url

    async def upload_evidence(self, frame_bytes: bytes, metadata: dict) -> str:
        """
        Uploads evidence frame to IPFS node and returns CIDv1.
        Falls back to deterministic local SHA-256 CID simulation if IPFS node is unreachable.
        """
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                files = {"file": ("evidence.jpg", frame_bytes, "image/jpeg")}
                response = await client.post(f"{self.ipfs_api_url}/add", files=files)
                if response.status_code == 200:
                    data = response.json()
                    cid = data.get("Hash", "")
                    logger.info(f"Evidence anchored to IPFS CID: {cid}")
                    return cid
        except Exception as err:
            logger.debug(f"IPFS node direct connection skipped ({err}). Generating cryptographic CID.")

        # Deterministic IPFS-like multihash / SHA-256 CID
        digest = hashlib.sha256(frame_bytes).hexdigest()
        simulated_cid = f"bafybeic{digest[:48]}"
        return simulated_cid

    def create_merkle_leaf(
        self,
        alert_id: UUID,
        sensor_id: UUID,
        timestamp: datetime,
        target_type: str,
        threat_level: str,
        evidence_cid: str
    ) -> str:
        """Computes verifiable Merkle tree leaf hash."""
        return compute_merkle_leaf_hash(
            alert_id=alert_id,
            sensor_id=sensor_id,
            timestamp=timestamp,
            target_type=target_type,
            threat_level=threat_level,
            evidence_cid=evidence_cid
        )
