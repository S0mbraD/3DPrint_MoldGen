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

- [ ] **P4.1** AI 服务统一层
  - AIServiceManager 实现
  - DeepSeek 对话封装（含流式/Function Calling）
  - 通义万相图像生成封装
  - Tripo3D 3D 模型生成封装
  - Qwen-VL 多模态分析封装
  - 错误处理 + provider 降级策略
  - API 用量统计 + 成本追踪

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
- [ ] P6.1-P6.8（完整工作流 UI / 项目管理 / 材料库 / 动画 / 快捷键 / 设置）

### 里程碑
- **M11**: 专业级桌面应用体验

---

## Phase 7: 测试与发布 (2 周)

### 任务清单
- [ ] P7.1 集成测试（含 AI 工作流端到端测试）
- [ ] P7.2 PyInstaller 打包（含 AI SDK + CUDA）
- [ ] P7.3 Tauri 构建 Windows 安装包
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
| M12 | Windows 安装包 | P7 |
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
