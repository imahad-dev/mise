# Architecture Decisions

## ADR-001: Same-Origin Proxy (No CORS)

Both Next.js apps rewrite their allowed `/api/*` paths to the FastAPI backend.
This eliminates CORS configuration entirely. Cookies are same-origin and just work.

**Trade-off:** Next.js proxy may buffer SSE responses. Mitigated by:
1. Debug SSE endpoint (`/debug/sse`) to test streaming in M0
2. Raised rewrite timeout for SSE paths
3. Caddy reverse proxy as fallback (`Caddyfile` in repo root)

## ADR-002: proxy.ts (Next.js 16)

Next.js ~15 uses `rewrites` in `next.config.ts`. If upgrading to Next 16, the
proxy mechanism may change to a `proxy.ts` file. See Next.js RFC for details.
Pin to ~15 until migration is explicitly planned.

## ADR-003: Caddy Fallback

If the Next.js rewrite proxy buffers SSE:
1. Uncomment the `caddy` service in `docker-compose.yml`
2. Access guest at `:8080`, owner at `:8081`
3. Caddy uses `flush_interval -1` to disable buffering on SSE paths

## ADR-004: Server-Side Payload Hash

The server computes the canonical `payload_hash` from the order payload.
This ensures a single source of truth — the client only sends an `idempotency_key`.
Same key with a different payload returns 409 Conflict.

## ADR-005: Allergen Status Precedence

`contains > unverified > no_declared_match`

If an item's allergens overlap with the guest's `allergens_to_avoid`, status is
`contains` regardless of verification status. Otherwise, if `allergen_verified`
is false, status is `unverified`. Only verified items with no overlap get
`no_declared_match`. This precedence is pinned in shared test vectors.
