import hashlib
import json
import logging
import os
import secrets
import shutil
import struct
from typing import Dict, List, Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx

logger = logging.getLogger("edge_engine.vault")

MAGIC_HEADER = b"IBEV"  # IBVAP Evidence Vault Bundle Header
DEFAULT_MAX_CACHE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB
DEFAULT_MIN_FREE_BYTES = 1 * 1024 * 1024 * 1024    # 1 GB


class EvidenceVault:
    """
    Evidence Packaging, AES-256-GCM Encryption, and IPFS Kubo Publisher with Disk Quota Protection.
    """

    def __init__(
        self,
        master_key: Optional[bytes | str] = None,
        ipfs_api_url: str = "http://localhost:5001",
        cache_dir: Optional[str] = None,
        allow_ephemeral_key: bool = False,
        max_cache_bytes: Optional[int] = None,
        min_free_bytes: Optional[int] = None
    ):
        """
        Initializes the Evidence Vault.
        
        Args:
            master_key: Explicit 32-byte binary key or 64-char hex string.
            ipfs_api_url: Kubo RPC endpoint.
            cache_dir: Local disk cache directory.
            allow_ephemeral_key: STRICTLY for unit tests / development.
            max_cache_bytes: Maximum allowed byte size for the cache directory.
            min_free_bytes: Minimum free disk space threshold before triggering FIFO eviction.
        """
        self.master_key = self._resolve_master_key(master_key, allow_ephemeral_key=allow_ephemeral_key)
        self.ipfs_api_url = ipfs_api_url.rstrip("/")
        self.cache_dir = cache_dir or os.getenv("EVIDENCE_CACHE_DIR", "./evidence_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._aesgcm = AESGCM(self.master_key)

        # Quota limits
        env_max = os.getenv("EVIDENCE_CACHE_MAX_BYTES")
        self.max_cache_bytes = max_cache_bytes or (int(env_max) if env_max else DEFAULT_MAX_CACHE_BYTES)
        env_min_free = os.getenv("EVIDENCE_MIN_FREE_BYTES")
        self.min_free_bytes = min_free_bytes or (int(env_min_free) if env_min_free else DEFAULT_MIN_FREE_BYTES)

    @staticmethod
    def _resolve_master_key(
        key_input: Optional[bytes | str],
        allow_ephemeral_key: bool = False
    ) -> bytes:
        """
        Validates that the key represents exactly 32 bytes (256-bit AES).
        Fails fast if missing or invalid unless allow_ephemeral_key is explicitly True.
        """
        raw = key_input if key_input is not None else os.getenv("EVIDENCE_MASTER_KEY", "")

        if isinstance(raw, str):
            raw_str = raw.strip()
            # Hex-encoded 32-byte key (64 hex characters)
            if len(raw_str) == 64:
                try:
                    parsed_hex = bytes.fromhex(raw_str)
                    if len(parsed_hex) == 32:
                        return parsed_hex
                except ValueError:
                    pass
            # Raw string bytes
            raw_bytes = raw_str.encode("utf-8")
        elif isinstance(raw, (bytes, bytearray)):
            raw_bytes = bytes(raw)
        else:
            raw_bytes = b""

        if len(raw_bytes) == 32:
            return raw_bytes

        # Missing or invalid length
        if allow_ephemeral_key:
            logger.warning(
                "EVIDENCE_MASTER_KEY is missing or not 32 bytes. "
                "allow_ephemeral_key=True is enabled (TEST/DEV MODE ONLY). "
                "Generating ephemeral in-memory AES-256 key."
            )
            return secrets.token_bytes(32)

        raise ValueError(
            "EVIDENCE_MASTER_KEY is required for production evidence encryption and must be exactly 32 bytes (256 bits). "
            "Set EVIDENCE_MASTER_KEY as a 32-byte raw string or 64-hex character string, "
            "or pass a valid 32-byte key to master_key. Never use ephemeral keys in production."
        )

    @staticmethod
    def pack_bundle(
        frame_jpeg: bytes,
        video_mp4: bytes,
        metadata: Dict
    ) -> bytes:
        """
        Packs frame snapshot, video clip, and metadata JSON into canonical binary bundle:
        [MAGIC (4B)] + [MetaLen (4B)] + [MetaBytes] + [JPEGLen (4B)] + [JPEGBytes] + [MP4Len (4B)] + [MP4Bytes]
        """
        meta_bytes = json.dumps(metadata).encode("utf-8")
        
        packed = bytearray()
        packed.extend(MAGIC_HEADER)
        
        # Meta
        packed.extend(struct.pack(">I", len(meta_bytes)))
        packed.extend(meta_bytes)
        
        # Frame
        packed.extend(struct.pack(">I", len(frame_jpeg)))
        packed.extend(frame_jpeg)
        
        # Video
        packed.extend(struct.pack(">I", len(video_mp4)))
        packed.extend(video_mp4)
        
        return bytes(packed)

    @staticmethod
    def unpack_bundle(bundle_bytes: bytes) -> Tuple[bytes, bytes, Dict]:
        """
        Unpacks canonical binary bundle into (frame_jpeg, video_mp4, metadata).
        """
        if not bundle_bytes.startswith(MAGIC_HEADER):
            raise ValueError("Invalid evidence bundle magic header")
        
        offset = 4
        
        # Meta
        meta_len = struct.unpack(">I", bundle_bytes[offset:offset+4])[0]
        offset += 4
        meta_bytes = bundle_bytes[offset:offset+meta_len]
        offset += meta_len
        metadata = json.loads(meta_bytes.decode("utf-8"))
        
        # Frame
        frame_len = struct.unpack(">I", bundle_bytes[offset:offset+4])[0]
        offset += 4
        frame_jpeg = bundle_bytes[offset:offset+frame_len]
        offset += frame_len
        
        # Video
        video_len = struct.unpack(">I", bundle_bytes[offset:offset+4])[0]
        offset += 4
        video_mp4 = bundle_bytes[offset:offset+video_len]
        
        return frame_jpeg, video_mp4, metadata

    def encrypt(self, plaintext: bytes) -> bytes:
        """
        Encrypts plaintext with AES-256-GCM.
        Output format: [12-byte IV] + [Ciphertext + 16-byte Tag]
        """
        iv = secrets.token_bytes(12)  # 96-bit IV
        ciphertext = self._aesgcm.encrypt(iv, plaintext, None)
        return iv + ciphertext

    def decrypt(self, encrypted_payload: bytes) -> bytes:
        """
        Decrypts AES-256-GCM payload.
        """
        if len(encrypted_payload) < 28:  # 12-byte IV + 16-byte minimum tag
            raise ValueError("Payload too short for AES-GCM")
        
        iv = encrypted_payload[:12]
        ciphertext = encrypted_payload[12:]
        return self._aesgcm.decrypt(iv, ciphertext, None)

    def encrypt_payload(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        return self.encrypt(plaintext)

    def decrypt_payload(self, encrypted_payload: bytes, associated_data: Optional[bytes] = None) -> bytes:
        return self.decrypt(encrypted_payload)

    def publish_to_ipfs(self, encrypted_payload: bytes) -> str:
        """
        Publishes encrypted payload to local IPFS Kubo node via /api/v0/add RPC endpoint.
        Returns the IPFS Content Identifier (CID). Falls back to disk cache on timeout.
        """
        try:
            with httpx.Client(timeout=2.0) as client:
                files = {"file": ("evidence.bin", encrypted_payload, "application/octet-stream")}
                resp = client.post(f"{self.ipfs_api_url}/api/v0/add", files=files)
                if resp.status_code == 200:
                    data = resp.json()
                    cid = data.get("Hash")
                    if cid:
                        logger.info(f"Published encrypted evidence to IPFS: {cid}")
                        return cid
        except Exception as exc:
            logger.warning(f"IPFS daemon unreachable ({exc}). Storing in fallback disk cache.")

    def get_cache_size_bytes(self) -> int:
        """Returns total bytes of all cached .bin evidence bundles."""
        total = 0
        try:
            for entry in os.scandir(self.cache_dir):
                if entry.is_file() and entry.name.endswith(".bin"):
                    total += entry.stat().st_size
        except Exception as e:
            logger.debug(f"Error scanning cache dir: {e}")
        return total

    def enforce_cache_quota(self, incoming_bytes: int = 0) -> int:
        """
        Enforces maximum cache size and minimum free disk thresholds.
        Evicts oldest .bin files (FIFO by mtime) while protecting in-flight writes (.tmp).
        Returns number of evicted files.
        """
        evicted_count = 0

        # Check free disk space if available
        free_disk_bytes = float("inf")
        try:
            usage = shutil.disk_usage(self.cache_dir)
            free_disk_bytes = usage.free
        except Exception:
            pass

        current_size = self.get_cache_size_bytes()
        needs_size_eviction = (current_size + incoming_bytes) > self.max_cache_bytes
        needs_disk_eviction = (free_disk_bytes - incoming_bytes) < self.min_free_bytes

        if not (needs_size_eviction or needs_disk_eviction):
            return 0

        logger.warning(
            f"Evidence cache quota threshold reached (Cache: {current_size / (1024*1024):.1f}MB / "
            f"Limit: {self.max_cache_bytes / (1024*1024):.1f}MB). Initiating FIFO eviction of oldest bundles."
        )

        try:
            # Collect all eligible .bin files (excluding .tmp files)
            bin_files = []
            for entry in os.scandir(self.cache_dir):
                if entry.is_file() and entry.name.endswith(".bin"):
                    try:
                        stat = entry.stat()
                        bin_files.append((stat.st_mtime, stat.st_size, entry.path))
                    except Exception:
                        pass

            # Sort ascending by mtime (oldest first)
            bin_files.sort(key=lambda x: x[0])

            for _, fsize, fpath in bin_files:
                if (current_size + incoming_bytes) <= self.max_cache_bytes and (free_disk_bytes - incoming_bytes) >= self.min_free_bytes:
                    break

                try:
                    os.remove(fpath)
                    current_size -= fsize
                    free_disk_bytes += fsize
                    evicted_count += 1
                    logger.debug(f"Evicted oldest cached evidence bundle: {os.path.basename(fpath)}")
                except Exception as del_err:
                    logger.warning(f"Could not remove cached file '{fpath}': {del_err}")

        except Exception as scan_err:
            logger.error(f"Error during cache eviction scan: {scan_err}")

        return evicted_count

    def publish_to_ipfs(self, encrypted_payload: bytes) -> str:
        """
        Publishes encrypted payload to local IPFS Kubo node via /api/v0/add RPC endpoint.
        Returns the IPFS Content Identifier (CID). Falls back to disk cache on timeout.
        Ensures disk quota is enforced and writes are performed atomically.
        """
        try:
            with httpx.Client(timeout=2.0) as client:
                files = {"file": ("evidence.bin", encrypted_payload, "application/octet-stream")}
                resp = client.post(f"{self.ipfs_api_url}/api/v0/add", files=files)
                if resp.status_code == 200:
                    data = resp.json()
                    cid = data.get("Hash")
                    if cid:
                        logger.info(f"Published encrypted evidence to IPFS: {cid}")
                        return cid
        except Exception as exc:
            logger.warning(f"IPFS daemon unreachable ({exc}). Storing in fallback disk cache.")

        # Deterministic offline fallback CID based on payload hash
        payload_hash = hashlib.sha256(encrypted_payload).hexdigest()
        cid = f"bafybeic{payload_hash[:16]}offline"
        
        # Enforce quota before writing
        self.enforce_cache_quota(incoming_bytes=len(encrypted_payload))

        # Atomic write: write to unique .tmp file, sync, and atomically replace
        cache_file = os.path.join(self.cache_dir, f"{cid}.bin")
        tmp_file = os.path.join(self.cache_dir, f".tmp_{cid}_{secrets.token_hex(4)}.tmp")
        try:
            with open(tmp_file, "wb") as f:
                f.write(encrypted_payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, cache_file)
        except Exception as write_err:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            logger.error(f"Failed atomic write to evidence cache: {write_err}")
            raise
            
        return cid

    def package_encrypt_and_store(
        self,
        frame_jpeg: bytes,
        video_mp4: bytes,
        metadata: Dict
    ) -> Tuple[bytes, str]:
        """
        Convenience pipeline: Pack -> Encrypt -> Publish IPFS -> Return (EncryptedBytes, CID).
        """
        bundle = self.pack_bundle(frame_jpeg, video_mp4, metadata)
        encrypted = self.encrypt(bundle)
        cid = self.publish_to_ipfs(encrypted)
        return encrypted, cid
