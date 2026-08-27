"""
Cursor-on-Target (CoT) Schema and XML Serializer for TAK/ATAK interoperability.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.sax.saxutils import escape
from pydantic import BaseModel, Field

from .sensor import GeoPoint


class CoTEvent(BaseModel):
    """
    Cursor-on-Target (CoT) standardized event contract for tactical command feeds.
    Conforms to MIL-STD schema: event/point/detail.
    """
    uid: str = Field(..., description="Unique event identifier (e.g. 'IBVAP-ALERT-UUID')")
    cot_type: str = Field(
        default="a-h-G-U-C",
        description="MIL-STD-2525 CoT type string (e.g. 'a-u-G' for Unknown Ground, 'a-h-G' for Hostile Ground)"
    )
    how: str = Field(default="m-g", description="How event was generated ('m-g' machine-generated, 'm-r' machine-radar)")
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event creation time")
    start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event valid start time")
    stale: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=5),
        description="Event expiration time"
    )
    point: GeoPoint = Field(..., description="WGS-84 location coordinate")
    callsign: str = Field(..., description="Tactical callsign displayed in ATAK UI")
    remarks: Optional[str] = Field(default=None, description="Human readable tactical remarks")
    sensor_uid: Optional[str] = Field(default=None, description="Source sensor UID")

    def to_cot_xml(self) -> str:
        """Serializes the tactical event to canonical CoT XML string format."""
        time_str = self.time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        start_str = self.start.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        stale_str = self.stale.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        remarks_xml = f"<remarks>{escape(self.remarks)}</remarks>" if self.remarks else ""
        sensor_xml = f'<sensor uid="{escape(self.sensor_uid)}"/>' if self.sensor_uid else ""

        xml_payload = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<event version="2.0" uid="{escape(self.uid)}" type="{escape(self.cot_type)}" '
            f'how="{escape(self.how)}" time="{time_str}" start="{start_str}" stale="{stale_str}">\n'
            f'  <point lat="{self.point.latitude:.6f}" lon="{self.point.longitude:.6f}" '
            f'hae="{self.point.altitude_m:.1f}" ce="10.0" le="5.0"/>\n'
            f'  <detail>\n'
            f'    <contact callsign="{escape(self.callsign)}"/>\n'
            f'    {sensor_xml}\n'
            f'    {remarks_xml}\n'
            f'  </detail>\n'
            f'</event>'
        )
        return xml_payload
