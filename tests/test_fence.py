"""
Unit Tests for Spatial Virtual Fencing, Ground Footprint PIP, and Loitering Escalation.
"""

import time
from uuid import uuid4
import pytest

from ibvap_core_types import (
    BoundingBox,
    GeoPoint,
    PolygonCoordinate,
    SensorConfig,
    ThreatLevel,
)
from analytics.fence import SpatialVirtualFence, VirtualZone, ZoneViolation


@pytest.fixture
def test_sensor_config():
    return SensorConfig(
        id=uuid4(),
        name="CAM-SECTOR-01",
        rtsp_url="videotestsrc",
        gps=GeoPoint(latitude=34.0522, longitude=74.8856, altitude_m=1620.0),
        bop_sector_id="BOP-ALPHA-01",
        active_polygon_coordinates=[
            PolygonCoordinate(x=0.20, y=0.30),
            PolygonCoordinate(x=0.80, y=0.30),
            PolygonCoordinate(x=0.80, y=0.80),
            PolygonCoordinate(x=0.20, y=0.80),
        ]
    )


def test_ground_contact_point_calculation(test_sensor_config):
    fence = SpatialVirtualFence(test_sensor_config)
    
    # BBox from x1=0.3, y1=0.4 to x2=0.5, y2=0.7
    bbox = BoundingBox(x1=0.30, y1=0.40, x2=0.50, y2=0.70, confidence=0.9, class_id=0)
    gx, gy = fence.calculate_ground_contact(bbox)
    
    # Ground point must be bottom-center: ((0.3+0.5)/2, 0.7) = (0.4, 0.7)
    assert gx == pytest.approx(0.40)
    assert gy == pytest.approx(0.70)


def test_virtual_fence_immediate_intrusion_alert(test_sensor_config):
    fence = SpatialVirtualFence(test_sensor_config, default_loiter_sec=3.0)

    # Intruder ground contact at (0.40, 0.60) inside polygon [0.2..0.8, 0.3..0.8]
    intruder = BoundingBox(x1=0.35, y1=0.40, x2=0.45, y2=0.60, confidence=0.95, class_id=0, track_id=101, label="Person")

    violations = fence.evaluate_tracks([intruder])
    assert len(violations) == 1
    assert violations[0].violation_type == "INTRUSION"
    assert violations[0].threat_level == ThreatLevel.HIGH
    assert violations[0].track_id == 101


def test_virtual_fence_loitering_escalation(test_sensor_config):
    # Set short loitering threshold for testing (0.1 seconds)
    fence = SpatialVirtualFence(test_sensor_config, default_loiter_sec=0.1)

    intruder = BoundingBox(x1=0.35, y1=0.40, x2=0.45, y2=0.60, confidence=0.95, class_id=0, track_id=202, label="Person")

    # Step 1: Initial entry -> Intrusion alert
    v1 = fence.evaluate_tracks([intruder])
    assert len(v1) == 1
    assert v1[0].violation_type == "INTRUSION"

    # Step 2: Dwell inside zone beyond threshold
    time.sleep(0.15)
    v2 = fence.evaluate_tracks([intruder])
    assert len(v2) == 1
    assert v2[0].violation_type == "LOITERING"
    assert v2[0].threat_level == ThreatLevel.CRITICAL
    assert v2[0].dwell_time_sec >= 0.1


def test_virtual_fence_ttl_track_cleanup(test_sensor_config):
    """
    P1-1 Regression Test: Verifies that inactive tracks are pruned after track_ttl_sec
    while active tracks currently inside the zone are preserved.
    """
    fence = SpatialVirtualFence(test_sensor_config, track_ttl_sec=0.2)

    # 1. Active track inside zone (ID: 501)
    box1 = BoundingBox(x1=0.35, y1=0.40, x2=0.45, y2=0.60, confidence=0.9, class_id=0, track_id=501, label="Person")
    fence.evaluate_tracks([box1])
    assert len(fence._track_states) == 1

    # 2. Simulate time passing beyond TTL (0.25s) without track 501
    time.sleep(0.25)
    
    # 3. Process new frame with only track 502
    box2 = BoundingBox(x1=0.50, y1=0.40, x2=0.60, y2=0.60, confidence=0.9, class_id=0, track_id=502, label="Person")
    fence.evaluate_tracks([box2])

    # Track 501 must be pruned by TTL; track 502 must be active
    assert (501, "ZONE-RESTRICTED-01") not in fence._track_states
    assert (502, "ZONE-RESTRICTED-01") in fence._track_states
    assert len(fence._track_states) == 1
