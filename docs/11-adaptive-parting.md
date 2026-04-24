# 11. 自适应分型面系统

> 版本: v4.0 — 2026-04-18
> 状态: Phase 1-2 已实现, Phase 2.5 模具分割集成完成

## 1. 问题分析

### 1.1 当前局限

当前 `PartingGenerator` 仅支持**平面分型面**，存在以下问题：

| 问题 | 影响 | 典型场景 |
|------|------|----------|
| 侧面凹陷 (undercut) 导致脱模困难 | 模型卡在模具中 | 人耳、鼻翼、手指间隙 |
| 平面分型线切过模型复杂曲面 | 分型面处产生飞边 | 人脸侧面轮廓 |
| 单方向分型无法覆盖所有面 | 部分面不可脱模 | T 形结构、倒钩 |
| 分型面不贴合模型表面 | 硅胶灌注时泄漏 | 高曲率模型边缘 |

### 1.2 目标

设计分层式自适应分型面系统，支持：

1. **曲面分型面** — 沿分型线生成贴合模型轮廓的非平面分型面
2. **Undercut 检测与处理** — 自动识别并量化侧面凹陷
3. **多片模具自动分割** — 当两片模具无法解决时，自动增加片数
4. **分型面优化** — 最小化分型线长度、平坦度、脱模力

## 2. 算法架构

### 2.1 分层处理管线

```
输入模型 + 脱模方向
    │
    ▼
┌───────────────────┐
│ L1: 分型线计算     │ ← 现有功能 (sign-change method)
│   - 法线符号变化    │
│   - 环路构建        │
│   - Laplacian 平滑 │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ L2: Undercut 分析  │ ← ✅ 已实现 (Phase 1)
│   - 射线可见性检测  │
│   - 凹陷体积量化    │
│   - 严重度分级      │
│   - 侧抽方向推荐 ✅ │ ← Phase 2
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ L3: 分型面生成     │ ← ✅ 已增强
│   - 平面 (现有)    │
│   - 高度场曲面 ✅   │ ← Phase 1 (含边界约束 + 向量化)
│   - 投影拉伸曲面 ✅ │ ← Phase 2 (含高度渐变)
│   - 样条插值曲面    │ ← 待实现
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ L3.5: 模具分割集成 │ ← ✅ Phase 2.5
│   - 自适应面分割    │
│   - cKDTree 高度查询│
│   - 布尔运算切除    │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ L4: 多片自动分割   │ ← 待实现
│   - 可见性分析      │
│   - 区域聚类        │
│   - 递归二分        │
└───────────────────┘
```

## 3. 已实现模块

### 3.1 UndercutAnalyzer (Phase 1)

**文件**: `moldgen/core/parting.py`

射线投射 undercut 检测器。

**算法**:
1. 对每个法线朝向与脱模方向相反的面 (dot < -0.01)
2. 从面质心沿 +direction 偏移 0.05mm 后发射射线
3. 收集所有命中点, 排除自身面
4. 最近命中距离 > threshold → 记为 undercut, 深度 = 该距离

**严重度分级** (v4.0 修复):
```python
if ratio < 0.02 and max_d < 3.0:    # 两个条件都满足 → 轻微
    severity = "mild"
elif ratio < 0.10 and max_d < 8.0:  # 两个条件都满足 → 中等 (修复: or→and)
    severity = "moderate"
else:                                 # 任一条件超标 → 严重
    severity = "severe"
```

> **v4.0 Bug Fix**: 旧版使用 `or` 连接两个条件, 导致 ratio=0.50 但 max_d=5.0 的模型
> 被错误分为 "moderate"。修改为 `and` 后, 只有两个指标都在范围内才判定为 moderate。

**输出 `UndercutInfo`**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `n_undercut_faces` | int | 存在 undercut 的面数 |
| `total_faces` | int | 总面数 |
| `undercut_ratio` | float | undercut 面占比 |
| `max_depth` | float | 最大深度 (mm) |
| `mean_depth` | float | 平均深度 |
| `total_volume` | float | 估算体积 (mm³) |
| `severity` | str | none / mild / moderate / severe |
| `side_pulls` | list | 推荐侧抽方向 (Phase 2) |

### 3.2 侧抽方向推荐 (Phase 2)

**文件**: `moldgen/core/parting.py` — `UndercutAnalyzer.recommend_side_pulls()`

当存在 undercut 时，自动推荐能解除遮挡的侧抽方向。

**算法**:
1. 收集 undercut 面法线的均值、SVD 主方向、垂直于主拉方向的基准方向
2. 去重并过滤（与主拉方向 > 30° 夹角）
3. 对每个候选方向评估能解除多少 undercut 面:
   - 面法线与候选方向点积 > 0 → 面从该方向可见
   - 面遮挡轴与候选方向夹角 > 45° → 可侧向滑出
4. 按覆盖率排序，返回 top-N

**输出 `SidePullDirection`**:

| 字段 | 说明 |
|------|------|
| `direction` | 推荐方向向量 |
| `n_resolved` | 能解除的 undercut 面数 |
| `coverage` | 覆盖率 (0-1) |
| `angle_from_primary` | 与主拉方向夹角 (度) |

### 3.3 高度场分型面 (Phase 1, v4.0 增强)

**文件**: `moldgen/core/parting.py` — `_build_heightfield_surface()`

在脱模方向垂直平面上建立均匀网格，沿 ±direction 射线投射取上下边界中点高度。

**v4.0 改进**:
- **边界约束**: 网格边缘逐渐混合回默认高度（线性渐变），确保模具切割边缘平整
- **向量化性能优化**: `np.minimum.at` / `np.maximum.at` 替代 Python 循环处理射线命中
- **向量化网格生成**: 使用 numpy 广播替代逐点 Python 循环

**自动选择逻辑** (`surface_type = "auto"`):
- 分型线非共面 + undercut moderate/severe → `projected`
- 分型线非共面 或 有 undercut → `heightfield`
- 其他 → `flat`

### 3.4 投影拉伸分型面 (Phase 2, v4.0 增强)

**文件**: `moldgen/core/parting.py` — `_build_projected_surface()`

从分型线向外径向拉伸，生成贴合模型轮廓的曲面。

**v4.0 改进**:
- **高度渐变**: 外环高度逐渐从分型线高度混合到默认平面高度，避免边缘突变

**算法**:
1. 以分型线为内环 (ring 0)
2. 计算每个顶点到中心的径向方向（投影到垂直于 direction 的平面）
3. 按 `projected_radial_steps` 步外延，每步延伸 `max_extent / n_steps`
4. 外环高度按线性比例从分型线高度渐变到默认平面高度
5. 在相邻环之间建立三角面片

**配置**: `projected_radial_steps` (默认 12)

如果投影生成失败，自动回退到 heightfield。

### 3.5 Undercut 热力图导出 (Phase 2)

**文件**: `moldgen/core/parting.py` — `PartingGenerator.export_undercut_heatmap()`

导出 per-face undercut 深度数据，用于 3D 视口着色。

返回结构:
```json
{
  "vertex_positions": [[x,y,z], ...],
  "face_indices": [[a,b,c], ...],
  "face_values": [0.0, 0.32, 0.87, ...],
  "max_depth": 12.5
}
```

前端 `UndercutOverlay.tsx` 使用蓝→青→绿→黄→红渐变色渲染 per-face 深度。

### 3.6 MoldBuilder 自适应分割集成 (Phase 2.5, v4.0 新增)

**文件**: `moldgen/core/mold_builder.py` — `_build_shells_adaptive_surface()`

**解决的核心问题**:
> 之前自适应分型面虽然能正确生成并显示在视口中，但模具壳体构建
> (`build_two_part_mold`) 始终使用平面 `slice_plane` 切割，完全忽略了
> heightfield/projected 分型面。这导致即使选择了自适应分型面，实际模具
> 仍按平面分割。

**新算法**:
1. 当 `parting_surface_type` 不为 "flat" 时，内部调用 `PartingGenerator` 生成分型面
2. 使用 `scipy.spatial.cKDTree` 建立分型面 UV 空间的 KD 树
3. 对 outer shell 每个顶点:
   - 投影到 UV 平面
   - 查询最近分型面网格点的高度
   - 根据顶点高度与分型面高度的关系分配到 upper/lower 半壳
4. 通过 `_extract_submesh` 提取半壳网格
5. 对每个半壳执行 `_robust_boolean_subtract(half, cavity)` 减去型腔
6. 如果自适应分割失败，自动回退到平面切割

`MoldResult` 包含:
- `undercut_severity`: 严重度字符串
- `parting_surface_type`: 使用的分型面类型

## 4. API

### 4.1 分型面生成 (增强)

```
POST /{model_id}/parting
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `surface_type` | string | `"auto"` | flat / heightfield / projected / auto |
| `heightfield_resolution` | int | 40 | 高度场网格分辨率 |
| `undercut_threshold` | float | 1.0 | 忽略的最小深度 (mm) |

响应新增: `undercut` (含 `side_pulls`), `surface_type_used`

### 4.2 独立 Undercut 分析

```
POST /{model_id}/undercut
```

### 4.3 Undercut 热力图

```
GET /{model_id}/undercut/heatmap
```

返回 per-face 深度数据用于 3D 着色。

### 4.4 模具生成 (增强)

```
POST /{model_id}/mold/generate
```

新增: `parting_surface_type` 参数

响应新增: `parting_surface_type`, `undercut_severity`

## 5. 前端变更

### 5.1 LeftPanel
- 分型面类型选择器: 自动 / 平面 / 高度场 / 投影拉伸
- "查看 Undercut 热力图" 按钮 (仅在有 undercut 时显示)
- "锁扣样式" 重命名 (原 "分型面样式")，避免与分型面类型混淆

### 5.2 RightPanel 属性面板
- 分型面类型显示
- Undercut 详情: 面数、占比、深度、严重度、体积
- 侧抽方向推荐数量
- 模具结果: 分型面类型 + undercut 严重度

### 5.3 UndercutOverlay.tsx
- 3D 视口中的 undercut 热力图着色层
- 蓝→青→绿→黄→红渐变 (按 face depth 归一化)
- 半透明覆盖在模型上
- 可通过场景管理器切换显隐

### 5.4 字体优化 (v4.0)
- 全局字体从 7-10px 范围提升到 11-12px，提高可读性

### 5.5 Store + Hook
- `UndercutHeatmapData`, `SidePullDirection` 接口
- `undercutHeatmap`, `undercutHeatmapVisible` 状态
- `useUndercutHeatmap()` hook
- `MoldResultInfo` 扩展 `parting_surface_type`, `undercut_severity`

## 6. 后续实现计划

### Phase 3: 多片自动分割 (MultiPieceSplitter)

- 球面均匀采样候选方向
- 每面片可见性分析 (基于 UndercutAnalyzer 射线)
- 贪心集合覆盖选最少方向
- 面片分配 + 区域合并
- 多片装配可视化

### Phase 4: 优化

- 分型线最短路径优化 (Dijkstra on mesh edges)
- 脱模力仿真 (接触面积 × 摩擦系数)
- GPU 加速射线投射 (CuPy / Numba)
- 样条曲面分型面 (B-spline fitting to parting line)

## 7. 已修复问题

### v4.0 修复清单

| 问题 | 原因 | 修复 |
|------|------|------|
| 严重度分级偏低 | `or` 逻辑导致 ratio>0.10 但 depth<8 仍为 moderate | 改为 `and` |
| 分型面类型与锁扣样式混淆 | 左侧面板两处"分型面XX"命名相似 | 重命名为"锁扣样式" |
| 模具壳体忽略自适应分型面 | `build_two_part_mold` 始终使用平面切割 | 新增 `_build_shells_adaptive_surface` |
| 高度场边缘突变 | 网格边缘直接使用 midpoint 高度 | 添加边界渐变约束 |
| 投影面外环高度突变 | 外环直接使用分型线高度 | 添加线性高度渐变 |
| 高度场射线循环慢 | O(n_pts × n_hits) Python 循环 | `np.minimum.at` 向量化 |
| UI 字体过小 (7-10px) | 设计时过于紧凑 | 全局提升至 11-12px |

## 8. 参考文献

1. "Molds for Meshes: Computing Smooth Parting Lines and Undercut Removal"
2. "A hybrid approach for automatic parting curve generation"
3. "Automatic Determination of 3-D Parting Lines and Surfaces"
4. "Algorithm for automatic parting surface extension"
5. "Generation of optimal parting direction based on undercut features"
