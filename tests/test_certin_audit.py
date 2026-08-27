"""
Regression and Security Tests for CERT-In Ed25519 Cryptographic Audit Logger (P0-4).
Validates persistent key loading, identity stability across restarts, signature verification,
and safe failure when keys are missing in production.
"""

from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

import sys
sys.path.insert(0, "apps/central-gateway/src")
from services.certin_audit import CertInAuditLogger


def test_certin_audit_persistent_key_from_pem_file(tmp_path):
    """
    Test 1: Proves that loading the same PEM key file across separate logger instances
    (simulating gateway restarts) produces the exact same public key identity.
    """
    key_path = tmp_path / "certin_audit_key.pem"

    # Generate and save a persistent Ed25519 private key
    orig_priv = ed25519.Ed25519PrivateKey.generate()
    pem_bytes = orig_priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    key_path.write_bytes(pem_bytes)

    # 1. Start gateway instance 1
    logger_1 = CertInAuditLogger(key_path=str(key_path))
    pub_key_1 = logger_1.public_key_hex

    # 2. Simulate gateway restart (instance 2)
    logger_2 = CertInAuditLogger(key_path=str(key_path))
    pub_key_2 = logger_2.public_key_hex

    assert pub_key_1 == pub_key_2
    assert pub_key_1 == orig_priv.public_key().public_bytes_raw().hex()


def test_certin_audit_signature_verification_across_restarts(tmp_path):
    """
    Test 2: Proves that an audit log entry signed before a gateway restart can be
    verified successfully after restart using the persisted public key.
    """
    key_path = tmp_path / "certin_restart_key.pem"
    orig_priv = ed25519.Ed25519PrivateKey.generate()
    key_path.write_bytes(
        orig_priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    )

    # Instance 1 logs an action before restart
    logger_before = CertInAuditLogger(key_path=str(key_path))
    record = logger_before.log_operator_action(
        operator_id="COMMANDER-ALPHA-01",
        action="DISMISS_FALSE_ALARM",
        resource_id="ALERT-9988-7766",
        metadata={"reason": "Wild boar detected in Sector 4"}
    )

    # Instance 2 (after restart) verifies the recorded log entry
    logger_after = CertInAuditLogger(key_path=str(key_path))
    is_valid = logger_after.verify_record(record)
    assert is_valid is True

    # Tampering test
    tampered_record = dict(record)
    tampered_record["action"] = "UNAUTHORIZED_ALTERATION"
    assert logger_after.verify_record(tampered_record) is False


def test_certin_audit_missing_key_fails_safely_in_production(monkeypatch):
    """
    Test 3: Proves that in production (allow_ephemeral_key=False), a missing key
    causes immediate safe failure (ValueError) rather than silently generating an ephemeral key.
    """
    monkeypatch.delenv("CERTIN_SIGNING_KEY_PATH", raising=False)
    monkeypatch.delenv("CERTIN_SIGNING_KEY_HEX", raising=False)

    with pytest.raises(ValueError, match="CERT-In Ed25519 private signing key is required"):
        CertInAuditLogger(allow_ephemeral_key=False)


def test_certin_audit_hex_environment_key_loading(monkeypatch):
    """
    Test 4: Proves loading 64-character hex string key from environment variable.
    """
    priv = ed25519.Ed25519PrivateKey.generate()
    hex_key = priv.private_bytes_raw().hex()
    monkeypatch.setenv("CERTIN_SIGNING_KEY_HEX", hex_key)

    logger = CertInAuditLogger()
    assert logger.public_key_hex == priv.public_key().public_bytes_raw().hex()
