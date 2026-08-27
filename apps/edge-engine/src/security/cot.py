"""
Cursor-on-Target (CoT) XML Generator and MIL-STD-2525 Symbology Translator for C4ISR.
Produces NATO / DOD compliant CoT events for ATAK, WinTAK, and tactical mesh networks.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from xml.sax.saxutils import escape

try:
    import defusedxml.ElementTree as DefusedET
    from defusedxml.common import DefusedXmlException, DTDForbidden, EntitiesForbidden
except ImportError:
    import xml.etree.ElementTree as DefusedET
    DefusedXmlException = Exception  # type: ignore
    DTDForbidden = Exception         # type: ignore
    EntitiesForbidden = Exception   # type: ignore

from ibvap_core_types import (
    GeoCentroid,
    GeoPoint,
    SensorConfig,
    TacticalAlert,
    TargetType,
    ThreatLevel,
)

# MIL-STD-2525 / CoT 2525C Type Mappings
MIL_STD_2525_MAP: Dict[TargetType, str] = {
    TargetType.PERSON: "a-h-G-U-C-I",      # Hostile Ground Combatant (Infantry)
    TargetType.VEHICLE: "a-u-G-E-V",     # Unknown Ground Vehicle (Border Transport)
    TargetType.DRONE: "a-h-A-M-F-Q",     # Hostile Air Drone / UAV
    TargetType.WEAPON: "a-h-G-I-U-W",    # Hostile Ground Equipment (Weapon/Launcher)
    TargetType.UNKNOWN: "a-u-G",         # Unknown Ground Track
}

# Hostile Vehicle override if threat level is HIGH or CRITICAL
MIL_STD_HOSTILE_VEHICLE = "a-h-G-E-V"


class CoTGenerator:
    """
    MIL-STD / NATO Compliant Cursor-on-Target XML Generator.
    
    Translates IBVAP edge detections and tactical alerts into MIL-STD-2525 Cursor-on-Target schema
    with precision point telemetry, contact callsigns, and tactical metadata detail tags.
    """

    def __init__(self, stale_duration_sec: int = 300):
        self.stale_duration_sec = stale_duration_sec

    def get_cot_type(self, target_type: TargetType, threat_level: ThreatLevel = ThreatLevel.MEDIUM) -> str:
        """Translates target classification and threat severity into MIL-STD-2525 CoT type code."""
        if target_type == TargetType.VEHICLE and threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            return MIL_STD_HOSTILE_VEHICLE
        return MIL_STD_2525_MAP.get(target_type, "a-u-G")

    def generate_xml(
        self,
        alert_id: str,
        bop_id: str,
        sensor_id: str,
        target_type: TargetType,
        threat_level: ThreatLevel,
        centroid: GeoCentroid,
        confidence: float = 0.95,
        remarks: Optional[str] = None,
        event_time: Optional[datetime] = None,
        stale_sec: Optional[int] = None,
        callsign: Optional[str] = None
    ) -> str:
        """
        Generates canonical MIL-STD Cursor-on-Target XML payload.
        """
        now = event_time or datetime.now(timezone.utc)
        start_time = now
        stale_time = now + timedelta(seconds=stale_sec or self.stale_duration_sec)

        time_str = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        stale_str = stale_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        cot_type = self.get_cot_type(target_type, threat_level)
        uid = f"IBVAP-ALERT-{alert_id}"
        cs = callsign or f"{bop_id}-{target_type.value}"
        rmk = remarks or f"Automated detection by sensor {sensor_id} at {bop_id}."

        xml_output = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<event version="2.0" uid="{escape(uid)}" type="{escape(cot_type)}" how="m-g" '
            f'time="{time_str}" start="{start_str}" stale="{stale_str}">\n'
            f'  <point lat="{centroid.latitude:.6f}" lon="{centroid.longitude:.6f}" '
            f'hae="{centroid.altitude_m:.1f}" ce="10.0" le="5.0"/>\n'
            f'  <detail>\n'
            f'    <contact callsign="{escape(cs)}"/>\n'
            f'    <sensor id="{escape(str(sensor_id))}" bop="{escape(bop_id)}"/>\n'
            f'    <threat level="{escape(threat_level.value)}" confidence="{confidence:.2f}"/>\n'
            f'    <remarks>{escape(rmk)}</remarks>\n'
            f'  </detail>\n'
            f'</event>'
        )
        return xml_output

    def generate_from_alert(self, alert: TacticalAlert, sensor_config: Optional[SensorConfig] = None) -> str:
        """Generates CoT XML string directly from a TacticalAlert contract."""
        return self.generate_xml(
            alert_id=str(alert.alert_id),
            bop_id=alert.bop_id,
            sensor_id=str(alert.sensor_id),
            target_type=alert.target_type,
            threat_level=alert.threat_level,
            centroid=alert.centroid,
            confidence=alert.confidence,
            remarks=alert.description,
            event_time=alert.timestamp
        )

    def validate_and_parse(self, cot_xml: str) -> Dict[str, str]:
        """
        Parses and validates CoT XML securely using defusedxml, extracting key tactical telemetry.
        Protects against XML Entity Expansion (Billion Laughs), DTD entity retrieval, and external SSRF vectors.
        """
        root = DefusedET.fromstring(cot_xml, forbid_dtd=True, forbid_entities=True)
        if root.tag != "event":
            raise ValueError(f"Root tag must be 'event', found '{root.tag}'")

        point = root.find("point")
        if point is None:
            raise ValueError("CoT XML missing mandatory <point> tag")

        detail = root.find("detail")
        contact = detail.find("contact") if detail is not None else None
        sensor = detail.find("sensor") if detail is not None else None
        threat = detail.find("threat") if detail is not None else None
        remarks = detail.find("remarks") if detail is not None else None

        return {
            "uid": root.attrib.get("uid", ""),
            "type": root.attrib.get("type", ""),
            "how": root.attrib.get("how", ""),
            "time": root.attrib.get("time", ""),
            "lat": point.attrib.get("lat", "0.0"),
            "lon": point.attrib.get("lon", "0.0"),
            "hae": point.attrib.get("hae", "0.0"),
            "callsign": contact.attrib.get("callsign", "") if contact is not None else "",
            "sensor_id": sensor.attrib.get("id", "") if sensor is not None else "",
            "bop_id": sensor.attrib.get("bop", "") if sensor is not None else "",
            "threat_level": threat.attrib.get("level", "") if threat is not None else "",
            "confidence": threat.attrib.get("confidence", "0.0") if threat is not None else "0.0",
            "remarks": remarks.text if remarks is not None and remarks.text else ""
        }
