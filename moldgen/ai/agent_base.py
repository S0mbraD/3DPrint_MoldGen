"""BaseAgent 抽象基类 — 所有内置 Agent 的基础"""

from __future__ import annotations

import logging
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
class StepResult:
    step_name: str
    success: bool
    tool_calls: list[dict] = field(default_factory=list)
    output: Any = None
    error: str | None = None
    needs_confirmation: bool = False
    confirmation_message: str = ""

    def to_dict(self) -> dict:
        return {
            "step_name": self.step_name,
            "success": self.success,
            "tool_calls": self.tool_calls,
            "output": str(self.output)[:500] if self.output else None,
            "error": self.error,
            "needs_confirmation": self.needs_confirmation,
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

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "mold_id": self.mold_id,
            "gating_id": self.gating_id,
            "sim_id": self.sim_id,
            "material": self.material,
            "mode": self.mode.value,
            "n_messages": len(self.conversation),
        }


class BaseAgent(ABC):
    """所有内置 Agent 的抽象基类"""

    def __init__(self, role: AgentRole):
        self.role = role
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
        """Execute a tool through the registry."""
        if name not in self.get_available_tools():
            return ToolResult(
                success=False,
                error=f"Agent {self.role.value} cannot use tool {name}",
            )
        return await self.tool_registry.execute(name, **kwargs)
