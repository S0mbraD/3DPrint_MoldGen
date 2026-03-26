"""BaseAgent 抽象基类 — 所有内置 Agent 的基础"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from moldgen.ai.tool_registry import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


class AgentRole(StrEnum):
    MASTER = "master"
    MODEL = "model"
    MOLD = "mold"
    INSERT = "insert"
    SIM = "sim"
    CREATIVE = "creative"


class ExecutionMode(StrEnum):
    AUTO = "auto"
    SEMI_AUTO = "semi_auto"
    STEP_BY_STEP = "step"


class ThinkingStyle(StrEnum):
    """Agent 思考风格 — 影响推理链深度和行为"""
    FAST = "fast"          # 快速关键字匹配，不使用 LLM
    BALANCED = "balanced"  # 简单 LLM 推理 + 关键字兜底
    DEEP = "deep"          # 深度 CoT 推理，带自省和多步计划


@dataclass
class AgentConfig:
    """每个 Agent 的运行时配置"""
    enabled: bool = True
    default_mode: ExecutionMode = ExecutionMode.SEMI_AUTO
    thinking_style: ThinkingStyle = ThinkingStyle.BALANCED
    max_retries: int = 2
    retry_delay: float = 1.0
    auto_confirm_threshold: float = 0.85
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout_seconds: float = 120.0
    enable_memory: bool = True
    enable_self_reflection: bool = True
    verbose_logging: bool = False

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "default_mode": self.default_mode.value,
            "thinking_style": self.thinking_style.value,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "auto_confirm_threshold": self.auto_confirm_threshold,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "enable_memory": self.enable_memory,
            "enable_self_reflection": self.enable_self_reflection,
            "verbose_logging": self.verbose_logging,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AgentConfig:
        cfg = cls()
        if "enabled" in d:
            cfg.enabled = bool(d["enabled"])
        if "default_mode" in d:
            cfg.default_mode = ExecutionMode(d["default_mode"])
        if "thinking_style" in d:
            cfg.thinking_style = ThinkingStyle(d["thinking_style"])
        if "max_retries" in d:
            cfg.max_retries = int(d["max_retries"])
        if "retry_delay" in d:
            cfg.retry_delay = float(d["retry_delay"])
        if "auto_confirm_threshold" in d:
            cfg.auto_confirm_threshold = float(d["auto_confirm_threshold"])
        if "temperature" in d:
            cfg.temperature = float(d["temperature"])
        if "max_tokens" in d:
            cfg.max_tokens = int(d["max_tokens"])
        if "timeout_seconds" in d:
            cfg.timeout_seconds = float(d["timeout_seconds"])
        if "enable_memory" in d:
            cfg.enable_memory = bool(d["enable_memory"])
        if "enable_self_reflection" in d:
            cfg.enable_self_reflection = bool(d["enable_self_reflection"])
        if "verbose_logging" in d:
            cfg.verbose_logging = bool(d["verbose_logging"])
        return cfg


@dataclass
class AgentMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_name:
            d["tool_name"] = self.tool_name
        return d


@dataclass
class AgentEvent:
    """Agent 执行过程中的实时事件"""
    event_type: str  # thinking | tool_call | tool_result | decision | error | progress | confirm_request
    agent_role: str
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "agent_role": self.agent_role,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class StepResult:
    step_name: str
    success: bool
    tool_calls: list[dict] = field(default_factory=list)
    output: Any = None
    error: str | None = None
    needs_confirmation: bool = False
    confirmation_message: str = ""
    thinking: str = ""
    events: list[AgentEvent] = field(default_factory=list)
    retries_used: int = 0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "step_name": self.step_name,
            "success": self.success,
            "tool_calls": self.tool_calls,
            "output": str(self.output)[:500] if self.output else None,
            "error": self.error,
            "needs_confirmation": self.needs_confirmation,
            "thinking": self.thinking[:300] if self.thinking else None,
            "events": [e.to_dict() for e in self.events[-10:]],
            "retries_used": self.retries_used,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


@dataclass
class AgentContext:
    """Shared execution context across agents."""
    model_id: str | None = None
    mold_id: str | None = None
    gating_id: str | None = None
    sim_id: str | None = None
    direction: list[float] | None = None
    material: str = "silicone_a30"
    mode: ExecutionMode = ExecutionMode.AUTO
    conversation: list[AgentMessage] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)
    user_preferences: dict[str, Any] = field(default_factory=dict)
    memory_context: str = ""

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "mold_id": self.mold_id,
            "gating_id": self.gating_id,
            "sim_id": self.sim_id,
            "material": self.material,
            "mode": self.mode.value,
            "n_messages": len(self.conversation),
            "has_memory": bool(self.memory_context),
        }


class BaseAgent(ABC):
    """所有内置 Agent 的抽象基类"""

    def __init__(self, role: AgentRole, config: AgentConfig | None = None):
        self.role = role
        self.config = config or AgentConfig()
        self.tool_registry = ToolRegistry()
        self.logger = logging.getLogger(f"agent.{role.value}")

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        ...

    @abstractmethod
    def get_available_tools(self) -> list[str]:
        """Return list of tool names this agent can use."""
        ...

    @abstractmethod
    async def execute(self, task: str, context: AgentContext) -> StepResult:
        """Execute a task with the given context."""
        ...

    def get_tool_schemas(self) -> list[dict]:
        """Get OpenAI-compatible tool schemas for this agent's tools."""
        schemas = []
        for name in self.get_available_tools():
            tool = self.tool_registry.get(name)
            if tool:
                schemas.append(tool.to_openai_schema())
        return schemas

    async def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        """Execute a tool through the registry with retry support."""
        if name not in self.get_available_tools():
            return ToolResult(
                success=False,
                error=f"Agent {self.role.value} cannot use tool {name}",
            )

        last_error: str | None = None
        for attempt in range(1 + self.config.max_retries):
            result = await self.tool_registry.execute(name, **kwargs)
            if result.success:
                return result
            last_error = result.error
            if attempt < self.config.max_retries:
                self.logger.warning(
                    "Tool %s failed (attempt %d/%d): %s, retrying...",
                    name, attempt + 1, self.config.max_retries + 1, result.error,
                )
                import asyncio
                await asyncio.sleep(self.config.retry_delay)

        return ToolResult(success=False, error=f"After {self.config.max_retries + 1} attempts: {last_error}")

    def emit_event(self, event_type: str, data: dict | None = None) -> AgentEvent:
        """Create an execution event for real-time tracking."""
        event = AgentEvent(
            event_type=event_type,
            agent_role=self.role.value,
            data=data or {},
        )
        if self.config.verbose_logging:
            self.logger.debug("Event [%s]: %s", event_type, data)
        return event

    def get_full_info(self) -> dict:
        """Complete agent info including config."""
        return {
            "role": self.role.value,
            "name": self.name,
            "description": self.description,
            "tools": self.get_available_tools(),
            "config": self.config.to_dict(),
        }
