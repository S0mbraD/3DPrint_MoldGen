# 开发路线图与阶段计划

## 总体时间线

```
P0 ──── P1 ──── P2 ──── P3 ──── P4 ──────── P5 ──── P6 ──── P7
基础     模型     模具     仿真     AI集成      插板     桌面     发布
设施     处理     生成     优化   +6大Agent    复合     完善
(2周)   (3周)   (4周)   (3周)    (5周)★     (3周)   (3周)   (2周)
                                                        ─────────
                                                        总计: 23-28周
```

## Phase 0: 项目基础设施 (2 周)

### 目标
Conda 环境 + Tauri 桌面骨架 + GPU 验证 + AI API 联通。

### 任务清单

- [x] **P0.1** Conda 环境配置 ✅
  - environment.yml 适配实际硬件 (RTX 4060 Ti 16GB)
  - moldgen conda env (Python 3.11) 创建成功
  - 核心 pip 包安装验证通过

- [x] **P0.2** 后端项目骨架（含 AI 路由）✅
  - FastAPI 项目结构完整 (api/core/gpu/ai/agents/prompts)
  - 47 个 Python 模块文件（含骨架桩文件）
  - GPU 检测 (nvidia-smi) — RTX 4060 Ti 16380 MB
  - AI 配置管理 (pydantic-settings, env vars)
  - REST API: system/models/molds/simulation/export/ai_chat/ai_agent
  - WebSocket: task_progress/ai_chat/ai_agent
  - 7 个 pytest 通过, ruff lint clean
  - 服务启动验证: http://127.0.0.1:8000/docs

- [ ] **P0.3** 前端 + Tauri 桌面骨架
  - Vite + React + R3F + Framer Motion
  - 深色工作站主题
  - Tauri 2.0 + Python Sidecar

- [ ] **P0.4** GPU 环境验证（Numba CUDA / CuPy / cuBVH）

- [ ] **P0.5** AI API 联通测试
  - DeepSeek 对话测试
  - 通义万相图像生成测试
  - Tripo3D 3D 模型生成测试
  - Qwen-VL 图像分析测试

### 交付物
- [x] `conda activate moldgen` 一键激活环境
- [x] FastAPI 后端可启动 (`python -m uvicorn moldgen.main:app`)
- [x] OpenAPI 文档可访问 (`/docs`)
- [ ] Tauri 桌面应用可启动
- [ ] 4 个 AI API 均可调用

---

## Phase 1: 模型导入与编辑 (3 周)

### 目标
多格式导入、修复、细化/简化、编辑、GPU 方向分析。

### 任务清单
- [ ] P1.1-P1.11（同前版本，含 mesh_io/repair/editor/orientation + 前端）

### 里程碑
- **M1**: 多格式导入 + 修复 + 细化/简化
- **M2**: GPU 方向分析正确

---

## Phase 2: 模具生成 (4 周)

### 任务清单
- [ ] P2.1-P2.10（同前版本，含 parting/mold_builder/gating + 多格式导出 + 前端）

### 里程碑
- **M3**: 简单模型双片模具
- **M4**: 复杂模型多片壳 + FDM 打印验证

---

## Phase 3: 灌注仿真与优化 (3 周)

### 任务清单
- [ ] P3.1-P3.7（同前版本，含 flow_sim L1/L2 + optimizer + 前端可视化）

### 里程碑
- **M5**: GPU 仿真性能达标
- **M6**: 仿真+优化闭环

---

## Phase 4: AI 集成与内置 Agent 系统 (5 周) ★核心新增 ✅ 完成

### 目标
完整的 AI 子系统 + 6大内置Agent自动执行引擎 + 悬浮球/Agent工作站前端。

### 第一阶段: AI 基础服务 (Week 1)

- [x] **P4.1** AI 服务统一层 ✅
  - AIServiceManager 实现
  - DeepSeek 对话封装（含流式/Function Calling）
  - 通义万相图像生成封装 (cloud + local SDXL/FLUX)
  - Tripo3D 3D 模型生成封装 (cloud + local TripoSR)
  - Qwen-VL 多模态分析封装
  - 错误处理 + provider 降级策略
  - 本地模型管理器 (下载/加载/卸载/VRAM管理)
  - 云端↔本地双后端透明切换

### 第二阶段: Agent 执行引擎 (Week 2)

- [ ] **P4.2** Agent 执行引擎核心
  - BaseAgent 抽象基类
  - AgentExecutionEngine（主调度引擎）
  - ExecutionContext（跨Agent共享上下文）
  - ExecutionPlan（任务计划数据结构）
  - 三种执行模式（Auto/SemiAuto/Step）
  - 确认规则表（CONFIRMATION_RULES）

- [ ] **P4.3** 全局工具注册表
  - ToolRegistry（Function Calling → 实际函数映射）
  - 所有软件功能注册为可调用工具（60+工具）
  - 工具分类（model/mold/insert/sim/ai/export）
  - 工具JSON Schema 定义
  - 工具执行结果格式化

### 第三阶段: 6大内置Agent (Week 3)

- [ ] **P4.4** MasterAgent — 总控调度
  - 关键词快速路由表（<10ms响应）
  - LLM意图分类（DeepSeek Function Calling）
  - 预定义流水线模板（full_from_text/full_from_model/mold_only 等）
  - LLM自由任务分解
  - 多Agent协调调度（拓扑排序执行）
  - 中途插入指令处理

- [ ] **P4.5** ModelAgent — 模型处理
  - 17个工具注册（load/repair/edit/transform/export...）
  - 自动执行链（导入→质量检查→自动修复→报告）
  - 智能决策规则（面数过高自动建议简化等）

- [ ] **P4.6** MoldDesignAgent — 模具设计
  - 15个工具注册（orientation/parting/shells/gating...）
  - 全自动流水线定义（AUTO_PIPELINE）
  - 条件确认（方向评分<0.7时确认）
  - 失败自动重试策略

- [ ] **P4.7** InsertAgent — 支撑板设计
  - 11个工具注册（analyze/generate/anchor/validate...）
  - 器官类型→策略映射（ORGAN_STRATEGY）
  - AI辅助分析（Qwen-VL解剖识别 + 几何分析 + LLM综合推理）
  - 方案展示+确认+生成流程

- [ ] **P4.8** SimOptAgent — 仿真优化
  - 12个工具注册（sim/defect/optimize/compare...）
  - 自动优化循环（缺陷→针对性调参→重仿真，max 5轮）
  - 智能仿真级别选择（根据模型大小和GPU状态）

- [ ] **P4.9** CreativeAgent — 创意生成
  - 7个工具注册（prompt/image/3d/review...）
  - 提示词优化策略（中文→英文+修饰词+专业术语）
  - 全自动流程（优化→生成图→选择→3D→审查）

### 第四阶段: Agent提示词与记忆 (Week 4)

- [ ] **P4.10** 6大Agent系统提示词
  - ai/prompts/ 下每个Agent对应提示词文件
  - 角色定义 + 可用工具 + 执行规则 + 决策逻辑 + 错误处理
  - 提示词迭代测试与优化

- [ ] **P4.11** Agent 记忆系统
  - 短期记忆（会话级对话历史+上下文+偏好提取）
  - 长期记忆（SQLite持久化：用户偏好/常用器官/成功配置）
  - 记忆查询与推荐（基于历史推荐参数）

- [ ] **P4.12** 错误恢复与降级
  - AI API 超时重试+provider切换
  - 工具执行失败→调参重试
  - 验证失败→自动修复
  - GPU OOM→降精度重试→CPU降级

### 第五阶段: 前端 (Week 5)

- [ ] **P4.13** 前端 — AI 悬浮球
  - 60px 圆形悬浮球（呼吸灯动画，可拖拽）
  - 侧边滑出对话面板（400px，Framer Motion）
  - 消息气泡（Markdown渲染 + 图片 + 3D缩略图）
  - 流式打字效果（SSE/WebSocket）
  - 操作确认按钮（确认/拒绝/修改）
  - 复杂任务→自动转入Agent工作站

- [ ] **P4.14** 前端 — Agent 工作站
  - 全屏/半屏工作站面板
  - **执行模式选择器**（Auto/Semi/Step运行时切换）
  - **实时执行日志**（时间戳+Agent名+操作内容+状态图标）
  - **确认决策卡片**（问题+选项按钮+自由文本输入）
  - **Agent状态栏**（6个Agent图标+颜色状态指示）
  - **快捷操作**（跳过/回退/暂停/全自动继续）
  - 中途对话插入指令
  - WebSocket实时事件流 + 自动重连

- [ ] **P4.15** AI 设置面板
  - API Key 配置（安全存储）
  - Agent启用/禁用
  - 默认执行模式设置
  - 用量统计展示
  - 每日额度设置

### 里程碑
- **M7**: 文字描述 → 生成器官3D模型并加载到场景
- **M8**: AI 对话辅助完成支撑板设计
- **M8b**: "做一个肝脏模具" → Agent全自动完成完整流水线

---

## Phase 5: 复合结构与支撑板 (3 周) ✅ 完成

### 目标
完整的支撑板生成系统（几何算法 + AI 辅助），一体化装配验证。

### 任务清单

- [ ] **P5.1** insert_generator — 几何算法
  - 自动位置分析（大平面/分型面/厚壁）
  - 板体裁剪、边缘倒角

- [ ] **P5.2** 锚固结构生成
  - 5种类型：网孔/凸起/沟槽/燕尾/菱形纹

- [ ] **P5.3** 一体化装配设计
  - 模具壳体中的支撑板定位槽
  - 安装路径验证
  - 灌注时固定方式

- [ ] **P5.4** 装配验证
  - 干涉/厚度/安装路径/FDM 检查

- [ ] **P5.5** 用户编辑 + AI 调整
  - 拖拽调整位置
  - 锚固参数实时调节
  - AI 对话微调

- [ ] **P5.6** 浇注系统适配 + 仿真适配
  - 避让支撑板
  - 仿真中考虑支撑板

- [ ] **P5.7** 前端 — 支撑板可视化与编辑

### 里程碑
- **M9**: 支撑板自动生成 + 一体化装配
- **M10**: 复合结构模具 FDM 打印验证

---

## Phase 6: 桌面应用完善 (3 周) ✅ 完成

### 任务清单
- [x] P6.1-P6.8（完整工作流 UI / 项目管理 / 材料库 / 动画 / 快捷键 / 设置）

### 里程碑
- **M11**: 专业级桌面应用体验

---

## Phase 6.6: nTopology 级分析套件 (1 周) ✅ 完成

### 目标
参照 nTopology 的 Implicit Modeling 和 DfAM 工作流，为项目增加专业级几何分析、高级网格操作、晶格库和设计校验能力。

### 已完成任务

- [x] **P6.6.1** 五维几何分析 (analysis.py)
  - 壁厚分析 (多射线逐顶点, 直方图, 薄壁警告)
  - 离散曲率 (Gaussian 角亏法 + Mean cotangent)
  - 拔模角分析 (逐面, 倒扣/临界比例)
  - 对称性分析 (cKDTree Hausdorff + PCA)
  - 悬垂分析 (3D 打印面法线检测)
  - BOM 估算 (多组件体积/重量/时间)

- [x] **P6.6.2** 高级网格操作 (mesh_editor.py)
  - Laplacian / Taubin / HC 三种平滑
  - 等尺重网格化 (subdivide→decimate)
  - 表面偏移 (法线平移)
  - 增厚 (曲面→实体, outward/inward/both)

- [x] **P6.6.3** 晶格库 + 场驱动 (insert_generator.py)
  - 6 种晶格: Hex, Grid, Gyroid (TPMS), Schwarz-P (TPMS), Diamond, Voronoi
  - 3 种密度场: 边缘, 曲率, 均匀
  - Lloyd relaxation for Voronoi

- [x] **P6.6.4** Analysis API (api/routes/analysis.py)
  - 10 个端点, Pydantic Field 验证, HTTPException, 日志
  - asyncio.to_thread 异步执行

- [x] **P6.6.5** 前端 UI
  - WorkflowPipeline (块状工作流)
  - 5 维分析折叠面板 + 直方图
  - 网格健康仪表 (加权评分)
  - 晶格图形选择器 + 场驱动密度
  - 表面纹理选择器 + DesignRulesChecker
  - MaterialLibrary 组件
  - useAnalysisApi hooks (10 个)

- [x] **P6.6.6** 代码质量
  - Silent except→logged except
  - core/__init__.py 导出补全
  - test_analysis.py (20+ 用例)
  - .gitignore Tauri 路径修复

### 里程碑
- **M11b**: nTopology 级分析 + 高级操作 + 晶格库完整可用

---

## Phase 6.7: TPMS 隐式场晶格库重写 + 网孔质量升级 (0.5 周) ✅ 完成

### 目标
仿照 nTopology 的 TPMS lattice 功能，重写晶格/网孔生成算法，使用数学精确的 TPMS 隐式场替代旧的近似实现，大幅提升网孔图案质量和圆润度。

### 完成项

- [x] `moldgen/core/tpms.py` — 7 种 TPMS 隐式场 (Gyroid, Schwarz-P, Schwarz-D, Neovius, Lidinoid, IWP, FRD)
- [x] 2D 场求值 + 形态学极值检测孔位算法 (scipy.ndimage.maximum_filter)
- [x] 自适应半径: r ∝ |f| (远离零等值面的区域孔更大)
- [x] 5 种场驱动连续半径调制 (edge/center/radial/stress/uniform)
- [x] `_carve_holes` 四阶段管线: 预细分 → 删除 → 圆周投射 → Laplacian 平滑
- [x] `_subdivide_near_holes()` 2 轮局部细分 [0.7r, 1.3r] 环带
- [x] InsertConfig 新参数: tpms_cell_size, tpms_z_slice, max_holes
- [x] API 路由更新 + 前端 LeftPanel TPMS 选择器 (两行: 几何 4 种 + TPMS 7 种)
- [x] 文档更新: algorithms, modules, error-log, README, roadmap

### 里程碑
- **M11c**: TPMS 隐式场精确晶格 + 网孔质量显著提升

---

## Phase 6.8: nTopology 全功能对标 — 隐式引擎 + TO + 3D 晶格 + 干涉 (1 周) ✅ 完成

### 目标
仿照 nTopology 的隐式建模引擎、拓扑优化、3D 晶格、装配干涉分析等核心功能，全面补齐项目能力短板。

### 完成项

- [x] `moldgen/core/distance_field.py` — SDF 隐式场引擎
  - mesh_to_sdf, smooth/sharp boolean, field 操作全集
  - 场驱动变厚度壳 (field_driven_shell)
  - Marching Cubes iso-surface 提取
- [x] `moldgen/core/topology_opt.py` — SIMP 拓扑优化
  - 2D 平面应力 + 3D 六面体砖单元
  - OC 更新 + 密度滤波 + 3 种 BC
  - density_to_mesh (Marching Cubes)
- [x] `moldgen/core/lattice.py` — 3D 体积晶格
  - 杆件: BCC/FCC/Octet/Kelvin/Diamond + 场驱动变杆径
  - TPMS 体积: 7 种 TPMS 壳体 + SDF 裁剪 + 变壁厚
  - Voronoi 泡沫: Lloyd 松弛 + k-NN 壁面
- [x] `moldgen/core/interference.py` — 干涉/间隙分析
  - 双向最近点有符号距离 + 体素干涉体积
  - 多零件装配全对检查
- [x] `moldgen/core/analysis.py` — 网格质量分析
  - 宽高比、角度、边长统计、拓扑、紧凑度
- [x] `moldgen/api/routes/advanced.py` — 10 个新 API 端点
- [x] 前端 LeftPanel: 网格质量、拓扑优化、变厚壳、3D 晶格面板
- [x] `useAdvancedApi.ts` hooks
- [x] 文档: algorithms, modules, roadmap, README, error-log

### 里程碑
- **M11d**: nTopology 全功能对标完成 — SDF + TO + 3D Lattice + Interference

---

## Phase 6.9: 全链路数据修复 + 日志机制 + 桌面封装 (1 周)

### 任务清单
- [x] P6.9.1 修复 `advanced.py` Boolean / Lattice / Shell 类型链断裂
- [x] P6.9.2 新增 `mesh_to_sdf_shared()` 共享网格 SDF 对齐
- [x] P6.9.3 后端日志三路输出 (控制台+文件滚动+错误独立)
- [x] P6.9.4 后端日志 API (`/system/logs`, `/system/logs/errors`)
- [x] P6.9.5 前端 `ErrorBoundary` + 全局 JS 错误 / Promise rejection 捕获
- [x] P6.9.6 前端内嵌控制台面板 (`ConsolePanel`) 实时日志查看
- [x] P6.9.7 TypeScript 全量修复 (AgentWorkstation, useWebSocket, SimulationViewer 等)
- [x] P6.9.8 Tauri `lib.rs` sidecar 启动/退出管理
- [x] P6.9.9 `scripts/build_backend.py` PyInstaller 后端打包
- [x] P6.9.10 `tauri.conf.json` externalBin + NSIS 配置

### 里程碑
- **M11e**: 全链路数据完整 + 日志可观测 + 桌面构建就绪

---

## Phase 7: 测试与发布 (2 周)

### 任务清单
- [ ] P7.1 集成测试（含 AI 工作流端到端测试）
- [x] P7.2 PyInstaller 打包（含 AI SDK + CUDA）— `scripts/build_backend.py`
- [x] P7.3 Tauri 构建 Windows 安装包 — `npm run tauri:build`
- [ ] P7.4 文档 + 发布

### 里程碑
- **M12**: Windows 安装包可用
- **M13**: v0.1.0 发布

---

## 里程碑总览

| # | 里程碑 | Phase |
|---|--------|-------|
| M0 | Tauri 骨架 + Conda 环境 + AI API 联通 | P0 |
| M1 | 多格式导入 + 编辑 | P1 |
| M2 | GPU 方向分析 | P1 |
| M3 | 双片模具 | P2 |
| M4 | 多片壳 + FDM 验证 | P2 |
| M5 | GPU 仿真性能达标 | P3 |
| M6 | 仿真+优化闭环 | P3 |
| M7 | AI 生成器官3D模型 | P4 ★ |
| M8 | AI 辅助支撑板设计 | P4 ★ |
| M8b | **Agent全自动流水线** (一句话→完整模具) | P4 ★★ |
| M9 | 支撑板一体化装配 | P5 |
| M10 | 复合模具打印验证 | P5 |
| M11 | 专业桌面应用 | P6 |
| M11b | nTopology 级分析+高级操作+晶格库 | P6.6 |
| M11c | TPMS 隐式场精确晶格+网孔质量升级 | P6.7 |
| M11d | nTopology 全功能对标 (SDF+TO+Lattice+Interference) | P6.8 |
| M11e | 全链路数据修复+日志机制+控制台面板 | P6.9 |
| M12 | Windows 安装包 (Tauri + PyInstaller sidecar) | P7 |
| M13 | v0.1.0 发布 | P7 |

## MVP 定义

**MVP = P0 + P1 + P2 + P4(AI+Agent核心)**
- Conda 环境 + Tauri 桌面应用
- 多格式导入 + 编辑 + GPU 方向分析
- 双片/多片壳模具 + 浇注系统 + 多格式导出
- AI 悬浮球对话 + 基础图像/3D 生成
- **内置Agent半自动执行**（MasterAgent路由 + 至少ModelAgent/MoldDesignAgent自动执行）
- **Agent工作站基础可用**（执行日志+确认卡片+模式切换）
- 医学教具工作流基础可用

## 医学教具测试模型库

| 器官 | 难度 | 预期壳数 | 支撑板 | 来源 |
|------|------|---------|--------|------|
| 肝脏 | ⭐⭐⭐ | 2-3 | 推荐 | AI生成/CT分割 |
| 肾脏 | ⭐⭐ | 2 | 可选 | AI生成/CT分割 |
| 心脏 | ⭐⭐⭐⭐ | 4-6 | 推荐 | AI生成/CT分割 |
| 脑 | ⭐⭐⭐⭐ | 3-4 | 推荐 | AI生成/CT分割 |
| 胃 | ⭐⭐ | 2-3 | 可选 | AI生成 |
| 血管段 | ⭐⭐⭐ | 2 | 推荐 | CT分割 |
| 骨骼段 | ⭐⭐ | 2 | 否 | CT分割 |
| 皮肤/组织片 | ⭐ | 2 | 底板 | AI生成 |
