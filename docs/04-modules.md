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

## 6. mold_builder 模块 — 模具壳体生成 (v5)

**核心改进**: 三级策略壳体构造 + 分型面互锁样式 + 螺丝固定法兰。

### 构造策略优先级

1. **布尔运算** (`_robust_boolean_subtract`): outer_box - cavity, 多引擎 (manifold3d → trimesh)
2. **体素回退** (`_build_shells_voxel`): 体素化 + marching cubes, 依赖 scikit-image
3. **直接拼接** (`_build_direct_shells`): box_half + cavity_inv_half, 仅可视化用

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
- `manifold3d>=2.5.0` (布尔运算首选引擎)
- `scikit-image>=0.22.0` (marching cubes 体素回退)
- `scipy` (ndimage 体素膨胀)

## 6b. fea 模块 — 有限元结构分析 (v5 新增)

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
    hole_pattern: str = "hexagonal"         # "grid" | "hexagonal" | "random"
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
