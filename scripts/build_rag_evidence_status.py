from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag_evidence_status import (  # noqa: E402
    build_rag_evidence_status,
    render_rag_evidence_status_markdown,
)


def main() -> int:
    args = parse_args()
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_rag_evidence_status(
        load_json(args.policy_report),
        load_json(args.explanation_report),
        load_json(args.human_report),
        load_json(args.goldset),
        load_json(args.goldset_evaluation),
        generated_at=generated_at,
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_rag_evidence_status_markdown(report), encoding="utf-8")
    print(f"rag_evidence_status_json={output_json}")
    print(f"rag_evidence_status_md={output_md}")
    print(f"status={report['status']}")
    print(f"goldset={report['current_evidence']['goldset']['approved_cases']}/{report['current_evidence']['goldset']['total_cases']}")
    return 0


def load_json(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a single honest RAG evidence status report.")
    parser.add_argument("--policy-report", default="data/rag_comparison_report.json")
    parser.add_argument("--explanation-report", default="data/explanation_eval_results.json")
    parser.add_argument("--human-report", default="data/explanation_eval_human_summary.json")
    parser.add_argument("--goldset", default="data/rag_goldset_v1.json")
    parser.add_argument("--goldset-evaluation", default="data/rag_goldset_evaluation_report.json")
    parser.add_argument("--output-json", default="data/rag_evidence_status.json")
    parser.add_argument("--output-md", default="docs/rag_evidence_status_20260715.md")
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
