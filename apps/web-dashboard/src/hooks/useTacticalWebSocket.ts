"use client";

import { useEffect, useRef, useState } from "react";
import type { SensorConfig, TacticalAlert } from "@ibvap/core-types";

interface UseTacticalWebSocketOptions {
  onAlertBatch?: (alerts: TacticalAlert[]) => void;
  onAlert?: (alert: TacticalAlert) => void;
  onSensorUpdate?: (sensor: SensorConfig) => void;
  maxRingBufferSize?: number;
}

export function useTacticalWebSocket(options: UseTacticalWebSocketOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const [latencyMs, setLatencyMs] = useState<number>(12);
  const [throughputMsgSec, setThroughputMsgSec] = useState<number>(0);

  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const onAlertBatchRef = useRef(options.onAlertBatch);
  const onAlertRef = useRef(options.onAlert);
  const onSensorRef = useRef(options.onSensorUpdate);

  onAlertBatchRef.current = options.onAlertBatch;
  onAlertRef.current = options.onAlert;
  onSensorRef.current = options.onSensorUpdate;

  // Animation-frame batching queues
  const pendingAlertsQueueRef = useRef<TacticalAlert[]>([]);
  const animationFrameIdRef = useRef<number | null>(null);
  const msgCounterRef = useRef<number>(0);
  const lastThroughputCalcRef = useRef<number>(Date.now());

  useEffect(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/v1/c2";
    let isMounted = true;

    // Animation frame flush loop for zero DOM-thrashing
    function scheduleFlush() {
      if (animationFrameIdRef.current !== null) return;

      animationFrameIdRef.current = requestAnimationFrame(() => {
        animationFrameIdRef.current = null;
        if (!isMounted) return;

        if (pendingAlertsQueueRef.current.length > 0) {
          const batch = pendingAlertsQueueRef.current.splice(0);
          if (onAlertBatchRef.current) {
            onAlertBatchRef.current(batch);
          } else if (onAlertRef.current) {
            batch.forEach((alert) => onAlertRef.current?.(alert));
          }
        }
      });
    }

    // Throughput calculation interval
    const throughputInterval = setInterval(() => {
      if (!isMounted) return;
      const now = Date.now();
      const elapsedSec = (now - lastThroughputCalcRef.current) / 1000;
      if (elapsedSec > 0) {
        setThroughputMsgSec(Math.round(msgCounterRef.current / elapsedSec));
        msgCounterRef.current = 0;
        lastThroughputCalcRef.current = now;
      }
    }, 1000);

    function connect() {
      try {
        const socket = new WebSocket(wsUrl);
        wsRef.current = socket;

        socket.onopen = () => {
          if (!isMounted) return;
          setIsConnected(true);
        };

        socket.onmessage = (event) => {
          if (!isMounted) return;
          msgCounterRef.current += 1;
          const tReceive = Date.now();

          try {
            const payload = JSON.parse(event.data);
            if (payload.timestamp) {
              const tSent = new Date(payload.timestamp).getTime();
              const delta = Math.max(1, tReceive - tSent);
              setLatencyMs(delta);
            }

            if (payload.event === "TACTICAL_ALERT" && payload.data) {
              const alert: TacticalAlert = payload.data;
              // Enqueue into rAF batch buffer
              pendingAlertsQueueRef.current.push(alert);
              // Cap batch queue to prevent unbounded growth during extreme spikes
              if (pendingAlertsQueueRef.current.length > 200) {
                pendingAlertsQueueRef.current = pendingAlertsQueueRef.current.slice(-200);
              }
              scheduleFlush();
            } else if (payload.event === "SENSOR_UPDATED" && payload.data) {
              const sensor: SensorConfig = payload.data;
              if (onSensorRef.current) onSensorRef.current(sensor);
            }
          } catch (e) {
            console.debug("WebSocket telemetry parse skipped:", e);
          }
        };

        socket.onclose = () => {
          if (!isMounted) return;
          setIsConnected(false);
          reconnectTimeoutRef.current = setTimeout(connect, 2000);
        };

        socket.onerror = () => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.close();
          }
        };
      } catch (err) {
        reconnectTimeoutRef.current = setTimeout(connect, 2500);
      }
    }

    connect();

    return () => {
      isMounted = false;
      clearInterval(throughputInterval);
      if (animationFrameIdRef.current) cancelAnimationFrame(animationFrameIdRef.current);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return { isConnected, latencyMs, throughputMsgSec };
}
