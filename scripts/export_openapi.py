"""Export OpenAPI schema from FastAPI app object (no running server needed).

Usage: docker compose exec -T api python scripts/export_openapi.py > packages/api-client/openapi.json
"""

import json
import sys
from pathlib import Path

# Add the api source to path
sys.path.insert(0, "/app")
repo_root = Path(__file__).resolve().parent.parent
api_dir = repo_root / "services" / "api"
if api_dir.exists():
    sys.path.insert(0, str(api_dir))

from src.main import app

if __name__ == "__main__":
    schema = app.openapi()
    content = json.dumps(schema, indent=2) + "\n"
    if len(sys.argv) > 1 and sys.argv[1] in ("-o", "--output") and len(sys.argv) > 2:
        out_file = Path(sys.argv[2])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(content, encoding="utf-8")
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        out_file = Path(sys.argv[1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(content, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(content)
