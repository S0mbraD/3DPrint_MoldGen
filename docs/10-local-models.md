# 本地 AI 模型系统

## 1. 系统概述

MoldGen 支持**云端 API** 和**本地 GPU 模型**双后端，用户可在设置中自由切换。

```
用户请求
   │
   ├─ 图像生成 ─┬─ 云端: 通义万相 (DashScope API)
   │            └─ 本地: SDXL / FLUX.1-schnell / SD 1.5 / Kolors
   │
   ├─ 3D 重建 ──┬─ 云端: Tripo3D API
   │            └─ 本地: TripoSR / InstantMesh / TRELLIS
   │
   ├─ 视觉分析 ── 云端: Qwen-VL (通义千问视觉)
   │
   └─ LLM 对话 ── 云端: DeepSeek / Qwen / Kimi (自动降级)
```

## 2. 推荐模型选择

### 2.1 按 GPU 显存分级

| GPU 显存 | 图像生成推荐 | 3D 重建推荐 | 说明 |
|---------|-------------|------------|------|
| ≥16GB (RTX 4060Ti 16G / 4080 / 4090) | SDXL 或 FLUX.1-schnell | TripoSR | 可同时加载，最佳体验 |
| 8-12GB (RTX 3070/3080/4060) | SDXL | TripoSR | 需交替加载，用完卸载 |
| 4-8GB (RTX 3060/4050) | SD 1.5 | TripoSR | 轻量模型，质量稍低 |
| <4GB 或无 GPU | 不推荐本地 | 不推荐本地 | 使用云端 API |

### 2.2 模型详细对比

#### 图像生成模型

| 模型 | VRAM | 磁盘 | 分辨率 | 速度 | 质量 | 特点 |
|------|------|------|-------|------|------|------|
| **SDXL 1.0** | 6.5GB | 6.9GB | 1024² | 中 | ⭐⭐⭐⭐⭐ | 推荐，质量最佳 |
| **FLUX.1-schnell** | 8GB | 23.8GB | 1024² | 极快 (1-4步) | ⭐⭐⭐⭐ | 最快，适合快速迭代 |
| **SD 1.5** | 4GB | 4.3GB | 512² | 中 | ⭐⭐⭐ | 轻量，低显存首选 |
| **Kolors (可图)** | 7GB | 10.5GB | 1024² | 中 | ⭐⭐⭐⭐ | 中文提示词最强 |

#### 3D 重建模型

| 模型 | VRAM | 磁盘 | 输入 | 速度 | 质量 | 特点 |
|------|------|------|------|------|------|------|
| **TripoSR** | 4GB | 1.5GB | 单图 | 极快 (~3s) | ⭐⭐⭐⭐ | 推荐，速度质量均衡 |
| **InstantMesh** | 8GB | 5.2GB | 单图 | 中 | ⭐⭐⭐⭐⭐ | 更高质量，复杂结构 |
| **TRELLIS** | 10GB | 4GB | 单图 | 中 | ⭐⭐⭐⭐⭐ | SOTA，微软出品 |

## 3. 安装指南

### 3.1 安装本地模型依赖

```bash
# 安装 PyTorch + CUDA (根据你的 CUDA 版本选择)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 安装本地模型依赖
pip install "moldgen[local-models]"

# 或手动安装
pip install diffusers transformers accelerate safetensors huggingface-hub Pillow
```

### 3.2 下载模型

**方式一：通过 UI**
1. 打开 设置 → 本地模型
2. 找到想要的模型，点击"下载"
3. 等待下载完成（首次较慢）

**方式二：通过 API**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ai/generate/local-models/download \
  -H "Content-Type: application/json" \
  -d '{"model_id": "sdxl-base"}'
```

**方式三：手动下载**
```bash
# 使用 huggingface-cli
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
  --local-dir data/local_models/sdxl-base

huggingface-cli download stabilityai/TripoSR \
  --local-dir data/local_models/triposr
```

### 3.3 配置 Provider

在 `.env` 中设置：
```env
# 切换到本地模型
MOLDGEN_AI_IMAGE_PROVIDER=local
MOLDGEN_AI_IMAGE_LOCAL_MODEL=sdxl-base
MOLDGEN_AI_MESH_PROVIDER=local
MOLDGEN_AI_MESH_LOCAL_MODEL=triposr
```

或在运行时通过设置页面切换。

## 4. 架构设计

### 4.1 核心模块

```
moldgen/ai/
├── local_models.py     # 本地模型管理器 (注册表/下载/加载/卸载/VRAM)
├── image_gen.py        # 图像生成 (云端万相 + 本地Diffusers)
├── model_gen.py        # 3D生成 (云端Tripo3D + 本地TripoSR)
├── vision.py           # 多模态视觉 (Qwen-VL)
├── chat.py             # LLM对话 (DeepSeek/Qwen/Kimi + 流式)
├── service_manager.py  # AI服务统一管理
└── agents/
    └── creative_agent.py  # 创意Agent (调用以上所有模块)
```

### 4.2 双后端透明切换

```python
# image_gen.py 核心逻辑
async def generate(self, prompt, provider=None, ...):
    provider = provider or config.ai.image_provider  # "cloud" or "local"
    if provider == "local":
        return await self._generate_local(prompt, model_id, ...)
    else:
        return await self._generate_cloud(prompt, ...)
```

### 4.3 VRAM 管理

- `LocalModelManager` 追踪所有已加载模型的显存占用
- 加载前检查可用显存，不足时提示卸载其他模型
- `auto_unload_after_gen` 选项：生成完成后自动释放显存
- 支持 `model_cpu_offload` 降低峰值显存

### 4.4 API 端点

```
POST /api/v1/ai/generate/image/generate      # 生成图像
POST /api/v1/ai/generate/mesh/text-to-3d     # 文字→3D
POST /api/v1/ai/generate/mesh/image-to-3d    # 图片→3D
POST /api/v1/ai/generate/prompt/optimize      # 提示词优化

GET  /api/v1/ai/generate/local-models         # 列出本地模型
POST /api/v1/ai/generate/local-models/download # 下载模型
POST /api/v1/ai/generate/local-models/{id}/load   # 加载
POST /api/v1/ai/generate/local-models/{id}/unload # 卸载
DELETE /api/v1/ai/generate/local-models/{id}       # 删除

GET  /api/v1/ai/generate/providers            # 获取provider配置
PUT  /api/v1/ai/generate/providers            # 切换provider
```

## 5. CreativeAgent 流水线

```
用户: "生成一个心脏教学模型"
  │
  ▼
CreativeAgent.execute()
  │
  ├─ 1. optimize_prompt()  ─── LLM 优化中文→英文提示词
  │                              fallback: 规则匹配医学术语
  ├─ 2. generate_images()  ─── 云端万相 或 本地SDXL
  │                              生成 2 张参考图
  ├─ 3. (用户选择 或 自动选择最佳图)
  │
  ├─ 4. image_to_3d()     ─── 云端Tripo3D 或 本地TripoSR
  │                              图片→3D网格
  ├─ 5. review_quality()  ─── Qwen-VL 审查解剖准确性
  │
  └─ 6. 交付给 ModelAgent 进行修复/优化
```

## 6. 性能基准

在 RTX 4060 Ti 16GB 上的预期性能：

| 操作 | 本地耗时 | 云端耗时 | 说明 |
|------|---------|---------|------|
| SDXL 生成 1张 (30步) | ~8s | N/A | 1024x1024 |
| FLUX.1 生成 1张 (4步) | ~3s | N/A | 1024x1024 |
| TripoSR 图→3D | ~3s | N/A | 256 MC分辨率 |
| 万相生成 1张 | N/A | ~3-5s | 含网络延迟 |
| Tripo3D 图→3D | N/A | ~10-30s | 含排队时间 |

**本地 vs 云端权衡：**
- 本地：无网络依赖、无 API 成本、隐私保护，但需要 GPU 显存
- 云端：无需本地 GPU、更新模型无成本，但需要 API Key 和网络
