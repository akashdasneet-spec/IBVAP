"""
Spatial Virtual Fencing and Multi-Zone Loitering Threat Analyzer.
Implements Point-in-Polygon (PIP) ray-casting, ground contact point calculation, and loitering escalation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID
from shapely.geometry import Point, Polygon

from ibvap_core_types import (
    BoundingBox,
    GeoCentroid,
    PolygonCoordinate,
    SensorConfig,
    TargetType,
    ThreatLevel,
)

logger = logging.getLogger("edge_engine.fence")


@dataclass
class ZoneViolation:
    zone_id: str
    zone_name: str
    violation_type: str  # "INTRUSION", "LOITERING", "ABANDONED_OBJECT"
    track_id: int
    target_type: TargetType
    threat_level: ThreatLevel
    dwell_time_sec: float
    ground_point: Tuple[float, float]  # Normalized (x, y)
    centroid: GeoCentroid
    bounding_box: BoundingBox
    description: str


@dataclass
class VirtualZone:
    zone_id: str
    name: str
    polygon_coords: List[PolygonCoordinate]
    loitering_threshold_sec: float = 5.0
    threat_level_intrusion: ThreatLevel = ThreatLevel.HIGH
    threat_level_loitering: ThreatLevel = ThreatLevel.CRITICAL
    allowed_classes: List[str] = field(default_factory=list)

    def __post_init__(self):
        if len(self.polygon_coords) < 3:
            # Fallback quadrilateral
            self._polygon = Polygon([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])
        else:
            self._polygon = Polygon([(c.x, c.y) for c in self.polygon_coords])

    def contains_point(self, x: float, y: float) -> bool:
        """Point-in-Polygon (PIP) ray-casting test."""
        return bool(self._polygon.contains(Point(x, y)))


@dataclass
class TrackZoneState:
    track_id: int
    zone_id: str
    first_detected_time: float
    last_detected_time: float
    alerted_intrusion: bool = False
    alerted_loitering: bool = False
    last_ground_point: Tuple[float, float] = (0.0, 0.0)

    @property
    def dwell_duration(self) -> float:
        return self.last_detected_time - self.first_detected_time


import threading

class SpatialVirtualFence:
    """
    Virtual Fencing & Perimeter Threat Analyzer.
    
    Key Features:
    - Calculates target ground contact footprint ((x1+x2)/2, y2) in camera coordinate space.
    - Shapely Point-in-Polygon (PIP) ray-casting.
    - Zone Dwell Time & Loitering Escalation (> threshold seconds).
    - Abandoned Object / Package Detection.
    - Ground Coordinate to WGS-84 GPS Projection.
    - Thread-safe TTL-based track state cleanup.
    """

    def __init__(
        self,
        sensor_config: SensorConfig,
        default_loiter_sec: float = 5.0,
        track_ttl_sec: float = 60.0
    ):
        self.sensor_config = sensor_config
        self.default_loiter_sec = default_loiter_sec
        self.track_ttl_sec = track_ttl_sec
        self.zones: Dict[str, VirtualZone] = {}
        self._track_states: Dict[Tuple[int, str], TrackZoneState] = {}
        self._lock = threading.Lock()

        self._init_zones_from_config()

    def _init_zones_from_config(self) -> None:
        """Initializes primary restricted zone from SensorConfig active polygon."""
        coords = self.sensor_config.active_polygon_coordinates
        primary_zone = VirtualZone(
            zone_id="ZONE-RESTRICTED-01",
            name=f"{self.sensor_config.bop_sector_id} RESTRICTED PERIMETER",
            polygon_coords=coords,
            loitering_threshold_sec=self.default_loiter_sec,
            threat_level_intrusion=ThreatLevel.HIGH,
            threat_level_loitering=ThreatLevel.CRITICAL
        )
        self.zones[primary_zone.zone_id] = primary_zone

    def add_custom_zone(self, zone: VirtualZone) -> None:
        """Adds a multi-vertex custom restricted zone."""
        self.zones[zone.zone_id] = zone

    def calculate_ground_contact(self, bbox: BoundingBox) -> Tuple[float, float]:
        """Calculates bottom-center contact point of bounding box ((x1+x2)/2, y2)."""
        return ((bbox.x1 + bbox.x2) / 2.0, bbox.y2)

    def project_to_gps(self, gx: float, gy: float) -> GeoCentroid:
        """Projects normalized camera coordinate to approximate WGS-84 GPS centroid."""
        lat = self.sensor_config.gps.latitude + (gy - 0.5) * 0.0012
        lon = self.sensor_config.gps.longitude + (gx - 0.5) * 0.0012
        return GeoCentroid(
            latitude=lat,
            longitude=lon,
            altitude_m=self.sensor_config.gps.altitude_m
        )

    def _map_target_type(self, bbox: BoundingBox) -> TargetType:
        label = (bbox.label or "").upper()
        if "PERSON" in label or bbox.class_id == 0:
            return TargetType.PERSON
        elif "VEHICLE" in label or bbox.class_id == 1:
            return TargetType.VEHICLE
        elif "WEAPON" in label or bbox.class_id == 2:
            return TargetType.WEAPON
        elif "PACKAGE" in label or bbox.class_id == 3:
            return TargetType.UNKNOWN
        return TargetType.UNKNOWN

    def evaluate_tracks(self, tracked_boxes: List[BoundingBox]) -> List[ZoneViolation]:
        """
        Evaluates active tracked bounding boxes against all defined virtual zones.
        Detects perimeter intrusions, loitering breaches, and stationary abandoned objects.
        """
        now = time.time()
        violations: List[ZoneViolation] = []
        active_track_zone_keys: Set[Tuple[int, str]] = set()

        with self._lock:
            for bbox in tracked_boxes:
                track_id = bbox.track_id or 0
                gx, gy = self.calculate_ground_contact(bbox)
                centroid = self.project_to_gps(gx, gy)
                target_type = self._map_target_type(bbox)

                for zone_id, zone in self.zones.items():
                    if zone.contains_point(gx, gy):
                        key = (track_id, zone_id)
                        active_track_zone_keys.add(key)

                        # Update or initiate dwell tracker state
                        if key not in self._track_states:
                            self._track_states[key] = TrackZoneState(
                                track_id=track_id,
                                zone_id=zone_id,
                                first_detected_time=now,
                                last_detected_time=now,
                                last_ground_point=(gx, gy)
                            )
                        else:
                            state = self._track_states[key]
                            state.last_detected_time = now
                            state.last_ground_point = (gx, gy)

                        state = self._track_states[key]
                        dwell_sec = state.dwell_duration

                        # 1. Intrusion Trigger (immediate upon entry)
                        if not state.alerted_intrusion:
                            state.alerted_intrusion = True
                            violations.append(
                                ZoneViolation(
                                    zone_id=zone_id,
                                    zone_name=zone.name,
                                    violation_type="INTRUSION",
                                    track_id=track_id,
                                    target_type=target_type,
                                    threat_level=zone.threat_level_intrusion,
                                    dwell_time_sec=0.0,
                                    ground_point=(gx, gy),
                                    centroid=centroid,
                                    bounding_box=bbox,
                                    description=f"Perimeter Intrusion: Target #{track_id} ({bbox.label}) breached {zone.name}."
                                )
                            )

                        # 2. Loitering Trigger (> threshold dwell duration)
                        if dwell_sec >= zone.loitering_threshold_sec and not state.alerted_loitering:
                            state.alerted_loitering = True
                            violations.append(
                                ZoneViolation(
                                    zone_id=zone_id,
                                    zone_name=zone.name,
                                    violation_type="LOITERING",
                                    track_id=track_id,
                                    target_type=target_type,
                                    threat_level=zone.threat_level_loitering,
                                    dwell_time_sec=dwell_sec,
                                    ground_point=(gx, gy),
                                    centroid=centroid,
                                    bounding_box=bbox,
                                    description=f"CRITICAL LOITERING: Target #{track_id} dwelling in {zone.name} for {dwell_sec:.1f}s (> {zone.loitering_threshold_sec}s)."
                                )
                            )

                        # 3. Abandoned Package Trigger
                        if bbox.label == "Abandoned Package" or bbox.class_id == 3:
                            if dwell_sec >= 2.0:
                                violations.append(
                                    ZoneViolation(
                                        zone_id=zone_id,
                                        zone_name=zone.name,
                                        violation_type="ABANDONED_OBJECT",
                                        track_id=track_id,
                                        target_type=TargetType.UNKNOWN,
                                        threat_level=ThreatLevel.CRITICAL,
                                        dwell_time_sec=dwell_sec,
                                        ground_point=(gx, gy),
                                        centroid=centroid,
                                        bounding_box=bbox,
                                        description=f"SUSPICIOUS OBJECT: Stationary package #{track_id} detected in {zone.name}."
                                    )
                                )

            # Safe TTL-based cleanup of inactive tracks (protects active tracks)
            self._cleanup_inactive_tracks_locked(now=now, active_keys=active_track_zone_keys)

        return violations

    def _cleanup_inactive_tracks_locked(self, now: float, active_keys: Set[Tuple[int, str]]) -> int:
        """Internal lock-guarded cleanup. Returns count of evicted tracks."""
        expired_keys = [
            k for k, state in self._track_states.items()
            if k not in active_keys and (now - state.last_detected_time > self.track_ttl_sec)
        ]
        for k in expired_keys:
            del self._track_states[k]
        return len(expired_keys)

    def cleanup_inactive_tracks(self, now: Optional[float] = None) -> int:
        """
        Thread-safe public cleanup method to evict inactive track states exceeding track_ttl_sec.
        Returns count of pruned track states.
        """
        current_time = now if now is not None else time.time()
        with self._lock:
            return self._cleanup_inactive_tracks_locked(now=current_time, active_keys=set())
