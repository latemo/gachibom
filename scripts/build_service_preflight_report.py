"""Build the service preflight report for the Jeju Maeum app/API."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.service_preflight import build_service_preflight_report, render_service_preflight_markdown, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_service_preflight_report(
        workspace_root=args.workspace_root,
        generated_at=generated_at,
    )
    write_json(report, args.output)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(render_service_preflight_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(f"service_preflight_report_output={args.output}")
    if args.output_md:
        print(f"service_preflight_report_md={args.output_md}")
    print(
        "summary="
        f"status:{report['overall_status']}, "
        f"checks:{summary['total_checks']}, "
        f"pass:{summary['passed_checks']}, "
        f"warn:{summary['warning_checks']}, "
        f"block:{summary['blocker_checks']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("data/service_preflight_report.json"))
    parser.add_argument("--output-md", type=Path, default=Path("docs/service_preflight_report_20260709.md"))
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
