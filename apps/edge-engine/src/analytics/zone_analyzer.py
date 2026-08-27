"""
Spatial Analytics and Restricted Polygon Zone Intrusion Analyzer.
"""

from typing import List, Optional, Tuple
from shapely.geometry import Point, Polygon

from ibvap_core_types import (
    BoundingBox,
    GeoCentroid,
    PolygonCoordinate,
    SensorConfig,
    TargetType,
    ThreatLevel,
)


class ZoneAnalyzer:
    """
    Evaluates real-time bounding box targets against defined BOP exclusion polygons.
    """

    def __init__(self, sensor_config: SensorConfig):
        self.sensor_config = sensor_config
        self.polygon = self._build_polygon(sensor_config.active_polygon_coordinates)

    def _build_polygon(self, coords: List[PolygonCoordinate]) -> Optional[Polygon]:
        if len(coords) < 3:
            # Fallback to default perimeter if not configured
            return Polygon([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])
        return Polygon([(c.x, c.y) for c in coords])

    def check_intrusion(self, bbox: BoundingBox) -> Tuple[bool, ThreatLevel, GeoCentroid]:
        """
        Determines if target bottom-center (footprint) is inside the restricted polygon.
        Calculates threat level and ground/sensor centroid.
        """
        bx, by = bbox.bottom_center
        target_point = Point(bx, by)

        is_inside = bool(self.polygon and self.polygon.contains(target_point))

        # Project coordinate to GPS space
        lat = self.sensor_config.gps.latitude + (by - 0.5) * 0.001
        lon = self.sensor_config.gps.longitude + (bx - 0.5) * 0.001
        centroid = GeoCentroid(
            latitude=lat,
            longitude=lon,
            altitude_m=self.sensor_config.gps.altitude_m
        )

        if not is_inside:
            return False, ThreatLevel.INFO, centroid

        # Intrusion Threat Assessment Logic
        if bbox.label in ["weapon", "drone"]:
            threat = ThreatLevel.CRITICAL
        elif bbox.label == "person" or bbox.class_id == 0:
            threat = ThreatLevel.HIGH
        elif bbox.label == "vehicle":
            threat = ThreatLevel.MEDIUM
        else:
            threat = ThreatLevel.LOW

        return True, threat, centroid
