"""
Automated Contract Validation Tests for IBVAP.
Tests Pydantic v2 data models, CoT XML generation, and Merkle leaf verification.
"""

from datetime import datetime, timezone
from uuid import uuid4
import pytest
from pydantic import ValidationError

from ibvap_core_types import (
    BoundingBox,
    DetectionBatch,
    GeoCentroid,
    GeoPoint,
    PolygonCoordinate,
    SensorConfig,
    TacticalAlert,
    TargetType,
    ThreatLevel,
    VectorEmbeddingPayload,
    compute_merkle_leaf_hash,
)
from ibvap_core_types.cot import CoTEvent


def test_sensor_config_valid():
    sensor = SensorConfig(
        name="CAM-NORTH-SECTOR-01",
        rtsp_url="rtsp://10.0.0.100:554/live",
        gps=GeoPoint(latitude=34.0522, longitude=74.8856, altitude_m=1620.0),
        bop_sector_id="BOP-ALPHA-01",
        active_polygon_coordinates=[
            PolygonCoordinate(x=0.1, y=0.1),
            PolygonCoordinate(x=0.9, y=0.1),
            PolygonCoordinate(x=0.9, y=0.9),
        ]
    )
    assert sensor.bop_sector_id == "BOP-ALPHA-01"
    assert len(sensor.active_polygon_coordinates) == 3


def test_sensor_config_invalid_rtsp():
    with pytest.raises(ValidationError):
        SensorConfig(
            name="INVALID-CAM",
            rtsp_url="ftp://invalid-url",
            gps=GeoPoint(latitude=34.0, longitude=74.0),
            bop_sector_id="BOP-ALPHA-01",
            active_polygon_coordinates=[
                PolygonCoordinate(x=0.1, y=0.1),
                PolygonCoordinate(x=0.9, y=0.1),
                PolygonCoordinate(x=0.9, y=0.9),
            ]
        )


def test_bounding_box_geometry_validation():
    # Valid box
    bbox = BoundingBox(x1=0.1, y1=0.2, x2=0.5, y2=0.8, confidence=0.95, class_id=0, track_id=42)
    assert bbox.width == pytest.approx(0.4)
    assert bbox.height == pytest.approx(0.6)
    assert bbox.center == pytest.approx((0.3, 0.5))
    assert bbox.bottom_center == pytest.approx((0.3, 0.8))

    # Invalid box (x2 < x1)
    with pytest.raises(ValidationError):
        BoundingBox(x1=0.8, y1=0.2, x2=0.2, y2=0.8, confidence=0.95, class_id=0)


def test_tactical_alert_factory_and_merkle_hash():
    sensor_id = uuid4()
    alert_id = uuid4()
    ts = datetime.now(timezone.utc)

    alert = TacticalAlert.create(
        alert_id=alert_id,
        timestamp=ts,
        bop_id="BOP-ALPHA-01",
        sensor_id=sensor_id,
        target_type=TargetType.PERSON,
        threat_level=ThreatLevel.HIGH,
        centroid=GeoCentroid(latitude=34.0528, longitude=74.8862, altitude_m=1622.0),
        evidence_cid="bafybeiczsscdsbs7ffqz55asqdf32gvwlsdp4s8gshd",
        confidence=0.96
    )

    # Validate CoT XML generation
    assert "IBVAP-" in alert.cot_xml_string
    assert "a-h-G-U-C-I" in alert.cot_xml_string
    assert 'lat="34.052800"' in alert.cot_xml_string

    # Validate Merkle leaf hash computation
    expected_hash = compute_merkle_leaf_hash(
        alert_id=alert_id,
        sensor_id=sensor_id,
        timestamp=ts,
        target_type="PERSON",
        threat_level="HIGH",
        evidence_cid="bafybeiczsscdsbs7ffqz55asqdf32gvwlsdp4s8gshd"
    )
    assert alert.merkle_leaf_hash == expected_hash
    assert len(alert.merkle_leaf_hash) == 64


def test_vector_embedding_512d_validation():
    # Valid 512-dim vector
    valid_vec = [0.05] * 512
    payload = VectorEmbeddingPayload(track_id=1, embedding_512d=valid_vec, watchlist_match_score=0.88)
    assert len(payload.embedding_512d) == 512
    assert payload.watchlist_match_score == 0.88

    # Invalid dimension (e.g. 511 elements)
    with pytest.raises(ValidationError):
        VectorEmbeddingPayload(track_id=1, embedding_512d=[0.05] * 511)
