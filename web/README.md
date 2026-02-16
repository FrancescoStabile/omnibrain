# OmniBrain Web UI

Next.js 15 + shadcn/ui + Tailwind CSS — the browser-first interface for OmniBrain.

> **Status**: Scaffolding only. Real implementation starts Day 6 of the sprint.

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 15 (App Router) |
| UI Components | shadcn/ui + Radix |
| Styling | Tailwind CSS 4 |
| Auth | JWT (from Python API) |
| State | Zustand |
| Real-time | Server-Sent Events |

## Getting Started

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

The API server must be running:
```bash
omnibrain serve    # http://localhost:8340
```

## Directory Structure (planned)

```
web/
├── app/
│   ├── layout.tsx           # Root layout with providers
│   ├── page.tsx             # Main chat interface
│   ├── login/page.tsx       # JWT auth
│   ├── skills/page.tsx      # Skill marketplace
│   └── settings/page.tsx    # Configuration
├── components/
│   ├── chat/                # Chat interface components
│   ├── skills/              # Skill cards, install flow
│   └── ui/                  # shadcn/ui components
├── lib/
│   ├── api.ts               # API client (SSE streams)
│   └── auth.ts              # JWT token management
├── package.json
├── next.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

## Design Reference

See [docs/UX-BIBLE.md](../docs/UX-BIBLE.md) for the complete design system.
