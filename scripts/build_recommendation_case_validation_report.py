from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.recommendation_case_validation import (
    build_recommendation_case_validation_report,
    render_recommendation_case_validation_markdown,
)


def main() -> int:
    args = parse_args()
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    places = json.loads(Path(args.places).read_text(encoding="utf-8"))
    report = build_recommendation_case_validation_report(
        places,
        generated_at=generated_at,
        limit=args.limit,
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_recommendation_case_validation_markdown(report), encoding="utf-8")
    if args.web_output_json:
        web_output_json = Path(args.web_output_json)
        web_output_json.parent.mkdir(parents=True, exist_ok=True)
        web_output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"recommendation_case_validation_json={output_json}")
    print(f"recommendation_case_validation_md={output_md}")
    if args.web_output_json:
        print(f"recommendation_case_validation_web_json={args.web_output_json}")
    print(
        "summary="
        f"status:{report['summary']['overall_status']}, "
        f"cases:{report['summary']['total_cases']}, "
        f"pass:{report['summary']['passed_cases']}, "
        f"fail:{report['summary']['failed_cases']}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build recommendation case validation JSON and Markdown reports.")
    parser.add_argument("--places", default="data/jeju_accessible_spots.json")
    parser.add_argument("--output-json", default="data/recommendation_case_validation_report.json")
    parser.add_argument("--output-md", default="docs/recommendation_case_validation_report_20260709.md")
    parser.add_argument("--web-output-json", default=None)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--limit", type=int, default=4)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
