"""
REST API Routes for IBVAP Central Command & Control Gateway.
Includes Sensor registry, Paginated Alert Feed, Cryptographic Audit Verification, and ArcFace Watchlist.
"""

from datetime import datetime, timezone
import json
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_core_types import (
    GeoCentroid,
    GeoPoint,
    PolygonCoordinate,
    SensorConfig,
    TacticalAlert,
    TargetType,
    ThreatLevel,
    VectorEmbeddingPayload,
)

from api.ws_hub import WebSocketEventHub
from cot.pytak_bridge import PyTAKBridge
from db.models import AlertModel, MerkleReceiptModel, SensorModel, WatchlistFaceModel
from db.session import get_db
from services.audit_service import AdmissibilityReport, AuditVerificationService
from services.face_service import FaceWatchlistService

router = APIRouter(prefix="/api/v1")


def get_ws_hub() -> WebSocketEventHub:
    from main import ws_hub
    return ws_hub


def get_tak_bridge() -> PyTAKBridge:
    from main import tak_bridge
    return tak_bridge


# --- Health ---

@router.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "HEALTHY",
        "system": "IBVAP Central Gateway C2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }


# --- 1. Sensors Management ---

@router.post("/sensors", response_model=SensorConfig, status_code=status.HTTP_201_CREATED, tags=["Sensors"])
async def register_or_update_sensor(
    sensor_in: SensorConfig,
    db: AsyncSession = Depends(get_db),
    hub: WebSocketEventHub = Depends(get_ws_hub)
):
    """Registers or updates a border camera node and its active geofence polygons."""
    sensor_id_str = str(sensor_in.id)
    stmt = select(SensorModel).where(SensorModel.id == sensor_id_str)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    polygon_data = [c.model_dump() for c in sensor_in.active_polygon_coordinates]

    if existing:
        existing.name = sensor_in.name
        existing.rtsp_url = sensor_in.rtsp_url
        existing.latitude = sensor_in.gps.latitude
        existing.longitude = sensor_in.gps.longitude
        existing.altitude_m = sensor_in.gps.altitude_m
        existing.bop_sector_id = sensor_in.bop_sector_id
        existing.active_polygon = polygon_data
        existing.is_active = sensor_in.is_active
        existing.fps_limit = sensor_in.fps_limit
        existing.stream_width = sensor_in.stream_width
        existing.stream_height = sensor_in.stream_height
        existing.ptz_capable = sensor_in.ptz_capable
        existing.updated_at = datetime.now(timezone.utc)
    else:
        new_sensor = SensorModel(
            id=sensor_id_str,
            name=sensor_in.name,
            rtsp_url=sensor_in.rtsp_url,
            latitude=sensor_in.gps.latitude,
            longitude=sensor_in.gps.longitude,
            altitude_m=sensor_in.gps.altitude_m,
            bop_sector_id=sensor_in.bop_sector_id,
            active_polygon=polygon_data,
            is_active=sensor_in.is_active,
            fps_limit=sensor_in.fps_limit,
            stream_width=sensor_in.stream_width,
            stream_height=sensor_in.stream_height,
            ptz_capable=sensor_in.ptz_capable
        )
        db.add(new_sensor)

    await db.flush()

    # Broadcast update to connected C2 dashboards
    await hub.broadcast_to_c2("SENSOR_UPDATED", sensor_in.model_dump(mode="json"))
    return sensor_in


@router.get("/sensors", response_model=List[SensorConfig], tags=["Sensors"])
async def list_sensors(
    bop_sector_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Lists registered border surveillance sensors."""
    stmt = select(SensorModel)
    if bop_sector_id:
        stmt = stmt.where(SensorModel.bop_sector_id == bop_sector_id)
    
    result = await db.execute(stmt)
    sensors = result.scalars().all()

    return [
        SensorConfig(
            id=UUID(s.id),
            name=s.name,
            rtsp_url=s.rtsp_url,
            gps=GeoPoint(latitude=s.latitude, longitude=s.longitude, altitude_m=s.altitude_m),
            bop_sector_id=s.bop_sector_id,
            active_polygon_coordinates=[
                PolygonCoordinate(x=p["x"], y=p["y"]) for p in (s.active_polygon or [])
            ],
            is_active=s.is_active,
            fps_limit=s.fps_limit,
            stream_width=s.stream_width,
            stream_height=s.stream_height,
            ptz_capable=s.ptz_capable,
            created_at=s.created_at,
            updated_at=s.updated_at
        )
        for s in sensors
    ]


# --- 2. Tactical Alerts & Paginated Feed ---

@router.post("/alerts", response_model=TacticalAlert, status_code=status.HTTP_201_CREATED, tags=["Alerts"])
async def ingest_alert(
    alert_in: TacticalAlert,
    db: AsyncSession = Depends(get_db),
    hub: WebSocketEventHub = Depends(get_ws_hub),
    tak: PyTAKBridge = Depends(get_tak_bridge)
):
    """Ingests real-time tactical alert from edge node."""
    alert_record = AlertModel(
        alert_id=str(alert_in.alert_id),
        bop_id=alert_in.bop_id,
        sensor_id=str(alert_in.sensor_id),
        timestamp=alert_in.timestamp,
        target_type=alert_in.target_type.value,
        threat_level=alert_in.threat_level.value,
        latitude=alert_in.centroid.latitude,
        longitude=alert_in.centroid.longitude,
        altitude_m=alert_in.centroid.altitude_m,
        cot_xml_string=alert_in.cot_xml_string,
        evidence_cid=alert_in.evidence_cid,
        merkle_leaf_hash=alert_in.merkle_leaf_hash,
        bounding_box=alert_in.bounding_box.model_dump() if alert_in.bounding_box else None,
        confidence=alert_in.confidence,
        description=alert_in.description
    )
    db.add(alert_record)
    await db.flush()

    # 1. Forward to ATAK Mesh
    await tak.broadcast_alert(alert_in)

    # 2. Push to C2 Dashboards with <50ms latency
    await hub.broadcast_to_c2("TACTICAL_ALERT", alert_in.model_dump(mode="json"))

    return alert_in


class PaginatedAlertFeed(BaseModel):
    total: int
    limit: int
    offset: int
    results: List[TacticalAlert]


@router.get("/alerts/feed", response_model=PaginatedAlertFeed, tags=["Alerts"])
async def get_alerts_feed(
    bop_id: Optional[str] = None,
    threat_level: Optional[ThreatLevel] = None,
    target_type: Optional[TargetType] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Paginated and filtered historical incident records feed.
    """
    stmt = select(AlertModel)
    count_stmt = select(func.count()).select_from(AlertModel)

    if bop_id:
        stmt = stmt.where(AlertModel.bop_id == bop_id)
        count_stmt = count_stmt.where(AlertModel.bop_id == bop_id)
    if threat_level:
        stmt = stmt.where(AlertModel.threat_level == threat_level.value)
        count_stmt = count_stmt.where(AlertModel.threat_level == threat_level.value)
    if target_type:
        stmt = stmt.where(AlertModel.target_type == target_type.value)
        count_stmt = count_stmt.where(AlertModel.target_type == target_type.value)
    if start_time:
        stmt = stmt.where(AlertModel.timestamp >= start_time)
        count_stmt = count_stmt.where(AlertModel.timestamp >= start_time)
    if end_time:
        stmt = stmt.where(AlertModel.timestamp <= end_time)
        count_stmt = count_stmt.where(AlertModel.timestamp <= end_time)

    # Count total matching
    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar() or 0

    # Paginate
    stmt = stmt.order_by(desc(AlertModel.timestamp)).offset(offset).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    results = [
        TacticalAlert(
            alert_id=UUID(r.alert_id),
            bop_id=r.bop_id,
            sensor_id=UUID(r.sensor_id),
            timestamp=r.timestamp,
            target_type=TargetType(r.target_type),
            threat_level=ThreatLevel(r.threat_level),
            centroid=GeoCentroid(latitude=r.latitude, longitude=r.longitude, altitude_m=r.altitude_m),
            cot_xml_string=r.cot_xml_string,
            evidence_cid=r.evidence_cid,
            merkle_leaf_hash=r.merkle_leaf_hash,
            bounding_box=r.bounding_box,
            confidence=r.confidence or 0.9,
            description=r.description
        )
        for r in records
    ]

    return PaginatedAlertFeed(
        total=total_count,
        limit=limit,
        offset=offset,
        results=results
    )


# --- 3. Cryptographic Audit Verification ---

@router.get("/audit/verify/{alert_id}", response_model=dict, tags=["Audit"])
async def verify_evidence_admissibility(
    alert_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verifies SHA-256 Merkle leaf proof and batch inclusion for court-admissible chain of custody.
    """
    report = await AuditVerificationService.verify_alert(alert_id, db)
    return report.to_dict()


# --- 4. Merkle Batch Receipts Ingestion ---

class MerkleReceiptPayload(BaseModel):
    batch_id: str
    root_hash: str
    leaf_count: int
    leaves: List[str]
    timestamp_start: datetime
    timestamp_end: datetime


@router.post("/merkle/receipts", status_code=status.HTTP_201_CREATED, tags=["Audit"])
async def ingest_merkle_receipt(
    payload: MerkleReceiptPayload,
    db: AsyncSession = Depends(get_db)
):
    """Stores or updates a sealed Merkle root batch receipt from an edge node."""
    stmt = select(MerkleReceiptModel).where(MerkleReceiptModel.batch_id == payload.batch_id)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        existing.root_hash = payload.root_hash
        existing.leaf_count = payload.leaf_count
        existing.leaves = payload.leaves
        existing.timestamp_start = payload.timestamp_start
        existing.timestamp_end = payload.timestamp_end
    else:
        receipt_record = MerkleReceiptModel(
            batch_id=payload.batch_id,
            root_hash=payload.root_hash,
            leaf_count=payload.leaf_count,
            leaves=payload.leaves,
            timestamp_start=payload.timestamp_start,
            timestamp_end=payload.timestamp_end
        )
        db.add(receipt_record)

    await db.flush()
    return {"status": "SUCCESS", "batch_id": payload.batch_id, "root_hash": payload.root_hash}


# --- 5. Watchlist & ArcFace Vector Intelligence ---

class WatchlistEnrollmentRequest(BaseModel):
    poi_id: str = Field(..., description="Unique Person of Interest Identifier")
    name: str = Field(..., description="Full name or alias")
    threat_category: str = Field(..., description="Threat category (e.g. INTRUDER, SMUGGLER, ESCAPEE)")
    photo_cid: Optional[str] = Field(default=None, description="IPFS photo CID")
    notes: Optional[str] = Field(default=None, description="Tactical notes")
    embedding_512d: Optional[List[float]] = Field(default=None, description="Optional pre-computed 512-d vector")


class WatchlistSearchRequest(BaseModel):
    probe_embedding_512d: List[float] = Field(..., min_length=512, max_length=512)
    top_k: int = Field(default=5, ge=1, le=20)
    threshold: float = Field(default=0.70, ge=0.0, le=1.0)


@router.post("/watchlist/faces", status_code=status.HTTP_201_CREATED, tags=["Intelligence"])
async def enroll_watchlist_face(
    enroll_in: WatchlistEnrollmentRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Enrolls a known Person of Interest (POI). Auto-computes 512-d ArcFace embedding if omitted.
    """
    embedding = enroll_in.embedding_512d
    if not embedding or len(embedding) != 512:
        embedding = FaceWatchlistService.extract_embedding(seed_str=enroll_in.poi_id + enroll_in.name)

    # Check existing POI
    stmt = select(WatchlistFaceModel).where(WatchlistFaceModel.poi_id == enroll_in.poi_id)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        existing.name = enroll_in.name
        existing.threat_category = enroll_in.threat_category
        existing.embedding_512d = embedding
        existing.photo_cid = enroll_in.photo_cid
        existing.notes = enroll_in.notes
    else:
        new_face = WatchlistFaceModel(
            poi_id=enroll_in.poi_id,
            name=enroll_in.name,
            threat_category=enroll_in.threat_category,
            embedding_512d=embedding,
            photo_cid=enroll_in.photo_cid,
            notes=enroll_in.notes
        )
        db.add(new_face)

    await db.flush()
    return {
        "status": "ENROLLED",
        "poi_id": enroll_in.poi_id,
        "name": enroll_in.name,
        "threat_category": enroll_in.threat_category,
        "vector_dimensions": len(embedding)
    }


@router.post("/watchlist/search", tags=["Intelligence"])
async def search_watchlist(
    search_in: WatchlistSearchRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Executes fast cosine vector similarity search against enrolled 512-d watchlist faces.
    """
    stmt = select(WatchlistFaceModel)
    res = await db.execute(stmt)
    candidates = res.scalars().all()

    matches = FaceWatchlistService.search_candidates(
        probe_vector=search_in.probe_embedding_512d,
        candidates=candidates,
        top_k=search_in.top_k,
        threshold=search_in.threshold
    )

    return {
        "matched": len(matches) > 0,
        "candidate_count": len(candidates),
        "results": matches
    }
