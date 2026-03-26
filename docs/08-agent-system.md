# 内置 Agent 系统设计

## 1. 设计理念

MoldGen 的内置 Agent 不只是聊天助手——它们是**具有自主执行能力的智能操作员**，能直接调用软件内部所有功能模块，完成从模型处理到模具导出的全链路自动化操作。

### 1.1 核心原则

- **自主执行**：Agent 可以在用户授权范围内自动执行完整工作流，无需逐步确认
- **分工协作**：多个专业 Agent 各司其职，由总控 Agent 调度协作
- **人机协同**：关键决策节点请求用户确认，非关键操作静默执行
- **全功能覆盖**：Agent 可访问软件内所有功能——模型处理、模具生成、仿真、导出等
- **可观测**：所有 Agent 操作在工作站面板实时可见，用户可随时介入

### 1.2 Agent 与软件功能的关系

```
传统软件:  用户 ──→ UI 按钮/参数 ──→ 功能模块
Agent 模式: 用户 ──→ 自然语言描述 ──→ Agent ──→ 功能模块
                                       ↑
                                  自主决策/规划/执行
```

## 2. 内置 Agent 体系

### 2.1 Agent 总览

```
┌─────────────────────────────────────────────────────────────────┐
│                     MasterAgent (总控Agent)                      │
│  意图识别 │ 任务规划 │ Agent路由 │ 进度管理 │ 异常处理            │
└────────┬──────────┬──────────┬──────────┬──────────┬────────────┘
         │          │          │          │          │
    ┌────▼────┐ ┌───▼────┐ ┌──▼───┐ ┌───▼────┐ ┌───▼────┐
    │ModelAgent│ │MoldAgent│ │Insert│ │SimAgent│ │Creative│
    │模型处理  │ │模具设计  │ │Agent │ │仿真优化 │ │Agent   │
    │         │ │         │ │支撑板 │ │        │ │创意生成 │
    └────┬────┘ └───┬────┘ └──┬───┘ └───┬────┘ └───┬────┘
         │          │          │          │          │
    ┌────▼──────────▼──────────▼──────────▼──────────▼────┐
    │              Tool Layer (工具层)                       │
    │  mesh_io │ mesh_repair │ mesh_editor │ orientation   │
    │  parting │ mold_builder│ insert_gen  │ gating        │
    │  flow_sim│ optimizer   │ export      │ ai_image/3d   │
    └─────────────────────────────────────────────────────┘
```

### 2.2 六大内置 Agent

| Agent | 职责 | 自动执行能力 | 人机确认点 |
|-------|------|------------|-----------|
| **MasterAgent** | 意图识别、任务规划、Agent 路由调度 | 规划全自动 | 任务开始确认 |
| **ModelAgent** | 模型导入、修复、细化/简化、编辑 | 修复/简化全自动 | 布尔运算前确认 |
| **MoldDesignAgent** | 方向分析、分型面、壳体、浇注系统 | 全流程可全自动 | 方向选择、片数确认 |
| **InsertAgent** | 支撑板位置分析、生成、锚固结构 | 方案生成自动 | 方案确认后生成 |
| **SimOptAgent** | 灌注仿真、缺陷检测、自动优化 | 仿真+优化全自动 | 优化结果审查 |
| **CreativeAgent** | 图像生成、3D模型生成、需求转化 | 生成全自动 | 选择确认 |

## 3. 各 Agent 详细设计

### 3.1 MasterAgent — 总控调度

**角色**：所有用户请求的第一入口，负责理解意图并分配给专业 Agent。

```python
class MasterAgent:
    """
    总控 Agent — 意图路由 + 任务编排 + 多Agent协调
    """
    
    SYSTEM_PROMPT = """
    你是 MoldGen 的总控 Agent。你的职责是：
    1. 理解用户的意图
    2. 将任务分解为子步骤
    3. 将子步骤分配给合适的专业 Agent
    4. 监控执行进度并协调多 Agent 协作
    5. 处理异常和降级
    
    你可以调度以下专业 Agent：
    - ModelAgent: 模型导入/修复/编辑/细化/简化
    - MoldDesignAgent: 脱模分析/分型面/模具壳体/浇注系统
    - InsertAgent: 支撑板设计/锚固结构/装配验证
    - SimOptAgent: 灌注仿真/缺陷检测/自动优化
    - CreativeAgent: AI图像生成/AI 3D模型生成
    
    决策规则：
    - 简单单步任务 → 直接路由到对应 Agent
    - 复杂多步任务 → 制定执行计划 → 按顺序调度
    - "从零开始做一个XX模型" → 完整流水线: Creative→Model→Mold→Insert→Sim→Export
    - 用户说"自动完成" → 全自动模式（仅关键节点确认）
    - 用户说"一步步来" → 逐步确认模式
    """
    
    ROUTING_TOOLS = [
        {
            "name": "dispatch_to_agent",
            "description": "将子任务分配给专业Agent执行",
            "parameters": {
                "agent": {"type": "string", "enum": ["model","mold","insert","sim","creative"]},
                "task": {"type": "string"},
                "auto_execute": {"type": "boolean", "description": "是否自动执行无需逐步确认"},
                "params": {"type": "object"}
            }
        },
        {
            "name": "create_execution_plan",
            "description": "为复杂任务创建多步骤执行计划",
            "parameters": {
                "steps": {
                    "type": "array",
                    "items": {
                        "agent": {"type": "string"},
                        "task": {"type": "string"},
                        "depends_on": {"type": "array", "items": {"type": "integer"}},
                        "auto_execute": {"type": "boolean"}
                    }
                }
            }
        },
        {
            "name": "ask_user",
            "description": "需要用户做出选择或确认时调用",
            "parameters": {
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "allow_free_text": {"type": "boolean"}
            }
        }
    ]
```

**意图路由示例**：

| 用户输入 | 识别意图 | 路由目标 | 执行模式 |
|---------|---------|---------|---------|
| "导入这个STL文件" | 模型导入 | ModelAgent | 自动 |
| "把模型简化到5万面" | 模型编辑 | ModelAgent | 自动 |
| "分析最佳脱模方向" | 模具设计 | MoldDesignAgent | 自动 |
| "生成模具" | 模具设计(全流程) | MoldDesignAgent | 半自动 |
| "添加支撑板" | 支撑板设计 | InsertAgent | 半自动 |
| "运行仿真并优化" | 仿真+优化 | SimOptAgent | 自动 |
| "做一个肝脏教学模型" | 完整流水线 | Master编排→全部Agent | 逐步确认 |
| "自动完成剩下所有步骤" | 全自动续行 | Master编排→剩余Agent | 全自动 |
| "帮我生成一张心脏参考图" | AI生成 | CreativeAgent | 自动 |
| "导出所有模具文件" | 导出 | ModelAgent(export) | 自动 |

### 3.2 ModelAgent — 模型处理

```python
class ModelAgent:
    """模型处理 Agent — 导入/修复/编辑/细化/简化"""
    
    SYSTEM_PROMPT = """
    你是 MoldGen 的模型处理专家。你负责 3D 模型的全部处理工作。
    
    自动执行规则：
    - 导入文件 → 自动执行，完成后报告模型信息
    - 网格修复 → 自动执行（先检查质量，有问题才修复），报告修复内容
    - 细化/简化 → 按用户指定参数自动执行
    - 布尔运算 → 执行前向用户展示预览，确认后执行
    - 多个操作连续执行时，中间结果静默处理，只报告最终结果
    
    智能决策：
    - 导入后自动检查网格质量，如有问题自动修复（无需用户指令）
    - 面片数>500K时自动建议简化（仿真用途不需要超高精度）
    - 检测到非流形时自动修复并提示用户
    """
    
    TOOLS = [
        "load_model",           # 加载模型文件
        "check_mesh_quality",   # 检查网格质量
        "repair_mesh",          # 修复网格
        "subdivide_mesh",       # 细化(Loop/自适应/按尺寸)
        "simplify_mesh",        # 简化(QEM/比例)
        "transform_mesh",       # 变换(平移/旋转/缩放/镜像)
        "boolean_operation",    # 布尔运算
        "measure",              # 测量(距离/角度/面积)
        "compute_section",      # 截面计算
        "compute_thickness",    # 壁厚分析
        "select_faces",         # 面片选择
        "delete_faces",         # 删除面片
        "fill_holes",           # 填充孔洞
        "shell_mesh",           # 抽壳
        "center_mesh",          # 居中
        "align_to_floor",       # 对齐到地面
        "export_model",         # 导出模型(多格式)
        "get_model_info",       # 获取模型信息(面数/体积/尺寸等)
    ]
    
    # 自动执行链：导入后自动触发的操作序列
    AUTO_CHAIN = {
        "after_load": [
            "check_mesh_quality",   # 自动质量检查
            # 如果质量不合格 → 自动修复
        ],
        "after_repair": [
            "get_model_info",       # 报告最终状态
        ]
    }
```

### 3.3 MoldDesignAgent — 模具设计

```python
class MoldDesignAgent:
    """模具设计 Agent — 方向分析→分型→壳体→浇注的全流程自动化"""
    
    SYSTEM_PROMPT = """
    你是 MoldGen 的模具设计专家。你能自动完成从方向分析到模具生成的全流程。
    
    自动执行规则：
    - "生成模具" → 自动执行: 方向分析→分型面→壳体→装配→浇注系统
    - 方向分析完成后自动选择最优方向（除非用户指定）
    - 分型面生成后自动验证（失败则换方法重试）
    - 壳体生成后自动进行 FDM 适配检查
    - 浇注系统自动设计并添加
    
    智能决策：
    - 根据模型复杂度自动决定壳数（优先最少片数）
    - 检测到大倒扣区域时主动提醒用户可能需要更多片
    - 壁厚不合格时自动调整参数并重新生成
    - 可根据材料类型(硅胶/注塑)自动调整全部参数
    
    全自动模式下的执行链：
    analyze_orientation → select_best_direction → generate_parting →
    build_shells → add_assembly_features → fdm_check → design_gating →
    report_result
    """
    
    TOOLS = [
        "analyze_orientation",      # GPU 方向分析
        "get_direction_candidates",  # 获取候选方向列表
        "select_direction",          # 选择脱模方向(自动/手动)
        "generate_parting_line",     # 生成分型线
        "generate_parting_surface",  # 生成分型面
        "split_into_shells",         # 多片壳分割
        "build_mold_shells",         # 构建模具壳体
        "add_alignment_pins",        # 添加定位销
        "add_bolt_holes",           # 添加螺栓孔
        "check_fdm_printability",   # FDM 可打印性检查
        "optimize_for_fdm",         # FDM 优化
        "design_gating_system",     # 设计浇注系统
        "set_mold_params",          # 设置模具参数
        "get_mold_info",            # 获取模具信息
        "preview_assembly",         # 预览装配(爆炸视图)
    ]
    
    # 全自动流水线定义
    AUTO_PIPELINE = [
        {"tool": "analyze_orientation", "auto": True},
        {"tool": "select_direction", "auto": True, "confirm_if": "score < 0.7"},
        {"tool": "generate_parting_line", "auto": True},
        {"tool": "generate_parting_surface", "auto": True, "retry_on_fail": True},
        {"tool": "split_into_shells", "auto": True},
        {"tool": "build_mold_shells", "auto": True},
        {"tool": "add_alignment_pins", "auto": True},
        {"tool": "add_bolt_holes", "auto": True},
        {"tool": "check_fdm_printability", "auto": True},
        {"tool": "optimize_for_fdm", "auto": True, "skip_if": "fdm_check_pass"},
        {"tool": "design_gating_system", "auto": True},
    ]
```

### 3.4 InsertAgent — 支撑板设计

```python
class InsertAgent:
    """支撑板 Agent — AI辅助的支撑板智能设计"""
    
    SYSTEM_PROMPT = """
    你是 MoldGen 的支撑板设计专家。你结合解剖学知识和工程经验，
    为硅胶模具设计内嵌支撑板。
    
    你的核心能力：
    - 分析模型几何结构（壁厚/截面/平面）确定支撑板位置
    - 根据器官类型选择最适合的锚固结构
    - 确保支撑板可一体置入模具并被硅胶完整包裹
    - 验证装配可行性
    
    自动执行规则：
    - 用户说"添加支撑板" → 自动分析 → 生成方案 → 展示方案 → 等待确认
    - 用户确认后 → 自动生成支撑板 + 锚固结构 + 装配验证
    - 用户说"自动处理支撑板" → 分析+生成+验证全自动
    - 验证失败时自动调整参数重试（最多3次）
    
    器官类型→支撑板策略映射：
    - 实质性器官(肝/肾/脑) → 中央横断面板, 网孔锚固
    - 空腔器官(胃/膀胱) → 内壁支撑环, 沟槽锚固
    - 管道结构(血管/肠道) → 轴向骨架, 凸起锚固
    - 组织片(皮肤/肌肉) → 底板, 菱形纹锚固
    """
    
    TOOLS = [
        "analyze_insert_positions",   # 自动分析支撑板位置
        "generate_insert_plate",      # 生成单个支撑板
        "add_anchor_structure",       # 添加锚固结构(网孔/凸起/沟槽/燕尾/菱形纹)
        "modify_insert",              # 修改支撑板(位置/尺寸/锚固)
        "delete_insert",              # 删除支撑板
        "add_locating_slots",         # 在模具壳体上添加定位槽
        "validate_insert_assembly",   # 装配验证
        "check_silicone_coverage",    # 检查硅胶包裹完整性
        "check_insertion_path",       # 检查安装路径
        "get_insert_info",            # 获取支撑板信息
        "analyze_with_vision",        # 调用Qwen-VL分析模型结构(用于解剖识别)
    ]
```

### 3.5 SimOptAgent — 仿真优化

```python
class SimOptAgent:
    """仿真优化 Agent — 灌注仿真 + 缺陷检测 + 自动优化"""
    
    SYSTEM_PROMPT = """
    你是 MoldGen 的仿真优化专家。你负责灌注流动仿真和模具优化。
    
    自动执行规则：
    - "运行仿真" → 自动选择仿真级别(L1/L2) → 执行 → 报告结果
    - "优化模具" → 仿真 → 检测缺陷 → 自动调参 → 重新仿真 → 循环直到收敛
    - 仿真完成自动进行缺陷检测并生成报告
    - 发现严重缺陷(短射>5%)时自动启动优化流程
    
    智能决策：
    - 小模型(<50K面) → L2仿真直接运行
    - 大模型(>200K面) → 先L1快速分析,确认大方向后再L2
    - 有GPU → L2 GPU加速; 无GPU → L1为主
    - 优化3轮不收敛 → 停止并报告,建议用户手动调整
    """
    
    TOOLS = [
        "run_simulation_l1",       # L1 启发式分析
        "run_simulation_l2",       # L2 达西流(GPU加速)
        "detect_defects",          # 缺陷检测
        "generate_sim_report",     # 生成仿真报告
        "optimize_gate_position",  # 优化浇口位置
        "optimize_runner_size",    # 优化流道尺寸
        "add_vent",                # 添加排气孔
        "adjust_wall_thickness",   # 调整壁厚
        "run_optimization_loop",   # 运行自动优化循环
        "compare_results",         # 对比优化前后结果
        "get_simulation_data",     # 获取仿真数据(充填时间/压力/缺陷)
        "select_material",         # 选择/更换灌注材料
    ]
    
    AUTO_OPTIMIZE_LOOP = {
        "max_iterations": 5,
        "convergence_threshold": 0.05,
        "auto_actions": {
            "short_shot": ["optimize_gate_position", "optimize_runner_size"],
            "air_trap": ["add_vent"],
            "fill_imbalance": ["optimize_gate_position"],
            "weld_line": ["optimize_gate_position"],
            "insert_air_pocket": ["add_vent", "modify_insert_anchor_density"],
        }
    }
```

### 3.6 CreativeAgent — 创意生成 ✅ 已实现

CreativeAgent 支持**云端+本地**双后端透明切换。

**后端支持：**

| 功能 | 云端 | 本地 |
|------|------|------|
| 图像生成 | 通义万相 (DashScope) | SDXL / FLUX.1-schnell / SD 1.5 / Kolors |
| 文字→3D | Tripo3D API | ❌ (需先生成图像) |
| 图片→3D | Tripo3D API | TripoSR / InstantMesh / TRELLIS |
| 模型审查 | Qwen-VL | Qwen-VL (云端) |
| 提示词优化 | DeepSeek/Qwen LLM | 规则匹配 (fallback) |

**实现的工具：**

```python
TOOLS = [
    "optimize_prompt",          # LLM 优化提示词 (fallback: 规则匹配)
    "generate_images",          # 生成参考图像 (云端万相/本地Diffusers)
    "generate_3d_from_text",    # 文字→3D (仅云端Tripo3D)
    "generate_3d_from_image",   # 图像→3D (云端Tripo3D/本地TripoSR)
    "review_model_quality",     # Qwen-VL 质量审查
    "list_local_models",        # 列出本地可用模型
    "switch_provider",          # 切换云端/本地后端
]
```

**执行流水线：** 提示词优化 → 图像生成 → (用户选择) → 图→3D → 审查 → 交付

详见 `docs/10-local-models.md`。

## 4. Agent 自动执行引擎

### 4.1 执行模式

```
三种执行模式:

全自动模式 (Auto):
  Agent 独立完成所有步骤,仅在最终结果处通知用户
  触发: 用户说"自动完成"/"帮我全部搞定"/"一键生成"

半自动模式 (Semi-Auto) [默认]:
  Agent 自动执行非关键步骤,关键决策点暂停等待用户确认
  关键决策点: 方向选择、壳数确认、支撑板方案、最终导出

逐步模式 (Step-by-Step):
  每个步骤执行前都暂停说明并等待用户确认
  触发: 用户说"一步步来"/"我想看每一步"
```

### 4.2 执行引擎架构

```python
class AgentExecutionEngine:
    """Agent 自动执行引擎"""
    
    def __init__(self, agents: Dict[str, BaseAgent], 
                 tool_registry: ToolRegistry,
                 ai_service: AIServiceManager):
        self.agents = agents
        self.tools = tool_registry
        self.ai = ai_service
        self.active_tasks: Dict[str, ExecutionContext] = {}
    
    async def execute(self, user_request: str, 
                      mode: ExecutionMode = ExecutionMode.SEMI_AUTO
                     ) -> AsyncIterator[ExecutionEvent]:
        """
        主执行入口
        
        1. MasterAgent 解析意图 → 生成执行计划
        2. 按计划依次调度专业 Agent
        3. 每个 Agent 内部按工具链自动执行
        4. 根据 mode 决定确认点
        """
        # MasterAgent 规划
        plan = await self.agents["master"].plan(user_request, mode)
        yield ExecutionEvent("plan_created", plan)
        
        # 逐步执行
        for step in plan.steps:
            agent = self.agents[step.agent_name]
            
            # 检查是否需要确认
            if step.needs_confirmation(mode):
                yield ExecutionEvent("need_confirmation", step)
                confirmation = await self.wait_for_user_input()
                if not confirmation.approved:
                    continue  # 跳过或调整
            
            # Agent 执行
            async for event in agent.execute(step.task, step.params, mode):
                yield event
            
            # 步骤完成
            yield ExecutionEvent("step_complete", step)
    
    async def handle_interrupt(self, task_id: str, instruction: str):
        """用户中途插入指令（如"停一下"/"改个参数"/"跳过这步"）"""
    
    async def resume(self, task_id: str):
        """恢复暂停的任务"""

class ExecutionContext:
    """执行上下文 — 跨Agent共享的状态"""
    task_id: str
    mode: ExecutionMode
    current_model: Optional[MeshData]
    current_mold: Optional[MoldResult]
    current_inserts: Optional[InsertResult]
    current_simulation: Optional[SimulationResult]
    execution_plan: ExecutionPlan
    history: List[ExecutionEvent]
    user_preferences: Dict[str, Any]  # 用户偏好(壁厚/材料/精度等)

class ExecutionMode(str, Enum):
    AUTO = "auto"             # 全自动
    SEMI_AUTO = "semi_auto"   # 半自动(默认)
    STEP_BY_STEP = "step"     # 逐步确认
```

### 4.3 Agent 间数据传递

```
CreativeAgent                 ModelAgent               MoldDesignAgent
  生成3D模型 ──→ MeshData ──→ 修复/编辑 ──→ MeshData ──→ 方向分析
                                                            │
                                                        MoldResult
                                                            │
InsertAgent ◄────────────────────────────────────────────────┘
  支撑板设计 ──→ InsertResult ──→ SimOptAgent
                                    仿真优化 ──→ SimResult
                                                    │
                                                 优化后重新生成?
                                                    ├─ 是 → MoldDesignAgent
                                                    └─ 否 → 导出
```

### 4.4 自动执行决策树

```python
CONFIRMATION_RULES = {
    # 操作类型 → 各模式下是否需要确认
    #                           Auto   Semi   Step
    "load_model":              (False, False, True),
    "repair_mesh":             (False, False, True),
    "simplify_mesh":           (False, False, True),
    "boolean_operation":       (False, True,  True),   # 不可逆操作
    "select_direction":        (False, True,  True),   # 关键决策
    "generate_parting":        (False, False, True),
    "build_shells":            (False, False, True),
    "shell_count_decision":    (False, True,  True),   # 关键决策
    "insert_plate_plan":       (False, True,  True),   # 关键决策
    "generate_inserts":        (False, False, True),
    "run_simulation":          (False, False, True),
    "auto_optimize":           (False, False, True),
    "export_files":            (False, True,  True),   # 最终输出
    "generate_image":          (False, False, True),
    "generate_3d_model":       (False, False, True),
    "select_generated_image":  (False, True,  True),   # 审美选择
    "delete_anything":         (True,  True,  True),   # 始终确认
}
```

## 5. Agent 工作站 UI 设计

### 5.1 工作站界面布局

```
┌────────────────────────────────────────────────────────────────┐
│  Agent 工作站                        [模式:半自动▼] [暂停] [关闭] │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  当前任务: 生成心脏解剖教学模型完整模具                            │
│  执行Agent: MoldDesignAgent                    总进度: ████░ 75% │
│                                                                │
│  ┌─────────────────────────────── 执行日志 ──────────────────┐  │
│  │                                                           │  │
│  │  [10:32:01] MasterAgent: 解析任务 → 5步执行计划           │  │
│  │  [10:32:02] CreativeAgent: 生成参考图像...                │  │
│  │  [10:32:08] CreativeAgent: ✅ 3张参考图已生成              │  │
│  │  [10:32:08] 📋 请选择参考图: [图1] [图2] [图3]            │  │
│  │  [10:32:15] 用户选择了图2                                 │  │
│  │  [10:32:16] CreativeAgent: 生成3D模型...                  │  │
│  │  [10:32:45] CreativeAgent: ✅ 心脏模型已生成并加载         │  │
│  │  [10:32:46] ModelAgent: 自动修复网格 → 修复3个孔洞         │  │
│  │  [10:32:48] ModelAgent: ✅ 模型就绪 (52K面, 128×90×65mm)  │  │
│  │  [10:32:49] MoldDesignAgent: 方向分析(GPU)...             │  │
│  │  [10:32:52] MoldDesignAgent: ✅ 最优方向 [0, 0, 1] 评分0.85│  │
│  │  [10:32:52] 📋 建议4片壳模具，是否确认？ [确认] [调整]     │  │
│  │  [10:32:55] 用户确认                                      │  │
│  │  [10:32:56] MoldDesignAgent: 生成分型面...                │  │
│  │  [10:33:02] MoldDesignAgent: 构建壳体...                  │  │
│  │  [10:33:10] MoldDesignAgent: ✅ 4片壳模具已生成            │  │
│  │  [10:33:11] InsertAgent: 分析支撑板位置... 🔄              │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────── 当前Agent状态 ────────┐  ┌────── 快捷操作 ────────┐ │
│  │  InsertAgent 执行中            │  │  [跳过此步] [回退一步]  │ │
│  │  正在分析模型截面...           │  │  [暂停] [全自动继续]    │ │
│  │  进度: ██░░░ 40%              │  │  [查看当前模具]         │ │
│  └───────────────────────────────┘  └────────────────────────┘ │
│                                                                │
│  💬 [输入指令: 可随时对当前Agent说话...]                         │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 Agent 状态指示

```
UI 中每个 Agent 的状态显示:

  🟢 ModelAgent     就绪        (空闲)
  🔵 MoldDesignAgent 执行中     (生成壳体 3/4)
  🟡 InsertAgent     等待中     (排队)
  🟠 SimOptAgent     等待输入   (需要选择材料)
  🔴 CreativeAgent   错误       (API 调用失败)
  ⚪ Agent名称       未激活     (本次不需要)
```

## 6. 完整工作流示例

### 6.1 "一键生成肝脏教学模具" 全自动流程

```
用户: "帮我做一个带门静脉系统的成人肝脏教学模型的硅胶模具，全自动完成"

MasterAgent 规划:
  Step 1: [CreativeAgent]  生成肝脏3D模型        auto=true
  Step 2: [ModelAgent]     模型修复+优化          auto=true
  Step 3: [MoldDesignAgent] 生成完整模具          auto=true
  Step 4: [InsertAgent]    设计支撑板            auto=true (方案确认)
  Step 5: [SimOptAgent]    仿真+优化             auto=true
  Step 6: [ModelAgent]     导出所有文件           auto=true (格式确认)

执行过程:
  CreativeAgent:
    → optimize_prompt("成人肝脏,门静脉系统") → 英文提示词
    → generate_images(3张) → 自动选择评分最高的
    → generate_3d_from_image() → 等待Tripo3D
    → review_model_quality() → "解剖结构基本合理,门静脉可见"
    → load_generated_model() → 加载到场景
    ✅ 交付模型给 ModelAgent
  
  ModelAgent:
    → check_mesh_quality() → "发现5个孔洞, 12个退化面"
    → repair_mesh() → 自动修复
    → get_model_info() → "48K面, 体积280×155×98mm, 封闭流形"
    ✅ 模型就绪
  
  MoldDesignAgent:
    → analyze_orientation(GPU) → 5个候选方向
    → select_direction(auto) → 选择评分0.87的最优方向
    → generate_parting_line() → 分型线
    → generate_parting_surface() → 分型面
    → split_into_shells() → 3片壳
    → build_mold_shells(wall=5mm, clearance=0.2mm)
    → add_alignment_pins(4个)
    → add_bolt_holes(M4, 间距50mm)
    → check_fdm_printability() → 通过
    → design_gating_system(silicone, gate_d=6mm)
    ✅ 模具就绪
  
  InsertAgent:
    → analyze_insert_positions() → 建议2块支撑板
    → [暂停] 展示方案: "建议在冠状面放置1块+底部1块"
    → [用户确认]
    → generate_insert_plate(板1: 冠状面, 网孔锚固)
    → generate_insert_plate(板2: 底部, 沟槽锚固)
    → add_locating_slots() → 模具壳体上添加定位槽
    → validate_insert_assembly() → 通过
    ✅ 支撑板就绪
  
  SimOptAgent:
    → select_material("silicone_shore_a30")
    → run_simulation_l2(GPU, 128³) → 充填率99.7%
    → detect_defects() → 1个小气泡(severity=0.2)
    → [severity<0.5, 自动处理] add_vent(气泡位置)
    → run_simulation_l2() → 充填率99.98%, 无缺陷
    ✅ 仿真通过
  
  ModelAgent (export):
    → [暂停] "导出格式？" → [用户: "STL和3MF都要"]
    → export_model(shells, format="stl")
    → export_model(shells, format="3mf")
    → export_model(inserts, format="stl")
    ✅ 全部导出完成

总耗时: ~3分钟 (其中AI生成~40秒, GPU仿真~30秒)
```

### 6.2 Agent 对话控制示例

```
用户: "把支撑板的孔再大一点"

MasterAgent:
  → 意图: 修改支撑板参数
  → 路由: InsertAgent
  → 上下文: 当前有2块支撑板, 锚固类型为网孔

InsertAgent:
  → 理解"孔再大一点" → 增大 hole_diameter 20% (3mm → 3.6mm)
  → modify_insert(insert_id=1, anchor_config={hole_diameter: 3.6})
  → modify_insert(insert_id=2, anchor_config={hole_diameter: 3.6})
  → validate_insert_assembly() → 通过
  → "已将两块支撑板的孔径从3mm调整为3.6mm，装配验证通过。"

用户: "第一块板往右移2毫米"

InsertAgent:
  → modify_insert(insert_id=1, action="move", offset=[2, 0, 0])
  → validate_insert_assembly() → 通过
  → "已将第1块支撑板向右移动2mm。"

用户: "重新跑一下仿真看看"

MasterAgent:
  → 路由: SimOptAgent

SimOptAgent:
  → run_simulation_l2() → 充填率99.95%
  → detect_defects() → 无缺陷
  → "仿真通过，充填率99.95%，无缺陷。"
```

## 7. Agent 记忆与上下文

### 7.1 短期记忆（会话内）

```python
class AgentMemory:
    """Agent 短期记忆 — 会话级"""
    
    conversation_history: List[Message]     # 完整对话历史
    execution_context: ExecutionContext      # 当前执行状态
    user_preferences: Dict[str, Any]        # 本次会话偏好
    
    # 从对话中提取的偏好
    # 例: 用户说"壁厚用6mm" → {"wall_thickness": 6.0}
    # 之后生成模具时自动使用此参数
```

### 7.2 长期记忆（跨会话）

```python
class AgentLongTermMemory:
    """Agent 长期记忆 — 持久化"""
    
    # 存储在 SQLite 中
    user_defaults: Dict[str, Any]           # 用户默认参数偏好
    frequent_organs: List[str]              # 常用器官类型
    preferred_materials: List[str]          # 常用材料
    past_successful_configs: List[dict]     # 历史成功配置
    
    def get_recommendation(self, organ_type: str) -> dict:
        """基于历史成功配置推荐参数"""
```

## 8. 错误处理与降级

```python
ERROR_HANDLING = {
    "ai_api_timeout": {
        "action": "retry",
        "max_retries": 3,
        "fallback": "notify_user_and_suggest_manual"
    },
    "ai_api_unavailable": {
        "action": "switch_provider",
        "deepseek_fallback": "qwen",
        "tongyi_fallback": "kolors",
        "tripo_fallback": "notify_user"  # 3D生成无法降级，提示手动导入
    },
    "mesh_operation_failed": {
        "action": "retry_with_different_params",
        "max_retries": 2,
        "fallback": "rollback_and_notify"
    },
    "gpu_out_of_memory": {
        "action": "reduce_resolution_and_retry",
        "fallback": "cpu_fallback"
    },
    "validation_failed": {
        "action": "auto_adjust_and_retry",
        "max_retries": 3,
        "fallback": "present_issue_to_user"
    }
}
```
