from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.no_rag_baseline import (
    build_no_rag_baseline_responses,
    build_no_rag_baseline_validation_report,
    render_no_rag_baseline_markdown,
    render_no_rag_cases_csv,
)


def main() -> int:
    args = parse_args()
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    responses = build_no_rag_baseline_responses(generated_at=generated_at)
    report = build_no_rag_baseline_validation_report(responses, generated_at=generated_at)

    output_responses = Path(args.output_responses)
    output_json = Path(args.output_json)
    output_cases_csv = Path(args.output_cases_csv)
    output_md = Path(args.output_md)

    for output_path in [output_responses, output_json, output_cases_csv, output_md]:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_responses.write_text(json.dumps(responses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_cases_csv.write_text(render_no_rag_cases_csv(report), encoding="utf-8")
    output_md.write_text(render_no_rag_baseline_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(f"no_rag_baseline_responses={output_responses}")
    print(f"no_rag_baseline_validation_json={output_json}")
    print(f"no_rag_baseline_cases_csv={output_cases_csv}")
    print(f"no_rag_baseline_md={output_md}")
    print(
        "summary="
        f"cases:{summary['passed_cases']}/{summary['total_cases']}, "
        f"checks:{summary['passed_checks']}/{summary['total_checks']}, "
        f"status:{summary['overall_status']}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build controlled no-RAG baseline response and validation files.")
    parser.add_argument("--output-responses", default="data/no_rag_baseline_responses.json")
    parser.add_argument("--output-json", default="data/no_rag_baseline_validation_report.json")
    parser.add_argument("--output-cases-csv", default="data/no_rag_baseline_validation_cases.csv")
    parser.add_argument("--output-md", default="docs/no_rag_baseline_validation_report_20260710.md")
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
