"""
ByteTrack Multi-Object Tracking (MOT) Association Engine.
Provides robust track ID persistence across occlusions, scale shifts, and edge camera vibration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np

from ibvap_core_types import BoundingBox


class TrackState(str, Enum):
    NEW = "NEW"
    TRACKED = "TRACKED"
    LOST = "LOST"
    REMOVED = "REMOVED"


class KalmanFilter2D:
    """
    Simplified, high-speed 2D Kalman filter for bounding box state tracking:
    State: [x_center, y_center, width, height, vx, vy, vw, vh]
    """

    def __init__(self):
        # State vector
        self.state: Optional[np.ndarray] = None
        # Covariance matrix
        self.P = np.eye(8, dtype=np.float32) * 10.0
        
        # State transition matrix F
        self.F = np.eye(8, dtype=np.float32)
        for i in range(4):
            self.F[i, i + 4] = 1.0  # x + vx, y + vy...

        # Measurement matrix H
        self.H = np.zeros((4, 8), dtype=np.float32)
        for i in range(4):
            self.H[i, i] = 1.0

        # Process noise Q and Measurement noise R
        self.Q = np.eye(8, dtype=np.float32) * 0.05
        self.R = np.eye(4, dtype=np.float32) * 1.0

    def initiate(self, bbox: BoundingBox) -> None:
        cx, cy = bbox.center
        w, h = bbox.width, bbox.height
        self.state = np.array([cx, cy, w, h, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        self.P = np.eye(8, dtype=np.float32) * 1.0

    def predict(self) -> np.ndarray:
        if self.state is None:
            return np.zeros(4, dtype=np.float32)
        self.state = self.F @ self.state
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.state[:4]

    def update(self, bbox: BoundingBox) -> None:
        cx, cy = bbox.center
        w, h = bbox.width, bbox.height
        z = np.array([cx, cy, w, h], dtype=np.float32)

        # Innovation
        y = z - (self.H @ self.state)
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)

        # Updated state and covariance
        self.state = self.state + K @ y
        self.P = (np.eye(8, dtype=np.float32) - K @ self.H) @ self.P


@dataclass
class STrack:
    track_id: int
    bbox: BoundingBox
    score: float
    class_id: int
    label: str
    state: TrackState = TrackState.TRACKED
    kalman: KalmanFilter2D = field(default_factory=KalmanFilter2D)
    age: int = 0
    time_since_update: int = 0
    hit_streak: int = 1

    def __post_init__(self):
        self.kalman.initiate(self.bbox)
        self.bbox = BoundingBox(
            x1=self.bbox.x1,
            y1=self.bbox.y1,
            x2=self.bbox.x2,
            y2=self.bbox.y2,
            confidence=self.score,
            class_id=self.class_id,
            track_id=self.track_id,
            label=self.label
        )

    def predict(self) -> None:
        pred_box = self.kalman.predict()
        cx, cy, w, h = pred_box[0], pred_box[1], pred_box[2], pred_box[3]
        x1 = max(0.0, float(cx - w / 2.0))
        y1 = max(0.0, float(cy - h / 2.0))
        x2 = min(1.0, float(cx + w / 2.0))
        y2 = min(1.0, float(cy + h / 2.0))
        
        self.bbox = BoundingBox(
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            confidence=self.score,
            class_id=self.class_id,
            track_id=self.track_id,
            label=self.label
        )
        self.age += 1
        self.time_since_update += 1

    def update(self, new_bbox: BoundingBox) -> None:
        self.kalman.update(new_bbox)
        self.bbox = BoundingBox(
            x1=new_bbox.x1,
            y1=new_bbox.y1,
            x2=new_bbox.x2,
            y2=new_bbox.y2,
            confidence=new_bbox.confidence,
            class_id=new_bbox.class_id,
            track_id=self.track_id,
            label=new_bbox.label or self.label
        )
        self.score = new_bbox.confidence
        self.time_since_update = 0
        self.hit_streak += 1
        self.state = TrackState.TRACKED

    def mark_lost(self) -> None:
        self.state = TrackState.LOST

    def mark_removed(self) -> None:
        self.state = TrackState.REMOVED


def calculate_iou_matrix(boxes_a: List[BoundingBox], boxes_b: List[BoundingBox]) -> np.ndarray:
    """Computes pairwise Intersection-over-Union (IoU) cost matrix."""
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)

    matrix = np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)
    for i, a in enumerate(boxes_a):
        for j, b in enumerate(boxes_b):
            inter_x1 = max(a.x1, b.x1)
            inter_y1 = max(a.y1, b.y1)
            inter_x2 = min(a.x2, b.x2)
            inter_y2 = min(a.y2, b.y2)

            inter_w = max(0.0, inter_x2 - inter_x1)
            inter_h = max(0.0, inter_y2 - inter_y1)
            inter_area = inter_w * inter_h

            area_a = a.width * a.height
            area_b = b.width * b.height
            union_area = area_a + area_b - inter_area

            iou = inter_area / union_area if union_area > 0 else 0.0
            matrix[i, j] = iou
    return matrix


class ByteTracker:
    """
    ByteTrack Multi-Object Tracker.
    Performs two-stage association to preserve IDs during partial and full occlusions.
    """

    def __init__(
        self,
        high_threshold: float = 0.5,
        low_threshold: float = 0.1,
        match_threshold: float = 0.7,  # 1 - IoU threshold
        max_time_lost: int = 30
    ):
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.match_threshold = match_threshold
        self.max_time_lost = max_time_lost

        self.tracked_stracks: List[STrack] = []
        self.lost_stracks: List[STrack] = []
        self.removed_stracks: List[STrack] = []
        self._next_id = 1
        self.frame_id = 0

    def _linear_assignment(
        self,
        cost_matrix: np.ndarray,
        thresh: float
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """Greedy matching for fast IoU linear assignment."""
        if cost_matrix.size == 0:
            return [], list(range(cost_matrix.shape[0])), list(range(cost_matrix.shape[1]))

        matches = []
        unmatched_a = list(range(cost_matrix.shape[0]))
        unmatched_b = list(range(cost_matrix.shape[1]))

        # Greedy match by lowest cost (highest IoU)
        while len(unmatched_a) > 0 and len(unmatched_b) > 0:
            sub_matrix = cost_matrix[np.ix_(unmatched_a, unmatched_b)]
            min_val = np.min(sub_matrix)
            if min_val > thresh:
                break
            min_idx = np.argmin(sub_matrix)
            r_idx, c_idx = np.unravel_index(min_idx, sub_matrix.shape)
            orig_r = unmatched_a[r_idx]
            orig_c = unmatched_b[c_idx]

            matches.append((orig_r, orig_c))
            unmatched_a.remove(orig_r)
            unmatched_b.remove(orig_c)

        return matches, unmatched_a, unmatched_b

    def update(self, detections: List[BoundingBox]) -> List[BoundingBox]:
        """
        Updates tracker state with new frame detections.
        Returns active tracked bounding boxes with persistent track_ids.
        """
        self.frame_id += 1
        activated_stracks = []
        refind_stracks = []
        lost_stracks = []
        removed_stracks = []

        # 1. Split detections into high-confidence and low-confidence
        dets_first = [d for d in detections if d.confidence >= self.high_threshold]
        dets_second = [d for d in detections if self.low_threshold <= d.confidence < self.high_threshold]

        # 2. Predict new locations of existing tracks with Kalman filter
        strack_pool = self.tracked_stracks + self.lost_stracks
        for strack in strack_pool:
            strack.predict()

        # -------------------------------------------------------------
        # Stage 1: Match high-confidence detections with active tracks
        # -------------------------------------------------------------
        pool_boxes = [s.bbox for s in strack_pool]
        first_boxes = dets_first
        iou_mat1 = 1.0 - calculate_iou_matrix(pool_boxes, first_boxes)

        matches_1, u_track_1, u_detection_1 = self._linear_assignment(iou_mat1, self.match_threshold)

        for track_idx, det_idx in matches_1:
            track = strack_pool[track_idx]
            det = first_boxes[det_idx]
            if track.state == TrackState.TRACKED or track.state == TrackState.NEW:
                track.update(det)
                activated_stracks.append(track)
            else:
                track.update(det)
                refind_stracks.append(track)

        # -------------------------------------------------------------
        # Stage 2: Match low-confidence detections with remaining tracks
        # -------------------------------------------------------------
        remain_tracks = [strack_pool[i] for i in u_track_1 if strack_pool[i].state in (TrackState.TRACKED, TrackState.LOST)]
        remain_boxes = [t.bbox for t in remain_tracks]
        second_boxes = dets_second
        iou_mat2 = 1.0 - calculate_iou_matrix(remain_boxes, second_boxes)

        matches_2, u_track_2, _ = self._linear_assignment(iou_mat2, 0.7)  # Generous threshold for occluded recovery

        for track_idx, det_idx in matches_2:
            track = remain_tracks[track_idx]
            det = second_boxes[det_idx]
            track.update(det)
            activated_stracks.append(track)

        # Mark unmatched tracks as lost
        for track_idx in u_track_2:
            track = remain_tracks[track_idx]
            track.mark_lost()
            lost_stracks.append(track)

        # -------------------------------------------------------------
        # Stage 3: Initiate new tracks from unmatched high-score detections
        # -------------------------------------------------------------
        for det_idx in u_detection_1:
            det = first_boxes[det_idx]
            new_track = STrack(
                track_id=self._next_id,
                bbox=det,
                score=det.confidence,
                class_id=det.class_id,
                label=det.label or "unknown"
            )
            self._next_id += 1
            activated_stracks.append(new_track)

        # -------------------------------------------------------------
        # Stage 4: Clean up lost and removed tracks
        # -------------------------------------------------------------
        for track in self.lost_stracks:
            if self.frame_id - track.age > self.max_time_lost:
                track.mark_removed()
                removed_stracks.append(track)

        # Update track state lists
        self.tracked_stracks = [t for t in activated_stracks if t.state in (TrackState.TRACKED, TrackState.NEW)]
        self.lost_stracks = [t for t in lost_stracks if t.state == TrackState.LOST]

        # Output active tracked bounding boxes
        output_boxes = []
        for track in self.tracked_stracks:
            output_boxes.append(track.bbox)

        return output_boxes
