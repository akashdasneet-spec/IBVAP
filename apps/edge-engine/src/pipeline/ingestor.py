"""
Multi-Threaded Video Ingestion Pipeline with Ring-Buffered Frame Dropping and Auto-Reconnect.
Supports hardware-accelerated GStreamer, standard RTSP (TCP), local video, and synthetic test streams.
"""

from dataclasses import dataclass
import logging
import queue
import threading
import time
from typing import Generator, Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger("edge_engine.ingestor")


@dataclass
class IngestedFrame:
    frame_id: int
    timestamp_ns: int
    data: np.ndarray  # HxWxC BGR image buffer
    width: int
    height: int
    is_synthetic: bool = False


class VideoIngestor:
    """
    High-throughput, multi-threaded RTSP / GStreamer video stream ingestor.
    
    Key Features:
    - Dedicated thread reading from video capture backend.
    - Bounded Queue with Ring-Buffer dropping (drops oldest frame when full to guarantee zero buffer lag).
    - Automatic Watchdog Reconnection with exponential backoff if the stream drops or freezes.
    - Fallback synthetic generator for testing / air-gapped simulations.
    """

    def __init__(
        self,
        source: str = "videotestsrc",
        queue_size: int = 5,
        target_fps: int = 30,
        reconnect_timeout_sec: float = 5.0,
        width: int = 1920,
        height: int = 1080,
        ring_buffer_size: Optional[int] = None,
        min_bandwidth_mbps: float = 1.5
    ):
        self.source = source
        self.queue_size = ring_buffer_size or queue_size
        self.ring_buffer_size = self.queue_size
        self.target_fps = target_fps
        self.reconnect_timeout_sec = reconnect_timeout_sec
        self.width = width
        self.height = height
        self.min_bandwidth_mbps = min_bandwidth_mbps
        self.is_degraded_mode = False  # Set to True if bandwidth < 1.5 Mbps (5 FPS keyframe mode)
        self.effective_fps = target_fps

        self._frame_queue: queue.Queue = queue.Queue(maxsize=self.queue_size)
        self._is_running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_seq = 0

        # Telemetry metrics
        self.total_frames_ingested = 0
        self.total_frames_dropped = 0
        self.dropped_frames = 0
        self.reconnect_count = 0
        self.last_frame_timestamp = 0.0
        self.last_frame_time = 0.0
        self._lock = threading.Lock()

    def set_bandwidth_mbps(self, mbps: float) -> None:
        """Dynamically adapts stream frame rate based on edge network conditions."""
        if mbps < self.min_bandwidth_mbps:
            self.is_degraded_mode = True
            self.effective_fps = 5  # Keyframe-only rate
            logger.warning(f"Bandwidth dropped to {mbps:.2f} Mbps (< {self.min_bandwidth_mbps} Mbps). Switched to 5 FPS degraded mode.")
        else:
            self.is_degraded_mode = False
            self.effective_fps = self.target_fps

    def _build_capture(self) -> Optional[cv2.VideoCapture]:
        """Builds OpenCV VideoCapture with GStreamer or FFmpeg backend."""
        if self.source.startswith("videotestsrc") or self.source == "mock":
            logger.info("Using Synthetic Test Pattern Frame Generator.")
            return None

        # Build GStreamer or RTSP capture
        if self.source.startswith("rtspsrc") or "nvv4l2decoder" in self.source:
            # GStreamer pipeline string
            cap = cv2.VideoCapture(self.source, cv2.CAP_GSTREAMER)
        elif self.source.startswith("rtsp://") or self.source.startswith("rtsps://"):
            # Set TCP transport for robust network delivery
            import os
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        elif self.source.isdigit():
            # USB Camera index (e.g. "0")
            cap = cv2.VideoCapture(int(self.source))
        else:
            # Local video file path
            cap = cv2.VideoCapture(self.source)

        if cap is not None and cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            logger.info(f"Successfully opened video capture source: {self.source}")
            return cap
        else:
            logger.warning(f"Failed to open video source: {self.source}. Will attempt auto-reconnect or fallback.")
            return None

    def _generate_synthetic_frame(self, frame_id: int) -> np.ndarray:
        """Generates a realistic test frame with border terrain simulation & moving targets."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Draw simulated terrain gradient (night vision / thermal terrain)
        cv2.rectangle(frame, (0, 0), (self.width, int(self.height * 0.4)), (15, 20, 25), -1)  # Sky/Horizon
        cv2.rectangle(frame, (0, int(self.height * 0.4)), (self.width, self.height), (35, 45, 40), -1)  # Ground

        # Draw border fence line
        fence_y = int(self.height * 0.45)
        cv2.line(frame, (0, fence_y), (self.width, fence_y), (80, 80, 80), 2)
        for fx in range(0, self.width, 80):
            cv2.line(frame, (fx, fence_y - 40), (fx, fence_y + 40), (100, 100, 100), 2)

        # Draw a moving simulated intruder
        t = frame_id * 0.04
        cx = int((0.35 + 0.3 * np.sin(t)) * self.width)
        cy = int((0.55 + 0.15 * np.cos(t * 0.7)) * self.height)
        
        # Target representation
        cv2.circle(frame, (cx, cy - 25), 12, (180, 180, 180), -1)  # Head
        cv2.rectangle(frame, (cx - 15, cy - 13), (cx + 15, cy + 35), (140, 140, 140), -1)  # Body

        # Target carrying weapon/package occasionally
        if int(frame_id / 60) % 2 == 1:
            cv2.rectangle(frame, (cx + 15, cy), (cx + 35, cy + 25), (100, 120, 160), -1)  # Package

        # Add timestamp & camera overlay
        cv2.putText(
            frame,
            f"IBVAP EDGE OPTICAL | FRAME #{frame_id:06d} | {time.strftime('%Y-%m-%d %H:%M:%S')}",
            (30, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 229, 255),
            2
        )
        return frame

    def _worker_loop(self) -> None:
        """Background acquisition thread."""
        frame_idx = 0
        backoff_delay = 1.0

        while self._is_running:
            # 1. Ensure capture source is active
            if self._cap is None and not (self.source.startswith("videotestsrc") or self.source == "mock"):
                self._cap = self._build_capture()
                if self._cap is None:
                    time.sleep(backoff_delay)
                    backoff_delay = min(backoff_delay * 1.5, 10.0)
                    continue
                else:
                    backoff_delay = 1.0

            # 2. Grab frame
            success = False
            raw_frame = None

            if self._cap is not None:
                success, raw_frame = self._cap.read()
                if not success or raw_frame is None:
                    logger.warning("RTSP stream disconnected or end-of-stream reached. Initiating auto-reconnect...")
                    if self._cap is not None:
                        self._cap.release()
                        self._cap = None
                    time.sleep(1.0)
                    continue
            else:
                # Synthetic Generator
                frame_idx += 1
                raw_frame = self._generate_synthetic_frame(frame_idx)
                success = True
                # Throttle synthetic rate to target FPS
                time.sleep(1.0 / self.target_fps)

            frame_idx += 1
            now_ns = time.time_ns()
            self.last_frame_time = time.time()

            h, w = raw_frame.shape[:2]
            ingested = IngestedFrame(
                frame_id=frame_idx,
                timestamp_ns=now_ns,
                data=raw_frame,
                width=w,
                height=h,
                is_synthetic=(self._cap is None)
            )

            # 3. Enqueue with Ring-Buffer drop logic
            with self._lock:
                if self._frame_queue.full():
                    try:
                        self._frame_queue.get_nowait()
                        self.total_frames_dropped += 1
                    except queue.Empty:
                        pass

                try:
                    self._frame_queue.put_nowait(ingested)
                    self.total_frames_ingested += 1
                except queue.Full:
                    self.total_frames_dropped += 1

    def start(self) -> "VideoIngestor":
        """Starts the background frame ingestion worker thread."""
        if not self._is_running:
            self._is_running = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="IngestorWorker")
            self._thread.start()
            logger.info(f"VideoIngestor started for source: {self.source}")
        return self

    def read(self, timeout: float = 2.0) -> Optional[IngestedFrame]:
        """
        Retrieves the latest available frame from the non-blocking queue.
        Returns None if no frame is available within timeout.
        """
        try:
            return self._frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def frames(self) -> Generator[IngestedFrame, None, None]:
        """Generator interface for easy iteration in main loop."""
        self.start()
        while self._is_running:
            frame = self.read()
            if frame is not None:
                yield frame

    def stop(self) -> None:
        """Stops ingestion worker and releases capture resources."""
        self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("VideoIngestor stopped.")

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
