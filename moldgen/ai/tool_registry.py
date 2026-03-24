"""全局工具注册表 — 将软件功能映射为 Agent 可调用的工具"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolParam:
    name: str
    type: str  # "string" | "number" | "boolean" | "array" | "object"
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass
class ToolDef:
    name: str
    description: str
    category: str  # "model" | "mold" | "sim" | "insert" | "export" | "ai"
    parameters: list[ToolParam] = field(default_factory=list)
    handler: Callable | None = None
    requires_confirmation: bool = False

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI Function Calling compatible schema."""
        props = {}
        required = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            props[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    message: str = ""

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"success": self.success, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        if self.error:
            d["error"] = self.error
        return d


class ToolRegistry:
    """全局工具注册表 — 单例，管理所有 Agent 可调用工具"""

    _instance: ToolRegistry | None = None

    def __new__(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._tools: dict[str, ToolDef] = {}
        self._register_builtin_tools()

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s [%s]", tool.name, tool.category)

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_tools(self, category: str | None = None) -> list[ToolDef]:
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def list_categories(self) -> list[str]:
        return sorted({t.category for t in self._tools.values()})

    def get_openai_tools(self, category: str | None = None) -> list[dict]:
        return [t.to_openai_schema() for t in self.list_tools(category)]

    async def execute(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {name}")
        if not tool.handler:
            return ToolResult(success=False, error=f"Tool {name} has no handler")

        try:
            result = tool.handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            return ToolResult(success=True, data=result, message=f"Tool {name} executed")
        except Exception as e:
            logger.exception("Tool %s execution failed", name)
            return ToolResult(success=False, error=str(e))

    def _register_builtin_tools(self) -> None:
        self._register_model_tools()
        self._register_mold_tools()
        self._register_insert_tools()
        self._register_sim_tools()
        self._register_export_tools()
        logger.info("Registered %d built-in tools", len(self._tools))

    # ── Model Tools ──────────────────────────────────────────────────

    def _register_model_tools(self) -> None:
        self.register(ToolDef(
            name="model_load",
            description="加载3D模型文件（STL/OBJ/FBX/STEP等）",
            category="model",
            parameters=[
                ToolParam("file_path", "string", "模型文件路径"),
            ],
        ))
        self.register(ToolDef(
            name="model_quality_check",
            description="检查模型质量（水密性、退化面、法线一致性等）",
            category="model",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
            ],
        ))
        self.register(ToolDef(
            name="model_repair",
            description="自动修复模型（填孔、修复法线、去重复面等）",
            category="model",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
            ],
        ))
        self.register(ToolDef(
            name="model_simplify",
            description="简化模型面数",
            category="model",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("target_faces", "number", "目标面数", required=False),
                ToolParam("ratio", "number", "简化比例(0-1)", required=False, default=0.5),
            ],
        ))
        self.register(ToolDef(
            name="model_subdivide",
            description="细化模型网格",
            category="model",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("iterations", "number", "细分次数", required=False, default=1),
            ],
        ))
        self.register(ToolDef(
            name="model_transform",
            description="变换模型（平移/旋转/缩放/镜像/居中/落地）",
            category="model",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("operation", "string", "操作类型",
                         enum=["translate", "rotate", "scale", "mirror", "center", "align_to_floor"]),
                ToolParam("params", "object", "操作参数", required=False),
            ],
        ))
        self.register(ToolDef(
            name="model_boolean",
            description="布尔运算（并集/差集/交集）",
            category="model",
            parameters=[
                ToolParam("model_id_a", "string", "模型A的ID"),
                ToolParam("model_id_b", "string", "模型B的ID"),
                ToolParam("operation", "string", "布尔操作", enum=["union", "difference", "intersection"]),
            ],
            requires_confirmation=True,
        ))
        self.register(ToolDef(
            name="model_get_info",
            description="获取模型详细信息（面数、体积、尺寸等）",
            category="model",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
            ],
        ))

    # ── Mold Tools ───────────────────────────────────────────────────

    def _register_mold_tools(self) -> None:
        self.register(ToolDef(
            name="mold_analyze_orientation",
            description="分析模型最优脱模方向",
            category="mold",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("n_samples", "number", "Fibonacci采样数", required=False, default=100),
            ],
        ))
        self.register(ToolDef(
            name="mold_evaluate_direction",
            description="评估指定脱模方向的性能",
            category="mold",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("direction", "array", "方向向量 [x,y,z]"),
            ],
        ))
        self.register(ToolDef(
            name="mold_generate_parting",
            description="生成分型线和分型面",
            category="mold",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("direction", "array", "脱模方向 [x,y,z]", required=False),
            ],
        ))
        self.register(ToolDef(
            name="mold_build_two_part",
            description="生成双片壳模具",
            category="mold",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("direction", "array", "脱模方向", required=False),
                ToolParam("wall_thickness", "number", "壁厚(mm)", required=False, default=4.0),
                ToolParam("shell_type", "string", "壳体类型", required=False, enum=["box", "conformal"]),
            ],
        ))
        self.register(ToolDef(
            name="mold_build_multi_part",
            description="生成多片壳模具",
            category="mold",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("directions", "array", "多个脱模方向列表"),
                ToolParam("wall_thickness", "number", "壁厚(mm)", required=False, default=4.0),
            ],
            requires_confirmation=True,
        ))

    # ── Insert Tools ──────────────────────────────────────────────────

    def _register_insert_tools(self) -> None:
        self.register(ToolDef(
            name="insert_analyze_positions",
            description="分析支撑板最佳位置",
            category="insert",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("n_candidates", "number", "候选数量", required=False, default=5),
                ToolParam("organ_type", "string", "器官类型",
                         required=False, enum=["solid", "hollow", "tubular", "sheet", "general"]),
            ],
        ))
        self.register(ToolDef(
            name="insert_generate",
            description="生成支撑板（完整流程：位置分析→生成→锚固→验证）",
            category="insert",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("n_plates", "number", "支撑板数量", required=False, default=1),
                ToolParam("thickness", "number", "板厚(mm)", required=False, default=2.0),
                ToolParam("organ_type", "string", "器官类型", required=False),
                ToolParam("anchor_type", "string", "锚固类型",
                         required=False, enum=["mesh_holes", "bumps", "grooves", "dovetail", "diamond"]),
                ToolParam("mold_id", "string", "模具ID(用于定位槽)", required=False),
            ],
            requires_confirmation=True,
        ))
        self.register(ToolDef(
            name="insert_add_anchor",
            description="为支撑板添加/更换锚固结构",
            category="insert",
            parameters=[
                ToolParam("insert_id", "string", "支撑板结果ID"),
                ToolParam("plate_index", "number", "板索引", required=False, default=0),
                ToolParam("anchor_type", "string", "锚固类型",
                         enum=["mesh_holes", "bumps", "grooves", "dovetail", "diamond"]),
            ],
        ))
        self.register(ToolDef(
            name="insert_validate",
            description="验证支撑板装配可行性",
            category="insert",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("insert_id", "string", "支撑板结果ID"),
                ToolParam("mold_id", "string", "模具ID", required=False),
            ],
        ))
        self.register(ToolDef(
            name="insert_get_info",
            description="获取支撑板详细信息",
            category="insert",
            parameters=[
                ToolParam("insert_id", "string", "支撑板结果ID"),
            ],
        ))

    # ── Simulation Tools ─────────────────────────────────────────────

    def _register_sim_tools(self) -> None:
        self.register(ToolDef(
            name="sim_design_gating",
            description="设计浇注系统（浇口+排气孔）",
            category="sim",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("mold_id", "string", "模具ID"),
                ToolParam("material", "string", "材料名称", required=False, default="silicone_a30"),
            ],
        ))
        self.register(ToolDef(
            name="sim_run",
            description="运行灌注仿真",
            category="sim",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("gating_id", "string", "浇注系统ID"),
                ToolParam("material", "string", "材料名称", required=False, default="silicone_a30"),
                ToolParam("level", "number", "仿真级别(1=启发式,2=达西流)", required=False, default=1),
            ],
        ))
        self.register(ToolDef(
            name="sim_optimize",
            description="自动优化仿真参数",
            category="sim",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("mold_id", "string", "模具ID"),
                ToolParam("gating_id", "string", "浇注系统ID"),
                ToolParam("material", "string", "材料名称", required=False, default="silicone_a30"),
                ToolParam("max_iterations", "number", "最大迭代次数", required=False, default=5),
            ],
        ))
        self.register(ToolDef(
            name="sim_list_materials",
            description="列出所有可用材料",
            category="sim",
            parameters=[],
        ))

    # ── Export Tools ─────────────────────────────────────────────────

    def _register_export_tools(self) -> None:
        self.register(ToolDef(
            name="export_model",
            description="导出模型文件",
            category="export",
            parameters=[
                ToolParam("model_id", "string", "模型ID"),
                ToolParam("format", "string", "导出格式", enum=["stl", "obj", "ply", "glb", "3mf"]),
                ToolParam("output_dir", "string", "输出目录", required=False),
            ],
        ))
        self.register(ToolDef(
            name="export_mold_shells",
            description="导出模具所有壳体",
            category="export",
            parameters=[
                ToolParam("mold_id", "string", "模具ID"),
                ToolParam("format", "string", "导出格式", enum=["stl", "obj", "3mf"]),
            ],
        ))
