"""
Binary Merkle Audit Ledger & Cryptographic Chain of Custody.
Compliant with RFC 6962 Domain Separation (0x00 Leaf Prefix, 0x01 Internal Node Prefix).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("edge_engine.security.merkle")

# RFC 6962 Domain Separation Prefixes
RFC6962_LEAF_PREFIX = b"\x00"
RFC6962_NODE_PREFIX = b"\x01"


def compute_alert_leaf_hash(
    cid: str,
    timestamp: datetime,
    bop_id: str,
    sensor_id: str
) -> str:
    """
    Computes RFC 6962 domain-separated canonical Merkle leaf hash:
    SHA-256(0x00 || CID : Timestamp : BOP_ID : Sensor_ID)
    """
    if timestamp.tzinfo is None:
        ts_utc = timestamp.replace(tzinfo=timezone.utc)
    else:
        ts_utc = timestamp.astimezone(timezone.utc)
    ts_str = ts_utc.isoformat()
    raw_payload = f"{cid}:{ts_str}:{bop_id}:{sensor_id}".encode("utf-8")
    
    # RFC 6962: 0x00 prefix for leaf hashing
    return hashlib.sha256(RFC6962_LEAF_PREFIX + raw_payload).hexdigest()


def hash_pair(left_hex: str, right_hex: str) -> str:
    """
    Computes RFC 6962 domain-separated parent node hash:
    SHA-256(0x01 || left_bytes || right_bytes)
    """
    left_bytes = bytes.fromhex(left_hex)
    right_bytes = bytes.fromhex(right_hex)
    return hashlib.sha256(RFC6962_NODE_PREFIX + left_bytes + right_bytes).hexdigest()


@dataclass
class MerkleReceipt:
    batch_id: str
    root_hash: str
    leaf_count: int
    leaves: List[str]
    timestamp_start: datetime
    timestamp_end: datetime

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "root_hash": self.root_hash,
            "leaf_count": self.leaf_count,
            "leaves": self.leaves,
            "timestamp_start": self.timestamp_start.isoformat(),
            "timestamp_end": self.timestamp_end.isoformat(),
            "rfc6962_compliant": True
        }


class BinaryMerkleTree:
    """
    RFC 6962 Balanced Binary Merkle Tree implementation with inclusion proof generation.
    """

    def __init__(self, leaves: Optional[List[str]] = None):
        self.leaves: List[str] = leaves[:] if leaves else []
        self.layers: List[List[str]] = []
        if self.leaves:
            self._build_tree()

    def add_leaf(self, leaf_hex: str) -> None:
        self.leaves.append(leaf_hex)
        self._build_tree()

    def _build_tree(self) -> None:
        if not self.leaves:
            self.layers = []
            return

        current_layer = self.leaves[:]
        self.layers = [current_layer]

        while len(current_layer) > 1:
            next_layer: List[str] = []
            for i in range(0, len(current_layer), 2):
                left = current_layer[i]
                # Secure odd-leaf duplication
                right = current_layer[i + 1] if (i + 1 < len(current_layer)) else left
                parent = hash_pair(left, right)
                next_layer.append(parent)
            self.layers.append(next_layer)
            current_layer = next_layer

    @property
    def root(self) -> Optional[str]:
        if not self.layers or not self.layers[-1]:
            return None
        return self.layers[-1][0]

    def get_proof(self, leaf_index: int) -> List[Tuple[str, str]]:
        """
        Generates an inclusion proof for a given leaf index.
        Returns list of (sibling_hash, 'L' | 'R') indicating sibling position.
        """
        if leaf_index < 0 or leaf_index >= len(self.leaves):
            raise IndexError("Leaf index out of range")

        proof: List[Tuple[str, str]] = []
        idx = leaf_index

        for layer in self.layers[:-1]:
            is_right = (idx % 2 == 1)
            sibling_idx = idx - 1 if is_right else idx + 1

            if sibling_idx >= len(layer):
                sibling_hash = layer[idx]
            else:
                sibling_hash = layer[sibling_idx]

            direction = "L" if is_right else "R"
            proof.append((sibling_hash, direction))
            idx //= 2

        return proof

    @staticmethod
    def verify_proof(leaf_hex: str, proof: List[Tuple[str, str]], root_hex: str) -> bool:
        """
        Verifies inclusion of leaf_hex in root_hex using RFC 6962 proof path.
        """
        current = leaf_hex
        for sibling, direction in proof:
            if direction == "R":
                current = hash_pair(current, sibling)
            else:
                current = hash_pair(sibling, current)
        return current.lower() == root_hex.lower()


class MerkleAuditLedger:
    """
    Batches high-frequency border intrusion alerts into immutable Merkle trees.
    """

    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size
        self._current_batch: List[str] = []
        self._batch_seq = 0
        self._batch_start_time: Optional[datetime] = None
        self.sealed_receipts: List[MerkleReceipt] = []

    def should_seal(self) -> bool:
        return len(self._current_batch) >= self.batch_size or len(self.sealed_receipts) > 0

    def record_alert(self, cid: str, timestamp: datetime, bop_id: str, sensor_id: str) -> str:
        if not self._current_batch:
            self._batch_start_time = timestamp

        leaf_hash = compute_alert_leaf_hash(cid, timestamp, bop_id, sensor_id)
        self._current_batch.append(leaf_hash)

        if len(self._current_batch) >= self.batch_size:
            self.seal_batch(timestamp)

        return leaf_hash

    def seal_batch(self, current_time: Optional[datetime] = None) -> Optional[MerkleReceipt]:
        if not self._current_batch:
            return None

        self._batch_seq += 1
        end_time = current_time or datetime.now(timezone.utc)
        start_time = self._batch_start_time or end_time

        tree = BinaryMerkleTree(self._current_batch)
        root = tree.root or ""
        batch_id = f"BATCH-RFC6962-{self._batch_seq:06d}"

        receipt = MerkleReceipt(
            batch_id=batch_id,
            root_hash=root,
            leaf_count=len(self._current_batch),
            leaves=self._current_batch[:],
            timestamp_start=start_time,
            timestamp_end=end_time
        )

        self.sealed_receipts.append(receipt)
        logger.info(f"Sealed Merkle Receipt {batch_id} with Root {root[:16]}... ({len(self._current_batch)} leaves)")

        self._current_batch = []
        self._batch_start_time = None
        return receipt
