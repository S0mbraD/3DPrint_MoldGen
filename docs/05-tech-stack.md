# 技术栈选型

## 1. 选型总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Desktop Shell: Tauri 2.0 (Rust)                    │
├──────────────────────────────────────────────────────────────────────┤
│                              Frontend                                 │
│  React 18 │ TypeScript │ Three.js │ R3F │ WebGPU                      │
│  Zustand │ TanStack Query │ Framer Motion │ Tailwind │ shadcn/ui      │
├──────────────────────────────────────────────────────────────────────┤
│                          AI Services (NEW)                            │
│  DeepSeek V3 (对话/Agent) │ 通义万相 (图像生成) │ Tripo3D (3D生成)     │
│  Qwen-VL (多模态视觉)    │ OpenAI 兼容 SDK                           │
├──────────────────────────────────────────────────────────────────────┤
│                      Backend: Python 3.11+ / FastAPI                  │
├──────────────────────────────────────────────────────────────────────┤
│                    GPU Compute: Numba CUDA / CuPy / cuBVH             │
├──────────────────────────────────────────────────────────────────────┤
│                    Core: trimesh │ manifold3d │ open3d │ pyassimp      │
├──────────────────────────────────────────────────────────────────────┤
│                Environment: Conda (Mambaforge)                        │
│                Packaging: PyInstaller │ Tauri Build                    │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. 环境管理：Conda

### 2.1 选择理由

- CUDA 工具链安装最简（`conda install cuda-toolkit`）
- Open3D / PyTorch 等科学计算库的预编译包最完整
- 跨平台环境一致性
- 与 pip 可混合使用

### 2.2 environment.yml

见项目根目录 `environment.yml` 文件，包含所有 Python 依赖。

### 2.3 关键安装命令

```bash
# 创建环境
conda env create -f environment.yml

# 激活环境
conda activate moldgen

# 更新环境
conda env update -f environment.yml --prune
```

## 3. AI 服务技术栈（核心新增）

### 3.1 对话/推理：DeepSeek V3

**选择理由**：
- 价格最低（¥0.5-2/百万 tokens），长期运营成本可控
- 代码生成和逻辑推理能力强（MMLU-Pro 75.9）
- 原生支持 Function Calling（构建 Agent 必需）
- 完全兼容 OpenAI SDK（切换成本为零）
- 64K 上下文窗口

```python
# 安装：pip install openai
from openai import OpenAI
client = OpenAI(api_key="sk-...", base_url="https://api.deepseek.com")

# Function Calling 构建 Agent
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[...],
    tools=[{
        "type": "function",
        "function": {
            "name": "generate_insert_plate",
            "description": "在指定位置生成支撑板",
            "parameters": {...}
        }
    }]
)
```

**备选切换方案**：因使用 OpenAI SDK，可无缝切换至：
- 通义千问 (数学/编程场景)
- Kimi (超长上下文)
- GPT-4o / Claude (如需国际服务)

### 3.2 图像生成：通义万相

**选择理由**：中文提示词最优、速度快（2-5秒）、阿里云生态

```python
# 通过 DashScope API
import dashscope
result = dashscope.ImageSynthesis.call(
    model="wanx2.1-t2i-plus",
    input={"prompt": "人体肝脏解剖结构，医学教科书插图风格"},
    parameters={"size": "1024*1024"}
)
```

### 3.3 3D 模型生成：Tripo3D

**选择理由**：中国团队、Python SDK、2秒生成、支持文字/图像→3D

```python
# pip install tripo3d
from tripo3d import TripoClient
client = TripoClient(api_key="...")

# 文字生成3D
task = client.text_to_model("human liver anatomical model, medical grade")
model = task.wait_for_completion()
model.download("liver_model.glb")

# 图像生成3D
task = client.image_to_model(image_path="liver_reference.png")
```

### 3.4 多模态视觉：Qwen-VL

**选择理由**：兼容 OpenAI SDK、中文理解强、支持图片+文本输入

```python
client = OpenAI(
    api_key="...",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
response = client.chat.completions.create(
    model="qwen-vl-plus",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "model_screenshot.png"}},
            {"type": "text", "text": "分析这个3D器官模型，识别解剖结构并建议支撑板位置"}
        ]
    }]
)
```

### 3.5 AI API 配置管理

```python
# config.py 中的 AI 配置
class AIConfig(BaseSettings):
    # 对话/Agent
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    
    # 图像生成
    tongyi_api_key: str = ""          # 阿里云 DashScope
    tongyi_image_model: str = "wanx2.1-t2i-plus"
    
    # 3D 模型生成
    tripo_api_key: str = ""
    tripo_model_version: str = "v2.5"
    
    # 多模态视觉
    qwen_api_key: str = ""            # 同 tongyi_api_key (DashScope)
    qwen_vision_model: str = "qwen-vl-plus"
    
    # 备选/降级
    fallback_chat_provider: str = "qwen"  # deepseek 不可用时降级
    
    class Config:
        env_prefix = "MOLDGEN_AI_"    # 环境变量前缀
```

## 4. 后端核心库

### 4.1 3D 网格处理
- **trimesh** — 主要网格处理
- **manifold3d** — 高性能布尔运算
- **open3d** — QEM 简化 / Loop 细分
- **pyassimp** — FBX 等格式导入

### 4.2 GPU 加速
- **Numba CUDA** — 自定义 CUDA 核
- **CuPy** — GPU 数组 / 稀疏求解
- **cuBVH** — GPU BVH 光线投射

### 4.3 科学计算
- **numpy / scipy** — 核心数值
- **networkx** — 图算法
- **scikit-learn** — 聚类/PCA

## 5. 前端技术栈

### 5.1 核心
- React 18 + TypeScript + Vite
- Three.js + React Three Fiber + drei
- Tailwind CSS + shadcn/ui
- Zustand + TanStack Query

### 5.2 动画
- **Framer Motion** — UI 动画（面板/步骤/数值）
- **@react-spring/three** — 3D 动画（爆炸/相机）

### 5.3 AI 相关前端
- **react-markdown** — Markdown 渲染（AI 回复）
- **react-syntax-highlighter** — 代码高亮
- **EventSource / WebSocket** — AI 流式响应

### 5.4 前端依赖

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "@react-three/fiber": "^8.16.0",
    "@react-three/drei": "^9.100.0",
    "three": "^0.163.0",
    "zustand": "^4.5.0",
    "@tanstack/react-query": "^5.28.0",
    "framer-motion": "^11.0.0",
    "@react-spring/three": "^9.7.0",
    "tailwindcss": "^3.4.0",
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0",
    "react-dropzone": "^14.2.0",
    "@tauri-apps/api": "^2.0.0",
    "@tauri-apps/plugin-shell": "^2.0.0",
    "@tauri-apps/plugin-fs": "^2.0.0"
  }
}
```

## 6. 桌面框架：Tauri 2.0

（同前版本，Python Sidecar 方案）

## 7. 开发工具链

```
环境: Conda (Mambaforge) + Node.js 18+ + Rust 1.77+
后端: ruff / mypy / pytest
前端: ESLint / Prettier / Vitest
版本: Git + Conventional Commits
```

## 8. AI API 成本估算

| 服务 | 单次典型用量 | 单次成本 | 月度预估(100次) |
|------|------------|---------|----------------|
| DeepSeek 对话 | ~2K tokens | ¥0.004 | ¥0.4 |
| DeepSeek Agent (含工具) | ~10K tokens | ¥0.02 | ¥2 |
| 通义万相 图像 | 1张 | ~¥0.02 | ¥2 |
| Tripo3D 3D生成 | 1个模型 | ~$0.5 | $50 |
| Qwen-VL 视觉 | 1张图 | ~¥0.01 | ¥1 |
| **月度总计** | | | **~¥40 + $50** |

Tripo3D 是主要成本项，可通过缓存和限制生成频率控制。

## 9. 技术风险（更新）

| 风险 | 缓解 |
|------|------|
| AI 生成3D模型质量不够精确 | 生成后提供编辑工具修正；降级为手动导入 |
| AI API 延迟影响用户体验 | 流式响应；后台任务+进度提示；结果缓存 |
| DeepSeek API 不可用 | 自动降级到通义千问/Kimi |
| AI 成本失控 | 用量监控面板；生成前确认；每日额度限制 |
| Function Calling 精度 | 严格的工具 JSON Schema；结果校验；用户确认关键操作 |
| 国内API访问海外服务 | Tripo3D 中国团队，访问友好；其他均国内服务 |
