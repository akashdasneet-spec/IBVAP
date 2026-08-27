"""
Automated Tests for Edge Spatial Zone Analysis and Polygon Intersection.
"""

from uuid import uuid4
import pytest

from ibvap_core_types import (
    BoundingBox,
    GeoPoint,
    PolygonCoordinate,
    SensorConfig,
    ThreatLevel,
)

# Import ZoneAnalyzer
import sys
sys.path.insert(0, "apps/edge-engine/src")
from analytics.zone_analyzer import ZoneAnalyzer


def test_zone_analyzer_intrusion_detection():
    sensor = SensorConfig(
        id=uuid4(),
        name="TEST-SENSOR-01",
        rtsp_url="videotestsrc",
        gps=GeoPoint(latitude=34.05, longitude=74.88, altitude_m=1600.0),
        bop_sector_id="BOP-TEST-01",
        active_polygon_coordinates=[
            PolygonCoordinate(x=0.2, y=0.2),
            PolygonCoordinate(x=0.8, y=0.2),
            PolygonCoordinate(x=0.8, y=0.8),
            PolygonCoordinate(x=0.2, y=0.8),
        ]
    )

    analyzer = ZoneAnalyzer(sensor)

    # 1. Target Inside Polygon (Center at 0.5, 0.5)
    inside_bbox = BoundingBox(x1=0.45, y1=0.4, x2=0.55, y2=0.6, confidence=0.92, class_id=0, label="person")
    is_in, threat, centroid = analyzer.check_intrusion(inside_bbox)
    assert is_in is True
    assert threat == ThreatLevel.HIGH
    assert centroid.latitude > 0

    # 2. Target Outside Polygon (Center at 0.05, 0.05)
    outside_bbox = BoundingBox(x1=0.01, y1=0.01, x2=0.09, y2=0.09, confidence=0.90, class_id=0, label="person")
    is_in_out, threat_out, _ = analyzer.check_intrusion(outside_bbox)
    assert is_in_out is False
    assert threat_out == ThreatLevel.INFO
