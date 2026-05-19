> 📖 [文档中心](README.md) | [← 上一篇: 核心算法](03-algorithms.md) | [下一篇: 技术栈 →](05-tech-stack.md)

# 模块详细设计

## 1. mesh_io 模块 — 多格式模型 I/O

### 1.1 支持格式（更新）

| 格式 | 导入 | 导出 | 加载方式 | 说明 |
|------|:---:|:---:|---------|------|
| STL (Binary/ASCII) | ✓ | ✓ | trimesh 原生 | FDM 打印标准格式 |
| OBJ | ✓ | ✓ | trimesh 原生 | 通用网格，支持材质 |
| FBX | ✓ | △ | pyassimp 后端 | 复杂格式，需过滤非几何数据 |
| 3MF | ✓ | ✓ | trimesh 原生 | 现代 3D 打印格式 |
| PLY | ✓ | ✓ | trimesh 原生 | 点云/网格格式 |
| STEP | ✓ | ✓ | cascadio/OCP | CAD 精确几何 |
| glTF/GLB | ✓ | ✓ | trimesh 原生 | 前端传输格式 |
| AMF | ✓ | △ | trimesh | 增材制造格式 |

### 1.2 核心接口

```python
class MeshIO:
    SUPPORTED_IMPORT = [".stl", ".obj", ".fbx", ".3mf", ".ply", ".step", ".stp",
                        ".gltf", ".glb", ".amf", ".dae", ".off"]
    SUPPORTED_EXPORT = [".stl", ".obj", ".3mf", ".ply", ".glb", ".step"]
    
    @staticmethod
    def load(filepath: Path, unit: str = "mm") -> MeshData:
        """加载模型文件，自动检测格式，FBX 通过 pyassimp 后端"""
    
    @staticmethod
    def export(mesh: MeshData, filepath: Path, format: str = "stl") -> None:
        """导出网格，支持多格式"""
    
    @staticmethod
    def export_multi(meshes: Dict[str, MeshData], directory: Path, 
                     format: str = "stl", naming: str = "shell_{i}") -> List[Path]:
        """批量导出多个网格（模具壳体+插板）"""
    
    @staticmethod
    def to_glb(mesh: MeshData) -> bytes:
        """转 GLB 二进制，用于前端传输"""

class MeshData:
    """内部统一网格数据结构"""
    vertices: np.ndarray        # (N, 3) float64
    faces: np.ndarray           # (M, 3) int64
    face_normals: np.ndarray    # (M, 3) float64
    vertex_normals: np.ndarray  # (N, 3) float64
    
    unit: str
    bounds: np.ndarray          # (2, 3) [min, max]
    volume: float
    surface_area: float
    is_watertight: bool
    face_count: int
    vertex_count: int
    
    edges: np.ndarray           # (E, 2) 延迟计算
    face_adjacency: np.ndarray  # 延迟计算
    
    def to_trimesh(self) -> trimesh.Trimesh: ...
    @staticmethod
    def from_trimesh(mesh: trimesh.Trimesh) -> 'MeshData': ...
```

## 2. mesh_repair 模块 — 网格修复

```python
class MeshRepair:
    def repair(self, mesh: MeshData) -> RepairResult: ...
    def check_quality(self, mesh: MeshData) -> QualityReport: ...

class QualityReport:
    is_watertight: bool
    non_manifold_edges: int
    degenerate_faces: int
    holes: int
    self_intersections: int
    duplicate_faces: int
    min_edge_length: float
    max_edge_length: float
    max_aspect_ratio: float
    face_count: int
    vertex_count: int
```

## 3. mesh_editor 模块 — 网格编辑（新增）

### 3.1 核心接口

```python
class MeshEditor:
    def __init__(self):
        self.history = EditHistory(max_history=50)
    
    # === 细化/简化 ===
    def subdivide_loop(self, mesh: MeshData, iterations: int = 1) -> MeshData:
        """Loop 细分，每次迭代面数 ×4"""
    
    def subdivide_to_size(self, mesh: MeshData, max_edge: float) -> MeshData:
        """按最大边长细化"""
    
    def subdivide_adaptive(self, mesh: MeshData, criteria: str = "curvature",
                          target_edge: float = 1.0) -> MeshData:
        """自适应细化（高曲率/大面积区域）"""
    
    def simplify_qem(self, mesh: MeshData, target_faces: int) -> MeshData:
        """QEM 简化到目标面数"""
    
    def simplify_ratio(self, mesh: MeshData, ratio: float) -> MeshData:
        """按比例简化 (0.5 = 面数减半)"""
    
    def generate_lod(self, mesh: MeshData, 
                     levels: List[float] = [1.0, 0.5, 0.25, 0.1]) -> List[MeshData]:
        """生成多级 LOD"""
    
    # === 变换 ===
    def translate(self, mesh: MeshData, offset: np.ndarray) -> MeshData: ...
    def rotate(self, mesh: MeshData, axis: np.ndarray, angle: float) -> MeshData: ...
    def scale(self, mesh: MeshData, factor: Union[float, np.ndarray]) -> MeshData: ...
    def mirror(self, mesh: MeshData, plane_normal: np.ndarray, 
               plane_point: np.ndarray = None) -> MeshData: ...
    def center(self, mesh: MeshData) -> MeshData:
        """居中到原点"""
    def align_to_floor(self, mesh: MeshData) -> MeshData:
        """最低点对齐到 Z=0"""
    
    # === 布尔运算 ===
    def boolean_union(self, a: MeshData, b: MeshData) -> MeshData: ...
    def boolean_difference(self, a: MeshData, b: MeshData) -> MeshData: ...
    def boolean_intersection(self, a: MeshData, b: MeshData) -> MeshData: ...
    
    # === 分析/测量 ===
    def measure_distance(self, mesh: MeshData, p1: np.ndarray, p2: np.ndarray) -> float: ...
    def measure_angle(self, mesh: MeshData, faces: List[int]) -> float: ...
    def compute_section(self, mesh: MeshData, plane_origin: np.ndarray,
                       plane_normal: np.ndarray) -> np.ndarray:
        """计算截面轮廓线"""
    def compute_thickness(self, mesh: MeshData) -> np.ndarray:
        """壁厚分析，返回每个顶点处的壁厚"""
    
    # === 拓扑编辑 ===
    def delete_faces(self, mesh: MeshData, face_indices: np.ndarray) -> MeshData: ...
    def fill_holes(self, mesh: MeshData) -> MeshData: ...
    def shell(self, mesh: MeshData, thickness: float) -> MeshData:
        """抽壳操作"""
    
    # === 高级操作 (nTopology-style, v6 新增) ===
    def smooth_laplacian(self, mesh: MeshData, iterations: int = 3,
                         lamb: float = 0.5) -> MeshData:
        """Laplacian 平滑 — 均匀邻域均值"""
    
    def smooth_taubin(self, mesh: MeshData, iterations: int = 3,
                      lamb: float = 0.5, mu: float = -0.53) -> MeshData:
        """Taubin 平滑 — 交替 λ/μ 防止体积收缩"""
    
    def smooth_humphrey(self, mesh: MeshData, iterations: int = 3,
                        alpha: float = 0.1, beta: float = 0.5) -> MeshData:
        """HC 平滑 (Humphrey's Classes) — 体积保持平滑"""
    
    def remesh_isotropic(self, mesh: MeshData,
                         target_edge_length: float | None = None) -> MeshData:
        """等尺重网格化 — subdivide→decimate 迫近目标边长"""
    
    def offset_surface(self, mesh: MeshData, distance: float) -> MeshData:
        """表面偏移 — 沿顶点法线平移"""
    
    def thicken(self, mesh: MeshData, thickness: float,
                direction: str = "both") -> MeshData:
        """将曲面网格增厚为实体 (outward / inward / both)"""
    
    # === 撤销/重做 ===
    def undo(self) -> MeshData: ...
    def redo(self) -> MeshData: ...
    def get_history(self) -> List[EditOperation]: ...

class EditOperation:
    type: str                    # "subdivide", "simplify", "translate", ...
    params: dict                 # 操作参数
    timestamp: datetime
    face_count_before: int
    face_count_after: int
    
    def apply(self, mesh: MeshData) -> MeshData: ...
    def reverse(self, mesh: MeshData) -> MeshData: ...
```

### 3.2 前端选择工具接口

```python
class SelectionService:
    def select_by_ray(self, mesh_id: str, ray_origin: List[float], 
                      ray_dir: List[float]) -> List[int]:
        """光线拾取面片"""
    
    def select_by_sphere(self, mesh_id: str, center: List[float], 
                         radius: float) -> List[int]:
        """球形区域选择"""
    
    def select_connected(self, mesh_id: str, seed_face: int,
                        angle_threshold: float = 30.0) -> List[int]:
        """连通区域选择（法线角度约束）"""
    
    def select_by_normal(self, mesh_id: str, direction: List[float],
                        threshold: float = 45.0) -> List[int]:
        """按法线方向选择"""
```

## 4. orientation_analyzer 模块 — GPU 加速脱模方向分析

```python
class OrientationAnalyzer:
    def __init__(self, config: OrientationConfig = None, 
                 gpu_compute: GPUCompute = None):
        self.gpu = gpu_compute or GPUCompute()  # 自动检测GPU
    
    def analyze(self, mesh: MeshData) -> OrientationResult: ...
    def evaluate_direction(self, mesh: MeshData, direction: np.ndarray) -> DirectionScore: ...
    def compute_visibility_map(self, mesh: MeshData, direction: np.ndarray) -> np.ndarray: ...
    def find_minimum_cover(self, mesh: MeshData) -> List[np.ndarray]: ...

class OrientationConfig:
    n_fibonacci_samples: int = 100
    n_top_candidates: int = 20
    n_final_candidates: int = 5
    visibility_method: str = "gpu"       # "gpu" | "raycast" | "raster"
    weights: dict = {
        "visibility": 0.30, "flatness": 0.20,
        "piece_count": 0.20, "symmetry": 0.15, "draft_angle": 0.15,
    }
```

## 5. parting_generator 模块 — 分型面生成

（接口设计同前版本，此处省略重复内容）

## 6. mold_builder 模块 — 模具壳体生成 (v8)

**核心改进**: 单位自适应 + 三级策略壳体构造 + 分型面互锁样式 + 螺丝固定法兰。

### 预处理 (v8 新增)

- **单位自适应** (`_auto_rescale_to_mm`): 自动检测模型单位 (m/cm/in)，缩放到 mm。扫描模型常以米为单位 (extents < 2)，不缩放会导致壁厚/间距参数远超模型尺寸，壳体几何完全错误。
- **最低面数** (`_ensure_min_faces`): 低面模型自动细分至 ≥ 12,000 面，保证空腔曲面有足够分辨率。
- **非水密修复**: `_create_cavity` 先修复模型再偏移，减少法线偏移后的自相交。

### 构造策略优先级

1. **布尔运算** (`_robust_boolean_subtract`): outer_box - cavity, 多引擎 (manifold3d → trimesh)
2. **体素回退** (`_build_shells_voxel`): 体素化 + marching cubes, 依赖 scikit-image
3. **直接拼接** (`_build_direct_shells`): box_half + cavity_inv_half, 仅可视化用

### 横截面与分型轮廓 (v6)

- `solid.section()` 在**过导入模型质心**、法向为脱模方向的分型面上截取 `mold_solid`，得到若干条 2D 折线。
- **外壳分型轮廓**取闭合回路中 **2D 面积最大** 的一条（鞋带头公式），而非周长最长——否则高面数腔体内表面常被误判为「主轮廓」，导致互锁特征沿腔体走线（ERR-020）。
- 面积均接近零时再按周长回退；轮廓点序保持 `discrete` 原始顺序供切向采样。

### 分型面互锁样式 (v5 新增)

`MoldConfig.parting_style` 支持 5 种样式:
- `flat`: 默认平面分割
- `dovetail`: 燕尾榫 — 梯形凸凹互锁
- `zigzag`: 锯齿形 — 三角齿状互锁
- `step`: 阶梯形 — 交替高低台阶
- `tongue_groove`: 榫槽 — 矩形凸凹配合

### 螺丝固定孔 (v5 → v6 重设计)

通过 `add_screw_holes=True` 在模具壁内生成 pocket+tab 螺丝孔:
- 自适应口袋尺寸: 基于到模型腔体的距离动态调整
- 支持 M1-M8 螺丝规格, 2/4/6/8 个孔位
- 带沉孔 (counterbore) 设计

### 浇注口/排气口 (v6.1 统一至浇注模块)

> **注意**: 浇注口和排气口不再在模具生成阶段自动创建。
> 它们现在由独立的浇注系统模块 (`GatingSystem`) 统一管理,
> 通过 `apply_to_mold()` 进行布尔差集切割。
> 详见 §8 gating_system 模块。

### 网格修复

每个壳体生成后自动执行多步修复: 退化面移除、法线修复、孔洞填充、绕序修复。

### 依赖

- `trimesh>=4.0.0` (核心网格操作)
- `shapely>=2.0.0` 与 `rtree>=1.0.0` (``trimesh.slice_plane`` 分型剖切加盖；缺省时回退到 `slice_faces_plane`）
- `manifold3d>=2.5.0` (布尔运算首选引擎)
- `scikit-image>=0.22.0` (marching cubes 体素回退)
- `scipy` (ndimage 体素膨胀)

## 6b. analysis 模块 — nTopology 级网格分析套件 (v6 新增)

提供五维几何分析能力，参考 nTopology 的 Implicit Modeling 和 Design for Additive Manufacturing (DfAM) 工作流。

### 数据类

```python
@dataclass
class ThicknessResult:
    per_vertex: np.ndarray       # (N,) 逐顶点壁厚 (mm)
    min_thickness: float
    max_thickness: float
    mean_thickness: float
    std_thickness: float
    thin_count: int              # 薄壁顶点数 (< thin_threshold)
    histogram_bins: list[float]
    histogram_counts: list[int]

@dataclass
class CurvatureResult:
    gaussian: np.ndarray         # (N,) Gaussian 曲率
    mean_curvature: np.ndarray   # (N,) Mean 曲率
    max_curvature: np.ndarray    # (N,) max(|G|, |H|)
    min_val: float
    max_val: float

@dataclass
class DraftAnalysisResult:
    per_face_angle: np.ndarray   # (M,) 逐面拔模角 (deg)
    min_draft: float
    max_draft: float
    mean_draft: float
    undercut_fraction: float     # 倒扣比例
    critical_fraction: float     # < critical_angle 比例
    histogram_bins: list[float]
    histogram_counts: list[int]

@dataclass
class SymmetryResult:
    x_symmetry: float            # [0, 1]
    y_symmetry: float
    z_symmetry: float
    best_plane: str              # "x" | "y" | "z"
    best_score: float
    principal_axes: list[list[float]]  # PCA 3×3

@dataclass
class OverhangResult:
    per_face_overhang: np.ndarray  # (M,) 布尔
    overhang_fraction: float
    overhang_area_mm2: float
    total_area_mm2: float
    critical_angle_deg: float

@dataclass
class BOMEntry:
    component: str
    volume_mm3: float
    surface_area_mm2: float
    face_count: int
    estimated_weight_g: float
    estimated_print_time_min: float
```

### 核心函数

```python
def compute_thickness(mesh: MeshData, n_rays: int = 6,
                      max_distance: float = 50.0,
                      thin_threshold: float = 1.0) -> ThicknessResult:
    """多射线逐顶点壁厚估计。算法: 沿 −normal + jitter 发射 n_rays 条射线，
    记录最近反向命中距离。O(N × n_rays) ray intersections."""

def compute_curvature(mesh: MeshData) -> CurvatureResult:
    """离散 Gaussian 曲率 (角亏法) + Mean 曲率 (cotangent Laplacian / trimesh)。"""

def compute_draft_analysis(mesh: MeshData,
                           pull_direction: list[float] | None = None,
                           critical_angle: float = 3.0) -> DraftAnalysisResult:
    """逐面拔模角。draft = arccos(|n · pull|)，倒扣 = n · pull < 0。"""

def compute_symmetry(mesh: MeshData) -> SymmetryResult:
    """X/Y/Z 轴平面对称评分。算法: 顶点镜像 + cKDTree 最近邻 Hausdorff 距离。"""

def compute_overhang(mesh: MeshData,
                     build_direction: list[float] | None = None,
                     critical_angle: float = 45.0) -> OverhangResult:
    """3D 打印悬垂检测。overhang = face normal 与 build_direction 夹角 > critical_angle。"""

def compute_bom(components: dict[str, MeshData],
                density_g_per_mm3: float = 1.24e-3) -> list[BOMEntry]:
    """多组件 BOM 估算 (体积/面积/重量/打印时间)。"""
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/analysis/{model_id}/thickness` | 壁厚分析 |
| POST | `/api/v1/analysis/{model_id}/curvature` | 曲率分析 |
| POST | `/api/v1/analysis/{model_id}/draft` | 拔模角分析 |
| POST | `/api/v1/analysis/{model_id}/symmetry` | 对称性分析 |
| POST | `/api/v1/analysis/{model_id}/overhang` | 悬垂分析 |
| POST | `/api/v1/analysis/{model_id}/smooth` | 网格平滑 |
| POST | `/api/v1/analysis/{model_id}/remesh` | 等尺重网格化 |
| POST | `/api/v1/analysis/{model_id}/thicken` | 曲面增厚为实体 |
| POST | `/api/v1/analysis/{model_id}/offset` | 表面偏移 |

所有端点包含:
- Pydantic `Field` 验证 (ge/le/gt/lt 约束)
- `asyncio.to_thread` 异步执行
- `try/except` + `logger.error` + `HTTPException(500)` 错误处理

## 6c. fea 模块 — 有限元结构分析 (v5 新增)

### 核心接口

```python
class FEASolver:
    def analyze(self, mesh: MeshData) -> FEAResult
```

### FEAResult 输出字段

| 字段 | 类型 | 说明 |
|------|------|------|
| displacement | (N,3) ndarray | 顶点位移向量 |
| displacement_magnitude | (N,) ndarray | 位移模 |
| von_mises_stress | (N,) ndarray | Von Mises 等效应力 |
| strain_energy | (N,) ndarray | 应变能密度 |
| safety_factor | (N,) ndarray | 安全系数 (σ_y/σ_vm) |
| max_displacement | float | 最大位移 (mm) |
| max_stress | float | 最大应力 (MPa) |
| min_safety_factor | float | 最小安全系数 |

### API 端点

- `POST /api/v1/simulation/fea/run` — 运行 FEA 分析
- `GET /api/v1/simulation/fea/visualization/{fea_id}` — 获取逐顶点可视化数据
- `GET /api/v1/simulation/fea/materials` — 列出材料预设
- `GET /api/v1/simulation/surface-map/{sim_id}` — 将仿真场映射到模型表面

## 6d. skin_mold 模块 — 蒙皮模具系统（v2 升级）

面向医学教具的软硬结合模具方案。v2 全面升级算法和功能。

### 核心类

| 类 | 说明 |
|-----|------|
| `SkinMoldConfig` | 全参数配置（蒙皮/模芯/支撑/定位/外模） |
| `SkinMoldGenerator` | 主生成器：模芯 + 空心化 + 支撑柱 + 定位 + 外模 + 厚度分析 |
| `SkinMoldResult` | 结果 + per-vertex 厚度图 + 均匀度评分 |
| `RegistrationFeature` | 定位销/方键数据 |

### v2 升级清单

| 功能 | v1 | v2 |
|------|----|----|
| 模芯生成 | EDT + MC | 形态学闭合 + 高斯 EDT 平滑 + MC + 自动简化 |
| 蒙皮厚度 | 均匀 | 均匀 / 曲率自适应变厚度 |
| 空心化 | concatenate 拼接 | boolean_subtract 水密差集 |
| 排液孔 | 1个底部中心 | 多个方向感知 |
| 定位特征 | 固定半径等角 | 碰撞感知自适应布局 |
| 定位类型 | 仅圆销 | 圆销 + 方键 |
| 支撑柱 | 无 | 模芯底部自动支撑 |
| 厚度分析 | 5000采样+统计 | 全顶点图+薄/厚点计数+均匀度评分 |
| 网格修复 | 凸包回退 | 体素填充修复（保留凹面） |
| 面数控制 | 无 | quadric_decimation 上限 |

### API 端点

```
POST /api/v1/molds/{model_id}/mold/generate-skin
GET  /api/v1/molds/skin/{skin_id}
GET  /api/v1/molds/skin/{skin_id}/core.glb
GET  /api/v1/molds/skin/{skin_id}/thickness-map   ← v2 新增
```

### 前端集成

- `moldStore.ts`: `moldMode`, `skinMoldResult` (含 `uniformity_score`, `n_thin_spots`)
- `useMoldApi.ts`: `useSkinMoldGeneration()` — 传递 v2 全部参数
- `LeftPanel.tsx` MoldPanel:
  - 标准/蒙皮模式切换
  - 变厚度蒙皮开关
  - 定位类型选择（圆销/方键）
  - 支撑柱开关
  - 厚度分析: P5/P95/标准差/均匀度评分/过薄过厚区域计数

---

## 7. insert_generator 模块 — 内嵌插板生成（v2: 多类型支撑板）

### v2 新增特性

- **4 种板型**: flat (平板), conformal (仿形), ribbed (加强筋), lattice (格栅)
- **仿形板**: cKDTree 表面最近邻投影 + Laplacian 平滑
- **加强筋**: 自动交叉排列肋条, 可配置高度/间距
- **格栅结构**: BCC 体心立方点阵, 可配置胞元尺寸/杆径
- **3D 可视化**: InsertPlateViewer 绿色半透明渲染, 源模型自动半透明
- **场景管理器集成**: 支撑板在场景树中可控 (显隐/透明度)

### 7.1 核心接口

```python
class InsertGenerator:
    def __init__(self, config: InsertConfig = None):
        self.config = config or InsertConfig()
    
    def auto_generate(self, model_mesh: MeshData, mold_result: MoldResult) -> InsertResult:
        """
        自动分析并生成内嵌插板
        
        Returns:
            InsertResult:
                inserts: List[InsertPlate]     # 生成的插板列表
                assembly_info: AssemblyInfo    # 装配信息
                silicone_volume: float         # 扣除插板后的硅胶体积
        """
    
    def generate_single(self, plane_origin: np.ndarray, plane_normal: np.ndarray,
                       model_mesh: MeshData, mold_result: MoldResult,
                       config: InsertConfig = None) -> InsertPlate:
        """手动指定平面生成单个插板"""
    
    def add_anchors(self, insert: InsertPlate, anchor_config: AnchorConfig) -> InsertPlate:
        """为插板添加锚固结构"""
    
    def edit_insert(self, insert: InsertPlate, edits: List[EditOperation]) -> InsertPlate:
        """编辑插板（用户自定义修改）"""
    
    def validate(self, insert: InsertPlate, model_mesh: MeshData,
                mold_result: MoldResult) -> InsertValidation:
        """验证插板可行性"""

class InsertConfig:
    thickness: float = 2.0                 # 板厚 mm
    inner_offset: float = 2.0              # 距模型表面最小距离 mm
    outer_offset: float = 1.0              # 距模具壳体最小距离 mm
    silicone_min_thickness: float = 2.0    # 硅胶最小包裹厚度 mm
    max_unsupported_thickness: float = 15.0 # 超过此厚度添加支撑插板 mm
    auto_anchor: bool = True               # 自动添加锚固结构
    fdm_min_wall: float = 1.2              # FDM 最小壁厚 mm

class AnchorConfig:
    type: str = "through_holes"             # 锚固类型
    # 网孔参数
    hole_diameter: float = 3.0
    hole_spacing: float = 7.0
    hole_pattern: str = "hexagonal"         # 几何: hex|grid|diamond|voronoi
                                            # TPMS: gyroid|schwarz_p|schwarz_d|neovius|lidinoid|iwp|frd
    # TPMS 参数
    tpms_cell_size: float | None = None     # TPMS 单胞尺寸 (mm), None=auto
    tpms_z_slice: float = 0.0              # 2D 切片 z 坐标
    max_holes: int = 300                   # 最大孔数
    # 场驱动半径调制
    variable_density: bool = False          # 启用场驱动半径调制
    density_field: str = "edge"            # edge|center|radial|stress|uniform
    density_min_factor: float = 0.4        # 最小半径系数
    density_max_factor: float = 1.0        # 最大半径系数
    # 凸起参数
    bump_height: float = 1.5
    bump_diameter: float = 2.5
    bump_spacing: float = 5.0
    # 沟槽参数
    groove_width: float = 1.5
    groove_depth: float = 1.0
    groove_spacing: float = 6.0
    groove_direction: str = "cross"         # "parallel" | "cross" | "radial"

class InsertPlate:
    mesh: MeshData                          # 插板网格
    insert_id: int
    plane_origin: np.ndarray                # 插板所在平面原点
    plane_normal: np.ndarray                # 法线
    thickness: float
    anchor_type: str
    anchor_config: AnchorConfig
    bounds: np.ndarray
    volume: float
    print_orientation: np.ndarray           # 建议打印方向
    installation_direction: np.ndarray       # 安装方向
```

## 7b. tpms 模块 — TPMS 隐式场晶格库 (v7 新增)

独立的三周期极小曲面 (TPMS) 数学库，为 `insert_generator` 提供精确的晶格/网孔布局。

### 7b.1 TPMS 曲面注册表

| 名称 | 函数签名 | 对称群 | 典型应用 |
|------|---------|--------|---------|
| **Gyroid** | `_gyroid(x,y,z)` | I4₁32 | 生物支架、均匀渗透 |
| **Schwarz-P** | `_schwarz_p(x,y,z)` | Pm3̄m | 热交换器、过滤器 |
| **Schwarz-D** | `_schwarz_d(x,y,z)` | Fd3̄m | 高比强度结构 |
| **Neovius** | `_neovius(x,y,z)` | Pm3̄m | 高孔隙率轻量化 |
| **Lidinoid** | `_lidinoid(x,y,z)` | I4₁32 | 手性流道设计 |
| **IWP** | `_iwp(x,y,z)` | Im3̄m | 双通道互穿结构 |
| **FRD** | `_frd(x,y,z)` | Fm3̄m | 复杂互连孔隙 |

### 7b.2 核心接口

```python
def evaluate_field_2d(
    name: str, half_span: float, cell_size: float,
    z_slice: float = 0.0, resolution: int = 200, margin: float = 0.0,
) -> TPMSFieldResult:
    """在 2D (u,v) 网格上求值 TPMS 场 f(ωu, ωv, ωz₀)"""

def extract_hole_centres(
    result: TPMSFieldResult, base_radius: float,
    min_spacing: float = None, max_holes: int = 300,
    adaptive_radius: bool = True,
) -> list[HoleCentre]:
    """从 |f| 场的形态学极值提取孔心，支持自适应半径"""

def apply_field_modulation(
    holes: list[HoleCentre], half_span: float,
    field_type: str = "edge", min_factor: float = 0.4, max_factor: float = 1.0,
) -> list[HoleCentre]:
    """5 种空间场连续调制孔径半径 (非二元删除)"""

def generate_tpms_holes(
    tpms_name: str, half_span: float, hole_diameter: float,
    cell_size: float = None, z_slice: float = 0.0,
    adaptive_radius: bool = True, max_holes: int = 300,
    density_field: str = None, density_min: float = 0.4, density_max: float = 1.0,
) -> list[tuple[float, float, float]]:
    """一站式 API: TPMS 名称 → [(u, v, radius)] 孔洞列表"""
```

### 7b.3 网孔雕刻管线 (insert_generator 集成)

```
_carve_holes() 管线:
  Phase 0: _subdivide_near_holes()  — 2 轮局部细分 [0.7r, 1.3r] 环带
  Phase 1: 面片删除               — 质心距 < r → remove (支持变半径)
  Phase 2: _snap_hole_boundaries() — 边界顶点投射到理想圆周
  Phase 3: _smooth_boundary_ring() — 3 轮 Laplacian 平滑边界 1-ring
```

## 7c. distance_field 模块 — SDF 隐式场引擎 (v10 新增)

nTopology 风格的隐式场基础设施，为 boolean 混合、场驱动设计、变厚度壳体提供底层能力。

### 7c.1 核心数据结构

```python
@dataclass
class SDFGrid:
    values: np.ndarray    # (nz, ny, nx) float32 有符号距离场
    origin: np.ndarray    # (3,) 世界坐标系原点
    spacing: float        # 体素边长 (mm)
    shape: tuple          # (nz, ny, nx)

    def sample(self, points) -> np.ndarray:  # 三线性插值
    def gradient(self, points) -> np.ndarray:  # 中心差分梯度
```

### 7c.2 核心接口

| 函数 | 功能 |
|------|------|
| `mesh_to_sdf(mesh, resolution, pad)` | 三角网格 → SDF 体素网格 |
| `smooth_union(a, b, k)` | Íñigo Quílez polynomial k-blend 并集 |
| `smooth_intersection(a, b, k)` | Smooth 交集 |
| `smooth_difference(a, b, k)` | Smooth 差集 |
| `field_offset(sdf, distance)` | 等距偏移 (正=外扩, 负=内缩) |
| `field_shell(sdf, thickness)` | 等厚壳体 |
| `field_variable_shell(sdf, thickness_field)` | 变厚度壳体 |
| `field_blend(a, b, op, blend_radius)` | 两 SDF 场混合布尔 |
| `field_remap(sdf, in_range, out_range)` | 值域线性重映射 |
| `field_gaussian_blur(sdf, sigma_mm)` | 高斯模糊 |
| `distance_field_from_points(template, points)` | 点集距离场 |
| `distance_field_from_axis(template, axis)` | 轴向距离场 |
| `extract_isosurface(sdf, iso)` | Marching Cubes 提取等值面 |
| `field_driven_shell(mesh, ...)` | 一站式场驱动变厚度壳 |

## 7d. topology_opt 模块 — SIMP 拓扑优化 (v10 新增)

密度法结构拓扑优化，最小化柔度 (最大化刚度)。

### 7d.1 核心接口

```python
def topology_opt_2d(config: TOConfig2D) -> TOResult2D
def topology_opt_3d(config: TOConfig3D) -> TOResult3D
def density_to_mesh(density, threshold, spacing) -> trimesh.Trimesh
```

| 参数 | 说明 |
|------|------|
| `nelx, nely, nelz` | 网格分辨率 |
| `volfrac` | 目标体积分数 (0.05–0.9) |
| `penal` | SIMP 惩罚指数 (典型 3.0) |
| `rmin` | 密度滤波半径 (元素单位) |
| `bc_type` | cantilever / mbb / bridge |

### 7d.2 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/advanced/topology-opt/2d` | 2D 拓扑优化 |
| POST | `/api/v1/advanced/topology-opt/3d` | 3D 拓扑优化 |

## 7e. lattice 模块 — 3D 体积晶格生成器 (v10 新增)

在任意包围网格内部生成晶格结构。

### 7e.1 晶格类型

| 类别 | 可用类型 | 说明 |
|------|---------|------|
| **graph** | BCC, FCC, Octet, Kelvin, Diamond | 杆件晶格 — 圆柱体素堆叠 |
| **tpms** | Gyroid, Schwarz-P/D, Neovius, Lidinoid, IWP, FRD | TPMS 壳体 — SDF + Marching Cubes |
| **foam** | Voronoi | Lloyd 松弛 + k=2 距离差壁面 |

### 7e.2 核心接口

```python
def generate_lattice(bounding_mesh, lattice_type, config) -> LatticeResult
def generate_graph_lattice(bounding_mesh, config) -> LatticeResult
def generate_tpms_lattice(bounding_mesh, config) -> LatticeResult
def generate_voronoi_foam(bounding_mesh, n_cells, wall_thickness, ...) -> LatticeResult
```

### 7e.3 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/advanced/lattice/generate` | 3D 晶格生成 |

## 7f. interference 模块 — 干涉/间隙分析 (v10 新增)

### 7f.1 核心接口

```python
def compute_clearance(mesh_a, mesh_b, sample_count) -> ClearanceResult
def validate_assembly(parts: list[(name, mesh)], min_clearance) -> AssemblyCheckResult
```

### 7f.2 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/advanced/interference/check` | 两零件干涉检测 |
| POST | `/api/v1/advanced/interference/assembly` | 多零件装配检查 |
| POST | `/api/v1/advanced/boolean` | 布尔运算 (含 smooth blend) |
| POST | `/api/v1/advanced/{model_id}/mesh-quality` | 网格质量分析 |
| POST | `/api/v1/advanced/sdf/compute` | SDF 计算 |
| POST | `/api/v1/advanced/sdf/variable-shell` | 场驱动变厚度壳 |

## 8. gating_system 模块 — 浇注系统 (v6.1 统一重构)

> **v6.1 变更**: 浇口/排气口功能已从模具模块(`mold_builder`)完全迁移至此模块。
> 模具生成阶段不再自动创建浇注口/排气口，改为在浇注系统设计阶段统一处理。

### 8.1 核心接口

```python
@dataclass
class GatingConfig:
    gate_diameter: float = 12.0     # 浇口直径 (mm)
    runner_width: float = 6.0       # 流道宽度 (mm)
    runner_depth: float = 4.0       # 流道深度 (mm)
    vent_width: float = 4.0         # 排气口宽度 (mm)
    vent_depth: float = 0.03        # 排气口深度 (mm, 硅胶用)
    n_vents: int = 4                # 排气口数量
    n_gates: int = 1                # 浇口数量 (1-4)
    runner_type: str = "cold"       # "cold" | "hot"
    gate_search_resolution: int = 20
    funnel_angle: float = 30.0      # 浇口漏斗角度
    gate_position: list | None = None      # 手动浇口位置 [x,y,z]
    vent_positions: list | None = None     # 手动排气口位置 [[x,y,z],...]

class GatingSystem:
    def design(self, mold: MoldResult, model: MeshData,
               material: MaterialProperties) -> GatingResult:
        """设计浇注系统 — 浇口优化 + BFS排气 + 流道布局"""

    def apply_to_mold(self, mold: MoldResult, result: GatingResult) -> None:
        """将浇注孔位切入模具壳体 (布尔差集, 自适应高度)"""
```

### 8.2 浇口位置优化算法

- **自动模式**: 在模型上方网格搜索 (gate_search_resolution²)
  - 评分 = `0.50 * flow_balance + 0.30 * accessibility + 0.20 * (1 - min_reach)`
  - flow_balance: 面积加权距离 std/mean 的倒数
  - accessibility: 到质心2D距离归一化
  - min_reach: 到最近面的距离惩罚
- **手动模式**: 用户指定坐标，自动投影到模型表面上方

### 8.3 排气口布置算法 (v6.1 BFS+气阱融合)

融合了原模具模块的 BFS 填充仿真算法:

1. **重力填充 BFS (Dijkstra)**: 从浇口最近面开始，上行成本 `1+3×dh`，下行 `max(0.3, 1+0.3×dh)`
2. **气阱检测**: 邻接图局部高度极值 = 空气聚集点
3. **综合评分**: `0.40 × fill_time + 0.35 × height + 0.25 × air_trap`
4. **最远点贪心选择**: 确保排气口间充分间距
5. **手动模式**: 用户坐标投影到面片中心 + 法线方向

### 8.4 孔位切割 (apply_to_mold)

- **自适应高度**: 每个壳体独立计算圆柱高度 (`shell_h_range + 4`, 上限 80mm)
- **分型面过滤**: 浇口只切入对应半模（根据与壳体质心的高度关系）
- **排气口沿法线**: 排气孔沿面片法线方向切割，而非全局方向
- **多浇口支持**: 二次浇口通过最远点策略自动布置

### 8.5 材料库

```python
class MaterialProperties:
    name: str = "silicone"
    viscosity: float = 3000.0       # mPa·s
    density: float = 1.1            # g/cm³
    cure_time: float = 240.0        # min
    shrinkage: float = 0.001
    max_pressure: float = 0.5       # MPa
    temperature: float = 25.0       # °C
```

## 9. flow_simulator 模块 — Fluent 风格灌注流动仿真（v6）

```python
class FlowSimulator:
    def __init__(self, config: SimConfig | None = None):
        self.config = config or SimConfig()
    
    def simulate(self, model: MeshData, gating: GatingResult,
                 material: MaterialProperties) -> SimulationResult:
        """运行灌注仿真，L1 启发式 / L2 达西流"""
    
    # L2 求解管线（v6 升级）：
    # 1. 体素化 → 2. 壁厚场 → 3. 渗透率 K=h²/12
    # 4. GMRES 压力求解 + 收敛追踪 → 5. 达西速度矢量 v=-K/μ·∇p
    # 6. 剪切率 + Cross 非牛顿修正 → 7. Dijkstra 充填前沿
    # 8. 前沿速度场 → 9. 温度场 → 10. 固化进度 → 11. 缺陷检测
    
    def extract_visualization_data(self, result) -> dict | None:
        """提取体素点云 + 速度矢量数组（供前端 3D 渲染）"""
    
    def extract_cross_section(self, result, axis, position, field_name) -> dict | None:
        """提取 2D 截面热力图数据"""
    
    def extract_surface_mapped_data(self, result, mesh, field_name) -> dict | None:
        """将体素场投影到网格表面顶点"""

class SimConfig:
    level: int = 2                       # 1=heuristic, 2=darcy
    voxel_resolution: int = 64           # 体素分辨率
    time_steps: int = 60
    animation_frames: int = 30
    use_gpu: bool = False
    detect_air_traps: bool = True
    detect_weld_lines: bool = True
    convergence_tol: float = 1e-6        # GMRES 收敛容差（v6）
    compute_shear_rate: bool = True
    compute_temperature: bool = True
    compute_cure_progress: bool = True

class SimulationResult:
    fill_fraction: float
    fill_time_seconds: float
    max_pressure: float
    defects: list[FlowDefect]
    # 体素场
    fill_time_field: np.ndarray | None      # (Nx, Ny, Nz)
    pressure_field: np.ndarray | None       # (Nx, Ny, Nz)
    velocity_magnitude: np.ndarray | None   # (Nx, Ny, Nz)
    velocity_vector: np.ndarray | None      # (3, Nx, Ny, Nz) — v6 新增
    flow_front_velocity: np.ndarray | None  # (Nx, Ny, Nz) — v6 新增
    convergence_history: list[dict] | None  # [{iteration, residual}] — v6 新增
    shear_rate_field: np.ndarray | None
    temperature_field: np.ndarray | None
    cure_progress_field: np.ndarray | None
    thickness_field: np.ndarray | None
    animation_frames: list[np.ndarray] | None
    # 元数据
    voxel_origin: np.ndarray | None
    voxel_pitch: float
    voxel_mask: np.ndarray | None
    gate_position: np.ndarray | None
    analysis: AnalysisReport | None

class AnalysisReport:
    # 原有指标 ...
    reynolds_number: float = 0.0           # Re = ρVL/μ — v6 新增
    pressure_drop: float = 0.0             # Pa — v6 新增
    recommendations: list[str]

class MaterialProperties:
    # 原有字段 ...
    n_power_law: float = 1.0               # 幂律指数 — v6 新增
    tau_star: float = 0.0                  # 临界剪切应力 Pa — v6 新增
```

**前端可视化组件（v6 新增）：**

| 组件 | 功能 |
|------|------|
| `VelocityArrows` | InstancedMesh 速度矢量箭头，最多 800 个，颜色随速度映射 |
| `ColorLegend` | CFD 色谱条图例，显示场名/单位/范围/充填进度 |
| `SimFloatingBar` | 升级控制栏：色谱选择/动画速率/矢量开关/图例开关 |
| `sampleSimPalette()` | JS 端色谱采样（与 GLSL 着色器一致） |
| `simPaletteCssGradient()` | CSS 渐变生成（用于 HTML 图例） |

## 10. gpu_compute 模块 — GPU 计算统一层（新增）

```python
class GPUCompute:
    """GPU 计算抽象层，CUDA 不可用时自动降级到 CPU"""
    
    def __init__(self):
        self.has_cuda = self._detect_cuda()
        self.device_name = self._get_device_name()  # e.g. "NVIDIA GeForce RTX 4060 Ti"
        self.vram_total = self._get_vram()           # e.g. 8192 MB
        self.vram_free = self._get_free_vram()
        self.compute_capability = self._get_cc()     # e.g. (8, 9)
    
    def get_info(self) -> GPUInfo:
        """返回 GPU 信息（用于前端显示和系统配置）"""
    
    # === BVH 光线投射 ===
    def build_bvh(self, mesh: MeshData) -> BVHHandle:
        """构建 BVH 加速结构"""
    
    def ray_intersect_batch(self, origins: np.ndarray, directions: np.ndarray,
                           bvh: BVHHandle) -> np.ndarray:
        """批量光线投射，返回命中掩码"""
    
    # === SDF 计算 ===
    def compute_sdf(self, mesh: MeshData, resolution: int = 128) -> np.ndarray:
        """GPU 加速的符号距离场计算"""
    
    def compute_unsigned_distance(self, mesh: MeshData, points: np.ndarray) -> np.ndarray:
        """批量计算点到网格的无符号距离"""
    
    # === 稀疏线性求解 ===
    def sparse_solve(self, A, b) -> np.ndarray:
        """CuPy 稀疏矩阵求解（GPU）或 scipy 降级"""
    
    # === 体素操作 ===
    def voxelize(self, mesh: MeshData, resolution: int) -> np.ndarray:
        """GPU 加速体素化"""
    
    def gradient_3d(self, field: np.ndarray) -> np.ndarray:
        """3D 梯度计算"""
    
    # === 性能监控 ===
    def get_memory_usage(self) -> dict:
        """返回当前 GPU 显存使用情况"""

class GPUInfo:
    available: bool
    device_name: str
    vram_total_mb: int
    vram_free_mb: int
    compute_capability: Tuple[int, int]
    cuda_version: str
    driver_version: str
```

## 11. API 模块

### 11.1 WebSocket 消息协议

```json
// 任务进度
{
    "type": "task_progress",
    "task_id": "uuid",
    "stage": "orientation_analysis",
    "progress": 0.45,
    "message": "正在评估候选方向 23/50...",
    "gpu_active": true
}

// 仿真帧
{
    "type": "sim_frame",
    "frame_index": 15,
    "fill_fraction": 0.3,
    "data_url": "/api/v1/simulation/{id}/frame/15"
}

// GPU 状态
{
    "type": "gpu_status",
    "vram_used_mb": 1234,
    "vram_total_mb": 8192,
    "gpu_utilization": 0.85,
    "temperature": 72
}
```

### 11.2 项目状态机

```python
class ProjectState(str, Enum):
    CREATED = "created"
    MODEL_LOADED = "model_loaded"
    MODEL_REPAIRED = "model_repaired"
    MODEL_EDITED = "model_edited"
    ORIENTATION_ANALYZED = "orientation_analyzed"
    PARTING_GENERATED = "parting_generated"
    MOLD_BUILT = "mold_built"
    INSERTS_GENERATED = "inserts_generated"
    GATING_DESIGNED = "gating_designed"
    SIMULATED = "simulated"
    OPTIMIZED = "optimized"
    EXPORTED = "exported"
    AI_GENERATING = "ai_generating"            # AI模型生成中
    AGENT_EXECUTING = "agent_executing"        # Agent自动执行中
    AGENT_WAITING_INPUT = "agent_waiting_input" # Agent等待用户确认
```

## 12. ai_service 模块 — AI 服务统一层（新增）

```python
class AIServiceManager:
    """AI 服务统一管理器 — 所有 AI 调用的入口"""
    
    def __init__(self, config: AIConfig):
        self.chat_client: OpenAI           # DeepSeek
        self.vision_client: OpenAI         # Qwen-VL
        self.image_client: TongyiClient    # 通义万相
        self.model3d_client: TripoClient   # Tripo3D
    
    async def chat(self, messages: List[dict], tools: List[dict] = None,
                   stream: bool = False) -> Union[ChatResponse, AsyncIterator]:
        """LLM 对话（支持 Function Calling 和流式输出）"""
    
    async def generate_image(self, prompt: str, style: str = "medical_textbook",
                            size: str = "1024x1024", count: int = 1) -> List[ImageResult]:
        """生成图像"""
    
    async def generate_3d_model(self, text_prompt: str = None,
                                image_path: str = None,
                                quality: str = "standard") -> Model3DResult:
        """生成3D模型（文字或图像输入）"""
    
    async def analyze_image(self, image_url: str, question: str) -> str:
        """多模态图像理解"""
    
    def get_usage_stats(self) -> dict:
        """获取 AI API 用量统计"""

class ImageResult:
    url: str
    local_path: Optional[str]
    prompt: str
    model: str

class Model3DResult:
    task_id: str
    status: str              # "pending" | "processing" | "completed" | "failed"
    model_path: Optional[str]  # GLB 文件路径
    mesh_data: Optional[MeshData]
```

## 13. ai_agent 模块 — 内置 Agent 执行系统（重大扩展）

### 13.1 Agent 执行引擎

```python
class AgentExecutionEngine:
    """Agent 自动执行引擎 — 核心调度中枢"""
    
    def __init__(self, agents: Dict[str, BaseAgent],
                 tool_registry: ToolRegistry,
                 ai_service: AIServiceManager):
        self.agents = agents        # 6大内置Agent
        self.tools = tool_registry  # 全局工具注册表
        self.ai = ai_service
        self.active_tasks: Dict[str, ExecutionContext] = {}
    
    async def execute(self, user_request: str,
                      mode: ExecutionMode = ExecutionMode.SEMI_AUTO
                     ) -> AsyncIterator[ExecutionEvent]:
        """
        主执行入口
        1. MasterAgent 解析意图 → 生成执行计划
        2. 按计划依次调度专业 Agent
        3. 每个 Agent 内部按工具链自动执行
        4. 根据 mode 决定确认点
        """
    
    async def handle_interrupt(self, task_id: str, instruction: str):
        """用户中途插入指令（暂停/跳过/改参数）"""
    
    async def resume(self, task_id: str):
        """恢复暂停的任务"""
    
    async def switch_mode(self, task_id: str, mode: ExecutionMode):
        """运行时切换执行模式"""
    
    def get_agent_statuses(self) -> Dict[str, AgentStatus]:
        """获取所有Agent当前状态"""

class ExecutionMode(str, Enum):
    AUTO = "auto"             # 全自动
    SEMI_AUTO = "semi_auto"   # 半自动(默认)
    STEP_BY_STEP = "step"     # 逐步确认

class ExecutionContext:
    """跨Agent共享的执行上下文"""
    task_id: str
    mode: ExecutionMode
    current_model: Optional[MeshData]
    current_mold: Optional[MoldResult]
    current_inserts: Optional[InsertResult]
    current_simulation: Optional[SimulationResult]
    execution_plan: ExecutionPlan
    history: List[ExecutionEvent]
    user_preferences: Dict[str, Any]

class ExecutionPlan:
    """由MasterAgent生成的执行计划"""
    steps: List[PlanStep]
    estimated_time_seconds: int
    
class PlanStep:
    step_id: int
    agent_name: str              # "model" | "mold" | "insert" | "sim" | "creative"
    task_description: str
    auto_execute: bool
    depends_on: List[int]        # 依赖的步骤ID
    
    def needs_confirmation(self, mode: ExecutionMode) -> bool:
        """根据执行模式判断是否需要确认"""

class ExecutionEvent:
    type: str                # "plan_created" | "agent_switch" | "step_start" |
                             # "step_complete" | "tool_call" | "tool_result" |
                             # "need_confirmation" | "token" | "error" |
                             # "task_complete" | "agent_status"
    data: dict
    timestamp: float
    agent: Optional[str]
```

### 13.2 BaseAgent 抽象基类

```python
class BaseAgent(ABC):
    """所有内置Agent的基类"""
    
    name: str                        # Agent唯一标识
    display_name: str                # 中文显示名
    system_prompt: str               # 系统提示词
    tools: List[str]                 # 可调用工具名列表
    auto_chain: Dict[str, List[str]] # 自动执行链规则
    
    @abstractmethod
    async def execute(self, task: str, params: dict,
                      mode: ExecutionMode,
                      context: ExecutionContext
                     ) -> AsyncIterator[ExecutionEvent]:
        """执行分配的子任务"""
    
    async def plan(self, task: str) -> List[dict]:
        """Agent内部规划子步骤"""
    
    def get_available_tools(self) -> List[dict]:
        """返回该Agent可用工具的JSON Schema列表"""
    
    def should_confirm(self, action: str, mode: ExecutionMode) -> bool:
        """判断某操作在当前模式下是否需要确认"""

class AgentStatus:
    agent_name: str
    state: str               # "idle" | "running" | "waiting" | "error" | "inactive"
    current_action: Optional[str]
    progress: Optional[float]
```

### 13.3 六大内置 Agent 接口

```python
class MasterAgent(BaseAgent):
    """总控Agent — 意图路由 + 任务编排"""
    name = "master"
    
    ROUTING_TOOLS = [
        "dispatch_to_agent",     # 分配子任务到专业Agent
        "create_execution_plan", # 创建多步骤执行计划
        "ask_user",              # 请求用户选择/确认
    ]
    
    async def plan(self, user_request: str, mode: ExecutionMode) -> ExecutionPlan:
        """调用LLM解析用户意图，生成执行计划"""
    
    async def route(self, user_input: str) -> Tuple[str, str, dict]:
        """意图路由: 返回 (agent_name, task, params)"""

class ModelAgent(BaseAgent):
    """模型处理Agent — 导入/修复/编辑/细化/简化"""
    name = "model"
    
    TOOLS = [
        "load_model", "check_mesh_quality", "repair_mesh",
        "subdivide_mesh", "simplify_mesh", "transform_mesh",
        "boolean_operation", "measure", "compute_section",
        "compute_thickness", "select_faces", "delete_faces",
        "fill_holes", "shell_mesh", "center_mesh",
        "align_to_floor", "export_model", "get_model_info",
    ]
    
    AUTO_CHAIN = {
        "after_load": ["check_mesh_quality"],  # 导入后自动检查
        "after_repair": ["get_model_info"],    # 修复后自动报告
    }

class MoldDesignAgent(BaseAgent):
    """模具设计Agent — 方向分析→分型→壳体→浇注"""
    name = "mold"
    
    TOOLS = [
        "analyze_orientation", "get_direction_candidates",
        "select_direction", "generate_parting_line",
        "generate_parting_surface", "split_into_shells",
        "build_mold_shells", "add_alignment_pins",
        "add_bolt_holes", "check_fdm_printability",
        "optimize_for_fdm", "design_gating_system",
        "set_mold_params", "get_mold_info", "preview_assembly",
    ]
    
    AUTO_PIPELINE = [
        {"tool": "analyze_orientation", "auto": True},
        {"tool": "select_direction", "auto": True, "confirm_if": "score < 0.7"},
        {"tool": "generate_parting_line", "auto": True},
        {"tool": "generate_parting_surface", "auto": True, "retry_on_fail": True},
        {"tool": "split_into_shells", "auto": True},
        {"tool": "build_mold_shells", "auto": True},
        {"tool": "add_alignment_pins", "auto": True},
        {"tool": "check_fdm_printability", "auto": True},
        {"tool": "design_gating_system", "auto": True},
    ]

class InsertAgent(BaseAgent):
    """支撑板Agent — AI辅助的支撑板智能设计"""
    name = "insert"
    
    TOOLS = [
        "analyze_insert_positions", "generate_insert_plate",
        "add_anchor_structure", "modify_insert", "delete_insert",
        "add_locating_slots", "validate_insert_assembly",
        "check_silicone_coverage", "check_insertion_path",
        "get_insert_info", "analyze_with_vision",
    ]
    
    # 器官类型→支撑板策略映射(硬编码专业知识)
    ORGAN_STRATEGY = {
        "solid_organ": {"plate": "central_transverse", "anchor": "through_holes"},
        "hollow_organ": {"plate": "inner_ring", "anchor": "grooves"},
        "tubular": {"plate": "axial_skeleton", "anchor": "bumps"},
        "tissue_sheet": {"plate": "base_plate", "anchor": "knurl"},
    }

class SimOptAgent(BaseAgent):
    """仿真优化Agent — 灌注仿真 + 缺陷检测 + 自动优化"""
    name = "simopt"
    
    TOOLS = [
        "run_simulation_l1", "run_simulation_l2",
        "detect_defects", "generate_sim_report",
        "optimize_gate_position", "optimize_runner_size",
        "add_vent", "adjust_wall_thickness",
        "run_optimization_loop", "compare_results",
        "get_simulation_data", "select_material",
    ]
    
    AUTO_OPTIMIZE_CONFIG = {
        "max_iterations": 5,
        "convergence_threshold": 0.05,
        "defect_actions": {
            "short_shot": ["optimize_gate_position", "optimize_runner_size"],
            "air_trap": ["add_vent"],
            "fill_imbalance": ["optimize_gate_position"],
            "weld_line": ["optimize_gate_position"],
        }
    }

class CreativeAgent(BaseAgent):
    """创意生成Agent — AI图像/3D模型生成 + 需求转化"""
    name = "creative"
    
    TOOLS = [
        "optimize_prompt", "generate_images",
        "generate_3d_from_text", "generate_3d_from_image",
        "review_model_quality", "suggest_improvements",
        "load_generated_model",
    ]
```

### 13.4 全局工具注册表

```python
class ToolRegistry:
    """Agent 工具注册表 — 将 Function Calling 映射到实际功能模块"""
    
    def __init__(self):
        self._tools: Dict[str, RegisteredTool] = {}
    
    def register(self, name: str, func: Callable,
                 schema: dict, category: str = "general"):
        """注册工具: name→(执行函数, JSON Schema, 分类)"""
    
    async def execute(self, name: str, args: dict,
                      context: ExecutionContext) -> ToolResult:
        """执行工具并返回结果"""
    
    def get_schemas(self, agent_name: str = None) -> List[dict]:
        """获取工具JSON Schema列表（可按Agent过滤）"""
    
    def get_all_tool_names(self) -> List[str]:
        """获取所有已注册工具名"""

class RegisteredTool:
    name: str
    func: Callable
    schema: dict            # OpenAI Function Calling JSON Schema
    category: str           # "model" | "mold" | "insert" | "sim" | "ai" | "export"
    requires_confirmation: Dict[ExecutionMode, bool]  # 各模式下是否需确认

class ToolResult:
    success: bool
    data: Any
    message: str
    duration_ms: float
```

### 13.5 Agent 记忆模块

```python
class AgentMemory:
    """Agent 短期记忆 — 会话级"""
    conversation_history: List[Message]
    execution_context: ExecutionContext
    user_preferences: Dict[str, Any]     # 从对话中提取的偏好

class AgentLongTermMemory:
    """Agent 长期记忆 — 持久化到SQLite"""
    user_defaults: Dict[str, Any]        # 用户默认参数偏好
    frequent_organs: List[str]           # 常用器官类型
    preferred_materials: List[str]       # 常用材料
    past_successful_configs: List[dict]  # 历史成功配置
    
    def get_recommendation(self, organ_type: str) -> dict:
        """基于历史成功配置推荐参数"""
    
    def save_successful_run(self, config: dict, result: dict):
        """保存成功执行的配置"""
```

### 13.6 确认规则表

```python
CONFIRMATION_RULES: Dict[str, Tuple[bool, bool, bool]] = {
    # 操作                      Auto   Semi   Step
    "load_model":              (False, False, True),
    "repair_mesh":             (False, False, True),
    "simplify_mesh":           (False, False, True),
    "boolean_operation":       (False, True,  True),   # 不可逆
    "select_direction":        (False, True,  True),   # 关键决策
    "shell_count_decision":    (False, True,  True),   # 关键决策
    "insert_plate_plan":       (False, True,  True),   # 关键决策
    "generate_inserts":        (False, False, True),
    "run_simulation":          (False, False, True),
    "auto_optimize":           (False, False, True),
    "export_files":            (False, True,  True),   # 最终输出
    "select_generated_image":  (False, True,  True),   # 审美选择
    "delete_anything":         (True,  True,  True),   # 始终确认
}
```

## 14. AI 相关前端组件接口（新增）

### 14.1 悬浮球状态

```typescript
interface AIChatStore {
  isOpen: boolean;
  messages: ChatMessage[];
  isGenerating: boolean;
  pendingAction: ActionRequest | null;
  
  toggle(): void;
  sendMessage(content: string, images?: File[]): Promise<void>;
  confirmAction(actionId: string): Promise<void>;
  rejectAction(actionId: string): Promise<void>;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  images?: string[];
  model3d?: string;
  action?: ActionRequest;
  timestamp: number;
}

interface ActionRequest {
  id: string;
  type: "confirm_inserts" | "confirm_mold" | "confirm_export" |
        "confirm_direction" | "confirm_shell_count" | "select_image";
  description: string;
  data: any;
  options?: string[];         // 选项列表
  status: "pending" | "confirmed" | "rejected";
}
```

### 14.2 Agent 工作站状态（新增）

```typescript
interface AgentWorkstationStore {
  isOpen: boolean;
  currentTask: AgentTask | null;
  executionMode: "auto" | "semi_auto" | "step";
  agentStatuses: Record<string, AgentStatusUI>;
  
  startTask(request: string): Promise<void>;
  switchMode(mode: "auto" | "semi_auto" | "step"): void;
  confirmStep(stepId: number, choice?: string): void;
  rejectStep(stepId: number): void;
  interruptTask(instruction: string): void;
  pauseTask(): void;
  resumeTask(): void;
  cancelTask(): void;
  skipStep(): void;
  goBackStep(): void;
}

interface AgentTask {
  taskId: string;
  description: string;
  status: "planning" | "running" | "paused" | "waiting_input" |
          "completed" | "failed" | "cancelled";
  plan: PlanStep[];
  currentStepId: number;
  startTime: number;
  estimatedTime: number;
  progress: number;            // 0-1
  executionLog: LogEntry[];
}

interface PlanStep {
  stepId: number;
  agentName: string;
  agentDisplayName: string;
  description: string;
  status: "pending" | "running" | "completed" | "skipped" | "failed";
  toolCalls: ToolCallRecord[];
  result?: any;
  needsConfirmation: boolean;
  confirmationQuestion?: string;
  confirmationOptions?: string[];
  startTime?: number;
  endTime?: number;
}

interface AgentStatusUI {
  name: string;
  displayName: string;
  state: "idle" | "running" | "waiting" | "error" | "inactive";
  currentAction?: string;
  progress?: number;
  icon: string;               // Agent图标
  color: string;              // 状态颜色
}

interface LogEntry {
  timestamp: number;
  agent: string;
  level: "info" | "action" | "result" | "confirmation" | "error";
  message: string;
  data?: any;
}

interface ToolCallRecord {
  tool: string;
  args: Record<string, any>;
  result?: any;
  duration_ms: number;
  status: "success" | "failed" | "skipped";
}
```

### 14.3 Agent Hooks（新增）

```typescript
function useAgentExecution(): {
  task: AgentTask | null;
  mode: ExecutionMode;
  agentStatuses: Record<string, AgentStatusUI>;
  isRunning: boolean;
  
  startExecution(request: string, mode?: ExecutionMode): Promise<void>;
  confirm(stepId: number, choice?: string): void;
  interrupt(instruction: string): void;
  switchMode(mode: ExecutionMode): void;
  pause(): void;
  resume(): void;
  cancel(): void;
};

function useAgentWebSocket(taskId: string): {
  events: ExecutionEvent[];
  connectionStatus: "connected" | "disconnected" | "reconnecting";
};
```

---

## 11. 日志与报错机制

### 11a. 后端日志 (`moldgen/utils/logger.py`)

```
setup_logging(level="INFO")
  ├── stdout (控制台格式)
  ├── data/logs/moldgen.log     (RotatingFileHandler 5MB × 5)
  └── data/logs/moldgen-error.log (ERROR 级, 5MB × 5)

get_recent_logs(n=200) → list[str]
get_recent_errors(n=100) → list[str]
```

**API 端点**:
- `GET /api/v1/system/logs?n=200` — 返回最新 N 行主日志
- `GET /api/v1/system/logs/errors?n=100` — 返回最新 N 行错误日志

### 11b. 前端错误捕获 (`App.tsx`)

| 机制 | 捕获范围 |
|------|---------|
| `ErrorBoundary` class | React 组件树渲染异常 |
| `window.onerror` | 同步 JS 运行时错误 |
| `window.unhandledrejection` | 未捕获 Promise rejection |
| `toastError()` | 所有错误统一通过 toast 弹窗通知用户 |

### 11c. 前端控制台 (`ConsolePanel.tsx`)

- 标题栏 Terminal 按钮切换显隐
- 实时拉取 `/system/logs` (3s 间隔)
- 错误日志独立 tab (5s 间隔)
- 日志行按级别 (ERROR/WARNING/INFO) 着色

---

## 12. 桌面封装 (Tauri 2.0)

### 12a. 架构

```
Tauri (Rust) ─── 启动 ──→ moldgen-server(.exe)  ← PyInstaller 打包
      │                         │
      ├── 前端 (Vite build)     └── FastAPI :8000
      │   └── WebView2               └── REST + WebSocket
      │
      └── on_exit → kill backend child
```

### 12b. 构建流程

```bash
# 1. 打包 Python 后端
python scripts/build_backend.py
# → frontend/src-tauri/binaries/moldgen-server-x86_64-pc-windows-msvc.exe

# 2. 构建 Tauri 安装包
cd frontend
npm run tauri:build
# → frontend/src-tauri/target/release/bundle/nsis/MoldGen_0.1.0_x64-setup.exe
# → frontend/src-tauri/target/release/bundle/msi/MoldGen_0.1.0_x64_en-US.msi
```

### 12c. Tauri 配置关键项 (`tauri.conf.json`)

| 配置 | 值 |
|------|-----|
| `bundle.targets` | `["nsis", "msi"]` |
| `bundle.externalBin` | `["binaries/moldgen-server"]` |
| `bundle.windows.nsis.languages` | `["SimpChinese", "English"]` |
| `bundle.windows.nsis.installMode` | `"both"` (per-user / all-users) |
| `app.windows[0].title` | `"MoldGen — AI 医学教具模具工作站"` |

---

## 15. 前端 UI 架构 (v2 重构)

### 15.1 整体布局

参考 Blender / Unity / 专业模具 CAD 软件的面板布局：

```
┌─────────────────────────────────────────────────────────────┐
│ [M] MoldGen  |  AI 医学教具模具工作站  ●   [ ⌘ ] [ ⚙ ]    │  ← 标题栏
├─────────────────────────────────────────────────────────────┤
│ ① 导入 ─ ② 编辑 ─ ③ 方向 ─ ④ 模具 ─ ...  0/8 完成        │  ← 工作流导航
├───────────┬──────────────────────────┬──────────────────────┤
│           │  工具条 (步骤相关)        │  大纲 │ 属性 │ 统计  │  ← 标签式右面板
│ 参数面板   │                          │                      │
│ (步骤驱动) │       3D 视口            │  场景大纲 (树形)      │
│           │   (R3F + Three.js)       │  ├ 源模型             │
│           │                          │  ├ 模具壳体           │
│           │                          │  │  ├ 壳体 #0         │
│           │                          │  │  └ 壳体 #1         │
│           │                          │  ├ 支撑板             │
│           │                          │  └ 仿真热力图         │
│           │                          │  ────────────────     │
│           │                          │  属性检查器 (选中对象) │
├───────────┴──────────────────────────┴──────────────────────┤
│ ● 已连接 | ⚡ GPU 4060Ti | 💾 799/16380 MB  │ v0.1.0 Agent │  ← 状态栏
└─────────────────────────────────────────────────────────────┘
```

### 15.2 组件结构

| 组件 | 文件 | 功能 |
|------|------|------|
| **App** | `App.tsx` | 根布局: 标题栏 + WorkflowPipeline + 三栏 + 浮动层 |
| **LeftPanel** | `layout/LeftPanel.tsx` | 步骤驱动参数面板 (290px), 8 个子面板按 currentStep 切换 |
| **RightPanel** | `layout/RightPanel.tsx` | 标签式面板 (280px): 大纲 / 属性 / 统计 三个标签页 |
| **SceneManager** | `layout/SceneManager.tsx` | **Blender Outliner 风格**场景树, 树形层级 + 选中高亮 + 属性检查 |
| **WorkflowPipeline** | `layout/WorkflowPipeline.tsx` | 8 步工作流导航条, 进度指示 + 状态标记 |
| **StepToolbar** | `layout/StepToolbar.tsx` | 视口上方步骤相关快捷操作条, 分组 + 分隔符 |
| **StatusBar** | `layout/StatusBar.tsx` | 底部状态栏: 连接 / GPU / VRAM / 步骤点 / Agent |
| **Viewport** | `viewer/Viewport.tsx` | R3F Canvas, 灯光/HDRI/Grid/Gizmo, 所有 3D 图层 |

### 15.3 场景管理器 (SceneManager)

借鉴 Blender Outliner + Unity Hierarchy:

- **树形层级**: 模型 → 模具壳体 → 单个壳体; 支撑板; 浇注系统; 仿真热力图
- **可见性开关**: 每个节点独立 Eye/EyeOff 切换
- **不透明度滑块**: 展开后可调 (SlidersHorizontal 图标)
- **选中高亮**: 点击选中节点, 底部显示属性检查器 (面数/水密性/尺寸等)
- **搜索过滤**: 顶部搜索栏快速定位对象
- **类型图标 + 色彩编码**: 每种对象类型有独立颜色 (model=蓝, mold=青, insert=绿, sim=粉)

### 15.4 主题设计

深色主题, CSS 变量体系:

| Token | 色值 | 用途 |
|-------|------|------|
| `bg-primary` | `#0d0d12` | 最深背景 (标题栏/主区域) |
| `bg-secondary` | `#14141e` | 次级背景 (状态栏/工具条) |
| `bg-panel` | `#191924` | 面板背景 |
| `bg-inset` | `#111118` | 内嵌元素背景 (属性行) |
| `accent` | `#6366f1` | 品牌主色 (Indigo) |
| `success` | `#10b981` | 成功/完成 (Emerald) |
| `obj-model` | `#60a5fa` | 模型对象 (蓝) |
| `obj-mold` | `#22d3ee` | 模具对象 (青) |
| `obj-insert` | `#4ade80` | 支撑对象 (绿) |
| `obj-sim` | `#f472b6` | 仿真对象 (粉) |

### 15.5 状态管理

Zustand 扁平存储 + TanStack Query:

| Store | 职责 |
|-------|------|
| `appStore` | 步骤FSM, 面板开关, 后端状态, GPU |
| `modelStore` | 模型ID/文件名/网格信息/GLB URL |
| `moldStore` | 方向/分型/模具结果, 壳体选择 |
| `insertStore` | 支撑位置/板/画笔模式 |
| `simStore` | 浇注/仿真/优化/可视化/FEA |
| `viewportStore` | 图层可见性/不透明度/显示模式/网格单位 |
| `aiStore` | 聊天/Agent 执行/WebSocket 事件 |

---

## 16. Phase 2 工具栏与交互系统 (v3)

### 16.1 统一工具栏事件系统

**问题**: Phase 1 中, `StepToolbar` 通过 `CustomEvent("moldgen:toolbar-action")` 分发工具按钮点击, 但只有 `EditPanel`（编辑修复步骤）监听了此事件, 导致其他 7 个步骤中的工具栏按钮完全无效。

**解决方案**: 引入 `useToolbarHandler` hook (`frontend/src/hooks/useToolbarActions.ts`):

```python
# 架构设计
useToolbarHandler(actions: Record<string, () => void>)
  # 每个 panel 独立注册自己的 action 映射
  # 通过 useRef 保持最新闭包, 避免 stale closure
  # 当 panel unmount 时自动清理 listener
```

现在 **全部 8 个步骤面板** 都注册了工具栏动作:

| Panel | 可用 toolbar actions |
|-------|---------------------|
| ImportPanel | `open`, `upload` |
| EditPanel | `auto_repair`, `simplify`, `subdivide`, `center`, `rotate`, `scale_up`, `scale_down`, `flip`, `mirror`, `d_measure` |
| OrientationPanel | `analyze`, `refresh`, `preview` |
| MoldPanel | `parting`, `build_shell`, `d_preview` |
| InsertPanel | `analyze_pos`, `gen_plate`, `validate` |
| GatingPanel | `design`, `preview` |
| SimPanel | `run_sim`, `optimize`, `heatmap`, `defects` |
| ExportPanel | `export_model`, `export_mold`, `export_insert`, `export_all`, `d_all` |

### 16.2 键盘快捷键系统

`useToolbarShortcuts` hook 根据当前步骤动态映射无修饰符单键:

| 步骤 | 快捷键 | 动作 |
|------|--------|------|
| import | O / U | 打开文件 / 上传 |
| repair | R / S | 自动修复 / 简化 |
| orientation | A | 分析方向 |
| mold | P / G | 分型面 / 生成壳体 |
| insert | A / G | 分析位置 / 生成支撑板 |
| gating | D | 设计浇注系统 |
| 全局 | F5 / F6 | 运行仿真 / 自动优化 |

Ctrl+1~8 切换步骤, Ctrl+B/I 面板开关等保持不变。

### 16.3 浇注系统参数扩展

`GatingPanel` → `useGatingDesign` → 后端现在传递全部参数:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `runner_type` | string | `"cold"` | 冷/热流道 |
| `n_gates` | int | 1 | 浇口数量 (1-4) |
| `runner_width` | float | 4.0mm | 流道宽度 |
| `gate_diameter` | float | 6.0mm | 浇口直径 |
| `n_vents` | int | 3 | 排气孔数 |

`GatingConfig` 数据类新增 `n_gates`, `runner_type` 字段。

### 16.4 模具设计参数扩展

`MoldPanel` → `useMoldGeneration` → 后端新增:

| 参数 | 类型 | 说明 |
|------|------|------|
| `surface_texture` | string | 模具表面纹理 (none/matte/fine_grain/medium_grain/coarse_grain/knurl) |
| `mold_material` | string | 模具材料 (pla/abs/petg/resin/silicone_mold/aluminum/steel) |

### 16.5 3D 视口增强

新增 **视图预设系统** (类 Blender Numpad):

| 视图 | 相机方向 | Blender 对应 |
|------|---------|-------------|
| 前 | [0,0,1] | Numpad 1 |
| 后 | [0,0,-1] | Ctrl+Numpad 1 |
| 右 | [1,0,0] | Numpad 3 |
| 左 | [-1,0,0] | Ctrl+Numpad 3 |
| 顶 | [0,1,0] | Numpad 7 |
| 底 | [0,-1,0] | Ctrl+Numpad 7 |
| 透视 | [0.7,0.5,0.7] | Numpad 5 |

通过 `ViewPresetListener`（R3F 内部组件）监听 `moldgen:view-preset` 事件实现相机切换。

---

## 18. Phase 2.5 算法与交互优化 (v4/v5)

### 18.1 模具壳体生成 — 根本性重构 (v5)

#### 根因分析

旧管线使用 **"先减后切"** 流程:

```
solid = outer_box - cavity      ← 布尔运算得到壁体
upper = slice_plane(solid, cap=True)   ← 切分 + 封帽
lower = slice_plane(solid, cap=True)
seal_parting_plane_gaps(upper)  ← 二次封盖
```

**Bug 1 — 腔体被封闭**: `slice_plane(solid, cap=True)` 在分型面创建封帽。壁体横截面是环形
(外方框 + 内腔轮廓), 但 trimesh 的 cap 做简单三角化, 把整个截面(含腔体开口)全部填满。
`_seal_parting_plane_gaps` 又做了二次封盖, 彻底堵死腔体。

**Bug 2 — 方形外壳不可见**: 布尔 `outer_box - cavity` 经常失败(manifold3d 未安装或输入非水密),
回退到 `_build_direct_shells` 使用 `trimesh.concatenate` 拼合面片(非流形), 或 `_build_shells_voxel`
通过 marching cubes 后再用同一个有缺陷的切分+封盖管线, 产生相同问题。

#### 新管线: "先切后减" (Slice-Then-Subtract)

```
outer_upper = slice_plane(outer_box, parting_plane, cap=True)  ← 简单凸切割, cap 正确
outer_lower = slice_plane(outer_box, parting_plane, cap=True)
shell_upper = outer_upper - cavity   ← 布尔减去完整腔体
shell_lower = outer_lower - cavity   ← 分型面处腔体自然敞开
```

**为什么这样修复**:
1. 切分对象是 outer_box (简单凸体), `slice_plane(cap=True)` 生成的是简单矩形封帽, 无环形问题
2. 布尔 `half_box - cavity` 的结果在分型面处自然留下腔体开口 (布尔移除了腔体内部)
3. 不需要 `_seal_parting_plane_gaps` — 腔体印迹保持敞开

#### 三级策略

| 策略 | 方法 | 分型面处理 |
|------|------|------------|
| S1 主路径 | `_build_shells_slice_then_subtract`: 切分 outer → 布尔减 cavity | 布尔自然保留腔体开口 |
| S2 体素回退 | `_build_shells_voxel`: 在分型面高度分割体素网格, 对每半独立 marching cubes | 每半自然有一面开口 |
| S3 直接拼合 | `_build_direct_shells`: 半盒 + 反转腔体半面拼合 | 几何拼合 |

#### `_safe_slice` 改进

新增 `cap` 参数 (默认 True). 在切分壁体时用 `cap=False` 防止封闭腔体:

```python
def _safe_slice(mesh, origin, normal, *, cap=True):
    cap_order = (True, False) if cap else (False, True)
    ...
```

### 18.1.1 浇注口/排气口自适应深度修复 (v5.1)

**问题**: `_cut_holes_in_shells` 中圆柱高度使用 `shell_extent_along_dir * 2.0` (整个模具沿方向的全长×2),
导致浇注口和排气口穿透了模具另一侧。

**根因**: 高度计算基于所有壳体的总范围而非单个壳体的壁厚。对于分型面两侧的两片壳体, 该值远超实际壁厚。

**修复**:
- 圆柱高度改为**按壳体自适应**: `min(shell_h_range + 2mm, (wall + margin) * 3)`
- 下限保护: `max(cyl_height, wall_thickness * 2)` 确保至少穿透壁体
- 增加壳体归属检查: 只在浇注口所在侧的壳体上切孔, 防止切到对侧壳体

### 18.1.2 分型面样式修复 (v5.1)

**问题**: 重构为 "先切后减" 管线后, `_split_solid_to_shells` 不再是主路径, 导致其中的
`_apply_parting_interlock` 分型面样式逻辑(dovetail/zigzag/step/tongue_groove)被旁路。

**根因**: 在重构 `build_two_part_mold` 时, 新的 `_build_shells_slice_then_subtract` 直接生成壳体,
绕过了原来包含分型面逻辑的 `_split_solid_to_shells`. 重构只关注了壳体形状和腔体开口,
遗漏了分型面互锁特征这个下游步骤。

**修复**:
- 新增 `_apply_parting_interlock_to_shells` 方法: 接受已生成的壳体列表, 提取上下壳体 trimesh,
  调用 `_create_parting_interlock` 或 `_displace_parting_verts`, 返回更新后的壳体
- 在 `build_two_part_mold` 的壳体修复后、拔模角检查前插入分型面样式应用步骤

### 18.2 仿形支撑板改进

**问题**: `_conformal_base_grid` 使用 `cKDTree` 查最近顶点, 而非最近表面点, 导致:
- 粗糙网格上投影不精确
- 板面跳变/不连续

**修复**:
- 改用 `trimesh.nearest.on_surface(grid_3d)` — 返回精确的面上最近点 + 面法线
- 添加边界缝合 (boundary stitching): 遍历有效网格边界, 在 inner/outer 表之间插入三角面, 使板片趋近水密

### 18.3 浇注系统算法增强

新增功能:

| 特性 | 实现 |
|------|------|
| **多浇口** | `_place_secondary_gates` — 最远点贪心布置, 与主浇口及已有浇口保持最大间距 |
| **流道路径** | `_compute_runner_paths` — 单浇口: 直通 sprue→gate; 多浇口: 星形/H 型从中心 sprue 分配; 排气孔: 短通道连接最近浇口 |
| **流道几何** | `_build_runner_meshes` — 长方体通道网格, 带正确的旋转/平移 |
| **运行器类型** | `GatingConfig.runner_type` ("cold"/"hot") 和 `n_gates` 参数现在通过 API 传递到后端 |

数据结构扩展:
- `RunnerSegment` 数据类: `start`, `end`, `width`, `depth`
- `GatingResult` 新增: `gates`, `runners`, `gate_meshes`, `runner_meshes` 字段

### 18.4 视口交互系统

**对象选择**: 点击 3D 视口中的模型/壳体 → `viewportStore.selectedObject` 更新 → 右侧面板自动切换到"属性"标签并显示选中对象的详细信息

| 组件 | 功能 |
|------|------|
| `ModelViewer` | 点击 → 选中模型, 显示网格信息 |
| `MoldShellViewer` | 点击 → 选中壳体, 显示面片/拔模角/可打印性 |
| `SelectedObjectInspector` | 右侧面板顶部浮动卡片, 显示选中对象参数 |
| `VisibilityToggles` | 视口右上角悬浮面板, 快速切换模型/模具/支撑可见性和透明度 |

### 18.5 `viewportStore` 扩展

新增字段:

```typescript
selectedObject: SelectedObject | null;
selectObject: (obj: SelectedObject | null) => void;

interface SelectedObject {
  type: "model" | "mold_shell" | "insert" | "gating" | "simulation" | null;
  id?: string | number;
  label?: string;
}
```

---

## 19. Phase 3 — 螺栓固定系统 + UI 布局优化 (v6)

### 19.1 螺栓固定系统 (M1-M8)

为平面分型的两片壳模具提供可靠的机械固定方案，参考专业注塑/翻模模具的紧固设计。

#### 19.1.1 M_SCREW_TABLE

预置 ISO 标准螺丝参数表，覆盖 M1 ~ M8 规格：

```python
M_SCREW_TABLE: dict[str, dict[str, float]] = {
    "M1":   {"through": 1.2, "tap": 0.85, "head": 2.0,  "nut": 2.5,  "nut_h": 0.8},
    # ... M1.6 / M2 / M2.5 / M3 / M4 / M5 / M6 / M8
}
```

| 参数 | 说明 |
|------|------|
| `through` | 通孔直径 (自由配合) |
| `tap` | 攻丝孔直径 |
| `head` | 螺栓头/沉头孔直径 |
| `nut` | 螺母外径 |
| `nut_h` | 螺母高度 |

#### 19.1.2 MoldConfig 新增字段

```python
# 螺栓固定系统 (凹槽 + 螺丝台 设计)
add_screw_holes: bool = False
screw_size: str = "M4"           # M1 / M1.6 / M2 / M2.5 / M3 / M4 / M5 / M6 / M8
n_screws: int = 4
screw_counterbore: bool = True   # 沉头孔
screw_tab_thickness: float = 5.0 # 分型面两侧保留的螺丝台厚度 (mm)

# 箍套夹具
add_clamp_bracket: bool = False
clamp_width: float = 15.0
clamp_thickness: float = 3.0
clamp_screw_size: str = "M3"
n_clamp_screws: int = 4
```

> **v6.2**: 移除了法兰 (flange) 功能，由凹槽+螺丝台方案完全替代。

#### 19.1.3 `_generate_screw_holes` 方法 — 凹槽+螺丝台设计

**核心设计**：参考专业模具软件，在四角（或边中点）从壳体外表面向下切除矩形凹槽
(pocket)，仅在分型面两侧保留 `screw_tab_thickness` 厚度的螺丝台 (tab)，
再在螺丝台上钻通孔。使用短螺栓（≈ 2 × tab_thickness）即可紧固。

截面示意 (单角)：

```
    ┌────────────────┐  壳体外表面
    │    pocket      │  ← 矩形凹槽 (布尔减法)
    │                │
    ├────┐      ┌────┤
    │    │ tab  │    │  ← screw_tab_thickness
    ├────┤      ├────┤  ← 分型面
    │    │ tab  │    │  ← screw_tab_thickness
    ├────┘      └────┤
    │                │
    │    pocket      │
    └────────────────┘
```

算法流程：

1. 构建正交基: `u_ax`, `v_ax` 在分型面上，`up` 为开模方向
2. 投影模型包围盒到 u/v 轴，获取 `half_u`, `half_v`
3. 在壁厚中点放置螺丝位: `wall_mid = (clearance + margin + wall_thickness) / 2`
4. 角落/边中点位置构建 (`corners` → `edge midpoints`)
5. 安全距离校验: `tm_model.nearest.on_surface()` 排除距型腔过近的位置
6. **对每个壳体、每个位置**:
   - **Step 1 — 凹槽**: `_make_oriented_box()` 创建世界坐标系盒体，从外表面切到 `center_h ± tab`
   - 若 box 布尔失败，自动降级为 `_make_cylinder()` 圆柱凹槽
   - **Step 2 — 通孔**: 小直径圆柱穿过螺丝台
   - **Step 3 — 沉头孔**: 在凹槽底面为螺栓头/螺母预留座面
7. 修复网格

**关键辅助函数 `_make_oriented_box()`**：
直接在世界坐标系计算 8 个顶点坐标（绕过 `trimesh.creation.box()` + `apply_transform`
的兼容性问题），使用验证过的 CCW 面绕向，确保 manifold3d 布尔引擎可靠接受。

**v6.2 改进**：
- 凹槽+螺丝台设计替代全高通孔，使标准短螺丝 (M4×10) 即可紧固
- `_make_oriented_box()` 替代 `trimesh.creation.box()+apply_transform` 解决布尔失败
- 增加圆柱凹槽后备确保 100% 鲁棒
- 移除法兰功能，简化为单一紧固方案

**v6.3 修复 — 凹槽薄壁问题**：
- **问题**: `pocket_xy` 被 `avail_wall - 1.0` 限制，凹槽外边缘在外壁面内侧 ~0.8mm
  处停止，留下了对 3D 打印有害的薄壁结构
- **修复**: `pocket_xy = max(head*2.5, avail_wall + 4.0)`，凹槽超过外壁面 2mm，
  布尔减法自动忽略超出壳体的部分
- **修复**: 螺丝孔生成后的修复步骤移除了 `fill_holes` 调用——该函数会将凹槽
  产生的开放面误判为"需要修复的洞"并封闭它们，等于把凹槽填回去了
- 详见 `docs/11-adaptive-parting.md` 中的自适应分型面系统设计

#### 19.1.4 `_generate_clamp_brackets` 方法

算法流程：

1. 在分型面外围均匀分布 `n_clamp_screws` 个箍套位置
2. 每个箍套为 C 形结构：外盒减去内盒 (U 形通道包裹分型线)
3. 箍套上下各打一个紧固螺丝通孔 (clamp_screw_size)
4. 输出独立 mesh，用于单独 3D 打印

### 19.2 UI 布局优化

#### 19.2.1 左侧面板精简 (v6.1)

将所有分析结果数据**完全移除**——不保留任何摘要或提示文字。

左侧面板仅保留：
- 操作按钮（分析、生成、验证）
- 参数控制（滑条、下拉选择、开关）
- 状态徽标（StatusBadge 绿/灰点）
- 步骤提示（StepHint 前往下一步）

**已移除的数据区域**：
- 方向分析结果（评分、方向向量、候选数）
- 分型面结果（分型线数、面数）
- 模具壳体详情（壳体表格、浇注口评分、排气口列表、定位销）
- 成本估算面板
- 支撑板详情（板片列表、锚固信息）
- 装配验证结果（消息列表）
- 浇注系统设计结果（评分、流道平衡、型腔体积等）
- 仿真结果（充填率条、缺陷分组、时间/压力/温度）
- 优化结果（收敛状态、迭代、充填改善）
- FEA 结果（位移、应力、安全系数）

#### 19.2.2 右侧 "大纲" 标签扩展

在 SceneManager（场景大纲）下方新增 `AnalysisDataSection` 组件：

```
┌─ 右侧面板 ─────────────────┐
│ [大纲] [属性] [统计]         │
│                              │
│ ┌─ 场景大纲 ──────────────┐ │
│ │ · 模型                  │ │
│ │ · 壳体 #0 / #1          │ │
│ │ · 支撑板                │ │
│ │ · 浇注系统              │ │
│ └────────────────────────┘ │
│                              │
│ ── 分析数据 ──               │
│ ▸ 方向分析  [82%]            │
│ ▸ 分型面                     │
│ ▸ 模具壳体  [2 壳]           │
│ ▸ 支撑板    [2 板]           │
│ ▸ 浇注系统  [91%]            │
│ ▸ 仿真结果  [99%]            │
│ ▸ 优化结果                   │
└──────────────────────────────┘
```

每个分析数据 section 默认折叠，带 badge 摘要，展开显示完整数据。

#### 19.2.3 新增 UI 控件（左侧 MoldPanel）

| 控件 | 说明 |
|------|------|
| 螺栓固定孔 开关 | 启用/禁用凹槽+螺丝台紧固 |
| 螺丝规格 下拉 | M1 ~ M8 标准规格选择 |
| 数量 按钮组 | 2 / 4 / 6 / 8 |
| 螺丝台厚度 滑块 | 2 ~ 15 mm (默认 5mm) |
| 沉头孔 开关 | 是/否 |
| 分型面箍套 开关 | 启用/禁用箍套生成 |
| 箍套螺丝 下拉 | M2 ~ M6 |
| 箍套数量 按钮组 | 2 / 4 / 6 |

### 19.3 API 变更

`POST /{model_id}/mold/generate` 新增请求字段：

```json
{
  "add_screw_holes": true,
  "screw_size": "M4",
  "n_screws": 4,
  "screw_counterbore": true,
  "screw_tab_thickness": 5.0,
  "add_clamp_bracket": false,
  "clamp_width": 15.0,
  "clamp_thickness": 3.0,
  "clamp_screw_size": "M3",
  "n_clamp_screws": 4
}
```

响应新增字段：

```json
{
  "screw_holes": [
    { "position": [x,y,z], "screw_size": "M4", "through_diameter": 4.5, ... }
  ],
  "clamp_brackets": [
    { "face_count": 120, "screw_positions": [[x,y,z], ...] }
  ]
}
```

---

## 20. Phase 4 — 自适应分型面系统 (v5 → v4.0 修复)

> 详细设计文档见 [11-adaptive-parting.md](./11-adaptive-parting.md)

### 20.1 Phase 1 — Undercut 检测 + 高度场分型面

- `UndercutAnalyzer`: 射线投射 undercut 检测, 深度量化, 严重度分级
- `_build_heightfield_surface()`: 射线投射取上下边界中点的非平面分型面
- 自动选择: 分型线非共面 → heightfield, 否则 → flat

### 20.2 Phase 2 — 投影分型面 + 侧抽 + 热力图

**侧抽方向推荐** (`recommend_side_pulls()`):
- 基于 undercut 面法线的 SVD 聚类 + 基准方向
- 评估每个候选方向的覆盖率 (面法线可见性 + 遮挡轴夹角判定)
- 输出 `SidePullDirection` 列表 (方向、覆盖率、与主拉夹角)

**投影拉伸分型面** (`_build_projected_surface()`):
- 从分型线径向外延, 每步等距拉伸
- 高度渐变: 外环高度从分型线高度线性混合到默认高度 (v4.0 改进)
- 回退: 生成失败则回退到 heightfield

**Undercut 热力图**:
- `export_undercut_heatmap()`: 导出 per-face 深度数据
- API: `GET /{model_id}/undercut/heatmap`
- 前端: `UndercutOverlay.tsx` 使用蓝→红渐变渲染

### 20.3 Phase 2.5 — 模具分割集成 + Bug 修复 (v4.0)

**v4.0 Bug 修复**:
- 严重度分级: `or` → `and` (ratio=0.50, depth=5 不再被误判为 moderate)
- 分型面命名: "分型面样式" → "锁扣样式" (消除与"分型面类型"的混淆)
- 高度场边界: 添加渐变约束，边缘平滑过渡到默认高度
- 射线循环: `np.minimum.at` / `np.maximum.at` 替代 Python 循环

**MoldBuilder 自适应分割** (`_build_shells_adaptive_surface()`):
- 当 `parting_surface_type` 不为 "flat" 时自动启用
- 通过 `scipy.spatial.cKDTree` 将 outer shell 顶点按分型面高度分配到上下半壳
- 自动回退: 分割失败则使用平面切割
- `MoldResult` 包含 `parting_surface_type`, `undercut_severity`

### 20.4 API 变更

```
POST /{model_id}/parting       — 新增 surface_type, heightfield_resolution, undercut_threshold
POST /{model_id}/undercut      — 独立 undercut 分析
GET  /{model_id}/undercut/heatmap — 热力图数据
POST /{model_id}/mold/generate — 新增 parting_surface_type; 响应含 undercut_severity
```

### 20.5 前端变更

- 分型面类型选择器: 自动 / 平面 / 高度场 / 投影拉伸
- "查看 Undercut 热力图" 按钮 + `UndercutOverlay.tsx` 3D 叠加层
- 模具结果显示 undercut 严重度 + 分型面类型
- 场景管理器新增 "Undercut 热力图" 节点 (analysis 类型)
- Store: `UndercutHeatmapData`, `SidePullDirection`, heatmap 状态
- Hook: `useUndercutHeatmap()`, `useUndercutAnalysis()`
- 全局字体: 7-10px → 11-12px

---

## 21. Phase 6 — 内骨骼模型3D打印兼容性修复 (v6.2)

### 21.1 问题描述

生成的内骨骼(insert)支撑板模型在3D打印切片软件(BambuStudio)中出现以下问题:
- **空层警告**: "模型在0.8和1.6之间出现空层，无法打印"
- **浮空区域警告**: "似乎对象insert_plate_0.stl有浮空区域"

### 21.2 根因分析 (6个问题)

| # | 问题 | 严重度 | 组件 | 影响 |
|---|------|--------|------|------|
| 1 | **面删除式孔洞缺少孔壁** | 致命 | `_carve_holes`, `_face_removal_mesh_holes` | 删除面后留下开放边界，网格不封闭 → 切片器无法确定体积 → 空层 |
| 2 | **仿形板边界缝合有bug** | 严重 | `_conformal_base_grid` 的 stitch 循环 | `pass` 空操作 + 错误的邻居计算 → 内外表面边界未完全封闭 → 浮空区域 |
| 3 | **肋条拼接使用concatenate** | 中等 | `_apply_ribs` | 三棱柱与板通过 `concatenate` 合并而非布尔并集 → 非流形(non-manifold)几何 |
| 4 | **回退板厚度仅0.1mm** | 中等 | `_generate_fallback_plate` | 低于标准层高(0.2mm) → 切片器产生空层 |
| 5 | **无网格修复步骤** | 中等 | 全流程 | `_clean_mesh` 仅清理退化面，不修复法线/填充孔洞；`MeshData.to_trimesh()` 使用 `process=False` |
| 6 | **导出缺少支柱网格** | 低 | `export.py` | STL导出只包含 `plate.mesh`，不含 `plate.pillar_mesh` |
| 7 | **`process=True` 破坏仿形板拓扑** | 致命 | `_conformal_base_grid` | `process=True` 的 `merge_vertices` 合并近重复顶点，破坏缝合面索引 → 网格不封闭 |
| 8 | **退化面移除破坏缝合** | 严重 | `_clean_mesh` | 仿形板的缝合三角面可能退化（零面积），但对拓扑连接至关重要，移除后重新打开边界 |
| 9 | **布尔运算缺少水密验证** | 严重 | `_manifold_subtract/_manifold_union` | manifold3d 布尔结果仅检查面数(>4)，不验证水密性 → 非水密结果被误当作成功 |
| 10 | **肋条/孔洞操作顺序** | 中等 | `generate_plate` | 先打孔再加肋条，导致布尔并集在复杂网格上失败；应先加肋条(简单几何)再打孔 |

### 21.3 修复措施

#### 21.3.1 新增 `_repair_mesh()` 综合修复函数

替代仅做简单清理的 `_clean_mesh`，新函数执行完整的网格修复流程:

```python
def _repair_mesh(mesh, *, fill=True):
    # 1. 合并近距顶点 (merge_vertices)
    # 2. 清除退化面 (nondegenerate_faces)
    # 3. 删除孤立顶点 (remove_unreferenced_vertices)
    # 4. 修复法线/缠绕方向 (fix_normals + fix_winding)
    # 5. 填充孔洞 (fill_holes) — 可选
    # 6. 最终法线一致性检查
```

#### 21.3.2 仿形板边界缝合重写

原 stitch 循环存在3个缺陷:
- `pass` 空操作没有实际功能
- `nxt_r, nxt_c = r + abs(dc), c_i + abs(dr)` 邻居计算混淆了行列方向
- 仅处理部分边界方向

新实现对4个方向分别处理 (右/左/下/上)，确保所有边界边都被正确缝合:

```python
# 每个有效网格点检查4个邻居方向
# 若邻居无效(出界或无效点)，则该边为边界
# 在该边界上创建两个三角面连接inner和outer表面
```

#### 21.3.3 孔洞生成策略优化

修改 `_add_mesh_holes` 的策略优先级:
1. **板片水密 → 布尔减法** (精确，保持封闭)
2. **板片非水密 → 先修复再布尔** (新增路径)
3. **布尔失败 → 面删除 + fill_holes封闭边界** (兜底方案)

面删除后调用 `_stitch_hole_boundaries` → `fill_holes` + `fix_normals` + `fix_winding`

#### 21.3.4 肋条使用布尔并集

`_apply_ribs` 在板片水密时使用 `_manifold_union` 合并肋条，避免 `concatenate` 产生的非流形几何:

```python
if plate_mesh.is_watertight:
    merged = _manifold_union(plate_mesh, rib_mesh)
    if merged is not None:
        return merged
# 否则 fallback 到 concatenate + _repair_mesh
```

#### 21.3.5 回退板厚度修正

`_generate_fallback_plate` 主轴维度从 `0.1` 改为 `max(config.thickness, 1.0)`，保证至少 1.0mm 可打印厚度。

#### 21.3.6 生成管道终端修复

`generate_plate` 返回前增加终端修复:

```python
_repair_mesh(plate_mesh)
if not plate_mesh.is_watertight:
    # 尝试 aggressive fill
    trimesh.repair.fill_holes(plate_mesh)
    trimesh.repair.fix_normals(plate_mesh, multibody=True)
```

#### 21.3.7 导出管道修复

- `MeshData.to_glb()`: 导出前执行 `process(validate=True)` + `fix_normals` + `fill_holes`
- `export_insert` (STL导出): 每个板片导出前执行完整修复
- 新增: 支柱网格(`pillar_mesh`)也被包含在导出ZIP中

#### 21.3.8 仿形板 `process=False` + 保留退化面

根因: `process=True` 调用 `merge_vertices()` 将近重复顶点合并，破坏了缝合面的顶点索引。
对于box模型的仿形板，580对近重复顶点被合并 → 拓扑完全破坏。

修复: 使用 `process=False` 创建网格，仅调用 `fix_normals` (非破坏性)。
退化面(零面积缝合三角形)对拓扑连接至关重要，仅在退化面占比>50%时回退到平板。

#### 21.3.9 布尔运算水密性验证

`_manifold_subtract` 和 `_manifold_union` 的结果检查从 `len(faces) > 4` 
增强为 `len(faces) > 4 and is_watertight`，防止非水密的布尔结果被误当作成功。

#### 21.3.10 肋条/孔洞操作顺序

将 `generate_plate` 中平板类型的特征应用顺序从"先孔洞后肋条"改为"先肋条后孔洞"。
肋条的布尔并集在简单几何(未打孔的板)上成功率更高。

### 21.4 修改文件清单

| 文件 | 修改类型 |
|------|----------|
| `moldgen/core/insert_generator.py` | 新增 `_repair_mesh`, 重写 stitch 循环, 修复孔洞/肋条/回退板/终端修复 |
| `moldgen/core/mesh_data.py` | `to_glb()` 增加导出前修复 |
| `moldgen/api/routes/export.py` | 导出前修复 + 包含支柱网格 |

---

## 22. 表面网孔生成修复 (v2.1)

### 22.1 问题现象

修复内骨骼水密性问题(§21)后，表面网孔（mesh holes）在仿形板（conformal）等类型上无法正常生成。用户在3D视口中看到的板片缺少预期的孔洞图案。

### 22.2 根因分析

#### 核心矛盾：`fill_holes` 与面删除式孔洞的冲突

§21的修复为确保水密性，在**4个位置**引入了 `trimesh.repair.fill_holes()` 调用：

| 位置 | 函数 | 调用方式 |
|------|------|----------|
| 1 | `_stitch_hole_boundaries()` | `fill_holes(mesh)` |
| 2 | `_generate_conformal()` 末尾 | `_repair_mesh(plate)` → `fill_holes` |
| 3 | `generate_plate()` 终端修复 | `_repair_mesh(plate_mesh)` → `fill_holes` |
| 4 | `generate_plate()` aggressive fill | `fill_holes(plate_mesh)` |

**关键区别：**

| 板类型 | 孔洞创建方式 | fill_holes 影响 |
|--------|------------|----------------|
| 扁平板 (Flat) | **布尔减法**（圆柱减去实体）→ 贯穿孔有壁面几何 | 无开放边界，不受影响 ✅ |
| 仿形板 (Conformal) | **面删除**（删除面→留开口）→ 贯穿孔无壁面 | fill_holes 将孔洞填回 ❌ |

面删除创建的开口在 `fill_holes` 看来就是"需要修复的孔洞"，被全部填回封闭。

#### 次要问题：`_manifold_subtract` 过度严格

§21添加的 `is_watertight` 检查拒绝了有效的布尔减法结果（浮点精度导致的边界误判），使 `_boolean_mesh_holes` 也失效。

### 22.3 修复措施

#### 22.3.1 仿形板改用布尔减法创建孔洞

`_carve_holes` 重新设计为双路径架构：

**主路径（新增 `_boolean_carve_holes`）：**
- 将UV坐标孔洞位置转换为3D坐标
- 在每个孔位创建匹配形状的切割体（圆形→圆柱，网格→立方体，菱形→4边柱）
- 沿板片局部法线对齐切割体
- 使用 manifold3d 布尔减法逐个切割
- 结果是水密闭合几何，`fill_holes` 不会影响

**回退路径（保留面删除）：**
- 仅在布尔引擎不可用或板片非水密时触发
- 不再调用 `_stitch_hole_boundaries`（不尝试 fill 回去）

#### 22.3.2 修复链条件化

所有 `fill_holes` 调用改为条件执行：

```python
# _generate_conformal 末尾
_repair_mesh(plate, fill=not integrate_holes)

# generate_plate 终端修复
has_face_removal_holes = "mesh_holes" in features and not is_watertight
_repair_mesh(plate_mesh, fill=not has_face_removal_holes)
```

#### 22.3.3 布尔减法放宽验证

`_manifold_subtract` 的返回检查从 `len(faces) > 4 and is_watertight` 恢复为 `len(faces) > 4`，因为：
- manifold3d 产生的布尔结果几何正确但可能因浮点精度被 trimesh 判定为非水密
- 该函数是孔洞切割的**主路径**，不应因精度问题拒绝有效结果

注意：`_manifold_union`（肋条合并）保留 `is_watertight` 检查，因为并集结果的水密性更关键。

#### 22.3.4 仿形板 fallback 时也应用孔洞

当仿形板网格退化（如box模型太平坦）回退到扁平板时，现在会正确应用布尔减法孔洞，而非返回无孔的板片。

### 22.4 验证结果

| 模型 | 板类型 | 面数 | 水密 | 孔洞 |
|------|--------|------|------|------|
| Sphere | flat | 2,938 | ✅ | ✅ |
| Sphere | conformal | 119,566 | ✅ | ✅ |
| Sphere | ribbed | 4,510 | ❌* | ✅ |
| Sphere | lattice | 2,936 | ✅ | ✅ |
| Box | flat | 2,524 | ✅ | ✅ |
| Box | conformal (fallback) | 2,532 | ✅ | ✅ |
| Box | ribbed | 2,524 | ✅ | ✅ |
| Box | lattice | 2,540 | ✅ | ✅ |

*ribbed 板因50次连续布尔减法的浮点误差累积导致 trimesh 判定非水密，但实际几何正确。

### 22.5 错误原因总结

**根本原因：** §21的修复追求"绝对水密性"，在所有路径上强制调用 `fill_holes`。这对布尔减法式孔洞（有壁面几何）无害，但对面删除式孔洞（无壁面几何）是毁灭性的——`fill_holes` 将刻意创建的开口全部填回。这是一个**修复引入的回归bug**：修复A（水密性）破坏了功能B（孔洞生成）。

正确的架构是让孔洞始终通过布尔减法创建（产生自带壁面的贯穿孔），这样水密性和孔洞生成不再矛盾。

---

## 23. 仿形板/晶格/网孔生成逻辑完善 (v2.2)

### 23.1 审查发现的问题

| # | 问题 | 严重度 | 修复 |
|---|------|--------|------|
| 1 | `InsertType.LATTICE` 未接入 `_generate_lattice`，实际只生成 flat+holes | 中等 | 接入真正的晶格生成器 |
| 2 | `_generate_lattice` 忽略 `lattice_type` 配置（只有 SC） | 中等 | 实现 BCC/FCC 对角线支撑 |
| 3 | 扁平板忽略 `hole_pattern` 配置，使用随机采样 | 中等 | 新增 `_apply_pattern_holes`，统一使用 `_hole_layout` |
| 4 | 仿形板 fallback 到 flat 时丢失孔洞（当 flat 非水密） | 严重 | 添加 `_repair_mesh` 后再打孔 |
| 5 | 300个孔洞的连续布尔减法浮点误差累积导致非水密 | 中等 | 批量布尔减法（先合并切割体再一次性减） |
| 6 | `saved_max` 死代码 | 低 | 移除 |
| 7 | `_add_mesh_holes` 文档与实现不一致 | 低 | 更新文档字符串 |

### 23.2 修复内容

#### 23.2.1 晶格结构完善

`InsertType.LATTICE` 现在调用真正的 `_generate_lattice` 而非 flat+holes。支持三种晶格类型：

| 类型 | 描述 | 支撑数 |
|------|------|--------|
| `sc` | 简单立方 — 仅轴向支撑 | 少 |
| `bcc` | 体心立方 — SC + 体对角线 | 中 |
| `fcc` | 面心立方 — SC + 面对角线 | 多 |

晶格网格上限从120提升到300支撑，分辨率上限从6×6×2扩展到10×10×3。生成后自动进行 `_repair_mesh` 和可选 `_voxel_repair` 以确保水密性。

#### 23.2.2 扁平板支持 hole_pattern

新增 `_apply_pattern_holes` 方法，使扁平板也能使用配置的孔洞图案（hex/grid/diamond/voronoi/TPMS），而不是之前的随机最远点采样。使用与仿形板相同的 `_hole_layout` → `_boolean_carve_holes` 管道。

#### 23.2.3 批量布尔减法优化

`_boolean_carve_holes` 和 `_boolean_mesh_holes` 改为"先合并所有切割体，再一次性减法"策略：

- **性能提升**: 300个孔洞从 ~20秒降低到 ~0.4秒
- **精度提升**: 避免了连续减法的浮点误差累积
- **回退机制**: 批量失败时自动切换到逐个减法

### 23.3 验证结果

| 模型 | 板类型 | 面数 | 特征 | 耗时 |
|------|--------|------|------|------|
| Sphere | flat | 15,026 | mesh_holes | 0.4s |
| Sphere | conformal | 135,388 | mesh_holes | 7.0s |
| Sphere | lattice (bcc) | 9,600 | lattice ✅水密 | 0.3s |
| Box | flat | 14,290 | mesh_holes | 0.4s |
| Box | conformal→flat | 2,544 | mesh_holes ✅水密 | 0.1s |
| Box | lattice (bcc) | 9,600 | lattice ✅水密 | 0.2s |

晶格类型测试：SC(6944面) / BCC(9600面) / FCC(9600面) 全部水密。

---

## 24. 浇注口未到达模具外表面修复 (v2.3)

### 24.1 问题现象

浇注口生成后，在可视化界面中浇注口通道未到达模具外表面，导致无法从外部向模具灌注材料。

### 24.2 根因分析

#### 浇注口位置基于模型边界而非模具壳体边界计算

原代码在计算浇注口高度时使用了**模型的 AABB 边界**：

```python
top_height = float(bounds[1] @ up) + 5.0  # model_top + 5mm
```

但模具外表面实际在 `model_top + clearance + margin + wall_thickness`（默认 +14.3mm）处。

| 项目 | 高度 | 差距 |
|------|------|------|
| 模型顶部 | 70.0 mm | — |
| **浇注口位置** | **75.0 mm** | 模型顶部 + 5 |
| 可视化圆柱顶部 | 84.0 mm | 浇注口 + 9 |
| **模具外表面** | **84.3 mm** | 模型顶部 + 14.3 |

可视化圆柱差 **0.3mm** 无法到达模具外表面。虽然布尔切割圆柱足够长（能穿过），但浇注口的**物理位置**不在入口处，可视化也无法反映正确的通道。

#### 排气孔切割高度沿错误轴计算

排气孔的切割圆柱高度使用 `direction`（模具开合方向）而非排气孔的**法线方向**计算 `shell_h_range`，导致沿排气法线方向的通道可能太短或太长。

#### 切割圆柱高度上限过低

原 `cyl_height` 上限为 80mm，对于大型模具可能不够。加上旧的 +4mm 余量也过小。

### 24.3 修复措施

#### 24.3.1 浇注口位置基于模具壳体边界

新增 `_mold_outer_height()` 方法获取上半壳体沿 `up` 方向的最大高度：

```python
outer_h = self._mold_outer_height(mold, up)
top_height = max(outer_h, model_top + 5.0) + 2.0
```

浇注口现在位于模具外表面上方 2mm 处，确保通道完全贯穿模具壁。

#### 24.3.2 可视化网格覆盖全通道

`_build_gate_mesh` 的圆柱高度从固定值改为基于实际距离计算：

```python
height = max((outer_h - gate_h) * 2 + 8.0, gate_diameter * 1.5, 20.0)
```

#### 24.3.3 排气孔切割沿正确轴向

排气孔的切割高度现在沿**排气法线方向**投影壳体顶点来计算，而非固定使用模具开合方向。

#### 24.3.4 切割余量增大

切割圆柱余量从 +4mm 增加到 +10mm，上限从 80mm 提高到 120mm。

### 24.4 修复后验证

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 浇注口位置 | 75.0 mm (模型+5) | **86.3 mm** (模具表面+2) |
| 可视化顶部 | 84.0 mm (**差0.3mm**) | **96.3 mm** (超出12mm) ✅ |
| 到达模具外表面 | **NO** | **YES** ✅ |

### 24.5 错误原因

设计浇注口位置时，开发者假设"模型顶部 + 5mm"足够到达模具外表面。但模具外壳的构建使用了 `clearance + margin + wall_thickness`（默认 14.3mm）的偏移量，远超 5mm。浇注口位置和可视化网格都基于这个错误的假设，导致通道无法贯穿模具壁。正确的做法是直接查询模具壳体的实际几何边界来确定浇注口入口位置。

---

## 25. 全面代码审计与修复 (v2.4)

### 25.1 审计范围

对项目后端核心模块（mold_builder、gating、parting、insert_generator、orientation）、API 路由层、前端组件/hooks/stores 进行了全面审计。

### 25.2 发现并修复的问题

#### 后端修复

| 编号 | 模块 | 问题 | 严重度 | 修复 |
|------|------|------|--------|------|
| B1 | mold_builder | `MoldConfig.add_pour_hole/add_vent_holes` 默认 `True` 但从未使用 | 高 | 默认改为 `False`，添加 deprecated 注释 |
| B2 | mold_builder | `build_two_part_mold` 零长度方向会产生 NaN | 高 | 添加 norm 检查，零向量回退到 [0,0,1] |
| B3 | mold_builder | 模块头部注释描述已过时的浇注口功能 | 中 | 更新为 v5 描述 |
| B4 | mold_builder | `_generate_flanges` 引用不存在的 MoldConfig 字段 | 严重 | 完全移除（已废弃功能） |
| B5 | mold_builder | `FlangeFeature` 类无调用者 | 中 | 移除死代码 |
| B6 | mold_builder | `self._scale_factor` 赋值但从未读取 | 低 | 移除死状态 |
| B7 | gating | `_boolean_subtract` 所有异常静默吞掉 | 高 | 添加 logger.debug/warning |
| B8 | gating | 非水密网格 `cavity_volume=0` 导致填充时间估算为零 | 高 | 回退到凸包体积 × 0.7 |
| B9 | gating | `_boolean_union` 死代码，无调用者 | 低 | 移除 |
| B10 | parting | `generate()` 零长度方向不保护 | 高 | 添加 norm 检查和回退 |
| B11 | parting | `UndercutAnalyzer` 射线异常静默返回 "none" | 中 | 添加 logger.warning |

#### 前端修复

| 编号 | 组件/模块 | 问题 | 严重度 | 修复 |
|------|-----------|------|--------|------|
| F1 | RightPanel/StatBar | `bg-${color}` 动态 Tailwind 类名不被 JIT 编译 | 高 | 改用静态映射 `BAR_COLORS` |
| F2 | ModelViewer | 每次 displayMode/opacity 变化创建新 Material 不 dispose | 高 | 添加 cleanup return，dispose 旧材质 |
| F3 | GatingViewer | BufferGeometry 不 dispose | 中 | 添加 useEffect cleanup |
| F4 | modelStore/clearModel | 不清理 moldStore/simStore/insertStore | 高 | 同步调用各 store 的 clear 方法 |
| F5 | insertStore | 缺少 `clearInserts` 方法 | 中 | 新增完整重置方法 |
| F6 | viewportStore | `shellOverrides` 在新模具生成时不清理 | 中 | 新增 `clearShellOverrides`，在 moldStore.clearMold 中调用 |
| F7 | moldStore/clearMold | 不重置 loading 标志位 | 中 | 清理 isAnalyzing/isGeneratingParting/isGeneratingMold |
| F8 | simStore/clearSim | 不重置 loading/running 标志位 | 中 | 清理 surfaceMapLoading/isDesigning*/isSimulating/feaRunning |
| F9 | useAgentExecute | 缺少 `res.ok` 检查，HTTP 错误被当成功处理 | 高 | 添加 res.ok 检查 + 中文错误信息 |
| F10 | useExportApi | 错误信息为英文 | 低 | 中文化所有错误提示 |
| F11 | useModelApi | 错误信息为英文 | 低 | 中文化所有错误提示 |

#### API / 前后端一致性修复

| 编号 | 问题 | 修复 |
|------|------|------|
| A1 | useMoldGeneration 发送已废弃的 pour/vent 参数 | 移除 addPourHole/pourHoleDiameter 等参数 |
| A2 | useRunOptimization 不更新优化后的 gatingId/simId | 读取 optimized_gating_id/optimized_sim_id 并更新 store |
| A3 | simStore 缺少 setGatingId/setSimId | 新增这两个方法 |
| A4 | models.py 中 thickness/curvature 与 analysis.py 重复 | 在 models.py 中标记 deprecated |

### 25.3 已知但保留的问题（低优先级）

| 问题 | 原因 |
|------|------|
| mold_builder 中遗留的 pour/vent 算法代码 | 供 hole-preview API 使用，暂不移除 |
| 布尔运算在三个模块中重复 | 需要统一到 core/boolean_ops.py，但改动范围大 |
| 填充时间估算为经验公式 | 物理精度有限，需要实验标定 |

---

## 26. 深度审计修复续 (v2.5)

### 26.1 后端修复

| 编号 | 模块 | 问题 | 修复 |
|------|------|------|------|
| B12 | mold_builder | `_build_shells_adaptive_surface` 中 `n_v`, `n_f`, `verts_top`, `verts_bot` 赋值但从未使用 | 移除死变量 |
| B13 | mold_builder | `cut_pillar_holes` 布尔运算异常被静默吞掉 | 改为 `logger.debug` |
| B14 | mold_builder | `_compute_pour_gate`/`_compute_vent_holes` 方向向量未归一化 | 入口处添加归一化 |
| B15 | mold_builder | `_repair_mesh` 所有修复步骤使用 bare `except: pass` | 全部改为 `logger.debug` |
| B16 | mold_builder | `_fallback_vents` 距离计算语义不清 | 统一为 `remaining + offset - p.position` |
| B17 | insert_generator | `_manifold_subtract`/`_manifold_union` 异常静默吞掉 | 添加 `logger.debug` |
| B18 | insert_generator | `_repair_mesh` 8 处 bare `except: pass` | 全部改为 `logger.debug` |
| B19 | insert_generator | `validate_assembly` 锚固缺失不影响验证结果 | 标记为警告消息（⚠），保持 all_valid 不变 |
| B20 | orientation | `n_top_candidates` 定义但未使用 | 接入 `_build_result` Phase 1 筛选 |

### 26.2 前端修复

| 编号 | 组件/模块 | 问题 | 修复 |
|------|-----------|------|------|
| F12 | useMoldApi | `useEvaluateDirection`、`useHolePreview`、`useMoldAnalysis` 导出但无组件使用 | 移除三个死 hook |
| F13 | useModelApi | `useThicknessAnalysis`、`useCurvatureAnalysis` 与 `useAnalysisApi` 重复 | 移除重复 hook |
| F14 | SceneManager | "Undercut 热力图" 中英混合标签 | 改为"底切热力图" |
| F15 | LeftPanel | `moldMaterial`/`surfaceTexture` UI 状态未发送到 API | 添加到 mutate 参数和请求体 |
| F16 | LeftPanel/completedSteps | 仅 import 和 repair 会 markStepCompleted | 在 orientation、mold 成功回调中也标记完成 |
| F17 | useMoldApi | `useMoldGeneration` 参数类型未包含 `moldMaterial`/`surfaceTexture` | 添加参数定义和请求体字段 |

---

## 27. 全面升级和完善计划 (v3.0 路线图)

### 27.1 架构层升级

#### Phase A: 核心基础 (优先级 P0)

| 功能 | 描述 | 涉及模块 | 预计工作量 |
|------|------|----------|-----------|
| **布尔运算统一层** | 将 mold_builder/gating/insert_generator 中重复的 manifold3d/trimesh 布尔逻辑抽取到 `core/boolean_ops.py`，统一错误处理和日志 | core/ | 2-3天 |
| **网格修复统一层** | 将 mold_builder._repair_mesh 和 insert_generator._repair_mesh 合并到 `core/mesh_repair.py`，提供分级修复策略 | core/ | 1-2天 |
| **会话持久化** | 后端工作流状态（模型ID、模具ID、浇注ID 等）持久化到 SQLite/JSON，重启不丢失 | api/, stores/ | 2天 |
| **错误恢复机制** | GPU OOM 自动降级到 CPU，网络断连自动重连，布尔运算失败自动尝试替代算法 | 全模块 | 2天 |

#### Phase B: 算法提升 (优先级 P1)

| 功能 | 描述 | 涉及模块 | 预计工作量 |
|------|------|----------|-----------|
| **自适应分型面 v2** | 基于模型曲率自适应网格密度，支持侧向抽芯路径自动规划 | parting.py | 3-4天 |
| **高级螺丝孔配置** | 支持更多螺丝规格（M10-M16），自定义位置拖拽放置，预览应力分布 | mold_builder.py, LeftPanel | 2天 |
| **物理填充仿真 v2** | 基于 Navier-Stokes 简化模型的流体仿真，替代当前经验公式 | gating.py, simulation | 4-5天 |
| **内骨架拓扑优化** | 基于有限元分析的内骨架结构优化，支持 SIMP/BESO 拓扑优化算法 | insert_generator.py | 3-4天 |
| **多材料模具支持** | 不同壳体部分使用不同材料参数（刚性/柔性/透明） | mold_builder.py, api/ | 2天 |

#### Phase C: 交互体验 (优先级 P1)

| 功能 | 描述 | 涉及模块 | 预计工作量 |
|------|------|----------|-----------|
| **视口内模型编辑** | 直接拖拽顶点/边/面，实时变形预览 | ModelViewer, Three.js | 4-5天 |
| **测量工具** | 距离、角度、面积、体积实时测量覆盖层 | Viewport | 2天 |
| **剖面视图** | 支持任意平面剖切模具，查看内部结构 | ModelViewer | 2天 |
| **撤销/重做系统** | 全局操作历史栈，支持 Ctrl+Z/Y | stores/ | 2天 |
| **拖拽布置浇注口/排气口** | 在3D视口中直接拖拽放置浇注口和排气口位置 | GatingViewer, LeftPanel | 2-3天 |

#### Phase D: 生产集成 (优先级 P2)

| 功能 | 描述 | 涉及模块 | 预计工作量 |
|------|------|----------|-----------|
| **切片软件集成** | 直接导出到 Cura/PrusaSlicer 并预览打印参数 | export.py, frontend | 3天 |
| **批量处理流水线** | 多模型队列：导入→方向分析→模具生成→导出 | api/, frontend | 3天 |
| **打印成本估算** | 基于材料密度、体积、打印时间的成本估算模块 | core/, frontend | 1天 |
| **项目版本管理** | 工作流快照和回滚，支持对比不同版本结果 | api/, stores/ | 3天 |
| **云端协作** | 多用户共享项目，评审和批注 | api/, 新模块 | 5天 |

#### Phase E: AI Agent 增强 (优先级 P2)

| 功能 | 描述 | 涉及模块 | 预计工作量 |
|------|------|----------|-----------|
| **Agent 交互面板** | 完整的对话式 AI 交互界面，支持进度条、暂停、确认 | ai/, frontend | 3天 |
| **智能参数推荐** | 基于模型特征自动推荐壁厚、分型面类型、螺丝配置等 | ai/agents/ | 2天 |
| **缺陷自动检测** | 扫描模具设计中的潜在问题（壁厚不足、脱模角不足等） | ai/agents/ | 2天 |
| **自然语言控制** | "把壁厚改成5mm"等自然语言指令直接操作参数 | ai/ | 2天 |

### 27.2 代码质量提升

| 领域 | 计划 |
|------|------|
| **单元测试** | 为 core/ 中每个模块添加 pytest 测试，目标覆盖率 > 80% |
| **集成测试** | 端到端测试：模型上传 → 模具生成 → 导出，验证完整流水线 |
| **类型安全** | 前端消除所有 `unknown`/`any` 类型转换，使用 Zod schema 验证 API 响应 |
| **性能基准** | 建立关键算法的性能基准测试，持续监控回归 |
| **文档生成** | 使用 Sphinx 自动生成 Python API 文档，Storybook 生成组件文档 |
| **CI/CD** | GitHub Actions 自动测试 + 构建 + 发布 Tauri 安装包 |

### 27.3 近期优先执行 (下一迭代)

1. **布尔运算统一层** — 消除三模块重复代码，统一错误处理
2. **网格修复统一层** — 合并重复的 `_repair_mesh` 实现
3. **视口内拖拽操作** — 浇注口/排气口/螺丝孔可拖拽放置
4. **测量工具** — 距离/角度测量
5. **单元测试框架** — 建立 pytest 基础设施并为核心模块编写测试

---

## 28. Phase A 实施记录 — 架构层升级 (v3.0)

### 28.1 布尔运算统一层 (`core/boolean_ops.py`)

**新建文件**：`moldgen/core/boolean_ops.py`

**公共 API**:
- `boolean_subtract(mesh_a, mesh_b, *, min_faces=4)` → 差集
- `boolean_union(mesh_a, mesh_b, *, min_faces=4, require_watertight=False)` → 并集
- `boolean_intersect(mesh_a, mesh_b, *, min_faces=4)` → 交集
- `batch_subtract(base, cutters, *, min_faces=4)` → 批量差集（先合并减一次，失败则逐个减）

**统一策略**:
1. 优先 manifold3d（精确 CSG）
2. 回退 trimesh engine loop: "manifold" → "blender" → default
3. 统一日志: debug 级记录引擎失败，warning 级记录全部失败
4. 可配置 `min_faces` 阈值和 `require_watertight` 参数

**重构影响**:
- `mold_builder.py`: `_robust_boolean_subtract/union/intersect` → 委托到 `boolean_ops`
- `gating.py`: `_boolean_subtract` → 删除，导入 `boolean_subtract as _boolean_subtract`
- `insert_generator.py`: `_manifold_subtract/union` → 委托到 `boolean_ops`

**消除代码**: 约 250 行重复的 manifold3d/trimesh 布尔逻辑

### 28.2 网格修复统一层 (`core/mesh_repair.py` 扩展)

**扩展已有文件**，新增低层 API:
- `clean_trimesh(mesh)` → 轻量清理（退化面 + 未引用顶点）
- `compact_vertex_indices(tm)` → 重索引顶点到密集 0…N-1
- `dedupe_faces(tm)` → 移除重复/反向三角形（带边界校验）
- `repair_trimesh(tm, *, fill=True, aggressive=False)` → 统一修复
  - `fill=False`: 保留有意的孔
  - `aggressive=True`: 额外 fix_inversion + dedupe + compact（模具输出用）
- `stitch_boundaries(mesh)` → 缝合开放边界
- `voxel_repair(mesh, pitch)` → 体素化重建（marching cubes）

**重构影响**:
- `mold_builder.py`: 删除 `_compact_mesh_vertex_indices`、`_boundary_undirected_edge_count`、`_dedupe_opposite_or_duplicate_tris`、`_repair_mesh`（共 ~120 行），用 `repair_trimesh(..., aggressive=True)` 替代
- `insert_generator.py`: 删除 `_clean_mesh`、`_repair_mesh`、`_stitch_hole_boundaries`、`_voxel_repair`（共 ~130 行），用统一层替代

### 28.3 视口内拖拽放置浇注口/排气口 (`GatingPlacer.tsx`)

**新建组件**: `frontend/src/components/viewer/GatingPlacer.tsx`

**功能**:
- **点击放置**: 用户在左侧面板选择"手动"模式后点击"🎯 点击放置"按钮，然后在3D视口中直接点击模型表面放置浇口/排气口
- **拖拽调整**: 已放置的标记点可通过拖拽移动，自动吸附到最近的模型表面
- **右键删除**: 右键点击标记点可删除
- **实时坐标显示**: 左侧面板同步显示当前坐标，也可手动输入精确值

**状态管理变更** (`simStore.ts`):
- 新增: `placementMode`, `manualGatePos`, `manualVentPositions` 及对应 setter
- 手动位置从 LeftPanel 本地状态迁移到全局 store，确保视口和面板同步

### 28.4 测量工具 (`MeasureOverlay.tsx`)

**新建组件**: `frontend/src/components/viewer/MeasureOverlay.tsx`

**功能**:
- **距离测量**: 点击两点测量3D欧氏距离
- **角度测量**: 点击三点测量夹角
- **面积测量**: 点击多点计算三角形扇面积

**UI**:
- 视口左上方新增测量工具栏（距离/角度/面积按钮 + 清除）
- 测量点显示为红色球体（带标号 P1, P2...）
- 测量线显示为黄色连线
- 结果以浮动标签显示（单位: mm / ° / mm²）

**状态管理变更** (`viewportStore.ts`):
- 新增: `MeasureTool` 类型, `measureTool`, `measurePoints`, `measureResult` 及计算逻辑

### 28.5 单元测试

**新建文件**:
- `tests/conftest.py` — 共享 fixture（unit_cube, unit_sphere, large_box 等）
- `tests/test_boolean_ops.py` — 6 个测试用例覆盖 subtract/union/intersect/batch
- `tests/test_mesh_repair.py` — 7 个测试用例覆盖 clean/compact/dedupe/repair/stitch

**测试结果**: 225 通过 / 8 预存失败（非本次引入）

---

## 29. 可定制设置系统 (v3.1)

### 29.1 概述

实现了完整的用户可定制设置系统，支持明暗主题切换、强调色选择、字体大小调节、界面密度、3D 视口选项等。所有设置通过 `localStorage` 自动持久化。

### 29.2 架构

```
settingsStore.ts        ─ Zustand + persist 中间件，所有设置状态
ThemeApplier.tsx         ─ 无 UI 组件，将设置映射到 CSS 变量
index.css @theme         ─ 定义 CSS 变量基准值（运行时被 ThemeApplier 覆盖）
SettingsDialog → UiSettings ─ 设置面板 UI
```

### 29.3 settingsStore (`stores/settingsStore.ts`)

**状态分组**:

| 分类 | 字段 | 类型 | 默认值 |
|------|------|------|--------|
| 外观 | `themeMode` | `"dark" / "light" / "system"` | `"dark"` |
| 外观 | `accentColor` | 7种预设色 | `"indigo"` |
| 外观 | `uiDensity` | `"compact" / "normal" / "comfortable"` | `"normal"` |
| 字体 | `fontSize` | number (10-18) | 13 |
| 字体 | `panelFontSize` | number (10-16) | 12 |
| 字体 | `monoFontSize` | number (10-16) | 12 |
| 边框 | `borderRadius` | number (0-16) | 8 |
| 视口 | `showGrid` | boolean | true |
| 视口 | `showAxes` | boolean | true |
| 视口 | `showGizmo` | boolean | true |
| 视口 | `autoRotate` | boolean | false |
| 视口 | `antiAlias` | boolean | true |
| 交互 | `enableAnimations` | boolean | true |
| 交互 | `confirmBeforeDelete` | boolean | true |
| 交互 | `autoSave` | boolean | false |
| 交互 | `autoSaveInterval` | number (10-300) | 60 |

**持久化**: 使用 `zustand/persist` 中间件，key 为 `moldgen-settings`，存储在 `localStorage`。

### 29.4 ThemeApplier (`components/ThemeApplier.tsx`)

无 UI 组件，挂载在 `App.tsx` 中。职责：

1. 监听 `settingsStore` 中的外观设置变化
2. 将深色/浅色主题的颜色 token 写入 `document.documentElement.style`
3. 将强调色 (accent) 覆盖 `--color-accent*` 变量
4. 设置 `html` 根元素 `font-size`
5. 设置 `data-theme` 属性和 `no-animations` class
6. 当 `themeMode === "system"` 时，监听 `prefers-color-scheme` 媒体查询变化

**颜色方案**:
- 深色模式: 基于原始 `@theme` 定义（bg-primary: #0d0d12 等）
- 浅色模式: 全新调色板（bg-primary: #f8f9fc, text-primary: #1a1d26 等）
- 强调色: 7 种预设（indigo/blue/emerald/rose/amber/violet/cyan），每种含 main/hover/muted 三阶

### 29.5 UiSettings 面板

替换了原有的占位 `UiSettings` 组件，实现完整设置面板，分为 5 个区域：

1. **主题与外观**: 明暗模式选择、强调色圆点选择器、界面密度
2. **字体大小**: 基础字体/面板字体/等宽字体滑块
3. **边框与形状**: 圆角半径滑块
4. **3D 视口**: 网格/坐标轴/方向标识/自动旋转/抗锯齿开关
5. **交互行为**: 动画效果/删除确认/自动保存开关

底部提供"恢复默认值"按钮。

### 29.6 Viewport 集成

`Viewport.tsx` 从 `settingsStore` 消费以下设置并实时响应：

- `showGrid` → 控制 `<Grid>` 组件渲染
- `showAxes` → 控制 `<axesHelper>` 渲染
- `showGizmo` → 控制 `<GizmoHelper>` 渲染
- `autoRotate` → 传入 `<OrbitControls autoRotate>`
- `antiAlias` → 传入 `<Canvas gl={{ antialias }}>`

### 29.7 CSS 支持

在 `index.css` 中新增：

- `html` 过渡动画: `transition: background-color 0.3s, color 0.3s`（主题切换平滑）
- `.no-animations` 全局类: 禁用所有 `animation-duration` 和 `transition-duration`

---

> 📖 [文档中心](README.md) | [← 上一篇: 核心算法](03-algorithms.md) | [下一篇: 技术栈 →](05-tech-stack.md) | [返回项目主页](../README.md)
