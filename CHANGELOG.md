# 变更日志 (Changelog)

所有重大变更均记录于此文件。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

> 📖 回到 [README](README.md) | [文档中心](docs/README.md) | [路线图](docs/06-roadmap.md)

---

## [Unreleased]

### 新增
- **蒙皮模具系统 v2** — 软硬结合教具的模芯 + 外模 + 定位特征全流程生成
  - SDF 内偏移模芯：形态学闭合 + 高斯 EDT 平滑 + Marching Cubes + 自动简化
  - 曲率自适应变厚度蒙皮（凸面加厚、平面减薄）
  - Boolean 差集水密空心化 + 方向感知排液孔
  - 碰撞感知定位特征（圆销/方键自适应布局）
  - 模芯底部支撑柱系统（灌注时悬浮定位）
  - 全顶点厚度图可视化 + 均匀度评分
  - API: `POST /generate-skin`, `GET /thickness-map`

### 修复
- 仿形板四角突出（添加投影轮廓裁剪）
- 灌注口贯穿模具两侧（限制到局部壳体厚度）
- 仿真热力图场切换无效（修复归一化范围）
- 模芯生成体素化仅返回表面而非填充内部（添加 `.fill()` 调用）
- 非水密模型修复不再使用 `convex_hull`（改为体素填充修复）

---

## [0.11.0] — 2026-04

### 新增
- **Tauri 桌面封装**: 自动 sidecar 后端启动/退出管理
- **日志系统升级**: 控制台 + 文件滚动 + 错误独立文件三路输出
- **前端错误边界**: 全局 ErrorBoundary + 运行时错误 toast 弹窗
- **前端控制台面板**: 实时后端日志查看，支持全部/错误分页

### 修复
- Boolean 类型链: `advanced.py` sharp-boolean 传参类型错误
- SDF blend 网格对齐: 不同模型 SDF 网格 shape/origin 不匹配
- TypeScript 全修复: React 19 useRef、未使用 import、类型断言

---

## [0.10.0] — 2026-03

### 新增
- **SDF 隐式场引擎** (`distance_field.py`)
  - Smooth/Sharp boolean、场操作（offset/shell/blend/remap/blur）
  - 场驱动变厚度壳 (3 种场类型)
- **SIMP 拓扑优化** (`topology_opt.py`) — 2D + 3D
- **3D 体积晶格** (`lattice.py`) — 杆件 5 种 + TPMS 7 种 + Voronoi 泡沫
- **干涉/间隙分析** (`interference.py`)
- **网格质量分析**: 宽高比、拓扑指标、紧凑度
- API: `/api/v1/advanced/` 全套路由

---

## [0.9.6] — 2026-03

### 新增
- **TPMS 隐式场晶格库** (`tpms.py`) — 7 种数学精确 TPMS 曲面
- 5 种空间场连续半径调制 (edge/center/radial/stress/uniform)
- 网孔雕刻升级: 预细分 → 面片删除 → 圆周投射 → Laplacian 平滑

---

## [0.9.5] — 2026-02

### 新增
- **nTopology 级分析套件**: 壁厚/曲率/拔模角/对称性/悬垂/BOM
- **高级网格操作**: 三种平滑 + 等尺重网格化 + 表面偏移 + 增厚
- **11 种网孔图案**: 4 几何 + 7 TPMS
- **工作流管线** (WorkflowPipeline) + 网格健康仪表 + 设计规则校验
- API: 10 个分析端点 + React Query hooks

---

## [0.9.3] — 2026-02

### 修复
- 分型面咬合几何体从模具外侧突出 → `boolean_intersect` 裁剪
- 支撑板特征系统重构: 板型 + 可选特征独立开关
- 立柱可视化: 板体 + 立柱独立加载

---

## [0.9.2] — 2026-01

### 修复
- 支撑立柱方向修正: 严格沿配置方向延伸
- 模具穿孔: 自动 Boolean 切割立柱通孔 (含 0.3mm 间隙)
- FEA 材质叠加修复: 正确叠加于实际模型几何体

### 改进
- 流线热力管 (TubeGeometry + 热力色映射)
- 浮动可视化工具栏

---

## [0.9.1] — 2026-01

### 修复
- 方向分析 GPU 降级: CuPy cutlass 缺失时自动降级至 CPU

### 新增
- 支撑板系统: 4 种板型 + 5 种锚固 + 支撑立柱

---

## [0.9.0] — 2025-12

### 新增
- 内骨骼系统重构
- 分型面生成修复 (非平面分型面渲染)

---

## [0.1.0–0.8.x] — 2025

- P0~P4 基础设施、模型处理、模具生成、仿真优化、AI Agent 系统搭建

---

[Unreleased]: ../../compare/v0.11.0...HEAD
[0.11.0]: ../../releases/tag/v0.11.0
[0.10.0]: ../../releases/tag/v0.10.0
[0.9.6]: ../../releases/tag/v0.9.6
[0.9.5]: ../../releases/tag/v0.9.5
[0.9.3]: ../../releases/tag/v0.9.3
[0.9.2]: ../../releases/tag/v0.9.2
[0.9.1]: ../../releases/tag/v0.9.1
[0.9.0]: ../../releases/tag/v0.9.0
