"""Export the live FastAPI schema deterministically; no DB or server required."""
import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "apps/api"))
from app.main import create_app
schema = create_app().openapi()
path = root / "packages/contracts/openapi.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
print(f"Exported {len(schema['paths'])} API paths to {path.relative_to(root)}")
