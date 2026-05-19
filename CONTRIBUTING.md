# 贡献指南

感谢你对 MoldGen 的关注！我们欢迎各种形式的贡献。

> 📖 回到 [README](README.md) | [文档中心](docs/README.md)

---

## 如何参与

### 🐛 报告 Bug

1. 在 [Issues](../../issues) 中搜索是否已有相同问题
2. 若没有，创建新 Issue 并选择 **Bug 报告** 模板
3. 尽量提供：复现步骤、期望行为、实际行为、截图/日志

### 💡 功能建议

1. 在 [Issues](../../issues) 中创建新 Issue，选择 **功能请求** 模板
2. 描述使用场景和期望功能

### 🔧 代码贡献

1. **Fork** 本仓库
2. 创建功能分支: `git checkout -b feature/your-feature`
3. 编写代码并通过测试
4. 提交 PR 并填写模板

---

## 开发环境搭建

```bash
# 后端
conda create -n moldgen python=3.11 -y
conda activate moldgen
pip install -e ".[dev]"

# 前端
cd frontend
npm install
npm run dev
```

详见 [部署与使用指南](docs/09-deployment.md)。

---

## 代码规范

### 语言约定

| 场景 | 语言 |
|------|------|
| 代码（变量名、函数名、注释） | **English** |
| UI 文本（标签、提示、消息） | **简体中文** |
| 文档 (`docs/`) | **简体中文**（代码示例用英文） |
| Git Commit Message | **English** |

### Python (后端)

- 遵循 PEP 8，行宽 100
- 类型标注: 使用 Python 3.11+ 语法 (`str | None` 而非 `Optional[str]`)
- 日志: `logging.getLogger(__name__)`, 不使用 `print()`
- 错误处理:
  - API 层: `HTTPException`
  - Core 层: 原生异常 + `logging.exception()`
  - GPU 层: 始终提供 CPU fallback

### TypeScript (前端)

- 严格模式 (`strict: true`)
- 状态管理: Zustand flat stores，每个领域一个 store
- API 调用: TanStack Query hooks，每个 API 领域一个文件
- 样式: Tailwind CSS v4

### 架构边界

| 目录 | 规则 |
|------|------|
| `moldgen/core/` | 纯几何算法，无 API、无 AI、无副作用 |
| `moldgen/gpu/` | CUDA 内核 + CPU fallback，始终检测 GPU 可用性 |
| `moldgen/ai/` | Agent 系统，遵循 BaseAgent + ToolRegistry 模式 |
| `moldgen/api/` | FastAPI 路由，薄层调用 core/ai 模块 |
| `frontend/src/stores/` | Zustand flat stores |
| `frontend/src/hooks/` | TanStack Query hooks |

---

## 提交规范

使用语义化提交消息:

```
feat: add variable thickness skin mold generation
fix: pour hole penetrating both sides of mold
docs: update skin mold algorithm documentation
refactor: extract boolean operations into boolean_ops.py
test: add unit tests for core generation pipeline
chore: update dependencies
```

---

## 分支策略

| 分支 | 用途 |
|------|------|
| `main` | 稳定发布分支 |
| `dev` | 开发集成分支 |
| `feature/*` | 功能开发分支 |
| `fix/*` | Bug 修复分支 |

---

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_mold.py -v

# 带覆盖率
pytest tests/ --cov=moldgen --cov-report=html
```

提交 PR 前请确保:
- [ ] 所有已有测试通过
- [ ] 新功能附带测试用例
- [ ] Python 代码通过类型检查
- [ ] 前端代码无 TypeScript 错误

---

## 项目结构速览

```
moldgen/          → Python 后端 (FastAPI + trimesh + CUDA)
frontend/         → React 19 前端 (Three.js + Zustand + Tailwind)
docs/             → 项目文档 (12 篇)
tests/            → 测试套件
.github/          → CI/CD + Issue/PR 模板
```

> 详见 [系统架构设计](docs/02-architecture.md)

---

## 行为准则

- 尊重每一位参与者
- 建设性的讨论和反馈
- 聚焦于技术问题本身

---

## 许可

贡献的代码将采用与项目相同的 [MIT License](./LICENSE)。
