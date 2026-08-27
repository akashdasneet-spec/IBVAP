"""
Unit Tests for LowLightEnhancer with Zero-DCE++ and Dynamic Luminance Bypass.
"""

import pytest
import numpy as np

from inference.enhancer import LowLightEnhancer, EnhancementResult


def test_enhancer_dynamic_bypass_high_light():
    """Verifies that bright/daylight frames (mean luminance > 0.45) bypass enhancement."""
    enhancer = LowLightEnhancer(luminance_threshold=0.45)
    
    # Create bright frame (value ~180/255 = 0.70 > 0.45)
    bright_frame = np.full((480, 640, 3), 180, dtype=np.uint8)
    
    result = enhancer.enhance(bright_frame)
    assert result.bypassed is True
    assert result.mean_luminance > 0.45
    assert result.latency_ms < 5.0  # Bypass must be sub-millisecond
    np.testing.assert_array_equal(result.frame, bright_frame)


def test_enhancer_curve_application_low_light():
    """Verifies that dark frames (mean luminance <= 0.45) undergo Zero-DCE++ curve enhancement."""
    enhancer = LowLightEnhancer(luminance_threshold=0.45, iterations=8)
    
    # Create dark night frame (value ~40/255 = 0.15 <= 0.45)
    dark_frame = np.full((480, 640, 3), 40, dtype=np.uint8)
    
    result = enhancer.enhance(dark_frame)
    assert result.bypassed is False
    assert result.mean_luminance <= 0.45
    assert result.latency_ms < 15.0  # Must execute in <15ms
    
    # Enhanced frame mean brightness should be strictly greater than input
    orig_mean = np.mean(dark_frame)
    enh_mean = np.mean(result.frame)
    assert enh_mean > orig_mean * 1.5
