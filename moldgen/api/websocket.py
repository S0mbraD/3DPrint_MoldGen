"""WebSocket 处理 — 任务进度、仿真帧、Agent 事件实时流"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器 — 支持频道订阅和心跳"""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._heartbeat_interval: float = 30.0
        self._last_heartbeat: dict[int, float] = {}

    async def connect(self, websocket: WebSocket, channel: str = "default") -> None:
        await websocket.accept()
        self._connections.setdefault(channel, []).append(websocket)
        self._last_heartbeat[id(websocket)] = time.time()
        logger.info(
            "WS connected: channel=%s, total=%d",
            channel, len(self._connections[channel]),
        )

    def disconnect(self, websocket: WebSocket, channel: str = "default") -> None:
        conns = self._connections.get(channel, [])
        if websocket in conns:
            conns.remove(websocket)
        self._last_heartbeat.pop(id(websocket), None)
        logger.info("WS disconnected: channel=%s", channel)

    def disconnect_all(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from all channels."""
        ws_id = id(websocket)
        for conns in self._connections.values():
            if websocket in conns:
                conns.remove(websocket)
        self._last_heartbeat.pop(ws_id, None)

    async def send(self, channel: str, data: dict[str, Any]) -> None:
        message = json.dumps(data, ensure_ascii=False)
        conns = self._connections.get(channel, [])
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)

    async def broadcast(self, data: dict[str, Any]) -> None:
        for channel in list(self._connections.keys()):
            await self.send(channel, data)

    async def send_to_pattern(self, prefix: str, data: dict[str, Any]) -> None:
        """Send to all channels matching a prefix (e.g. 'agent:')."""
        for channel in list(self._connections.keys()):
            if channel.startswith(prefix):
                await self.send(channel, data)

    def get_stats(self) -> dict:
        return {
            "channels": {ch: len(conns) for ch, conns in self._connections.items() if conns},
            "total_connections": sum(len(c) for c in self._connections.values()),
        }


ws_manager = ConnectionManager()


async def ws_task_progress(websocket: WebSocket, task_id: str) -> None:
    """任务进度 WebSocket"""
    channel = f"task:{task_id}"
    await ws_manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
            else:
                logger.debug("WS task msg: %s", data[:200])
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, channel)


async def ws_ai_agent(websocket: WebSocket, task_id: str) -> None:
    """Agent 执行事件流 WebSocket — 实时推送 Agent 事件"""
    channel = f"agent:{task_id}"
    await ws_manager.connect(websocket, channel)

    from moldgen.ai.agent_base import AgentEvent

    async def event_listener(event: AgentEvent) -> None:
        await ws_manager.send(channel, {
            "type": "agent_event",
            "event": event.to_dict(),
        })

    engine = _get_engine()
    if engine:
        engine.add_event_listener(event_listener)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
            elif msg_type == "user_input":
                await ws_manager.send(channel, {
                    "type": "ack",
                    "message": "Input received",
                })
            elif msg_type == "subscribe":
                sub_channel = msg.get("channel", "")
                if sub_channel:
                    ws_manager._connections.setdefault(sub_channel, []).append(websocket)
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        if engine:
            engine.remove_event_listener(event_listener)
        ws_manager.disconnect(websocket, channel)


async def ws_ai_chat(websocket: WebSocket) -> None:
    """AI 对话流式 WebSocket — 支持心跳"""
    channel = "ai:chat"
    await ws_manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
            else:
                logger.debug("WS chat msg: %s", data[:200])
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, channel)


async def ws_global_events(websocket: WebSocket) -> None:
    """全局事件 WebSocket — 接收所有 Agent 事件、系统通知"""
    channel = "global"
    await ws_manager.connect(websocket, channel)

    from moldgen.ai.agent_base import AgentEvent

    async def global_listener(event: AgentEvent) -> None:
        await ws_manager.send(channel, {
            "type": "agent_event",
            "event": event.to_dict(),
        })

    engine = _get_engine()
    if engine:
        engine.add_event_listener(global_listener)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
    except WebSocketDisconnect:
        if engine:
            engine.remove_event_listener(global_listener)
        ws_manager.disconnect(websocket, channel)


def _get_engine():
    """Lazily get the global AgentExecutionEngine to avoid circular imports."""
    try:
        from moldgen.api.routes.ai_agent import _engine
        return _engine
    except ImportError:
        return None
