/**
 * Canonical TypeScript Data Contracts for IBVAP Monorepo.
 * Mirrored from packages/core-types/src/python
 */

export interface GeoPoint {
  latitude: number;
  longitude: number;
  altitude_m: number;
}

export interface PolygonCoordinate {
  x: number; // Normalized [0.0, 1.0]
  y: number; // Normalized [0.0, 1.0]
  geo_point?: GeoPoint;
}

export interface SensorConfig {
  id: string;
  name: string;
  rtsp_url: string;
  gps: GeoPoint;
  bop_sector_id: string;
  active_polygon_coordinates: PolygonCoordinate[];
  is_active: boolean;
  fps_limit: number;
  stream_width: number;
  stream_height: number;
  ptz_capable: boolean;
  created_at: string;
  updated_at: string;
}

export interface BoundingBox {
  x1: number; // Normalized [0.0, 1.0]
  y1: number;
  x2: number;
  y2: number;
  confidence: number;
  class_id: number;
  track_id?: number;
  label?: string;
}

export interface DetectionBatch {
  sensor_id: string;
  frame_id: number;
  timestamp: string;
  detections: BoundingBox[];
  inference_latency_ms: number;
}

export type ThreatLevel = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type TargetType = "PERSON" | "VEHICLE" | "DRONE" | "WEAPON" | "UNKNOWN";

export interface GeoCentroid {
  latitude: number;
  longitude: number;
  altitude_m: number;
}

export interface TacticalAlert {
  alert_id: string;
  bop_id: string;
  sensor_id: string;
  timestamp: string;
  target_type: TargetType;
  threat_level: ThreatLevel;
  centroid: GeoCentroid;
  cot_xml_string: string;
  evidence_cid: string;
  merkle_leaf_hash: string;
  bounding_box?: BoundingBox;
  confidence: number;
  description?: string;
}

export interface VectorEmbeddingPayload {
  track_id: number;
  embedding_512d: number[]; // Length: 512
  watchlist_match_score?: number;
  sensor_id?: string;
  matched_poi_id?: string;
  model_name: string;
  extracted_at: string;
}

export interface CoTEvent {
  uid: string;
  cot_type: string;
  how: string;
  time: string;
  start: string;
  stale: string;
  point: GeoPoint;
  callsign: string;
  remarks?: string;
  sensor_uid?: string;
}
