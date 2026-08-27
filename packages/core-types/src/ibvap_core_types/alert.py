"""
Tactical Alert and Threat Assessment Contracts for IBVAP.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from .cot import CoTEvent
from .detection import BoundingBox
from .sensor import GeoPoint


class ThreatLevel(str, Enum):
    """Military / Border Security Threat Escalation Matrix."""
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TargetType(str, Enum):
    """Classified Target Types detected by Edge AI node."""
    PERSON = "PERSON"
    VEHICLE = "VEHICLE"
    DRONE = "DRONE"
    WEAPON = "WEAPON"
    UNKNOWN = "UNKNOWN"


class GeoCentroid(BaseModel):
    """Centroid of detected intrusion target in WGS-84 coordinate space."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Centroid latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Centroid longitude")
    altitude_m: float = Field(default=0.0, description="Centroid altitude in meters")

    def to_geopoint(self) -> GeoPoint:
        return GeoPoint(latitude=self.latitude, longitude=self.longitude, altitude_m=self.altitude_m)


def compute_merkle_leaf_hash(
    alert_id: UUID,
    sensor_id: UUID,
    timestamp: datetime,
    target_type: str,
    threat_level: str,
    evidence_cid: str
) -> str:
    """
    Computes a cryptographic SHA-256 Merkle leaf hash for non-repudiation
    and immutable chain-of-custody logging.
    """
    if timestamp.tzinfo is None:
        ts_utc = timestamp.replace(tzinfo=timezone.utc)
    else:
        ts_utc = timestamp.astimezone(timezone.utc)
    ts_iso = ts_utc.isoformat()
    raw_payload = f"{alert_id}:{sensor_id}:{ts_iso}:{target_type}:{threat_level}:{evidence_cid}".encode("utf-8")
    return hashlib.sha256(b"\x00" + raw_payload).hexdigest()


class TacticalAlert(BaseModel):
    """
    Tactical Alert Contract.
    Dispatched when edge analytics or central gateway flags an intrusion, zone breach, or classified target.
    """
    alert_id: UUID = Field(default_factory=uuid4, description="Unique Tactical Alert UUID")
    bop_id: str = Field(..., min_length=2, max_length=64, description="Border Outpost (BOP) Identifier")
    sensor_id: UUID = Field(..., description="Originating sensor UUID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Alert detection UTC timestamp")
    target_type: TargetType = Field(..., description="Classified Target Type")
    threat_level: ThreatLevel = Field(..., description="Assessed Threat Severity Level")
    centroid: GeoCentroid = Field(..., description="Ground/Aerial target centroid in WGS-84")
    cot_xml_string: str = Field(..., description="Cursor-on-Target XML representation for ATAK/TAK integration")
    evidence_cid: str = Field(..., min_length=10, description="IPFS Content Identifier (CID) for cryptographic evidence")
    merkle_leaf_hash: str = Field(..., min_length=64, max_length=64, description="SHA-256 Merkle leaf hash for tamper-evident audit log")
    bounding_box: Optional[BoundingBox] = Field(default=None, description="Optional bounding box metadata in camera frame")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="AI detection/classifier confidence score")
    description: Optional[str] = Field(default=None, description="Human readable tactical synopsis")

    @classmethod
    def create(
        cls,
        bop_id: str,
        sensor_id: UUID,
        target_type: TargetType,
        threat_level: ThreatLevel,
        centroid: GeoCentroid,
        evidence_cid: str,
        bounding_box: Optional[BoundingBox] = None,
        confidence: float = 0.9,
        description: Optional[str] = None,
        alert_id: Optional[UUID] = None,
        timestamp: Optional[datetime] = None,
    ) -> "TacticalAlert":
        """Factory method that automatically constructs CoT XML and Merkle Leaf Hash."""
        _id = alert_id or uuid4()
        _ts = timestamp or datetime.now(timezone.utc)

        # Build CoT Event
        cot_type_map = {
            TargetType.PERSON: "a-h-G-U-C-I",      # Hostile Ground Combatant
            TargetType.VEHICLE: "a-h-G-E-V",     # Hostile Ground Vehicle
            TargetType.DRONE: "a-h-A-M-F-Q",     # Hostile Air Drone / UAV
            TargetType.WEAPON: "a-h-G-I-U-W",    # Hostile Weapon / Equipment
            TargetType.UNKNOWN: "a-u-G",         # Unknown Ground
        }
        cot_type = cot_type_map.get(target_type, "a-u-G")
        cot_event = CoTEvent(
            uid=f"IBVAP-{_id}",
            cot_type=cot_type,
            time=_ts,
            point=centroid.to_geopoint(),
            callsign=f"{bop_id}-{target_type.value}",
            remarks=description or f"Intrusion detected at {bop_id} by sensor {sensor_id}",
            sensor_uid=str(sensor_id),
        )

        merkle_hash = compute_merkle_leaf_hash(
            alert_id=_id,
            sensor_id=sensor_id,
            timestamp=_ts,
            target_type=target_type.value,
            threat_level=threat_level.value,
            evidence_cid=evidence_cid
        )

        return cls(
            alert_id=_id,
            bop_id=bop_id,
            sensor_id=sensor_id,
            timestamp=_ts,
            target_type=target_type,
            threat_level=threat_level,
            centroid=centroid,
            cot_xml_string=cot_event.to_cot_xml(),
            evidence_cid=evidence_cid,
            merkle_leaf_hash=merkle_hash,
            bounding_box=bounding_box,
            confidence=confidence,
            description=description
        )
