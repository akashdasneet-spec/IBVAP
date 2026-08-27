"""
SQLAlchemy 2.0 Async Models for IBVAP Central Gateway.
Compatible with SQLite (local development) and PostgreSQL (production).
"""

from datetime import datetime, timezone
import json
from typing import List, Optional
from uuid import uuid4
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import JSON, TypeDecorator


class Base(DeclarativeBase):
    pass


class SensorModel(Base):
    """Registered Border Sensors and Camera nodes."""
    __tablename__ = "sensors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(100), nullable=False)
    rtsp_url = Column(String(512), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude_m = Column(Float, default=0.0)
    bop_sector_id = Column(String(64), nullable=False, index=True)
    active_polygon = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, default=True)
    fps_limit = Column(Integer, default=30)
    stream_width = Column(Integer, default=1920)
    stream_height = Column(Integer, default=1080)
    ptz_capable = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    alerts = relationship("AlertModel", back_populates="sensor", cascade="all, delete-orphan")


class AlertModel(Base):
    """Tactical Alerts and Intrusion Records."""
    __tablename__ = "tactical_alerts"
    __table_args__ = (
        Index("idx_alerts_bop_timestamp", "bop_id", "timestamp"),
        Index("idx_alerts_threat_timestamp", "threat_level", "timestamp"),
        Index("idx_alerts_sensor_timestamp", "sensor_id", "timestamp"),
    )

    alert_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    bop_id = Column(String(64), nullable=False, index=True)
    sensor_id = Column(String(36), ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    target_type = Column(String(32), nullable=False)
    threat_level = Column(String(32), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude_m = Column(Float, default=0.0)
    cot_xml_string = Column(Text, nullable=False)
    evidence_cid = Column(String(128), nullable=False)
    merkle_leaf_hash = Column(String(64), nullable=False, unique=True, index=True)
    bounding_box = Column(JSON, nullable=True)
    confidence = Column(Float, default=0.9)
    description = Column(Text, nullable=True)

    sensor = relationship("SensorModel", back_populates="alerts")


class MerkleReceiptModel(Base):
    """Immutable Merkle Tree Batch Receipts for Admissibility Verification."""
    __tablename__ = "merkle_receipts"

    batch_id = Column(String(64), primary_key=True)
    root_hash = Column(String(64), nullable=False, index=True)
    leaf_count = Column(Integer, nullable=False)
    leaves = Column(JSON, nullable=False, default=list)
    timestamp_start = Column(DateTime(timezone=True), nullable=False)
    timestamp_end = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WatchlistFaceModel(Base):
    """Persons of Interest (POI) and Watchlist 512-d Face Vector Embeddings."""
    __tablename__ = "watchlist_faces"

    poi_id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    threat_category = Column(String(64), nullable=False)
    embedding_512d = Column(JSON, nullable=False)  # List of 512 normalized floats
    photo_cid = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
