from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag_comparison import (
    build_rag_comparison_report,
    render_cases_csv,
    render_metrics_csv,
    render_rag_comparison_markdown,
)


def main() -> int:
    args = parse_args()
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()

    case_validation_report = json.loads(Path(args.case_validation).read_text(encoding="utf-8"))
    tourism_weak_courses = json.loads(Path(args.tourism_weak_courses).read_text(encoding="utf-8"))
    no_rag_report_path = Path(args.no_rag_validation)
    no_rag_validation_report = (
        json.loads(no_rag_report_path.read_text(encoding="utf-8"))
        if no_rag_report_path.exists()
        else None
    )
    report = build_rag_comparison_report(
        case_validation_report,
        tourism_weak_courses,
        no_rag_validation_report,
        generated_at=generated_at,
    )

    output_json = Path(args.output_json)
    output_metrics_csv = Path(args.output_metrics_csv)
    output_cases_csv = Path(args.output_cases_csv)
    output_md = Path(args.output_md)

    for output_path in [output_json, output_metrics_csv, output_cases_csv, output_md]:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_metrics_csv.write_text(render_metrics_csv(report), encoding="utf-8")
    output_cases_csv.write_text(render_cases_csv(report), encoding="utf-8")
    output_md.write_text(render_rag_comparison_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(f"rag_comparison_json={output_json}")
    print(f"rag_comparison_metrics_csv={output_metrics_csv}")
    print(f"rag_comparison_cases_csv={output_cases_csv}")
    print(f"rag_comparison_md={output_md}")
    print(
        "summary="
        f"with_rag_cases:{summary['with_rag_passed_cases']}/{summary['scenario_cases']}, "
        f"checks:{summary['with_rag_passed_checks']}/{summary['with_rag_total_checks']}, "
        f"without_rag:{summary['without_rag_status']}, "
        f"without_rag_checks:{summary.get('without_rag_passed_checks')}/{summary.get('without_rag_total_checks')}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build RAG vs non-RAG comparison reports.")
    parser.add_argument("--case-validation", default="data/recommendation_case_validation_report.json")
    parser.add_argument("--tourism-weak-courses", default="data/tourism_weak_recommendation_courses.json")
    parser.add_argument("--no-rag-validation", default="data/no_rag_baseline_validation_report.json")
    parser.add_argument("--output-json", default="data/rag_comparison_report.json")
    parser.add_argument("--output-metrics-csv", default="data/rag_comparison_metrics.csv")
    parser.add_argument("--output-cases-csv", default="data/rag_comparison_cases.csv")
    parser.add_argument("--output-md", default="docs/rag_comparison_report_20260710.md")
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
