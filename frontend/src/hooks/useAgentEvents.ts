import { useCallback } from "react";
import { useAIStore, type AgentEventData } from "../stores/aiStore";
import { useWebSocket, type WSStatus } from "./useWebSocket";

export function useAgentEvents(enabled = true): {
  status: WSStatus;
  send: (data: unknown) => void;
} {
  const addLiveEvent = useAIStore((s) => s.addLiveEvent);

  const onMessage = useCallback(
    (data: unknown) => {
      const msg = data as { type?: string; event?: AgentEventData };
      if (msg?.type === "agent_event" && msg.event) {
        addLiveEvent(msg.event);
      }
    },
    [addLiveEvent],
  );

  return useWebSocket({
    url: "/ws/events",
    onMessage,
    autoReconnect: true,
    heartbeatInterval: 25000,
    enabled,
  });
}
