---
name: moldgen-frontend
description: >-
  Develop MoldGen's React/Three.js/Tauri frontend. Use when working on UI components,
  3D viewport, state management, hooks, or frontend/ TypeScript/TSX files.
---

# MoldGen Frontend Development

## Stack

- React 19, TypeScript 5.9, Vite 8
- 3D: Three.js + @react-three/fiber + @react-three/drei
- State: Zustand 5 (stores in `src/stores/`)
- Data: TanStack React Query 5 (hooks in `src/hooks/`)
- Styling: Tailwind CSS 4 + clsx + tailwind-merge
- Animation: Framer Motion 12
- Icons: Lucide React
- Desktop: Tauri 2

## Project Layout

```
frontend/src/
├── App.tsx              # Root layout
├── main.tsx             # Entry point
├── components/
│   ├── layout/          # LeftPanel, Toolbar, etc.
│   ├── viewer/          # 3D viewport, simulation viewer
│   ├── ai/              # ChatBubble, AgentWorkstation
│   └── settings/        # SettingsDialog
├── stores/              # Zustand stores (appStore, modelStore, moldStore, aiStore, etc.)
├── hooks/               # React Query hooks (useModelApi, useMoldApi, useAgentApi, etc.)
└── lib/                 # Utility functions (cn)
```

## Conventions

- Functional components only, no class components
- Zustand stores: flat state + actions in the same `create()` call
- API hooks pattern: `useQuery` for reads, `useMutation` for writes
- API base: `/api/v1/` (proxied to FastAPI backend)
- Tailwind utility classes; use `cn()` from `lib/utils` for conditional classes
- CSS variables for theme colors: `bg-bg-panel`, `text-text-primary`, `border-border`, `text-accent`
- Motion: `framer-motion` for transitions and animations
- All labels/text in Chinese (面向中国用户)

## Component Patterns

- Reusable controls: `SettingSlider`, `SettingSelect`, `SettingToggle`, `InfoRow` in SettingsDialog
- 3D components use R3F declarative pattern with `<Canvas>`, `<mesh>`, etc.
- Agent-related UI connects to `aiStore` and `useAgentApi` hooks
