# MoldGen — AI 驱动的医学教具智能模具生成工作站

## 项目愿景

MoldGen 是一款面向**临床教学与手术教具开发**的 AI 驱动智能模具生成桌面工作站。系统深度融合 AI 对话、AI 图像生成、AI 3D 模型生成能力，通过 FDM 3D 打印技术，实现从需求描述到可生产模具的全自动化流程。

### 核心场景
- **病理器官模型**：肿瘤、病变组织、异常解剖结构的硅胶教具
- **生理器官模型**：标准人体器官（心、肝、肾、脑等）的仿真教学模型
- **手术训练模型**：供手术技能训练的多材料复合结构模型
- **定制化教具**：根据 CT/MRI 影像数据定制的患者特异性模型

### 全流程能力

```
AI 对话描述需求 ──→ AI 生成参考图像 ──→ AI 生成3D模型 ──→ 模型编辑/优化
        │                                                         │
        └─── 或直接导入 STL/OBJ/FBX/3MF/STEP/医学影像 ────────────┘
                                                                   │
                                                                   ▼
  自动脱模方向分析 → 多片壳模具生成 → 内嵌支撑板(AI辅助) → 浇注系统
        │                                                         │
        ▼                                                         ▼
  GPU加速灌注仿真 → 自动优化 → 多格式导出模具+支撑板 → FDM打印 → 硅胶灌注
```

## 核心价值

- **AI 原生**：内置 AI 悬浮球 + Agent 工作站，对话即可生成教具模型
- **6大内置Agent**：MasterAgent统一调度，ModelAgent/MoldAgent/InsertAgent/SimAgent/CreativeAgent分工自动执行，支持"一句话→完整模具"全自动流水线
- **医学专业**：针对解剖结构优化，支持医学影像导入与复合仿真材料
- **复合结构**：硅胶灌注 + 3D 打印内嵌支撑板，模拟真实组织力学特性
- **专业工作站**：现代美观 UI + 流畅动画，兼具专业严谨的工程工具风格
- **GPU 加速**：CUDA/WebGPU 双加速分析与仿真
- **桌面应用**：Tauri 2.0 轻量级跨平台桌面应用

## AI 能力集成

| AI 能力 | 服务商（首选国内） | 用途 |
|---------|------------------|------|
| 对话/推理 | DeepSeek V3 / 通义千问 | AI 悬浮球对话、Agent 推理、需求分析、支撑板智能规划 |
| 图像生成 | 通义万相 / 可图(Kolors) | 从文字描述生成器官参考图像 |
| 3D 模型生成 | Tripo3D / Meshy | 从文字/图像生成器官 3D 模型 |
| 多模态理解 | Qwen-VL / GLM-4V | 分析模型截图、识别解剖结构、辅助决策 |

## 文档索引

| 文档 | 说明 |
|------|------|
| [技术调研与竞品分析](docs/01-research.md) | 竞品、AI API、医学教具制造调研 |
| [系统架构设计](docs/02-architecture.md) | 整体架构、6大Agent体系、执行引擎 |
| [核心算法设计](docs/03-algorithms.md) | 脱模分析、Agent路由/调度/协作算法 |
| [模块详细设计](docs/04-modules.md) | 各模块接口，含Agent执行引擎完整设计 |
| [技术栈选型](docs/05-tech-stack.md) | Conda 环境、AI SDK、国内 API 选型 |
| [开发路线图](docs/06-roadmap.md) | 含 Agent 系统的完整开发计划 (23-28周) |
| [AI开发指令](docs/07-ai-prompts.md) | AI 辅助开发的 Prompt 模板 |
| [Agent系统设计](docs/08-agent-system.md) | **6大内置Agent详细设计、自动执行引擎、工作流示例** |
| [部署与使用指南](docs/09-deployment.md) | 环境要求、安装部署、界面操作、快捷键、AI配置、FAQ |

## 快速开始

```bash
# 1. 创建 Conda 环境
conda create -n moldgen python=3.11 -y
conda activate moldgen

# 2. 安装后端依赖
pip install -e ".[dev]"

# 3. 安装 GPU 加速 (需 NVIDIA GPU)
conda install -y -c nvidia cuda-toolkit=12.8
conda install -y -c conda-forge numba
pip install cupy-cuda12x

# 4. 配置 AI API (可选)
cp .env.example .env
# 编辑 .env 填入 API Key

# 5. 启动后端
python -m uvicorn moldgen.main:app --reload
# API 文档: http://127.0.0.1:8000/docs

# 6. 启动前端
cd frontend && npm install && npm run dev
# 前端: http://localhost:1420
```

## 项目结构

```
moldgen/
├── main.py              # FastAPI 入口
├── config.py            # 配置管理 (pydantic-settings)
├── api/
│   ├── routes/          # REST API (system/models/molds/sim/export/ai_chat/ai_agent)
│   ├── schemas/         # 请求/响应 Schema
│   └── websocket.py     # WebSocket (任务进度/AI流式/Agent事件)
├── core/                # 几何/模具引擎 (Phase 1-3)
├── gpu/                 # GPU 计算层 (device/ray_cast/sdf/flow_kernel)
├── ai/
│   ├── agents/          # 6大内置Agent (master/model/mold/insert/simopt/creative)
│   ├── prompts/         # Agent系统提示词
│   ├── service_manager  # AI 服务统一层
│   ├── execution_engine # Agent 自动执行引擎
│   └── memory           # Agent 记忆 (短期+长期)
├── models/              # 数据库模型
└── utils/               # 日志等工具
```

## 开发环境

- **CPU**: Intel i7 / **GPU**: NVIDIA RTX 4060 Ti (16GB VRAM)
- **OS**: Windows 10
- **环境管理**: Conda (Miniconda)
- **桌面封装**: Tauri 2.0

## 开发进度

| Phase | 状态 | 说明 |
|-------|------|------|
| P0 基础设施 | ✅ 完成 | 后端骨架 ✅ / Conda+GPU ✅ / 前端+Tauri ✅ / AI API ✅ |
| P1 模型处理 | ✅ 完成 | MeshIO多格式导入 ✅ / 修复 ✅ / 编辑(简化/细化/布尔) ✅ / API ✅ / 前端3D ✅ |
| P2 模具生成 | ✅ 完成 | 方向分析(Fibonacci+多准则) ✅ / 分型线/面 ✅ / 双片壳+多片壳模具 ✅ / 定位销+浇口+排气 ✅ / API ✅ / 前端模具面板 ✅ |
| P3 仿真优化 | ✅ 完成 | 材料库(7种预设) ✅ / 浇注系统设计 ✅ / L1启发式仿真 ✅ / L2达西流仿真 ✅ / 缺陷检测 ✅ / 自动优化 ✅ / API ✅ / 前端仿真面板 ✅ |
| P4 AI+Agent | ✅ 完成 | ToolRegistry(25+工具) ✅ / BaseAgent+ExecutionEngine ✅ / 6大Agent(Master/Model/Mold/Insert/Sim/Creative) ✅ / 意图路由+流水线模板 ✅ / Agent API(execute/classify/pipelines/tools) ✅ / 前端Agent工作站+AI对话 ✅ |
| P5 复合结构 | ✅ 完成 | InsertGenerator(位置分析+截面生成) ✅ / 5种锚固(网孔/凸起/沟槽/燕尾/菱形纹) ✅ / 器官类型策略映射 ✅ / 装配验证 ✅ / 模具定位槽 ✅ / InsertAgent实现 ✅ / API(analyze/generate/validate/GLB) ✅ / 前端支撑板面板 ✅ |
| P6 桌面完善 | ✅ 完成 | 多格式导出(STL/OBJ/PLY/GLB/3MF) ✅ / 模具ZIP导出 ✅ / 支撑板ZIP导出 ✅ / 一键全部导出 ✅ / 导出面板UI ✅ / RightPanel增强(支撑板+仿真信息) ✅ / 键盘快捷键(Ctrl+1~6/B/I/J) ✅ |
| P6.5 UI增强 | ✅ 完成 | 各步骤工具栏(StepToolbar) ✅ / 设置弹窗(API/模具/仿真/支撑板/GPU/界面) ✅ / Toast通知系统 ✅ / EditPanel增强(细分/旋转/缩放/测量) ✅ / 部署文档 ✅ |
| P7 发布 | ⏳ | 集成测试/打包/文档 |

## License

待定 (计划采用 AGPL-3.0 或 MIT)
# 3DPrint_MoldGen
# 3DPrint_MoldGen
