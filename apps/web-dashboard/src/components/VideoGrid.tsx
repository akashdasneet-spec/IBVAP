"use client";

import React, { useEffect, useRef, useState } from "react";
import type { SensorConfig, TacticalAlert } from "@ibvap/core-types";
import { Camera, Eye, Grid2X2, Maximize2, Radio, RefreshCw, ShieldAlert, Video } from "lucide-react";

interface VideoGridProps {
  sensors: SensorConfig[];
  alerts: TacticalAlert[];
  selectedSensor: SensorConfig | null;
  onSelectSensor: (sensor: SensorConfig) => void;
}

const CLASS_COLORS: Record<string, { stroke: string; fill: string }> = {
  PERSON: { stroke: "#00e676", fill: "rgba(0, 230, 118, 0.15)" },
  VEHICLE: { stroke: "#00e5ff", fill: "rgba(0, 229, 255, 0.15)" },
  DRONE: { stroke: "#d500f9", fill: "rgba(213, 0, 249, 0.15)" },
  WEAPON: { stroke: "#ff1744", fill: "rgba(255, 23, 68, 0.25)" },
  UNKNOWN: { stroke: "#ffab00", fill: "rgba(255, 171, 0, 0.15)" },
};

export const VideoGrid: React.FC<VideoGridProps> = ({
  sensors,
  alerts,
  selectedSensor,
  onSelectSensor,
}) => {
  const [layout, setLayout] = useState<"1x1" | "2x2">("2x2");
  const [simulatedStreamDrop, setSimulatedStreamDrop] = useState<Record<string, boolean>>({});

  // Canvas refs for zero-copy 60 FPS HUD overlay rendering
  const canvasRefs = useRef<Record<string, HTMLCanvasElement | null>>({});
  const animFrameRefs = useRef<Record<string, number>>({});

  const displaySensors = layout === "1x1" && selectedSensor
    ? [selectedSensor]
    : sensors.slice(0, 4);

  // Synchronized canvas rendering loop using rAF / requestVideoFrameCallback
  useEffect(() => {
    displaySensors.forEach((sensor) => {
      const canvas = canvasRefs.current[sensor.id];
      if (!canvas) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      let active = true;

      const renderFrame = () => {
        if (!active) return;

        const width = canvas.width;
        const height = canvas.height;
        ctx.clearRect(0, 0, width, height);

        // Find active alert for this sensor
        const alert = alerts.find((a) => a.sensor_id === sensor.id);
        const bbox = alert?.bounding_box;

        if (bbox && !simulatedStreamDrop[sensor.id]) {
          const x1 = bbox.x1 * width;
          const y1 = bbox.y1 * height;
          const w = (bbox.x2 - bbox.x1) * width;
          const h = (bbox.y2 - bbox.y1) * height;

          const color = CLASS_COLORS[alert.target_type] || CLASS_COLORS.UNKNOWN;

          // 1. Draw target box
          ctx.strokeStyle = color.stroke;
          ctx.lineWidth = 2;
          ctx.fillStyle = color.fill;
          ctx.fillRect(x1, y1, w, h);
          ctx.strokeRect(x1, y1, w, h);

          // 2. Draw tactical corner brackets
          const bracketLen = 8;
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 1.5;

          // Top-left
          ctx.beginPath();
          ctx.moveTo(x1, y1 + bracketLen);
          ctx.lineTo(x1, y1);
          ctx.lineTo(x1 + bracketLen, y1);
          ctx.stroke();

          // Bottom-right
          ctx.beginPath();
          ctx.moveTo(x1 + w, y1 + h - bracketLen);
          ctx.lineTo(x1 + w, y1 + h);
          ctx.lineTo(x1 + w - bracketLen, y1 + h);
          ctx.stroke();

          // 3. Draw Track Label Tag
          const label = `#${bbox.track_id || 101} ${bbox.label || alert.target_type} [${Math.round(bbox.confidence * 100)}%]`;
          ctx.font = "bold 10px monospace";
          const textWidth = ctx.measureText(label).width;

          ctx.fillStyle = "rgba(0, 0, 0, 0.85)";
          ctx.fillRect(x1, y1 - 16, textWidth + 8, 16);
          ctx.strokeStyle = color.stroke;
          ctx.strokeRect(x1, y1 - 16, textWidth + 8, 16);

          ctx.fillStyle = color.stroke;
          ctx.fillText(label, x1 + 4, y1 - 4);

          // 4. Draw Ground Contact Point
          const groundX = x1 + w / 2;
          const groundY = y1 + h;
          ctx.beginPath();
          ctx.arc(groundX, groundY, 3.5, 0, Math.PI * 2);
          ctx.fillStyle = "#00e5ff";
          ctx.fill();
        }

        // Draw crosshair reticle in center
        ctx.strokeStyle = "rgba(0, 229, 255, 0.15)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(width / 2 - 10, height / 2);
        ctx.lineTo(width / 2 + 10, height / 2);
        ctx.moveTo(width / 2, height / 2 - 10);
        ctx.lineTo(width / 2, height / 2 + 10);
        ctx.stroke();

        animFrameRefs.current[sensor.id] = requestAnimationFrame(renderFrame);
      };

      animFrameRefs.current[sensor.id] = requestAnimationFrame(renderFrame);

      return () => {
        active = false;
        if (animFrameRefs.current[sensor.id]) {
          cancelAnimationFrame(animFrameRefs.current[sensor.id]);
        }
      };
    });
  }, [displaySensors, alerts, simulatedStreamDrop]);

  return (
    <div className="flex flex-col h-full bg-black border-t border-tactical-border overflow-hidden select-none">
      {/* Grid Controls Header */}
      <div className="h-9 bg-tactical-surface/90 border-b border-tactical-border px-3 flex items-center justify-between text-xs font-mono">
        <div className="flex items-center space-x-2">
          <Video className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-bold text-slate-200">ZERO-COPY SURVEILLANCE WALL</span>
          <span className="text-[10px] text-slate-400">({displaySensors.length} SYNCED CANVASES)</span>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setLayout("1x1")}
            className={`px-2 py-0.5 rounded text-[10px] flex items-center gap-1 ${
              layout === "1x1" ? "bg-cyan-600 text-white font-bold" : "bg-slate-800 text-slate-400 hover:text-white"
            }`}
          >
            <Maximize2 className="w-3 h-3" />
            <span>SOLO</span>
          </button>
          <button
            onClick={() => setLayout("2x2")}
            className={`px-2 py-0.5 rounded text-[10px] flex items-center gap-1 ${
              layout === "2x2" ? "bg-cyan-600 text-white font-bold" : "bg-slate-800 text-slate-400 hover:text-white"
            }`}
          >
            <Grid2X2 className="w-3 h-3" />
            <span>2X2 MATRIX</span>
          </button>
        </div>
      </div>

      {/* Grid Canvas Viewports */}
      <div className={`flex-1 grid ${layout === "2x2" ? "grid-cols-2 grid-rows-2" : "grid-cols-1 grid-rows-1"} gap-1 p-1 bg-[#04060d]`}>
        {displaySensors.map((sensor) => {
          const activeAlert = alerts.find((a) => a.sensor_id === sensor.id);
          const isSelected = selectedSensor?.id === sensor.id;
          const isDropped = simulatedStreamDrop[sensor.id];

          return (
            <div
              key={sensor.id}
              onClick={() => onSelectSensor(sensor)}
              className={`relative bg-[#070b16] border rounded overflow-hidden flex flex-col justify-between cursor-pointer group transition-all ${
                isSelected ? "border-cyan-400 ring-1 ring-cyan-400/50" : "border-slate-800 hover:border-slate-600"
              }`}
            >
              {/* Header Overlay */}
              <div className="p-2 bg-gradient-to-b from-black/90 to-transparent flex items-center justify-between text-[11px] font-mono z-20 pointer-events-none">
                <div className="flex items-center space-x-1.5 truncate">
                  <Camera className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
                  <span className="font-bold text-slate-100 truncate">{sensor.name}</span>
                </div>
                <div className="flex items-center space-x-2 text-[9px] flex-shrink-0">
                  <span className="px-1 py-0.2 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded font-semibold animate-pulse">
                    30 FPS HW
                  </span>
                  <span className="text-slate-400">{sensor.bop_sector_id}</span>
                </div>
              </div>

              {/* Zero-Copy Canvas HUD & Stream Failure Fallback Tile */}
              <div className="relative flex-1 flex items-center justify-center overflow-hidden">
                {isDropped ? (
                  /* Animated Stream Loss Fallback */
                  <div className="absolute inset-0 bg-rose-950/40 backdrop-blur-sm flex flex-col items-center justify-center z-20 font-mono text-center p-4">
                    <Radio className="w-8 h-8 text-rose-500 animate-pulse mb-2" />
                    <span className="text-xs font-bold text-rose-300 tracking-wider">
                      SIGNAL LOST // RE-ACQUIRING WEBRTC RTSP FEED...
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1">
                      ATTEMPTING MULTICAST FAILOVER (CODEC: H.264/NVDEC)
                    </span>
                  </div>
                ) : (
                  <>
                    {/* Simulated Camera Video Stream Base */}
                    <div className="absolute inset-0 opacity-20 bg-[radial-gradient(#00e5ff_1px,transparent_1px)] [background-size:20px_20px]" />
                    
                    {/* Zero-Copy HTML5 Canvas Overlay */}
                    <canvas
                      ref={(el) => {
                        canvasRefs.current[sensor.id] = el;
                      }}
                      width={640}
                      height={360}
                      className="w-full h-full object-contain absolute inset-0 z-10"
                    />
                  </>
                )}

                {/* Incursion Alert Flash Banner */}
                {activeAlert && !isDropped && (
                  <div className="absolute bottom-2 left-2 right-2 bg-rose-950/90 border border-rose-600 px-2 py-1 rounded flex items-center justify-between text-[10px] font-mono text-rose-200 z-20 animate-pulse shadow-lg">
                    <div className="flex items-center space-x-1.5">
                      <ShieldAlert className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                      <span className="font-bold">{activeAlert.threat_level}: {activeAlert.target_type} BREACH</span>
                    </div>
                    <span className="text-[9px] text-rose-300">
                      {new Date(activeAlert.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                )}
              </div>

              {/* Bottom Footer */}
              <div className="p-1.5 bg-black/90 flex items-center justify-between text-[9px] font-mono text-slate-400 border-t border-slate-900 z-20">
                <span>GPS: {sensor.gps.latitude.toFixed(4)}, {sensor.gps.longitude.toFixed(4)}</span>
                <span className="text-cyan-400">TRIPWIRE: ARMED</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
