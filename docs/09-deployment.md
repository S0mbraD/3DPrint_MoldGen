# MoldGen 部署与使用指南

## 目录

1. [环境要求](#1-环境要求)
2. [安装部署](#2-安装部署)
3. [启动运行](#3-启动运行)
4. [界面使用](#4-界面使用)
5. [工作流程](#5-工作流程)
6. [快捷键](#6-快捷键)
7. [AI 配置](#7-ai-配置)
8. [常见问题](#8-常见问题)
9. [生产部署](#9-生产部署)

---

## 1. 环境要求

### 硬件要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | Intel i5 / AMD Ryzen 5 | Intel i7 / AMD Ryzen 7 |
| GPU | NVIDIA GTX 1060 (6GB) | NVIDIA RTX 4060 Ti (16GB) |
| 内存 | 16 GB | 32 GB |
| 存储 | 10 GB 可用空间 | 50 GB SSD |

### 软件要求

| 软件 | 版本 | 说明 |
|------|------|------|
| 操作系统 | Windows 10/11, Ubuntu 22.04+ | macOS 仅限 CPU 模式 |
| Conda | Miniconda 或 Anaconda | 用于 Python 环境管理 |
| Node.js | v18+ | 前端构建工具链 |
| NVIDIA 驱动 | 535+ | GPU 加速必需 |
| CUDA Toolkit | 12.8 | 由 Conda 管理 |
| Rust | 1.70+ | Tauri 桌面打包 (可选) |

---

## 2. 安装部署

### 2.1 克隆项目

```bash
git clone <repository-url> moldgen
cd moldgen
```

### 2.2 创建 Python 环境

```bash
# 方式 A: 使用 environment.yml (推荐)
conda env create -f environment.yml
conda activate moldgen

# 方式 B: 手动创建
conda create -n moldgen python=3.11 -y
conda activate moldgen
pip install -e ".[dev,mesh]"
```

> **重要**: `mesh` 可选依赖包含 `trimesh`, `manifold3d`, `scikit-image` 等，是模具生成功能所必需的。

### 2.3 安装 GPU 加速 (可选但强烈推荐)

```bash
conda install -y -c nvidia cuda-toolkit=12.8
conda install -y -c conda-forge numba>=0.64
pip install cupy-cuda12x
```

验证 GPU:
```bash
python -c "from moldgen.gpu.device import GPUDevice; g = GPUDevice(); print(g.info)"
```

### 2.4 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 2.5 配置 AI API (可选)

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入 API Key:
```ini
DEEPSEEK_API_KEY=sk-your-deepseek-key
QWEN_API_KEY=sk-your-qwen-key
KIMI_API_KEY=sk-your-kimi-key
TRIPO_API_KEY=tsk_your-tripo-key
```

> 不配置 AI Key 也可以使用所有核心功能（模型导入、模具生成、仿真等）。
> AI 功能（对话助手、Agent 自动化、模型生成）需要对应的 API Key。

---

## 3. 启动运行

### 3.1 开发模式（推荐测试）

需要同时启动后端和前端两个进程：

**终端 1 — 启动后端 API 服务:**
```bash
conda activate moldgen
cd <项目根目录>
python -m uvicorn moldgen.main:app --reload --host 127.0.0.1 --port 8000
```

**终端 2 — 启动前端开发服务器:**
```bash
cd <项目根目录>/frontend
npm run dev
```

然后打开浏览器访问: **http://localhost:1420**

> 前端开发服务器会自动将 `/api` 请求代理到后端 `127.0.0.1:8000`。

### 3.2 API 文档

后端启动后可访问自动生成的 API 文档:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

### 3.3 Tauri 桌面应用模式 (可选)

```bash
cd frontend
npm run tauri:dev
```

> 需要安装 Rust 工具链。首次编译较慢 (~3分钟)。

---

## 4. 界面使用

### 4.1 界面布局

```
┌─────────────────────────────────────────────────────┐
│ 标题栏 (MoldGen)                      [⚙] [◧] [◨] │
├─────────────────────────────────────────────────────┤
│ 工具栏 [导入|编辑|方向|模具|支撑板|浇注|仿真|导出] [⚙]│
├──────┬──────────────────────────────────┬───────────┤
│ 步骤 │                                  │ 信息      │
│ 工具 │      3D 视口                     │ 面板      │
│ 栏   │      (Three.js)                  │           │
│      │                                  │           │
│ 参数 │                                  │           │
│ 面板 │                                  │           │
├──────┴──────────────────────────────────┴───────────┤
│ 状态栏 (GPU 状态 / 模型信息 / 版本)                   │
└─────────────────────────────────────────────────────┘
                                        [💬 AI 悬浮球]
```

### 4.2 面板说明

| 区域 | 功能 |
|------|------|
| **工具栏** | 8 个工作流步骤导航，点击切换 |
| **步骤工具栏** | 每个步骤的专属快捷工具按钮 (位于左面板顶部) |
| **参数面板 (左)** | 当前步骤的操作参数和执行按钮 |
| **3D 视口 (中)** | 模型/模具实时 3D 预览，支持旋转、平移、缩放 |
| **信息面板 (右)** | 模型属性、仿真结果、支撑板信息 |
| **状态栏** | GPU、模型统计、版本 |
| **AI 悬浮球** | 右下角，点击打开 AI 对话面板 |
| **设置** | 标题栏/工具栏齿轮图标，或 `Ctrl+,` |

---

## 5. 工作流程

### 5.1 标准流程

```
步骤 1: 导入模型 (STL/OBJ/FBX/3MF/STEP/PLY/glTF)
   ↓
步骤 2: 编辑 (修复 → 简化/细分 → 变换/缩放)
   ↓
步骤 3: 模具设计 (脱模方向 → 分型面 → 壳体生成)
   ↓
步骤 4: 支撑板 (位置分析 → 板生成 → 锚固 → 装配验证)
   ↓
步骤 5: 仿真 (材料 → 浇注系统 → 灌注仿真 → 自动优化)
   ↓
步骤 6: 导出 (STL/OBJ/PLY/GLB/3MF → 单独/打包)
```

### 5.2 详细操作

#### 步骤 1: 导入模型
- 点击上传区域或拖拽文件
- 支持格式: STL, OBJ, FBX, 3MF, STEP, PLY, glTF, AMF, DAE, OFF
- 导入后自动显示在 3D 视口

#### 步骤 2: 编辑
- **修复**: 自动修复非流形、孔洞、退化面
- **简化**: 拖动滑块设定目标比例，减少面数
- **细分**: Loop 细分 (1~4 次迭代)
- **变换**: 居中、落地、翻转、镜像
- **旋转**: X/Y/Z 轴 90° 快速旋转
- **缩放**: 0.1× ~ 5.0× 精确缩放
- **测量**: 查看顶点数、面数、尺寸、体积、水密性

#### 步骤 3: 模具设计
1. **分析脱模方向** — Fibonacci 球面采样 + 多准则评分
2. **生成分型面** — 基于最优方向自动生成
3. **生成壳体** — 选择壁厚 (2~8mm) 和壳类型 (方形/随形)

#### 步骤 4: 支撑板
1. 选择器官类型 (通用/实质/空腔/管道/组织片)
2. 分析最佳位置
3. 设置板厚、数量、锚固类型
4. 生成并验证装配

#### 步骤 5: 仿真
1. 选择材料 (硅胶 A10/A30/A50, 聚氨酯, 环氧树脂等)
2. 设计浇注系统
3. 运行灌注仿真 (L1 快速 / L2 精确)
4. 自动优化 (迭代改进浇口、排气等参数)

#### 步骤 6: 导出
- 单独导出: 模型 / 模具壳体 (ZIP) / 支撑板 (ZIP)
- 一键导出: 全部打包为 ZIP
- 格式: STL (FDM推荐), OBJ, PLY, GLB, 3MF

### 5.3 AI 辅助

- **AI 对话**: 点击右下角悬浮球，自然语言描述需求
- **Agent 工作站**: `Ctrl+Shift+A` 打开，管理 6 个专业 Agent
- **快速指令**: "全自动模具设计"、"分析脱模方向"、"生成心脏教学模型" 等

---

## 6. 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+1` ~ `Ctrl+6` | 切换工作流步骤 |
| `Ctrl+B` | 切换左侧参数面板 |
| `Ctrl+I` | 切换右侧信息面板 |
| `Ctrl+J` | 切换 AI 对话 |
| `Ctrl+Shift+A` | 切换 Agent 工作站 |
| `Ctrl+,` | 打开设置 |
| 鼠标左键拖拽 | 旋转 3D 视图 |
| 鼠标右键拖拽 | 平移 3D 视图 |
| 鼠标滚轮 | 缩放 3D 视图 |

---

## 7. AI 配置

### 7.1 通过设置面板

点击齿轮图标 → "AI API" 标签页 → 填入 API Key → 保存

### 7.2 通过环境变量

在 `.env` 文件中配置:

```ini
# 对话 AI (任选一个即可)
DEEPSEEK_API_KEY=sk-...        # DeepSeek V3
QWEN_API_KEY=sk-...            # 通义千问
KIMI_API_KEY=sk-...            # Kimi (Moonshot)

# 图像生成
WANXIANG_API_KEY=sk-...        # 通义万相

# 3D 模型生成
TRIPO_API_KEY=tsk_...          # Tripo3D
```

### 7.3 AI 服务说明

| 服务 | 费用 | 用途 |
|------|------|------|
| DeepSeek V3 | ~¥1/百万token | 主力对话/推理 |
| 通义千问 | 免费额度 | 备选对话 |
| Kimi | 免费额度 | 长上下文对话 |
| 通义万相 | ~¥0.04/张 | 图像生成 |
| Tripo3D | 按模型计费 | 3D 模型生成 |

---

## 8. 常见问题

### Q: GPU 未被识别？
A: 确保已安装 NVIDIA 驱动 535+，并在 Conda 环境中安装了 `cuda-toolkit=12.8`。可运行:
```bash
python -c "import numba.cuda; print(numba.cuda.gpus)"
```

### Q: 前端访问报 502 / 网络错误？
A: 确保后端已启动在 `127.0.0.1:8000`。检查终端是否有错误信息。

### Q: AI 功能不可用？
A: 核心功能不依赖 AI。AI 功能需要在 `.env` 或设置面板中配置对应的 API Key。

### Q: 模型导入失败？
A: 检查文件格式是否受支持。部分 FBX 文件需要安装 `assimp` 系统库:
```bash
conda install -y -c conda-forge assimp
```

### Q: 仿真很慢？
A: 降低体素分辨率 (设置 → 仿真参数)，或使用 L1 快速仿真而非 L2。启用 GPU 加速可获得显著提速。

### Q: 端口被占用？
A: 修改后端端口: `python -m uvicorn moldgen.main:app --port 8001`
前端 `vite.config.ts` 中同步更新 proxy target。

---

## 9. 生产部署

### 9.1 构建前端

```bash
cd frontend
npm run build
```

产物位于 `frontend/dist/`。

### 9.2 打包后端

```bash
pip install pyinstaller
pyinstaller --onefile --name moldgen-server moldgen/main.py
```

### 9.3 构建 Tauri 桌面应用

```bash
cd frontend
npm run tauri:build
```

产物位于 `frontend/src-tauri/target/release/`。

### 9.4 Docker 部署 (Linux)

```dockerfile
FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y python3.11 python3-pip nodejs npm
COPY . /app
WORKDIR /app
RUN pip install -e . && cd frontend && npm install && npm run build
EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "moldgen.main:app", "--host", "0.0.0.0"]
```

---

## 10. 算法版本记录

### v5 (当前版本)

| 模块 | 改进 | 效果 |
|------|------|------|
| 分型面互锁 | 5种分型面样式: flat/dovetail/zigzag/step/tongue_groove | 改善模具半壳对位精度和结构强度 |
| 螺丝固定法兰 | 在分型面外侧生成法兰+螺丝通孔 | 模具可通过螺丝夹紧固定，防止灌注时分离 |
| 表面映射可视化 | 将体素仿真数据投射到模型表面三角网格 | 类似SolidWorks的表面热力图叠加效果 |
| 有限元分析(FEA) | 弹簧质量近似FEA: Von Mises应力/位移/安全系数 | 结构强度预判，8种材料预设 |
| FEA可视化 | 逐顶点着色: Von Mises/位移/安全系数/应变能 | 直观查看应力集中和薄弱区域 |
| 模具壳体可见性 | 修复heatmapVisible默认true导致壳体永不渲染的bug | 生成模具后立即可见，粉色+蓝色半透明材质 |
| 壳体材质 | MeshPhysicalMaterial + transmission/clearcoat | 高质量半透明渲染(粉#0, 蓝#1) |
| 流线可视化 | fill_time梯度追踪 + 空间网格哈希加速 | 直观展示灌注流动路径 |
| 粒子密度 | 1x/2x/3x密度倍增 + 抖动插值 | 更密集的粒子可视化效果 |
| 粒子渲染 | AdditiveBlending + 辉光边缘 | 更亮眼的流体发光效果 |
| 错误边界 | MoldShellViewer 添加 ErrorBoundary + 独立Suspense | GLB加载失败不再导致Canvas崩溃 |
| 支撑板可视化 | InsertPlateViewer 绿色半透明材质 + 源模型自动半透明 | 生成支撑板后立即可见 |
| 支撑板类型 | 4种: flat/conformal/ribbed/lattice | 仿形、加强筋、拓扑优化格栅 |
| 仿形板 | cKDTree 表面最近邻 + Laplacian 平滑 | 跟随模型曲面轮廓 |
| 格栅结构 | BCC 体心立方点阵 + 截面裁剪 | 轻量化最优刚度/重量比 |
| 场景管理器 | 支撑板条目 (Pin 图标, 绿色) | 显隐/透明度可控 |
| 仿形板性能 | 网格采样+向量化投影 (替代 section+extrude+per-vert loop) | 10万面模型 ~0.5s (vs >60s) |
| 格栅性能 | 预计算端点+批量创建+200杆上限 (替代 O(n³×8) 循环) | ~1-3s (vs >120s) |
| 位置分析 | 投影法快速面积估算 (替代 tm.section boolean) | 消除挂起风险 |
| 锚固优化 | 特征数上限8个; conformal/lattice/ribbed跳过锚固 | 减少 boolean 操作 |
| 装配验证 | AABB 包围盒碰撞检测 (替代 boolean intersection) | 毫秒级 |
| API线程 | asyncio.to_thread 包装 | 不阻塞 FastAPI 事件循环 |

### v5.1 — 支撑板生成修复

| 模块 | 问题 | 修复 |
|------|------|------|
| insert_generator.py | `remove_degenerate_faces()` 在 trimesh 4.x 中不存在，导致 conformal/ribbed/lattice 全部 500 | 新增 `_clean_mesh()` 辅助函数，使用 `nondegenerate_faces()` + `update_faces()` 替代 |
| mold_builder.py | `_repair_mesh()` 中同样调用已废弃 API | 统一替换为 `update_faces(nondegenerate_faces())` |
| fea.py | `analyze()` 入口同样调用已废弃 API | 同上修复 |
| useInsertApi.ts | `fetch()` 不检查 `res.ok`，500 错误被静默处理为空数据 | 新增 `checkedJson()` 辅助函数，HTTP 非 2xx 抛出异常触发 `onError` 回调 |
| 场景管理器 | 生成失败时 `insertId=null`，场景管理器不显示支撑板条目 | 上述前端修复后，错误会被正确捕获并通过 toast 提示用户 |

### v4

| 模块 | 改进 | 效果 |
|------|------|------|
| 壳体构造 | 三级策略: 布尔运算 → 体素回退 → 直接拼接 | 任何模型都能生成含空腔的有效模具 |
| 布尔运算 | 多引擎尝试: manifold3d → trimesh(manifold/blender/default) | 大幅提高布尔成功率 |
| 体素回退 | scipy.ndimage 膨胀 + skimage marching_cubes | 布尔全失败时仍可生成水密壳体 |
| 孔位切割 | 浇筑口/排气口圆柱体实际布尔差集到壳体 | 导出模具含真实通孔，可直接3D打印 |
| 网格修复 | 每壳体生成后多步修复(退化面/法线/孔洞/绕序) | 消除流形边错误，提高切片兼容性 |
| L2仿真 | NaN/inf 安全化: 压力求解后检查 + to_dict 安全浮点 | 消除 JSON 序列化崩溃 |
| 变换API | 前端参数修正: axis→向量, angle→angle_deg, flip→mirror | 旋转/翻转/镜像操作恢复正常 |
| 视口渲染 | 移除Center, 添加CameraAutoFit自动对准模型 | 模具与模型坐标对齐，正确显示 |

### v3

| 模块 | 改进 | 效果 |
|------|------|------|
| 浇筑口 (Pour Gate) | 4指标加权评分: 高度×中心性×可及性×厚度 | 放置在最佳充填位置而非简单最高点 |
| 排气口 (Vent) | 重力BFS流前模拟 + 气穴检测 + 最远点采样 | 精确预测最后充填区和气体滞留区 |
| 空腔偏移 | Laplacian 法线平滑后偏移 | 凹面区域自相交大幅减少 |
| 分型线 | 法线符号变化检测 (fallback) | 任何曲面模型都能找到分型线 |
| 对齐销 | 实际圆柱网格 (trimesh) | 前端可直接3D渲染 |
| 孔位 | 漏斗(浇口) + 细管(排气) 实际网格 | 可视化更直观 |
| 拔模角 | 每壳体自动分析, is_printable 标记 | FDM可打印性预判 |
| 分型面 | 无分型线时质心平面兜底 | 保证任何模型都有分型面输出 |

---

## 11. 前端功能更新记录

### v3 前端升级

| 页面/组件 | 改进 | 效果 |
|-----------|------|------|
| StepToolbar | 连接 `onAction` 事件分发 | 工具栏按钮可触发面板操作 |
| 方向分析页 | 候选方向**点击切换** + **手动方向输入** (XYZ) | 用户可自由选择/微调脱模方向 |
| 方向分析页 | 显示 `mean_draft_angle`, 候选列表含拔模角 | 更丰富的决策信息 |
| 模具页 | 显示 v3 浇口评分/直径、排气口BFS分数 | 算法透明度提升 |
| 模具页 | 壳体拔模角检查 + 可打印性标记 | FDM 友好度可视 |
| 模具页 | 对齐特征 (销/孔) 计数显示 | 装配信息完整 |
| 浇注页 | `gate_diameter` + `n_vents` 参数传递到后端 | UI参数真正生效 |
| 仿真页 | L1/L2 级别切换按钮 + 中文材料名称 | 仿真控制更灵活 |
| 右侧信息面板 | 浇口评分、排气口数、定位销数、拔模角 | v3 数据完整展示 |
| 键盘快捷键 | Ctrl+1~8 覆盖全部 8 个工作流步骤 | 旧版仅 6 个, 跳过了方向和浇注 |
| MoldStore | 支持 v3 类型: `HoleInfo`, `AlignmentFeatureInfo`, `min_draft_angle` | 前后端数据对齐 |

### v6 前端 UI/UX 重构

| 页面/组件 | 改进 | 效果 |
|-----------|------|------|
| 共享组件 | 新增 `CollapsibleSection` 可折叠区域组件 | 长面板内容可收起，减少滚动 |
| 共享组件 | 新增 `ParamSlider` / `ParamSelect` / `ParamRow` 参数组件 | 统一参数输入样式，代码复用 |
| 共享组件 | 新增 `ResultCard` / `ResultRow` 结果展示组件 | 统一结果卡片样式 |
| 共享组件 | 新增 `StepHint` 步骤引导组件 | 完成步骤后引导用户进入下一步 |
| 共享组件 | 新增 `StatusBadge` 工作流进度徽章 | 各面板顶部显示步骤完成状态 |
| ActionButton | 新增 `variant="primary"` 主按钮样式 + `disabled` 属性 | 关键操作视觉突出 |
| Section | 新增 `icon` 和 `badge` 属性 | 段落标题带图标和状态标记 |
| 所有面板 | 空状态改为图标+文案+跳转按钮 | 比纯文字"请先导入模型"更友好 |
| 所有面板 | 顶部添加 `StatusBadge` 工作流进度条 | 一目了然当前状态 |
| 支撑板面板 | 仿形/加强筋/格栅参数全部可编辑 (ParamSlider) | 偏移距离/筋高/间距/胞元尺寸等可调 |
| 支撑板面板 | 参数传递到后端 (conformal_offset/rib_height/lattice_cell_size 等) | UI参数真正生效 |
| 支撑板面板 | 板数选择改为数字按钮组 (1/2/3/4) | 点击比输入框更方便 |
| 浇注面板 | 排气孔数改为按钮组 (1/2/3/4/6/8) | 快速选择 |
| 浇注面板 | 使用 `ParamSlider` 重构参数输入 | 统一风格 |
| 仿真面板 | 热力图/动画/截面/表面映射/FEA 改为 CollapsibleSection | 长面板不再需要大量滚动 |
| 仿真面板 | 各子section 带 badge 显示状态 (已加载/播放中/完成等) | 快速掌握各功能状态 |
| 模具面板 | 完成后底部显示 `StepHint` 引导至支撑板/浇注 | 流程引导 |
| CrossSectionCanvas | 修复 useCallback/useState 为正确的 useEffect | 截面图可靠刷新 |
| MoldPanel | 修复浇口评分 `(score ?? 0 * 100)` → `((score ?? 0) * 100)` | 正确显示百分比 |

### v5 前端升级

| 页面/组件 | 改进 | 效果 |
|-----------|------|------|
| 模具页 | 分型面样式选择器 (5种) | 用户可选择燕尾榫/锯齿/阶梯/榫槽等互锁方式 |
| 模具页 | 螺丝法兰开关 + 数量选择 (2/4/6/8) | 可选生成带螺丝孔的固定法兰 |
| 仿真页 | 表面叠加显示模式 (Section 9) | 将热力图映射到模型表面，类SolidWorks可视化 |
| 仿真页 | 有限元分析面板 (Section 10) | 材料选择→运行FEA→查看应力/位移/安全系数 |
| FEA可视化 | 4场切换: Von Mises/位移/安全系数/应变能 | 彩色热力图叠加在模型上 |
| 壳体渲染 | MeshPhysicalMaterial (粉色#0/蓝色#1) | 高质量半透明玻璃效果 |
| 流线可视化 | 流线开关+数量控制 (10-80) | 直观流动路径显示 |
| 粒子控制 | 密度倍增按钮 (1x/2x/3x) | 更密集的流体可视化 |
| simStore | 新增: surfaceMap/FEA状态管理 | 完整的新功能状态支持 |
| useSimApi | 新增: useFetchSurfaceMap, useRunFEA, useFetchFEAVisualization | 完整API Hook链路 |
| InsertPlateViewer | 新组件: GLB加载 + 绿色MeshPhysicalMaterial | 支撑板3D渲染 |
| ModelViewer | 支撑板可见时自动降低源模型透明度 (→0.35) | X光式叠加视图 |
| InsertPanel | 板型选择器 (平板/仿形/加强筋/格栅) + 类型特定参数 | 完整支撑板控制 |
| viewportStore | insertVisible, insertOpacity 状态 | 支撑板显隐控制 |
| SceneManager | 支撑板条目 (数量, Pin图标) | 场景树完整 |

### 快捷键对照表

| 快捷键 | 功能 |
|--------|------|
| Ctrl+1 | 导入 |
| Ctrl+2 | 编辑 |
| Ctrl+3 | 方向分析 |
| Ctrl+4 | 模具 |
| Ctrl+5 | 支撑板 |
| Ctrl+6 | 浇注 |
| Ctrl+7 | 仿真 |
| Ctrl+8 | 导出 |
| Ctrl+B | 切换左侧面板 |
| Ctrl+I | 切换右侧面板 |
| Ctrl+J | AI 对话 |
| Ctrl+, | 设置 |
| Ctrl+Shift+A | Agent 工作站 |

---

## 12. 仿真系统 v4 升级记录

### 后端升级 (moldgen/core/flow_sim.py)

| 特性 | 说明 |
|------|------|
| **多物理场** | L2 仿真新增剪切率、温度、固化进度、壁厚共 7 个场 |
| **剪切率场** | γ̇ ≈ 6V/h 狭缝流近似，识别高剪切区域 |
| **温度场** | 热扩散模型 + 放热固化效应（Arrhenius 温度修正） |
| **固化进度场** | 简化 Kamal-Sourour 模型，反应速率随温度变化 |
| **综合分析报告** | AnalysisReport 含 20+ 指标：均匀性、平衡性、壁厚、剪切、温度等 |
| **优化建议** | 基于指标自动生成中文优化建议列表 |
| **可视化数据** | extract_visualization_data() 输出点云 + 7 个归一化场 |
| **截面切片** | extract_cross_section() 输出任意轴/位置的 2D 热力图数据 |

### API 新增端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/simulation/visualization/{sim_id}` | GET | 体素点云 + 所有场归一化值 |
| `/simulation/analysis/{sim_id}` | GET | 完整分析报告 + 可用场列表 |
| `/simulation/cross-section/{sim_id}` | GET | 2D 截面热力图 (axis/position/field) |

### 前端升级

| 组件 | 改进 |
|------|------|
| **SimulationViewer.tsx** | 新组件：WebGL ShaderMaterial 点云热力图，GLSL 自定义着色器 |
| **DefectMarkers** | 新组件：缺陷位置球体标记（颜色按类型，大小按严重度） |
| **Viewport.tsx** | 集成 SimulationViewer + DefectMarkers + HeatmapLegend 色带图例 |
| **SimPanel** | 8 大功能区：材料、浇注系统、仿真运行、热力图可视化、充填动画播放器、截面分析、综合分析报告、自动优化 |
| **热力图控制** | 7 场切换、透明度、点大小、显隐切换 |
| **动画播放器** | 播放/暂停/复位、进度条、0.5×/1×/2×/4× 速率、循环切换 |
| **截面分析** | XYZ 轴选择、位置滑块、Canvas 2D 热力图渲染 |
| **分析报告** | 可折叠面板：均匀性进度条、剪切/温度/壁厚统计、优化建议列表 |
| **RightPanel** | 扩展 SimInfoSection：质量评分、均匀性指标、壁厚、滞流区、温度、固化进度、体素统计 |
| **simStore.ts** | 新增 VisualizationData、CrossSectionData 类型及动画/热力图全部状态 |
| **useSimApi.ts** | 新增 useFetchVisualization、useFetchAnalysis、useFetchCrossSection hooks |
