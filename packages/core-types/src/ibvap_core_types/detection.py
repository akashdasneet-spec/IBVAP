from datetime import datetime, timezone
from typing import Annotated, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    """
    Normalized 2D Bounding Box with tracking and classification metadata.
    Coordinates are normalized to [0.0, 1.0] relative to frame dimensions.
    """
    x1: Annotated[float, Field(ge=0.0, le=1.0, description="Top-left X coordinate normalized [0.0, 1.0]")]
    y1: Annotated[float, Field(ge=0.0, le=1.0, description="Top-left Y coordinate normalized [0.0, 1.0]")]
    x2: Annotated[float, Field(ge=0.0, le=1.0, description="Bottom-right X coordinate normalized [0.0, 1.0]")]
    y2: Annotated[float, Field(ge=0.0, le=1.0, description="Bottom-right Y coordinate normalized [0.0, 1.0]")]
    confidence: Annotated[float, Field(ge=0.0, le=1.0, description="Detection confidence score [0.0, 1.0]")]
    class_id: int = Field(..., ge=0, description="Target classification numeric identifier")
    track_id: Optional[int] = Field(default=None, description="Persistent ByteTrack / DeepSORT tracker identifier")
    label: Optional[str] = Field(default=None, description="Human readable class name (e.g. 'person', 'drone', 'vehicle')")

    @model_validator(mode="after")
    def validate_box_geometry(self) -> "BoundingBox":
        if self.x2 < self.x1:
            raise ValueError(f"Invalid bounding box: x2 ({self.x2}) must be >= x1 ({self.x1})")
        if self.y2 < self.y1:
            raise ValueError(f"Invalid bounding box: y2 ({self.y2}) must be >= y1 ({self.y1})")
        return self

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def bottom_center(self) -> tuple[float, float]:
        """Base coordinate in frame space (useful for ground plane homography)."""
        return ((self.x1 + self.x2) / 2.0, self.y2)


class DetectionBatch(BaseModel):
    """Batch of detections produced per video frame by Edge TensorRT Engine."""
    sensor_id: UUID = Field(..., description="Originating sensor UUID")
    frame_id: int = Field(..., ge=0, description="Sequential frame index")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of capture")
    detections: List[BoundingBox] = Field(default_factory=list, description="List of detected targets in frame")
    inference_latency_ms: float = Field(default=0.0, ge=0.0, description="TensorRT pipeline inference latency in ms")
