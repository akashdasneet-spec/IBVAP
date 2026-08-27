"use client";

import React, { useEffect, useState } from "react";
import type { SensorConfig, TacticalAlert } from "@ibvap/core-types";
import { Header } from "@/components/Header";
import { TacticalMap } from "@/components/TacticalMap";
import { VideoGrid } from "@/components/VideoGrid";
import { AlertFeed } from "@/components/AlertFeed";
import { AuditDrawer } from "@/components/AuditDrawer";
import { useTacticalWebSocket } from "@/hooks/useTacticalWebSocket";
import { api } from "@/lib/api";

export default function DashboardPage() {
  const [sensors, setSensors] = useState<SensorConfig[]>([
    {
      id: "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
      name: "EDGE-OPTICAL-ALPHA-01",
      rtsp_url: "rtsp://edge-01.tactical.internal:554/live",
      gps: { latitude: 34.0522, longitude: 74.8856, altitude_m: 1620.0 },
      bop_sector_id: "BOP-SECTOR-ALPHA-01",
      active_polygon_coordinates: [
        { x: 0.2, y: 0.35 },
        { x: 0.8, y: 0.35 },
        { x: 0.85, y: 0.88 },
        { x: 0.15, y: 0.88 },
      ],
      is_active: true,
      fps_limit: 30,
      stream_width: 1920,
      stream_height: 1080,
      ptz_capable: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
      name: "EDGE-THERMAL-ALPHA-02",
      rtsp_url: "rtsp://edge-02.tactical.internal:554/live",
      gps: { latitude: 34.0558, longitude: 74.8912, altitude_m: 1635.0 },
      bop_sector_id: "BOP-SECTOR-ALPHA-01",
      active_polygon_coordinates: [
        { x: 0.15, y: 0.25 },
        { x: 0.75, y: 0.25 },
        { x: 0.80, y: 0.80 },
        { x: 0.10, y: 0.80 },
      ],
      is_active: true,
      fps_limit: 30,
      stream_width: 1920,
      stream_height: 1080,
      ptz_capable: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ]);

  const [alerts, setAlerts] = useState<TacticalAlert[]>([
    {
      alert_id: "9f8e7d6c-5b4a-3210-fedc-ba9876543210",
      bop_id: "BOP-SECTOR-ALPHA-01",
      sensor_id: "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
      timestamp: new Date().toISOString(),
      target_type: "PERSON",
      threat_level: "HIGH",
      centroid: { latitude: 34.0528, longitude: 74.8862, altitude_m: 1622.0 },
      cot_xml_string: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<event version="2.0" uid="IBVAP-ALERT-01" type="a-h-G-U-C-I" how="m-g" time="${new Date().toISOString()}">\n  <point lat="34.052800" lon="74.886200" hae="1622.0" ce="10.0" le="5.0"/>\n  <detail><contact callsign="BOP-ALPHA-01-PERSON"/></detail>\n</event>`,
      evidence_cid: "bafybeiczsscdsbs7ffqz55asqdf32gvwlsdp4s8gshd",
      merkle_leaf_hash: "a4f89d3000b1a03975ef7c9802cf67e012903fe51fa98bc54c0e6db61491cf65",
      bounding_box: { x1: 0.42, y1: 0.45, x2: 0.52, y2: 0.68, confidence: 0.94, class_id: 0, track_id: 101, label: "Person" },
      confidence: 0.94,
      description: "Perimeter intrusion detected in Sector Alpha restricted zone.",
    },
  ]);

  const [selectedSensor, setSelectedSensor] = useState<SensorConfig | null>(sensors[0] || null);
  const [selectedAlert, setSelectedAlert] = useState<TacticalAlert | null>(alerts[0] || null);
  const [isAuditDrawerOpen, setIsAuditDrawerOpen] = useState(false);

  // Fetch Initial REST Data
  useEffect(() => {
    async function loadData() {
      const [fetchedSensors, fetchedAlerts] = await Promise.all([
        api.getSensors(),
        api.getAlertsFeed(20),
      ]);
      if (fetchedSensors.length > 0) setSensors(fetchedSensors);
      if (fetchedAlerts.results.length > 0) setAlerts(fetchedAlerts.results);
    }
    loadData();
  }, []);

  // Real-Time WebSocket Hook with rAF Batching & Bounded Ring Buffer
  const { isConnected, latencyMs, throughputMsgSec } = useTacticalWebSocket({
    onAlertBatch: (newAlertBatch) => {
      setAlerts((prev) => {
        const ids = new Set(newAlertBatch.map((a) => a.alert_id));
        const filteredPrev = prev.filter((a) => !ids.has(a.alert_id));
        // Bounded ring buffer: Cap at 200 items
        return [...newAlertBatch, ...filteredPrev].slice(0, 200);
      });
      if (newAlertBatch.length > 0) {
        setSelectedAlert(newAlertBatch[0]);
      }
    },
    onSensorUpdate: (updatedSensor) => {
      setSensors((prev) => [
        ...prev.filter((s) => s.id !== updatedSensor.id),
        updatedSensor,
      ]);
    },
  });

  const handleSelectAlert = (alert: TacticalAlert) => {
    setSelectedAlert(alert);
    setIsAuditDrawerOpen(true);
  };

  return (
    <main className="flex flex-col h-screen overflow-hidden bg-tactical-dark select-none">
      {/* Top Tactical Command Bar */}
      <Header
        wsConnected={isConnected}
        activeSensorsCount={sensors.length}
        alertCount={alerts.length}
      />

      {/* Main Operations Grid */}
      <div className="flex-1 grid grid-cols-12 overflow-hidden relative">
        {/* Left / Center Area: Map (Top) + Surveillance Wall (Bottom) */}
        <div className="col-span-9 flex flex-col border-r border-tactical-border h-full overflow-hidden">
          {/* Top Half: Geospatial MapLibre C4ISR View (55% Height) */}
          <div className="h-[55%] relative">
            <TacticalMap
              sensors={sensors}
              alerts={alerts}
              selectedSensor={selectedSensor}
              selectedAlert={selectedAlert}
              onSelectSensor={setSelectedSensor}
              onSelectAlert={handleSelectAlert}
            />
          </div>

          {/* Bottom Half: Multi-Camera Video Surveillance Wall (45% Height) */}
          <div className="h-[45%] relative">
            <VideoGrid
              sensors={sensors}
              alerts={alerts}
              selectedSensor={selectedSensor}
              onSelectSensor={setSelectedSensor}
            />
          </div>
        </div>

        {/* Right Area: Incident Log Feed */}
        <div className="col-span-3 h-full overflow-hidden">
          <AlertFeed
            alerts={alerts}
            onSelectAlert={handleSelectAlert}
          />
        </div>

        {/* Slide-In Forensic Audit Drawer Overlay */}
        {isAuditDrawerOpen && selectedAlert && (
          <div className="absolute top-0 right-0 bottom-0 z-40">
            <AuditDrawer
              alert={selectedAlert}
              onClose={() => setIsAuditDrawerOpen(false)}
            />
          </div>
        )}
      </div>
    </main>
  );
}
