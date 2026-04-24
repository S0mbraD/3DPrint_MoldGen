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

### 螺丝固定法兰 (v5 新增)

通过 `add_flanges=True` 在分型面外侧生成安装法兰:
- 均匀分布 n 个法兰, 每个含圆柱螺丝通孔
- 支持自定义: 法兰宽度/厚度, 螺丝孔直径, 数量

### 孔位切割

浇筑口和排气口通过 `_cut_holes_in_shells` 使用布尔差集切入壳体网格，生成实际通孔。

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

## 8. gating_system 模块 — 浇注系统

### 8.1 核心接口（更新 — 含插板适配）

```python
class GatingSystem:
    def design(self, mold: MoldResult, material: MaterialProperties,
               inserts: Optional[InsertResult] = None) -> GatingResult:
        """
        设计浇注系统，如有插板则避让插板并利用网孔辅助流动
        """
    
    def optimize_gate_position(self, mold: MoldResult,
                               inserts: Optional[InsertResult] = None) -> List[np.ndarray]:
        """浇口位置优化（避开插板安装区域）"""

class MaterialProperties:
    name: str = "silicone"
    viscosity: float = 3000.0       # mPa·s
    density: float = 1.1            # g/cm³
    cure_time: float = 240.0        # min
    shrinkage: float = 0.001
    max_pressure: float = 0.5       # MPa
    temperature: float = 25.0       # °C (灌注温度)
    
    # 预设材料库
    @classmethod
    def silicone_shore_a30(cls) -> 'MaterialProperties': ...
    @classmethod
    def silicone_shore_a50(cls) -> 'MaterialProperties': ...
    @classmethod
    def polyurethane(cls) -> 'MaterialProperties': ...
    @classmethod
    def epoxy_resin(cls) -> 'MaterialProperties': ...
    @classmethod
    def abs_injection(cls) -> 'MaterialProperties': ...
    @classmethod
    def pp_injection(cls) -> 'MaterialProperties': ...
```

## 9. flow_simulator 模块 — GPU 加速灌注仿真

```python
class FlowSimulator:
    def __init__(self, config: SimConfig = None, gpu_compute: GPUCompute = None):
        self.gpu = gpu_compute or GPUCompute()
    
    def simulate(self, mold: MoldResult, gating: GatingResult,
                 material: MaterialProperties,
                 inserts: Optional[InsertResult] = None) -> SimulationResult:
        """运行灌注仿真，自动选择 CPU/GPU 路径"""
    
    def run_level1(self, ...) -> SimulationResult:
        """启发式快速分析 (CPU, <2s)"""
    
    def run_level2(self, ...) -> SimulationResult:
        """简化达西流 (GPU加速, <30s)"""

class SimConfig:
    level: int = 2
    mesh_resolution: int = 128           # 体素分辨率
    time_steps: int = 100
    animation_frames: int = 50
    use_gpu: bool = True                 # 优先GPU
    detect_air_traps: bool = True
    detect_weld_lines: bool = True
    consider_inserts: bool = True        # 仿真时考虑插板存在
```

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

## 21. 开发路线图

### Phase 5 计划

| 优先级 | 功能 | 描述 |
|--------|------|------|
| P0 | 会话持久化 | 后端工作流状态持久化到磁盘, 重启不丢失 |
| P0 | 错误恢复 | GPU OOM / 网络断连时优雅降级 |
| P1 | 高级编辑 | 视口内直接拖拽编辑顶点/面 (MeshEditor) |
| P1 | 测量工具 | 距离/角度/面积实时测量叠加层 |
| P1 | 多片模具工作流 | UI 完整支持 3+ 片壳体的拆分与装配 |
| P2 | Agent 工作站 | 完整的 AI Agent 交互界面, 进度/暂停/确认 |
| P2 | 批量处理 | 多模型批量导入→模具→导出流水线 |
| P3 | 打印集成 | 直接发送到切片软件 (Cura/PrusaSlicer) |
| P3 | 版本管理 | 工作流快照与回滚 |
