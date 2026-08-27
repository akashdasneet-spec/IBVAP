import argparse
import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sys
import time
from typing import Generator, List, Optional
from uuid import UUID, uuid4
import cv2
import httpx
import numpy as np

# Safe path bootstrap for packages and submodules
_current_file = Path(__file__).resolve()
_edge_src = _current_file.parent

if str(_edge_src) not in sys.path:
    sys.path.insert(0, str(_edge_src))

# Safe fallback for core-types if not installed in environment
try:
    import ibvap_core_types
except ImportError:
    for _parent in _current_file.parents:
        _candidate = _parent / "packages" / "core-types" / "src"
        if _candidate.is_dir():
            sys.path.insert(0, str(_candidate))
            break

# Core contracts
from ibvap_core_types import (
    BoundingBox,
    DetectionBatch,
    GeoPoint,
    PolygonCoordinate,
    SensorConfig,
    TacticalAlert,
    TargetType,
    ThreatLevel,
)

# Pipeline & Security modules
from analytics.fence import SpatialVirtualFence, ZoneViolation
from crypto.evidence_hasher import EvidenceHasher
from inference.enhancer import LowLightEnhancer
from inference.detector import DetectorConfig, YOLOv11Detector
from pipeline.ingestor import VideoIngestor, IngestedFrame
from security.cot import CoTGenerator
from security.vault import EvidenceVault
from security.merkle import MerkleAuditLedger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("edge_engine.main")


CLASS_COLORS = {
    "Person": (0, 230, 118),       # Green
    "Vehicle": (0, 229, 255),      # Cyan
    "Weapon": (255, 23, 68),       # Red
    "Abandoned Package": (255, 145, 0)  # Orange
}


def draw_hud(
    frame: np.ndarray,
    tracked_boxes: List[BoundingBox],
    violations: List[ZoneViolation],
    fence: SpatialVirtualFence,
    fps: float,
    enhance_latency: float,
    infer_latency: float,
    bypassed_enhance: bool
) -> np.ndarray:
    """Renders defense tactical HUD with bounding boxes, zone polygons, and telemetry banner."""
    canvas = frame.copy()
    h, w = canvas.shape[:2]

    # 1. Draw Virtual Restricted Zones
    overlay = canvas.copy()
    for zone_id, zone in fence.zones.items():
        pts = np.array([[int(c.x * w), int(c.y * h)] for c in zone.polygon_coords], np.int32)
        pts = pts.reshape((-1, 1, 2))
        
        # Red fill if zone currently has violations, cyan otherwise
        is_active_violation = any(v.zone_id == zone_id for v in violations)
        fill_color = (0, 0, 180) if is_active_violation else (100, 150, 0)
        border_color = (0, 0, 255) if is_active_violation else (0, 229, 255)

        cv2.fillPoly(overlay, [pts], fill_color)
        cv2.polylines(canvas, [pts], isClosed=True, color=border_color, thickness=2)

    cv2.addWeighted(overlay, 0.25, canvas, 0.75, 0, canvas)

    # 2. Draw Tracked Target Bounding Boxes & Footprint Ground Points
    for bbox in tracked_boxes:
        x1, y1 = int(bbox.x1 * w), int(bbox.y1 * h)
        x2, y2 = int(bbox.x2 * w), int(bbox.y2 * h)
        
        label_name = bbox.label or "Target"
        color = CLASS_COLORS.get(label_name, (200, 200, 200))
        
        # Check if this target is in violation
        is_target_violating = any(v.track_id == bbox.track_id for v in violations)
        if is_target_violating:
            color = (0, 0, 255)  # Flash red for active threat

        # Draw box
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)

        # Draw ground contact point
        gx, gy = int((x1 + x2) / 2), y2
        cv2.circle(canvas, (gx, gy), 5, (0, 255, 255), -1)

        # Draw header tag
        tag = f"ID:{bbox.track_id} {label_name} {int(bbox.confidence * 100)}%"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(canvas, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(canvas, tag, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    # 3. Top Telemetry Banner
    banner_h = 38
    cv2.rectangle(canvas, (0, 0), (w, banner_h), (10, 14, 22), -1)
    cv2.line(canvas, (0, banner_h), (w, banner_h), (40, 50, 70), 1)

    enhance_tag = "ENHANCE: BYPASSED" if bypassed_enhance else f"ENHANCE: {enhance_latency:.1f}ms"
    hud_text = (
        f"IBVAP EDGE AI | FPS: {fps:.1f} | INFER: {infer_latency:.1f}ms | {enhance_tag} | "
        f"TRACKS: {len(tracked_boxes)} | ALERTS: {len(violations)}"
    )
    cv2.putText(canvas, hud_text, (15, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 229, 255), 1, cv2.LINE_AA)

    # 4. Draw Active Violation Alerts Banner if present
    if len(violations) > 0:
        alert_h = 30 * len(violations)
        cv2.rectangle(canvas, (10, h - alert_h - 10), (w - 10, h - 10), (0, 0, 120), -1)
        for i, v in enumerate(violations):
            alert_msg = f"🚨 [{v.threat_level.value}] {v.violation_type} | {v.description}"
            cv2.putText(canvas, alert_msg, (20, h - alert_h + (i * 28) + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)

    return canvas


class EdgePipelineEngine:
    """
    Complete Edge Processing Pipeline.
    Combines Ingestion, Low-Light Enhancement, YOLOv11+ByteTrack, and Virtual Fencing.
    """

    def __init__(
        self,
        source: str = "videotestsrc",
        bop_id: str = "BOP-SECTOR-ALPHA-01",
        sensor_id: Optional[UUID] = None,
        conf_threshold: float = 0.45,
        loiter_sec: float = 5.0,
        enable_enhancement: bool = True,
        gateway_url: Optional[str] = None,
        evidence_master_key: Optional[bytes | str] = None,
        allow_ephemeral_key: bool = False
    ):
        self.source = source
        self.bop_id = bop_id
        self.sensor_id = sensor_id or UUID("a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d")
        self.enable_enhancement = enable_enhancement
        self.gateway_url = gateway_url

        # Check environment if ephemeral keys are permitted (test / dev mode only)
        env_allow_ephemeral = os.getenv("IBVAP_ALLOW_EPHEMERAL_KEY", "").lower() in ("true", "1", "yes")
        final_allow_ephemeral = allow_ephemeral_key or env_allow_ephemeral

        # 1. Sensor & Zone Configuration
        self.sensor_config = SensorConfig(
            id=self.sensor_id,
            name=f"EDGE-OPTICAL-{bop_id}",
            rtsp_url=source if not source.isdigit() else f"camera://{source}",
            gps=GeoPoint(latitude=34.052235, longitude=74.885628, altitude_m=1620.0),
            bop_sector_id=bop_id,
            active_polygon_coordinates=[
                PolygonCoordinate(x=0.20, y=0.35),
                PolygonCoordinate(x=0.80, y=0.35),
                PolygonCoordinate(x=0.85, y=0.88),
                PolygonCoordinate(x=0.15, y=0.88),
            ],
            fps_limit=30
        )

        # 2. Pipeline & Security Modules
        self.ingestor = VideoIngestor(source=source, target_fps=30)
        self.enhancer = LowLightEnhancer(luminance_threshold=0.45)
        self.detector = YOLOv11Detector(DetectorConfig(conf_threshold=conf_threshold, enable_tracking=True))
        self.fence = SpatialVirtualFence(self.sensor_config, default_loiter_sec=loiter_sec)
        self.hasher = EvidenceHasher()
        self.cot_generator = CoTGenerator()
        self.vault = EvidenceVault(
            master_key=evidence_master_key,
            allow_ephemeral_key=final_allow_ephemeral
        )
        self.merkle_ledger = MerkleAuditLedger(batch_size=25)

        # Telemetry
        self.fps_avg = 0.0
        self._prev_time = time.perf_counter()

    def process_frame(self, frame_data: np.ndarray) -> Tuple[np.ndarray, List[BoundingBox], List[ZoneViolation], List[TacticalAlert], dict]:
        """
        Executes complete pipeline on a single frame.
        Returns: (rendered_hud, tracked_boxes, zone_violations, tactical_alerts, metrics)
        """
        t0 = time.perf_counter()

        # 1. Low-Light Enhancement with Dynamic Bypass
        if self.enable_enhancement:
            enh_res = self.enhancer.enhance(frame_data)
            proc_frame = enh_res.frame
            enhance_latency = enh_res.latency_ms
            bypassed_enhance = enh_res.bypassed
        else:
            proc_frame = frame_data
            enhance_latency = 0.0
            bypassed_enhance = True

        # 2. YOLOv11 Target Detection & ByteTrack
        tracked_boxes, infer_latency = self.detector.detect_and_track(proc_frame)

        # 3. Spatial Virtual Fencing & Loitering Analysis
        violations = self.fence.evaluate_tracks(tracked_boxes)

        # 4. Generate Encrypted Evidence, Merkle Leaf Hash, CoT XML & TacticalAlert
        tactical_alerts: List[TacticalAlert] = []
        for v in violations:
            alert_id = uuid4()
            now_utc = datetime.now(timezone.utc)

            # Encode high-res frame snapshot (JPEG)
            _, enc_img = cv2.imencode(".jpg", proc_frame)
            frame_jpeg = enc_img.tobytes()
            dummy_mp4_clip = b"\x00\x00\x00\x18ftypmp42" + frame_jpeg[:500]

            # Encrypt evidence bundle and anchor to IPFS
            meta = {
                "alert_id": str(alert_id),
                "bop_id": self.bop_id,
                "sensor_id": str(self.sensor_id),
                "violation": v.violation_type,
                "threat_level": v.threat_level.value
            }
            _, evidence_cid = self.vault.package_encrypt_and_store(frame_jpeg, dummy_mp4_clip, meta)

            # Record in Merkle Audit Ledger
            leaf_hash = self.merkle_ledger.record_alert(
                cid=evidence_cid,
                timestamp=now_utc,
                bop_id=self.bop_id,
                sensor_id=str(self.sensor_id)
            )

            # Generate MIL-STD CoT XML
            cot_xml = self.cot_generator.generate_xml(
                alert_id=str(alert_id),
                bop_id=self.bop_id,
                sensor_id=str(self.sensor_id),
                target_type=v.target_type,
                threat_level=v.threat_level,
                centroid=v.centroid,
                confidence=v.bounding_box.confidence,
                remarks=v.description,
                event_time=now_utc
            )

            alert = TacticalAlert(
                alert_id=alert_id,
                bop_id=self.bop_id,
                sensor_id=self.sensor_id,
                timestamp=now_utc,
                target_type=v.target_type,
                threat_level=v.threat_level,
                centroid=v.centroid,
                cot_xml_string=cot_xml,
                evidence_cid=evidence_cid,
                merkle_leaf_hash=leaf_hash,
                bounding_box=v.bounding_box,
                confidence=v.bounding_box.confidence,
                description=v.description
            )
            tactical_alerts.append(alert)

        # 5. Compute FPS
        now = time.perf_counter()
        dt = now - self._prev_time
        self._prev_time = now
        current_fps = (1.0 / dt) if dt > 0 else 30.0
        self.fps_avg = 0.9 * self.fps_avg + 0.1 * current_fps if self.fps_avg > 0 else current_fps

        # 6. Render Tactical Visual HUD
        hud_frame = draw_hud(
            frame=proc_frame,
            tracked_boxes=tracked_boxes,
            violations=violations,
            fence=self.fence,
            fps=self.fps_avg,
            enhance_latency=enhance_latency,
            infer_latency=infer_latency,
            bypassed_enhance=bypassed_enhance
        )

        metrics = {
            "fps": self.fps_avg,
            "enhance_ms": enhance_latency,
            "infer_ms": infer_latency,
            "bypassed_enhance": bypassed_enhance,
            "total_ms": (now - t0) * 1000.0,
            "tracks_count": len(tracked_boxes),
            "violations_count": len(violations)
        }

        return hud_frame, tracked_boxes, violations, tactical_alerts, metrics

    def run_stream(self, max_frames: Optional[int] = None, display: bool = False) -> Generator[TacticalAlert, None, None]:
        """
        Runs the full video stream ingestion & inference loop.
        Yields generated TacticalAlert objects in real time.
        """
        logger.info(f"Starting IBVAP Edge Engine for {self.bop_id} (Source: {self.source})")
        self.ingestor.start()
        frame_idx = 0

        try:
            while True:
                ingested = self.ingestor.read(timeout=2.0)
                if ingested is None:
                    continue

                frame_idx += 1
                hud_frame, boxes, violations, alerts, metrics = self.process_frame(ingested.data)

                # Log FPS & tactical telemetry
                if frame_idx % 30 == 0 or len(violations) > 0:
                    logger.info(
                        f"Frame #{frame_idx:05d} | FPS: {metrics['fps']:.1f} | Latency: {metrics['total_ms']:.1f}ms | "
                        f"Active Tracks: {metrics['tracks_count']} | Violations: {metrics['violations_count']}"
                    )

                # Yield generated alerts
                for alert in alerts:
                    logger.warning(f"🚨 TACTICAL ALERT: [{alert.threat_level.value}] {alert.description}")
                    yield alert

                # Optional GUI display
                if display:
                    cv2.imshow("IBVAP Edge Tactical C2 HUD", hud_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                if max_frames and frame_idx >= max_frames:
                    logger.info(f"Reached maximum frame limit ({max_frames}). Stopping stream.")
                    break

        finally:
            self.ingestor.stop()
            if display:
                cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="IBVAP Edge Analytics & Video Ingestion Engine")
    parser.add_argument("--source", type=str, default="videotestsrc", help="RTSP URL, video file path, webcam index, or 'videotestsrc'")
    parser.add_argument("--bop-id", type=str, default="BOP-SECTOR-ALPHA-01", help="Border Outpost Sector ID")
    parser.add_argument("--conf", type=float, default=0.45, help="YOLOv11 Detection Confidence Threshold")
    parser.add_argument("--loiter-sec", type=float, default=5.0, help="Loitering alert duration threshold in seconds")
    parser.add_argument("--no-enhance", action="store_true", help="Disable Zero-DCE++ Low Light Enhancement")
    parser.add_argument("--display", action="store_true", help="Show real-time OpenCV HUD window")
    parser.add_argument("--headless", action="store_true", help="Run without UI in headless server mode")
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after N frames (useful for testing)")
    parser.add_argument("--gateway-url", type=str, default=None, help="C2 Central Gateway URL to dispatch alerts")

    args = parser.parse_args()

    engine = EdgePipelineEngine(
        source=args.source,
        bop_id=args.bop_id,
        conf_threshold=args.conf,
        loiter_sec=args.loiter_sec,
        enable_enhancement=not args.no_enhance,
        gateway_url=args.gateway_url
    )

    display_gui = args.display and not args.headless

    for alert in engine.run_stream(max_frames=args.max_frames, display=display_gui):
        # Transmit or process alert
        pass


if __name__ == "__main__":
    main()
