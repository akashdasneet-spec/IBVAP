"""
Canonical Data Contracts for Intelligent Border Video Analytics Platform (IBVAP).
"""

from .alert import (
    GeoCentroid,
    TacticalAlert,
    TargetType,
    ThreatLevel,
    compute_merkle_leaf_hash,
)
from .cot import CoTEvent
from .detection import BoundingBox, DetectionBatch
from .embedding import VectorEmbeddingPayload
from .sensor import GeoPoint, PolygonCoordinate, SensorConfig

__all__ = [
    "GeoPoint",
    "PolygonCoordinate",
    "SensorConfig",
    "BoundingBox",
    "DetectionBatch",
    "ThreatLevel",
    "TargetType",
    "GeoCentroid",
    "TacticalAlert",
    "compute_merkle_leaf_hash",
    "VectorEmbeddingPayload",
    "CoTEvent",
]
