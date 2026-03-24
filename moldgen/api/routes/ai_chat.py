"""AI 聊天 API"""

from fastapi import APIRouter
from pydantic import BaseModel

from moldgen.ai.service_manager import AIServiceManager

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    model: str = "deepseek"
    history: list[dict] = []


@router.post("/send")
async def send_chat_message(req: ChatRequest):
    """Send a message to AI and get a response."""
    mgr = AIServiceManager()
    messages = req.history + [{"role": "user", "content": req.message}]
    try:
        result = await mgr.chat_completion(messages=messages, model=req.model)
        return {"status": "ok", "data": result}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"AI service error: {e}"}


@router.get("/status")
async def ai_status():
    """Return status of all configured AI services."""
    mgr = AIServiceManager()
    status = mgr.get_status()
    return {
        "services": {
            "deepseek": {"configured": status.deepseek},
            "qwen": {"configured": status.qwen},
            "kimi": {"configured": status.kimi},
            "wanxiang": {"configured": status.wanxiang},
            "tripo3d": {"configured": status.tripo3d},
        }
    }


@router.post("/test/{model}")
async def test_ai_connection(model: str):
    """Test connectivity to a specific AI model."""
    mgr = AIServiceManager()
    result = await mgr.test_connection(model)
    return result
