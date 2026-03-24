"""API 路由注册"""

from fastapi import APIRouter

from moldgen.api.routes import ai_agent, ai_chat, export, inserts, models, molds, simulation, system

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(molds.router, prefix="/molds", tags=["molds"])
api_router.include_router(simulation.router, prefix="/simulation", tags=["simulation"])
api_router.include_router(inserts.router, prefix="/inserts", tags=["inserts"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(ai_chat.router, prefix="/ai/chat", tags=["ai-chat"])
api_router.include_router(ai_agent.router, prefix="/ai/agent", tags=["ai-agent"])
