from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag_goldset_evaluation import build_goldset_evaluation_report  # noqa: E402


def main() -> int:
    args = parse_args()
    goldset = json.loads(Path(args.goldset).read_text(encoding="utf-8-sig"))
    run_path = Path(args.runs)
    records = load_jsonl(run_path) if run_path.exists() else []
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_goldset_evaluation_report(goldset, records, generated_at=generated_at)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"rag_goldset_report={output_path}")
    print(f"status={report['status']}")
    print(f"reportable={str(report['reportable']).lower()}")
    print(
        f"approved={report['coverage']['approved_cases']}/{report['coverage']['total_cases']}, "
        f"runs={report['coverage']['run_record_count']}"
    )
    return 0


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}: {path}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL line {line_number} must be an object: {path}")
        rows.append(value)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score approved Gold Set v1 run records.")
    parser.add_argument("--goldset", default="data/rag_goldset_v1.json")
    parser.add_argument("--runs", default="data/rag_goldset_run_records.jsonl")
    parser.add_argument("--output", default="data/rag_goldset_evaluation_report.json")
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
