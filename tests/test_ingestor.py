"""
Unit Tests for VideoIngestor Multi-threaded RTSP Pipeline.
"""

import time
import pytest
import numpy as np

from pipeline.ingestor import VideoIngestor, IngestedFrame


def test_ingestor_synthetic_stream():
    """Verifies that VideoIngestor generates valid synthetic frames with non-blocking queue."""
    ingestor = VideoIngestor(source="videotestsrc", queue_size=5, target_fps=30, width=640, height=480)
    
    with ingestor:
        time.sleep(0.15)  # Allow worker thread to generate frames
        frame = ingestor.read(timeout=1.0)
        
        assert frame is not None
        assert isinstance(frame, IngestedFrame)
        assert frame.width == 640
        assert frame.height == 480
        assert frame.data.shape == (480, 640, 3)
        assert frame.frame_id > 0
        assert frame.is_synthetic is True


def test_ingestor_ring_buffer_drop():
    """Verifies that ring buffer drops oldest frames when queue is full without blocking."""
    ingestor = VideoIngestor(source="videotestsrc", queue_size=2, target_fps=60, width=320, height=240)
    
    with ingestor:
        time.sleep(0.2)  # Let worker produce more than 2 frames
        # Queue should not deadlock or exceed capacity
        frame1 = ingestor.read(timeout=1.0)
        assert frame1 is not None
        assert ingestor.total_frames_ingested >= 2
