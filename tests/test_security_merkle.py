"""
Unit Tests for Binary Merkle Audit Ledger and Inclusion Proofs.
"""

from datetime import datetime, timezone
import pytest

from security.merkle import (
    BinaryMerkleTree,
    MerkleAuditLedger,
    MerkleReceipt,
    compute_alert_leaf_hash,
    hash_pair,
)


def test_leaf_hash_computation():
    now = datetime.now(timezone.utc)
    cid = "bafybeiczsscdsbs7ffqz55asqdf32gvwlsdp4s8gshd"
    bop_id = "BOP-ALPHA-01"
    sensor_id = "SENSOR-TOWER-01"

    leaf = compute_alert_leaf_hash(cid, now, bop_id, sensor_id)
    assert len(leaf) == 64
    assert isinstance(leaf, str)

    # Deterministic output for same input
    leaf2 = compute_alert_leaf_hash(cid, now, bop_id, sensor_id)
    assert leaf == leaf2


def test_binary_merkle_tree_root():
    leaves = [f"{i:064x}" for i in range(4)]
    tree = BinaryMerkleTree(leaves)

    # Expected root calculation:
    # h01 = hash(l0, l1)
    # h23 = hash(l2, l3)
    # root = hash(h01, h23)
    h01 = hash_pair(leaves[0], leaves[1])
    h23 = hash_pair(leaves[2], leaves[3])
    expected_root = hash_pair(h01, h23)

    assert tree.root == expected_root


def test_merkle_proof_generation_and_verification():
    # Tree with 5 leaves (tests odd number node duplication)
    leaves = [f"{i:04x}" + "a" * 60 for i in range(5)]
    tree = BinaryMerkleTree(leaves)
    root = tree.root

    for i in range(len(leaves)):
        proof = tree.get_proof(i)
        # Verify valid proof
        is_valid = BinaryMerkleTree.verify_proof(leaves[i], proof, root)
        assert is_valid is True

        # Verify that tampered leaf hash fails verification
        tampered_leaf = leaves[i][:-2] + "ff"
        is_tampered_valid = BinaryMerkleTree.verify_proof(tampered_leaf, proof, root)
        assert is_tampered_valid is False


def test_merkle_audit_ledger_batching():
    ledger = MerkleAuditLedger(batch_size=3)
    now = datetime.now(timezone.utc)

    # Add 2 alerts (not yet at threshold)
    ledger.record_alert("cid_1", now, "BOP-1", "S-1")
    ledger.record_alert("cid_2", now, "BOP-1", "S-2")
    assert ledger.should_seal() is False

    # Add 3rd alert -> triggers batch seal
    ledger.record_alert("cid_3", now, "BOP-1", "S-3")
    assert ledger.should_seal() is True

    receipt = ledger.sealed_receipts[-1] if ledger.sealed_receipts else ledger.seal_batch()
    assert receipt is not None
    assert receipt.batch_id.startswith("BATCH-")
    assert receipt.leaf_count == 3
    assert len(receipt.root_hash) == 64
    assert len(receipt.leaves) == 3
