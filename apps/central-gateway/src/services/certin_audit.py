import os
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger("gateway.certin_audit")

AUDIT_LOG_FILE = Path(os.getenv("CERTIN_AUDIT_LOG_PATH", "audit_ledger_certin.jsonl"))


class CertInAuditLogger:
    """
    Append-only CERT-In security event logger with Ed25519 asymmetric signatures.
    Supports persistent private key loading via file path, hex string, or PEM bytes.
    """

    def __init__(
        self,
        private_key: Optional[ed25519.Ed25519PrivateKey] = None,
        key_path: Optional[Union[str, Path]] = None,
        allow_ephemeral_key: bool = False
    ):
        """
        Initializes the audit logger with a persistent Ed25519 signing key.
        
        Args:
            private_key: Explicit Ed25519PrivateKey instance.
            key_path: Filesystem path to private key (PEM or raw 32-byte binary).
            allow_ephemeral_key: If False (default), missing keys will raise ValueError.
                                 If True, generates an in-memory key (test mode only).
        """
        self._private_key = self._resolve_private_key(
            private_key=private_key,
            key_path=key_path,
            allow_ephemeral_key=allow_ephemeral_key
        )
        self._public_key = self._private_key.public_key()
        self._public_key_hex = self._public_key.public_bytes_raw().hex()

    @staticmethod
    def _resolve_private_key(
        private_key: Optional[ed25519.Ed25519PrivateKey] = None,
        key_path: Optional[Union[str, Path]] = None,
        allow_ephemeral_key: bool = False
    ) -> ed25519.Ed25519PrivateKey:
        # 1. Directly passed key instance
        if private_key is not None:
            return private_key

        # 2. Key path from argument or environment
        effective_path = key_path or os.getenv("CERTIN_SIGNING_KEY_PATH")
        if effective_path:
            path_obj = Path(effective_path)
            if path_obj.is_file():
                try:
                    # Check file permissions on POSIX (warn if group/world readable)
                    if hasattr(os, "stat") and os.name != "nt":
                        mode = path_obj.stat().st_mode
                        if mode & 0o077:
                            logger.warning(
                                f"Insecure file permissions on audit signing key '{effective_path}': "
                                f"mode is {oct(mode)}. Key should be restricted to 0600."
                            )

                    raw_data = path_obj.read_bytes()
                    # Try loading as PEM
                    try:
                        loaded = serialization.load_pem_private_key(raw_data, password=None)
                        if isinstance(loaded, ed25519.Ed25519PrivateKey):
                            return loaded
                    except Exception:
                        pass

                    # Try loading as raw 32 bytes or 64-hex string
                    if len(raw_data) == 32:
                        return ed25519.Ed25519PrivateKey.from_private_bytes(raw_data)
                    raw_str = raw_data.decode("utf-8").strip()
                    if len(raw_str) == 64:
                        return ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw_str))
                except Exception as e:
                    logger.error(f"Failed to read CERT-In signing key from '{effective_path}': {e}")
                    raise

        # 3. Hex string from environment
        hex_key = os.getenv("CERTIN_SIGNING_KEY_HEX", "").strip()
        if hex_key and len(hex_key) == 64:
            try:
                return ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hex_key))
            except Exception as e:
                logger.error(f"Failed to parse CERTIN_SIGNING_KEY_HEX: {e}")

        # 4. Ephemeral fallback check
        env_allow_ephemeral = os.getenv("IBVAP_ALLOW_EPHEMERAL_KEY", "").lower() in ("true", "1", "yes")
        if allow_ephemeral_key or env_allow_ephemeral:
            logger.warning(
                "No persistent CERT-In Ed25519 signing key found. "
                "allow_ephemeral_key=True is enabled (TEST/DEV MODE ONLY). "
                "Generating ephemeral in-memory signing key."
            )
            return ed25519.Ed25519PrivateKey.generate()

        raise ValueError(
            "CERT-In Ed25519 private signing key is required for production audit logging. "
            "Provision a key via CERTIN_SIGNING_KEY_PATH (file path) or CERTIN_SIGNING_KEY_HEX (64-character hex string), "
            "or explicitly pass allow_ephemeral_key=True for non-production testing."
        )

    @property
    def public_key_hex(self) -> str:
        return self._public_key_hex

    def log_operator_action(
        self,
        operator_id: str,
        action: str,
        resource_id: str,
        ip_address: str = "127.0.0.1",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Signs and writes an operator security event to the append-only log.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        event_id = str(uuid4())

        canonical_payload = {
            "event_id": event_id,
            "timestamp_utc": now_utc,
            "operator_id": operator_id,
            "action": action,
            "resource_id": resource_id,
            "ip_address": ip_address,
            "metadata": metadata or {}
        }

        # Sign canonical UTF-8 bytes
        msg_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
        signature = self._private_key.sign(msg_bytes).hex()

        record = {
            **canonical_payload,
            "signature_algorithm": "Ed25519",
            "public_key_hex": self._public_key_hex,
            "signature_hex": signature
        }

        try:
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to append to CERT-In audit log: {e}")

        return record

    @staticmethod
    def verify_record(record: Dict[str, Any]) -> bool:
        """
        Verifies the cryptographic integrity of a signed CERT-In audit entry.
        """
        try:
            pub_hex = record["public_key_hex"]
            sig_hex = record["signature_hex"]
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))

            payload = {
                "event_id": record["event_id"],
                "timestamp_utc": record["timestamp_utc"],
                "operator_id": record["operator_id"],
                "action": record["action"],
                "resource_id": record["resource_id"],
                "ip_address": record["ip_address"],
                "metadata": record.get("metadata", {})
            }

            msg_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
            pub_key.verify(bytes.fromhex(sig_hex), msg_bytes)
            return True
        except Exception:
            return False


# Global singleton instance (enforces persistent key in production, permits ephemeral key in dev/test)
_is_prod = os.getenv("IBVAP_ENV", "development").lower() == "production"
try:
    audit_logger = CertInAuditLogger(allow_ephemeral_key=not _is_prod)
except Exception as _err:
    logger.warning(f"Could not initialize global audit_logger: {_err}")
    audit_logger = None  # type: ignore
