from datetime import datetime, timezone
from typing import Annotated, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class VectorEmbeddingPayload(BaseModel):
    """
    Vector Embedding Payload for Cross-Camera Re-Identification (ReID) and Watchlist Matching.
    Standardized to 512-dimensional L2-normalized float vectors.
    """
    track_id: int = Field(..., ge=0, description="Local track identifier on edge node")
    embedding_512d: Annotated[
        List[float],
        Field(min_length=512, max_length=512, description="512-dimensional normalized feature embedding vector")
    ]
    watchlist_match_score: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = Field(
        default=None,
        description="Cosine similarity score against active border watchlist [0.0, 1.0]"
    )
    sensor_id: Optional[UUID] = Field(default=None, description="Sensor UUID where embedding was extracted")
    matched_poi_id: Optional[str] = Field(default=None, description="Identifier of matched Person of Interest if triggered")
    model_name: str = Field(default="osnet_ain_x1_0_512d", description="ReID feature extractor backbone")
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of feature extraction")

    @field_validator("embedding_512d")
    @classmethod
    def validate_finite_numbers(cls, v: List[float]) -> List[float]:
        for idx, val in enumerate(v):
            if val is None or val != val:  # Check for NaN
                raise ValueError(f"Embedding contains invalid NaN at dimension {idx}")
        return v
