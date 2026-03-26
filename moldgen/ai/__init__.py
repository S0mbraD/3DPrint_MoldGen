from moldgen.ai.agent_base import (
    AgentConfig,
    AgentContext,
    AgentEvent,
    AgentRole,
    BaseAgent,
    ExecutionMode,
    ThinkingStyle,
)
from moldgen.ai.execution_engine import AgentExecutionEngine
from moldgen.ai.memory import AgentMemoryManager
from moldgen.ai.tool_registry import ToolRegistry

__all__ = [
    "AgentConfig",
    "AgentContext",
    "AgentEvent",
    "AgentExecutionEngine",
    "AgentMemoryManager",
    "AgentRole",
    "BaseAgent",
    "ExecutionMode",
    "ThinkingStyle",
    "ToolRegistry",
    "ChatService",
    "ImageGenerator",
    "LocalModelManager",
    "MeshGenerator",
    "VisionAnalyzer",
]


def __getattr__(name: str):
    """Lazy imports for heavy modules to avoid import-time overhead."""
    lazy = {
        "ChatService": "moldgen.ai.chat",
        "ImageGenerator": "moldgen.ai.image_gen",
        "MeshGenerator": "moldgen.ai.model_gen",
        "VisionAnalyzer": "moldgen.ai.vision",
        "LocalModelManager": "moldgen.ai.local_models",
    }
    if name in lazy:
        import importlib
        mod = importlib.import_module(lazy[name])
        return getattr(mod, name)
    raise AttributeError(f"module 'moldgen.ai' has no attribute {name!r}")
