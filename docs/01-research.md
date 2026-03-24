# 技术调研与竞品分析

## 1. 竞品分析

### 1.1 竞品对比矩阵（更新）

| 特性 | 3D Mold Maker | Moldboxer | OpenSCAD | 3Deus Dynamics | **MoldGen** |
|------|:---:|:---:|:---:|:---:|:---:|
| 多格式导入(FBX等) | △ | △ | ✗ | ✗ | **✓** |
| 模型编辑/细化/简化 | ✗ | ✗ | ✗ | ✗ | **✓** |
| AI 对话生成模型 | ✗ | ✗ | ✗ | ✗ | **✓** |
| AI 图像→3D模型 | ✗ | ✗ | ✗ | ✗ | **✓** |
| 医学教具专用 | ✗ | ✗ | ✗ | **✓** | **✓** |
| 自动最优方向分析 | ✗ | △ | ✗ | △ | **✓** |
| 多片壳(>2片) | ✗ | △ | ✗ | ✓ | **✓** |
| 复合结构(支撑板) | ✗ | ✗ | ✗ | △ | **✓** |
| AI辅助支撑板设计 | ✗ | ✗ | ✗ | ✗ | **✓** |
| 灌注流动仿真 | ✗ | ✗ | ✗ | ✗ | **✓** |
| GPU加速 | ✗ | ✗ | ✗ | ✗ | **✓** |
| 桌面应用 | ✗ | ✗ | ✓ | ✗ | **✓** |
| 开源 | ✗ | ✗ | ✓ | ✗ | **✓** |

### 1.2 医学教具制造行业参考

#### 3Deus Dynamics（西班牙）
- **定位**：3D 打印硅胶解剖模型专业制造商
- **产品**：血管手术、消化内镜(ERCP)、妇产科等训练模型
- **技术**：FDM 打印模具 → 医用级硅胶灌注 → 多色多材料
- **认证**：ISO 13485 + CE 标记 + ISO 10993 生物相容性
- **模型特性**：1:1 真实尺寸、可透明/着色、可反复使用
- **启示**：验证了 FDM 模具+硅胶灌注路线的工业可行性

#### 关键论文
- "Production of ERCP training model using 3D printing technique" (BMC Gastroenterology, 2020)
  - 3D 打印 ERCP 训练模型，胆道系统硅胶灌注
  - 临床医生评价优于传统训练方式

## 2. AI API 调研（新增）

### 2.1 对话/推理 AI

| 服务商 | 模型 | 输入价格 | 输出价格 | 免费额度 | 特点 |
|--------|------|---------|---------|---------|------|
| **DeepSeek** | V3 | ¥0.5-2/M tokens | ¥2-8/M tokens | 500万 | 性价比最高，代码能力强，兼容OpenAI SDK |
| 通义千问 | Max/Plus | ¥2.4/M tokens | ¥9.6/M tokens | 100万 | 数学编程全球第一，多模态 |
| 月之暗面 | Kimi K2.5 | ¥2-5/M tokens | ¥6-20/M tokens | 注册送 | 长文本最强(20万字)，Agent能力突出 |
| 智谱AI | GLM-4-Plus | ¥5/M tokens | ¥5/M tokens | 2500万 | 免费额度最大，多模态 |
| 百度 | ERNIE 4.0 | ¥4/M tokens | ¥8-16/M tokens | 部分限免 | 中文知识库最强 |
| 字节 | 豆包Doubao | ¥5/M tokens | ¥9/M tokens | 50万 | 成本适中 |

**首选方案**：**DeepSeek V3** — 原因：
- 性价比最高（价格仅为通义千问的 1/5）
- 代码能力超越 GPT-4o 和 Claude 3.5
- 支持 Function Calling（Agent 构建必需）
- 兼容 OpenAI SDK（零迁移成本，未来可切换到 OpenAI/Anthropic）
- 支持 64K 上下文
- 可开源私有部署

**备选**：通义千问-Max（多模态/数学强）、Kimi（长文本/Agent场景）

### 2.2 图像生成 AI

| 服务商 | 模型 | 价格 | 速度 | 特点 |
|--------|------|------|------|------|
| **通义万相** | wan2.2-t2i-plus | 按量计费 | 2-5s | 中文提示词最佳，高分辨率200万像素 |
| 可图/可灵 | Kolors 2.0 | ¥0.05/次 | 5-10s | DiT架构，4K细节，局部重绘 |
| 百度文心 | 一格 | 按量计费 | 3-8s | 集成百度生态 |
| Stability AI | SDXL/SD3 | $0.002-0.05/次 | 3-10s | 开源可私有部署 |

**首选方案**：**通义万相** — 中文提示词支持最好，速度快，阿里云生态

### 2.3 3D 模型生成 AI

| 服务商 | 模型 | 模式 | 价格 | 特点 |
|--------|------|------|------|------|
| **Tripo3D** | v2.5/v3.0 | 文字/图片→3D | $0.01/credit | 中国团队，2秒生成，Python SDK，650万用户 |
| Meshy | v4 | 文字/图片→3D | 订阅制 | 干净拓扑，适合动画 |
| Rodin AI | - | 文字/图片→3D | 按需 | 几何编辑能力强 |

**首选方案**：**Tripo3D** — 原因：
- 中国团队开发，国内访问友好
- 官方 Python SDK (`pip install tripo3d`)
- 支持 Text→3D、Image→3D、Multi-view→3D
- 最新 v3.0 雕塑级精度
- API 定价透明（$0.01/credit）
- 输出可直接转为 STL/OBJ

### 2.4 多模态视觉理解

| 服务商 | 模型 | 用途 |
|--------|------|------|
| **通义千问** | Qwen3-VL/Qwen3.5-plus | 分析模型截图、识别解剖结构 |
| 智谱AI | GLM-4V | 图像理解 + 多模态推理 |

**首选**：**Qwen-VL** — 兼容 OpenAI SDK，多模态理解强

### 2.5 AI API 统一接入架构

所有国内 API 均兼容 OpenAI SDK 协议，因此可以：
```python
from openai import OpenAI

# DeepSeek 对话
deepseek = OpenAI(api_key="...", base_url="https://api.deepseek.com")

# 通义千问 多模态
qwen = OpenAI(api_key="...", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

# 统一接口，只需切换 client 和 model
```

## 3. 医学影像与解剖数据集（新增）

| 数据集 | 规模 | 器官 | 格式 | 用途 |
|--------|------|------|------|------|
| CT-ORG (TCIA) | 140 CT | 肺/骨/肝/肾/膀胱 | NIfTI | 基础器官分割 |
| CADS | 22K CT | 167 解剖结构 | NIfTI | 全身解剖 |
| AbdomenAtlas-8K | 5.2K CT | 9 腹部器官 | NIfTI | 腹部器官 |
| TotalSegmentator | - | 117 结构 | NIfTI | 全身CT/MR分割 |

**用途**：NIfTI → 3D Slicer 分割 → STL 导出 → MoldGen 导入 → 模具生成

## 4. 核心技术可行性（更新）

| 技术 | 风险 | 缓解 |
|------|------|------|
| AI 对话控制插板生成 | 中 | DeepSeek Function Calling 成熟，定义清晰的工具接口 |
| AI 3D 模型生成质量 | 中高 | Tripo v3.0 精度提升；生成后必须人工/AI审查+编辑 |
| 医学模型精度要求 | 中 | 定位为教学而非临床诊断，精度要求可适当放宽 |
| AI API 访问稳定性 | 低 | 国内API延迟<100ms；多服务商降级 |
| 复合结构打印/灌注 | 中 | 已有 3Deus Dynamics 等验证工业可行性 |

## 5. 关键技术结论

1. **AI 对话**选用 DeepSeek V3 (性价比+Function Calling)，OpenAI SDK 协议确保可切换
2. **图像生成**选用通义万相 (中文友好)，备选 Kolors/Stability AI
3. **3D 生成**选用 Tripo3D (中国团队+Python SDK+高精度)
4. **多模态**选用 Qwen-VL (解剖结构识别/模型分析)
5. **统一 SDK 协议**：所有 AI 均通过 OpenAI 兼容 SDK 接入，架构统一
6. **医学教具方向**已有工业验证（3Deus Dynamics, ERCP训练模型等）
7. **复合结构**（支撑板+硅胶灌注）是核心差异化，AI 辅助设计是创新点
