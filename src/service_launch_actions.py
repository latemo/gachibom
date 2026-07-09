"""Build an actionable service launch plan from readiness gates."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any


SOURCE_FILES = [
    "data/operations_readiness_report.json",
    "data/roadview_service_seed_gate_status.json",
    "data/roadview_provider_404_image_report.json",
    "data/roadview_image_receipt_report.json",
    "data/roadview_visual_review_sheet.json",
]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_service_launch_action_plan(
    operations_readiness: dict[str, Any],
    service_seed_gate_status: dict[str, Any],
    provider_404_report: dict[str, Any],
    image_receipt_report: dict[str, Any],
    visual_review_sheet: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    gate_summary = service_seed_gate_status.get("summary", {})
    receipt_summary = image_receipt_report.get("summary", {})
    visual_summary = visual_review_sheet.get("summary", {})
    missing_places = missing_image_places(provider_404_report)
    review_places = visual_review_places(visual_review_sheet)
    actions = [
        recover_missing_images_action(gate_summary, receipt_summary, missing_places, provider_404_report),
        complete_visual_review_action(gate_summary, visual_summary, review_places),
        promote_active_candidates_action(gate_summary),
        keep_limited_release_action(operations_readiness, gate_summary),
    ]
    app_highlights = [
        {
            "title": action["title"],
            "status_label": action["status_label"],
            "metric": action["metric"],
            "next_step": action["next_steps"][0] if action["next_steps"] else "",
        }
        for action in actions[:3]
    ]

    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "overall_status": operations_readiness.get("overall_status", "blocked_for_full_service"),
        "status_label": service_status_label(operations_readiness.get("overall_status", "")),
        "summary": summarize_action_plan(
            actions,
            gate_summary,
            receipt_summary,
            visual_summary,
            missing_places,
        ),
        "actions": actions,
        "affected_places": affected_places(missing_places, review_places),
        "app_highlights": app_highlights,
        "source_files": SOURCE_FILES,
    }


def summarize_action_plan(
    actions: list[dict[str, Any]],
    gate_summary: dict[str, Any],
    receipt_summary: dict[str, Any],
    visual_summary: dict[str, Any],
    missing_places: list[dict[str, Any]],
) -> dict[str, Any]:
    priorities = Counter(action["priority"] for action in actions)
    statuses = Counter(action["status"] for action in actions)
    first_action = actions[0]["title"] if actions else ""
    return {
        "total_actions": len(actions),
        "critical_actions": priorities.get("critical", 0),
        "blocked_actions": statuses.get("blocked_external_request", 0)
        + statuses.get("manual_review_required", 0),
        "service_seed_places": int(gate_summary.get("total_places", 0)),
        "missing_roadview_images": int(
            gate_summary.get("missing_requested_images", receipt_summary.get("missing_requested_images", 0))
        ),
        "affected_missing_image_places": len(missing_places),
        "visual_review_open_places": int(visual_summary.get("by_status", {}).get("open", 0))
        or int(gate_summary.get("open_visual_review_places", 0)),
        "visual_review_pending_fields": int(visual_summary.get("by_field_status", {}).get("pending_visual_review", 0)),
        "promoted_active_candidates": int(gate_summary.get("promoted_active_candidates", 0)),
        "first_action": first_action,
        "next_action": gate_summary.get("next_action", ""),
    }


def recover_missing_images_action(
    gate_summary: dict[str, Any],
    receipt_summary: dict[str, Any],
    missing_places: list[dict[str, Any]],
    provider_404_report: dict[str, Any],
) -> dict[str, Any]:
    missing_count = int(gate_summary.get("missing_requested_images", receipt_summary.get("missing_requested_images", 0)))
    affected_count = len(missing_places)
    status = "blocked_external_request" if missing_count else "ready"
    status_label = "외부 수령 필요" if missing_count else "완료"
    return {
        "id": "recover_missing_roadview_original_images",
        "priority": "critical",
        "priority_label": "즉시 처리",
        "status": status,
        "status_label": status_label,
        "owner": "데이터 수령 담당",
        "title": f"누락 로드뷰 원본 이미지 {missing_count}장 복구",
        "metric": f"{missing_count}장 / {affected_count}곳",
        "why": "전체 원본 이미지가 일부 빠진 장소는 상용 공개 게이트에서 원본 수령 완료로 판정할 수 없습니다.",
        "evidence": [
            {"label": "예상 원본", "value": f"{int(gate_summary.get('expected_images', receipt_summary.get('expected_images', 0)))}장"},
            {"label": "수령 원본", "value": f"{int(gate_summary.get('received_requested_images', receipt_summary.get('received_requested_images', 0)))}장"},
            {"label": "누락 원본", "value": f"{missing_count}장"},
            {"label": "영향 장소", "value": f"{affected_count}곳"},
        ],
        "affected_places": missing_places,
        "inputs": [
            "data/roadview_provider_404_image_request.csv",
            "docs/roadview_provider_404_recovery_request.md",
        ],
        "outputs": [
            "data/roadview_missing_image_recovery_report.json",
            "data/raw/roadview_images/",
            "data/roadview_image_receipt_report.json",
            "data/roadview_service_seed_gate_status.json",
        ],
        "done_when": [
            f"누락 {missing_count}장 또는 제공기관이 인정한 대체 원본이 data/raw/roadview_images에 배치됨",
            "로드뷰 이미지 수령 리포트의 missing_requested_images가 0으로 내려감",
            "서비스 시드 게이트의 image_receipt_complete 보류가 사라짐",
        ],
        "next_steps": [
            provider_404_report.get("recommended_action", "제공기관에 누락 파일 복구 또는 대체 원본을 요청"),
            "수령 파일명을 요청 CSV의 image_file_name 기준으로 맞춰 배치",
            "누락 이미지 회복 검증 리포트로 70장 해소 여부를 먼저 확인",
            "수령 후 수령 리포트와 게이트 상태를 재생성",
        ],
    }


def complete_visual_review_action(
    gate_summary: dict[str, Any],
    visual_summary: dict[str, Any],
    review_places: list[dict[str, Any]],
) -> dict[str, Any]:
    open_places = int(visual_summary.get("by_status", {}).get("open", 0)) or int(
        gate_summary.get("open_visual_review_places", 0)
    )
    pending_fields = int(visual_summary.get("by_field_status", {}).get("pending_visual_review", 0))
    status = "manual_review_required" if open_places else "ready"
    status_label = "사람 검수 필요" if open_places else "완료"
    return {
        "id": "complete_roadview_visual_review",
        "priority": "critical",
        "priority_label": "즉시 처리",
        "status": status,
        "status_label": status_label,
        "owner": "접근성 검수 담당",
        "title": f"로드뷰 시드 {open_places}곳 시각 검수 완료",
        "metric": f"{open_places}곳 / {pending_fields}개 필드",
        "why": "출입구 단차, 경사, 바닥 상태, 주차장-입구 동선은 이미지 판정 전까지 추천 근거로 확정할 수 없습니다.",
        "evidence": [
            {"label": "열린 검수 장소", "value": f"{open_places}곳"},
            {"label": "미판정 필드", "value": f"{pending_fields}개"},
            {"label": "우선 샘플 확보", "value": f"{int(gate_summary.get('received_priority_sample_images', 0))}/{int(gate_summary.get('expected_priority_sample_images', 0))}장"},
            {"label": "검수 완료 장소", "value": f"{int(gate_summary.get('verified_roadview_places', 0))}곳"},
        ],
        "affected_places": review_places,
        "inputs": [
            "docs/roadview_visual_review_share.zip",
            "docs/roadview_visual_review_share_20260709/index.html",
        ],
        "outputs": [
            "data/roadview_visual_review_sheet.json",
            "data/roadview_service_seed_promotion_readiness.json",
        ],
        "done_when": [
            "각 장소의 필수 4개 필드가 verified, needs_follow_up, conflict 중 하나로 판정됨",
            "불확실한 항목은 verified로 올리지 않고 후속 확인으로 남김",
            "로드뷰 이미지 검수 완료 장소 수가 17곳으로 올라감",
        ],
        "next_steps": [
            "공유 HTML에서 장소별 대표 이미지를 열고 4개 필드를 버튼으로 판정",
            "판정 CSV를 병합해 roadview_visual_review_sheet.json을 갱신",
            "충돌 또는 후속 확인 항목은 추천 점수에서 보수적으로 감점",
        ],
    }


def promote_active_candidates_action(gate_summary: dict[str, Any]) -> dict[str, Any]:
    total_places = int(gate_summary.get("total_places", 0))
    promoted = int(gate_summary.get("promoted_active_candidates", 0))
    blocked = max(total_places - promoted, 0)
    return {
        "id": "promote_verified_service_seed_candidates",
        "priority": "high",
        "priority_label": "검수 직후",
        "status": "waiting_previous_gate" if blocked else "ready",
        "status_label": "이전 단계 대기" if blocked else "완료",
        "owner": "데이터 파이프라인 담당",
        "title": "검수 통과 장소 활성 후보 승격",
        "metric": f"{promoted}/{total_places}곳",
        "why": "상용 추천에는 검수 통과 또는 명확한 제한 조건이 붙은 장소만 활성 후보로 넣어야 합니다.",
        "evidence": [
            {"label": "전체 시드", "value": f"{total_places}곳"},
            {"label": "활성 후보", "value": f"{promoted}곳"},
            {"label": "대기 장소", "value": f"{blocked}곳"},
        ],
        "affected_places": [],
        "inputs": [
            "data/roadview_service_seed_promotion_readiness.json",
            "data/roadview_visual_review_sheet.json",
        ],
        "outputs": [
            "data/roadview_service_seed_active_candidates.json",
            "data/roadview_service_seed_gate_status.json",
        ],
        "done_when": [
            "활성 후보 수가 서비스 시드 17곳과 일치함",
            "활성 후보 준비 보류 항목이 사라짐",
        ],
        "next_steps": [
            "시각 검수 완료 후 승격 준비 리포트를 재생성",
            "통과 장소만 활성 후보로 내보냄",
            "앱 추천 기본 데이터 재생성 전 활성 후보 수를 확인",
        ],
    }


def keep_limited_release_action(operations_readiness: dict[str, Any], gate_summary: dict[str, Any]) -> dict[str, Any]:
    status_label = service_status_label(operations_readiness.get("overall_status", ""))
    return {
        "id": "keep_limited_release_boundary",
        "priority": "high",
        "priority_label": "상시 유지",
        "status": "internal_review_ready",
        "status_label": "내부 검증 가능",
        "owner": "서비스 운영 담당",
        "title": "상용 공개 전 노출 범위 고정",
        "metric": status_label,
        "why": "서비스화 전에는 검수되지 않은 로드뷰 근거가 실제 사용자 추천 근거처럼 보이지 않아야 합니다.",
        "evidence": [
            {"label": "운영 게이트", "value": status_label},
            {"label": "다음 조치", "value": gate_summary.get("next_action", "게이트 재점검")},
        ],
        "affected_places": [],
        "inputs": [
            "web/data/operations_readiness_report.json",
            "web/data/recommendation_case_validation_report.json",
        ],
        "outputs": [
            "web/data/service_launch_action_plan.json",
            "docs/service_launch_action_plan_20260709.md",
        ],
        "done_when": [
            "앱 좌측 게이트에서 상용 공개 보류와 다음 실행 항목이 함께 보임",
            "검수 전 장소는 서비스 추천 근거로 과장 표기되지 않음",
        ],
        "next_steps": [
            "운영 게이트가 전체 공개 가능으로 바뀔 때까지 제한 공개 문구 유지",
            "추천 품질 검증표와 서비스 실행 계획을 같은 기준일로 갱신",
        ],
    }


def missing_image_places(provider_404_report: dict[str, Any]) -> list[dict[str, Any]]:
    by_place = provider_404_report.get("summary", {}).get("by_place", {})
    image_names: dict[str, list[str]] = defaultdict(list)
    for item in provider_404_report.get("items", []):
        place_name = item.get("place_name", "")
        if not place_name:
            continue
        image_names[place_name].append(item.get("image_file_name", ""))

    places = [
        {
            "place_name": place_name,
            "missing_image_count": int(count),
            "sample_image_file_names": [name for name in image_names.get(place_name, []) if name][:5],
        }
        for place_name, count in by_place.items()
    ]
    return sorted(places, key=lambda item: (-item["missing_image_count"], item["place_name"]))


def visual_review_places(visual_review_sheet: dict[str, Any]) -> list[dict[str, Any]]:
    places = []
    for item in visual_review_sheet.get("items", []):
        card = item.get("card", {})
        field_results = item.get("field_results", [])
        pending_fields = [field.get("field", "") for field in field_results if field.get("status") == "pending_visual_review"]
        places.append(
            {
                "place_name": card.get("name", ""),
                "status": item.get("status", ""),
                "review_decision": item.get("review_decision", ""),
                "pending_field_count": len(pending_fields),
                "pending_fields": pending_fields,
            }
        )
    return [place for place in places if place["status"] == "open"]


def affected_places(missing_places: list[dict[str, Any]], review_places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for place in review_places:
        name = place["place_name"]
        merged[name] = {
            "place_name": name,
            "needs_missing_images": False,
            "missing_image_count": 0,
            "needs_visual_review": True,
            "pending_field_count": place.get("pending_field_count", 0),
        }
    for place in missing_places:
        name = place["place_name"]
        merged.setdefault(
            name,
            {
                "place_name": name,
                "needs_missing_images": False,
                "missing_image_count": 0,
                "needs_visual_review": False,
                "pending_field_count": 0,
            },
        )
        merged[name]["needs_missing_images"] = True
        merged[name]["missing_image_count"] = place.get("missing_image_count", 0)
    return sorted(
        merged.values(),
        key=lambda item: (
            not item["needs_missing_images"],
            -int(item["missing_image_count"]),
            item["place_name"],
        ),
    )


def service_status_label(status: str) -> str:
    labels = {
        "ready_for_full_service": "전체 공개 가능",
        "ready_with_warnings": "제한 공개 가능",
        "blocked_for_full_service": "상용 공개 보류",
        "blocked": "상용 공개 보류",
    }
    return labels.get(status, "확인 필요")


def render_service_launch_action_plan_markdown(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        "# 제주의마음 서비스 런칭 실행 계획",
        "",
        f"- 기준일: {plan['generated_at']}",
        f"- 현재 판정: {plan['status_label']}",
        f"- 우선 실행: {summary['first_action']}",
        f"- 로드뷰 원본 누락: {summary['missing_roadview_images']}장 / {summary['affected_missing_image_places']}곳",
        f"- 시각 검수 대기: {summary['visual_review_open_places']}곳 / {summary['visual_review_pending_fields']}개 필드",
        f"- 활성 후보: {summary['promoted_active_candidates']}/{summary['service_seed_places']}곳",
        "",
        "## 실행 항목",
        "",
    ]
    for index, action in enumerate(plan["actions"], start=1):
        lines.extend(
            [
                f"### {index}. {action['title']}",
                "",
                f"- 우선순위: {action['priority_label']}",
                f"- 상태: {action['status_label']}",
                f"- 담당: {action['owner']}",
                f"- 지표: {action['metric']}",
                f"- 이유: {action['why']}",
                "- 근거:",
            ]
        )
        lines.extend([f"  - {item['label']}: {item['value']}" for item in action["evidence"]])
        lines.append("- 다음 실행:")
        lines.extend([f"  - {step}" for step in action["next_steps"]])
        lines.append("- 완료 기준:")
        lines.extend([f"  - {done}" for done in action["done_when"]])
        lines.append("")

    missing_places = [place for place in plan["affected_places"] if place["needs_missing_images"]]
    if missing_places:
        lines.extend(["## 누락 이미지 영향 장소", ""])
        lines.extend(
            [
                f"- {place['place_name']}: 누락 {place['missing_image_count']}장, 검수 대기 {place['pending_field_count']}개 필드"
                for place in missing_places
            ]
        )
        lines.append("")

    lines.extend(["## 출처 파일", ""])
    lines.extend([f"- `{source}`" for source in plan["source_files"]])
    lines.append("")
    return "\n".join(lines)
