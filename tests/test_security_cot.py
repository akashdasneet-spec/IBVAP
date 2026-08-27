"""
Unit Tests for MIL-STD / NATO Cursor-on-Target (CoT) XML Generator.
"""

from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import pytest

from ibvap_core_types import GeoCentroid, TacticalAlert, TargetType, ThreatLevel
from security.cot import CoTGenerator, MIL_STD_2525_MAP


def test_cot_symbol_mapping():
    generator = CoTGenerator()

    # Person / Intruder -> a-h-G-U-C-I
    assert generator.get_cot_type(TargetType.PERSON) == "a-h-G-U-C-I"
    # Vehicle Medium -> a-u-G-E-V (Unknown Ground Vehicle)
    assert generator.get_cot_type(TargetType.VEHICLE, ThreatLevel.MEDIUM) == "a-u-G-E-V"
    # Vehicle High Threat -> a-h-G-E-V (Hostile Ground Vehicle)
    assert generator.get_cot_type(TargetType.VEHICLE, ThreatLevel.HIGH) == "a-h-G-E-V"
    # Drone -> a-h-A-M-F-Q
    assert generator.get_cot_type(TargetType.DRONE) == "a-h-A-M-F-Q"
    # Weapon -> a-h-G-I-U-W
    assert generator.get_cot_type(TargetType.WEAPON) == "a-h-G-I-U-W"


def test_cot_xml_structure_and_validity():
    generator = CoTGenerator(stale_duration_sec=120)

    centroid = GeoCentroid(latitude=34.0528, longitude=74.8862, altitude_m=1622.0)
    xml_str = generator.generate_xml(
        alert_id="ALERT-TEST-001",
        bop_id="BOP-ALPHA-01",
        sensor_id="SENSOR-TOWER-04",
        target_type=TargetType.PERSON,
        threat_level=ThreatLevel.HIGH,
        centroid=centroid,
        confidence=0.96,
        remarks="Unauthorized movement near fence line."
    )

    # 1. Verify XML is well-formed
    root = ET.fromstring(xml_str)
    assert root.tag == "event"
    assert root.attrib["version"] == "2.0"
    assert root.attrib["uid"] == "IBVAP-ALERT-ALERT-TEST-001"
    assert root.attrib["type"] == "a-h-G-U-C-I"

    # 2. Check Point tag
    point = root.find("point")
    assert point is not None
    assert point.attrib["lat"] == "34.052800"
    assert point.attrib["lon"] == "74.886200"
    assert point.attrib["hae"] == "1622.0"

    # 3. Check Detail tags
    detail = root.find("detail")
    assert detail is not None
    
    contact = detail.find("contact")
    assert contact is not None
    assert contact.attrib["callsign"] == "BOP-ALPHA-01-PERSON"

    sensor = detail.find("sensor")
    assert sensor is not None
    assert sensor.attrib["id"] == "SENSOR-TOWER-04"
    assert sensor.attrib["bop"] == "BOP-ALPHA-01"

    threat = detail.find("threat")
    assert threat is not None
    assert threat.attrib["level"] == "HIGH"
    assert threat.attrib["confidence"] == "0.96"


def test_cot_parse_and_validate():
    generator = CoTGenerator()
    centroid = GeoCentroid(latitude=34.123456, longitude=74.654321, altitude_m=1500.0)

    xml_str = generator.generate_xml(
        alert_id="12345",
        bop_id="BOP-BRAVO-02",
        sensor_id="S-01",
        target_type=TargetType.DRONE,
        threat_level=ThreatLevel.CRITICAL,
        centroid=centroid,
        confidence=0.99
    )

    parsed = generator.validate_and_parse(xml_str)
    assert parsed["uid"] == "IBVAP-ALERT-12345"
    assert parsed["type"] == "a-h-A-M-F-Q"
    assert parsed["lat"] == "34.123456"
    assert parsed["lon"] == "74.654321"
    assert parsed["bop_id"] == "BOP-BRAVO-02"
    assert parsed["threat_level"] == "CRITICAL"


def test_cot_rejects_malicious_entity_expansion_and_dtd():
    """
    P1-3 Regression Test: Proves that defusedxml blocks Billion Laughs entity expansion attacks and DTD injections.
    """
    generator = CoTGenerator()

    # 1. Billion Laughs entity expansion payload
    malicious_xml = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
     <!ENTITY lol "lol">
     <!ELEMENT lolz (#PCDATA)>
     <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
     <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
    ]>
    <event version="2.0" uid="ATTACK-01" type="a-h-G" time="2026-08-27T00:00:00Z" start="2026-08-27T00:00:00Z" stale="2026-08-27T00:05:00Z">
      <point lat="0" lon="0" hae="0"/>
      <detail><remarks>&lol2;</remarks></detail>
    </event>"""

    # defusedxml will raise DTDForbidden / EntitiesForbidden exception
    with pytest.raises(Exception):
        generator.validate_and_parse(malicious_xml)
