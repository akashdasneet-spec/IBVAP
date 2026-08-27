-- IBVAP Database Initialization Script
-- Enables pgvector extension and creates initial tables & indexes

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Sensors Table
CREATE TABLE IF NOT EXISTS sensors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    rtsp_url VARCHAR(512) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    altitude_m DOUBLE PRECISION DEFAULT 0.0,
    bop_sector_id VARCHAR(64) NOT NULL,
    active_polygon JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    fps_limit INTEGER DEFAULT 30,
    stream_width INTEGER DEFAULT 1920,
    stream_height INTEGER DEFAULT 1080,
    ptz_capable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sensors_bop_sector ON sensors(bop_sector_id);

-- Tactical Alerts Table
CREATE TABLE IF NOT EXISTS tactical_alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    bop_id VARCHAR(64) NOT NULL,
    sensor_id UUID NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    target_type VARCHAR(32) NOT NULL,
    threat_level VARCHAR(32) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    altitude_m DOUBLE PRECISION DEFAULT 0.0,
    cot_xml_string TEXT NOT NULL,
    evidence_cid VARCHAR(128) NOT NULL,
    merkle_leaf_hash VARCHAR(64) UNIQUE NOT NULL,
    bounding_box JSONB,
    confidence DOUBLE PRECISION DEFAULT 0.9,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_bop_id ON tactical_alerts(bop_id);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON tactical_alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_threat_level ON tactical_alerts(threat_level);
CREATE INDEX IF NOT EXISTS idx_alerts_merkle_hash ON tactical_alerts(merkle_leaf_hash);

-- Vector Watchlist & ReID Embeddings (512-dimension HNSW Index)
CREATE TABLE IF NOT EXISTS watchlist_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    poi_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    threat_category VARCHAR(64) NOT NULL,
    embedding_512d vector(512) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Fast Approximate Nearest Neighbor (ANN) HNSW Index on 512-d embeddings
CREATE INDEX IF NOT EXISTS idx_watchlist_hnsw 
ON watchlist_embeddings 
USING hnsw (embedding_512d vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Seed Sample BOP Sector Sensor
INSERT INTO sensors (id, name, rtsp_url, latitude, longitude, altitude_m, bop_sector_id, active_polygon)
VALUES (
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    'EDGE-OPTICAL-ALPHA-01',
    'rtsp://edge-01.tactical.internal:554/live',
    34.052235,
    74.885628,
    1620.0,
    'BOP-SECTOR-ALPHA-01',
    '[{"x": 0.2, "y": 0.3}, {"x": 0.8, "y": 0.3}, {"x": 0.85, "y": 0.9}, {"x": 0.15, "y": 0.9}]'::jsonb
) ON CONFLICT (id) DO NOTHING;
