"""Run the roadview visual review decision pipeline end to end."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_request_tracker import build_data_request_tracker, export_data_request_tracker_csv
from src.operations_readiness import build_operations_readiness_report
from src.roadview_image_download import write_json
from src.roadview_missing_image_recovery import (
    build_roadview_missing_image_recovery_report,
    render_roadview_missing_image_recovery_markdown,
)
from src.roadview_new_candidates import (
    apply_roadview_visual_review_sheet,
    build_service_seed_active_candidates,
    build_service_seed_gate_status,
    build_service_seed_promotion_readiness,
)
from src.roadview_review_exports import (
    apply_visual_review_decision_csv,
    build_roadview_visual_review_board_html,
    load_json,
    write_text,
)
from src.service_launch_actions import (
    build_service_launch_action_plan,
    render_service_launch_action_plan_markdown,
)
from src.service_preflight import build_service_preflight_report, render_service_preflight_markdown


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    reviewed_at = date.fromisoformat(args.reviewed_at) if args.reviewed_at else generated_at

    provider_404_report = load_optional_json(args.provider_404_report)
    recovery_summary = {}
    recovery_outputs: dict[str, Path] = {}
    if provider_404_report:
        missing_image_recovery = build_roadview_missing_image_recovery_report(
            provider_404_report,
            receipt_root=args.receipt_root,
            generated_at=generated_at,
            hash_files=not args.skip_recovery_hash,
        )
        write_json(missing_image_recovery, args.missing_image_recovery_output)
        recovery_summary = missing_image_recovery["summary"]
        recovery_outputs["missing_image_recovery"] = args.missing_image_recovery_output
        if args.missing_image_recovery_md_output:
            write_text(
                render_roadview_missing_image_recovery_markdown(missing_image_recovery),
                args.missing_image_recovery_md_output,
            )
            recovery_outputs["missing_image_recovery_md"] = args.missing_image_recovery_md_output

    visual_sheet = load_json(args.visual_review_sheet)
    decision_result = apply_visual_review_decision_csv(
        visual_sheet,
        args.decisions_csv,
        reviewer=args.reviewer,
        reviewed_at=reviewed_at,
        generated_at=generated_at,
    )
    import_report = decision_result["import_report"]
    write_json(import_report, args.decision_import_report_output)

    if import_report["summary"]["invalid"]:
        pipeline_report = build_pipeline_report(
            generated_at=generated_at,
            status="blocked_invalid_decisions",
            summaries={
                **({"missing_image_recovery": recovery_summary} if recovery_summary else {}),
                "decision_import": import_report["summary"],
            },
            outputs={
                **recovery_outputs,
                "decision_import_report": args.decision_import_report_output,
            },
            next_action="CSV의 invalid 행을 수정한 뒤 파이프라인을 다시 실행",
        )
        write_json(pipeline_report, args.pipeline_report_output)
        print(f"decision_import_report_output={args.decision_import_report_output}")
        print(f"visual_review_pipeline_report_output={args.pipeline_report_output}")
        print(
            "summary="
            f"status:{pipeline_report['status']}, "
            f"invalid:{import_report['summary']['invalid']}, "
            f"applied:0"
        )
        return 1

    updated_visual_sheet = decision_result["updated_visual_review_sheet"]
    write_json(updated_visual_sheet, args.visual_review_sheet_output)

    image_apply = apply_roadview_visual_review_sheet(
        load_json(args.roadview_image_review),
        updated_visual_sheet,
        generated_at=generated_at,
    )
    updated_image_review = image_apply["updated_roadview_image_review"]
    visual_apply_report = image_apply["apply_report"]
    write_json(updated_image_review, args.roadview_image_review_output)
    write_json(visual_apply_report, args.visual_apply_report_output)

    promotion_readiness = build_service_seed_promotion_readiness(
        load_json(args.seed_cards),
        load_json(args.work_queue),
        load_json(args.official_source_review),
        updated_image_review,
        load_optional_json(args.crowd_policy_review),
        load_optional_json(args.category_refinement_review),
        generated_at=generated_at,
    )
    write_json(promotion_readiness, args.promotion_readiness_output)

    active_result = build_service_seed_active_candidates(
        load_json(args.seed_cards),
        promotion_readiness,
        load_json(args.official_source_review),
        load_optional_json(args.category_refinement_review),
        generated_at=generated_at,
    )
    write_json(active_result["active_candidates"], args.active_candidates_output)
    write_json(active_result["promotion_report"], args.active_candidate_report_output)

    gate_status = build_service_seed_gate_status(
        load_json(args.acquisition_request),
        load_json(args.receipt_report),
        load_json(args.image_asset_manifest),
        updated_visual_sheet,
        promotion_readiness,
        active_result["promotion_report"],
        generated_at=generated_at,
    )
    write_json(gate_status, args.gate_status_output)

    data_request_tracker = build_data_request_tracker(
        acquisition_request=load_json(args.acquisition_request),
        receipt_report=load_json(args.receipt_report),
        service_seed_gate_status=gate_status,
        generated_at=generated_at,
        workspace_root=ROOT,
    )
    write_json(data_request_tracker, args.data_request_tracker_output)
    export_data_request_tracker_csv(data_request_tracker, args.data_request_tracker_csv_output)

    operations_readiness = build_operations_readiness_report(
        load_json(args.place_cards),
        data_request_tracker,
        gate_status,
        generated_at=generated_at,
        workspace_root=ROOT,
    )
    write_json(operations_readiness, args.operations_readiness_output)
    if args.operations_readiness_web_output:
        write_json(operations_readiness, args.operations_readiness_web_output)

    service_launch_action_plan = build_service_launch_action_plan(
        operations_readiness,
        gate_status,
        provider_404_report or {},
        load_json(args.receipt_report),
        updated_visual_sheet,
        generated_at=generated_at,
    )
    write_json(service_launch_action_plan, args.service_launch_action_plan_output)
    if args.service_launch_action_plan_md_output:
        write_text(
            render_service_launch_action_plan_markdown(service_launch_action_plan),
            args.service_launch_action_plan_md_output,
        )
    if args.service_launch_action_plan_web_output:
        write_json(service_launch_action_plan, args.service_launch_action_plan_web_output)

    service_preflight = build_service_preflight_report(
        workspace_root=ROOT,
        generated_at=generated_at,
    )
    write_json(service_preflight, args.service_preflight_output)
    if args.service_preflight_md_output:
        write_text(render_service_preflight_markdown(service_preflight), args.service_preflight_md_output)

    board_html = build_roadview_visual_review_board_html(
        updated_visual_sheet,
        provider_404_report=provider_404_report,
        output_path=args.visual_review_board_output,
        generated_at=generated_at,
    )
    write_text(board_html, args.visual_review_board_output)

    summaries = {
        **({"missing_image_recovery": recovery_summary} if recovery_summary else {}),
        "decision_import": import_report["summary"],
        "visual_apply": visual_apply_report["summary"],
        "promotion_readiness": promotion_readiness["summary"],
        "active_candidates": active_result["promotion_report"]["summary"],
        "gate_status": gate_status["summary"],
        "operations_readiness": operations_readiness["summary"],
        "service_launch_action_plan": service_launch_action_plan["summary"],
        "service_preflight": service_preflight["summary"],
    }
    outputs = {
        **recovery_outputs,
        "visual_review_sheet": args.visual_review_sheet_output,
        "decision_import_report": args.decision_import_report_output,
        "roadview_image_review": args.roadview_image_review_output,
        "visual_apply_report": args.visual_apply_report_output,
        "promotion_readiness": args.promotion_readiness_output,
        "active_candidates": args.active_candidates_output,
        "active_candidate_report": args.active_candidate_report_output,
        "gate_status": args.gate_status_output,
        "data_request_tracker": args.data_request_tracker_output,
        "data_request_tracker_csv": args.data_request_tracker_csv_output,
        "operations_readiness": args.operations_readiness_output,
        **({"operations_readiness_web": args.operations_readiness_web_output} if args.operations_readiness_web_output else {}),
        "service_launch_action_plan": args.service_launch_action_plan_output,
        **(
            {"service_launch_action_plan_md": args.service_launch_action_plan_md_output}
            if args.service_launch_action_plan_md_output
            else {}
        ),
        **(
            {"service_launch_action_plan_web": args.service_launch_action_plan_web_output}
            if args.service_launch_action_plan_web_output
            else {}
        ),
        "service_preflight": args.service_preflight_output,
        **({"service_preflight_md": args.service_preflight_md_output} if args.service_preflight_md_output else {}),
        "visual_review_board": args.visual_review_board_output,
    }
    pipeline_report = build_pipeline_report(
        generated_at=generated_at,
        status="completed",
        summaries=summaries,
        outputs=outputs,
        next_action=operations_readiness["summary"].get("next_action", ""),
    )
    write_json(pipeline_report, args.pipeline_report_output)

    print(f"visual_review_sheet_output={args.visual_review_sheet_output}")
    print(f"roadview_image_review_output={args.roadview_image_review_output}")
    print(f"visual_review_pipeline_report_output={args.pipeline_report_output}")
    print(
        "summary="
        f"status:{pipeline_report['status']}, "
        f"decision_applied:{import_report['summary']['applied']}, "
        f"visual_applied:{visual_apply_report['summary']['by_action'].get('applied', 0)}, "
        f"ready:{gate_status['summary']['ready_for_service_activation_count']}, "
        f"blocked:{gate_status['summary']['blocked_count']}"
    )
    return 0


def build_pipeline_report(
    *,
    generated_at: date,
    status: str,
    summaries: dict[str, Any],
    outputs: dict[str, Path],
    next_action: str,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at.isoformat(),
        "status": status,
        "summary": summaries,
        "outputs": {name: str(path).replace("\\", "/") for name, path in outputs.items()},
        "next_action": next_action,
    }


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path and path.exists():
        return load_json(path)
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-review-sheet", type=Path, default=Path("data/roadview_visual_review_sheet.json"))
    parser.add_argument("--decisions-csv", type=Path, default=Path("data/roadview_visual_review_decisions.csv"))
    parser.add_argument("--roadview-image-review", type=Path, default=Path("data/roadview_image_review.json"))
    parser.add_argument("--seed-cards", type=Path, default=Path("data/roadview_service_seed_cards.review.json"))
    parser.add_argument("--work-queue", type=Path, default=Path("data/roadview_service_seed_work_queue.json"))
    parser.add_argument("--official-source-review", type=Path, default=Path("data/roadview_official_source_review.json"))
    parser.add_argument("--crowd-policy-review", type=Path, default=Path("data/roadview_crowd_policy_review.json"))
    parser.add_argument("--category-refinement-review", type=Path, default=Path("data/roadview_category_refinement_review.json"))
    parser.add_argument("--acquisition-request", type=Path, default=Path("data/roadview_image_acquisition_request.json"))
    parser.add_argument("--receipt-report", type=Path, default=Path("data/roadview_image_receipt_report.json"))
    parser.add_argument("--image-asset-manifest", type=Path, default=Path("data/roadview_image_asset_manifest.json"))
    parser.add_argument("--provider-404-report", type=Path, default=Path("data/roadview_provider_404_image_report.json"))
    parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path("data/raw/roadview_images"),
        help="Directory containing delivered roadview image files for provider-404 recovery verification.",
    )
    parser.add_argument("--place-cards", type=Path, default=Path("data/jeju_accessible_spots.json"))
    parser.add_argument(
        "--missing-image-recovery-output",
        type=Path,
        default=Path("data/roadview_missing_image_recovery_report.json"),
    )
    parser.add_argument(
        "--missing-image-recovery-md-output",
        type=Path,
        default=Path("docs/roadview_missing_image_recovery_report_20260709.md"),
    )
    parser.add_argument("--visual-review-sheet-output", type=Path, default=Path("data/roadview_visual_review_sheet.json"))
    parser.add_argument(
        "--decision-import-report-output",
        type=Path,
        default=Path("data/roadview_visual_review_decision_import_report.json"),
    )
    parser.add_argument("--roadview-image-review-output", type=Path, default=Path("data/roadview_image_review.json"))
    parser.add_argument(
        "--visual-apply-report-output",
        type=Path,
        default=Path("data/roadview_visual_review_apply_report.json"),
    )
    parser.add_argument(
        "--promotion-readiness-output",
        type=Path,
        default=Path("data/roadview_service_seed_promotion_readiness.json"),
    )
    parser.add_argument(
        "--active-candidates-output",
        type=Path,
        default=Path("data/roadview_service_seed_active_candidates.json"),
    )
    parser.add_argument(
        "--active-candidate-report-output",
        type=Path,
        default=Path("data/roadview_service_seed_active_candidate_report.json"),
    )
    parser.add_argument("--gate-status-output", type=Path, default=Path("data/roadview_service_seed_gate_status.json"))
    parser.add_argument("--data-request-tracker-output", type=Path, default=Path("data/data_request_tracker.json"))
    parser.add_argument("--data-request-tracker-csv-output", type=Path, default=Path("data/data_request_tracker.csv"))
    parser.add_argument(
        "--operations-readiness-output",
        type=Path,
        default=Path("data/operations_readiness_report.json"),
    )
    parser.add_argument(
        "--operations-readiness-web-output",
        type=Path,
        default=Path("web/data/operations_readiness_report.json"),
    )
    parser.add_argument(
        "--service-launch-action-plan-output",
        type=Path,
        default=Path("data/service_launch_action_plan.json"),
    )
    parser.add_argument(
        "--service-launch-action-plan-md-output",
        type=Path,
        default=Path("docs/service_launch_action_plan_20260709.md"),
    )
    parser.add_argument(
        "--service-launch-action-plan-web-output",
        type=Path,
        default=Path("web/data/service_launch_action_plan.json"),
    )
    parser.add_argument(
        "--service-preflight-output",
        type=Path,
        default=Path("data/service_preflight_report.json"),
    )
    parser.add_argument(
        "--service-preflight-md-output",
        type=Path,
        default=Path("docs/service_preflight_report_20260709.md"),
    )
    parser.add_argument(
        "--visual-review-board-output",
        type=Path,
        default=Path("docs/roadview_visual_review_board.html"),
    )
    parser.add_argument(
        "--pipeline-report-output",
        type=Path,
        default=Path("data/roadview_visual_review_pipeline_report.json"),
    )
    parser.add_argument("--reviewer", default="operator")
    parser.add_argument("--reviewed-at", help="Default review date in YYYY-MM-DD. Defaults to generated-at.")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--skip-recovery-hash", action="store_true", help="Skip SHA-256 hashing for recovered files.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
