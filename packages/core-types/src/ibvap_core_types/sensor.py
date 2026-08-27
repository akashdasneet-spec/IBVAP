"""
Sensor and Geospatial Data Contracts for IBVAP.
"""

from datetime import datetime, timezone
from typing import Annotated, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator


class GeoPoint(BaseModel):
    """WGS-84 Geospatial coordinate with altitude."""
    latitude: Annotated[float, Field(ge=-90.0, le=90.0, description="Latitude in decimal degrees")]
    longitude: Annotated[float, Field(ge=-180.0, le=180.0, description="Longitude in decimal degrees")]
    altitude_m: Annotated[float, Field(default=0.0, description="Altitude above sea level in meters")]

    model_config = {"frozen": True}


class PolygonCoordinate(BaseModel):
    """Normalized 2D camera coordinate and optional mapped ground geocoordinate."""
    x: Annotated[float, Field(ge=0.0, le=1.0, description="Normalized X coordinate in camera FOV [0.0, 1.0]")]
    y: Annotated[float, Field(ge=0.0, le=1.0, description="Normalized Y coordinate in camera FOV [0.0, 1.0]")]
    geo_point: Optional[GeoPoint] = Field(default=None, description="Optional projected ground WGS-84 coordinate")


class SensorConfig(BaseModel):
    """
    Sensor Configuration Contract.
    Defines edge ingestion parameters, spatial deployment details, and active tripwire/exclusion polygons.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique sensor identifier (UUIDv4)")
    name: str = Field(..., min_length=2, max_length=100, description="Operational designation (e.g. 'CAM-NORTH-TOWER-01')")
    rtsp_url: str = Field(..., description="Secure RTSP or RTSPS stream endpoint URI")
    gps: GeoPoint = Field(..., description="Sensor physical installation GPS coordinate")
    bop_sector_id: str = Field(..., min_length=2, max_length=64, description="Border Outpost Sector ID (e.g., 'BOP-SECTOR-BRAVO-02')")
    active_polygon_coordinates: List[PolygonCoordinate] = Field(
        default_factory=list,
        min_length=3,
        description="Vertices defining the restricted intrusion detection polygon in camera frame"
    )
    is_active: bool = Field(default=True, description="Indicates if edge node is actively processing the stream")
    fps_limit: int = Field(default=30, ge=1, le=120, description="Processing target frames per second")
    stream_width: int = Field(default=1920, ge=320, description="Video stream width resolution")
    stream_height: int = Field(default=1080, ge=240, description="Video stream height resolution")
    ptz_capable: bool = Field(default=False, description="Whether camera supports Pan-Tilt-Zoom remote actuation")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Record creation UTC timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Record update UTC timestamp")

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_scheme(cls, v: str) -> str:
        if not (v.startswith("rtsp://") or v.startswith("rtsps://") or v.startswith("http://") or v.startswith("https://") or v.startswith("file://") or v.startswith("videotestsrc")):
            raise ValueError("Stream URL must use rtsp://, rtsps://, http(s)://, file:// or videotestsrc scheme")
        return v
