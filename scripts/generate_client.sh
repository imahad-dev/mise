#!/usr/bin/env bash
set -euo pipefail

# Generate TypeScript API client from FastAPI OpenAPI schema
# Usage: ./scripts/generate_client.sh

echo "=== Exporting OpenAPI schema ==="
docker compose exec -T api python scripts/export_openapi.py > packages/api-client/openapi.json

echo "=== Generating TypeScript types ==="
pnpm --filter api-client generate

echo "✅ Client generated at packages/api-client/src/generated/"
