<p align="center">
  <img src="assets/logo-placeholder.svg" alt="MoldGen Logo" width="120" />
</p>

<h1 align="center">MoldGen</h1>

<p align="center">
  <strong>AI 驱动的医学教具智能模具生成桌面工作站</strong>
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4.svg" alt="Platform" />
  <img src="https://img.shields.io/badge/python-3.11-3776ab.svg" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/node-%3E%3D18-339933.svg" alt="Node.js ≥18" />
  <img src="https://img.shields.io/badge/Tauri-2.0-ffc131.svg" alt="Tauri 2.0" />
  <img src="https://img.shields.io/badge/CUDA-12.x-76b900.svg" alt="CUDA" />
</p>

<p align="center">
  <a href="./docs/README.md">📖 文档中心</a> ·
  <a href="./docs/09-deployment.md">🚀 部署指南</a> ·
  <a href="./CHANGELOG.md">📋 变更日志</a> ·
  <a href="./CONTRIBUTING.md">🤝 贡献指南</a> ·
  <a href="./docs/06-roadmap.md">🗺️ 路线图</a>
</p>

---

## 项目简介

MoldGen 是一款面向 **临床教学与手术教具开发** 的 AI 驱动智能模具生成工作站。通过深度融合 AI 对话、AI 图像/3D 生成能力与专业的模具设计算法，实现从需求描述到可 FDM 3D 打印模具的全自动化流程。

```
AI 对话描述需求 → AI 生成3D模型 → 脱模方向分析 → 模具壳体生成
       │                                                    │
       └── 或直接导入 STL/OBJ/3MF/STEP/医学影像 ───────────┘
                                                             ▼
浇注系统设计 ← 内嵌支撑板生成 ← 蒙皮模芯生成 ← GPU灌注仿真 → 多格式导出
```

### 核心应用场景

- **病理器官模型** — 肿瘤、病变组织、异常解剖结构的硅胶教具
- **手术训练模型** — 供手术技能训练的多材料复合结构模型
- **定制化教具** — 根据 CT/MRI 影像数据定制的患者特异性模型
- **软硬结合教具** — 硅胶蒙皮 + 3D 打印硬质模芯的复合结构（如手臂模型）

---

## 功能亮点

<table>
<tr>
<td width="50%">

**🤖 AI 原生集成**
- AI 悬浮球 + Agent 工作站
- 6 大内置 Agent 全自动流水线
- 对话即可生成教具模型

</td>
<td width="50%">

**🔬 专业模具算法**
- 自适应脱模方向分析
- 多片壳模具 + 5 种分型面样式
- 蒙皮模具系统（模芯 + 外模 + 定位特征）

</td>
</tr>
<tr>
<td>

**🧩 nTopology 级分析**
- SDF 隐式场引擎 + SIMP 拓扑优化
- 3D 晶格（BCC/FCC/Octet + 7 种 TPMS）
- 壁厚/曲率/拔模/对称/悬垂/网格质量分析

</td>
<td>

**🏭 完整制造链**
- 内嵌支撑板（仿形板 + 5 种锚固 + 11 种网孔）
- 达西流灌注仿真 + 缺陷检测 + 自动优化
- GPU 加速（CUDA/WebGPU）

</td>
</tr>
</table>

> 📖 完整功能列表见 [模块详细设计](docs/04-modules.md) | 算法原理见 [核心算法文档](docs/03-algorithms.md)

---

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                  Tauri 2.0 桌面应用层                     │
├────────────────────────┬────────────────────────────────┤
│   React 19 + Three.js  │       FastAPI + trimesh        │
│   TypeScript 前端       │       Python 后端              │
│                        │                                │
│  · Zustand 状态管理     │  · core/  几何算法引擎          │
│  · TanStack Query      │  · gpu/   CUDA 计算层          │
│  · @react-three/fiber  │  · ai/    Agent 系统           │
│  · Tailwind CSS v4     │  · api/   REST API             │
├────────────────────────┴────────────────────────────────┤
│            CUDA 12.x / WebGPU 加速层                     │
└─────────────────────────────────────────────────────────┘
```

> 📖 详细架构见 [系统架构设计](docs/02-architecture.md) | 技术栈见 [技术栈选型](docs/05-tech-stack.md)

---

## 快速开始

### 环境要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| OS | Windows 10 | Windows 11 |
| CPU | Intel i5 | Intel i7 / AMD Ryzen 7 |
| GPU | GTX 1060 (6GB) | RTX 4060 Ti (16GB) |
| RAM | 16 GB | 32 GB |

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/moldgen.git
cd moldgen

# 2. 创建 Conda 环境
conda create -n moldgen python=3.11 -y
conda activate moldgen

# 3. 安装后端依赖
pip install -e ".[dev]"

# 4. 安装 GPU 加速 (需 NVIDIA GPU)
conda install -y -c nvidia cuda-toolkit=12.8
conda install -y -c conda-forge numba
pip install cupy-cuda12x

# 5. 配置 AI API (可选)
cp .env.example .env    # 编辑 .env 填入 API Key

# 6. 启动后端
python -m uvicorn moldgen.main:app --reload
# API 文档: http://127.0.0.1:8000/docs

# 7. 启动前端
cd frontend && npm install && npm run dev
# 前端: http://localhost:1420
```

> 📖 完整部署教程见 [部署与使用指南](docs/09-deployment.md)

---

## 项目结构

```
moldgen/                    # Python 后端
├── main.py                 # FastAPI 入口
├── config.py               # 配置管理
├── api/routes/             # REST API 路由
├── core/                   # 几何/模具/分析/仿真引擎
│   ├── mold_builder.py     #   模具壳体生成
│   ├── skin_mold.py        #   蒙皮模具系统
│   ├── insert_generator.py #   内嵌支撑板
│   ├── flow_sim.py         #   灌注仿真
│   ├── gating.py           #   浇注系统
│   ├── orientation.py      #   脱模方向分析
│   ├── distance_field.py   #   SDF 隐式场引擎
│   ├── lattice.py          #   3D 晶格生成器
│   └── ...
├── gpu/                    # CUDA 计算层
└── ai/                     # Agent 系统 (6 大 Agent)

frontend/                   # React + Three.js 前端
├── src/
│   ├── components/         # UI 组件
│   ├── hooks/              # TanStack Query hooks
│   └── stores/             # Zustand 状态管理
└── src-tauri/              # Tauri 桌面封装

docs/                       # 项目文档 (→ docs/README.md)
tests/                      # 测试套件
```

---

## 文档中心

所有文档位于 [`docs/`](docs/README.md) 目录，按类别组织：

| 类别 | 文档 | 说明 |
|------|------|------|
| **入门** | [部署与使用指南](docs/09-deployment.md) | 安装、启动、界面操作、快捷键 |
| **设计** | [系统架构](docs/02-architecture.md) | 整体架构、6 大 Agent 体系 |
| | [核心算法](docs/03-algorithms.md) | 脱模分析、模具生成、仿真、蒙皮模具 |
| | [模块设计](docs/04-modules.md) | 各模块接口与功能矩阵 |
| | [Agent 系统](docs/08-agent-system.md) | Agent 详细设计与工作流示例 |
| **参考** | [技术栈选型](docs/05-tech-stack.md) | Conda、AI SDK、国内 API 选型 |
| | [技术调研](docs/01-research.md) | 竞品分析、医学教具制造调研 |
| | [自适应分型面](docs/11-adaptive-parting.md) | 自适应分型面算法详解 |
| **开发** | [开发路线图](docs/06-roadmap.md) | 完整开发计划 |
| | [AI 开发指令](docs/07-ai-prompts.md) | AI 辅助开发 Prompt 模板 |
| | [错误与教训](docs/error-log.md) | 开发过程中的问题记录 |

---

## 开发进度

| Phase | 状态 | 内容 |
|-------|------|------|
| P0 基础设施 | ✅ | Conda + GPU + Tauri 骨架 + AI API |
| P1 模型处理 | ✅ | 多格式导入/修复/编辑 + 3D 视口 |
| P2 模具生成 | ✅ | 方向分析 + 分型面 + 双片壳模具 + 紧固件 |
| P3 仿真优化 | ✅ | 材料库 + 达西流仿真 + 缺陷检测 + 自动优化 |
| P4 AI+Agent | ✅ | 6 大 Agent + 意图路由 + 流水线模板 |
| P5 支撑板 | ✅ | 4 种板型 + 5 种锚固 + 立柱系统 |
| P6 桌面完善 | ✅ | 多格式导出 + UI 增强 + nTopology 级分析 |
| P7 发布 | ⏳ | 集成测试 / 打包 / 文档完善 |

> 📖 详细路线图见 [开发路线图](docs/06-roadmap.md) | 完整变更记录见 [CHANGELOG.md](CHANGELOG.md)

---

## 参与贡献

欢迎各种形式的贡献！请先阅读 [贡献指南](CONTRIBUTING.md)。

- 🐛 **报告 Bug** — [创建 Issue](../../issues/new?template=bug_report.md)
- 💡 **功能建议** — [创建 Issue](../../issues/new?template=feature_request.md)
- 📖 **改进文档** — 直接提交 PR
- 🔧 **代码贡献** — Fork → Branch → PR

---

## 许可证

本项目基于 [MIT License](./LICENSE) 开源。

Copyright © 2026 MoldGen Contributors
