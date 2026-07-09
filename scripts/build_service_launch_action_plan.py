"""Build the service launch action plan from current readiness reports."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.service_launch_actions import (
    build_service_launch_action_plan,
    load_json,
    render_service_launch_action_plan_markdown,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    plan = build_service_launch_action_plan(
        load_json(args.operations_readiness),
        load_json(args.service_seed_gate_status),
        load_json(args.provider_404_report),
        load_json(args.image_receipt_report),
        load_json(args.visual_review_sheet),
        generated_at=generated_at,
    )
    write_json(plan, args.output_json)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(render_service_launch_action_plan_markdown(plan), encoding="utf-8")
    if args.web_output_json:
        write_json(plan, args.web_output_json)

    summary = plan["summary"]
    print(f"service_launch_action_plan_json={args.output_json}")
    print(f"service_launch_action_plan_md={args.output_md}")
    if args.web_output_json:
        print(f"service_launch_action_plan_web_json={args.web_output_json}")
    print(
        "summary="
        f"status:{plan['overall_status']}, "
        f"actions:{summary['total_actions']}, "
        f"missing_images:{summary['missing_roadview_images']}, "
        f"visual_review_open:{summary['visual_review_open_places']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operations-readiness",
        type=Path,
        default=Path("data/operations_readiness_report.json"),
        help="Operations readiness report JSON.",
    )
    parser.add_argument(
        "--service-seed-gate-status",
        type=Path,
        default=Path("data/roadview_service_seed_gate_status.json"),
        help="Roadview service seed gate status JSON.",
    )
    parser.add_argument(
        "--provider-404-report",
        type=Path,
        default=Path("data/roadview_provider_404_image_report.json"),
        help="Provider 404 missing roadview image report JSON.",
    )
    parser.add_argument(
        "--image-receipt-report",
        type=Path,
        default=Path("data/roadview_image_receipt_report.json"),
        help="Roadview image receipt report JSON.",
    )
    parser.add_argument(
        "--visual-review-sheet",
        type=Path,
        default=Path("data/roadview_visual_review_sheet.json"),
        help="Roadview visual review sheet JSON.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("data/service_launch_action_plan.json"),
        help="Output action plan JSON.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("docs/service_launch_action_plan_20260709.md"),
        help="Output action plan Markdown.",
    )
    parser.add_argument(
        "--web-output-json",
        type=Path,
        default=Path("web/data/service_launch_action_plan.json"),
        help="Optional app-facing action plan JSON.",
    )
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
