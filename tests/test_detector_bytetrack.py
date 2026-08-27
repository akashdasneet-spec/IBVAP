"""
Unit Tests for YOLOv11 Target Detection and ByteTrack Association Engine.
"""

import pytest
import numpy as np

from ibvap_core_types import BoundingBox
from inference.detector import YOLOv11Detector, DetectorConfig
from inference.tracker import ByteTracker, STrack, TrackState


def test_bytetrack_association_and_id_continuity():
    """Verifies that ByteTrack maintains consistent track IDs across consecutive frames."""
    tracker = ByteTracker(high_threshold=0.5, low_threshold=0.1)

    # Frame 1: Detection at (0.3, 0.4, 0.4, 0.6)
    f1_detections = [
        BoundingBox(x1=0.30, y1=0.40, x2=0.40, y2=0.60, confidence=0.95, class_id=0, label="Person")
    ]
    tracked_f1 = tracker.update(f1_detections)
    assert len(tracked_f1) == 1
    t1_id = tracked_f1[0].track_id
    assert t1_id is not None

    # Frame 2: Smooth motion to (0.32, 0.41, 0.42, 0.61)
    f2_detections = [
        BoundingBox(x1=0.32, y1=0.41, x2=0.42, y2=0.61, confidence=0.92, class_id=0, label="Person")
    ]
    tracked_f2 = tracker.update(f2_detections)
    assert len(tracked_f2) == 1
    # Track ID must remain identical across frames
    assert tracked_f2[0].track_id == t1_id


def test_bytetrack_low_confidence_recovery():
    """Verifies that ByteTrack Stage 2 recovers occluded targets with low detection scores."""
    tracker = ByteTracker(high_threshold=0.5, low_threshold=0.15)

    # Frame 1: High confidence detection
    tracker.update([
        BoundingBox(x1=0.50, y1=0.50, x2=0.60, y2=0.70, confidence=0.90, class_id=0, label="Person")
    ])

    # Frame 2: High confidence detection to confirm track
    t_f2 = tracker.update([
        BoundingBox(x1=0.51, y1=0.50, x2=0.61, y2=0.70, confidence=0.88, class_id=0, label="Person")
    ])
    confirmed_id = t_f2[0].track_id

    # Frame 3: Target partially occluded by foliage -> low confidence (0.30 < 0.50)
    t_f3 = tracker.update([
        BoundingBox(x1=0.52, y1=0.51, x2=0.62, y2=0.71, confidence=0.30, class_id=0, label="Person")
    ])
    assert len(t_f3) == 1
    assert t_f3[0].track_id == confirmed_id


def test_yolov11_detector_end_to_end():
    """Verifies YOLOv11 detector outputs tracked boxes with latency metrics."""
    detector = YOLOv11Detector(DetectorConfig(conf_threshold=0.4, enable_tracking=True))
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    boxes, latency_ms = detector.detect_and_track(dummy_frame)
    assert isinstance(boxes, list)
    assert len(boxes) > 0
    assert boxes[0].track_id is not None
    assert latency_ms > 0.0
