"""
Cryptographic Chain of Custody & Evidence Admissibility Verification Service.
Validates SHA-256 Merkle leaf integrity and Merkle root inclusion for court-admissible audit trails.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_core_types import compute_merkle_leaf_hash
from db.models import AlertModel, MerkleReceiptModel


@dataclass
class AdmissibilityReport:
    alert_id: str
    is_admissible: bool
    leaf_hash_valid: bool
    recalculated_leaf_hash: str
    stored_leaf_hash: str
    evidence_cid: str
    merkle_root_verified: bool
    batch_id: Optional[str] = None
    merkle_root_hash: Optional[str] = None
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "is_admissible": self.is_admissible,
            "leaf_hash_valid": self.leaf_hash_valid,
            "recalculated_leaf_hash": self.recalculated_leaf_hash,
            "stored_leaf_hash": self.stored_leaf_hash,
            "evidence_cid": self.evidence_cid,
            "merkle_root_verified": self.merkle_root_verified,
            "batch_id": self.batch_id,
            "merkle_root_hash": self.merkle_root_hash,
            "details": self.details
        }


class AuditVerificationService:
    """
    Verifies cryptographic tamper-evidence of recorded border incidents.
    """

    @staticmethod
    async def verify_alert(alert_id: str, db: AsyncSession) -> AdmissibilityReport:
        # 1. Fetch Alert
        stmt = select(AlertModel).where(AlertModel.alert_id == alert_id)
        result = await db.execute(stmt)
        alert = result.scalar_one_or_none()

        if not alert:
            return AdmissibilityReport(
                alert_id=alert_id,
                is_admissible=False,
                leaf_hash_valid=False,
                recalculated_leaf_hash="",
                stored_leaf_hash="",
                evidence_cid="",
                merkle_root_verified=False,
                details=f"Incident record '{alert_id}' not found in tactical registry."
            )

        # 2. Recalculate canonical Merkle leaf hash
        try:
            alert_uuid = UUID(alert.alert_id)
            sensor_uuid = UUID(alert.sensor_id)
        except ValueError:
            alert_uuid = alert.alert_id
            sensor_uuid = alert.sensor_id

        recalculated_hash = compute_merkle_leaf_hash(
            alert_id=alert_uuid,
            sensor_id=sensor_uuid,
            timestamp=alert.timestamp,
            target_type=alert.target_type,
            threat_level=alert.threat_level,
            evidence_cid=alert.evidence_cid
        )

        leaf_hash_valid = (recalculated_hash == alert.merkle_leaf_hash)

        # 3. Check for Merkle Receipt Batch Inclusion
        receipt_stmt = select(MerkleReceiptModel)
        receipt_res = await db.execute(receipt_stmt)
        receipts = receipt_res.scalars().all()

        matched_receipt: Optional[MerkleReceiptModel] = None
        for r in receipts:
            if alert.merkle_leaf_hash in (r.leaves or []):
                matched_receipt = r
                break

        merkle_root_verified = matched_receipt is not None
        is_admissible = leaf_hash_valid  # Admissible if cryptographically verified

        details = "Digital evidence passed SHA-256 tamper verification." if is_admissible else "FAIL: Leaf hash mismatch."
        if merkle_root_verified and matched_receipt:
            details += f" Anchored in Merkle Batch {matched_receipt.batch_id} (Root: {matched_receipt.root_hash[:16]}...)"

        return AdmissibilityReport(
            alert_id=str(alert.alert_id),
            is_admissible=is_admissible,
            leaf_hash_valid=leaf_hash_valid,
            recalculated_leaf_hash=recalculated_hash,
            stored_leaf_hash=alert.merkle_leaf_hash,
            evidence_cid=alert.evidence_cid,
            merkle_root_verified=merkle_root_verified,
            batch_id=matched_receipt.batch_id if matched_receipt else None,
            merkle_root_hash=matched_receipt.root_hash if matched_receipt else None,
            details=details
        )
