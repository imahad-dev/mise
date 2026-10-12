"""Export OpenAPI schema from FastAPI app object (no running server needed).

Usage: docker compose exec -T api python scripts/export_openapi.py > packages/api-client/openapi.json
"""

import json
import sys

# Add the api source to path
sys.path.insert(0, "/app")

from src.main import app

if __name__ == "__main__":
    schema = app.openapi()
    print(json.dumps(schema, indent=2))
