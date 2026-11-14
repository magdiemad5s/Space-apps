"""Run the saved local models offline; this command never trains models."""
import argparse
import json
from pathlib import Path

from .features import build_request_from_history
from .service import ModelService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Flat request JSON, or a raw-history JSON with --history")
    parser.add_argument("--history", action="store_true", help="Derive baseline/history from earlier observations")
    parser.add_argument("--model", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts/bundle.joblib")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text())
    if args.history:
        payload = build_request_from_history(payload["current"], payload["calibration_history"], payload["recent_history"])
    result = ModelService(args.model).predict(payload)
    rendered = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
