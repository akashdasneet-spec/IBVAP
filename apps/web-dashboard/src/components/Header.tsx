"use client";

import React from "react";
import { Shield, Radio, Server, Activity, Database } from "lucide-react";

interface HeaderProps {
  wsConnected: boolean;
  activeSensorsCount: number;
  alertCount: number;
}

export const Header: React.FC<HeaderProps> = ({ wsConnected, activeSensorsCount, alertCount }) => {
  return (
    <header className="h-14 bg-tactical-surface border-b border-tactical-border px-4 flex items-center justify-between z-20">
      <div className="flex items-center space-x-3">
        <div className="p-2 bg-cyan-950/60 border border-tactical-accent/40 rounded">
          <Shield className="w-5 h-5 text-tactical-accent" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-sm tracking-wider text-slate-100">IBVAP DEFENSE C2</span>
            <span className="text-[10px] px-1.5 py-0.5 bg-cyan-950 text-cyan-400 border border-cyan-800 rounded font-mono">
              v1.0-PROD
            </span>
          </div>
          <p className="text-[10px] text-slate-400 font-mono">SECTOR ALPHA-01 // TACTICAL SURVEILLANCE MESH</p>
        </div>
      </div>

      <div className="flex items-center space-x-6 text-xs font-mono">
        {/* Status indicator */}
        <div className="flex items-center space-x-2">
          <Radio className={`w-4 h-4 ${wsConnected ? "text-emerald-400 animate-pulse" : "text-rose-500"}`} />
          <span className="text-slate-300">C2 LINK:</span>
          <span className={wsConnected ? "text-emerald-400 font-semibold" : "text-rose-500 font-semibold"}>
            {wsConnected ? "ONLINE (TLS)" : "DISCONNECTED"}
          </span>
        </div>

        {/* PyTAK status */}
        <div className="flex items-center space-x-2">
          <Server className="w-4 h-4 text-cyan-400" />
          <span className="text-slate-300">ATAK MESH:</span>
          <span className="text-cyan-400 font-semibold">MULTICAST 239.2.3.1</span>
        </div>

        {/* IPFS status */}
        <div className="flex items-center space-x-2">
          <Database className="w-4 h-4 text-amber-400" />
          <span className="text-slate-300">IPFS PROOF:</span>
          <span className="text-amber-400 font-semibold">KUBO LOCAL</span>
        </div>

        {/* Active Sensors badge */}
        <div className="px-2.5 py-1 bg-slate-900 border border-slate-700 rounded flex items-center space-x-2">
          <Activity className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-slate-400">SENSORS:</span>
          <span className="text-slate-100 font-bold">{activeSensorsCount}</span>
        </div>
      </div>
    </header>
  );
};
