---
name: moldgen-agent-dev
description: >-
  Develop and extend MoldGen's built-in Agent system. Use when creating new agents,
  adding tools to the registry, modifying agent routing, updating execution pipelines,
  or working with moldgen/ai/ files.
---

# MoldGen Agent System Development

## Architecture

```
moldgen/ai/
├── agent_base.py       # BaseAgent ABC, AgentConfig, AgentContext, AgentEvent, StepResult
├── execution_engine.py # AgentExecutionEngine, PlanStep, ExecutionPlan, PIPELINE_TEMPLATES
├── tool_registry.py    # ToolRegistry singleton, ToolDef, ToolParam, ToolResult
├── memory.py           # ShortTermMemory, LongTermMemory, AgentMemoryManager
├── service_manager.py  # AIServiceManager — unified AI API access
├── chat.py             # Chat completion logic
├── agents/
│   ├── master_agent.py  # MasterAgent — intent routing + LLM reasoning + self-reflection
│   ├── model_agent.py   # ModelAgent — mesh import/repair/edit
│   ├── mold_agent.py    # MoldDesignAgent — orientation/parting/shells
│   ├── insert_agent.py  # InsertAgent — support plate design
│   ├── simopt_agent.py  # SimOptAgent — simulation + optimization
│   └── creative_agent.py# CreativeAgent — AI image/3D generation
└── prompts/             # System prompt templates for each agent
```

## Adding a New Agent

1. Create `moldgen/ai/agents/your_agent.py`:
   - Subclass `BaseAgent` from `agent_base.py`
   - Implement: `name`, `description`, `system_prompt`, `get_available_tools()`, `execute()`
   - Use `self.call_tool(name, **kwargs)` for tool execution (has built-in retry)
   - Use `self.emit_event(type, data)` for real-time event tracking

2. Add `AgentRole` enum value in `agent_base.py`

3. Register in `moldgen/ai/agents/__init__.py`

4. Register in `moldgen/api/routes/ai_agent.py` (add to `_engine.register_agent(...)`)

5. Add routing keywords in `master_agent.py` `KEYWORD_ROUTES`

## Adding a New Tool

Register in `ToolRegistry._register_builtin_tools()`:

```python
self.register(ToolDef(
    name="tool_name",
    description="工具描述",
    category="model|mold|insert|sim|export|ai",
    parameters=[
        ToolParam("param_name", "string|number|boolean|array|object", "描述", required=True),
    ],
    handler=actual_function,  # async or sync
    requires_confirmation=False,
))
```

## Thinking Styles

- `ThinkingStyle.FAST`: Keyword matching only, no LLM calls
- `ThinkingStyle.BALANCED`: LLM classification with keyword fallback
- `ThinkingStyle.DEEP`: Chain-of-thought reasoning + self-reflection + fallback

## Key Patterns

- All agents share `AgentContext` for cross-agent state (model_id, mold_id, etc.)
- `AgentConfig` controls per-agent behavior (retries, temperature, timeouts)
- `AgentMemoryManager` provides short-term (session) and long-term (persisted) memory
- Events (`AgentEvent`) enable real-time UI updates via WebSocket
- API routes at `/api/v1/ai/agent/` expose config, memory, history, execution
