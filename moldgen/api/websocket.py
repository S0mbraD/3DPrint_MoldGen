"""WebSocket 处理 — 任务进度、仿真帧、Agent 事件流"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str = "default") -> None:
        await websocket.accept()
        self._connections.setdefault(channel, []).append(websocket)
        logger.info("WS connected: channel=%s, total=%d", channel, len(self._connections[channel]))

    def disconnect(self, websocket: WebSocket, channel: str = "default") -> None:
        conns = self._connections.get(channel, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info("WS disconnected: channel=%s", channel)

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
        for channel in self._connections:
            await self.send(channel, data)


ws_manager = ConnectionManager()


async def ws_task_progress(websocket: WebSocket, task_id: str) -> None:
    """任务进度 WebSocket"""
    await ws_manager.connect(websocket, f"task:{task_id}")
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug("WS task msg: %s", data[:200])
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, f"task:{task_id}")


async def ws_ai_agent(websocket: WebSocket, task_id: str) -> None:
    """Agent 执行事件流 WebSocket"""
    await ws_manager.connect(websocket, f"agent:{task_id}")
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "user_input":
                await ws_manager.send(
                    f"agent:{task_id}",
                    {"type": "ack", "message": "Input received"},
                )
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, f"agent:{task_id}")


async def ws_ai_chat(websocket: WebSocket) -> None:
    """AI 对话流式 WebSocket"""
    await ws_manager.connect(websocket, "ai:chat")
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug("WS chat msg: %s", data[:200])
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "ai:chat")
