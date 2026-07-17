from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag_goldset import build_draft_goldset, render_goldset_csv  # noqa: E402


def main() -> int:
    args = parse_args()
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    document = build_draft_goldset(generated_at=generated_at)
    json_path = Path(args.output_json)
    csv_path = Path(args.output_csv)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path.write_text(render_goldset_csv(document), encoding="utf-8-sig")
    summary = document["summary"]
    print(f"rag_goldset_json={json_path}")
    print(f"rag_goldset_csv={csv_path}")
    print(f"status={document['status']}")
    print(f"cases={summary['case_count']}, dev={summary['split_counts']['dev']}, test={summary['split_counts']['test']}")
    print(f"approved={summary['approved_case_count']}, pending={summary['pending_case_count']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the review-first Value Together RAG Gold Set v1 draft.")
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--output-json", default="data/rag_goldset_v1.json")
    parser.add_argument("--output-csv", default="data/rag_goldset_v1_review.csv")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
