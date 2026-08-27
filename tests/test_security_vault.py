"""
Unit Tests for EvidenceVault AES-256-GCM Encryption and Packaging Engine.
"""

import pytest
from cryptography.exceptions import InvalidTag

from security.vault import EvidenceVault, MAGIC_HEADER


def test_evidence_bundle_packing_unpacking():
    dummy_frame = b"\xFF\xD8\xFF\xE0" + b"\x00" * 500 + b"\xFF\xD9"  # Fake JPEG
    dummy_video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000     # Fake MP4
    metadata = {
        "alert_id": "TEST-ALERT-001",
        "sensor_id": "SENSOR-01",
        "timestamp": "2026-08-27T12:00:00Z"
    }

    packed = EvidenceVault.pack_bundle(dummy_frame, dummy_video, metadata)
    assert packed.startswith(MAGIC_HEADER)

    # Unpack and verify
    unpacked_frame, unpacked_video, unpacked_meta = EvidenceVault.unpack_bundle(packed)
    assert unpacked_frame == dummy_frame
    assert unpacked_video == dummy_video
    assert unpacked_meta["alert_id"] == "TEST-ALERT-001"


def test_aes_256_gcm_encryption_decryption():
    valid_key = b"1" * 32
    vault = EvidenceVault(master_key=valid_key)
    plaintext = b"TOP-SECRET-TACTICAL-PAYLOAD-FOR-BOP-ALPHA-01"

    # Encrypt
    encrypted = vault.encrypt_payload(plaintext)
    assert len(encrypted) > len(plaintext)
    assert encrypted != plaintext

    # Decrypt
    decrypted = vault.decrypt_payload(encrypted)
    assert decrypted == plaintext


def test_aes_256_gcm_tamper_detection():
    """Verifies that any modification to the ciphertext or tag fails authentication with InvalidTag."""
    vault = EvidenceVault(master_key=b"A" * 32)
    plaintext = b"INTELLIGENT-BORDER-VIDEO-ANALYTICS-EVIDENCE"

    encrypted = bytearray(vault.encrypt_payload(plaintext))

    # Tamper with one byte in the ciphertext payload
    encrypted[-5] ^= 0xFF

    with pytest.raises(InvalidTag):
        vault.decrypt_payload(bytes(encrypted))


def test_package_encrypt_and_store():
    vault = EvidenceVault(master_key="0123456789abcdef" * 4)  # 64-hex string
    dummy_frame = b"JPEG_SNAPSHOT_DATA_12345"
    dummy_video = b"MP4_5SEC_ALERT_VIDEO_CLIP"
    metadata = {"alert_id": "ALERT-UUID-456", "bop": "BOP-ALPHA-01"}

    encrypted, cid = vault.package_encrypt_and_store(dummy_frame, dummy_video, metadata)
    assert len(encrypted) > 0
    assert cid.startswith("bafybeic")


def test_evidence_vault_key_fail_fast_in_production(monkeypatch):
    """Verifies that EvidenceVault strictly refuses to run if key is missing/invalid in production."""
    monkeypatch.delenv("EVIDENCE_MASTER_KEY", raising=False)

    # 1. Missing key without allow_ephemeral_key raises ValueError
    with pytest.raises(ValueError, match="EVIDENCE_MASTER_KEY is required"):
        EvidenceVault(master_key=None, allow_ephemeral_key=False)

    # 2. Key with invalid length raises ValueError
    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        EvidenceVault(master_key=b"too_short_key", allow_ephemeral_key=False)

    # 3. Setting allow_ephemeral_key=True allows test mode key generation
    vault_ephemeral = EvidenceVault(allow_ephemeral_key=True)
    assert len(vault_ephemeral.master_key) == 32


def test_evidence_vault_cache_quota_and_fifo_eviction(tmp_path):
    """
    P1-4 Regression Test: Verifies that EvidenceVault enforces max_cache_bytes
    and evicts oldest .bin files (FIFO by mtime) when quota is exceeded.
    """
    cache_dir = tmp_path / "quota_cache"
    cache_dir.mkdir()

    # Max cache capacity: 2500 bytes
    vault = EvidenceVault(
        master_key=b"Q" * 32,
        ipfs_api_url="http://127.0.0.1:9999",  # Force offline cache
        cache_dir=str(cache_dir),
        max_cache_bytes=2500
    )

    # 1. Store bundle 1 (approx 1000 bytes)
    payload1 = b"B" * 1000
    cid1 = vault.publish_to_ipfs(payload1)
    file1 = cache_dir / f"{cid1}.bin"
    assert file1.exists()

    # 2. Store bundle 2 (approx 1000 bytes)
    payload2 = b"C" * 1000
    cid2 = vault.publish_to_ipfs(payload2)
    file2 = cache_dir / f"{cid2}.bin"
    assert file2.exists()
    assert vault.get_cache_size_bytes() >= 2000

    # 3. Store bundle 3 (approx 1000 bytes) -> Total 3000 > 2500 limit
    # Bundle 1 (oldest) must be evicted
    payload3 = b"D" * 1000
    cid3 = vault.publish_to_ipfs(payload3)
    file3 = cache_dir / f"{cid3}.bin"
    assert file3.exists()

    # File 1 must have been evicted to make room, while File 2 and File 3 remain
    assert not file1.exists()
    assert file2.exists()
    assert file3.exists()
    assert vault.get_cache_size_bytes() <= 2500
