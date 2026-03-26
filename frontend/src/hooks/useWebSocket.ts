import { useCallback, useEffect, useRef, useState } from "react";

export type WSStatus = "connecting" | "connected" | "disconnected" | "reconnecting";

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  autoReconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
  enabled?: boolean;
}

export function useWebSocket({
  url,
  onMessage,
  onConnect,
  onDisconnect,
  autoReconnect = true,
  reconnectInterval = 3000,
  maxReconnectAttempts = 20,
  heartbeatInterval = 25000,
  enabled = true,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const [status, setStatus] = useState<WSStatus>("disconnected");

  const cleanup = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = undefined;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = undefined;
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    cleanup();
    setStatus("connecting");

    const wsUrl = url.startsWith("ws")
      ? url
      : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}${url}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("connected");
      reconnectAttemptsRef.current = 0;
      onConnect?.();

      heartbeatTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, heartbeatInterval);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "pong") return;
        onMessage?.(data);
      } catch {
        onMessage?.(event.data);
      }
    };

    ws.onclose = () => {
      cleanup();
      setStatus("disconnected");
      onDisconnect?.();

      if (autoReconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
        const delay = Math.min(
          reconnectInterval * Math.pow(1.5, reconnectAttemptsRef.current),
          30000,
        );
        setStatus("reconnecting");
        reconnectTimerRef.current = setTimeout(() => {
          reconnectAttemptsRef.current += 1;
          connect();
        }, delay);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [url, onMessage, onConnect, onDisconnect, autoReconnect, reconnectInterval, maxReconnectAttempts, heartbeatInterval, cleanup]);

  const disconnect = useCallback(() => {
    cleanup();
    reconnectAttemptsRef.current = maxReconnectAttempts;
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("disconnected");
  }, [cleanup, maxReconnectAttempts]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === "string" ? data : JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    if (enabled) {
      connect();
    }
    return () => {
      cleanup();
      reconnectAttemptsRef.current = maxReconnectAttempts;
      wsRef.current?.close();
    };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  return { status, send, connect, disconnect };
}
