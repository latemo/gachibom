"""Build a consolidated operations readiness report for service launch gates."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


MIN_PLACE_CARDS = 30
MIN_VERIFIED_OR_PARTIAL_RATIO = 0.7
REQUIRED_DOCS = [
    "docs/jeju_maeum_launch_checklist.md",
    "docs/data_request_tracker_workflow.md",
    "docs/service_seed_gate_status_workflow.md",
    "docs/roadview_image_acquisition_guide.md",
]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_operations_readiness_report(
    place_cards: list[dict[str, Any]],
    data_request_tracker: dict[str, Any],
    service_seed_gate_status: dict[str, Any],
    *,
    generated_at: date | None = None,
    workspace_root: str | Path = ".",
) -> dict[str, Any]:
    sections = [
        base_place_catalog_section(place_cards),
        public_data_dependencies_section(data_request_tracker),
        roadview_service_seed_section(service_seed_gate_status),
        operational_documents_section(Path(workspace_root)),
    ]
    checks = [check for section in sections for check in section["checks"]]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "criteria": {
            "ready_for_full_service": "자동 점검에서 blocker가 없고 외부 데이터 의존성이 해소된 상태",
            "ready_with_warnings": "서비스 제한 공개는 가능하지만 운영 보강 warning이 남은 상태",
            "blocked_for_full_service": "상용 서비스 공개 전 해소해야 할 blocker가 있는 상태",
        },
        "overall_status": operations_overall_status(checks),
        "summary": summarize_operations_readiness(checks),
        "sections": sections,
        "blockers": [check for check in checks if check["status"] == "block"],
        "warnings": [check for check in checks if check["status"] == "warn"],
        "next_actions": readiness_next_actions(checks),
    }


def base_place_catalog_section(place_cards: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(place_cards)
    active_count = sum(1 for card in place_cards if card.get("status") == "active")
    source_covered = sum(1 for card in place_cards if card.get("sources"))
    safety_covered = sum(1 for card in place_cards if card.get("safety_notes"))
    verified_or_partial = sum(
        1 for card in place_cards if card.get("verification", {}).get("status") in {"verified", "partial"}
    )
    ratio = verified_or_partial / total if total else 0
    checks = [
        readiness_check(
            "place_catalog_minimum_count",
            "pass" if total >= MIN_PLACE_CARDS else "block",
            "blocker",
            f"{total} cards",
            f">= {MIN_PLACE_CARDS} cards",
            "제한 공개에 필요한 최소 장소 카드 수",
            "공식 출처 기반 장소 카드를 추가 수집",
        ),
        readiness_check(
            "place_catalog_source_coverage",
            "pass" if source_covered == total and total > 0 else "block",
            "blocker",
            f"{source_covered}/{total}",
            "100%",
            "모든 장소 카드의 출처 보유 여부",
            "출처 없는 장소는 hidden 처리하거나 공식 출처를 보강",
        ),
        readiness_check(
            "place_catalog_safety_notes",
            "pass" if safety_covered == total and total > 0 else "block",
            "blocker",
            f"{safety_covered}/{total}",
            "100%",
            "방문 전 주의사항과 안전 메모 보유 여부",
            "안전 메모가 없는 장소를 보강",
        ),
        readiness_check(
            "place_catalog_verified_or_partial_ratio",
            "pass" if ratio >= MIN_VERIFIED_OR_PARTIAL_RATIO else "block",
            "blocker",
            f"{ratio:.1%}",
            f">= {MIN_VERIFIED_OR_PARTIAL_RATIO:.0%}",
            "verified 또는 partial 장소 비율",
            "needs_check 장소의 공식 출처와 접근성 필드를 보강",
        ),
        readiness_check(
            "place_catalog_active_visibility",
            "pass" if active_count == total and total > 0 else "warn",
            "warning",
            f"{active_count}/{total}",
            "primary catalog all active",
            "기본 장소 카탈로그 노출 상태",
            "hidden 또는 blocked 장소가 사용자 결과에 노출되지 않는지 확인",
        ),
    ]
    return section("base_place_catalog", checks)


def public_data_dependencies_section(data_request_tracker: dict[str, Any]) -> dict[str, Any]:
    items = data_request_tracker.get("items", [])
    image_item = next((item for item in items if item.get("source_id") == "roadview_image_files"), {})
    api_item = next((item for item in items if item.get("source_id") == "roadview_api"), {})
    summary = data_request_tracker.get("summary", {})
    checks = [
        readiness_check(
            "public_data_ready_sources",
            "pass" if summary.get("ready_to_use_sources", 0) >= 2 else "warn",
            "warning",
            f"{summary.get('ready_to_use_sources', 0)}/{summary.get('total_sources', 0)}",
            "downloaded public datasets ready",
            "다운로드형 공공데이터 로컬 산출물 준비 여부",
            "원본 CSV와 변환 JSON 산출물을 재생성",
        ),
        readiness_check(
            "roadview_image_request_submission",
            "block"
            if image_item.get("request_status") in {"ready_to_submit", "awaiting_receipt", "action_required"}
            else "pass",
            "blocker",
            image_item.get("request_status", "missing"),
            "ready_to_use",
            "로드뷰 이미지 원본 수령 상태",
            image_item.get("next_action", "이미지 원본 요청 및 수령 상태 확인"),
        ),
        readiness_check(
            "roadview_api_access_policy",
            "warn" if api_item.get("request_status") == "action_required" else "pass",
            "warning",
            api_item.get("request_status", "missing"),
            "not_required_ready or ready_to_use",
            "로드뷰 OpenAPI 무인증 호출 가능 여부",
            api_item.get("next_action", "API 호출 상태와 장애 대응 절차 확인"),
        ),
    ]
    return section("public_data_dependencies", checks)


def roadview_service_seed_section(service_seed_gate_status: dict[str, Any]) -> dict[str, Any]:
    summary = service_seed_gate_status.get("summary", {})
    checks = [
        readiness_check(
            "roadview_service_seed_gate",
            "pass" if service_seed_gate_status.get("overall_status") == "ready_for_service_activation" else "block",
            "blocker",
            service_seed_gate_status.get("overall_status", "missing"),
            "ready_for_service_activation",
            "로드뷰 서비스 시드 17곳의 공개 승격 가능 여부",
            summary.get("next_action", "통합 게이트 리포트 재생성"),
        ),
        readiness_check(
            "roadview_visual_review_samples",
            "pass" if summary.get("missing_priority_sample_images", 0) == 0 else "block",
            "blocker",
            f"missing {summary.get('missing_priority_sample_images', 0)}",
            "missing 0",
            "우선 시각 검수 샘플 이미지 확보 여부",
            "이미지 원본 수령 후 자산 매니페스트 재생성",
        ),
        readiness_check(
            "roadview_active_candidates",
            "pass" if summary.get("promoted_active_candidates", 0) == summary.get("total_places", 0) and summary.get("total_places", 0) > 0 else "block",
            "blocker",
            f"{summary.get('promoted_active_candidates', 0)}/{summary.get('total_places', 0)}",
            "all service seeds promoted",
            "서비스 시드 활성 후보 산출 여부",
            "로드뷰 이미지 검수 완료 후 활성 후보 산출 재실행",
        ),
    ]
    return section("roadview_service_seed", checks)


def operational_documents_section(workspace_root: Path) -> dict[str, Any]:
    checks = [
        readiness_check(
            f"document_exists_{Path(doc).stem}",
            "pass" if (workspace_root / doc).exists() else "warn",
            "warning",
            "exists" if (workspace_root / doc).exists() else "missing",
            "exists",
            doc,
            "운영 문서를 작성하거나 최신 산출물 링크를 반영",
        )
        for doc in REQUIRED_DOCS
    ]
    return section("operational_documents", checks)


def readiness_check(
    check_id: str,
    status: str,
    severity: str,
    actual: str,
    expected: str,
    detail: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "severity": severity,
        "actual": actual,
        "expected": expected,
        "detail": detail,
        "next_action": next_action,
    }


def section(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "status": section_status(checks),
        "checks": checks,
    }


def section_status(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "block" for check in checks):
        return "block"
    if any(check["status"] == "warn" for check in checks):
        return "warn"
    return "pass"


def operations_overall_status(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "block" for check in checks):
        return "blocked_for_full_service"
    if any(check["status"] == "warn" for check in checks):
        return "ready_with_warnings"
    return "ready_for_full_service"


def summarize_operations_readiness(checks: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = Counter(check["status"] for check in checks)
    return {
        "total_checks": len(checks),
        "passed_checks": by_status.get("pass", 0),
        "warning_checks": by_status.get("warn", 0),
        "blocker_checks": by_status.get("block", 0),
        "by_status": dict(by_status),
        "next_action": readiness_next_actions(checks)[0] if readiness_next_actions(checks) else "",
    }


def readiness_next_actions(checks: list[dict[str, Any]]) -> list[str]:
    blockers = [check["next_action"] for check in checks if check["status"] == "block"]
    warnings = [check["next_action"] for check in checks if check["status"] == "warn"]
    deduped = []
    for action in blockers + warnings:
        if action and action not in deduped:
            deduped.append(action)
    return deduped
