---
name: moldgen-backend
description: >-
  Develop MoldGen's Python/FastAPI backend. Use when working on API routes,
  core geometry algorithms, GPU kernels, configuration, or moldgen/ Python files.
---

# MoldGen Backend Development

## Stack

- Python 3.11+, FastAPI, Pydantic v2, uvicorn
- Geometry: trimesh, manifold3d, open3d, scipy, scikit-image
- GPU: numba CUDA JIT, CuPy, cubvh
- AI: openai SDK (compatible with DeepSeek/Qwen/Kimi), dashscope
- DB: SQLAlchemy + aiosqlite
- Linting: ruff (line-length 100, target py311)

## Project Layout

```
moldgen/
├── main.py          # FastAPI app factory + lifespan
├── config.py        # Pydantic settings (ServerConfig, AIConfig, GPUConfig)
├── __init__.py      # Package version
├── api/
│   ├── routes/      # FastAPI routers (system, models, molds, simulation, inserts, export, ai_chat, ai_agent)
│   └── websocket.py # WebSocket handlers
├── core/            # Geometry & algorithm modules
├── gpu/             # CUDA kernels and GPU device management
├── ai/              # Agent system (see moldgen-agent-dev skill)
├── models/          # SQLAlchemy ORM
└── utils/           # Logger, helpers
```

## API Route Conventions

- Prefix: `/api/v1/{domain}/`
- Use `APIRouter()`, register in `moldgen/api/routes/__init__.py`
- Request/response: Pydantic `BaseModel`
- Async handlers preferred
- Error responses: `HTTPException` with status code

## Core Module Patterns

- Pure functions operating on numpy arrays and trimesh meshes
- GPU functions in `moldgen/gpu/` with CPU fallback in `moldgen/gpu/fallback.py`
- Config via `moldgen.config.get_config()` singleton
- Logging: `logging.getLogger(__name__)`

## Testing

- pytest in `tests/` directory
- Run: `pytest` or `pytest tests/test_agent.py -v`
