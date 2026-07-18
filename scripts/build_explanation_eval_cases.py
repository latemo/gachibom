from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.explanation_eval_cases import build_explanation_eval_cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic recommendation-explanation evaluation cases."
    )
    parser.add_argument("--seed", default="web/data/app_recommendation_seed.json")
    parser.add_argument("--output", default="-", help="JSON output path, or '-' for stdout.")
    parser.add_argument("--compact", action="store_true", help="Write compact JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    payload = build_explanation_eval_cases(seed)
    encoded = json.dumps(payload, ensure_ascii=False, indent=None if args.compact else 2) + "\n"
    if args.output == "-":
        sys.stdout.write(encoded)
    else:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded, encoding="utf-8")
        print(f"explanation_eval_cases_output={output_path}")
        print(f"summary=scenarios:{payload['scenario_count']}, questions_per_scenario:6, cases:{payload['case_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
