/**
 * Central Gateway REST Client for IBVAP Tactical Dashboard.
 */

import type { SensorConfig, TacticalAlert, VectorEmbeddingPayload } from "@ibvap/core-types";

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";

export interface AdmissibilityReport {
  alert_id: string;
  is_admissible: boolean;
  leaf_hash_valid: boolean;
  recalculated_leaf_hash: string;
  stored_leaf_hash: string;
  evidence_cid: string;
  merkle_root_verified: boolean;
  batch_id?: string;
  merkle_root_hash?: string;
  details: string;
}

export interface PaginatedFeedResponse {
  total: number;
  limit: number;
  offset: number;
  results: TacticalAlert[];
}

export const api = {
  async getSensors(bopSectorId?: string): Promise<SensorConfig[]> {
    try {
      const url = bopSectorId
        ? `${GATEWAY_URL}/api/v1/sensors?bop_sector_id=${encodeURIComponent(bopSectorId)}`
        : `${GATEWAY_URL}/api/v1/sensors`;
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return [];
      return await res.json();
    } catch {
      return [];
    }
  },

  async getAlertsFeed(limit: number = 50, offset: number = 0, bopId?: string): Promise<PaginatedFeedResponse> {
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      if (bopId) params.append("bop_id", bopId);
      const res = await fetch(`${GATEWAY_URL}/api/v1/alerts/feed?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) return { total: 0, limit, offset, results: [] };
      return await res.json();
    } catch {
      return { total: 0, limit, offset, results: [] };
    }
  },

  async verifyAuditProof(alertId: string): Promise<AdmissibilityReport> {
    const res = await fetch(`${GATEWAY_URL}/api/v1/audit/verify/${encodeURIComponent(alertId)}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`Audit verification failed with HTTP ${res.status}`);
    }
    return await res.json();
  },

  async searchWatchlist(probeEmbedding: number[], threshold: number = 0.75): Promise<any> {
    const res = await fetch(`${GATEWAY_URL}/api/v1/watchlist/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        probe_embedding_512d: probeEmbedding,
        top_k: 5,
        threshold,
      }),
    });
    return await res.json();
  },
};
