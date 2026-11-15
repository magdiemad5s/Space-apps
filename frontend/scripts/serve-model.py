"""Compatibility entry point for the trusted, unchanged model service.

Prefer the repository-root Start-Astra.cmd or start.sh launcher. Use Python 3.12
and ai/requirements.txt. Model-loading errors are never silently suppressed.
"""
from pathlib import Path
import os
import sys

default_ai = Path(__file__).resolve().parents[2] / "ai"
ai_dir = Path(os.environ.get("ASTRA_AI_DIR", str(default_ai))).resolve()
if not (ai_dir / "astra_shield_ml" / "api.py").is_file():
    sys.exit("Set ASTRA_AI_DIR to the ai directory containing astra_shield_ml/api.py.")
os.chdir(ai_dir)
sys.path.insert(0, str(ai_dir))

if __name__ == "__main__":
    import uvicorn

    # Do not patch XGBoost deserialization or alter the model artifact.
    uvicorn.run("astra_shield_ml.api:app", host="127.0.0.1", port=8000)
