# AI 辅助开发 Prompt 指令集

本文档提供用于指导 AI (如 Claude Opus 4.6) 辅助开发 MoldGen 项目的 Prompt 模板。
每个 Prompt 对应一个具体的开发任务，包含足够的上下文让 AI 理解项目全貌后聚焦执行。

---

## 使用说明

1. 每次新会话，先提供 **项目上下文 Prompt**（Section 0）
2. 然后根据当前开发阶段选择对应的 **任务 Prompt**
3. 每个 Prompt 都是自包含的，包含必要的技术约束和验收标准
4. 用 `[PLACEHOLDER]` 标记的地方需根据实际情况替换

---

## Section 0: 项目上下文 Prompt（每次会话开头使用）

```
你正在参与开发 MoldGen — 一款面向临床教学与手术教具开发的 AI 驱动智能模具生成桌面工作站。

## 项目概述
MoldGen 是一个 Tauri 2.0 桌面应用，主要用于生成病理/生理器官组织模型的硅胶灌注模具。
系统深度集成 AI 能力（对话/图像生成/3D模型生成），支持全流程：
1. AI 对话驱动：用户通过 AI 悬浮球/Agent工作站描述需求，AI 自动生成器官模型
2. 多格式模型导入（STL/OBJ/FBX/3MF/STEP）、网格修复、细化/简化、自定义编辑
3. GPU 加速的最优脱模方向分析（可见性分析、倒扣检测、多准则评分）
4. 分型线提取与分型面生成
5. 多片壳模具几何构建（壳体偏移、定位销、螺栓孔、FDM适配）
6. AI 辅助的复合结构设计：硅胶灌注 + 内嵌打印支撑板（锚固结构，一体置入模具）
7. 浇注系统设计（浇口、流道、排气孔，适配支撑板避让）
7. CPU/GPU 双加速的灌注流动仿真与可视化
8. 基于规则的自动优化迭代
9. 多格式模具文件导出（STL/OBJ/3MF/STEP）

## 技术栈
- 桌面框架: Tauri 2.0 (Rust shell + WebView2)
- 后端: Python 3.11+ / FastAPI / trimesh / manifold3d / open3d / pyassimp
- GPU: Numba CUDA / CuPy / cuBVH (目标硬件 RTX 4060 Ti, 8GB VRAM)
- AI 服务: DeepSeek V3 (对话/Agent) / 通义万相 (图像) / Tripo3D (3D生成) / Qwen-VL (视觉)
  所有 AI 通过 OpenAI 兼容 SDK 统一接入
- 前端: React 18 + TypeScript / Three.js + React Three Fiber / WebGPU
- UI: Tailwind CSS + shadcn/ui / Framer Motion (UI动画) / @react-spring/three (3D动画)
- 状态管理: Zustand + TanStack Query
- 通信: REST API + WebSocket + SSE (AI流式) / GLB 二进制传输
- 环境: Conda (Mambaforge) / 构建: Vite + uvicorn + PyInstaller

## 代码规范
- Python: ruff 格式化, 类型注解, docstring (Google style)
- TypeScript: ESLint + Prettier, 严格模式
- 提交信息: Conventional Commits
- 测试: pytest (后端) / vitest (前端)

## UI/UX 设计规范
- 深色主题优先，专业 CAD 工作站风格
- Framer Motion 驱动所有 UI 过渡（弹簧物理动画）
- 3D 动画使用 @react-spring/three
- 面板展开: spring, stiffness 300, damping 30
- 页面切换: duration 300ms, easeInOut
- 所有动画可关闭（无障碍）

## 项目结构
后端: moldgen/ 按 api/ core/ gpu/ models/ services/ 组织
前端: frontend/src/ 按 components/ (viewer/editor/panels/animation) hooks/ stores/ services/ 组织
桌面: src-tauri/ Rust 层

## GPU 双路径策略
所有计算模块同时实现 GPU (CUDA) 和 CPU (NumPy/SciPy) 路径。
GPUCompute 类自动检测 CUDA 可用性，不可用时降级到 CPU。

请根据以上上下文执行后续指令。在每个任务中，请：
1. 先分析任务需求和技术挑战
2. 给出清晰的实现方案
3. 编写可运行的代码（含类型注解）
4. 实现 GPU/CPU 双路径（如涉及计算密集型任务）
5. 包含必要的错误处理和降级逻辑
6. 提供对应的单元测试
```

---

## Section 1: Phase 0 — 项目基础设施

### Prompt 1.1: 初始化后端项目

```
## 任务：初始化 MoldGen 后端项目骨架

### 要求：
1. 创建以下目录结构：
   moldgen/
   ├── __init__.py
   ├── main.py              # FastAPI 入口
   ├── config.py             # pydantic-settings 配置
   ├── api/
   │   ├── routes/
   │   │   ├── models.py     # 模型上传/查询
   │   │   ├── edit.py       # 模型编辑
   │   │   ├── molds.py      # 模具生成
   │   │   ├── inserts.py    # 插板生成
   │   │   ├── simulation.py # 仿真
   │   │   ├── export.py     # 多格式导出
   │   │   └── system.py     # GPU状态/系统信息
   │   ├── schemas/
   │   └── websocket.py
   ├── core/
   │   ├── mesh_io.py, mesh_repair.py, mesh_editor.py
   │   ├── orientation.py, parting.py
   │   ├── mold_builder.py, insert_generator.py, gating.py
   │   ├── flow_sim.py, optimizer.py
   ├── gpu/
   │   ├── device.py         # GPU 检测与管理
   │   ├── ray_cast.py       # cuBVH 光线投射
   │   ├── sdf.py            # CUDA SDF
   │   ├── flow_kernel.py    # CUDA 流动求解
   │   └── fallback.py       # CPU 降级
   ├── models/
   ├── services/
   └── utils/

2. main.py: FastAPI + CORS(localhost:1420 for Tauri) + WebSocket + 静态文件
3. config.py: 上传目录、GPU配置、最大文件大小等
4. gpu/device.py: CUDA 检测、设备信息获取、VRAM 查询
5. api/routes/system.py: GET /api/v1/system/gpu 返回 GPU 信息
6. 文件上传接口支持 STL/OBJ/FBX/3MF/STEP/PLY
7. requirements.txt

### 验收标准：
- uvicorn 启动正常
- /api/v1/system/gpu 返回 RTX 4060 Ti 信息
- 上传文件正常工作
- /docs OpenAPI 文档可访问
```

### Prompt 1.2: 初始化 Tauri 桌面应用

```
## 任务：创建 Tauri 2.0 + React + Three.js 桌面应用骨架

### 要求：
1. 使用 Tauri 2.0 创建项目
2. 前端: Vite + React 18 + TypeScript + Tailwind CSS + shadcn/ui
3. 配置 R3F (React Three Fiber) 基础 3D 场景
4. 配置 Framer Motion

5. Tauri 配置:
   - Python Sidecar（externalBin 配置）
   - 窗口: 标题 "MoldGen", 默认最大化, 深色装饰
   - 文件拖拽权限
   - shell 权限（启动 sidecar）
   - fs 权限（读写项目目录）

6. 布局设计（专业 CAD 工作站风格）:
   - 顶部: 自定义标题栏（Tauri 无装饰窗口 + 自定义拖拽区域 + 窗口按钮）
   - 顶部下方: 工具栏 + 步骤导航条
   - 左侧: 可折叠参数面板（Framer Motion 弹簧动画）
   - 中央: 3D 场景（R3F Canvas, 占主要空间）
   - 右侧: 可折叠信息面板
   - 底部: 状态栏（GPU状态/内存/面片数/操作提示）

7. 3D 场景:
   - WebGPU 渲染器（降级 WebGL）
   - OrbitControls
   - 环境光 + 方向光
   - 坐标轴 + 网格地板
   - 暗色背景（#1a1a2e 到 #16213e 渐变）

8. 深色主题:
   - 背景: #0f0f14 / #1a1a24
   - 面板: #1e1e2e
   - 强调: #6366f1 (紫蓝)
   - 成功: #22c55e
   - 警告: #f59e0b
   - 危险: #ef4444

### 验收标准：
- `tauri dev` 启动桌面窗口
- 深色专业主题
- 3D 场景可旋转缩放
- 面板展开/折叠有弹簧动画
- Python sidecar 自动启动并连接
```

### Prompt 1.3: GPU 计算层实现

```
## 任务：实现 GPU 计算统一抽象层 (gpu/ 模块)

### 目标硬件：RTX 4060 Ti, 8GB VRAM, Compute Capability 8.9

### 要求：

1. gpu/device.py — GPU 设备管理
   - detect_cuda() → bool
   - get_device_info() → GPUInfo（设备名/VRAM/CC/驱动版本）
   - get_memory_usage() → dict（已用/可用/总量）
   - 异常安全：CUDA 不可用时不崩溃

2. gpu/ray_cast.py — cuBVH 光线投射
   - build_bvh(mesh) → BVHHandle
   - ray_intersect_batch(origins, directions, bvh) → hit_mask
   - 批量处理：支持 100K+ 光线
   - CPU 降级：trimesh.ray.intersects_any

3. gpu/sdf.py — CUDA SDF 计算
   - compute_sdf(mesh, resolution) → 3D ndarray
   - Numba CUDA kernel 实现
   - CPU 降级：trimesh proximity + scipy ndimage

4. gpu/flow_kernel.py — CUDA 流动求解核
   - voxelize(mesh, resolution) → 3D binary grid
   - assemble_laplacian(grid, K) → sparse matrix (CuPy)
   - sparse_solve(A, b) → solution (CuPy solver)
   - CPU 降级：scipy.sparse.linalg

5. gpu/fallback.py — CPU 降级实现
   - 每个 GPU 函数的对应 CPU 版本
   - 自动选择逻辑

6. __init__.py — GPUCompute 主类
   - 单例模式
   - 自动检测并选择 GPU/CPU
   - 统一接口

### 性能目标（RTX 4060 Ti）：
- BVH 构建: <100ms (50K 面片)
- 光线投射 100K rays: <50ms (GPU) vs ~500ms (CPU embree)
- SDF 128³: <200ms (GPU) vs ~5s (CPU)
- 稀疏求解 128³: <1s (GPU) vs ~10s (CPU)

### 测试：
- GPU 可用时使用 GPU 路径
- 强制 CPU 模式测试降级
- 精度对比：GPU vs CPU 结果误差 < 1e-4
```

---

## Section 2: Phase 1 — 模型处理与编辑

### Prompt 2.1: 多格式网格 IO

```
## 任务：实现支持 FBX 等多格式的 mesh_io 模块

### 要求：

1. MeshData 类（同架构文档定义）
2. MeshIO.load() 支持:
   - STL/OBJ/3MF/PLY/glTF — trimesh 原生
   - FBX/DAE/3DS — pyassimp 后端
     * 需过滤骨骼/动画/材质，仅保留几何
     * 应用节点层级变换矩阵
     * 多网格合并
   - STEP/STP — cascadio (可选，降级提示安装)
3. MeshIO.export() 支持: STL/OBJ/3MF/PLY/GLB/STEP
4. MeshIO.export_multi() 批量导出（模具壳体 + 插板分文件）
5. MeshIO.to_glb() 二进制输出

### FBX 特殊处理：
```python
def _load_fbx(filepath):
    import pyassimp
    scene = pyassimp.load(str(filepath), 
                          processing=pyassimp.postprocess.aiProcess_Triangulate |
                                     pyassimp.postprocess.aiProcess_JoinIdenticalVertices)
    # 遍历场景图，收集所有网格并应用变换
    # 合并为单一 MeshData
    # 释放场景资源
```

### 测试：
- 加载各格式测试文件
- FBX 含骨骼/动画的文件正确过滤
- 单位转换准确性
- 批量导出多壳体
```

### Prompt 2.2: 网格细化与简化

```
## 任务：实现 mesh_editor 模块的细化/简化功能

### 要求：

1. Loop 细分:
   - subdivide_loop(mesh, iterations) — 全局 Loop 细分
   - 使用 trimesh.remesh.subdivide_loop
   - 每次迭代面数 ×4，确保流形性

2. 自适应细化:
   - subdivide_adaptive(mesh, criteria, target_edge)
   - 支持准则: "curvature"(高曲率), "edge_length"(超长边), "area"(大面积)
   - 使用 trimesh.remesh.subdivide(face_index=...) 选择性细分

3. 按尺寸细化:
   - subdivide_to_size(mesh, max_edge)
   - 所有边不超过 max_edge 长度

4. QEM 简化:
   - simplify_qem(mesh, target_faces) — Open3D 二次误差度量
   - simplify_ratio(mesh, ratio) — 按比例简化

5. LOD 生成:
   - generate_lod(mesh, levels=[1.0, 0.5, 0.25, 0.1])
   - 返回多级简化网格列表

6. 所有操作后:
   - 验证输出网格流形性
   - 如果破坏流形则自动修复
   - 记录操作到 EditHistory

### 测试：
- Stanford Bunny Loop 细分 1/2/3 次 → 面数正确
- 简化到 50%/25%/10% → 形状保持度量
- 细化后简化回原面数 → 误差在可接受范围
```

### Prompt 2.3: 模型编辑器

```
## 任务：实现 mesh_editor 的变换、布尔、撤销/重做功能

### 要求：

1. 变换操作（均可撤销）:
   - translate, rotate, scale, mirror, center, align_to_floor

2. 布尔运算（可撤销）:
   - boolean_union, boolean_difference, boolean_intersection
   - 使用 manifold3d 引擎

3. 测量（只读）:
   - measure_distance, measure_angle
   - compute_section（截面轮廓）
   - compute_thickness（壁厚场）

4. 拓扑编辑（可撤销）:
   - delete_faces, fill_holes, shell（抽壳）

5. 选择服务:
   - select_by_ray（光线拾取）
   - select_by_sphere（球形区域）
   - select_connected（连通扩展，法线角度约束）
   - select_by_normal（按法线方向）

6. EditHistory:
   - 最大 50 步撤销栈
   - 每个 EditOperation 有 apply() 和 reverse()
   - undo(), redo()

### 前端集成:
- POST /api/v1/models/{id}/edit 接收操作指令JSON
- 返回更新后的 GLB 数据和操作记录

### 测试：
- 变换后体积不变（缩放除外）
- 布尔运算结果正确
- 撤销 N 步 → 重做 N 步 = 原始状态
```

### Prompt 2.4: GPU 加速方向分析

```
## 任务：实现 GPU 加速的脱模方向分析模块

### 算法流程:
1. 候选方向生成（6主轴 + K面片法线 + 6 PCA + N球面采样）
2. GPU 批量可见性分析（cuBVH）
3. 倒扣区域检测与聚类
4. 多准则方向评分（可见性/平坦度/片数/对称性/拔模角）
5. 层次筛选（粗筛→细筛→精选）
6. 最小方向覆盖（贪心集合覆盖）

### GPU 加速策略:
- 所有候选方向的光线投射打包为一个大批次
- 单次 cuBVH kernel 调用完成
- CPU 上汇总评分

### 性能目标:
- 10K 面片 × 100 方向: <3s (GPU), <15s (CPU)
- 100K 面片 × 100 方向: <15s (GPU), <120s (CPU)

### 输出:
OrientationResult:
  primary_direction, directions (排序), coverage_map,
  min_directions_needed, undercut_regions

### 测试:
- 球体：任何方向评分相近
- 立方体：主轴方向最优
- Stanford Bunny：正确识别耳朵/尾巴倒扣
- GPU vs CPU 结果一致
```

---

## Section 3: Phase 2 — 模具生成

### Prompt 3.1: 分型面生成

```
## 任务：实现 parting_generator 模块

### 算法要求：
1. 分型线提取：面片分类(upper/lower) → 分型边 → 环路构建 → 平滑
2. 分型面生成：平面投影法 / 规则面法 / SDF法（GPU加速）
3. 多片壳分割：多方向分割 + 拆卸顺序（拓扑排序）
4. 验证：每壳可脱模 + 无干涉

### 测试:
- 球体+Z方向 → 赤道分型线 → 半球分割
- 立方体 → 正方形分型线
- 双方向分割 → 3片壳 + 合法拆卸顺序
```

### Prompt 3.2: 模具壳体 + 装配 + 多格式导出

```
## 任务：实现 mold_builder + 多格式导出

### 壳体生成:
- Box 壳体（默认）/ Conformal 随形壳体
- 布尔差集（manifold3d）
- 分型面切割

### 装配结构:
- 定位销/孔: 分型面上 2-4 个, d=4mm, tolerance=0.2mm
- 螺栓孔: 外边缘间距 50mm, M4 通孔+沉头

### FDM 适配:
- 壁厚 ≥ 0.8mm, 悬垂 ≤ 45°, 圆角 R ≥ 0.5mm

### 多格式导出:
- 逐壳体导出: shell_1.stl, shell_2.stl, ...
- 批量打包: 所有壳体 + 装配说明
- 支持: STL(binary)/OBJ/3MF/STEP
- 3MF 支持多组件打包
```

### Prompt 3.3: 浇注系统

```
## 任务：实现 gating_system 模块

### 功能:
1. 浇口位置优化（测地距离平衡 + 薄壁距离 + 可达性）
2. 流道生成（梯形截面, FDM友好）
3. 排气孔布局（充填末端）
4. 溢流槽（可选）

### 材料区分:
- 硅胶: 大浇口(6mm), 浅排气(0.03mm), 低压
- 注塑: 精确浇口, 细排气, 高压

### 插板适配（预留接口）:
- 浇注系统避让插板区域
- 检测插板网孔是否可辅助流动
```

---

## Section 4: Phase 3 — 仿真与优化

### Prompt 4.1: GPU 加速灌注仿真

```
## 任务：实现 flow_simulator 的 L1 启发式 + L2 GPU 达西流

### Level 1 (CPU, <2s):
- 测地距离场（Dijkstra/FMM）
- 截面积变化分析
- 薄壁检测

### Level 2 (GPU, <30s @ 128³):
1. GPU 体素化: Numba CUDA kernel
2. GPU SDF → 壁厚场
3. 渗透率 K = h²/12
4. CuPy 稀疏矩阵组装
5. CuPy 稀疏求解 ∇·(K/μ·∇P) = 0
6. Numba CUDA VOF 前沿追踪
7. 缺陷检测（短射/气泡/熔接线）

### 输出:
SimulationResult:
  fill_time, pressure, velocity, fill_fraction,
  defects, animation_frames

### 前端可视化数据:
  vertex_colors (Float32Array) per animation frame
  colormap: "jet" | "viridis" | "coolwarm"

### 性能目标 (RTX 4060 Ti):
  64³: <5s | 128³: <30s | 256³: <3min
```

### Prompt 4.2: 自动优化

```
## 任务：实现 optimizer 模块（基于规则的启发式优化）

### 优化循环:
仿真→缺陷→调整→重新生成→重复 (max 10轮)

### 规则:
短射→增大浇口/流道 | 气泡→添加排气 | 不平衡→移动浇口
插板滞留→增密网孔

### 输出:
OptimizationResult: final_mold, final_sim, iterations, history
```

---

## Section 5: Phase 4 — 复合结构与插板（新增）

### Prompt 5.1: 插板自动生成

```
## 任务：实现 insert_generator 模块 — 插板位置分析与几何生成

### 功能要求：

1. 插板位置自动分析 auto_generate():
   策略1 — 大平面区域: 检测模型中面积>100mm²的平面区域
   策略2 — 分型面附近: 沿分型面放置插板
   策略3 — 厚壁支撑: 硅胶厚度>15mm区域添加支撑板
   
   所有插板与模型表面保持 ≥ silicone_min_thickness 间距

2. 插板几何生成 generate_single():
   - 在指定平面位置生成板体
   - 裁剪到模具壳体内部轮廓
   - 保持与型腔/壳体的安全间距
   - 边缘倒角

3. InsertConfig 参数:
   thickness=2.0mm, inner_offset=2.0mm, outer_offset=1.0mm,
   silicone_min_thickness=2.0mm

### 测试:
- 简单箱体模型 → 自动在底面生成一块插板
- 手办模型 → 在最大横截面处生成插板
- 所有插板通过干涉检测
```

### Prompt 5.2: 锚固结构生成

```
## 任务：实现插板表面锚固结构生成

### 锚固结构类型:

1. 网孔 (Through Holes):
   - 六角排列圆孔 (d=3mm, spacing=7mm)
   - 布尔差集: plate - cylinders
   - 硅胶穿过孔洞形成双面互锁

2. 凸起 (Bumps):
   - 半球形凸点 (h=1.5mm, d=2.5mm)
   - 布尔并集: plate + hemispheres

3. 沟槽 (Grooves):
   - 交叉线性槽 (w=1.5mm, d=1.0mm, spacing=6mm)
   - 沿路径扫掠矩形截面 → 布尔差集

4. 燕尾槽 (Dovetail):
   - 梯形截面沟槽，底宽>顶宽
   - 机械锁定效果最强

5. 菱形纹 (Knurl):
   - 两组交叉沟槽形成菱形凸起
   - 全面粗糙化

### 接口:
AnchorGenerator.generate(plate, AnchorConfig) → 带锚固结构的插板

### 验证:
- 锚固结构不穿透板体
- 板体剩余材料满足 FDM 最小壁厚
- 结合面积比 (孔面积/总面积) > 10%

### 测试:
- 100x100mm 平板 → 六角网孔 → 验证孔数和间距
- 凸起+沟槽组合 → 无自相交
```

### Prompt 5.3: 插板装配验证与编辑

```
## 任务：实现插板装配验证和用户编辑功能

### 装配验证:
1. 插板与型腔（原模型）不相交
2. 插板与模具壳体不干涉
3. 硅胶包裹厚度 ≥ 最小值
4. 存在无碰撞安装路径（沿某方向可插入）
5. 插板 FDM 可打印（壁厚/悬垂/支撑检查）
6. 锚固结构密度足够

### 用户编辑:
- edit_insert(insert, operations) 支持：
  * 平移/旋转插板位置
  * 修改板厚
  * 切换锚固结构类型
  * 调节锚固参数（孔径/间距/密度）
  * 自定义插板形状轮廓
- 编辑后自动重新验证

### 前端组件:
- InsertViewer: 插板半透明显示，锚固结构细节
- InsertPanel: 参数面板，实时预览
- 复合爆炸视图: 壳体+插板+硅胶空间
- 安装顺序动画: @react-spring/three 驱动
```

---

## Section 6: Phase 5 — 前端 UI/UX

### Prompt 6.1: 工作流步骤导航

```
## 任务：实现完整的工作流步骤导航 UI

### 步骤:
1. 导入 → 2. 修复/编辑 → 3. 方向分析 → 4. 模具生成
→ 5. 插板(可选) → 6. 浇注系统 → 7. 仿真 → 8. 导出

### UI 设计:
- 顶部步骤条: 圆形图标 + 连接线 + 步骤名
- 当前步骤高亮，已完成步骤打勾
- 步骤切换: Framer Motion AnimatePresence 滑动过渡
- 可点击回到已完成步骤（但警告数据可能重置）
- 步骤间数据通过 Zustand store 传递

### 动画细节:
- 步骤圆形进入: scale 0→1, spring stiffness 400
- 连接线填充: width 0→100%, duration 500ms
- 内容区: x 30→0, opacity 0→1, duration 300ms
- 步骤完成: checkmark 弹出动画
```

### Prompt 6.2: 仿真可视化

```
## 任务：实现灌注仿真的前端可视化

### 充填动画:
- 时间滑块控制（播放/暂停/倍速）
- vertex colors 着色: 蓝(冷)→红(热) colormap
- 未充填区域半透明
- 流动前沿高亮线

### 静态场:
- 充填时间/压力/速度 热力图切换
- 色标图例 (colorbar)
- 可配置 colormap (jet/viridis/coolwarm)

### 缺陷标注:
- 气泡: 红色脉冲球体 (Framer Motion 循环动画)
- 熔接线: 红色发光线条
- 短射: 红色闪烁区域

### 技术:
- BufferGeometry vertex colors (Float32Array)
- 预加载所有帧 + requestAnimationFrame 播放
- WebGPU compute 加速色标映射
```

---

## Section 7: 通用辅助 Prompt

### Prompt 7.1: 代码审查

```
## 任务：审查代码

维度: 正确性、性能(NumPy向量化/GPU路径)、健壮性、可维护性、测试覆盖、GPU/CPU降级完整性

[粘贴代码]
```

### Prompt 7.2: Bug 修复

```
## 任务：修复以下问题

问题描述: [描述]
复现步骤: [步骤]
相关代码: [代码]
期望行为: [正确行为]

请分析根因、修复、编写回归测试。
```

### Prompt 7.3: 性能优化

```
## 任务：优化性能

当前: [耗时/内存]
目标: [目标指标]
代码: [代码]

优化方向: NumPy向量化 / Numba JIT / CUDA kernel / 预计算缓存 /
         算法改进 / CuPy替换SciPy / 并行计算
```

### Prompt 7.4: 添加新材料

```
## 任务：添加灌注材料 [材料名]

参数: 粘度=[值]mPa·s, 密度=[值]g/cm³, 固化时间=[值]min,
     收缩率=[值], 最大压力=[值]MPa, 温度=[值]°C

请: 添加到预设库、调整浇注参数、更新仿真参数、添加到前端选择器。
```

### Prompt 7.5: 处理特殊几何

```
## 任务：改进对 [特征] 的处理

特征: [深孔/薄壁/螺纹/倒扣/镂空/...]
当前问题: [描述]
期望: [正确处理方式]

涉及模块: 方向分析 / 分型面 / 模具构建 / 插板 / 仿真
```

---

## Section 8: Tauri 打包与发布

### Prompt 8.1: PyInstaller 打包

```
## 任务：将 MoldGen Python 后端打包为可执行文件

### 要求:
1. PyInstaller 打包 moldgen 为 moldgen-server.exe
2. 包含所有 Python 依赖
3. CUDA 库处理:
   - 检测是否有 CUDA: 如有则包含 CuPy/Numba CUDA 运行时
   - 如无 CUDA: 打包仅 CPU 版本
4. Assimp DLL 包含
5. 排除不需要的大包（测试/文档等）
6. spec 文件配置

### 测试:
- 打包后 exe 可独立运行
- GPU 功能正常（如有CUDA）
- 无 CUDA 时 CPU 降级正常
- 文件大小 < 500MB（目标）
```

### Prompt 8.2: Tauri 构建配置

```
## 任务：配置 Tauri 生产构建

### 要求:
1. tauri.conf.json 配置:
   - 应用信息（名称/版本/图标）
   - externalBin: moldgen-server
   - bundle: NSIS Windows 安装器
   - 文件关联: .stl, .obj, .fbx, .3mf
   - 权限: shell, fs, dialog, process

2. 构建脚本:
   - 先 PyInstaller 打包后端
   - 再 tauri build 打包完整应用
   - 输出 .exe 安装器

3. 安装流程:
   - 安装向导（NSIS）
   - 桌面快捷方式
   - 开始菜单
   - 文件关联注册
```

---

## Section 9: AI 集成开发（新增）

### Prompt 9.1: AI 服务统一层

```
## 任务：实现 moldgen/ai/ 模块 — AI 服务统一管理

### 要求：

1. ai/service_manager.py — AIServiceManager 类:
   - 初始化 4 个 AI 客户端（DeepSeek/通义万相/Tripo3D/Qwen-VL）
   - 所有对话类 API 使用 OpenAI SDK（统一协议）
   - async chat(): 对话（支持 Function Calling + 流式输出）
   - async generate_image(): 图像生成（通义万相 DashScope API）
   - async generate_3d_model(): 3D模型生成（Tripo3D Python SDK）
   - async analyze_image(): 多模态分析（Qwen-VL）
   - get_usage_stats(): API 用量统计
   - 错误处理 + 自动降级（DeepSeek不可用→Qwen）

2. ai/chat.py — DeepSeek 对话封装:
   - 流式输出（async generator yield tokens）
   - Function Calling 处理（解析 tool_calls → 执行 → 回传结果）
   - 对话历史管理
   - Token 计数与成本追踪

3. ai/image_gen.py — 通义万相封装:
   - DashScope ImageSynthesis API
   - 支持中文提示词
   - 图像下载到本地缓存
   - 多图生成

4. ai/model_gen.py — Tripo3D 封装:
   - pip install tripo3d
   - text_to_model() / image_to_model()
   - 异步任务等待 + 进度回调
   - GLB 下载 → MeshData 转换

5. ai/vision.py — Qwen-VL 封装:
   - OpenAI SDK 兼容模式调用 DashScope
   - 图片 + 文本 → 分析结果
   - 支持 base64 和 URL 两种图片输入

### 配置:
class AIConfig(BaseSettings):
    deepseek_api_key: str
    tongyi_api_key: str
    tripo_api_key: str
    qwen_api_key: str
    class Config:
        env_prefix = "MOLDGEN_AI_"

### 测试:
- 对话返回正确响应
- Function Calling 正确解析
- 图像生成并下载
- 3D模型生成并转为 MeshData
- 图像分析返回文本
- DeepSeek 不可用时降级到 Qwen
```

### Prompt 9.2: Agent 执行引擎实现

```
## 任务：实现 Agent 自动执行引擎 — 6大内置Agent的调度核心

### 要求：

1. ai/execution_engine.py — AgentExecutionEngine:
   - execute(user_request, mode) → AsyncIterator[ExecutionEvent]
     * 调用 MasterAgent 生成执行计划
     * 按计划依次调度专业 Agent
     * 每个 Agent 内部按工具链自动执行
     * 根据 mode (auto/semi_auto/step) 决定确认点
   - handle_interrupt(task_id, instruction): 用户中途插入指令
   - resume(task_id): 恢复暂停的任务
   - switch_mode(task_id, mode): 运行时切换执行模式
   
   ExecutionContext 跨Agent共享:
   - current_model, current_mold, current_inserts, current_simulation
   - execution_plan, history, user_preferences

2. ai/agent_base.py — BaseAgent 抽象基类:
   - name, display_name, system_prompt, tools, auto_chain
   - execute(task, params, mode, context) → AsyncIterator[ExecutionEvent]
   - plan(task) → List[dict]
   - should_confirm(action, mode) → bool

3. ai/tool_registry.py — ToolRegistry:
   - 全局工具注册表，映射所有 Function Calling 到实际函数
   - register(name, func, schema, category)
   - execute(name, args, context) → ToolResult
   - get_schemas(agent_name) → List[dict] 按Agent过滤

4. 确认规则表 CONFIRMATION_RULES:
   定义每个操作在三种模式下是否需要确认:
   - auto: 仅 delete_anything 需确认
   - semi_auto: 关键决策(方向/壳数/支撑板方案/导出)需确认
   - step: 全部需确认

### 执行模式:
- AUTO: "全自动/帮我搞定/一键生成" → 仅关键节点通知
- SEMI_AUTO [默认]: 非关键自动,关键决策暂停确认
- STEP_BY_STEP: "一步步来/我想看每一步" → 每步确认

### 事件类型:
plan_created | agent_switch | step_start | step_complete |
tool_call | tool_result | need_confirmation | token |
error | task_complete | agent_status

### API 端点:
POST /api/v1/ai/agent/execute — 创建并启动自动执行任务
POST /api/v1/ai/agent/task/{id}/input — 用户确认/拒绝
POST /api/v1/ai/agent/task/{id}/interrupt — 中途插入指令
PUT  /api/v1/ai/agent/task/{id}/mode — 切换模式
WS   /ws/ai/agent/{task_id} — 实时事件流

### 测试:
- 半自动模式: "生成肝脏模具" → 方向和壳数处暂停确认,其余自动
- 全自动模式: "全自动完成" → 仅通知,不暂停
- 中途切换: 执行中从半自动切到全自动 → 后续步骤不再暂停
- 中途插入: 执行中用户说"壁厚改成6mm" → Agent接收并应用
```

### Prompt 9.2b: 六大内置Agent实现

```
## 任务：实现6大内置Agent (ai/agents/ 目录)

### 要求：

1. agents/master_agent.py — MasterAgent 总控调度:
   - 意图路由: 关键词快速匹配 + LLM分类双路径
   - 任务编排: 预定义流水线模板 + LLM自由分解
   - 进度管理: 跟踪所有子步骤状态
   - 异常处理: Agent失败时的降级和重试策略
   - ROUTING_TOOLS: dispatch_to_agent, create_execution_plan, ask_user
   
   关键词路由表(快速路径,<10ms):
   "导入/加载" → ModelAgent
   "修复/简化/细化" → ModelAgent  
   "方向/分型/模具" → MoldDesignAgent
   "支撑板/插板" → InsertAgent
   "仿真/灌注/优化" → SimOptAgent
   "生成图/生成模型" → CreativeAgent
   "做一个/一键/全自动" → 完整流水线

2. agents/model_agent.py — ModelAgent 模型处理:
   - 17个工具: load/check/repair/subdivide/simplify/transform/boolean/
     measure/section/thickness/select/delete/fill/shell/center/align/export/info
   - 自动链: 导入后→自动检查质量→有问题自动修复→报告结果
   - 智能决策: 面数>500K自动建议简化; 非流形自动修复

3. agents/mold_agent.py — MoldDesignAgent 模具设计:
   - 15个工具: orientation/candidates/select/parting_line/parting_surface/
     split/build_shells/pins/bolts/fdm_check/fdm_optimize/gating/params/info/preview
   - 全自动流水线: 按顺序执行所有步骤,失败自动重试
   - 智能决策: 根据复杂度自动决定壳数; 检测到大倒扣主动提醒

4. agents/insert_agent.py — InsertAgent 支撑板:
   - 11个工具: analyze_positions/generate_plate/add_anchor/modify/delete/
     locating_slots/validate_assembly/silicone_coverage/insertion_path/info/vision
   - 器官策略映射: 实质性→中央横断+网孔; 空腔→内壁环+沟槽; 管道→骨架+凸起
   - AI辅助: 调用Qwen-VL分析解剖结构→结合几何分析→综合规划

5. agents/simopt_agent.py — SimOptAgent 仿真优化:
   - 12个工具: sim_l1/sim_l2/defects/report/optimize_gate/optimize_runner/
     vent/wall_thickness/optimization_loop/compare/data/material
   - 自动优化循环: 仿真→缺陷→针对性调参→重新仿真(max5轮)
   - 智能决策: 根据模型大小选L1/L2; 根据GPU状态选精度

6. agents/creative_agent.py — CreativeAgent 创意生成:
   - 7个工具: optimize_prompt/generate_images/3d_from_text/3d_from_image/
     review_quality/suggest_improvements/load_model
   - 提示词优化: 中文→英文翻译+质量修饰词+风格修饰词+器官专业术语
   - 自动流程: 优化提示词→生成3张图→(等待选择或自动选最佳)→生成3D→审查质量

### 每个Agent的文件结构:
```python
class XxxAgent(BaseAgent):
    name = "xxx"
    display_name = "Xxx Agent"
    
    SYSTEM_PROMPT = """..."""
    TOOLS = [...]
    AUTO_CHAIN = {...}  # 自动触发规则
    
    async def execute(self, task, params, mode, context):
        # Agent内部执行逻辑
```

### 系统提示词文件 (ai/prompts/):
每个Agent对应一个提示词文件，定义:
- 角色身份和专业能力
- 可调用工具列表和使用场景
- 自动执行规则（何时自动/何时确认）
- 智能决策规则（何时做什么选择）
- 错误处理策略

### 测试:
- MasterAgent: "做一个肝脏模型" → 生成5步计划，正确分配Agent
- ModelAgent: 导入STL → 自动检查+修复 → 报告结果
- MoldDesignAgent: "生成模具" → 全流程自动执行到完成
- InsertAgent: "添加支撑板" → 分析+方案展示+确认后生成
- SimOptAgent: "仿真并优化" → 检测缺陷+自动调参+收敛
- CreativeAgent: "生成心脏模型" → 提示词优化+图像+3D+审查
```

### Prompt 9.3: AI 悬浮球前端

```
## 任务：实现 AI 悬浮球 + 对话面板前端组件

### 组件设计:

1. ChatBubble.tsx — 悬浮球:
   - 60px 圆形，固定在右下角
   - 呼吸灯动画（Framer Motion: scale 1→1.05 循环）
   - 可拖拽定位（framer-motion drag）
   - AI 生成中时旋转动画
   - 点击切换对话面板

2. ChatPanel.tsx — 对话面板:
   - 侧边滑出（Framer Motion: x 400→0, spring stiffness 300）
   - 400px 宽，全高
   - 消息列表（AI/用户气泡区分）
   - AI 回复: Markdown 渲染 + 流式打字效果
   - 图片预览（AI 生成的参考图）
   - 3D 模型缩略图（点击加载到主场景）
   - 操作确认卡片（确认/拒绝/修改 按钮）
   - 底部: 输入框 + 图片拖拽区

3. 数据流:
   - useAIChat() Hook → Zustand aiStore
   - WebSocket /ws/ai/chat 流式接收
   - SSE 降级方案
   - 消息持久化（本地 IndexedDB）

### 动画规范:
- 悬浮球呼吸: scale [1, 1.05, 1], duration 2s, repeat Infinity
- 面板滑出: x [400, 0], transition spring stiffness 300 damping 30
- 新消息: y [20, 0] + opacity [0, 1], duration 300ms
- 打字效果: 逐字符渲染，间隔 20ms
- 确认按钮: scale [0.95, 1] on hover

### 视觉风格:
- 深色面板背景 (#1a1a2e)
- AI 气泡: 深蓝 (#1e3a5f)
- 用户气泡: 深紫 (#2d1b69)
- 操作卡片: 边框高亮 (#6366f1)
```

### Prompt 9.4: Agent 工作站前端

```
## 任务：实现 Agent 工作站前端组件（支持自动执行引擎）

### AgentWorkstation.tsx:
- 可从悬浮球触发或独立打开
- 全屏/半屏模式切换

顶部区域:
  - 任务描述 + 总进度条
  - 执行模式选择器: [全自动] [半自动] [逐步] (运行时可切换)
  - 操作按钮: [暂停] [恢复] [取消] [关闭]
  - 当前执行Agent名称 + 状态图标

中间区域 — 执行日志:
  - 时间戳 + Agent名 + 操作内容
  - 不同Agent用不同颜色标识
  - ✅ 完成 / 🔄 执行中 / ⏳ 等待 / ❌ 错误 状态图标
  - 确认卡片(高亮): 问题 + 选项按钮 + 自由文本输入
  - 图片预览(AI生成的参考图行内展示)
  - 3D缩略图(可点击加载到主场景)
  - 自动滚动到最新日志

底部区域:
  - Agent状态条: 6个Agent图标 + 状态颜色指示
    🟢 就绪 | 🔵 执行中 | 🟡 等待 | 🟠 需输入 | 🔴 错误 | ⚪ 未激活
  - 快捷操作: [跳过此步] [回退一步] [全自动继续]
  - 对话输入框: 可随时对当前Agent说话/插入指令

### AgentWorkstationStore (Zustand):
  - startTask(request): 创建任务 → WebSocket连接
  - switchMode(mode): 切换执行模式
  - confirmStep(stepId, choice): 确认/选择
  - interruptTask(instruction): 中途插入指令
  - pause/resume/cancel: 任务控制

### 数据流:
- WebSocket /ws/ai/agent/{task_id} 接收 ExecutionEvent 流
- useAgentExecution() Hook 管理完整执行状态
- useAgentWebSocket(taskId) Hook 管理WebSocket连接和重连

### 动画:
- 步骤卡片进入: stagger 100ms, y [30, 0], opacity [0, 1]
- Agent切换: 状态条图标弹跳动画
- 状态切换: 图标旋转/打勾/脉冲动画
- 进行中: border glow animation (box-shadow pulse)
- 确认卡片: scale [0.95, 1] 弹出 + 边框高亮
- 完成时: confetti/checkmark celebration animation
```

### Prompt 9.5: Agent 记忆与长期学习

```
## 任务：实现 Agent 记忆系统

### 要求：

1. ai/memory.py — AgentMemory (短期/会话级):
   - conversation_history: 完整对话历史
   - execution_context: 当前执行状态(模型/模具/支撑板/仿真)
   - user_preferences: 从对话中提取的偏好
     例: 用户说"壁厚用6mm" → {"wall_thickness": 6.0}
     后续Agent自动使用此参数
   - extract_preferences(message): 从用户消息提取偏好的LLM调用

2. ai/memory.py — AgentLongTermMemory (持久化/跨会话):
   - SQLite 存储
   - user_defaults: 用户默认参数偏好
   - frequent_organs: 常用器官类型 (按使用频率排序)
   - preferred_materials: 常用材料
   - past_successful_configs: 历史成功配置
   - get_recommendation(organ_type): 基于历史推荐参数
   - save_successful_run(config, result): 任务成功完成后保存配置

3. 记忆集成:
   - Agent执行时自动查询长期记忆获取推荐参数
   - 任务成功完成后自动保存到长期记忆
   - 对话中提取的偏好自动应用到后续操作

### 测试:
- 用户说"壁厚6mm" → 后续生成模具自动用6mm
- 第二次做肝脏模型 → 自动推荐上次成功的参数
- 常做心脏模型 → frequent_organs 排序正确
```
