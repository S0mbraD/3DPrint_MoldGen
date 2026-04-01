# 核心算法设计

## 1. 模型预处理算法

### 1.1 网格修复流程

```
输入网格 M (STL/OBJ/FBX/3MF/STEP/PLY)
  │
  ├─ 0. 格式适配：FBX 去除骨骼/动画/材质，仅保留几何
  ├─ 1. 退化面片移除：面积 < ε 的三角形
  ├─ 2. 重复顶点合并：距离 < δ 的顶点
  ├─ 3. 法线一致化：确保所有面片法线朝外
  ├─ 4. 孔洞填充：检测边界环并三角化填充
  ├─ 5. 非流形边修复：分裂共享非流形边的面片
  ├─ 6. 自相交修复：检测并解决自相交三角形
  └─ 7. 流形验证：确认输出为封闭2-流形
  │
输出 WatertightMesh M'
```

### 1.2 FBX 特殊处理

FBX 文件可能包含场景图、骨骼、动画、多材质等非几何数据：

```python
def load_fbx(filepath):
    scene = pyassimp.load(filepath)
    meshes = []
    for mesh in scene.meshes:
        # 仅提取顶点和面数据
        vertices = mesh.vertices
        faces = mesh.faces
        # 应用节点变换矩阵（FBX 含层级变换）
        transform = get_node_transform(scene, mesh)
        vertices = apply_transform(vertices, transform)
        meshes.append(create_mesh(vertices, faces))
    
    # 合并多个网格为单一网格（如模型由多部分组成）
    combined = merge_meshes(meshes)
    return combined
```

## 2. 网格细化与简化算法（新增）

### 2.1 网格细化 (Subdivision/Refinement)

#### Loop 细分（三角网格专用）
每次迭代将每个三角形分为 4 个子三角形：

```
原始三角形:          Loop 细分后:
    A                    A
   / \                  / \
  /   \               /   \
 /     \            e_AB---e_CA
B───────C          / \   / \
                  /   \ /   \
                 B───e_BC────C

奇数顶点(新): e_AB, e_BC, e_CA — 边中点的加权平均
偶数顶点(旧): A, B, C — 原顶点的加权重新定位
```

**权重计算**：
- 奇数顶点（内部边）: e = 3/8(V₁+V₂) + 1/8(V₃+V₄)
- 奇数顶点（边界边）: e = 1/2(V₁+V₂)
- 偶数顶点: V' = (1-n·β)V + β·Σ(neighbors)，β = 1/n·(5/8-(3/8+1/4·cos(2π/n))²)

**实现**：trimesh `subdivide_loop(iterations=N)`

#### 自适应细化
不均匀细化，仅在需要的区域增加面片密度：

```python
def adaptive_refine(mesh, criteria, target_edge_length):
    """
    criteria: 细化判据
    - "curvature": 高曲率区域细化（曲面细节保留）
    - "edge_length": 超长边细分
    - "area": 大面积三角形细分
    - "region": 用户指定区域细化
    """
    while True:
        faces_to_refine = select_faces(mesh, criteria, target_edge_length)
        if len(faces_to_refine) == 0:
            break
        mesh = trimesh.remesh.subdivide(mesh, face_index=faces_to_refine)
    return mesh
```

#### 按尺寸细化
`trimesh.remesh.subdivide_to_size(mesh, max_edge)` — 将所有边细分到不超过指定长度。

### 2.2 网格简化 (Decimation)

#### QEM 简化（二次误差度量）

```
算法步骤:
1. 为每个顶点计算二次误差矩阵 Q（基于相邻面片平面方程）
2. 为每条边计算坍缩代价 = v'ᵀ(Q₁+Q₂)v'（v'为最优新顶点位置）
3. 使用优先队列，迭代执行代价最小的边坍缩
4. 更新受影响边的代价
5. 重复直到达到目标面数或误差阈值

优点: 保持模型整体形状，误差可控
```

**实现**：Open3D `mesh.simplify_quadric_decimation(target_face_count)`

#### 简化策略

```python
class SimplificationStrategy:
    # 比例简化：保留原始面数的百分比
    def by_ratio(self, mesh, ratio: float):  # ratio=0.5 → 面数减半
        target = int(len(mesh.faces) * ratio)
        return open3d_simplify(mesh, target)
    
    # 目标面数简化
    def by_face_count(self, mesh, target_faces: int):
        return open3d_simplify(mesh, target_faces)
    
    # 误差阈值简化：简化到误差超过阈值为止
    def by_error_threshold(self, mesh, max_error: float):
        return iterative_simplify(mesh, max_error)
    
    # 多级 LOD 生成（分析用简化版 + 最终输出原始版）
    def generate_lod(self, mesh, levels=[1.0, 0.5, 0.25, 0.1]):
        return [self.by_ratio(mesh, r) for r in levels]
```

### 2.3 细化/简化流程

```
导入模型
  │
  ▼
┌──────────────────────────┐
│  网格质量评估              │
│  ├─ 面片数量              │
│  ├─ 最小/最大边长          │
│  ├─ 最差三角形品质         │
│  └─ 曲面细节分辨率估计     │
└──────────┬───────────────┘
           │
           ▼
     ┌─────┴─────┐
     │ 用户选择？  │
     └─────┬─────┘
     ┌─────┼──────────┐
     ▼     ▼          ▼
  细化   保持原样    简化
     │                │
     ▼                ▼
  Loop 细分         QEM 简化
  自适应细化        比例/面数/误差
     │                │
     └────────┬───────┘
              ▼
         修复 + 验证
         (确保流形性)
```

## 3. 模型自定义编辑算法（新增）

### 3.1 编辑操作类型

| 操作 | 类型 | 实现 |
|------|------|------|
| 平移/旋转/缩放 | 基础变换 | 矩阵变换 |
| 镜像 | 变换 | 反射矩阵 + 法线翻转 |
| 布尔运算 | 组合 | manifold3d (union/difference/intersection) |
| 测量 | 只读 | 顶点距离、角度、面积计算 |
| 截面查看 | 只读 | 平面-网格求交 |
| 局部缩放 | 变形 | 区域选择 + 权重衰减变换 |
| 顶点/面删除 | 拓扑编辑 | 删除 + 孔洞填充 |
| 抽壳 | 几何 | 法线方向偏移 + 布尔差集 |
| 标注 | 元数据 | 3D 空间文本/箭头标记 |

### 3.2 撤销/重做系统

```python
class EditHistory:
    """操作历史栈，支持撤销/重做"""
    
    def __init__(self, max_history=50):
        self.undo_stack: List[EditOperation] = []
        self.redo_stack: List[EditOperation] = []
    
    def execute(self, operation: EditOperation, mesh: MeshData) -> MeshData:
        result = operation.apply(mesh)
        self.undo_stack.append(operation)
        self.redo_stack.clear()
        return result
    
    def undo(self, mesh: MeshData) -> MeshData:
        if not self.undo_stack:
            return mesh
        op = self.undo_stack.pop()
        self.redo_stack.append(op)
        return op.reverse(mesh)
    
    def redo(self, mesh: MeshData) -> MeshData:
        if not self.redo_stack:
            return mesh
        op = self.redo_stack.pop()
        self.undo_stack.append(op)
        return op.apply(mesh)

class EditOperation:
    """编辑操作基类"""
    type: str
    params: dict
    
    def apply(self, mesh: MeshData) -> MeshData: ...
    def reverse(self, mesh: MeshData) -> MeshData: ...
```

### 3.3 区域选择

```python
class SelectionMethods:
    def select_by_click(mesh, ray_origin, ray_dir) -> List[int]:
        """光线投射选择单个面片"""
    
    def select_by_brush(mesh, center, radius) -> List[int]:
        """画刷选择球形区域内的面片"""
    
    def select_by_lasso(mesh, screen_polygon, camera) -> List[int]:
        """套索选择屏幕多边形内的面片"""
    
    def select_connected(mesh, seed_face, angle_threshold) -> List[int]:
        """从种子面片扩展选择法线角度相近的连通面片"""
    
    def select_by_normal(mesh, direction, threshold) -> List[int]:
        """选择法线朝向特定方向的面片"""
```

## 4. 最优脱模方向分析（GPU 加速版）

### 4.1 算法概述

目标：找到使模型最易脱模的方向集合。GPU 加速关键路径。

### 4.2 GPU 加速可见性分析

```python
def gpu_visibility_analysis(mesh, direction, gpu_compute):
    """
    GPU 加速版可见性分析
    使用 cuBVH 进行批量光线投射
    """
    normals = mesh.face_normals
    facing_mask = np.dot(normals, direction) > 0
    
    origins = mesh.triangles_center[facing_mask]
    ray_dirs = np.tile(direction, (len(origins), 1))
    
    # cuBVH GPU 批量光线投射 (比 embree CPU 快 5-20x)
    bvh = gpu_compute.build_bvh(mesh)
    hits = gpu_compute.ray_intersect_batch(
        origins + direction * 1e-5,
        ray_dirs,
        bvh
    )
    
    visibility = np.zeros(len(mesh.faces), dtype=np.int8)
    visibility[facing_mask & ~hits] = 1   # 可见
    visibility[facing_mask & hits] = -1   # 倒扣
    visibility[~facing_mask] = 0          # 背面
    
    return visibility
```

### 4.3 GPU 并行方向评估

```python
def parallel_direction_scoring(mesh, candidate_directions, gpu_compute):
    """
    并行评估所有候选方向
    
    GPU 策略:
    - 将所有方向的光线投射打包为一个大批次
    - 单次 GPU kernel 调用完成所有方向的可见性计算
    - CPU 上进行评分汇总
    """
    all_origins = []
    all_directions = []
    direction_offsets = []
    
    offset = 0
    for d in candidate_directions:
        facing = np.dot(mesh.face_normals, d) > 0
        origins = mesh.triangles_center[facing]
        dirs = np.tile(d, (len(origins), 1))
        all_origins.append(origins)
        all_directions.append(dirs)
        direction_offsets.append((offset, offset + len(origins)))
        offset += len(origins)
    
    # 单次 GPU 批量投射
    all_origins = np.concatenate(all_origins)
    all_directions = np.concatenate(all_directions)
    all_hits = gpu_compute.ray_intersect_batch(all_origins, all_directions, bvh)
    
    # 分割结果并评分
    scores = []
    for i, d in enumerate(candidate_directions):
        start, end = direction_offsets[i]
        hits = all_hits[start:end]
        score = compute_direction_score(mesh, d, hits)
        scores.append(score)
    
    return scores
```

### 4.4 方向评分系统

```
Score(d) = w₁·V(d) + w₂·F(d) + w₃·P(d) + w₄·S(d) + w₅·D(d)
```

| 指标 | 符号 | 说明 | 默认权重 |
|------|------|------|---------|
| 可见面积比 | V(d) | 可见表面积 / 总表面积 | 0.30 |
| 平坦度 | F(d) | 分型线投影平坦度 | 0.20 |
| 片数惩罚 | P(d) | 所需模具片数的倒数 | 0.20 |
| 对称性 | S(d) | 各片体积均衡度 | 0.15 |
| 拔模角 | D(d) | 最小拔模角（越大越好） | 0.15 |

### 4.5 候选方向生成与筛选

```
候选方向集合:
  主轴方向: ±X, ±Y, ±Z (6个)
  面片法线: 面积最大K个面片法线 (K=20)
  PCA方向:  3个主成分 × 2方向 (6个)
  球面采样: 斐波那契均匀采样N个 (N=100 可配置)
  对称轴:   如有对称性 (M个)

层次筛选 (GPU加速):
  1. 粗筛 — GPU批量可见性 → top-20%
  2. 细筛 — 完整多准则评分 → top-5
  3. 精选 — 用户可视化选择或自动最高分
```

### 4.6 最小方向覆盖（集合覆盖，贪心）

```python
def greedy_direction_cover(mesh, candidate_directions, gpu_compute):
    uncovered = set(range(len(mesh.faces)))
    selected_directions = []
    
    while uncovered:
        # GPU 并行计算每个方向能覆盖的未覆盖面片数
        best_dir = max(candidate_directions,
                       key=lambda d: len(visible_set(mesh, d, gpu_compute) & uncovered))
        selected_directions.append(best_dir)
        uncovered -= visible_set(mesh, best_dir, gpu_compute)
    
    return selected_directions
```

## 5. 分型面生成算法 (v3 实现)

### 5.1 分型线提取

```
给定脱模方向 d:

策略 1 — 严格阈值法 (原始):
  1. 面片分类: upper (n·d > cos(85°)), lower (n·d < -cos(85°))
  2. 分型边: 相邻面分属 upper/lower 的边

策略 2 — 法线符号变化法 (v3 新增, 更鲁棒):
  1. 计算每个面的 dot = normal · direction
  2. 分型边: 相邻面的 dot 符号不同 (正→负 或 负→正)
  3. 当策略1找到 < 3 条边时自动切换到策略2
  4. 保证: 任何曲面模型在"赤道"处都有符号变化

环路构建: 将分型边连接为有序闭合环路
平滑: 向量化 Laplacian 平滑 (np.roll, 5 次迭代)

保证输出: 即使无分型线, 也在质心处生成平面分型面
```

### 5.2 分型面构建

**方法 A — 平面投影法**（分型线近似平面时）
**方法 B — 规则面法**（一般情况）
**方法 C — 距离场法**（最通用，可 GPU 加速）

```python
def generate_parting_surface_sdf(mesh, direction, parting_line, gpu_compute):
    """GPU 加速的 SDF 方法生成分型面"""
    # GPU 计算模型 SDF
    sdf = gpu_compute.compute_sdf(mesh, grid_resolution=128)
    
    # 在分型线处约束零等值面
    constrained_sdf = apply_parting_constraints(sdf, parting_line)
    
    # Marching Cubes 提取等值面
    parting_surface = marching_cubes(constrained_sdf, level=0)
    
    # 修剪到模具包围盒
    parting_surface = clip_to_bounding_box(parting_surface, mold_bbox)
    
    return parting_surface
```

### 5.3 多片壳分割与拆卸顺序

```
1. 多方向分割 → k 个壳体区域
2. 壳间遮挡有向图 → 拓扑排序 → 拆卸顺序
3. 验证：每个壳可沿对应方向无碰撞脱模
```

## 6. 模具壳体生成算法 (v4 实现)

### 6.1 三级策略壳体构造

```
策略 A — 布尔运算 (首选，产生最佳质量):
  1. 外壳 = Box(cavity + margin + wall_thickness).to_mesh()
  2. 内腔 = 模型 + clearance 偏移 (Laplacian 平滑法线)
  3. mold_solid = _robust_boolean_subtract(外壳, 内腔)
     - 引擎优先级: manifold3d → trimesh(manifold) → trimesh(blender) → trimesh(default)
     - 始终尝试，不再要求模型水密
  4. split(mold_solid, 分型面) → 2 个半壳：`trimesh.slice_plane`（需 **shapely** + **rtree**）或回退到 **`slice_faces_plane`**（仅 numpy 裁剪，保留与剖切面相交的壳体外轮廓三角片），再由 `_seal_parting_plane_gaps` 封补分型开口。
     - **仅**用 `(面心−质心)·n ≥ 0` 选三角片会在剖切面相交处丢掉跨面壳体墙，方块壳会退化成「分型盘 + 随形内腔」，切片器里看不见侧壁。

策略 B — 体素化 + Marching Cubes (布尔失败时的可靠回退):
  1. 体素化模型: trimesh.voxelized(pitch)；pitch 由 ``min(0.55, max_extent/160, wall/4)`` 等与尺寸挂钩的目标步长推导，分辨率 clamp 在 96…320，较旧的 ``max_extent/80`` 更细以减轻视口台阶感。
  2. 膨胀 clearance: scipy.ndimage.binary_dilation(model_voxels, iterations=ceil(clearance/pitch))
  3. 填充外壳: np.pad(cavity_voxels, wall_px) → box_voxels & ~padded_cavity
  4. Marching Cubes: skimage.measure.marching_cubes(mold_voxels, 0.5) → 网格
  5. 可选简化: simplify_quadric_decimation(100k faces)
  6. 分割半壳: slice_plane(center, direction, cap=True)

策略 C — 直接拼接 (最后手段):
  1. 外壳 Box 与内腔翻转网格均用与策略 A 相同的半空间剖切（`_safe_slice`），**不得**仅按面心点积二分三角片（参见策略 A）。
  2. concatenate(box_half, cavity_half)，再经修复与 `_seal_parting_plane_gaps` 封补。

自动选择: 始终 A → 失败 → B → 失败 → C
```

### 6.2 空腔偏移 (Laplacian 平滑法线)

```
原始方法: new_v = vertex + normal × clearance
问题: 凹面区域法线发散导致自相交

改进方法:
  1. Laplacian 平滑法线 (1次迭代, λ=0.5):
     smooth_n[v] = 0.5 × normal[v] + 0.5 × mean(normal[neighbors])
  2. 重新归一化: smooth_n = smooth_n / ||smooth_n||
  3. new_v = vertex + smooth_n × clearance
  效果: 邻域法线方向收敛, 大幅降低自相交
```

### 6.3 浇筑口/排气口切割 (v4 新增)

```
v4 之前: 孔位仅作为元数据存储，壳体网格无实际孔洞
v4: 使用布尔差集将圆柱体从壳体中减去

流程:
  1. 为每个浇筑口/排气口创建圆柱体 (_make_cylinder)
  2. 对每个壳体逐个执行 _robust_boolean_subtract(shell, cylinder)
  3. 成功 → 壳体含实际通孔; 失败 → 保留原始壳体
  4. 修复结果网格 (_repair_mesh)
```

### 6.4 网格修复 (v4 增强)

每个壳体生成后自动执行:
```python
remove_degenerate_faces/更新面   # 移除退化面（nondegenerate_faces）
repair.fill_holes()              # 填充孔洞
repair.fix_normals()            # 修复法线
repair.fix_winding()            # 修复面绕序
repair.fix_inversion()          # 修复反转
_dedupe_opposite_or_duplicate_tris()  # 仅在不增加开放边条数时去掉重合三角片
_compact_mesh_vertex_indices()   # 将 faces 索引压到稠密 0…N-1，避免残留大索引
```

### 6.4.1 脱模方向分层封补 — 解决切片「顶面未封闭 / 暗色缝隙」(v6)

**现象**：布尔半壳在分型面附近除了一圈外轮廓外，往往还有内腔开口；若仅对分型面一层做「单环填盖」，会把外环与内环**各自**当成独立圆盘填充，顶视图在内外之间留下**环形无三角区**，切片软件显示深色缝并报告非封闭体。

**改进**（`mold_builder._seal_parting_plane_gaps`）：

1. 从当前三角网格用面边统计得到**全体**开放边（每条无向边仅属于一个三角形）。
2. 按边中点在**脱模方向**（与 `MoldShell.direction` 一致）上的标高 **分桶**（桶宽约 1.25 mm 或模型尺寸的约 2%，避免同一平面开口的边被拆到多个桶里形不成闭坏）。
3. 在每个桶内将开放边连成闭坏，按 2D 投影后的**嵌套关系**区分**外环**与**孔环**，使用 **`manifold3d.triangulate([外环.xy, 孔1.xy, …])`** 一次性填充**带孔的平面**（不依赖 shapely；与仅 `pip install trimesh` 的环境兼容）。
4. 将新三角形并入网格后执行 **`_compact_mesh_vertex_indices`**，保证顶点索引与 `faces` 一致，便于后续导出 GLB/STL。

**切片依赖（重要）**：`trimesh.slice_plane` 会链式依赖 **shapely** 与 **rtree**。二者缺任一都会令 `slice_plane` 失败并退回到 `slice_faces_plane`；MoldGen 已实现该回退以免丢失侧壁，但此时分型封补更依赖 `_seal_parting_plane_gaps`。为获得「自动加盖」的剖切与水密半壳，**请在 `mesh` 可选依赖中同时安装 `shapely` 与 `rtree`**（`pyproject.toml` / `environment.yml` 已列出）。

### 6.5 拔模角检查

每个壳体自动分析侧面拔模角：
```python
side_faces = faces where |normal · direction| < 0.3  # 侧面
draft_angle = arcsin(|normal · direction|) for each side face
min_draft = min(draft_angles)
is_printable = min_draft >= config.min_draft_angle  # default 1°
```

### 6.6 装配结构

- **定位销/孔**: 实际圆柱网格 (`trimesh.creation.cylinder`)
- **浇筑口**: 漏斗形网格 (圆柱 + 圆锥), 布尔差集切入壳体
- **排气口**: 细管圆柱网格, 布尔差集切入壳体
- 所有几何体均生成 `MeshData`, 前端可直接渲染

### 6.7 分型面互锁样式 (v5 新增)

支持 5 种分型面样式，通过 `parting_style` 参数切换:

```
flat (默认):    平面分割 — 最简单，依赖定位销对齐
dovetail 燕尾榫: 梯形截面凸凹咬合 — 防止横向滑移，自对准
zigzag 锯齿形:  三角形齿状咬合 — 增大接触面积，防旋转
step 阶梯形:    交替高低台阶 — 增加垂直方向锁定力
tongue_groove 榫槽: 矩形凸凹配合 — 精确对位，易脱模

算法:
  1. mold_solid.section(过模型质心的分型平面) → 多条 2D 折线（外壳截面 + 腔体截面）
  2. **回路选取 (v6 修正)**：对每条路径计算 2D 鞋带头面积；**取面积最大者**为外壳分型轮廓（避免高面数内腔周长更长的误选）；面积退化时再按周长回退
  3. 沿该轮廓按 parting_pitch 弧长采样（`_sample_outline_at_pitch`），得到切向一致的放置点
  4. 每个特征为小型局部化互锁单元（`_make_interlock_unit`），在采样点处以切向/法向定向
  5. 布尔：上模 union 互锁体，下模 subtract；失败则顶点位移回退
  6. 参数: parting_depth (特征深度 mm), parting_pitch (间距 mm)

**半壳分割**: `_safe_slice` 优先 `slice_plane`（需 shapely+rtree）；失败则 `intersections.slice_faces_plane`（几何裁剪）；**最后手段**才按 `(面心−质心)·n` 选三角片 (`_extract_submesh`)。内腔翻转网格的拼接半壳同样走 `_safe_slice`，避免方块壳只剩顶底而无侧壁。

**说明文档 / 故障记录**: 误选内腔回路问题见 `docs/error-log.md` **ERR-020**。
```

### 6.8 螺丝固定法兰 (v5 新增)

在模具外壁分型面处生成安装法兰:

```
配置参数:
  add_flanges: bool     — 是否启用
  flange_width: float   — 法兰伸出宽度 (mm)
  flange_thickness: float — 法兰厚度 (mm)
  screw_hole_diameter: float — 螺丝孔直径 (mm, 默认 M4)
  n_flanges: int        — 法兰数量

算法:
  1. 计算法兰位置: 在分型平面的外围, 按 360°/n_flanges 均匀分布
  2. 每个法兰: Box(width × thickness × width*0.8) + 旋转对齐到径向
  3. 螺丝孔: _make_cylinder(法兰中心, direction, screw_diameter/2)
  4. 组合: concatenate(shell, flange_box) → _robust_boolean_subtract(combined, screw_cylinder)
  5. 修复: _repair_mesh 确保水密性
```

### 6.9 FDM 打印适配

```
检查项:
1. 最小壁厚 ≥ 0.8mm (2× 线宽)
2. 悬垂角 ≤ 45° (否则标记需支撑)
3. 拔模角 ≥ 1° (v3: 自动检测并标记 is_printable)
4. 平底面优化 (每壳有大平面)
5. 桥接检查 (跨度 > 阈值添加肋)
6. 圆角 R ≥ 0.5mm (减少应力集中)
```

## 7. 内嵌插板生成算法（v2: 多类型支撑板）

### 7.1 算法概述

插板（Insert Plate）是嵌入硅胶模具内部的 3D 打印刚性板件，为硅胶提供结构支撑，并通过表面锚固结构实现机械互锁。

### 7.1b 支撑板类型 (v2 新增)

| 类型 | 说明 | 适用场景 |
|------|------|---------|
| **flat** (平板) | 模型截面挤出的平面板 | 通用，简单模型 |
| **conformal** (仿形) | 跟随模型表面轮廓偏移的曲面板 | 复杂曲面模型，需要均匀硅胶厚度 |
| **ribbed** (加强筋) | 平板 + 交叉加强筋结构 | 需要高刚度支撑的大型模型 |
| **lattice** (格栅) | BCC/Octet 点阵结构，拓扑优化 | 轻量化，最优刚度/重量比 |

#### 仿形板算法 (conformal) — v2 高性能重写
```
旧算法 (v1): section→extrude_polygon→per-vertex KDTree loop → 极慢, 可能挂起
新算法 (v2): 网格采样→向量化投影→三角化 → O(grid_res²), 无 Python 循环

流程:
  1. 在分型平面上建立局部坐标系 (u_ax, v_ax, up)
  2. 生成 grid_res×grid_res 的均匀网格点 (numpy meshgrid)
     grid_res = min(40, max(10, span/2))  — 自适应分辨率
  3. 向量化 cKDTree.query(all_points, workers=-1) 找最近模型表面点
  4. 有效性掩码: 距离 < max_dist 且在模型轮廓内
  5. 内壳顶点 = surface_point + surface_normal × offset (向量化)
  6. 外壳顶点 = inner + up × thickness (向量化)
  7. 网格四边形→三角形 (numpy 索引运算, 无循环)
  8. 边界检测→侧面缝合

性能: 10万面模型 ~0.5s (vs v1 可能 >60s 或挂起)
```

#### 加强筋板算法 (ribbed)
```
1. 生成基础平板 (同 flat 流程, 自动简化>20k面的模型)
2. 沿两个横向轴按 rib_spacing 间距排列肋条
3. 每条筋: Box(rib_width × 板宽 × rib_height)
4. 拼接: concatenate(base_plate, ribs...)
```

#### 格栅结构算法 (lattice) — v2 优化
```
旧算法: O(nx*ny*nz*8) 个独立 cylinder 创建 + boolean intersection → 极慢
新算法: 预计算端点 + 批量创建 + 硬上限 200 根杆件

流程:
  1. 限制网格维度: max 8×8×3 (防止爆炸)
  2. 预计算所有杆件端点 (边杆 + BCC 对角杆)
  3. 如端点数 > 200, 等间距采样到 200
  4. 批量创建低面数圆柱 (4 sections, 非默认 32)
  5. concatenate 一次性合并 (无 boolean intersection)

性能: ~1-3s (vs v1 可能 >120s)
```

#### 性能关键优化点
```
1. 位置分析: 快速面积估算 (投影法, 非 section boolean)
2. 截面操作: 自动简化 >20k 面模型; 简化 >200 顶点的多边形
3. 锚固特征: 上限 8 个 (防止 N 次 boolean 叠加)
4. 装配验证: AABB 包围盒检测 (非 boolean intersection)
5. 仿形/格栅/加强筋板: 跳过锚固 boolean (结构本身已有互锁效果)
6. API: asyncio.to_thread 避免阻塞事件循环
7. trimesh 4.x 兼容: _clean_mesh() 使用 nondegenerate_faces()+update_faces() 替代已废弃的 remove_degenerate_faces()
```

### 7.2 插板位置自动分析

```python
def analyze_insert_positions(model_mesh, mold_shells, config):
    """
    自动确定插板位置和形状
    
    策略:
    1. 识别模型中的大平面区域 → 候选插板平面
    2. 识别模具壳体间的分型面 → 沿分型面放置插板
    3. 识别硅胶厚度大的区域 → 需要支撑的区域
    4. 确保插板不干涉型腔（留有硅胶包裹间距）
    """
    candidates = []
    
    # 策略1: 大平面区域检测
    large_planes = detect_large_planar_regions(model_mesh, min_area=100)  # mm²
    for plane in large_planes:
        insert = generate_plate_along_plane(
            plane, model_mesh, mold_shells,
            offset=config.silicone_min_thickness  # 硅胶最小包裹厚度
        )
        candidates.append(insert)
    
    # 策略2: 分型面附近
    for parting_surface in mold_shells.parting_surfaces:
        insert = generate_plate_along_parting(
            parting_surface, model_mesh,
            offset=config.silicone_min_thickness
        )
        candidates.append(insert)
    
    # 策略3: 厚壁区域支撑
    thickness_field = compute_wall_thickness(model_mesh, mold_shells)
    thick_regions = thickness_field > config.max_unsupported_thickness
    for region in cluster_regions(thick_regions):
        insert = generate_support_plate(region, model_mesh, mold_shells)
        candidates.append(insert)
    
    return filter_and_merge(candidates)
```

### 7.3 锚固结构生成

```python
class AnchorGenerator:
    """在插板表面生成锚固结构"""
    
    def generate_through_holes(self, plate_mesh, config):
        """
        网孔 — 硅胶穿过圆孔实现双面互锁
        
        参数:
          hole_diameter: 2-5mm
          hole_spacing: 5-10mm
          pattern: "grid" | "hexagonal" | "random"
        """
        hole_centers = self._distribute_holes(
            plate_mesh, config.hole_spacing, config.pattern
        )
        for center in hole_centers:
            cylinder = create_cylinder(
                center=center,
                radius=config.hole_diameter / 2,
                height=plate_mesh.thickness * 1.5  # 穿透
            )
            plate_mesh = boolean_difference(plate_mesh, cylinder)
        return plate_mesh
    
    def generate_bumps(self, plate_mesh, config):
        """
        凸起 — 插板表面的半球形凸点
        
        参数:
          bump_height: 1-2mm
          bump_diameter: 2-3mm
          bump_spacing: 4-8mm
        """
        bump_centers = self._distribute_bumps(plate_mesh, config.bump_spacing)
        for center in bump_centers:
            bump = create_hemisphere(center, config.bump_diameter / 2, config.bump_height)
            plate_mesh = boolean_union(plate_mesh, bump)
        return plate_mesh
    
    def generate_grooves(self, plate_mesh, config):
        """
        沟槽 — 线性凹槽
        
        参数:
          groove_width: 1-2mm
          groove_depth: 1-2mm
          groove_spacing: 5-10mm
          groove_direction: "parallel" | "cross" | "radial"
        """
        groove_paths = self._generate_groove_paths(
            plate_mesh, config.groove_spacing, config.groove_direction
        )
        for path in groove_paths:
            groove = sweep_rectangle_along_path(
                path, config.groove_width, config.groove_depth
            )
            plate_mesh = boolean_difference(plate_mesh, groove)
        return plate_mesh
    
    def generate_dovetail(self, plate_mesh, config):
        """燕尾槽 — 高强度机械锁定"""
        # 截面为梯形的沟槽，底部宽于顶部
        ...
    
    def generate_knurl(self, plate_mesh, config):
        """菱形纹 — 全面粗糙化"""
        # 交叉沟槽形成菱形凸起
        ...
```

### 7.4 插板与模具装配验证

```python
def validate_insert_assembly(insert, mold_shells, model_mesh, config):
    """
    验证插板设计的可行性
    
    检查项:
    1. 插板不与型腔（原始模型）相交
    2. 插板与模具壳体不干涉
    3. 硅胶包裹厚度 ≥ 最小值（默认 2mm）
    4. 插板可被安装（存在无碰撞的安装路径）
    5. 插板 FDM 可打印（壁厚、悬垂角检查）
    6. 锚固结构密度足够（结合面积比 > 阈值）
    """
    issues = []
    
    # 干涉检查
    if intersects(insert, model_mesh):
        issues.append(InsertIssue("INTERSECTION_WITH_MODEL"))
    
    for shell in mold_shells:
        if intersects(insert, shell.mesh):
            issues.append(InsertIssue("INTERSECTION_WITH_SHELL"))
    
    # 硅胶厚度检查
    min_gap = compute_min_distance(insert, model_mesh)
    if min_gap < config.silicone_min_thickness:
        issues.append(InsertIssue("SILICONE_TOO_THIN", min_gap))
    
    # 安装路径检查
    if not has_insertion_path(insert, mold_shells):
        issues.append(InsertIssue("NO_INSERTION_PATH"))
    
    return ValidationResult(is_valid=len(issues) == 0, issues=issues)
```

### 7.5 插板可编辑参数

| 参数分类 | 参数 | 范围 | 默认 |
|---------|------|------|------|
| 几何 | 板厚 | 1-5mm | 2mm |
| 几何 | 外边距（距模具壳体） | 0.5-3mm | 1mm |
| 几何 | 内边距（距原始模型） | 1-5mm | 2mm |
| 锚固 | 结构类型 | 网孔/凸起/沟槽/燕尾/菱形纹 | 网孔 |
| 锚固 | 孔径 (网孔) | 2-5mm | 3mm |
| 锚固 | 孔间距 (网孔) | 5-10mm | 7mm |
| 锚固 | 排列方式 | 网格/六角/随机 | 六角 |
| 锚固 | 凸起高度 | 0.5-3mm | 1.5mm |
| 锚固 | 沟槽深度 | 0.5-3mm | 1mm |
| FDM | 最小壁厚 | ≥ 0.8mm | 1.2mm |
| FDM | 打印方向 | 自动/手动 | 自动 |

## 8. 浇注系统设计算法 (v3 实现)

### 8.1 浇口位置优化 — 多准则评分

浇口（Pour Gate）放置使用四指标加权评分，已在 `mold_builder.py` 中实现：

```
Score(v) = 0.40 · Height(v) + 0.25 · Centrality(v) + 0.20 · Access(v) + 0.15 · Thickness(v)
```

| 指标 | 计算方法 | 权重 | 说明 |
|------|---------|------|------|
| Height | 顶点高度归一化，仅保留 top 20% | 0.40 | 重力灌注需从最高点 |
| Centrality | 投影到分型面上距质心距离的反函数 | 0.25 | 保证均匀充填 |
| Accessibility | 顶点法线与方向的点积 (朝上面优先) | 0.20 | 便于浇筑操作 |
| Thickness | 基于 kNN 邻域半径的局部厚度估计 | 0.15 | 厚区流动性好 |

**参考文献**:
- Zhai et al. (2005): Gate location optimization using flow simulation
- Lee & Kim (1996): Optimal gate via mold fill balance

**实际几何体**: 自动生成漏斗形网格 (圆柱 + 圆锥) 用于 3D 可视化

### 8.2 排气口位置优化 — 流前BFS仿真 + 气穴检测

排气口（Vent Hole）使用重力充填BFS模拟确定最优位置：

```
算法流程:
1. 构建面邻接图 G = (F, E_adj)
2. 从浇筑口最近面出发，执行加权 Dijkstra:
   - 向上流动成本: cost = 1.0 + Δh × 3.0 (模拟重力阻力)
   - 向下流动成本: cost = max(0.3, 1.0 + Δh × 0.3)
3. fill_time[f] = 到面 f 的最短加权路径 → 越大越晚充填
4. 气穴检测: 面高度 > 所有邻面高度 → 局部极值 = 潜在气穴
5. 综合评分:
   VentScore(f) = 0.40 · fill_time_norm + 0.35 · height_norm + 0.25 · trap_norm
6. 最远点采样 (Farthest Point Sampling):
   - 选择得分最高的面
   - 排除最小间距内的面 (15% × 模型最大尺寸)
   - 重复直到 n_vent_holes 个
```

**参考文献**:
- Zheng et al. (2007): CAE-based optimization of vent locations
- Kwon & Park (2014): Air trap prediction in casting

**实际几何体**: 每个排气口自动生成圆柱管网格

### 8.3 复合结构浇注系统调整

当存在内嵌插板时：
```
1. 浇口需避开插板区域
2. 流道需绕过插板
3. 排气孔考虑插板周围的空气滞留
4. 插板的网孔可作为辅助流道（硅胶通过网孔流动）
5. 灌注量需考虑插板占据的体积
```

### 8.4 对齐销/孔 — 实际几何体

每个对齐销和配合孔均生成实际圆柱网格 (`trimesh.creation.cylinder`)：
- 销: 直径 4mm, 高度 8mm, 均匀分布在分型面外围
- 孔: 直径 4.2mm (+0.2mm 公差), 高度 9mm

## 9. 灌注流动仿真算法（v5: 多场分析 + 表面映射 + 可视化）

### 9.1 Level 1 — 启发式分析（毫秒级，CPU）

面级启发式分析，无需体素化：
- 距离场：计算各面片到浇口的欧式距离
- 薄壁检测：基于面积分布 P10 识别薄壁面片
- 短射风险：距离 > 85% 最大距离的面片
- 流动不平衡：面积加权距离标准差
- 输出：充填率估计、缺陷列表、简要分析报告

### 9.2 Level 2 — 简化达西流（秒级，多场计算）

v4 版本在原有达西流基础上新增了多个物理场的计算：

**求解流程：**
1. **体素化**：trimesh.voxelized → 布尔型腔掩码
2. **壁厚场**：scipy.ndimage.distance_transform_edt × pitch
3. **渗透率**：K = h²/12（平行板模型）
4. **压力场求解**：向量化稀疏矩阵组装 + scipy.sparse.linalg.spsolve
5. **速度场**：|∇P| × 渗透率系数
6. **剪切率场（v4 新增）**：γ̇ ≈ 6V/h（狭缝流近似）
7. **Dijkstra 充填前沿**：基于速度场的最短路径充填时间
8. **温度场（v4 新增）**：T = T_mold + (T_inlet − T_mold) × exp(−t/τ)，τ = h²/(4α)，含放热固化效应
9. **固化进度场（v4 新增）**：α(t) = 1 − exp(−k·t)，Arrhenius 温度修正
10. **缺陷检测**：短射、气穴（连通分量分析）、熔接线（梯度突变）、滞流区

### 9.3 多物理场详细说明

**剪切率估算（Slit Flow Approximation）**
```
γ̇ = 6V / h
```
V 为局部流速，h 为局部壁厚。高剪切率可能导致材料降解或局部过热。

**温度场估算（热扩散 + 放热固化）**
```
T(t) = T_mold + (T_inlet − T_mold) · exp(−t/τ) + ΔT_exo · f(t)
τ = h² / (4α),  α ≈ 0.1 mm²/s
ΔT_exo = 10°C (放热峰), f(t) = (t/t_peak) · exp(1 − t/t_peak)
```

**固化进度（简化 Kamal-Sourour 模型）**
```
α(t) = 1 − exp(−k(T) · t)
k(T) = k_ref · exp(E_a/R · (1/T_ref − 1/T))
E_a/R ≈ 5000 K
```

### 9.4 综合分析报告（v4 新增）

仿真完成后自动生成 `AnalysisReport`，包含以下指标：

| 类别 | 指标 | 说明 |
|------|------|------|
| 充填质量 | fill_quality_score | 0.7×充填率 + 0.3×(1−缺陷惩罚) |
| 均匀性 | fill_uniformity_index | 1 − CV(充填时间) |
| 均匀性 | pressure_uniformity_index | 1 − CV(压力) |
| 均匀性 | velocity_uniformity_index | 1 − CV(速度) |
| 平衡性 | fill_balance_score | 八分体平均充填时间方差倒数 |
| 剪切 | max/avg_shear_rate | 最大/平均剪切率 |
| 温度 | temperature_range / avg | 温度范围与平均值 |
| 固化 | cure_progress_range / avg | 固化进度范围与平均值 |
| 壁厚 | min/max/avg_thickness | 壁厚统计 |
| 壁厚 | thin/thick_wall_fraction | 薄壁/厚壁比例 |
| 流动 | flow_length_ratio | 最大流长 / 特征长度 |
| 效率 | gate_efficiency | 充填率 / 最大压力 |
| 缺陷 | n_stagnation_zones | 连通分量标记的滞流区数 |
| 缺陷 | n_high_shear_zones | 高剪切区域数 |
| 建议 | recommendations | 基于指标的中文优化建议列表 |

### 9.5 3D 可视化系统（v4 新增）

**后端 API：**
- `GET /simulation/visualization/{sim_id}`：提取体素点云，包含所有场的归一化值
- `GET /simulation/analysis/{sim_id}`：返回完整分析报告
- `GET /simulation/cross-section/{sim_id}?axis=z&position=0.5&field=fill_time`：2D 截面热力图

**前端 WebGL 渲染：**
- 自定义 GLSL ShaderMaterial 实现多场热力图切换
- 蓝→青→绿→黄→红 五段色带映射
- 基于 fill_time 的充填动画（Dijkstra 时间阈值控制可见性）
- 动画播放器：播放/暂停/进度条/速率/循环
- 缺陷标记球体（颜色按类型区分，大小按严重度缩放）
- Canvas 2D 截面热力图渲染

**支持的可视化场：**
| 场 | 说明 | 色带含义 |
|-----|------|---------|
| fill_time | 充填时间 | 蓝=早期，红=晚期 |
| pressure | 压力分布 | 蓝=低压，红=高压 |
| velocity | 流速分布 | 蓝=低速，红=高速 |
| shear_rate | 剪切率 | 蓝=低剪切，红=高剪切 |
| temperature | 温度分布 | 蓝=低温，红=高温 |
| cure_progress | 固化进度 | 蓝=未固化，红=已固化 |
| thickness | 壁厚分布 | 蓝=薄壁，红=厚壁 |

### 9.6 性能目标

| 级别 | 网格规模 | CPU 时间 | GPU 时间 (RTX 4060 Ti) |
|------|---------|---------|----------------------|
| L1 启发式 | 10K 面片 | <2s | — |
| L2 达西流 | 48³ 体素 | ~5s | <2s |
| L2 达西流 | 64³ 体素 | ~15s | <5s |
| L2 达西流 | 128³ 体素 | ~4min | <30s |

### 9.7 参考文献

- Darcy flow: H. Hele-Shaw, "Investigation of the Nature of Surface Resistance", Trans. IME, 1898
- Slit flow shear rate: Bird, Stewart & Lightfoot, "Transport Phenomena", 2nd Ed.
- Kamal-Sourour cure kinetics: Kamal & Sourour, "Kinetics and thermal characterization of thermoset cure", 1973
- Dijkstra fill front: Dijkstra, "A note on two problems in connexion with graphs", 1959

## 10. 自动优化算法

### 10.1 优化循环

```
初始参数 θ₀ → 生成模具 → 仿真 → 缺陷检测 → 参数调整 → 重复
收敛条件: 缺陷为空 OR 迭代次数 > max_iter OR 改善 < 阈值
```

### 10.2 缺陷-调整规则映射

| 缺陷 | 调整动作 |
|------|---------|
| 短射 | 增大浇口 / 添加辅助浇口 / 增大流道 |
| 气泡 | 在气泡位置附近添加排气孔 |
| 充填不平衡 | 移动浇口向慢充填区域 |
| 熔接线 | 调整浇口布局改变流向 |
| 插板周围滞留 | 增加插板网孔密度 / 调整排气 |

### 10.3 优化方法

- **首选**：基于规则的启发式（快速收敛）
- **可选**：贝叶斯优化（连续参数）/ 遗传算法（多目标）

## 11. 有限元分析 (FEA) 算法 (v5 新增)

### 11.1 简化弹簧质量模型

使用三角网格边作为弹簧系统，通过稀疏矩阵求解器计算位移场:

```
输入: 三角网格 M, 材料参数 (E, ν, σ_y, ρ)
  │
  ├─ 1. 构建弹簧刚度矩阵 K (n_edges × 3 DOF)
  │     k_ij = E / (1 - ν²) / length_ij
  │     K[3i+d, 3i+d] += k_d  (对角线)
  │     K[3i+d, 3j+d] -= k_d  (耦合)
  │
  ├─ 2. 施加载荷向量 F
  │     压力: F_v += normal_v × pressure × area_v / 3
  │     重力: F_v += mass_v × g × g_direction
  │
  ├─ 3. 施加边界条件 (罚函数法)
  │     固定底部 10% 顶点: K[dof, dof] += penalty (10^6 × max_diag)
  │
  ├─ 4. 求解: u = K^{-1} F  (scipy.sparse.linalg.spsolve)
  │
  ├─ 5. 后处理
  │     位移: d_v = ||u[3v:3v+3]||
  │     应变: ε_ij = (||deformed_edge|| - ||original_edge||) / ||original_edge||
  │     应力: σ_ij = E × ε_ij
  │     Von Mises: σ_vm = sqrt(Σσ²/n_edges)
  │     安全系数: SF = σ_yield / σ_vm
  │
  └─ 输出: FEAResult (位移场, Von Mises 应力, 安全系数, 应变能)
```

### 11.2 材料预设

| 材料 | E (MPa) | ν | ρ (kg/mm³) | σ_y (MPa) |
|------|---------|------|------------|-----------|
| PLA | 2500 | 0.36 | 1.24e-6 | 40 |
| ABS | 2100 | 0.39 | 1.04e-6 | 35 |
| PETG | 2020 | 0.40 | 1.27e-6 | 50 |
| Nylon | 1700 | 0.42 | 1.14e-6 | 70 |
| Silicone | 5 | 0.48 | 1.1e-6 | 5 |
| Resin | 2800 | 0.35 | 1.18e-6 | 55 |
| Aluminum | 69000 | 0.33 | 2.7e-6 | 240 |
| Steel | 200000 | 0.30 | 7.85e-6 | 250 |

### 11.3 表面映射可视化 (v5 新增)

将体素场仿真数据投影到模型三角面网格表面:

```
输入: 体素场 V (fill_time/pressure/velocity/...), 模型网格 M
  │
  ├─ 1. 将每个顶点坐标映射到体素空间: voxel_idx = (vertex - origin) / pitch
  ├─ 2. 查找最近有效体素 (3邻域搜索回退)
  ├─ 3. 读取体素值, 归一化到 [0, 1]
  └─ 4. 前端: 逐顶点着色 (vertex colors) 渲染热力图叠加
```

## 12. nTopology 级几何分析算法 (v6 新增)

### 12.1 壁厚分析 — 多射线逐顶点估计

```
算法:
  对每个顶点 v, 沿 n_rays 条方向发射射线:
    ray_0 = -normal_v               (主方向)
    ray_i = -normal_v + jitter_i    (抖动方向, i=1..n_rays-1)
  
  对每条射线, 从 v + dir × ε 出发做射线-网格求交:
    hit_dist = ||intersection - origin||
    thickness[v] = min(thickness[v], hit_dist)
  
  后处理:
    thickness = clip(thickness, 0, max_distance)
    thin_count = count(thickness < thin_threshold)
    histogram = np.histogram(finite_thickness, bins=20)

复杂度: O(N × n_rays × R), R = 射线求交 (BVH 加速)
参考: nTopology Wall Thickness Check, Materialise Magics
```

### 12.2 离散曲率计算

```
Gaussian 曲率 (角亏法 / Angle Defect):
  K(v) = (2π - Σ θ_ij) / A(v)
  
  其中 θ_ij 为顶点 v 在三角形 (v, v_i, v_j) 中的内角
  A(v) = Σ area(face) / 3  (Voronoi 面积)
  
  计算步骤:
    1. 对每个面 (i, j, k):
       计算三个内角 α_i, α_j, α_k
    2. 角亏 defect[v] = 2π - Σ(v 所在面的内角)
    3. 面积和 area_sum[v] = Σ(v 所在面面积) / 3
    4. K[v] = defect[v] / area_sum[v]

Mean 曲率:
  使用 trimesh.curvature.discrete_mean_curvature_measure
  回退: H(v) = K(v) × 0.5

参考: Meyer et al. "Discrete Differential-Geometry Operators for
      Triangulated 2-Manifolds" (2003)
```

### 12.3 拔模角分析

```
对每个面 f, 拔模角定义为:
  draft_angle = 90° - arccos(|n_f · pull_direction|)
  等价于: draft_angle = arcsin(|n_f · pull_direction|)

倒扣检测:
  undercut = (n_f · pull_direction < 0)
  
临界面:
  critical = (draft_angle < critical_threshold)  — 默认 3°

输出:
  per_face_angle: (M,) 逐面拔模角度
  undercut_fraction: 倒扣面积 / 总面积
  critical_fraction: 临界面积 / 总面积
  histogram: 角度分布直方图

参考: nTopology Draft Analysis, Moldex3D Draft Angle Check
```

### 12.4 对称性分析

```
算法:
  1. 中心化: verts_c = vertices - centroid
  2. 构建 cKDTree(verts_c)
  3. 对每个轴 (X, Y, Z):
     a. 镜像: reflected = verts_c; reflected[:, axis] *= -1
     b. 最近邻: dists, _ = tree.query(reflected)
     c. 归一化: norm_dist = dists / extent(verts_c[:, axis])
     d. 评分: score = max(0, 1 - 4 × mean(norm_dist))
        score=1 表示完美对称, score=0 表示完全不对称
  4. 最佳平面 = argmax(scores)
  5. PCA: SVD(verts_c) → 主轴方向

参考: nTopology Symmetry Detection, CGAL Symmetry Tools
```

### 12.5 悬垂分析 (3D 打印)

```
对每个面 f:
  cos_angle = n_f · build_direction
  face_angle = arccos(cos_angle)          — 面法线与打印方向的夹角
  overhang = (face_angle > 90° + critical_angle)  — 默认 critical=45°

等价判断: n_f · build_direction < -cos(critical_angle)

输出:
  per_face_overhang: (M,) 布尔掩码
  overhang_fraction: 悬垂面数 / 总面数
  overhang_area_mm2: 悬垂面积
  total_area_mm2: 总面积

参考: nTopology Overhang Detection, Autodesk Netfabb
```

### 12.6 高级平滑算法

```
Laplacian 平滑:
  v'_i = v_i + λ × L(v_i)
  L(v_i) = (1/|N(i)|) × Σ_{j∈N(i)} (v_j - v_i)
  每次迭代沿 Laplacian 方向移动。缺点: 体积收缩。

Taubin 平滑 (λ|μ):
  交替两步:
    v'  = v  + λ × L(v)     (收缩步, λ > 0)
    v'' = v' + μ × L(v')    (膨胀步, μ < 0, |μ| > λ)
  通常 λ=0.5, μ=-0.53。收缩与膨胀近似抵消, 保持体积。

HC 平滑 (Humphrey's Classes):
  1. p = original_vertices
  2. 对每次迭代:
     b = v + λ × L(v)          — Laplacian 步
     d = b - (α × p + (1-α) × v)  — 偏差
     v = b - (β × d + (1-β) × L(d))  — 修正
  体积保持优于 Taubin, 适合精密模型。

参考: Taubin (1995), Vollmer et al. (1999)
```

### 12.7 等尺重网格化

```
目标: 将网格边长统一到 target_edge_length

算法 (subdivide-decimate 循环):
  1. 计算 mean_edge = 平均边长
  2. 如未指定 target, 使用 target = mean_edge
  3. 细分: trimesh.remesh.subdivide_to_size(target × 0.8)
  4. 简化: open3d.simplify_quadric_decimation(target_face_count)
     target_face_count = surface_area / (√3/4 × target²)

参考: nTopology Remesh, Mesquite Mesh Quality Improvement
```

### 12.8 表面增厚

```
将开放曲面网格转为封闭实体:

算法:
  1. 计算逐顶点法线 normals (N, 3)
  2. 外壳: outer = vertices + normals × (thickness/2)  [direction=both]
  3. 内壳: inner = vertices - normals × (thickness/2)
  4. 反转内壳面片绕序: inner_faces = inner_faces[:, ::-1]
  5. 缝合侧面: 检测边界边, 创建四边形连接内外壳边界
  6. 合并: concatenate(outer_mesh, inner_mesh, side_mesh)

direction 变体:
  outward: outer = verts + normals × thickness; inner = verts
  inward:  outer = verts; inner = verts - normals × thickness
  both:    ±thickness/2

参考: nTopology Thicken, Rhino OffsetMesh
```

### 12.9 TPMS 晶格生成 (v2 — 隐式场精确实现)

```
三周期极小曲面 (Triply Periodic Minimal Surface) 是零平均曲率的
三维周期曲面，用于生成高性能晶格/网孔结构。

── 隐式场数学定义 ────────────────────────────────────

所有 TPMS 定义为 f(x,y,z) = 0 的零等值面:

  Gyroid:     sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x)
  Schwarz-P:  cos(x) + cos(y) + cos(z)
  Schwarz-D:  sin(x)sin(y)sin(z) + sin(x)cos(y)cos(z)
              + cos(x)sin(y)cos(z) + cos(x)cos(y)sin(z)
  Neovius:    3(cos(x)+cos(y)+cos(z)) + 4·cos(x)cos(y)cos(z)
  Lidinoid:   sin(2x)cos(y)sin(z) + sin(2y)cos(z)sin(x)
              + sin(2z)cos(x)sin(y) - cos(2x)cos(2y)
              - cos(2y)cos(2z) - cos(2z)cos(2x) + 0.3
  IWP:        2(cos(x)cos(y) + cos(y)cos(z) + cos(z)cos(x))
              - (cos(2x) + cos(2y) + cos(2z))
  FRD:        4·cos(x)cos(y)cos(z)
              - (cos(2x)cos(2y) + cos(2y)cos(2z) + cos(2z)cos(2x))

参考: nTopology TPMS Equations, Schoen (1970)

── 2D 切片网孔布局管线 ─────────────────────────────────

对一块位于 z=z₀ 平面的支撑板:

  1. 构造 (u,v) 高分辨率网格 (60-400 点/轴, 自适应):
     ω = 2π / cell_size
     grid: [−half_span + margin, half_span − margin]²

  2. 求值: field[i,j] = f(ω·u_j, ω·v_i, ω·z₀)
     零等值线 f=0 即为 TPMS "壁"
     |f| 大的区域远离壁 → 适合放孔

  3. 局部极值检测:
     abs_field = |field|
     local_max = scipy.ndimage.maximum_filter(abs_field, footprint)
     peaks = (abs_field == local_max) & (abs_field > 0.15 × max)
     footprint 尺寸 = min_spacing / du (保证间距)

  4. 贪心选择 (距离约束):
     按 |f| 降序排列极值点
     逐个加入，跳过距已选点 < min_spacing 的点
     上限 max_holes=300

  5. 自适应半径:
     ratio = |f(peak)| / max(|f|)
     r = base_r × (0.5 + 0.5 × ratio)
     → 远离壁的区域孔更大，靠近壁的区域孔更小

复杂度: O(resolution² + N log N) (N = 极值点数)

── 场驱动半径调制 ─────────────────────────────────────

每个孔的半径经空间场连续调制 (非二元删除):

  r_final = r × (min_factor + (max_factor − min_factor) × t)
  t = field_value(u, v, half_span, field_type)

  field_type:
    "edge"    → t = 1 − edge_dist/hs      (边缘大、中心小)
    "center"  → t = edge_dist/hs           (中心大、边缘小)
    "radial"  → t = √(u²+v²) / (hs√2)     (径向渐增)
    "stress"  → t = edge_dist/hs (代理)    (应力反比)
    "uniform" → t = 0                       (全部最小)

  若 r_final < 0.3 × r_original → 移除该孔

── 几何图案 ─────────────────────────────────────────

  Hex (蜂窝):  经典六角密堆积, 行交错 spacing/2
  Grid (网格): 正方形等距阵列
  Diamond (菱形): 45° 旋转正方形阵列
  Voronoi:     随机撒种 + 5 轮 Lloyd 松弛 → 近均匀分布

── 网孔雕刻质量 ─────────────────────────────────────

  Phase 0: 预细分 — 2 轮选择性细分 [0.7r, 1.3r] 环形带
  Phase 1: 面片删除 — 质心距孔心 < r 的面被移除
  Phase 2: 边界拟合 — 边界顶点投射到理想圆周
  Phase 3: 平滑 — 3 轮 Laplacian 平滑边界 1-ring

参考: nTopology Lattice Library, Al-Ketan & Abu Al-Rub (2019)
      "TPMS architectured materials: A review"
```

## 13. AI 辅助模型生成流程（新增）

### 11.1 文字→器官模型 全流程

```
用户输入: "生成一个带有门静脉系统的成人肝脏模型"
  │
  ▼
Step 1: LLM 需求解析 (DeepSeek)
  ├─ 器官类型: 肝脏
  ├─ 特征: 含门静脉系统
  ├─ 规格: 成人、1:1 比例
  ├─ 估计尺寸: ~280×160×100mm
  └─ 生成优化提示词: "anatomical adult human liver with portal vein system,
     medical grade, detailed surface texture, realistic proportions"
  │
  ▼
Step 2: 参考图像生成 (通义万相)
  ├─ 生成 3-4 张不同角度的器官参考图
  ├─ 用户选择最满意的参考图
  └─ （可选）用户上传自有参考图
  │
  ▼
Step 3: 3D 模型生成 (Tripo3D)
  ├─ Image→3D: 将参考图转为 3D 模型
  ├─ 下载 GLB/OBJ 格式
  └─ 加载到 MoldGen 场景
  │
  ▼
Step 4: AI 模型审查 (Qwen-VL)
  ├─ 截取多角度截图
  ├─ Qwen-VL 分析: "这是一个解剖学上合理的肝脏模型吗？"
  ├─ 识别问题: 比例失调/结构缺失/拓扑异常
  └─ 生成修改建议
  │
  ▼
Step 5: 用户编辑/确认
  ├─ mesh_editor 修复/调整
  └─ 确认 → 进入模具生成流程
```

### 11.2 AI 辅助支撑板决策算法

```python
async def ai_assisted_insert_planning(model_mesh, mold_result, ai_service):
    """
    AI 辅助支撑板规划：结合几何分析 + LLM 推理
    """
    # Step 1: 几何分析（自动）
    thickness_map = compute_wall_thickness(model_mesh, mold_result)
    cross_sections = compute_cross_sections(model_mesh, n_planes=10)
    large_planes = detect_large_planar_regions(model_mesh)
    volume = model_mesh.volume
    
    # Step 2: 截取模型多角度图像
    screenshots = render_multi_view(model_mesh, views=["front","side","top","section"])
    
    # Step 3: Qwen-VL 分析解剖结构
    anatomy_analysis = await ai_service.analyze_image(
        screenshots,
        "识别这个3D模型的解剖结构，标注主要结构区域和内部空腔"
    )
    
    # Step 4: DeepSeek 综合推理 (Function Calling)
    planning_result = await ai_service.chat(
        messages=[{
            "role": "system",
            "content": INSERT_ADVISOR_PROMPT
        }, {
            "role": "user", 
            "content": f"""
            模型分析结果:
            - 体积: {volume:.0f} mm³
            - 壁厚范围: {thickness_map.min():.1f}-{thickness_map.max():.1f} mm
            - 大平面区域: {len(large_planes)} 个
            - 解剖分析: {anatomy_analysis}
            
            请规划支撑板方案。
            """
        }],
        tools=[
            {"name": "add_insert_plate", "params": "plane_origin, plane_normal, anchor_type, reason"},
            {"name": "set_insert_thickness", "params": "thickness_mm"},
            {"name": "set_anchor_config", "params": "type, hole_diameter, spacing"},
        ]
    )
    
    # Step 5: 提取工具调用 → 生成支撑板方案
    insert_plan = extract_insert_plan(planning_result)
    
    return insert_plan  # 返回给用户确认
```

### 11.3 医学模型特殊处理

```
医学器官模型的预处理额外步骤:

1. 尺寸校验: 与标准解剖尺寸数据库对比
   - 成人肝脏: ~280×160×100mm
   - 成人肾脏: ~120×60×30mm
   - 成人心脏: ~130×90×65mm
   如偏差>20%，向用户提示

2. 表面质量评估:
   - AI生成的模型常有表面噪点
   - 自动平滑 (Laplacian/Taubin)
   - 保留解剖细节的同时去除伪影

3. 内部结构完整性:
   - 检测并填充内部孔洞
   - 确保模型为实体（非壳体）
   - 对于含管道的模型，验证管道连通性

4. 材料映射建议:
   - 实质性组织 → 硅胶 Shore A 20-30
   - 血管壁 → 硅胶 Shore A 40-50
   - 骨骼/软骨 → 支撑板或硬质树脂
```

## 12. Agent 路由与自动执行算法（新增）

### 12.1 MasterAgent 意图路由算法

```python
async def route_user_intent(user_input: str, context: ExecutionContext,
                            ai_service: AIServiceManager) -> RoutingDecision:
    """
    MasterAgent 意图路由：将用户自然语言转换为执行计划
    
    路由策略:
    1. 关键词快速匹配 (延迟 <10ms)
    2. LLM 意图分类 (延迟 ~500ms, 仅关键词匹配失败时)
    """
    # 快速路由: 关键词匹配
    fast_route = keyword_route(user_input)
    if fast_route:
        return fast_route
    
    # LLM 路由: DeepSeek Function Calling
    routing_result = await ai_service.chat(
        messages=[
            {"role": "system", "content": MASTER_ROUTING_PROMPT},
            {"role": "user", "content": user_input}
        ],
        tools=[
            {"name": "dispatch_single", "params": "agent, task, auto_execute"},
            {"name": "create_plan", "params": "steps[]"},
            {"name": "ask_user", "params": "question, options"},
        ]
    )
    
    return parse_routing_result(routing_result)

# 关键词快速路由表
KEYWORD_ROUTES = {
    # 模型处理
    ("导入", "加载", "打开文件", "上传"): ("model", "load_model"),
    ("修复", "修复网格"): ("model", "repair_mesh"),
    ("细化", "细分", "subdivision"): ("model", "subdivide_mesh"),
    ("简化", "减面", "decimation"): ("model", "simplify_mesh"),
    ("平移", "旋转", "缩放", "镜像"): ("model", "transform_mesh"),
    ("布尔", "合并", "切割", "相减"): ("model", "boolean_operation"),
    ("导出", "保存", "输出"): ("model", "export_model"),
    
    # 模具设计
    ("方向", "脱模方向", "方向分析"): ("mold", "analyze_orientation"),
    ("分型", "分型面", "分型线"): ("mold", "generate_parting"),
    ("模具", "壳体", "生成模具"): ("mold", "full_pipeline"),
    ("浇口", "流道", "浇注系统"): ("mold", "design_gating"),
    
    # 支撑板
    ("支撑板", "插板", "支撑"): ("insert", "auto_or_dialog"),
    
    # 仿真
    ("仿真", "灌注", "模拟", "流动"): ("simopt", "run_simulation"),
    ("优化", "改进", "迭代"): ("simopt", "optimize"),
    
    # 创意生成
    ("生成图", "画", "参考图", "图像"): ("creative", "generate_images"),
    ("生成模型", "AI生成", "AI建模"): ("creative", "generate_3d"),
    
    # 完整流水线触发词
    ("做一个", "帮我做", "一键", "全自动", "从零开始"):
        ("master", "full_pipeline"),
}

def keyword_route(user_input: str) -> Optional[RoutingDecision]:
    """关键词快速匹配路由"""
    for keywords, (agent, task) in KEYWORD_ROUTES.items():
        if any(kw in user_input for kw in keywords):
            return RoutingDecision(
                agent=agent, task=task,
                auto_execute=agent != "master",
                confidence=0.8
            )
    return None
```

### 12.2 执行计划生成算法

```python
async def generate_execution_plan(task_description: str,
                                  context: ExecutionContext,
                                  mode: ExecutionMode,
                                  ai_service: AIServiceManager
                                 ) -> ExecutionPlan:
    """
    MasterAgent 将复杂任务分解为有序步骤
    
    分解策略:
    - 分析任务涉及的功能模块
    - 确定步骤间依赖关系（DAG）
    - 根据 ExecutionMode 设置确认点
    - 估算总耗时
    """
    # 预定义的流水线模板
    PIPELINE_TEMPLATES = {
        "full_from_text": [
            # 从文字描述到完整模具
            {"agent": "creative", "task": "generate_3d_model", "deps": []},
            {"agent": "model", "task": "repair_and_prepare", "deps": [0]},
            {"agent": "mold", "task": "full_mold_pipeline", "deps": [1]},
            {"agent": "insert", "task": "design_inserts", "deps": [2]},
            {"agent": "simopt", "task": "simulate_and_optimize", "deps": [3]},
            {"agent": "model", "task": "export_all", "deps": [4]},
        ],
        "full_from_model": [
            # 从已有模型到完整模具
            {"agent": "model", "task": "check_and_repair", "deps": []},
            {"agent": "mold", "task": "full_mold_pipeline", "deps": [0]},
            {"agent": "insert", "task": "design_inserts", "deps": [1]},
            {"agent": "simopt", "task": "simulate_and_optimize", "deps": [2]},
            {"agent": "model", "task": "export_all", "deps": [3]},
        ],
        "mold_only": [
            {"agent": "mold", "task": "full_mold_pipeline", "deps": []},
            {"agent": "simopt", "task": "quick_validate", "deps": [0]},
        ],
        "optimize_existing": [
            {"agent": "simopt", "task": "simulate_and_optimize", "deps": []},
        ],
    }
    
    # 匹配模板或LLM自由生成
    template = match_template(task_description, context)
    if template:
        steps = PIPELINE_TEMPLATES[template]
    else:
        steps = await ai_generate_plan(task_description, ai_service)
    
    # 注入确认点
    for step in steps:
        step["needs_confirmation"] = should_confirm_step(
            step["agent"], step["task"], mode
        )
    
    return ExecutionPlan(steps=steps, estimated_time=estimate_time(steps))
```

### 12.3 自动执行决策树

```
用户输入
  │
  ├─ 关键词匹配成功?
  │   ├─ 是 → 单Agent任务
  │   │   ├─ 检查确认规则表
  │   │   │   ├─ 需确认 → 展示预览 → 等待确认 → 执行
  │   │   │   └─ 不需确认 → 直接执行
  │   │   └─ 执行完成 → 自动触发后续链(AUTO_CHAIN)?
  │   │       ├─ 有后续 → 执行后续操作
  │   │       └─ 无后续 → 报告结果
  │   │
  │   └─ 否 → LLM意图分析
  │       ├─ 单步任务 → dispatch_single → 同上
  │       ├─ 多步任务 → create_plan → 执行计划
  │       │   └─ 逐步执行:
  │       │       ├─ 全自动: 仅delete操作确认
  │       │       ├─ 半自动: 关键决策确认
  │       │       └─ 逐步: 每步确认
  │       └─ 需要澄清 → ask_user → 获取更多信息 → 重新路由
  │
  └─ 执行过程中的异常处理:
      ├─ 工具执行失败 → retry(max=3) → 降级方案 → 报告用户
      ├─ AI API 超时 → retry → 切换provider → 通知用户
      ├─ 验证失败 → 自动调参重试(max=3) → 展示问题 → 等待指令
      └─ GPU OOM → 降低分辨率重试 → CPU降级
```

### 12.4 多Agent协作调度算法

```python
async def orchestrate_multi_agent(plan: ExecutionPlan,
                                  engine: AgentExecutionEngine
                                 ) -> AsyncIterator[ExecutionEvent]:
    """
    多Agent协作调度
    
    执行策略:
    - 按依赖关系拓扑排序
    - 无依赖的步骤可并行（当前版本串行，预留并行接口）
    - Agent之间通过 ExecutionContext 传递数据
    - 每个Agent完成后更新上下文
    """
    completed: Set[int] = set()
    
    for step in topological_sort(plan.steps):
        # 等待依赖步骤完成
        while not all(dep in completed for dep in step.depends_on):
            await asyncio.sleep(0.1)
        
        # 切换到目标Agent
        agent = engine.agents[step.agent_name]
        yield ExecutionEvent("agent_switch", {
            "from": engine.current_agent,
            "to": step.agent_name,
            "task": step.task_description
        })
        
        # Agent执行（内部可能有多个工具调用）
        async for event in agent.execute(
            step.task_description,
            step.params,
            engine.current_context.mode,
            engine.current_context
        ):
            yield event
            
            # 处理需要确认的事件
            if event.type == "need_confirmation":
                user_response = await engine.wait_for_user_input()
                if not user_response.approved:
                    if user_response.skip:
                        break  # 跳过此步骤
                    elif user_response.modified_params:
                        step.params.update(user_response.modified_params)
                        # 用修改后的参数重新执行
        
        completed.add(step.step_id)
        yield ExecutionEvent("step_complete", {"step_id": step.step_id})
    
    yield ExecutionEvent("task_complete", {
        "summary": generate_summary(engine.current_context)
    })

def topological_sort(steps: List[PlanStep]) -> List[PlanStep]:
    """步骤拓扑排序（确保依赖顺序）"""
    in_degree = {s.step_id: len(s.depends_on) for s in steps}
    queue = [s for s in steps if in_degree[s.step_id] == 0]
    result = []
    while queue:
        step = queue.pop(0)
        result.append(step)
        for s in steps:
            if step.step_id in s.depends_on:
                in_degree[s.step_id] -= 1
                if in_degree[s.step_id] == 0:
                    queue.append(s)
    return result
```

### 12.5 Agent 内部自动执行链

```python
async def execute_auto_pipeline(agent: BaseAgent,
                                pipeline: List[dict],
                                context: ExecutionContext,
                                mode: ExecutionMode
                               ) -> AsyncIterator[ExecutionEvent]:
    """
    Agent 内部按预定义流水线自动执行多个工具
    
    每个工具执行后:
    1. 检查执行结果是否成功
    2. 失败则检查是否有重试策略
    3. 检查是否满足跳过条件 (skip_if)
    4. 检查是否触发确认条件 (confirm_if)
    5. 成功则将结果传递给下一个工具
    """
    for step in pipeline:
        tool_name = step["tool"]
        
        # 跳过条件检查
        if "skip_if" in step and evaluate_condition(step["skip_if"], context):
            yield ExecutionEvent("tool_skipped", {"tool": tool_name})
            continue
        
        # 确认条件检查
        needs_confirm = False
        if mode == ExecutionMode.STEP_BY_STEP:
            needs_confirm = True
        elif mode == ExecutionMode.SEMI_AUTO:
            needs_confirm = CONFIRMATION_RULES.get(tool_name, (False,True,True))[1]
        
        if "confirm_if" in step:
            condition_result = evaluate_condition(step["confirm_if"], context)
            needs_confirm = needs_confirm or condition_result
        
        if needs_confirm:
            yield ExecutionEvent("need_confirmation", {
                "tool": tool_name,
                "description": f"即将执行: {tool_name}"
            })
            response = await wait_for_confirmation()
            if not response.approved:
                continue
        
        # 执行工具
        yield ExecutionEvent("tool_call", {"tool": tool_name})
        result = await agent.tools.execute(tool_name, context)
        
        # 失败处理
        if not result.success:
            if step.get("retry_on_fail"):
                for attempt in range(3):
                    result = await agent.tools.execute(tool_name, context)
                    if result.success:
                        break
            if not result.success:
                yield ExecutionEvent("error", {
                    "tool": tool_name, "error": result.message
                })
                return
        
        yield ExecutionEvent("tool_result", {
            "tool": tool_name, "result": result.data
        })
        
        # 更新上下文
        update_context(context, tool_name, result)
```

### 12.6 错误恢复与降级策略

```python
ERROR_RECOVERY = {
    "ai_api_timeout": {
        "strategy": "retry_then_switch",
        "retries": 3,
        "retry_delay_ms": [1000, 2000, 4000],  # 指数退避
        "fallback_providers": {
            "deepseek": "qwen",
            "tongyi_wanxiang": "kolors",
            "tripo": None,  # 无替代，通知用户
            "qwen_vl": "deepseek_vision",
        }
    },
    "tool_execution_failed": {
        "strategy": "retry_with_adjusted_params",
        "retries": 2,
        "param_adjustments": {
            "simplify_mesh": {"ratio": "ratio * 1.2"},
            "generate_parting_surface": {"method": "next_method"},
            "build_mold_shells": {"wall_thickness": "wall_thickness + 1"},
        },
        "final_fallback": "report_to_user"
    },
    "validation_failed": {
        "strategy": "auto_fix_then_retry",
        "retries": 3,
        "auto_fix_actions": {
            "INTERSECTION_WITH_MODEL": "increase_offset",
            "SILICONE_TOO_THIN": "increase_silicone_thickness",
            "NO_INSERTION_PATH": "try_alternative_position",
            "FDM_WALL_TOO_THIN": "increase_wall_thickness",
        }
    },
    "gpu_oom": {
        "strategy": "reduce_and_retry",
        "resolution_reduction": [0.75, 0.5, 0.25],
        "final_fallback": "cpu_mode"
    }
}
```

## 13. Agent 工具函数定义（更新）

### 12.1 工具 JSON Schema

```python
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_reference_image",
            "description": "生成器官参考图像，用于后续3D模型生成",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "器官描述，中文或英文"},
                    "style": {"type": "string", "enum": ["medical_textbook", "realistic", "diagram"]},
                    "views": {"type": "integer", "description": "生成图片数量", "default": 3}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_3d_model",
            "description": "从文字描述或图像生成3D器官模型",
            "parameters": {
                "type": "object",
                "properties": {
                    "text_prompt": {"type": "string"},
                    "image_path": {"type": "string"},
                    "quality": {"type": "string", "enum": ["draft", "standard", "high"], "default": "standard"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_insert_plates",
            "description": "分析3D模型并建议支撑板位置和配置",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_id": {"type": "string"},
                    "organ_type": {"type": "string"},
                    "requirements": {"type": "string", "description": "用户的特殊要求"}
                },
                "required": ["model_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modify_insert_plate",
            "description": "修改指定支撑板的参数",
            "parameters": {
                "type": "object",
                "properties": {
                    "insert_id": {"type": "integer"},
                    "action": {"type": "string", "enum": ["move", "resize", "change_anchor", "delete"]},
                    "params": {"type": "object"}
                },
                "required": ["insert_id", "action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_mold",
            "description": "为当前模型生成完整模具",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_id": {"type": "string"},
                    "wall_thickness": {"type": "number", "default": 5.0},
                    "mold_type": {"type": "string", "enum": ["silicone", "injection"], "default": "silicone"},
                    "include_inserts": {"type": "boolean", "default": true}
                },
                "required": ["model_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_simulation",
            "description": "运行灌注流动仿真",
            "parameters": {
                "type": "object",
                "properties": {
                    "mold_id": {"type": "string"},
                    "material": {"type": "string", "default": "silicone_shore_a30"},
                    "level": {"type": "integer", "enum": [1, 2], "default": 2}
                },
                "required": ["mold_id"]
            }
        }
    }
]
```

---

## 13. nTopology 级隐式场与高级算法 (v10 新增)

### 13.1 SDF (有符号距离场) 计算

```
Mesh → SDF 转换:
  1. 计算 bounding box + padding → 均匀体素网格 (nz × ny × nx)
  2. 对每个体素中心 P:
     - closest_point(mesh, P) → 最近距离 d
     - mesh.contains(P) → 内/外判定 (winding number)
     - sdf(P) = d if outside, -d if inside
  3. 存储为 float32 体素数组 + origin + spacing

复杂度: O(N_voxels × log N_faces) (trimesh BVH 加速)
```

### 13.2 Smooth Boolean (Íñigo Quílez)

```
smooth_union(a, b, k):
    h = clamp(0.5 + 0.5(b-a)/k, 0, 1)
    return a·h + b·(1-h) - k·h·(1-h)

k 参数控制混合圆角半径 (mm)。k→0 退化为 sharp boolean。
```

### 13.3 SIMP 拓扑优化

```
  E_e = ρ_e^p · E_0  (p=3)
  min C = f^T u  subject to  Σρ_e/N ≤ V_frac
  ∂C/∂ρ_e = -p · ρ_e^(p-1) · u_e^T K_e u_e
  OC 更新 + 密度卷积滤波
```

### 13.4 3D 晶格单胞

```
BCC(8杆), FCC(15杆), Octet(BCC+FCC), Kelvin, Diamond
TPMS 体积: |f(ωx,ωy,ωz)| - t/2 ≤ 0 → Marching Cubes
Voronoi 泡沫: Lloyd 松弛 + k=2 最近邻距离差 → 壳体
```

### 13.5 干涉/间隙分析

```
双向最近点有符号距离 + 体素干涉体积估算
```

### 13.6 网格质量指标

```
aspect_ratio, min/max angle, edge_length stats
euler=V-E+F, genus=(2-euler)/2, compactness=36πV²/A³
```
