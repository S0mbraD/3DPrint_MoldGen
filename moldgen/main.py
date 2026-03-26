"""MoldGen FastAPI 入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from moldgen import __version__
from moldgen.api.routes import api_router
from moldgen.api.websocket import ws_ai_agent, ws_ai_chat, ws_global_events, ws_task_progress
from moldgen.config import get_config
from moldgen.utils.logger import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    logger.info("MoldGen v%s starting...", __version__)
    logger.info("Data dir: %s", config.data_dir.resolve())

    from moldgen.gpu.device import GPUDevice

    gpu = GPUDevice()
    info = gpu.info
    if info.available:
        logger.info(
            "GPU: %s | VRAM: %d MB | Numba: %s | CuPy: %s",
            info.device_name,
            info.vram_total_mb,
            info.numba_cuda,
            info.cupy_available,
        )
    else:
        logger.warning("No GPU detected — running in CPU-only mode")

    ai = config.ai
    ai_status = {
        "DeepSeek": bool(ai.deepseek_api_key),
        "Qwen": bool(ai.qwen_api_key),
        "Kimi": bool(ai.kimi_api_key),
        "Tripo3D": bool(ai.tripo_api_key),
    }
    configured = [k for k, v in ai_status.items() if v]
    if configured:
        logger.info("AI services configured: %s", ", ".join(configured))
    else:
        logger.warning("No AI API keys configured")

    from moldgen.ai.tool_handlers import wire_handlers

    n_wired = wire_handlers()
    logger.info("Tool handlers wired: %d", n_wired)

    logger.info("API docs: http://%s:%d/docs", config.host, config.port)

    yield

    logger.info("MoldGen shutting down...")


def create_app() -> FastAPI:
    setup_logging("INFO")
    config = get_config()
    config.ensure_dirs()

    app = FastAPI(
        title="MoldGen",
        description="AI 驱动的医学教具智能模具生成工作站",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.websocket("/ws/task/{task_id}")
    async def ws_task(websocket: WebSocket, task_id: str):
        await ws_task_progress(websocket, task_id)

    @app.websocket("/ws/ai/chat")
    async def ws_chat(websocket: WebSocket):
        await ws_ai_chat(websocket)

    @app.websocket("/ws/ai/agent/{task_id}")
    async def ws_agent(websocket: WebSocket, task_id: str):
        await ws_ai_agent(websocket, task_id)

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket):
        await ws_global_events(websocket)

    app.mount("/static/uploads", StaticFiles(directory=str(config.upload_dir)), name="uploads")

    return app


app = create_app()


def main():
    import uvicorn

    config = get_config()
    uvicorn.run(
        "moldgen.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
