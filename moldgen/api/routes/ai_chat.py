"""AI 聊天 API — 支持非流式 + SSE 流式对话"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from moldgen.ai.service_manager import AIServiceManager

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    model: str = "deepseek"
    history: list[dict] = []
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False


@router.post("/send")
async def send_chat_message(req: ChatRequest):
    """Send a message to AI and get a response (supports SSE streaming)."""
    from moldgen.ai.chat import ChatService
    svc = ChatService()

    messages = req.history + [{"role": "user", "content": req.message}]

    if req.stream:
        return StreamingResponse(
            _sse_stream(svc, messages, req),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await svc.chat(
        messages=messages,
        provider=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        system_prompt=req.system_prompt,
    )

    if result.success:
        return {
            "status": "ok",
            "data": {
                "content": result.content,
                "model": result.model,
                "provider": result.provider,
                "usage": result.usage,
            },
        }
    return {"status": "error", "message": result.error}


async def _sse_stream(svc, messages: list[dict], req: ChatRequest):
    try:
        async for token in svc.chat_stream(
            messages=messages,
            provider=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            system_prompt=req.system_prompt,
        ):
            payload = json.dumps({"token": token}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error("SSE stream error: %s", e)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@router.get("/status")
async def ai_status():
    """Return status of all configured AI services (including local models)."""
    mgr = AIServiceManager()
    status = mgr.get_status()
    return {
        "services": {
            "deepseek": {"configured": status.deepseek},
            "qwen": {"configured": status.qwen},
            "kimi": {"configured": status.kimi},
            "wanxiang": {"configured": status.wanxiang},
            "tripo3d": {"configured": status.tripo3d},
        },
        "local": {
            "image_loaded": status.local_image,
            "mesh_loaded": status.local_mesh,
        },
        "providers": {
            "image": status.image_provider,
            "mesh": status.mesh_provider,
        },
    }


@router.post("/test/{model}")
async def test_ai_connection(model: str):
    """Test connectivity to a specific AI model."""
    mgr = AIServiceManager()
    result = await mgr.test_connection(model)
    return result


@router.post("/optimize-prompt")
async def optimize_prompt(req: ChatRequest):
    """Optimize a user prompt for AI image/3D generation."""
    from moldgen.ai.chat import ChatService
    svc = ChatService()
    optimized = await svc.optimize_prompt(req.message)
    return {"status": "ok", "original": req.message, "optimized": optimized}
