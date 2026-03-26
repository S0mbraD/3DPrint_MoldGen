# 错误与教训记录 — 开发过程中的理解偏差与修复

> 本文档记录开发过程中出现的理解错误、技术问题及修复方案，供后续开发参考避免重犯。

---

## ERR-001: 分型面咬合特征出现在模具外侧

**日期**: 2026-03-24  
**严重级别**: 高  
**影响范围**: `moldgen/core/mold_builder.py`

### 错误描述
分型面样式（燕尾榫/锯齿/阶梯/舌槽）的咬合几何体延伸超出了模具壳体边界，在模具外侧产生可见的突出结构。

### 根因分析
`_create_parting_interlock()` 方法中，咬合特征的 `span_v`（沿分型面展开的长度）设置为 `max(extents) + 2 * margin`，导致几何体超出模具实体的边界。在执行布尔并集/差集时，超出部分被直接添加到壳体外侧。

### 正确理解
分型面咬合是**两片模具壳体之间**的接触面形式。咬合特征必须**完全位于模具壁厚范围内**，不能在模具外表面产生任何突出。

### 修复方案（初次）
在 `_apply_parting_interlock()` 中，对咬合几何体先执行 `boolean_intersect(interlock, solid)` 将其裁剪到模具实体内部。但此方案不彻底，当布尔运算失败时仍回退到原始几何体。→ 见 **ERR-006** 的根本修复。

### 教训
- **几何体生成后必须验证边界**: 任何附加到已有网格的几何体，都应先裁剪到宿主网格范围内
- **分型面咬合 ≠ 外部结构**: 分型面特征是两片壳体**接合处**的内部特征
- **裁剪不如从源头约束**: 后续修复(ERR-006)证明从源头限制几何体尺寸比后期裁剪更可靠

---

## ERR-002: 支撑板类型/特征混淆 — 把可选特征当作互斥类型

**日期**: 2026-03-24  
**严重级别**: 高  
**影响范围**: `moldgen/core/insert_generator.py`, 前端 UI

### 错误描述
将支撑板的各种特征错误地设计为互斥的类型分类：
- "板型" 包含了 flat / conformal / ribbed / lattice 四种
- "锚固类型" 包含了 mesh_holes / bumps / grooves / dovetail / diamond 五种

用户实际需求是：选择**基础板型**（平板或仿形板），然后**可选开启**多个特征（网孔、加强筋、啮合结构）。

### 根因分析
对用户需求的结构化理解有误。将"属性维度"（特征开关）和"类型维度"（基础形状）混为一谈，导致用户只能选一种组合，无法自由搭配。

### 正确理解
- **基础板型**: 只有 `flat`（平板截面挤出）和 `conformal`（仿形板跟随曲面）
- **可选特征**（可同时启用多个）:
  - `add_mesh_holes`: 表面网孔 — 硅胶渗透通孔
  - `add_ribs`: 加强筋 — 交叉肋条增强刚性
  - `add_interlocking`: 啮合固定结构 — 燕尾榫/凸起/沟槽/菱形纹

### 修复方案
1. `InsertConfig` 中将 `add_mesh_holes`、`add_ribs`、`add_interlocking` 设计为独立布尔/字符串开关
2. `generate_plate()` 方法改为: 先生成基础板 → 再依次叠加启用的特征
3. 前端 UI 改为: 基础板型下拉 + 三个独立的特征开关（含子参数面板）

### 教训
- **类型 vs 特征**: 基础形状是"类型"（互斥），附加功能是"特征"（可叠加）
- **用户语义理解**: "选择支撑板特征为是否有表面网孔、加强筋与啮合固定结构" → 明确是开关式特征，不是互斥选项
- **先询问再实现**: 当需求表述有多种理解方式时，应先确认再实现

---

## ERR-003: 支撑板立柱已生成但视口中不可见

**日期**: 2026-03-24  
**严重级别**: 中  
**影响范围**: `frontend/src/components/viewer/InsertPlateViewer.tsx`

### 错误描述
后端正确生成了支撑板立柱（pillar_mesh 不为空），API 也提供了 `pillars.glb` 端点，但 3D 视口中从不渲染立柱。

### 根因分析
`InsertPlateViewer` 组件只加载了板体的 GLB（`/plate/{index}/glb`），完全没有加载立柱的 GLB（`/plate/{index}/pillars.glb`）。这是一个简单的遗漏：后端提供了端点，但前端从未调用。

### 修复方案
在 `InsertPlateViewer` 中同时渲染两个 GLB：
1. 板体 GLB → 绿色材质
2. 立柱 GLB → 橙色材质（独立 Suspense + ErrorBoundary，避免立柱 404 影响板体渲染）

### 教训
- **端到端验证**: 新增 API 端点后，必须同时验证前端是否实际调用了该端点
- **数据流追踪**: 后端生成 → API 序列化 → 前端请求 → 3D 渲染，每个环节都需要验证

---

## ERR-004: 支撑板立柱方向混合径向偏移

**日期**: 2026-03-23  
**严重级别**: 中  
**影响范围**: `moldgen/core/insert_generator.py`

### 错误描述
立柱方向计算为 `0.4 * radial + 0.6 * pillar_dir`，导致立柱不是沿配置的方向（如背面）笔直延伸，而是向四周散开。

### 修复方案
立柱方向改为严格跟随 `pillar_dir`（不混合径向分量），只选择板面朝向出口方向的采样点。

### 教训
- **方向语义**: 用户说"立柱从背面伸出"，意味着所有立柱都应**平行于**背面法线方向，不应有散射

---

## ERR-005: FEA 可视化使用占位几何体

**日期**: 2026-03-23  
**严重级别**: 中  
**影响范围**: `frontend/src/components/viewer/SimulationViewer.tsx`

### 错误描述
`FEAMeshOverlay` 组件创建了一个 `sphereGeometry args={[0.01, 1, 1]}`（半径 0.01mm 的微型球体）来尝试映射 FEA 顶点颜色，导致 FEA 结果完全不可见。

### 修复方案
使用 `useLoader(GLTFLoader, glbUrl)` 加载实际模型的 GLB 几何体，克隆后映射 FEA 顶点颜色。顶点数不匹配时使用最近邻插值。

### 教训
- **可视化必须使用实际几何体**: 向已有模型叠加数据时，必须使用该模型的实际网格

---

## ERR-006: 分型面咬合特征横贯模具全宽（阶梯/锯齿样式）

**日期**: 2026-03-24  
**严重级别**: 高  
**影响范围**: `moldgen/core/mold_builder.py`

### 错误描述
阶梯/锯齿/燕尾等分型面样式生成后，在 3D 视口中表现为横贯模具全宽的水平架子状结构，穿过了模型空腔区域，而非仅存在于模具壁厚区域的接合面上。

### 根因分析
`_create_parting_interlock()` 中每个咬合特征的 `span_v` 被设置为 `max(extents) + 2 * margin`（模具全宽），导致每个特征是一个贯穿整个模具的长条形几何体。虽然此前已添加了 `_robust_boolean_intersect(interlock, solid)` 裁剪步骤，但当布尔运算失败时，代码回退到使用 **未裁剪的原始几何体**（`"clip failed, using raw geometry"`），直接将全宽长条添加到壳体上。

### 修复方案
**完全重写** `_create_parting_interlock()` 的几何体生成策略：

1. 通过 `solid.section()` 获取模具在分型面处的**横截面轮廓**（3D 路径）
2. 沿轮廓以 `pitch` 为间距采样特征放置点（`_sample_outline_at_pitch()`）
3. 在每个采样点处生成**小型局部化**的咬合特征单元（`_make_interlock_unit()`）
4. 每个单元沿轮廓切线方向定向，尺寸约为 `pitch × 0.55` × `pitch × 0.45` × `depth`
5. 将采样点向横截面质心方向内移，防止边界突出

同时修改 `_apply_parting_interlock()`:
- 移除了 `_robust_boolean_intersect` 裁剪步骤（特征已内在约束于壁厚区域）
- 当布尔 subtract 失败时，回退到**平面分割**（不再使用未裁剪几何体）

### 教训
- **几何体应内在约束**: 不要生成超大几何体再裁剪，而应从一开始就生成正确尺寸的几何体
- **布尔运算不可靠时的回退策略**: 回退应是安全的（平面分割），而非危险的（使用未裁剪原始几何体）
- **利用横截面信息**: 模具的横截面轮廓天然提供了壁厚区域的位置信息

---

## ERR-007: 支撑板表面网孔未生成（布尔减法静默失败）

**日期**: 2026-03-24  
**严重级别**: 高  
**影响范围**: `moldgen/core/insert_generator.py`

### 错误描述
选择"表面网孔"后，系统提示已生成 `mesh_holes` 特征，但支撑板表面实际上没有任何可见的孔洞。

### 根因分析
多层问题叠加导致网孔完全无法生成：

1. **非水密网格**: `_generate_flat()` 调用 `_extrude_section()` 对横截面进行自定义挤出，生成的网格**不是水密的**（`is_watertight=False`, genus=1）。
2. **布尔引擎失败**: `manifold3d` 对非水密输入返回 0 个面（空网格）；`trimesh.difference()` 因 `is_volume` 检查失败直接抛出异常。
3. **异常被静默吞掉**: 代码使用 `contextlib.suppress(Exception)` 完全隐藏了所有错误，让开发者无从得知布尔操作从未成功。
4. **圆柱方向错误**: 用于切孔的圆柱始终沿 Z 轴对齐，而支撑板可能在任意方向，导致圆柱可能不穿过板面。

### 修复方案

**A. 修复板体水密性**（根本修复）:
- `_generate_flat()` 不再使用自定义 `_extrude_section()`
- 改为在 `_get_cross_section()` 中使用 `trimesh.creation.extrude_polygon()` 直接生成正确厚度的水密实体
- 新生成的板体 `is_watertight=True`，`manifold3d` 布尔运算正常工作

**B. 双路径网孔策略**:
- 水密板体 → `manifold3d` 布尔减法（生成精确圆形孔洞）
- 非水密板体 → 面删除法（删除孔洞半径范围内的所有三角面）
- 面删除法作为可靠后备方案，保证任何情况下都能产生可见孔洞

**C. 孔洞方向修正**:
- 使用 `plate.nearest.on_surface()` 获取每个孔洞位置处的局部法线
- 圆柱沿局部法线对齐，确保穿透板体

**D. 移除静默异常吞掉**:
- `contextlib.suppress(Exception)` 替换为 `logger.debug()` 记录

### 教训
- **`contextlib.suppress(Exception)` 是调试杀手**: 永远不要静默吞掉所有异常；至少记录日志
- **布尔运算需要水密输入**: `manifold3d` 和大多数布尔引擎要求输入为有效流形网格
- **必须验证输出**: "features 列表中有 mesh_holes" ≠ "板体表面实际有孔"
- **自定义挤出 vs 库函数**: `trimesh.creation.extrude_polygon()` 生成正确拓扑，自定义挤出容易遗漏封边

---

## ERR-008: 分型面咬合只出现在一侧模具（特征未跨越分型平面）

**日期**: 2026-03-24  
**严重级别**: 高  
**影响范围**: `moldgen/core/mold_builder.py` → `_make_interlock_unit()`

### 错误描述
阶梯等分型面样式的咬合特征只在上壳体可见（有凸起），下壳体完全平坦——没有对应的凹槽。

### 根因分析
`_make_interlock_unit()` 中所有特征的 Z 中心设在 `position + up * depth / 2`，即特征体完全位于分型平面**上方**。
- `boolean_union(upper, interlock)` 成功：特征与上壳体重叠，被添加
- `boolean_subtract(lower, interlock)` 无效：特征完全在上壳体领域内，与下壳体**零重叠**，所以减法无效果

此外，step 样式用 `if index % 2 != 0: return None` 跳过所有奇数索引，进一步减少了特征数量。

### 正确理解
分型面咬合特征必须**跨越分型平面**——从 `-depth/2` 延伸到 `+depth/2`。这样：
- 上壳体通过 union 获得特征的**上半部分**（凸起）
- 下壳体通过 subtract 被切去特征的**下半部分**（凹槽）
- 合模时凸起嵌入凹槽，实现互锁

### 修复方案
将所有特征的位置从 `position + up * depth/2` 改为 `position`（以分型平面为中心），使特征几何体自然跨越平面。同时恢复所有索引的特征生成（step 不再跳过奇数索引）。

### 教训
- **跨越分型面**: 咬合特征必须同时存在于两侧壳体的领域内，否则布尔运算只对一侧生效
- **union + subtract 对称性**: 只有当被操作几何体与 BOTH 壳体重叠时，两个操作才都有效果

---

## ERR-009: 加强筋独立于支撑板悬浮在空中

**日期**: 2026-03-24  
**严重级别**: 中  
**影响范围**: `moldgen/core/insert_generator.py` → `_apply_ribs()`

### 错误描述
加强筋显示为独立的方形网格结构，悬浮在仿形支撑板上方，未与板面贴合。

### 根因分析
`_apply_ribs()` 使用 `center[main_ax] + (thickness/2 + rib_height/2) * sign` 计算肋条中心位置。这基于板体**包围盒中心**的固定偏移，而非**实际板面位置**：
- 对于仿形板，板面高度随表面曲率变化，不等于包围盒中心 + thickness/2
- 偏移量 `thickness/2 + rib_height/2` 将肋条放在了板体上方，造成断连

### 修复方案
重写 `_apply_ribs()` 使肋条贴合板面：
1. 将每条肋线分割为多个短段（~3mm）以跟踪曲面
2. 对每段，查找最近的板面顶点获取实际表面高度
3. 将肋条底部放置在实际表面位置，使其与板面接触

### 教训
- **不可依赖包围盒定位**: 仿形板的表面位置随曲率变化，必须使用实际顶点坐标
- **分段跟踪曲面**: 对于弯曲表面上的线性结构，需分段逼近

---

## ERR-010: 仿形板网孔面删除法未命中面（粗糙网格问题）

**日期**: 2026-03-24  
**严重级别**: 中  
**影响范围**: `moldgen/core/insert_generator.py` → `_face_removal_mesh_holes()`

### 错误描述
仿形支撑板选择网孔后，面删除法未能删除足够的面，孔洞不可见。

### 根因分析
原始面删除法只检查面**质心**是否在孔洞半径内。仿形板面片较大且较少，面质心可能不在孔洞区域内，即使面的顶点跨越了孔洞区域。

### 修复方案
改进面删除算法，同时检查：
- 面质心距离 < 半径
- 任意顶点距离 < 半径（`v0_dist | v1_dist | v2_dist`）

只要面的质心或任一顶点落入孔洞区域，即标记为删除。

### 教训
- **粗糙网格上的空间查询**: 不能只用质心判断，需同时检查顶点
- **网格分辨率影响算法效果**: 面删除法在低分辨率网格上需要更宽松的匹配条件

---

## ERR-011: 流线未从浇注口位置起始

**日期**: 2026-03-24  
**严重级别**: 中  
**影响范围**: `moldgen/core/flow_sim.py`, `frontend/src/components/viewer/SimulationViewer.tsx`

### 错误描述
流体仿真中的流线（streamlines）不从模具浇注口位置开始，物理上看起来不合理。

### 根因分析
1. **后端**: `SimulationResult` 没有存储浇注口位置（`gate_position`），可视化数据中也不包含该信息
2. **前端**: `StreamlineViewer` 使用 `fill_time < 0.15` 筛选种子点，但 `seedStep` 跳步太大可能跳过所有早期填充点
3. **数据断链**: 仿真使用 `gating.gate.position`，但该信息未传递到可视化数据，前端无法获知浇注口位置

### 修复方案
1. `SimulationResult` 新增 `gate_position` 字段
2. `_run_level2` 存储 `gating.gate.position` 到结果
3. `extract_visualization_data()` 输出 `gate_position`
4. 前端 `StreamlineViewer` 优先从浇注口附近选取种子点（按到浇注口距离排序）

### 教训
- **关键物理参数必须贯穿整个数据流**: 浇注口位置是流体仿真的物理起点，必须从后端传递到前端可视化
- **流线种子策略应基于物理**: 种子点应从浇注口位置出发，而非依赖不可靠的 fill_time 阈值

---

### ERR-012: 仿形板网孔不可见（面密度不足）→ 已被 ERR-014 替代

| 项目 | 内容 |
|------|------|
| **发现版本** | v0.9.4 |
| **状态** | ~~已修复~~ → 被 ERR-014 彻底替代 |
| **现象** | 用户选择网孔特征后，仿形支撑板表面无可见孔洞 |
| **首次修复** | 细分网格后做面删除——虽可见，但孔洞形状不规则、锯齿化 |
| **根因升级** | 面删除法本质上依赖三角面片边界，永远无法生成均匀圆形孔洞 |

---

### ERR-013: 加强筋以包围盒定位，在仿形板上呈独立尖刺 → 已被 ERR-015 替代

| 项目 | 内容 |
|------|------|
| **发现版本** | v0.9.4 |
| **状态** | ~~已修复~~ → 被 ERR-015 彻底替代 |
| **现象** | 加强筋生成后呈独立三棱柱阵列（"刺猬"效果） |
| **首次修复** | 逐面法线挤出三棱柱——方向正确，但每面独立挤出导致不连续 |
| **根因升级** | 后处理方式无论如何精细化，都受原始网格拓扑限制，产生非均匀结果 |

---

### ERR-014: 仿形板网孔不均匀（后处理固有缺陷）

| 项目 | 内容 |
|------|------|
| **发现版本** | v0.9.5 |
| **现象** | 细分 + 面删除虽然能切出可见孔洞，但孔洞形状随三角面片走向变化，不规则且不均匀 |
| **根因** | 面删除法（无论是否细分）永远受限于三角面片的拓扑结构。删除面的边界由三角边决定，无法产生光滑圆形 |
| **正确理解** | 孔洞应在参数空间（u-v 坐标）中定义，在网格构建阶段就跳过对应区域，而非事后删除面 |
| **修复** | 完全改为**参数空间集成**方式：<br>1. `_hex_hole_layout()` 在 u-v 空间以六角密排网格计算孔心位置，保证最优均匀分布<br>2. `_generate_conformal(..., integrate_holes=True)` 在构建网格四边形时，跳过质心落在孔半径内的网格单元<br>3. 提高仿形板 grid_res 至 120（网格间距 ~1.3mm），使孔边缘光滑度接近圆形<br>4. 仅对非仿形（平板等水密网格）保留布尔减法方式 |
| **效果** | 孔洞分布完全均匀（最近邻距离标准差 = 0）；孔边缘由细密网格单元组成，接近圆形；面积缩减 ~12% |
| **教训** | **几何特征应在构建阶段集成，而非后处理。** 参数化构建从根本上避免了拓扑依赖问题 |

---

### ERR-015: 加强筋不连续（逐面挤出固有缺陷）

| 项目 | 内容 |
|------|------|
| **发现版本** | v0.9.5 |
| **现象** | 逐面法线挤出虽然方向正确，但每个三角面独立形成一个三棱柱，产生"刺猬"效果而非连续脊线 |
| **根因** | 后处理逐面挤出不共享顶点，相邻面的棱柱不连接，边界不连续。且 `_ensure_interior()` 对含筋板体做全局缩放，进一步破坏筋高度 |
| **正确理解** | 加强筋应是参数空间中的连续条带：在网格构建阶段，将筋线位置的顶点沿局部法线额外偏移 `rib_height`，利用网格四边形的连续性自然形成光滑脊线 |
| **修复** | 完全改为**顶点偏移集成**方式：<br>1. `_rib_vertex_mask()` 在 u-v 空间标记筋线位置的顶点（交叉网格模式）<br>2. `_generate_conformal(..., integrate_ribs=True)` 对筋顶点的 outer 层沿局部法线 `sn_unit` 额外偏移 `rib_height`<br>3. 利用仿形网格四边形拓扑的连续性，自然形成光滑过渡的脊线<br>4. 对仿形板跳过 `_ensure_interior()`（仿形板已约束于模型表面，全局缩放会破坏筋高度）<br>5. 平板仍使用独立方式生成筋 |
| **效果** | 筋条连续光滑、沿曲面法线延伸 ~3mm、无尖刺；筋交叉处自然融合 |
| **教训** | **不可在参数化网格生成后再叠加几何**——应修改参数化构建过程本身。`_ensure_interior()` 等全局变换不应用于已含精细特征的网格 |

---

### ERR-016: 仿形板/模具面数过低，特征分辨率不足

| 项目 | 内容 |
|------|------|
| **发现版本** | v0.9.6 |
| **现象** | 仿形板网孔虽然在参数空间集成，但由于网格分辨率仍然不够（每孔仅 ~9 cells），孔边缘呈锯齿方块而非圆形。模具壳体仅 452-1180 面，表面粗糙 |
| **根因** | 1. 仿形板 grid_res 固定为 `min(120, int(span/1.5))`，与特征尺寸无关。当 half_span 较小时 grid_res 远低于 120，特征分辨率不足<br>2. 模具构建直接使用低面数原始模型（718 面），壳体分辨率与原始面数成正比<br>3. 体素模具固定 resolution=80，不随模型尺寸调整 |
| **正确理解** | 网格分辨率应由**特征尺寸驱动**，而非仅由板/模具尺寸驱动。每个 5mm 孔需 ~20+ cells 才显圆形，每条 2mm 筋需 >=3 顶点宽度 |
| **修复 v1（已废弃）** | 自适应 grid_res + 迭代质量分析——仍使用 grid-cell 删除法，无法消除锯齿 |
| **修复 v2（当前）** | **三阶段流水线 (Generate → Refine → Carve)**：见 ERR-017 |
| **教训** | **分辨率必须由最小特征尺寸驱动，不可硬编码上限。** 低模输入必须先提升面数再参与后续几何运算。Grid-cell 删除法本质上无法产生光滑边界 |

---

### ERR-017: Grid-cell 删除法生成的孔洞/筋条始终呈锯齿状

| 项目 | 内容 |
|------|------|
| **发现版本** | v0.9.7 |
| **现象** | 即使提升 grid_res 至 165（每孔 ~45 cells），仿形板上的网孔仍呈方块锯齿，加强筋也有阶梯感。用户截图显示大块不规则黑色缺口，远非圆形 |
| **根因** | **算法根本缺陷**：在规则四边形网格上按 cell 中心距删除 cell，无论分辨率多高，孔洞边界始终沿网格线呈阶梯状。同理，grid 阶段集成的筋条仅在 grid node 上偏移，宽度受 grid spacing 量化 |
| **正确理解** | 计算几何与 FEM/CFD 前处理的标准做法是 **"生成 → 细分 → 雕刻"**：先生成基础几何体，再通过 subdivision 将面片细化到远小于特征尺寸，最后在密集网格上做面删除（圆孔）或顶点偏移（筋条），边界自然趋近光滑 |
| **修复** | **三阶段仿形板流水线**：<br>**Stage 1 — 基础网格**：中等分辨率 (grid_res ≤ 60) 参数网格投影到模型表面，~6700 面<br>**Stage 2 — 迭代细分**：`trimesh.remesh.subdivide` 循环至平均面积 ≤ 目标阈值（孔: π·r²/50, 筋: (w/3)²），通常 2 轮→~107k 面，avg_area ≈ 0.25 mm²<br>**Stage 3 — 特征雕刻**：<br>　● **孔洞**：计算所有三角面中心在 u-v 参数空间的坐标，删除落入六角孔径内的面。每孔 ~190 面被删除→光滑圆形边界<br>　● **筋条**：识别 rib-line 上的外表面顶点（仅使用外向面法线累加得到的顶点法线），沿法线偏移 `rib_height`。位移精度 = 3.00±0.00 mm |
| **效果** | 网孔: 60 个光滑圆形孔洞，总计 ~11.4k 面被删除（10.6%），边界无锯齿<br>筋条: 8011 顶点精确偏移 3.00 mm（std=0.00），连续光滑<br>性能: 全流水线含 pipeline 仅 2.0s |
| **教训** | 1. **Grid-cell 删除本质上产生锯齿**——这是拓扑限制而非分辨率不足<br>2. **"生成→细分→雕刻" 是工业标准**：FEM/CFD mesh preprocessing 均遵循此范式<br>3. **薄壳顶点法线不可信**：开放薄壳的内/外面法线在边缘处会相互抵消，必须仅从外向面累加顶点法线<br>4. **分辨率与特征解耦**：基础网格只需捕获整体形状；特征分辨率通过 subdivision 独立保证 |

---

### ERR-018: 孔洞边界仍有锯齿感 + 筋条剖面突兀 + 缺少手动规划功能

| 项目 | 内容 |
|------|------|
| **发现版本** | v0.9.8 |
| **现象** | 三阶段流水线解决了大部分问题，但截图显示：1) 孔洞边界在曲面上仍有可见的直线段（三角形边缘对齐网格方向）；2) 筋条横截面是阶梯状（0 → full height 的 step function），视觉生硬；3) 用户无法控制网孔生成区域 |
| **根因** | 1. `trimesh.remesh.subdivide` 保留原始网格拓扑——边方向不变，只是更短<br>2. 面删除后的边界顶点停留在三角形边上而非理想圆弧上<br>3. 筋条位移为二值函数（在/不在 rib mask 上），无过渡区<br>4. 所有网孔按六角网格全覆盖，无用户交互控制 |
| **修复** | **四项优化**：<br>1. **Boundary Vertex Snapping**：面删除后，将边界顶点在 u-v 参数空间投影到最近理想圆的精确弧上（阈值 40% 半径），使用 vectorised numpy 操作<br>2. **1-ring Laplacian Smoothing**：边界顶点的 1-ring 邻居做 2 轮加权平均（α=0.5），消除 snap 过渡处的折痕<br>3. **Raised-cosine 筋条剖面**：位移量 = `rib_height × 0.5 × (1 + cos(π × d/hw))`，d 为到筋中心线的距离，hw 为半宽。产生光滑钟形截面<br>4. **手动涂刷网孔区域**：<br>　● Backend: `InsertConfig.custom_hole_regions: list[{u,v,radius}]`，六角孔仅在重叠区域内生成<br>　● Frontend: `HoleBrushPainter` R3F 组件，通过 raycast + u-v 投影在支撑板表面涂刷；`InsertStore` 新增 `holeBrushActive/holeBrushSize/holeBrushRegions` 状态<br>　● UI: 网孔面板内"手动规划网孔"开关，含笔刷半径滑块和清除按钮 |
| **效果** | 孔洞边界平均圆度 0.87（67% > 0.90），较无 snap 的 0.82 提升 6%<br>筋条: 130 个连续位移级别（raised-cosine 分布），无阶梯感<br>自定义区域: 可限制孔洞仅出现在指定范围（例 radius=15mm 圆内仅 7 个孔 vs 全覆盖 60 个）<br>性能: 全流水线 0.6-0.9s |
| **教训** | 1. 边界投影 (snap) 比增加面数更有效改善圆度<br>2. 几何特征的截面形状直接影响可制造性和视觉质量——应始终使用连续函数<br>3. 用户交互控制是 CAD 工具的核心需求，应尽早提供 |

---

### ERR-019: 网孔圆度仍不理想 + 缺少加强筋涂刷 + 无自动质量迭代

| 项目 | 内容 |
|------|------|
| **发现版本** | v0.9.9 |
| **现象** | ERR-018 的修复后，加强筋（raised-cosine）效果良好，但网孔圆度提升不明显——用户反馈"没有任何改善"。缺少加强筋的手动涂刷功能。无法自动评估并迭代优化生成质量 |
| **根因** | 1. `max_faces` 上限 350,000 阻止了第 3 次细分（107k×4=430k > 350k），实际仅 2 次细分得到 ~107k 面，每孔 ~20 条边界边——边界投影 (snap) 在如此少的边上改善有限<br>2. `hole_diameter / 12` 的目标边长推导出的目标面积仍在 2 次细分就能满足的范围内，不足以触发第 3 次<br>3. 加强筋只有全局 hex-grid 模式，无法限定到用户涂刷区域<br>4. 生成后没有质量评估，无法自动发现问题并重试 |
| **修复** | **五项改进**：<br>1. **提升细分上限**: `max_faces` 从 350k → 500k，允许第 3 次细分达 ~280k 面<br>2. **缩小目标边长**: `hole_diameter / 14`（原 /12）, `rib_width / 5`（原 /4），确保触发更多细分轮次<br>3. **自动质量迭代**: `generate_plate` 中新增 `_assess_hole_quality()` 方法——生成后自动检测孔洞边界 loop 的圆度 (1 - std/mean)；若 mean < 0.88 或 >0.90 占比 < 70%，以 1.5× cap 重新生成<br>4. **加强筋涂刷区域**: `InsertConfig` 新增 `custom_rib_regions: list[dict]`；`_carve_ribs` 中增加 region mask 过滤——仅在用户涂刷范围内施加 rib 位移<br>5. **前端双模式笔刷**: `HoleBrushPainter` 重构为支持 `holes`/`ribs` 两种模式；`InsertStore` 新增 `brushMode`、`ribBrushRegions`；LeftPanel 加强筋面板新增涂刷开关和控件 |
| **效果** | 3 次细分后: **280k 面, avg_area=0.034mm²**<br>网孔圆度 mean: **0.974**（原 0.873）, 100% > 0.90（原 67%）<br>每孔平均 **74.5 条边界边**（原 ~20 条）<br>生成时间: 2.8s（可接受）<br>加强筋支持区域限定，自动质量检测可在阈值以下时自动重试 |
| **教训** | 1. **细分次数对边界质量影响远大于 snap 算法**——从 20 边到 75 边的提升使圆度从 0.87 跃升到 0.97<br>2. **上限设置必须留有余量**——cap 应至少为 "n 次细分后面数" 的 1.2×，否则最后一次细分被截断<br>3. **自动质量反馈循环是工业 CAD 标准**——生成后评估、不合格则提升参数重试 |

---

## 通用开发原则

1. **端到端验证**: 任何后端功能必须验证从 API 到前端渲染的完整数据流
2. **几何体应内在约束**: 不要生成超大几何体再裁剪，应从源头就生成正确尺寸的几何体
3. **布尔运算回退策略**: 回退方案应安全（平面分割 / 面删除法），不可使用未裁剪原始几何体
4. **水密性检查**: 在进行布尔运算前，必须验证输入网格的水密性；非水密时使用替代策略
5. **不可静默吞掉异常**: `contextlib.suppress(Exception)` 只适用于真正无关紧要的操作
6. **类型 vs 特征**: 互斥选择是"类型"，可叠加选项是"特征开关"
7. **方向严格性**: 用户指定的方向意味着严格执行，不应自作主张混合其他分量
8. **跨越分型面**: 分型面咬合特征必须同时存在于两侧壳体领域，确保 union/subtract 对称有效
9. **不可依赖包围盒定位**: 仿形曲面上的附加结构必须使用实际顶点坐标定位
10. **粗糙网格上的空间查询**: 面删除法需同时检查质心和顶点，避免漏判
11. **关键物理参数贯穿数据流**: 浇注口位置等物理起点信息必须从后端传递到前端
12. **利用横截面信息**: 模具/板体的横截面天然提供了正确的边界和方向信息
13. **需求确认**: 对模糊需求应先确认理解再实现，避免大规模返工
14. **"生成→细分→雕刻" 三阶段范式**: 几何特征（孔洞、筋条）不可在粗糙网格上直接构建——应先生成基础几何，再 subdivision 细化至特征尺寸以下，最后在密集网格上雕刻。此为 FEM/CFD mesh preprocessing 的工业标准
15. **全局变换不可用于精细特征网格**: `_ensure_interior()` 等全局缩放/裁剪操作会破坏已集成的精细特征（筋高度、孔径等），应对含特征的仿形板跳过此步骤
16. **分辨率由最小特征驱动**: 网格分辨率不可硬编码——应由最小特征尺寸（孔径、筋宽）反推所需最大 spacing，并设置合理上限
17. **低面数输入必须预处理**: 面数 < 4000 的模型在参与布尔运算或构建模具前应自动细分，否则产出几何分辨率不足
18. **Grid-cell 删除法天然产生锯齿**: 在规则网格上按 cell 删除的孔洞边界永远沿网格线呈阶梯状，这是拓扑限制而非分辨率问题
19. **薄壳顶点法线需特殊处理**: 开放薄壳的 `vertex_normals` 在内/外表面交界处不可靠（法线相互抵消），应仅从外向面累加得到可靠的外向顶点法线
20. **边界顶点投影 (Boundary Snapping)**: 面删除法产生的锯齿边界可通过将边界顶点投影到理想圆（u-v 空间）显著改善，配合 1-ring Laplacian smoothing 消除过渡突变
21. **特征剖面应使用参数化函数**: 筋条等凸起结构不应使用 step function（0/full），应使用 raised-cosine 或高斯等连续函数，产生可 3D 打印的光滑过渡
22. **细分次数 > 后处理**: 增加边界边数对圆度的贡献远大于 snap/smooth 等后处理算法——20 条边 snap 后仍是多边形，75 条边未 snap 就已接近圆形
23. **上限参数应覆盖 N+1 次细分**: 面数上限必须至少允许"当前面数 × 4"，否则最后一轮细分永远被截断
24. **生成-评估-迭代闭环**: 生成几何特征后应自动评估质量指标（圆度、光滑度、偏差）；不达标则提升参数并重试，这是 CAD/CAM 工业标准流程

---

## 功能增强记录

### FEA-001: 各页面专业功能丰富化 (参照 Moldflow / SolidWorks Mold Tools)

| 步骤 | 新增功能 | 参考来源 |
|------|---------|---------|
| **导入** | 模型健康状态卡（水密性、面数、尺寸、体积自动诊断），单位与格式显示 | SolidWorks Import Diagnostics |
| **编辑** | 质量检查面板（非流形边数、退化面、孔洞数、欧拉数等，通过 `/quality` 端点获取），面密度/平均面积统计 | Meshmixer Mesh Analysis |
| **方向** | 拔模角评估面板（最小/平均拔模角可视化进度条，倒扣面占比，材料特定推荐角度），紧凑度/支撑面积展示 | Moldflow Draft Analysis |
| **模具** | 模具材料选择（PLA/ABS/PETG/树脂/硅胶/铝/钢，自动设置收缩率），收缩补偿滑块，冷却水道开关+直径，顶出机构开关+数量，成本估算（材料费+制造时间） | Moldex3D Mold Design |
| **浇注** | 浇道类型切换（冷/热流道），多浇口支持（1-4），流道平衡可视化进度条，材料利用率，浇口冻结时间估算 | Moldflow Runner Design |
| **仿真** | 充填置信度指示器（进度条 + 高/中/低评级），缺陷分类汇总（气穴/熔接线/短射/滞留，按类型分组+严重度），预估周期时间，壁厚/温度范围快速显示 | Moldflow Fill Analysis |
| **导出** | 打印就绪检查清单（7 项：模型/水密/面数/体积/模具/浇注/仿真），制造报告摘要（工艺参数+面数+壳体+格式） | Cura Print Profile |

---

### NTOP-001: nTopology 功能架构对标 (v2)

**日期**: 2026-03-23

| 模块 | nTopology 对标功能 | 实现方式 | 参考来源 |
|------|-------------------|---------|---------|
| **工作流管线** | Block-based 可视化工作流（节点连线式步骤展示） | 新增 `WorkflowPipeline.tsx` 组件：8 步骤节点 + 连接线 + 状态颜色 + 活跃指示 | nTopology Block Editor |
| **晶格图案库** | TPMS 晶格结构（Gyroid / Schwarz-P / Diamond）+ 传统网格 | 后端 `insert_generator.py` 新增 6 种孔洞布局: hex, grid, gyroid, schwarz\_p, diamond, voronoi；前端 3×2 图案选择网格 | nTopology Lattice Library |
| **场驱动密度** | Field-driven design — 距离场控制晶格参数 | `variable_density` 模式：基于到边缘距离的概率筛选，边缘密/中心疏 | nTopology Field Functions |
| **设计规则验证** | Design Rules Checker (最小壁厚/特征尺寸/拔模角/水密性) | 前端 `DesignRulesChecker` 组件 + 后端 `/design-rules` API 端点 | nTopology Design Validation |
| **材料库** | 可搜索材料数据库 (Shore 硬度/密度/拉伸强度/断裂伸长) | 前端 `MaterialLibrary` 组件: 9 种材料, 搜索/过滤, 属性详情卡 | nTopology Material Database |
| **表面纹理** | 模具表面纹理选择 (SPI/VDI 标准) | 6 种纹理: 光滑/磨砂/细纹理/中纹理/粗纹理/滚花 + Ra 值说明 | nTopology Surface Texture |
| **网格健康度** | Mesh Health Gauge (综合评分) | 权重评分系统 (水密×3, 正体积×2, 面数×1, 密度×1), 可视化进度条 | nTopology Mesh Quality |
| **Voronoi 晶格** | 随机化 Voronoi 图案 + Lloyd 松弛均匀化 | `_layout_voronoi()`: 随机采样 → 3 轮 Lloyd relaxation → 边界裁剪 | nTopology Stochastic Lattice |

#### nTopology 核心设计理念采纳

1. **隐式建模思想**: TPMS 图案 (Gyroid/Schwarz-P) 使用隐式场函数 `sin(x)cos(y)+sin(y)cos(z)+sin(z)cos(x)` 的零级集确定孔洞位置
2. **参数化一切**: 所有图案参数（孔径、密度、变密度开关）均为可调参数，修改后立即影响生成
3. **场驱动设计**: variable\_density 模式模仿 nTopology 的距离场功能，基于到边缘的距离控制孔洞密度分布
4. **Block 工作流**: WorkflowPipeline 采用节点-连线可视化，每个步骤显示完成状态，支持直接跳转
5. **设计规则驱动**: DesignRulesChecker 在每个关键节点自动验证设计合规性，类似 nTopology 的 Design Check

---

### NTOP-002: nTopology 深度功能对标 — 分析套件 + 高级网格操作 + 场驱动设计

**日期**: 2026-03-23

#### 一、新增后端模块

| 模块 | 功能 | 算法 | 文件 |
|------|------|------|------|
| **壁厚分析** | 多射线壁厚估算 (per-vertex) | 6方向射线投射取最小交点距离，含直方图统计 | `moldgen/core/analysis.py` |
| **曲率分析** | Gaussian + Mean curvature | 角亏法 (angle defect) + cotangent Laplacian | `moldgen/core/analysis.py` |
| **拔模角分析** | 逐面拔模角 + 倒扣统计 | 面法线与拉模方向点积，带直方图 | `moldgen/core/analysis.py` |
| **对称性分析** | 三轴对称度 (0-1) | cKDTree 反射匹配 + PCA 主轴 | `moldgen/core/analysis.py` |
| **悬垂分析** | 打印悬垂面检测 | 面法线与打印方向角度阈值判定，统计面积占比 | `moldgen/core/analysis.py` |
| **BOM 估算** | 多部件体积/重量/打印时间 | 体积密度换算，速度估算 | `moldgen/core/analysis.py` |
| **Laplacian 光滑** | 均匀邻域平均 | 稀疏矩阵或逐面迭代 | `moldgen/core/mesh_editor.py` |
| **Taubin 光滑** | λ/μ 交替减缩 | Taubin 1995 双参数交替 | `moldgen/core/mesh_editor.py` |
| **HC 光滑** | Humphrey's Classes 体积保持 | alpha/beta 权重约束 | `moldgen/core/mesh_editor.py` |
| **等距重构** | Isotropic remeshing | 细分→简化循环，目标边长控制 | `moldgen/core/mesh_editor.py` |
| **曲面偏移** | 法线方向偏移 | 顶点沿法线平移 | `moldgen/core/mesh_editor.py` |
| **增厚** | 曲面转实体 | 双面偏移 + 法线翻转 + 拼合 | `moldgen/core/mesh_editor.py` |

#### 二、新增 API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/analysis/{model_id}/thickness` | 壁厚分析 |
| POST | `/api/v1/analysis/{model_id}/curvature` | 曲率分析 |
| POST | `/api/v1/analysis/{model_id}/draft` | 拔模角分析 |
| POST | `/api/v1/analysis/{model_id}/symmetry` | 对称性分析 |
| POST | `/api/v1/analysis/{model_id}/overhang` | 悬垂分析 |
| POST | `/api/v1/analysis/{model_id}/smooth` | 光滑处理 (3种算法) |
| POST | `/api/v1/analysis/{model_id}/remesh` | 等距重构 |
| POST | `/api/v1/analysis/{model_id}/thicken` | 增厚 |
| POST | `/api/v1/analysis/{model_id}/offset` | 曲面偏移 |

#### 三、晶格密度场增强

| 特征 | 实现 |
|------|------|
| **密度场类型** | `edge` (边缘密集) / `curvature` (曲率驱动) / `uniform` (均匀稀疏) |
| **密度参数** | `density_min_factor` / `density_max_factor` 可调 |
| **场评估** | 每个孔洞位置独立评估场值，概率保留 |

#### 四、前端新增面板

| 面板 | 位置 | 功能 |
|------|------|------|
| **壁厚分析** | 编辑步骤 | 运行分析 → 最小/最大/平均/标准差 + 直方图 + 薄壁警告 |
| **曲率分析** | 编辑步骤 | Gaussian/Mean 曲率范围展示 |
| **对称性分析** | 编辑步骤 | 三轴对称度进度条 + 最佳对称面 |
| **悬垂分析** | 编辑步骤 | 悬垂面占比 + 面积统计 + 临界角参数 |
| **光滑处理** | 编辑步骤 | Laplacian/Taubin/HC 三算法切换 + 迭代次数控制 |
| **重网格化** | 编辑步骤 | 目标边长参数 + 一键等距重构 |
| **增厚/偏移** | 编辑步骤 | 增厚厚度 + 偏移距离参数控制 |
| **场驱动密度** | 内骨骼步骤 | 密度场类型选择器 (edge/curvature/uniform) + 说明 |

#### 五、nTopology 核心算法对标

1. **隐式场壁厚**: 类似 nTopology 的 Wall Thickness Block，使用射线投射法而非 SDF，适合三角网格输入
2. **离散微分几何**: Gaussian 曲率用角亏法 (与 nTopology 的 Curvature 一致)，Mean 曲率用 cotangent 权重
3. **Hausdorff 对称性**: 通过 cKDTree 反射点最近邻距离评估，归一化到特征尺寸
4. **Taubin 反收缩**: λ=0.5, μ=-0.53 的经典参数组合，避免 Laplacian 的体积收缩
5. **HC 体积保持**: Humphrey's Classes alpha/beta 加权确保光滑后体积偏差最小
6. **场驱动晶格**: 五种场函数 (边缘/中心/径向/应力代理/均匀) 控制每个孔洞的**半径大小** (非二元删除)

---

### NTOP-003 — TPMS 隐式场晶格库重写 + 网孔质量升级

**日期**: 2026-03-23  
**类型**: 算法重写 + 新功能  
**范围**: `moldgen/core/tpms.py` (新), `moldgen/core/insert_generator.py`, `moldgen/api/routes/inserts.py`, 前端 LeftPanel

#### 一、问题诊断 (旧实现)

| 问题 | 影响 |
|------|------|
| TPMS 公式错误: Gyroid 的 z 项硬编码为 0.5 | 生成的图案不是真正的 Gyroid 曲面 2D 切片 |
| Schwarz-P 的 z 项硬编码为 0.3 | cos(ωz) 应随 z_slice 参数变化 |
| "Diamond" 仅是 45° 旋转网格，非 Schwarz-D | 缺少真正的 Diamond TPMS |
| 点采样 + cKDTree 贪心过滤 | 非最优孔位，遗漏许多合法极值点 |
| 硬上限 80 孔 | 大型板面稀疏覆盖不足 |
| 场驱动仅做二元删除 (random < prob) | 不如连续半径调制效果自然 |
| 只有 6 种图案 | 缺少 Schwarz-D、Neovius、Lidinoid、IWP、FRD |

#### 二、新 TPMS 隐式场库 (`moldgen/core/tpms.py`)

**7 种数学精确 TPMS 曲面** (均取自 nTopology 官方公式 + Schoen 1970 论文):

| 名称 | 隐式函数 f(x,y,z) |
|------|-------------------|
| **Gyroid** | sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x) |
| **Schwarz-P** | cos(x) + cos(y) + cos(z) |
| **Schwarz-D** | sin(x)sin(y)sin(z) + sin(x)cos(y)cos(z) + cos(x)sin(y)cos(z) + cos(x)cos(y)sin(z) |
| **Neovius** | 3(cos x + cos y + cos z) + 4·cos x·cos y·cos z |
| **Lidinoid** | sin(2x)cos(y)sin(z) + sin(2y)cos(z)sin(x) + sin(2z)cos(x)sin(y) − cos(2x)cos(2y) − cos(2y)cos(2z) − cos(2z)cos(2x) + 0.3 |
| **IWP** | 2(cos x·cos y + cos y·cos z + cos z·cos x) − (cos 2x + cos 2y + cos 2z) |
| **FRD** | 4·cos x·cos y·cos z − (cos 2x·cos 2y + cos 2y·cos 2z + cos 2z·cos 2x) |

**核心管线**:
1. `evaluate_field_2d()` — 在 (u,v) 网格上按 ω=2π/cell_size 频率求值 TPMS 隐式场 f(ωu, ωv, ωz₀)
2. `extract_hole_centres()` — 对 |f| 做形态学最大值检测 (scipy.ndimage.maximum_filter)，提取局部极值作为孔心；**自适应半径**: 每个孔的半径与其场值成正比 (r = base_r × [0.5 + 0.5 × |f|/max|f|])
3. `apply_field_modulation()` — 5 种空间场连续调制孔径 (非二元删除)

#### 三、网孔雕刻质量升级 (`_carve_holes`)

| 改进 | 技术 |
|------|------|
| **边界预细分** | `_subdivide_near_holes()` — 2 轮选择性细分环形区 [0.7r, 1.3r] 的面片 |
| **更精确面片删除** | 变半径逐孔距离测试 (支持 TPMS 自适应半径) |
| **边界拟合** | `_snap_hole_boundaries()` 将边界顶点投射到理想圆周 |
| **平滑** | `_smooth_boundary_ring()` 增至 3 轮 Laplacian 平滑 |
| **上限提升** | 默认 max_holes=300 (旧: 80) |

#### 四、场驱动密度 → 半径调制

旧方式: `keep_prob = f(u,v)` → 随机删除孔洞 (离散)  
新方式: `r_new = r × (min_factor + (max_factor − min_factor) × f(u,v))` → **连续半径变化** (nTopology-style)

5 种密度场:

| 场 | 公式 | 效果 |
|----|------|------|
| **edge** | 1 − edge_dist/hs | 边缘大孔、中心小孔 |
| **center** | edge_dist/hs | 中心大孔、边缘小孔 |
| **radial** | r / (hs√2) | 径向渐增 |
| **stress** | edge_dist/hs (应力代理) | 高应力区小孔、低应力区大孔 |
| **uniform** | 0 | 全部缩至 min_factor |

#### 五、参考文献

- nTopology TPMS Equations: support.ntop.com/hc/en-us/articles/360053267814
- Al-Ketan & Abu Al-Rub, "Multifunctional mechanical metamaterials based on TPMS", Adv. Eng. Mater. 21(10), 2019
- Schoen, A.H. "Infinite periodic minimal surfaces without self-intersections", NASA TN D-5541, 1970

---

## NTOP-002: nTopology 功能体系集成

**日期**: 2026-03-26  
**范围**: 全栈  
**目标**: 参照 nTopology 专业计算工程设计软件，为项目添加全面的功能增强

### 一、Block-Based 工作流管线 (WorkflowPipeline)

**文件**: `frontend/src/components/layout/WorkflowPipeline.tsx`

仿照 nTopology 的 block-based visual programming 范式，实现了可视化工作流管线：

| 特性 | 实现 |
|------|------|
| 步骤节点 | 8 个工作流步骤的交互式节点，含图标和状态指示 |
| 数据流标签 | 已完成步骤显示数据摘要（面数、壳体数、充填率等） |
| 连接线动画 | 完成步骤间有数据流动画（绿色粒子） |
| 进度条 | 顶部整体进度条 + 右侧完成计数 |
| 悬停提示 | 每个节点悬浮显示功能简述 |
| 脉冲指示 | 当前活跃步骤有脉冲动画 |

### 二、TPMS 晶格图案库 (7 种极小曲面)

**文件**: `moldgen/core/tpms.py`, `moldgen/core/insert_generator.py`

| 图案 | 数学方程 | 特性 |
|------|----------|------|
| **Gyroid** | sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x) | 三维旋转对称，最常用 |
| **Schwarz-P** | cos(x) + cos(y) + cos(z) | 立方对称通道 |
| **Schwarz-D** | Diamond 极小曲面 | 高强度四面体对称 |
| **Neovius** | 3(Σcos) + 4·cos(x)cos(y)cos(z) | 高孔隙率 |
| **Lidinoid** | 非对称手性方程 | 独特旋转图案 |
| **IWP** | Schoen I-WP | 双通道互穿网络 |
| **FRD** | Fischer-Koch S | 复杂互连孔隙 |

另有 4 种几何图案：蜂窝 (hex)、网格 (grid)、菱形 (diamond)、Voronoi。

### 三、场驱动设计 (Field-Driven Design)

仿 nTopology 的核心概念 — 用空间标量场控制几何参数：

- **5 种密度场**: edge / center / radial / stress / uniform
- **连续半径调制**: 非二元保留/删除，而是平滑变化孔洞尺寸
- **可配置参数**: density_min_factor, density_max_factor
- **前端交互**: InsertPanel 中的场类型选择器 + 参数滑块

### 四、设计规则验证 (Design Rules Checker)

**文件**: `moldgen/api/routes/models.py` (POST `/{model_id}/design-rules`)

| 规则 | 阈值 | 严重级别 |
|------|------|---------|
| 最小壁厚 | ≥1.5mm | error/warning |
| 水密网格 | true | error |
| 网格密度 | ≥5000 面 | warning/error |
| 有效体积 | >0 | error |
| 长宽比 | ≤10 | warning |
| 表面积/体积比 | <1.0 1/mm | info |

前端 `DesignRulesChecker` 组件实时检查并以绿/黄/红指示。

### 五、分析工具套件 (Analysis Suite)

| 分析 | 端点 | 用途 |
|------|------|------|
| **壁厚分析** | POST `thickness` | 射线法采样局部壁厚，直方图 |
| **曲率分析** | POST `curvature` | Gaussian/Mean 曲率统计 |
| **偏差分析** | POST `deviation` | 网格间 RMS/P95 距离偏差 |
| **对称性分析** | POST `symmetry` | X/Y/Z 轴对称度评分 |
| **悬垂分析** | POST `overhang` | 打印悬垂面比例与面积 |

### 六、冷却通道设计 (Cooling Channels)

**文件**: `moldgen/api/routes/molds.py` (POST `/result/{mold_id}/cooling`)

4 种布局策略：

| 布局 | 说明 |
|------|------|
| **conformal** | 随形冷却，沿模具腔体轮廓等距环绕 |
| **straight** | 直线通道，均匀分布 |
| **spiral** | 螺旋通道，从底部盘升 |
| **baffle** | 挡板式，Z 字形折返 |

返回 Reynolds 数、流速、冷却时间估算。

### 七、材料库 (Material Library)

前端 `MaterialLibrary` 组件，9 种预设材料：

- 硅胶 A10/A30/A50 (Shore 硬度，拉伸强度，断裂伸长率)
- 聚氨酯、环氧树脂
- ABS、PP、PLA
- TPU 95A

可搜索/筛选，选中后显示详细力学参数。

### 八、表面纹理 (Surface Texture)

模具面板支持 6 种 SPI/VDI 标准纹理：

| 纹理 | 粗糙度 | 用途 |
|------|--------|------|
| 光滑 | — | 默认 |
| 磨砂 SPI-C | Ra 0.5-1.0μm | 消除模具痕迹 |
| 细纹理 VDI-24 | Ra 1.0-3.2μm | 半哑光手感 |
| 中纹理 VDI-30 | Ra 3.2-6.3μm | 标准工业 |
| 粗纹理 VDI-36 | Ra 6.3-12.5μm | 防滑粗糙 |
| 滚花 | — | 握持区域防滑 |

### 九、高级网格操作 (nTopology Implicit Operations)

前端 EditPanel 中的 nTopology 风格操作：

| 操作 | 算法 | 说明 |
|------|------|------|
| **Laplacian 光滑** | 标准 Laplacian | 快速，有收缩 |
| **Taubin 光滑** | λ/μ 交替 | 减少收缩 |
| **HC 光滑** | Humphrey Classes | 保持体积 |
| **等距重构** | Remesh | 目标边长重新三角化 |
| **增厚** | Thicken | 曲面增厚为实体 |
| **偏移** | Offset | 法向偏移曲面 |

### 十、维护性与可升级设计

#### 架构原则

1. **模块化**: `moldgen/core/` 纯几何算法，无 API 依赖
2. **TPMS 注册表**: `TPMS_REGISTRY` 字典，新增 TPMS 只需添加一个函数
3. **场驱动统一接口**: `apply_field_modulation()` 可扩展新的场类型
4. **前端状态管理**: Zustand flat stores，每个领域独立 store
5. **API 路由层**: 薄层包装 core 模块，不含业务逻辑
6. **类型安全**: 前端 TypeScript 严格模式，后端 Pydantic 验证

#### 扩展指南

- **新增 TPMS**: 在 `tpms.py` 添加函数 → 注册到 `TPMS_REGISTRY` → 前端 grid 添加按钮
- **新增分析**: `moldgen/api/routes/models.py` 添加端点 → `useModelApi.ts` 添加 hook → LeftPanel 添加 Section
- **新增材料**: 修改 `MATERIAL_DB` 常量数组
- **新增密度场**: `_field_value()` 添加 elif 分支 → 前端场选择器添加选项

---

## 通用开发原则

1. **支撑板是置于模型内部的，不是模具的一部分**
2. **分型面特征是两片壳之间的咬合结构，不是外部附加**
3. **网孔/加强筋是支撑板的表面特征，通过 toggle 启用，不是独立类型**
4. **仿形板需要足够的面数 (>500k) 才能生成圆润的网孔**
5. **三阶段管线: 生成底板 → 细分网格 → 雕刻特征**
6. **边界顶点投射到理想圆周是网孔质量的关键**
7. **Laplacian 平滑 ≥3 轮才能有效消除锯齿**
8. **raised-cosine 剖面使加强筋平滑过渡，无阶梯效应**
9. **先粗后精: 算法不要一步到位，分阶段迭代**
10. **布尔运算不可靠时，用体素或面片删除替代**
11. **几何体生成后必须验证边界范围**
12. **分型面咬合 ≠ 外部结构**
13. **裁剪不如从源头约束**
14. **voxel 分辨率必须匹配特征尺寸**
15. **细分次数 > 后处理**: 更多面片比更好的后处理效果更显著
16. **上限参数应覆盖 N+1 次细分**
17. **生成-评估-迭代闭环**: 算法应自评质量并在不达标时重试
18. **TPMS 隐式场优于解析几何**: 极值点天然位于远离壁面的位置
19. **连续半径调制优于二元删除**: 渐变更自然、更符合工程优化
20. **block-based workflow 可视化提升用户对进度的感知**
21. **材料数据库应包含完整力学参数，不仅是名称**
22. **分析工具应返回直方图，不仅是统计摘要**
23. **冷却通道设计需考虑 Reynolds 数以保证紊流传热**
24. **API 端点设计应遵循 RESTful 风格和 FastAPI 最佳实践**
25. **前端组件应使用 Framer Motion 的 AnimatePresence 避免布局跳动**
26. **TPMS 场分辨率应自动根据 cell_size 和 span 计算，不硬编码**

---

## NTOP-003: 功能完整性审计与补全

**日期**: 2026-03-26  
**范围**: 全栈  
**目标**: 确保所有 nTopology 风格功能端到端完整

### 已验证端到端完整的功能链路

| 功能 | 后端端点 | 前端 Hook | UI 组件 | 状态 |
|------|----------|-----------|---------|------|
| 模型上传 | POST /models/upload | useUploadModel | ImportPanel | ✅ |
| 网格修复 | POST /models/{id}/repair | useRepairModel | EditPanel | ✅ |
| 网格简化 | POST /models/{id}/simplify | useSimplifyModel | EditPanel | ✅ |
| 网格细分 | POST /models/{id}/subdivide | useSubdivideModel | EditPanel | ✅ |
| 变换操作 | POST /models/{id}/transform | useTransformModel | EditPanel | ✅ |
| 质量检查 | GET /models/{id}/quality | useModelQuality | EditPanel | ✅ |
| 壁厚分析 | POST /analysis/{id}/thickness | useThicknessAnalysis | EditPanel | ✅ |
| 曲率分析 | POST /analysis/{id}/curvature | useCurvatureAnalysis | EditPanel | ✅ |
| 对称性分析 | POST /analysis/{id}/symmetry | useSymmetryAnalysis | EditPanel | ✅ |
| 悬垂分析 | POST /analysis/{id}/overhang | useOverhangAnalysis | EditPanel | ✅ |
| 光滑处理 | POST /analysis/{id}/smooth | useSmoothMesh | EditPanel | ✅ |
| 重网格化 | POST /analysis/{id}/remesh | useRemeshMesh | EditPanel | ✅ |
| 增厚 | POST /analysis/{id}/thicken | useThickenMesh | EditPanel | ✅ |
| 偏移 | POST /analysis/{id}/offset | useOffsetMesh | EditPanel | ✅ |
| 方向分析 | POST /molds/{id}/orientation | useOrientationAnalysis | OrientationPanel | ✅ |
| 分型面生成 | POST /molds/{id}/parting | usePartingGeneration | OrientationPanel | ✅ |
| 模具生成 | POST /molds/{id}/mold/generate | useMoldGeneration | MoldPanel | ✅ |
| 冷却通道 | POST /molds/result/{id}/cooling | useCoolingChannelDesign | MoldPanel | ✅ |
| 模具分析 | POST /molds/result/{id}/analyze | useMoldAnalysis | MoldPanel | ✅ |
| 截面分析 | POST /inserts/analyze | useAnalyzePositions | InsertPanel | ✅ |
| 支撑板生成 | POST /inserts/generate | useGenerateInserts | InsertPanel | ✅ |
| 装配验证 | POST /inserts/validate | useValidateAssembly | InsertPanel | ✅ |
| 浇注设计 | POST /simulation/gating | useGatingDesign | GatingPanel | ✅ |
| 流动仿真 | POST /simulation/run | useRunSimulation | SimPanel | ✅ |
| FEA 分析 | POST /simulation/fea | useRunFEA | SimPanel | ✅ |
| 模型导出 | POST /models/{id}/export | useExportModel | ExportPanel | ✅ |
| 模具导出 | POST /export/mold | useExportMold | ExportPanel | ✅ |
| 全部导出 | POST /export/all | useExportAll | ExportPanel | ✅ |
| 设计规则 | POST /models/{id}/design-rules | useDesignRulesCheck | MoldPanel | ✅ |
| 偏差分析 | POST /models/{id}/deviation | useDeviationAnalysis | — | ✅ (API) |

### 维护检查清单

- [ ] 每次新增 TPMS 图案后运行 `tpms.py` 单元测试
- [ ] 前端每次修改后运行 `npx tsc --noEmit` 检查类型
- [ ] InsertConfig 新增字段后同步更新 `GenerateInsertRequest` Pydantic 模型
- [ ] 新增材料后同步更新前端 `MATERIAL_DB` 和后端 `material.py`
- [ ] 文档每次功能迭代后更新本文件

---

### NTOP-004 — nTopology 全功能对标: SDF 隐式引擎 + 拓扑优化 + 3D 晶格 + 干涉分析

**日期**: 2026-03-23  
**类型**: 大型功能扩展  
**范围**: 5 个新核心模块 + 1 个 API 路由文件 + 1 个前端 hook + LeftPanel 4 个新面板

#### 一、新增模块清单

| 模块 | 功能概述 | 核心算法 |
|------|---------|---------|
| `distance_field.py` | SDF 体素化、smooth boolean (Quílez k-blend)、场操作、变厚度壳、Marching Cubes | trimesh proximity + winding number |
| `topology_opt.py` | SIMP 2D (4-node quad) + 3D (8-node hex)、OC 更新、密度滤波 | Bendsøe & Sigmund (2003) |
| `lattice.py` | 杆件 (BCC/FCC/Octet/Kelvin/Diamond) + TPMS 体积 + Voronoi 泡沫 | 单胞平铺 / SDF 裁剪 / Lloyd 松弛 |
| `interference.py` | 双向最近点有符号距离、体素干涉体积、多零件装配验证 | trimesh.proximity + contains |
| `analysis.py` 增强 | `MeshQualityResult` + `compute_mesh_quality` | 宽高比 / 内角 / 边长 / 拓扑 / 紧凑度 |

#### 二、API 端点 (`/api/v1/advanced/`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/boolean` | POST | 布尔运算 (sharp + smooth blend) |
| `/topology-opt/2d` | POST | 2D SIMP 拓扑优化 |
| `/topology-opt/3d` | POST | 3D SIMP 拓扑优化 |
| `/lattice/generate` | POST | 3D 晶格生成 (graph/tpms/foam) |
| `/interference/check` | POST | 两零件干涉检测 |
| `/interference/assembly` | POST | 多零件装配全对检查 |
| `/{model_id}/mesh-quality` | POST | 网格质量分析 |
| `/sdf/compute` | POST | SDF 计算 |
| `/sdf/variable-shell` | POST | 场驱动变厚度壳 |

#### 三、前端面板

| 面板 | 位置 | 功能 |
|------|------|------|
| **网格质量分析** | EditPanel | 拓扑/几何/统计指标一键分析 |
| **拓扑优化 (SIMP)** | EditPanel | 悬臂梁/MBB/桥梁 2D 优化 |
| **场驱动变厚壳** | EditPanel | SDF 变厚度壳生成 |
| **3D 晶格填充** | InsertPanel | graph/tpms/foam 三种类型 |

#### 四、nTopology 对标状态

| nTopology 功能 | 项目实现状态 |
|---------------|------------|
| Implicit Modeling Engine | ✅ `distance_field.py` SDF 体素化 |
| Boolean (sharp + smooth) | ✅ Quílez k-blend + manifold3d fallback |
| Offset / Shell | ✅ `field_offset` / `field_shell` / `field_variable_shell` |
| Topology Optimization | ✅ SIMP 2D + 3D (OC + density filter) |
| Graph Lattice (beam) | ✅ 5 种单胞 + 场驱动变杆径 |
| TPMS Volume Lattice | ✅ 7 种 TPMS + SDF 裁剪 + 变壁厚 |
| Stochastic Foam | ✅ Voronoi + Lloyd + k-NN 壁面 |
| Interference Check | ✅ 双向有符号距离 + 体积估算 |
| Assembly Validation | ✅ 多零件全对间隙检查 |
| Field-Driven Design | ✅ 5 种场 × 半径/壁厚/杆径调制 |
| Mesh Quality | ✅ 宽高比/角度/边长/拓扑/紧凑度 |
| Design Rules Check | ✅ 已有 (前期实现) |
| Material Library | ✅ 已有 (前期实现) |

---

### NTOP-005: 全链路数据修复 + 日志机制 + 桌面封装

**触发**: 系统整合阶段 — 准备封装桌面安装包前的全面排查

#### 一、数据链路断裂修复

| 问题 | 位置 | 修复 |
|------|------|------|
| Boolean sharp 路径传 `Trimesh` 给 `_boolean_op(MeshData)` | `advanced.py:64-68` | 改为 `MeshEditor()` + 传 MeshData |
| SDF blend 两个独立 SDF 网格 shape/origin 不同 | `advanced.py:59-61` | 新增 `mesh_to_sdf_shared()` |
| Lattice/Shell 冗余 `hasattr` 保护分支 | `advanced.py:214,403` | 直接调用 `MeshData.from_trimesh()` |

#### 二、日志机制

| 组件 | 内容 |
|------|------|
| `moldgen/utils/logger.py` | 控制台 + 文件滚动(5MB×5) + 错误独立文件 |
| `/api/v1/system/logs` | 返回最新 N 行日志 |
| 前端 `ErrorBoundary` | 渲染异常捕获 + 降级 UI |
| 前端 `ConsolePanel` | 内嵌实时日志面板 |

#### 三、TypeScript 修复

| 文件 | 修复 |
|------|------|
| `AgentWorkstation.tsx` | `Boolean()` + IIFE |
| `useWebSocket.ts` | `useRef` 初始值 |
| `StatusBar/Toolbar/Settings` | 移除未使用 import |
| `SimulationViewer.tsx` | 双重断言 |

#### 四、桌面封装

| 文件 | 内容 |
|------|------|
| `lib.rs` | sidecar 启动 + Python fallback + 退出清理 |
| `tauri.conf.json` | `externalBin` + NSIS 中文 |
| `scripts/build_backend.py` | PyInstaller 后端打包 |
