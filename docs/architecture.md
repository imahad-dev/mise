# Mise Architecture

> See `mise-foundation.md` for the full implementation plan.

## Services

| Service | Port | Description |
|---------|------|-------------|
| **api** | 8000 | FastAPI backend (Python 3.11) |
| **guest-web** | 3000 | Next.js ~15 guest PWA |
| **owner-web** | 3001 | Next.js ~15 owner dashboard + kitchen |
| **inference** | 8080 | Mock OpenAI-compatible inference server |
| **postgres** | 5432 (dev only) | PostgreSQL 16 |
| **redis** | 6379 (dev only) | Redis 7 |

## Data Flow

```
Guest → QR scan → guest-web → /api/guest/* → api → postgres
                                                  → redis (pub)
Kitchen ← owner-web ← /api/restaurants/*/kitchen/* ← api ← redis (sub/SSE)
Owner ← owner-web ← /api/restaurants/* ← api ← postgres
```

## Proxy Architecture

Both Next.js apps proxy their allowed `/api/*` paths to the FastAPI backend.
No CORS needed — all requests are same-origin from the browser's perspective.

- **guest-web** proxies: `/api/guest/*`, `/api/orders/*`
- **owner-web** proxies: `/api/auth/*`, `/api/restaurants/*`, `/api/metrics/*`
