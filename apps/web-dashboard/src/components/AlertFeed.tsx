"use client";

import React, { useState } from "react";
import type { TacticalAlert, ThreatLevel } from "@ibvap/core-types";
import { AlertTriangle, ShieldAlert, CheckCircle2, FileCode, Hash, HardDrive } from "lucide-react";

interface AlertFeedProps {
  alerts: TacticalAlert[];
  onSelectAlert?: (alert: TacticalAlert) => void;
}

const threatBadgeStyles: Record<ThreatLevel, string> = {
  CRITICAL: "bg-rose-950/80 text-rose-300 border-rose-600 animate-pulse",
  HIGH: "bg-orange-950/80 text-orange-300 border-orange-600",
  MEDIUM: "bg-amber-950/80 text-amber-300 border-amber-600",
  LOW: "bg-blue-950/80 text-blue-300 border-blue-600",
  INFO: "bg-slate-800 text-slate-300 border-slate-600",
};

export const AlertFeed: React.FC<AlertFeedProps> = ({ alerts, onSelectAlert }) => {
  const [activeCotModal, setActiveCotModal] = useState<string | null>(null);

  return (
    <div className="flex flex-col h-full bg-tactical-surface border-l border-tactical-border">
      {/* Header */}
      <div className="p-3 border-b border-tactical-border flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <ShieldAlert className="w-4 h-4 text-rose-500" />
          <span className="font-bold text-xs tracking-wider text-slate-200 uppercase font-mono">
            TACTICAL INCIDENT LOG
          </span>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 bg-slate-900 border border-slate-700 rounded text-slate-400">
          {alerts.length} EVENTS
        </span>
      </div>

      {/* Feed list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-slate-500 text-xs font-mono">
            <CheckCircle2 className="w-8 h-8 mb-2 text-slate-600" />
            <span>SECTOR CLEAR // NO ACTIVE ALERTS</span>
          </div>
        ) : (
          alerts.map((alert) => {
            const badgeClass = threatBadgeStyles[alert.threat_level] || threatBadgeStyles.INFO;

            return (
              <div
                key={alert.alert_id}
                onClick={() => onSelectAlert && onSelectAlert(alert)}
                className="p-3 bg-slate-900/90 border border-slate-800 hover:border-cyan-500/50 rounded transition-all cursor-pointer font-mono text-xs"
              >
                {/* Top Row: Threat Level & Timestamp */}
                <div className="flex items-center justify-between mb-1.5">
                  <span className={`text-[10px] font-bold px-2 py-0.5 border rounded ${badgeClass}`}>
                    {alert.threat_level} // {alert.target_type}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </span>
                </div>

                {/* Description */}
                <div className="text-slate-200 text-xs mb-2 font-sans font-medium">
                  {alert.description || `Target detected in restricted perimeter.`}
                </div>

                {/* Centroid coordinates & sector */}
                <div className="text-[10px] text-slate-400 flex items-center justify-between border-t border-slate-800/80 pt-1.5 mb-1.5">
                  <span>BOP: {alert.bop_id}</span>
                  <span>
                    GPS: {alert.centroid.latitude.toFixed(4)}, {alert.centroid.longitude.toFixed(4)}
                  </span>
                </div>

                {/* Cryptographic Merkle Hash & IPFS CID */}
                <div className="space-y-1 bg-black/40 p-1.5 rounded text-[9px] text-slate-400">
                  <div className="flex items-center space-x-1 truncate">
                    <Hash className="w-3 h-3 text-cyan-400 flex-shrink-0" />
                    <span className="text-slate-500">MERKLE:</span>
                    <span className="text-cyan-300 truncate font-mono">{alert.merkle_leaf_hash}</span>
                  </div>
                  <div className="flex items-center space-x-1 truncate">
                    <HardDrive className="w-3 h-3 text-amber-400 flex-shrink-0" />
                    <span className="text-slate-500">IPFS CID:</span>
                    <span className="text-amber-300 truncate font-mono">{alert.evidence_cid}</span>
                  </div>
                </div>

                {/* CoT XML Inspector Action */}
                <div className="mt-2 flex justify-end">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setActiveCotModal(alert.cot_xml_string);
                    }}
                    className="flex items-center space-x-1 text-[10px] text-slate-400 hover:text-cyan-300 underline"
                  >
                    <FileCode className="w-3 h-3" />
                    <span>View CoT XML</span>
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Modal for Cursor-on-Target XML inspection */}
      {activeCotModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded max-w-2xl w-full p-4 font-mono text-xs shadow-2xl">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800 mb-3">
              <span className="font-bold text-cyan-400">MIL-STD CURSOR-ON-TARGET (CoT) XML</span>
              <button
                onClick={() => setActiveCotModal(null)}
                className="text-slate-400 hover:text-white px-2 py-1 bg-slate-800 rounded"
              >
                CLOSE
              </button>
            </div>
            <pre className="bg-black/60 p-3 rounded text-[11px] text-emerald-400 overflow-x-auto max-h-96 whitespace-pre-wrap">
              {activeCotModal}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};
