# 系统架构设计

## 1. 架构总览

MoldGen 采用 **Tauri 2.0 桌面应用** + **AI 服务层** 的混合架构。

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Tauri 2.0 Desktop Shell                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    Frontend (WebView2)                           │ │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────┐  │ │
│  │  │ AI悬浮球   │ │ Agent工作站│ │ 3D编辑器   │ │ 模具生成/仿真 │  │ │
│  │  │ ChatBubble│ │ AgentPanel│ │ MeshEditor│ │ MoldWorkbench │  │ │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────────┘  │ │
│  │  React 18 + TypeScript + R3F + Framer Motion + shadcn/ui       │ │
│  └──────────────────────────┬──────────────────────────────────────┘ │
│                              │ HTTP/WS (localhost)                    │
│  ┌───────────────────────────▼──────────────────────────────────────┐│
│  │                    Python Backend (FastAPI Sidecar)               ││
│  │                                                                   ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐ ││
│  │  │  AI Service      │  │ Processing Engine│  │ Simulation Engine│ ││
│  │  │  ┌────────────┐  │  │  MeshIO/Repair  │  │ FlowSimulator   │ ││
│  │  │  │ Agent 调度  │  │  │  MeshEditor     │  │ Optimizer       │ ││
│  │  │  │ LLM 对话   │  │  │  Orientation    │  │ (GPU加速)       │ ││
│  │  │  │ 图像生成   │  │  │  Parting/Mold   │  │                 │ ││
│  │  │  │ 3D模型生成 │  │  │  InsertGen      │  │                 │ ││
│  │  │  │ 多模态理解 │  │  │  GatingSystem   │  │                 │ ││
│  │  │  └────────────┘  │  │  (GPU加速)      │  │                 │ ││
│  │  └─────────────────┘  └─────────────────┘  └──────────────────┘ ││
│  │                                                                   ││
│  │  ┌──────────────────────────────────────────────────────────────┐ ││
│  │  │                    GPU Compute Layer                         │ ││
│  │  │  Numba CUDA │ CuPy │ cuBVH │ CPU Fallback                  │ ││
│  │  └──────────────────────────────────────────────────────────────┘ ││
│  └───────────────────────────┬──────────────────────────────────────┘│
│                              │ HTTPS                                 │
└──────────────────────────────┼───────────────────────────────────────┘
                               ▼
              ┌────────────────────────────────┐
              │       External AI Services      │
              │  DeepSeek │ 通义万相 │ Tripo3D  │
              │  Qwen-VL │ Kolors (备选)       │
              └────────────────────────────────┘
```

## 2. AI 子系统架构（核心新增）

### 2.1 AI 悬浮球 (AI Chat Bubble)

始终悬浮在界面右下角的对话入口，用户可随时唤起：

```
用户操作流:
  1. 点击悬浮球 → 展开对话窗口
  2. 输入需求描述 → AI 理解意图
  3. AI 分析后:
     ├─ 简单问题 → 直接回答
     ├─ 需要生成图像 → 调用通义万相 → 展示参考图
     ├─ 需要生成模型 → 调用 Tripo3D → 加载到场景
     ├─ 需要调整模具参数 → Function Calling → 自动操作
     ├─ 需要规划支撑板 → 分析模型 → 建议方案 → 用户确认 → 生成
     └─ 复杂多步任务 → 转入 Agent 工作站

UI 设计:
  - 悬浮球: 60px 圆形, 呼吸灯动画, 拖拽可移动
  - 展开: 侧边滑出对话面板 (400px 宽)
  - 消息气泡: 用户/AI 区分, 支持 Markdown 渲染
  - 支持图片预览、3D 模型缩略图、操作确认按钮
  - 输入: 文本 + 图片粘贴/拖拽
```

### 2.2 内置 Agent 体系（核心架构）

MoldGen 内置六大专业 Agent，可直接调用软件全部功能模块自主执行操作：

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

| Agent | 职责 | 自动执行能力 | 人机确认点 |
|-------|------|------------|-----------|
| **MasterAgent** | 意图识别、任务规划、Agent 路由调度 | 规划全自动 | 任务开始确认 |
| **ModelAgent** | 模型导入、修复、细化/简化、编辑 | 修复/简化全自动 | 布尔运算前确认 |
| **MoldDesignAgent** | 方向分析、分型面、壳体、浇注系统 | 全流程可全自动 | 方向选择、片数确认 |
| **InsertAgent** | 支撑板位置分析、生成、锚固结构 | 方案生成自动 | 方案确认后生成 |
| **SimOptAgent** | 灌注仿真、缺陷检测、自动优化 | 仿真+优化全自动 | 优化结果审查 |
| **CreativeAgent** | 图像生成、3D模型生成、需求转化 | 生成全自动 | 选择确认 |

> 各 Agent 的详细设计（System Prompt、工具列表、自动执行链、决策规则）参见 [08-agent-system.md](./08-agent-system.md)

### 2.3 Agent 执行引擎

Agent 自动执行引擎负责驱动所有 Agent 协作完成复杂任务：

```
三种执行模式:
  全自动 (Auto):     Agent 独立完成全部步骤，仅关键节点通知用户
  半自动 (Semi-Auto): 非关键步骤自动执行，关键决策暂停确认 [默认]
  逐步 (Step):       每步骤执行前暂停等待用户确认
```

```python
class AgentExecutionEngine:
    """Agent 自动执行引擎 — 核心调度中枢"""
    
    agents: Dict[str, BaseAgent]         # 6大内置Agent
    tools: ToolRegistry                  # 全局工具注册表
    ai: AIServiceManager                 # AI服务接入层
    active_tasks: Dict[str, ExecutionContext]  # 活跃任务
    
    async def execute(user_request, mode) -> AsyncIterator[ExecutionEvent]:
        """MasterAgent规划 → 专业Agent逐步执行 → 流式事件输出"""
    
    async def handle_interrupt(task_id, instruction):
        """用户中途插入指令（暂停/跳过/改参数）"""
    
    async def resume(task_id):
        """恢复暂停的任务"""

class ExecutionContext:
    """跨Agent共享的执行上下文"""
    current_model: Optional[MeshData]
    current_mold: Optional[MoldResult]
    current_inserts: Optional[InsertResult]
    current_simulation: Optional[SimulationResult]
    execution_plan: ExecutionPlan
    user_preferences: Dict[str, Any]
```

### 2.4 Agent 数据流与协作

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
                                                 优化后需重新生成?
                                                    ├─ 是 → MoldDesignAgent
                                                    └─ 否 → 导出
```

### 2.5 Agent 工作站 (Agent Workstation UI)

```
┌────────────────────────────────────────────────────────────────┐
│  Agent 工作站                        [模式:半自动▼] [暂停] [关闭] │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  当前任务: 生成心脏解剖教学模型完整模具                            │
│  执行Agent: MoldDesignAgent                    总进度: ████░ 75% │
│                                                                │
│  ┌─────────────────────────── 执行日志 ──────────────────────┐  │
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
│  │  [10:32:52] MoldDesignAgent: ✅ 最优方向 [0,0,1] 评分0.85 │  │
│  │  [10:32:52] 📋 建议4片壳模具，是否确认？ [确认] [调整]     │  │
│  │  [10:32:55] 用户确认                                      │  │
│  │  [10:33:10] MoldDesignAgent: ✅ 4片壳模具已生成            │  │
│  │  [10:33:11] InsertAgent: 分析支撑板位置... 🔄              │  │
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

### 2.6 AI 辅助支撑板设计流程

```
用户: "这个肝脏模型需要内部支撑板"
  │
  ▼
MasterAgent → 路由到 InsertAgent
  │
  ▼
InsertAgent 自动执行:
  ├─ analyze_insert_positions() → 几何分析
  ├─ analyze_with_vision() → Qwen-VL 解剖结构识别
  └─ 综合分析 → 生成支撑板建议方案
  │
  ▼
InsertAgent 向用户展示方案 [半自动确认点]:
  "建议在以下位置放置 3 块支撑板：
   1. 肝脏冠状面中部 — 六角网孔锚固 — 支撑左右叶
   2. 门静脉主干旁 — 凸点锚固 — 防止血管通道塌陷
   3. 底部固定板 — 沟槽锚固 — 整体固定"
  │
  ├─ 用户确认 → InsertAgent 自动执行: generate + validate
  ├─ 用户对话调整 → "把第2块板移到偏右一点" → modify_insert → 重新验证
  └─ 用户切换手动编辑 → 暂停Agent，进入编辑器模式
```

## 3. 核心模块划分（更新）

| 模块 | 职责 | 关键依赖 |
|------|------|---------|
| `ai_service` | **AI 服务统一层** | openai SDK |
| `ai_agent` | **Agent 执行引擎+6大内置Agent** | DeepSeek API |
| `ai_agents/master` | **总控Agent — 意图路由+任务编排** | ai_agent |
| `ai_agents/model` | **模型处理Agent — 导入/修复/编辑** | mesh_io, mesh_editor |
| `ai_agents/mold` | **模具设计Agent — 方向/分型/壳体** | orientation, mold_builder |
| `ai_agents/insert` | **支撑板Agent — 位置分析/生成** | insert_generator, ai_vision |
| `ai_agents/simopt` | **仿真优化Agent — 仿真/缺陷/优化** | flow_simulator, optimizer |
| `ai_agents/creative` | **创意生成Agent — 图像/3D生成** | ai_image_gen, ai_model_gen |
| `ai_image_gen` | **图像生成** | 通义万相 API |
| `ai_model_gen` | **3D 模型生成** | Tripo3D SDK |
| `ai_vision` | **多模态视觉理解** | Qwen-VL API |
| `mesh_io` | 多格式模型 IO | trimesh, pyassimp |
| `mesh_repair` | 网格修复 | trimesh, manifold3d |
| `mesh_editor` | 编辑/细化/简化 | trimesh, open3d |
| `orientation_analyzer` | GPU 方向分析 | cuBVH, numba |
| `parting_generator` | 分型面生成 | numpy, trimesh |
| `mold_builder` | 模具壳体构建 | manifold3d |
| `insert_generator` | 支撑板生成 (含AI辅助) | trimesh, ai_agent |
| `gating_system` | 浇注系统 | trimesh |
| `flow_simulator` | GPU 灌注仿真 | numba, cupy |
| `optimizer` | 自动优化 | scipy |
| `gpu_compute` | GPU 计算层 | numba, cupy, cuBVH |

## 4. 数据流（更新）

```
                ┌─── AI路径 ───────────────────────────┐
                │                                       │
    用户文字描述  │   AI悬浮球 / Agent工作站               │
        │        │       │                               │
        ▼        │       ▼                               │
    ┌────────┐   │  ┌──────────┐    ┌──────────────┐    │
    │AI对话   │───┤  │ 图像生成  │──→│ 3D模型生成    │    │
    │DeepSeek│   │  │ 通义万相  │    │ Tripo3D      │    │
    └────────┘   │  └──────────┘    └──────┬───────┘    │
                 │                          │            │
                 └──────────────────────────┼────────────┘
                                            │
                    用户直接导入文件 ──────────┤
                    (STL/OBJ/FBX/3MF/STEP)   │
                                            ▼
                                     ┌──────────────┐
                                     │   mesh_io    │ 多格式加载
                                     └──────┬───────┘
                                            ▼
                                     ┌──────────────┐
                                     │ mesh_repair  │ 修复
                                     └──────┬───────┘
                                            ▼
                                     ┌──────────────┐
                                     │ mesh_editor  │ 细化/简化/编辑
                                     └──────┬───────┘
                                            ▼
                                  ┌─────────────────────┐
                                  │ orientation_analyzer │ GPU方向分析
                                  └─────────┬───────────┘
                                            ▼
                                  ┌─────────────────────┐
                                  │ parting_generator    │ 分型面
                                  └─────────┬───────────┘
                                            ▼
                                  ┌─────────────────────┐
                                  │ mold_builder         │ 模具壳体
                                  └─────────┬───────────┘
                                            ▼
                               ┌──────────────────────────┐
                               │ insert_generator          │
                               │  ├─ AI对话确定需求        │ ◄── AI辅助
                               │  ├─ Qwen-VL分析结构       │
                               │  ├─ 自动生成支撑板        │
                               │  └─ 用户编辑确认          │
                               └────────────┬─────────────┘
                                            ▼
                               ┌──────────────────────────┐
                               │ gating_system + flow_sim  │ GPU仿真
                               └────────────┬─────────────┘
                                            ▼
                               ┌──────────────────────────┐
                               │ optimizer → 导出          │ 多格式
                               └──────────────────────────┘
```

## 5. AI Service 统一接入层

```python
class AIServiceManager:
    """AI 服务统一管理器"""
    
    def __init__(self, config: AIConfig):
        # 对话/推理 — DeepSeek (兼容 OpenAI SDK)
        self.chat_client = OpenAI(
            api_key=config.deepseek_api_key,
            base_url="https://api.deepseek.com"
        )
        
        # 多模态视觉 — Qwen-VL (兼容 OpenAI SDK)
        self.vision_client = OpenAI(
            api_key=config.qwen_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        # 图像生成 — 通义万相
        self.image_client = TongyiImageClient(api_key=config.tongyi_api_key)
        
        # 3D 模型生成 — Tripo3D
        self.model_3d_client = Tripo3DClient(api_key=config.tripo_api_key)
    
    async def chat(self, messages, tools=None) -> ChatResponse:
        """对话（支持 Function Calling）"""
    
    async def generate_image(self, prompt, size="1024x1024") -> ImageResult:
        """生成图像"""
    
    async def generate_3d_model(self, prompt=None, image=None) -> ModelResult:
        """生成3D模型（文字或图像输入）"""
    
    async def analyze_image(self, image, question) -> str:
        """多模态图像理解"""
```

## 6. 后端目录结构（更新）

```
moldgen/
├── api/
│   ├── routes/
│   │   ├── models.py           # 模型上传/查询
│   │   ├── edit.py             # 模型编辑
│   │   ├── molds.py            # 模具生成
│   │   ├── inserts.py          # 支撑板生成
│   │   ├── simulation.py       # 仿真
│   │   ├── export.py           # 多格式导出
│   │   ├── system.py           # GPU/系统状态
│   │   ├── ai_chat.py          # AI 对话 [新增]
│   │   └── ai_agent.py         # Agent 任务 [新增]
│   ├── schemas/
│   └── websocket.py            # WS (含AI流式响应)
├── core/                       # 几何/模具引擎 (同前)
├── gpu/                        # GPU 计算层 (同前)
├── ai/                         # AI 服务层 [新增]
│   ├── __init__.py
│   ├── service_manager.py      # AI 服务统一管理
│   ├── chat.py                 # LLM 对话 (DeepSeek)
│   ├── execution_engine.py     # Agent 自动执行引擎 [新增]
│   ├── agent_base.py           # BaseAgent 抽象基类 [新增]
│   ├── tool_registry.py        # 全局工具注册表 [新增]
│   ├── agents/                 # 6大内置Agent [新增]
│   │   ├── __init__.py
│   │   ├── master_agent.py     # MasterAgent 总控调度
│   │   ├── model_agent.py      # ModelAgent 模型处理
│   │   ├── mold_agent.py       # MoldDesignAgent 模具设计
│   │   ├── insert_agent.py     # InsertAgent 支撑板设计
│   │   ├── simopt_agent.py     # SimOptAgent 仿真优化
│   │   └── creative_agent.py   # CreativeAgent 创意生成
│   ├── image_gen.py            # 图像生成 (通义万相)
│   ├── model_gen.py            # 3D模型生成 (Tripo3D)
│   ├── vision.py               # 多模态理解 (Qwen-VL)
│   ├── memory.py               # Agent记忆管理(短期+长期) [新增]
│   └── prompts/                # 系统提示词模板
│       ├── master.py           # 总控Agent提示词 [新增]
│       ├── model_agent.py      # 模型处理Agent提示词 [新增]
│       ├── mold_agent.py       # 模具设计Agent提示词 [新增]
│       ├── insert_advisor.py   # 支撑板Agent提示词
│       ├── simopt_agent.py     # 仿真优化Agent提示词 [新增]
│       ├── creative_agent.py   # 创意生成Agent提示词 [新增]
│       └── model_reviewer.py   # 模型审查提示词
├── models/
├── services/
├── config/
└── utils/
```

## 7. 前端架构（v2 UI 重构）

参考 Blender Outliner / Unity Inspector / 专业模具 CAD 软件面板设计重构。

```
frontend/src/
├── components/
│   ├── layout/                  # UI 布局 [v2 重构]
│   │   ├── LeftPanel.tsx        # 步骤驱动参数面板 (290px)
│   │   ├── RightPanel.tsx       # 标签式面板 (大纲/属性/统计)
│   │   ├── SceneManager.tsx     # 场景管理器 (Blender Outliner 风格) [新增]
│   │   ├── WorkflowPipeline.tsx # 工作流导航条 (8 步)
│   │   ├── StepToolbar.tsx      # 视口上方快捷工具条
│   │   └── StatusBar.tsx        # 底部状态栏
│   ├── ai/                      # AI 组件
│   │   ├── ChatBubble.tsx       # AI 悬浮球
│   │   └── AgentWorkstation.tsx # Agent 工作站
│   ├── viewer/                  # 3D 查看器
│   │   ├── Viewport.tsx         # R3F Canvas 主视口
│   │   ├── ModelViewer.tsx      # 源模型渲染
│   │   ├── MoldShellViewer.tsx  # 模具壳体渲染
│   │   ├── InsertPlateViewer.tsx # 支撑板渲染
│   │   ├── GatingViewer.tsx     # 浇注系统渲染
│   │   └── SimulationViewer.tsx # 仿真热力图/流线/缺陷
│   ├── settings/                # 设置对话框
│   └── ui/                      # 通用 UI (Toast/Console/History)
├── hooks/                       # TanStack Query API hooks
│   ├── useModelApi.ts           # 模型上传/修复/简化
│   ├── useMoldApi.ts            # 方向/分型/模具
│   ├── useSimApi.ts             # 浇注/仿真/FEA
│   ├── useInsertApi.ts          # 支撑板
│   ├── useExportApi.ts          # 导出
│   ├── useAgentApi.ts           # Agent 执行
│   └── ...
├── stores/                      # Zustand 扁平存储
│   ├── appStore.ts              # 步骤 FSM / 面板 / 后端状态
│   ├── modelStore.ts            # 模型数据
│   ├── moldStore.ts             # 模具数据
│   ├── viewportStore.ts         # 视口图层可见性/显示模式
│   ├── simStore.ts              # 仿真数据
│   ├── aiStore.ts               # AI/Agent 状态
│   └── ...
├── index.css                    # Tailwind v4 + 主题变量 + 对象类型色彩
└── App.tsx                      # 根布局组件
```

### 7.1 场景管理器 (SceneManager) — Blender Outliner 风格

- **树形层级**: 模型 → 模具壳体 → 单壳; 支撑板; 浇注系统; 仿真热力图
- **交互功能**: 选中高亮 / 可见性开关 / 不透明度滑块 / 属性检查
- **搜索过滤**: 顶部搜索栏快速定位
- **类型色彩**: model=蓝 / mold=青 / insert=绿 / sim=粉 / gating=橙

### 7.2 右面板标签系统

| 标签 | 功能 |
|------|------|
| **大纲** | SceneManager 场景树 + 可见性 + 属性检查器 |
| **属性** | 模型/网格/尺寸/方向/模具/浇注/仿真属性, 可折叠分段 |
| **统计** | 工作流进度 + 几何统计条形图 + 仿真摘要 |

## 8. 通信架构（更新）

### 8.1 AI 相关 API 端点

```
# AI 对话
POST   /api/v1/ai/chat              发送对话消息
POST   /api/v1/ai/chat/stream       流式对话 (SSE)
GET    /api/v1/ai/chat/history       对话历史

# Agent 执行引擎
POST   /api/v1/ai/agent/execute          创建并启动自动执行任务
GET    /api/v1/ai/agent/task/{id}         获取任务状态+执行计划
POST   /api/v1/ai/agent/task/{id}/input   用户输入/确认/拒绝
POST   /api/v1/ai/agent/task/{id}/interrupt  中途插入指令
POST   /api/v1/ai/agent/task/{id}/resume  恢复暂停任务
PUT    /api/v1/ai/agent/task/{id}/mode    切换执行模式(auto/semi/step)
DELETE /api/v1/ai/agent/task/{id}         取消任务
GET    /api/v1/ai/agent/agents            获取可用Agent列表+状态

# 图像生成
POST   /api/v1/ai/image/generate    生成图像
GET    /api/v1/ai/image/{id}        获取图像

# 3D 模型生成
POST   /api/v1/ai/model3d/generate  生成3D模型
GET    /api/v1/ai/model3d/{id}      获取模型状态/下载

# WebSocket
WS     /ws/ai/chat                  流式AI对话
WS     /ws/ai/agent/{task_id}       Agent任务实时更新
```

### 8.2 AI 流式响应协议

```json
// 对话流式响应 (SSE/WebSocket)
{"type": "token", "content": "这个肝脏模型"}
{"type": "token", "content": "建议放置3块支撑板："}
{"type": "tool_call", "tool": "suggest_insert_plates", "args": {...}}
{"type": "tool_result", "result": {"inserts": [...]}}
{"type": "token", "content": "第1块板位于..."}
{"type": "action_request", "action": "confirm_inserts", "data": {...}}
{"type": "done"}

// Agent 执行引擎事件流 (WebSocket /ws/ai/agent/{task_id})
{"type": "plan_created", "plan": {"steps": [...], "estimated_time": 180}}
{"type": "agent_switch", "from": "master", "to": "creative", "task": "生成参考图像"}
{"type": "step_start", "step_id": 1, "agent": "creative", "action": "generate_images"}
{"type": "tool_call", "agent": "creative", "tool": "generate_images", "args": {...}}
{"type": "tool_result", "agent": "creative", "result": {"images": [...]}}
{"type": "step_complete", "step_id": 1, "agent": "creative"}
{"type": "need_confirmation", "step_id": 2, "question": "建议4片壳模具，是否确认？",
 "options": ["确认", "调整片数", "手动选择方向"]}
{"type": "user_confirmed", "step_id": 2, "choice": "确认"}
{"type": "agent_status", "agents": {"model": "idle", "mold": "running", "insert": "queued"}}
{"type": "task_complete", "summary": {...}, "total_time": 178}
{"type": "error", "agent": "creative", "error": "API timeout", "recovery": "retry"}
```

## 9. 支撑板一体化设计原则（新增）

### 9.1 一体置入概念

支撑板必须能在模具组装阶段一次性置入，灌注硅胶后永久保留在成品中：

```
装配流程:
  1. FDM 打印模具壳体（多片）
  2. FDM 打印支撑板（带锚固结构）
  3. 将支撑板放入模具下半壳（卡入定位槽）
  4. 合拢上半壳（支撑板被夹持固定）
  5. 通过浇口灌注硅胶
  6. 硅胶穿过支撑板网孔/包裹凸起 → 固化
  7. 拆除模具壳体
  8. 得到: 硅胶外层 + 内嵌支撑板的复合结构
```

### 9.2 支撑板在模具中的固定方式

```
┌──────────────── 模具上壳 ────────────────────┐
│                                               │
│   ┌─────────────────────────────────────┐     │
│   │         硅胶填充空间                  │     │
│   │    ═══╬═══╬═══╬═══╬═══             │     │
│   │     支撑板 (网孔/凸起)               │     │
│   │                                     │     │
│   │         ┌─────────┐                 │     │
│   │         │ 原始模型  │                 │     │
│   │         │ (型腔)   │                 │     │
│   │         └─────────┘                 │     │
│   └─────────────────────────────────────┘     │
│      ▲               ▲                        │
│    定位槽           定位槽                      │
│   (卡住支撑板边缘)   (确保精确定位)              │
│                                               │
└──────────────── 模具下壳 ────────────────────┘
```

### 9.3 医学器官模型的支撑板特殊考量

| 器官类型 | 支撑板策略 | 锚固类型 | 说明 |
|---------|-----------|---------|------|
| 实质性器官(肝/肾) | 中央横断面板 | 网孔 | 硅胶从两侧穿过，保持器官形状 |
| 空腔器官(胃/膀胱) | 内壁支撑环 | 沟槽 | 维持腔体形状 |
| 管道结构(血管/肠) | 轴向支撑骨架 | 凸起 | 防止管道塌陷 |
| 组织片(皮肤/肌肉) | 底板 | 菱形纹 | 提供整体刚性 |
