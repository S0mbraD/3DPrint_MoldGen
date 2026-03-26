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
- **内嵌支撑板系统**：硅胶灌注 + 3D 打印内嵌结构加固板，通过锚固特征与硅胶牢固结合，通过支撑立柱穿过模具壁定位，为教具提供内部骨骼/组织真实触感
- **nTopology 全功能对标**：SDF 隐式场引擎 (smooth boolean / 场操作 / 变厚度壳)，SIMP 拓扑优化 (2D+3D)，3D 体积晶格 (杆件 BCC/FCC/Octet/Kelvin + TPMS 7 种 + Voronoi 泡沫)，干涉/间隙分析，壁厚/曲率/拔模/对称性/悬垂/网格质量六维分析，Laplacian/Taubin/HC 平滑，等尺重网格化，**11 种网孔图案**，5 种场驱动连续半径调制
- **专业工作站**：现代美观 UI + 流畅动画，可视化工作流管线，设计规则校验，网格健康度仪表
- **GPU 加速**：CUDA/WebGPU 双加速分析与仿真
- **桌面应用**：Tauri 2.0 轻量级跨平台桌面应用

## 内嵌支撑板系统设计

### 核心概念

支撑板（Insert Plate）是置于硅胶教具**内部**的刚性结构板，目的是:
1. 为教具提供类似真实器官中骨骼、软骨或其他硬组织的手感
2. 通过锚固结构（贯穿孔/凸起/沟槽/燕尾榫/菱形纹）与硅胶牢固结合
3. 通过细小支撑立柱穿过模具壁固定位置

```
         ┌──── 模具壳体（3D打印）
         │     ┌──── 硅胶层
         │     │     ┌──── 支撑板（3D打印，带锚固特征）
         ▼     ▼     ▼
    ╔═══╗ ░░░░░ ████ ░░░░░ ╔═══╗
    ║   ║ ░░░░░ ████ ░░░░░ ║   ║  ← 横截面示意
    ║   ║ ░░░░░ ████ ░░░░░ ║   ║
    ╚═══╝ ░░░░░ ████ ░░░░░ ╚═══╝
              │   │
              │   └──── 支撑立柱穿过硅胶层和模具壁
              └──── 灌注完成后剪断立柱，板片永久嵌入硅胶中
```

### 工艺流程

1. 3D打印支撑板（含锚固特征表面）
2. 将支撑板通过立柱悬挂在模具空腔中
3. 灌注硅胶，硅胶包裹支撑板并渗入锚固特征
4. 脱模后剪断立柱，支撑板永久嵌入硅胶内

### 基础板型

| 类型 | 代码名 | 适用场景 | 说明 |
|------|--------|----------|------|
| 平板 | `flat` | 通用 | 模型截面挤出，经典方式 |
| 仿形板 | `conformal` | 曲面器官 | 沿模型内表面偏移，跟随曲面轮廓 |

### 可选特征（可叠加启用）

| 特征 | 配置项 | 说明 | 用途 |
|------|--------|------|------|
| 表面网孔 | `add_mesh_holes` | 板面上的贯穿通孔 | 硅胶渗透穿孔形成铆接，增强结合力 |
| 加强筋 | `add_ribs` | 交叉肋条 | 增强板面刚性，模拟骨骼触感 |
| 啮合固定 | `add_interlocking` | 燕尾榫/凸起/沟槽/菱形纹 | 板面边缘机械咬合，防止位移 |

### 支撑立柱

- 直径 1~4mm 的细小圆柱，从支撑板表面延伸穿过硅胶层和模具壁
- **模具壳体自动切割对应通孔**：生成支撑板后自动在模具壳体上切割圆柱形穿孔，确保立柱可通过
- 严格沿配置方向延伸（自动/底部/顶部/背面/正面/左侧/右侧），不再混合径向偏移
- 仅选取板面朝向出口方向的采样点，确保立柱集中在预期面
- 射线追踪精确定位模型表面出口点，自动跳过近距离自交叉
- 灌注完成后可剪断立柱，支撑板永久嵌入硅胶中

### 器官 → 推荐配置映射

| 器官类型 | 推荐板型 | 推荐锚固 | 说明 |
|----------|----------|----------|------|
| 实质性器官(肝/肾/脑) | 仿形板 | 贯穿孔 | 跟随器官曲面 |
| 空腔器官(胃/膀胱) | 平板 | 凸起互锁 | 简单支撑 |
| 管道结构(血管/肠道) | 平板 | 沟槽 | 沿截面 |
| 四肢/骨骼 | 加强筋板 | 贯穿孔 | 模拟骨骼 |
| 组织片(皮肤) | 格栅板 | 菱形纹 | 轻量柔性 |

### 分型面样式

| 样式 | 代码名 | 说明 |
|------|--------|------|
| 平面 | `flat` | 标准平面分型 |
| 燕尾榫 | `dovetail` | 梯形截面咬合 |
| 锯齿形 | `zigzag` | 三角形锯齿咬合 |
| 阶梯形 | `step` | 交错高度阶梯咬合 |
| 舌槽形 | `tongue_groove` | 凸舌 + 凹槽配合 |

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
| [错误与教训记录](docs/error-log.md) | 开发过程中的理解偏差、技术问题及修复方案记录 |

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
│   ├── __init__.py      # API 包标记
│   ├── routes/          # REST API
│   │   ├── models.py        # 模型上传/编辑/查询
│   │   ├── molds.py         # 模具生成/壳体/分型面
│   │   ├── inserts.py       # 支撑板生成/验证
│   │   ├── analysis.py      # nTopology 级分析 + 高级网格操作
│   │   ├── simulation.py    # 灌注仿真/FEA
│   │   ├── export.py        # 多格式导出
│   │   ├── ai_chat.py       # AI 对话
│   │   ├── ai_agent.py      # Agent 执行
│   │   ├── ai_generate.py   # AI 图像/3D 生成
│   │   └── system.py        # 系统状态/GPU/配置
│   ├── schemas/         # 请求/响应 Schema
│   └── websocket.py     # WebSocket (任务进度/AI流式/Agent事件)
├── core/                # 几何/模具/分析引擎
│   ├── analysis.py          # 壁厚/曲率/拔模/对称性/悬垂/BOM 分析
│   ├── fea.py               # 有限元弹簧质量模型
│   ├── mesh_data.py         # 统一网格数据结构
│   ├── mesh_editor.py       # 编辑 + 平滑/重网格化/偏移/增厚
│   ├── mesh_io.py           # 多格式导入导出
│   ├── mesh_repair.py       # 网格修复
│   ├── insert_generator.py  # 支撑板 (6 种晶格 + 场驱动密度)
│   ├── mold_builder.py      # 模具壳体 (布尔+体素+分型面+浇口)
│   ├── parting.py           # 分型线/面生成
│   ├── orientation.py       # 脱模方向分析 (GPU 加速)
│   ├── flow_sim.py          # 达西流灌注仿真
│   ├── gating.py            # 浇注系统设计
│   ├── material.py          # 材料库 (7+ 预设)
│   └── optimizer.py         # 自动优化循环
├── gpu/                 # GPU 计算层 (device/ray_cast/sdf/flow_kernel)
├── ai/
│   ├── agents/          # 6大内置Agent (master/model/mold/insert/simopt/creative)
│   ├── prompts/         # Agent系统提示词
│   ├── service_manager  # AI 服务统一层
│   ├── execution_engine # Agent 自动执行引擎
│   └── memory           # Agent 记忆 (短期+长期)
├── models/              # 数据库模型
└── utils/               # 日志等工具

tests/
├── test_analysis.py     # analysis 模块测试
├── test_mesh.py         # mesh 模块测试
├── test_insert.py       # 支撑板测试
├── test_mold.py         # 模具生成测试
├── test_simulation.py   # 仿真测试
├── test_api.py          # API 端点测试
├── test_agent.py        # Agent 系统测试
└── test_ai_api.py       # AI API 测试

frontend/
├── src/
│   ├── components/
│   │   └── layout/
│   │       ├── WorkflowPipeline.tsx  # nTopology 风格工作流管线
│   │       ├── LeftPanel.tsx         # 主控面板 (分析/编辑/生成)
│   │       └── ...
│   ├── hooks/
│   │   ├── useAnalysisApi.ts    # 分析/网格操作 hooks
│   │   └── ...
│   └── stores/
│       └── modelStore.ts        # Zustand 状态管理
└── src-tauri/               # Tauri 桌面封装
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
| P2 模具生成 | ✅ 完成 | 方向分析(Fibonacci+多准则) ✅ / 分型线/面 ✅ / 双片壳+多片壳模具 ✅ / 定位销+浇口+排气 ✅ / 分型面样式(燕尾/锯齿/阶梯/舌槽) ✅ / 分型面布尔修复 ✅ / API ✅ / 前端模具面板 ✅ |
| P3 仿真优化 | ✅ 完成 | 材料库(7种预设) ✅ / 浇注系统设计 ✅ / L1启发式仿真 ✅ / L2达西流仿真 ✅ / 缺陷检测 ✅ / 自动优化 ✅ / API ✅ / 前端仿真面板 ✅ |
| P4 AI+Agent | ✅ 完成 | ToolRegistry(25+工具) ✅ / BaseAgent+ExecutionEngine ✅ / 6大Agent(Master/Model/Mold/Insert/Sim/Creative) ✅ / 意图路由+流水线模板 ✅ / Agent API(execute/classify/pipelines/tools) ✅ / 前端Agent工作站+AI对话 ✅ |
| P5 支撑板系统 | ✅ 完成 | 支撑板生成器(4种板型: 平板/仿形/加强筋/格栅) ✅ / 锚固系统(5种: 贯穿孔/凸起/沟槽/燕尾榫/菱形纹) ✅ / 支撑立柱系统(自动方位/数量/射线追踪) ✅ / 内部包容性裁剪 ✅ / 器官类型→板型+锚固推荐映射 ✅ / 装配验证 ✅ / InsertAgent实现 ✅ / API(analyze/generate/validate/GLB/pillars.glb) ✅ / 前端支撑板面板 ✅ |
| P6 桌面完善 | ✅ 完成 | 多格式导出(STL/OBJ/PLY/GLB/3MF) ✅ / 模具ZIP导出 ✅ / 支撑板ZIP导出 ✅ / 一键全部导出 ✅ / 导出面板UI ✅ / RightPanel增强(支撑板+仿真信息) ✅ / 键盘快捷键(Ctrl+1~6/B/I/J) ✅ |
| P6.5 UI增强 | ✅ 完成 | 各步骤工具栏(StepToolbar) ✅ / 设置弹窗(API/模具/仿真/支撑板/GPU/界面) ✅ / Toast通知系统 ✅ / EditPanel增强(细分/旋转/缩放/测量) ✅ / 部署文档 ✅ |
| P6.6 nTopology级分析 | ✅ 完成 | 壁厚分析(多射线) ✅ / 曲率分析(Gaussian+Mean) ✅ / 拔模角分析 ✅ / 对称性分析(PCA) ✅ / 悬垂分析 ✅ / BOM估算 ✅ / 三种平滑(Laplacian/Taubin/HC) ✅ / 等尺重网格化 ✅ / 表面偏移+增厚 ✅ / 6种晶格(Hex/Grid/Gyroid/Schwarz-P/Diamond/Voronoi) ✅ / 场驱动变密度 ✅ / 工作流管线 ✅ / 网格健康仪表 ✅ / 设计规则校验 ✅ / 材料库 ✅ / 表面纹理 ✅ / 分析API ✅ / 测试 ✅ |
| P7 发布 | ⏳ | 集成测试/打包/文档 |

## 变更日志

### v0.10.0 — nTopology 全功能对标: SDF 隐式引擎 + 拓扑优化 + 3D 晶格 + 干涉分析

**新增 `moldgen/core/distance_field.py` — SDF 隐式场引擎**:
- `mesh_to_sdf()`: 三角网格 → 体素化有符号距离场 (trimesh proximity + winding number)
- **Smooth boolean**: `smooth_union/intersection/difference` (Íñigo Quílez polynomial k-blend)
- **Sharp boolean**: `sharp_union/intersection/difference`
- **场操作**: `field_offset`, `field_shell`, `field_variable_shell`, `field_blend`, `field_remap`, `field_gaussian_blur`, `field_threshold`
- **距离场生成**: `distance_field_from_points`, `distance_field_from_axis`
- **Iso-surface 提取**: `extract_isosurface` (Marching Cubes via scikit-image)
- **场驱动变厚度壳**: `field_driven_shell` — 3 种场类型 (离心距/底面距/曲率代理)

**新增 `moldgen/core/topology_opt.py` — SIMP 拓扑优化**:
- **2D SIMP**: `topology_opt_2d()` — 平面应力四节点双线性单元 + OC 更新 + 密度滤波
- **3D SIMP**: `topology_opt_3d()` — 8 节点六面体砖单元 + 2 点 Gauss 积分
- 3 种边界条件: cantilever (悬臂梁)、MBB beam、bridge
- `density_to_mesh()`: 密度场 → Marching Cubes 网格

**新增 `moldgen/core/lattice.py` — 3D 体积晶格生成器**:
- **杆件晶格**: BCC、FCC、Octet、Kelvin、Diamond 单胞 + 场驱动变杆径
- **TPMS 体积晶格**: 7 种 TPMS 曲面的三维壳体 + 场驱动变壁厚 + 自动裁剪至包围网格
- **Voronoi 泡沫**: 随机种子 + 5 轮 Lloyd 松弛 + 壁距离场提取
- `generate_lattice()` 统一调度器

**新增 `moldgen/core/interference.py` — 干涉/间隙分析**:
- `compute_clearance()`: 双向最近点查询 + 有符号距离 + 干涉体积估算
- `validate_assembly()`: 多零件装配间隙全对检查

**增强 `moldgen/core/analysis.py` — 网格质量分析**:
- `compute_mesh_quality()`: 三角形宽高比、最小/最大内角、边长统计、退化面检测、瘦三角形计数
- 拓扑指标: 水密性、流形性、欧拉特征、亏格
- 紧凑度 (36πV²/A³)
- 3 种直方图: 宽高比、边长、最小角

**新增 API 路由** (`/api/v1/advanced/`):
- `POST /boolean` — 布尔运算 (sharp + smooth blend)
- `POST /topology-opt/2d`, `/topology-opt/3d` — SIMP 拓扑优化
- `POST /lattice/generate` — 3D 晶格生成
- `POST /interference/check`, `/interference/assembly` — 干涉分析
- `POST /{model_id}/mesh-quality` — 网格质量分析
- `POST /sdf/compute`, `/sdf/variable-shell` — SDF 操作

**前端**:
- EditPanel: 网格质量分析面板、拓扑优化面板 (SIMP 2D)、场驱动变厚度壳面板
- InsertPanel: 3D 晶格填充面板 (graph/TPMS/foam 三种类型)
- 新增 `useAdvancedApi.ts` hooks

### v0.9.6 — TPMS 隐式场晶格库重写 + 网孔质量升级

**新增 `moldgen/core/tpms.py`**:
- 7 种数学精确 TPMS 曲面: Gyroid、Schwarz-P、Schwarz-D、Neovius、Lidinoid、IWP、FRD (公式取自 nTopology 官方 + Schoen 1970)
- `evaluate_field_2d()`: 高分辨率 2D 网格场求值 (ω=2π/cell_size)
- `extract_hole_centres()`: scipy.ndimage.maximum_filter 形态学极值检测 + 自适应半径
- `apply_field_modulation()`: 5 种空间场 (edge/center/radial/stress/uniform) 连续半径调制
- `generate_tpms_holes()`: 一站式 TPMS → 孔位列表 API

**insert_generator.py 重写**:
- `_hole_layout()` 分派器: TPMS 图案走隐式场管线，几何图案走直接布局
- `_carve_holes()` 四阶段管线: 预细分 → 面片删除 → 圆周投射 → Laplacian 平滑
- `_subdivide_near_holes()`: 2 轮选择性细分 [0.7r, 1.3r] 环带
- `_apply_variable_density()` 重写: 从二元随机删除改为连续半径调制
- `InsertConfig` 新增: `tpms_cell_size`, `tpms_z_slice`, `max_holes`
- 几何图案上限: 80 → 300; Voronoi Lloyd 迭代: 3 → 5

**前端**:
- LeftPanel 网孔选择器分两组: 几何图案 (4 种) + TPMS 极小曲面 (7 种)
- 每种 TPMS 图案显示数学公式说明
- 密度场选项扩展至 5 种 (edge/center/radial/stress/uniform)

**API**:
- `GenerateInsertRequest` 新增: `tpms_cell_size`, `tpms_z_slice`, `max_holes`
- `hole_pattern` 扩展至 11 种有效值

### v0.9.5 — nTopology 级分析套件 + 高级网格操作 + 代码质量加固

**分析套件 (analysis.py)**:
- 壁厚分析: 多射线（6方向）逐顶点内向厚度估计，支持薄壁警告和直方图
- 曲率分析: 离散 Gaussian（角亏法）+ Mean 曲率，逐顶点标量场
- 拔模角分析: 逐面拔模角 + 倒扣/临界比例 + 直方图
- 对称性分析: X/Y/Z 轴平面对称评分（Hausdorff 度量 + cKDTree）+ PCA 主轴
- 悬垂分析: 逐面悬垂检测 + 面积/比例统计 + 临界角度
- BOM 估算: 多组件体积/表面积/估重/估时

**高级网格操作 (mesh_editor.py)**:
- 三种平滑: Laplacian（均匀邻域均值）、Taubin（交替 λ/μ 防缩）、HC（Humphrey 体积保持）
- 等尺重网格化: 细分→简化循环迫近目标边长
- 表面偏移: 沿顶点法线平移
- 增厚: 将曲面网格转为实体（outward/inward/both）

**晶格 & 场驱动 (insert_generator.py + tpms.py)**:
- **11 种晶格模式**: Hex、Grid、Diamond (几何)、Voronoi (Lloyd) + Gyroid、Schwarz-P、Schwarz-D、Neovius、Lidinoid、IWP、FRD (TPMS 隐式场)
- **TPMS 隐式场管线**: 高分辨率 2D 场求值 → scipy.ndimage 形态学极值检测 → 贪心间距过滤 → 自适应半径 (r ∝ |f|)
- **五种密度场**: edge/center/radial/stress/uniform — 连续半径调制 (非二元删除)
- **网孔雕刻升级**: 2 轮边界预细分 + 圆周投射 + 3 轮 Laplacian 平滑 → 更圆润孔洞
- **上限提升**: max_holes 80 → 300

**API 路由 (analysis.py)**:
- 10 个新端点: thickness / curvature / draft / symmetry / overhang / smooth / remesh / thicken / offset / bom
- Pydantic Field 验证 + HTTPException 错误处理 + 日志记录

**前端**:
- WorkflowPipeline: nTopology 风格块状工作流可视化
- EditPanel: 网格健康仪表 + 5 维分析折叠面板 + 高级操作控件
- InsertPanel: 6 种晶格图形选择器 + 场驱动密度控制
- MoldPanel: SPI/VDI 表面纹理选择器 + DesignRulesChecker
- MaterialLibrary: 可复用材料选择组件 (拉伸/硬度/密度属性)
- useAnalysisApi: 10 个 React Query hooks

**代码质量**:
- 修复所有 silent `except Exception: pass` → 添加 `logger.debug/error`
- core/__init__.py 导出 analysis + fea 全部公共符号
- 新增 moldgen/api/__init__.py 包标记
- 新增 tests/test_analysis.py (6 个测试类, 20+ 用例)
- .gitignore 修复 Tauri target 路径通配

### v0.9.3 — 分型面修复 + 支撑板特征重构 + 立柱可视化修复

**分型面咬合修复** (ERR-001):
- 分型面咬合几何体（燕尾/锯齿/阶梯/舌槽）现在先通过 `boolean_intersect` 裁剪到模具实体范围内，再执行上壳体并集/下壳体差集
- 新增 `_robust_boolean_intersect()` 方法（manifold3d + trimesh 多引擎回退）
- 咬合特征不再从模具外侧突出，仅存在于两片壳体接合面

**支撑板特征系统重构** (ERR-002):
- **基础板型** 简化为 `flat`（平板）和 `conformal`（仿形板）两种
- **可选特征** 改为独立开关，可自由组合:
  - `add_mesh_holes`: 表面网孔 — 硅胶渗透通孔
  - `add_ribs`: 加强筋 — 交叉肋条增强刚性
  - `add_interlocking`: 啮合固定 — 燕尾榫/凸起/沟槽/菱形纹
- 前端 UI 对应改为: 板型下拉 + 三个独立特征开关（含子参数折叠面板）
- `generate_plate()` 方法改为渐进式叠加: 基础板 → 网孔 → 加强筋 → 啮合结构

**立柱可视化修复** (ERR-003):
- `InsertPlateViewer` 现在同时加载板体 GLB 和立柱 GLB（独立 Suspense/ErrorBoundary）
- 立柱使用橙色材质区分于绿色板体

**详见**: [错误与教训记录](docs/error-log.md)

### v0.9.2 — 支撑立柱方向修复 + 模具穿孔 + 仿真可视化增强

**支撑立柱系统修复**:
- **方向修正**: 立柱严格沿配置方向（auto/bottom/top/back/front/left/right）延伸，移除之前的径向混合偏移
- **模具穿孔**: 生成支撑板后自动在模具壳体上 Boolean 切割对应圆柱形穿孔（含 0.3mm 间隙），确保立柱与模具壳体嵌合固定
- **采样优化**: 仅选取板面朝向出口侧的采样点，立柱集中在预期面
- **射线追踪改进**: 自动跳过 <0.5mm 的近距离自交叉点

**仿真/FEA 可视化增强**:
- **FEA 材质叠加修复**: FEA 分析结果现在正确叠加于实际模型几何体表面（从 GLB 加载模型网格，映射顶点颜色），而非之前的占位小球
- **浮动可视化工具栏**: 仿真/FEA 的热力图、场切换、流线、表面叠加、动画控制等全部移至视口下方浮动工具栏，左侧面板仅保留核心操作按钮
- **流线热力管**: 流线从 LineBasicMaterial 升级为 TubeGeometry + 热力色映射，管径自适应体素尺度，颜色随充填时间从蓝→绿→黄→红渐变
- **粒子密度提升**: 默认粒子密度从 1× 提升至 2×，默认点大小从 3.0 提升至 4.5，流线默认开启
- **色标条**: FEA 浮动栏内嵌渐变色标条，直观指示低→高值区间

**UI 布局优化**:
- SimPanel 精简为 9 个区块（材料→浇注→仿真→可视化→表面叠加→截面→分析→优化→FEA），可视化控制全部悬浮于视口下方
- 立柱方位选择扩展为 7 个选项（自动/底部/顶部/背面/正面/左侧/右侧）

### v0.9.1 — 支撑板系统修正 + 方向分析修复

**支撑板系统 (内嵌结构加固板) 修正**:
- **修正理解**: 支撑板是置于硅胶教具**内部**的刚性结构加固板，通过锚固结构与硅胶牢固结合，通过细小支撑立柱穿过模具壁定位
- **4种板型**: 平板(flat)、仿形板(conformal)、加强筋板(ribbed)、格栅板(lattice)
- **5种锚固类型**: 贯穿孔(mesh_holes)、凸起(bumps)、沟槽(grooves)、燕尾榫(dovetail)、菱形纹(diamond)
- **支撑立柱系统**: 自动从板面采样点生成穿过模具壁的连接柱，支持方位选择
- **内部包容性**: 板片自动缩放至模型内部，保证最小硅胶层厚度
- **装配验证**: 检查板片边界、厚度、锚固、立柱间距等

**方向分析 GPU 降级修复**:
- 修复 CuPy GPU 路径因 cutlass 库缺失导致的 500 错误
- 新增 try/except 包裹 GPU 分析，自动降级至 CPU 路径

### v0.9.0 — 内骨骼系统重构 + 分型面修复

**分型面生成修复**:
- 修复非平面分型面(燕尾/锯齿/阶梯/舌槽)的渲染问题
- 新增 `_robust_boolean_union` 方法
- 分型面交错特征正确嵌入上壳体、从下壳体减去

### v0.11.0 — 系统整合 + 桌面封装 + 全链路排错

**数据链路修复**:
- **修复 Boolean 类型链**: `advanced.py` sharp-boolean 路径错误地向 `_boolean_op` 传递 `Trimesh` 而非 `MeshData`，且后续 `from_trimesh` 与返回类型矛盾。现改为正确构造 `MeshEditor()` 并传 `MeshData`
- **修复 SDF blend 网格对齐**: 两个不同模型分别计算 SDF 导致网格 shape/origin 不同无法 blend。新增 `mesh_to_sdf_shared()` 在联合包围盒上计算共享网格
- **清理冗余 hasattr 分支**: `from_trimesh` 始终存在，删除所有 `hasattr(MeshData, "from_trimesh")` 保护分支

**日志与报错机制**:
- **后端**: `moldgen/utils/logger.py` 全面升级为控制台 + 文件滚动 + 错误独立文件三路输出；单文件 5MB / 5 轮滚动
- **后端 API**: 新增 `GET /api/v1/system/logs` 和 `GET /api/v1/system/logs/errors` 获取最新日志
- **前端**: 新增全局 `ErrorBoundary` 捕获渲染异常，`window.onerror` + `unhandledrejection` 捕获运行时错误并 toast 弹窗
- **前端控制台面板**: 标题栏新增终端按钮可切换内嵌控制台，实时拉取后端日志，支持 全部/错误 分页与自动刷新

**TypeScript 全修复**:
- `AgentWorkstation.tsx`: `unknown → ReactNode` 修复，使用 `Boolean()` + IIFE 模式
- `useWebSocket.ts`: React 19 `useRef` 缺少初始值修复
- `StatusBar.tsx`, `Toolbar.tsx`, `SettingsDialog.tsx`: 移除未使用 import
- `SimulationViewer.tsx`: `as unknown as Record` 双重断言修复

**Tauri 桌面封装**:
- `lib.rs` 重构: 启动时自动寻找 sidecar 二进制或 Python 环境启动后端，退出时自动杀掉后端进程
- `tauri.conf.json`: 添加 `externalBin` 声明 sidecar、NSIS 中文安装向导
- 新增 `scripts/build_backend.py`: PyInstaller 一键打包后端为 `moldgen-server.exe`，自动复制到 Tauri binaries 目录
- `.gitignore` 更新: 新增 `build_tmp/`, `dist_backend/`, `binaries/`, `data/logs/`

## License

待定 (计划采用 AGPL-3.0 或 MIT)
