"use client";

import React from "react";
import type { SensorConfig, TacticalAlert } from "@ibvap/core-types";
import { Camera, Crosshair, Eye, Maximize2, Shield } from "lucide-react";

interface StreamHUDProps {
  sensor: SensorConfig | null;
  activeAlert: TacticalAlert | null;
}

export const StreamHUD: React.FC<StreamHUDProps> = ({ sensor, activeAlert }) => {
  return (
    <div className="relative w-full h-full bg-black flex flex-col justify-between border border-tactical-border overflow-hidden">
      {/* Top Telemetry HUD */}
      <div className="p-3 bg-gradient-to-b from-black/80 to-transparent flex items-center justify-between text-xs font-mono z-10">
        <div className="flex items-center space-x-2">
          <Camera className="w-4 h-4 text-cyan-400" />
          <span className="font-bold text-slate-200">{sensor ? sensor.name : "CAM-NORTH-SECTOR-01"}</span>
          <span className="px-1.5 py-0.5 bg-red-950/80 border border-red-700 text-red-400 text-[10px] rounded animate-pulse">
            LIVE 30 FPS
          </span>
        </div>

        <div className="flex items-center space-x-4 text-[11px] text-slate-300">
          <div>LAT: {sensor?.gps.latitude.toFixed(5) || "34.0522"}</div>
          <div>LON: {sensor?.gps.longitude.toFixed(5) || "74.8856"}</div>
          <div>ALT: {sensor?.gps.altitude_m || "1620"}m</div>
        </div>
      </div>

      {/* Center Simulated Frame & Bounding Box Overlays */}
      <div className="relative flex-1 flex items-center justify-center">
        {/* Reticle / Crosshair */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
          <Crosshair className="w-48 h-48 text-cyan-400" />
        </div>

        {/* Dynamic Intrusion Bounding Box overlay */}
        {activeAlert?.bounding_box && (
          <div
            className="absolute border-2 border-rose-500 bg-rose-500/10 transition-all duration-200 pointer-events-none"
            style={{
              left: `${activeAlert.bounding_box.x1 * 100}%`,
              top: `${activeAlert.bounding_box.y1 * 100}%`,
              width: `${(activeAlert.bounding_box.x2 - activeAlert.bounding_box.x1) * 100}%`,
              height: `${(activeAlert.bounding_box.y2 - activeAlert.bounding_box.y1) * 100}%`,
            }}
          >
            <div className="absolute -top-5 left-0 bg-rose-600 text-white font-mono text-[9px] px-1 py-0.5 whitespace-nowrap">
              TARGET #{activeAlert.bounding_box.track_id || "101"} [{Math.round(activeAlert.confidence * 100)}%]
            </div>
          </div>
        )}

        {/* Video stream placeholder / synthetic radar background */}
        <div className="text-center space-y-2 pointer-events-none">
          <Eye className="w-12 h-12 text-slate-700 mx-auto animate-pulse" />
          <div className="text-xs font-mono text-slate-500">OPTICAL / THERMAL SENSOR STREAM</div>
          <div className="text-[10px] font-mono text-cyan-500/60">TENSORRT INFERENCE ENGINE ATTACHED</div>
        </div>
      </div>

      {/* Bottom Telemetry HUD */}
      <div className="p-2.5 bg-gradient-to-t from-black/90 to-transparent flex items-center justify-between text-[11px] font-mono text-slate-400 z-10 border-t border-slate-800/50">
        <div>PROTOCOL: RTSP/H.264 // NVDEC HW ACCEL</div>
        <div className="flex items-center space-x-2">
          <span className="text-emerald-400">TRIPWIRE: ACTIVE</span>
          <span className="text-slate-600">|</span>
          <span className="text-cyan-400">POLYGON: RESTRICTED</span>
        </div>
      </div>
    </div>
  );
};
