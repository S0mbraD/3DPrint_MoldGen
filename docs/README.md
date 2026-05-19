# MoldGen 文档中心

> 📖 [← 返回项目主页](../README.md)

MoldGen 的完整技术文档。按阅读顺序和用途分为四大类。

---

## 🚀 快速入门

| 文档 | 说明 |
|------|------|
| [部署与使用指南](09-deployment.md) | 环境要求、安装部署、界面操作、快捷键、AI 配置、FAQ |
| [项目 README](../README.md) | 项目简介、快速安装、功能亮点 |

---

## 🏗️ 系统设计

核心设计文档，理解 MoldGen 的架构和算法。

| # | 文档 | 内容概要 |
|---|------|---------|
| 02 | [系统架构设计](02-architecture.md) | 整体架构、前后端分层、模块依赖、数据流、6 大 Agent 体系 |
| 03 | [核心算法设计](03-algorithms.md) | 脱模分析 · 分型面 · 模具壳体 · 灌注仿真 · 蒙皮模具 · SDF 引擎 |
| 04 | [模块详细设计](04-modules.md) | 各模块接口、功能矩阵、API 端点一览、前端组件映射 |
| 08 | [Agent 系统设计](08-agent-system.md) | 6 大内置 Agent 详细设计、ToolRegistry、执行引擎、工作流示例 |
| 11 | [自适应分型面](11-adaptive-parting.md) | 倒扣分析 + 高度场/投影分型面的自适应算法 |

### 算法文档快速导航

`03-algorithms.md` 包含以下核心算法章节:

1. 脱模方向分析（Fibonacci 采样 + GPU 加速）
2. 分型线/面生成（平面 + 自适应）
3. 模具壳体构建（法线偏移 + Boolean 分壳）
4. 浇注系统设计（BFS 填充 + 流道优化）
5. 灌注仿真（L1 启发式 + L2 达西流）
6. 内嵌支撑板（仿形 + 晶格 + 网孔雕刻）
7. SDF 隐式场引擎 + 拓扑优化
8. 3D 晶格生成（TPMS + Voronoi）
9. 仿真可视化（流线 + 粒子 + 热力图着色器）
10. **蒙皮模具系统 v2**（模芯 + 变厚度 + 定位 + 支撑柱）
11. 自动优化算法

---

## 📋 参考资料

| # | 文档 | 内容概要 |
|---|------|---------|
| 01 | [技术调研与竞品分析](01-research.md) | 竞品对比、AI API 调研、医学教具制造工艺 |
| 05 | [技术栈选型](05-tech-stack.md) | Conda 环境、trimesh/manifold3d、AI SDK、国内 API |
| 10 | [本地模型部署](10-local-models.md) | 本地 AI 模型配置 |

---

## 🛠️ 开发者资源

| # | 文档 | 内容概要 |
|---|------|---------|
| 06 | [开发路线图](06-roadmap.md) | 完整开发计划（P0~P7，23-28 周） |
| 07 | [AI 开发指令](07-ai-prompts.md) | AI 辅助开发的 Prompt 模板库 |
| — | [错误与教训记录](error-log.md) | 开发过程中的典型问题、根因分析、修复方案 |
| — | [变更日志](../CHANGELOG.md) | 版本发布记录 |
| — | [贡献指南](../CONTRIBUTING.md) | 代码规范、提交流程、分支策略 |

---

## 📁 文件索引

```
docs/
├── README.md                ← 你在这里
├── 01-research.md           # 技术调研与竞品分析
├── 02-architecture.md       # 系统架构设计
├── 03-algorithms.md         # 核心算法设计 (★ 最核心)
├── 04-modules.md            # 模块详细设计
├── 05-tech-stack.md         # 技术栈选型
├── 06-roadmap.md            # 开发路线图
├── 07-ai-prompts.md         # AI 开发指令
├── 08-agent-system.md       # Agent 系统设计
├── 09-deployment.md         # 部署与使用指南 (★ 入门首读)
├── 10-local-models.md       # 本地模型部署
├── 11-adaptive-parting.md   # 自适应分型面
└── error-log.md             # 错误与教训记录
```

---

## 相关链接

- [项目主页](../README.md)
- [变更日志](../CHANGELOG.md)
- [贡献指南](../CONTRIBUTING.md)
- [安全策略](../SECURITY.md)
- [MIT 许可证](../LICENSE)
