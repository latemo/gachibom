"""Build operational tracking records for public data requests and receipts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


DATA_SOURCES = [
    {
        "source_id": "roadview_api",
        "dataset_name": "제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 오픈 API",
        "provider": "제주특별자치도",
        "portal_url": "https://www.data.go.kr/data/15109149/openapi.do?recommendDataYn=Y",
        "source_type": "openapi",
        "acquisition_mode": "direct_public_api",
        "service_usage": "키 없이 호출 가능한 관광지 접근성 시설 원천 데이터 조회와 갱신 자동화 후보",
        "local_artifacts": [],
        "expected_counts": {"facility_places": 107, "metadata_rows": 4748},
    },
    {
        "source_id": "roadview_image_files",
        "dataset_name": "제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지",
        "provider": "제주특별자치도",
        "portal_url": "https://www.data.go.kr/data/15110209/fileData.do",
        "source_type": "image_files",
        "acquisition_mode": "application_required",
        "service_usage": "출입구 단차, 경사, 바닥 상태, 주차장-출입구 동선 시각 검수",
        "local_artifacts": [
            {"path": "docs/roadview_image_data_request_message.md", "required": True},
            {"path": "data/roadview_image_acquisition_priority_samples.csv", "required": True},
            {"path": "data/roadview_image_acquisition_full_request.csv", "required": True},
            {"path": "data/roadview_image_acquisition_place_summary.csv", "required": True},
            {"path": "data/roadview_image_receipt_report.json", "required": True},
        ],
        "expected_counts": {"full_dataset_images": 4748},
    },
    {
        "source_id": "roadview_image_metadata",
        "dataset_name": "제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
        "provider": "제주특별자치도",
        "portal_url": "https://www.data.go.kr/data/15109158/fileData.do",
        "source_type": "file_data",
        "acquisition_mode": "public_download",
        "service_usage": "장소별 로드뷰 이미지 파일명, 촬영일, 좌표 매칭",
        "local_artifacts": [
            {"path": "data/roadview_image_metadata.json", "required": True},
            {"path": "data/raw/jeju_roadview_image_metadata_20250730.csv", "required": False},
        ],
        "expected_counts": {"metadata_rows": 4748},
    },
    {
        "source_id": "roadview_facility_status",
        "dataset_name": "제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
        "provider": "제주특별자치도",
        "portal_url": "https://www.data.go.kr/data/15109153/fileData.do",
        "source_type": "file_data",
        "acquisition_mode": "public_download",
        "service_usage": "장애인 화장실, 장애인 주차장, 휠체어 대여, 휴게실 등 공식 시설 근거",
        "local_artifacts": [
            {"path": "data/place_catalog.roadview_facility.json", "required": True},
            {"path": "data/raw/jeju_roadview_facility_status_20250730.csv", "required": False},
        ],
        "expected_counts": {"facility_places": 107},
    },
    {
        "source_id": "tourism_weak_recommendation_courses",
        "dataset_name": "제주관광공사_관광 약자 유형별 제주관광 추천코스",
        "provider": "제주관광공사",
        "portal_url": "https://www.data.go.kr/data/15117357/fileData.do",
        "source_type": "file_data",
        "acquisition_mode": "public_download",
        "service_usage": "관광약자 유형별 공공 추천코스 일치도 보강과 신규 장소 후보 발굴",
        "local_artifacts": [
            {"path": "data/raw/jeju_tourism_weak_recommendation_courses_20260528.csv", "required": True},
            {"path": "data/tourism_weak_recommendation_courses.json", "required": True},
        ],
        "expected_counts": {"courses": 16},
    },
]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_data_request_tracker(
    *,
    acquisition_request: dict[str, Any] | None = None,
    receipt_report: dict[str, Any] | None = None,
    service_seed_gate_status: dict[str, Any] | None = None,
    generated_at: date | None = None,
    workspace_root: str | Path = ".",
) -> dict[str, Any]:
    root = Path(workspace_root)
    items = [
        build_data_request_tracker_item(
            source,
            acquisition_request=acquisition_request or {},
            receipt_report=receipt_report or {},
            service_seed_gate_status=service_seed_gate_status or {},
            workspace_root=root,
        )
        for source in DATA_SOURCES
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "criteria": {
            "ready_to_use": "필수 로컬 산출물이 있고 서비스 반영 차단 사유가 없는 데이터",
            "ready_to_submit": "요청 문안과 첨부 목록은 준비됐지만 제공기관 제출 또는 수령 기록이 없는 데이터",
            "awaiting_receipt": "요청 대상 원본 수령이 필요해 서비스 검수 게이트가 막힌 데이터",
            "action_required": "원본 수령, 누락 산출물, 갱신 자동화 중 하나가 필요한 데이터",
        },
        "summary": summarize_data_request_tracker(items),
        "items": items,
    }


def build_data_request_tracker_item(
    source: dict[str, Any],
    *,
    acquisition_request: dict[str, Any],
    receipt_report: dict[str, Any],
    service_seed_gate_status: dict[str, Any],
    workspace_root: Path,
) -> dict[str, Any]:
    artifact_statuses = [
        artifact_status(artifact, workspace_root)
        for artifact in source.get("local_artifacts", [])
    ]
    metrics = data_source_metrics(source["source_id"], acquisition_request, receipt_report, service_seed_gate_status)
    request_status = data_source_request_status(source, artifact_statuses, metrics)
    gate_status = "pass" if request_status in {"ready_to_use", "not_required_ready"} else "fail"
    return {
        "source_id": source["source_id"],
        "dataset_name": source["dataset_name"],
        "provider": source["provider"],
        "portal_url": source["portal_url"],
        "source_type": source["source_type"],
        "acquisition_mode": source["acquisition_mode"],
        "service_usage": source["service_usage"],
        "request_status": request_status,
        "gate_status": gate_status,
        "expected_counts": source.get("expected_counts", {}),
        "current_counts": metrics,
        "local_artifacts": artifact_statuses,
        "blocking_reason": data_source_blocking_reason(source, artifact_statuses, metrics, request_status),
        "next_action": data_source_next_action(source, request_status),
    }


def artifact_status(artifact: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    path = Path(artifact["path"])
    absolute_path = workspace_root / path
    return {
        "path": path.as_posix(),
        "required": artifact.get("required", False),
        "exists": absolute_path.exists(),
    }


def data_source_metrics(
    source_id: str,
    acquisition_request: dict[str, Any],
    receipt_report: dict[str, Any],
    service_seed_gate_status: dict[str, Any],
) -> dict[str, int]:
    if source_id == "roadview_image_files":
        acquisition_summary = acquisition_request.get("summary", {})
        receipt_summary = receipt_report.get("summary", {})
        gate_summary = service_seed_gate_status.get("summary", {})
        return {
            "requested_images": acquisition_summary.get("total_requested_images", 0),
            "priority_sample_images": acquisition_summary.get("priority_sample_images", 0),
            "received_requested_images": receipt_summary.get("received_requested_images", 0),
            "missing_requested_images": receipt_summary.get("missing_requested_images", 0),
            "service_seed_blocked_places": gate_summary.get("blocked_count", 0),
        }
    if source_id == "roadview_image_metadata":
        return {
            "metadata_rows": acquisition_request.get("source_dataset", {}).get("expected_full_dataset_image_count", 0)
        }
    if source_id == "roadview_facility_status":
        return {"facility_places": 107}
    if source_id == "tourism_weak_recommendation_courses":
        return {"courses": 16}
    return {}


def data_source_request_status(
    source: dict[str, Any],
    artifact_statuses: list[dict[str, Any]],
    metrics: dict[str, int],
) -> str:
    required_missing = any(artifact["required"] and not artifact["exists"] for artifact in artifact_statuses)
    if source["acquisition_mode"] == "application_required":
        if metrics.get("missing_requested_images", 0) == 0 and metrics.get("requested_images", 0) > 0:
            return "ready_to_use"
        if metrics.get("received_requested_images", 0) > 0 and metrics.get("missing_requested_images", 0) > 0:
            return "awaiting_receipt"
        if metrics.get("requested_images", 0) > 0 and not required_missing:
            return "ready_to_submit"
        return "action_required"
    if source["acquisition_mode"] == "direct_public_api":
        return "not_required_ready"
    if required_missing:
        return "action_required"
    return "not_required_ready"


def data_source_blocking_reason(
    source: dict[str, Any],
    artifact_statuses: list[dict[str, Any]],
    metrics: dict[str, int],
    request_status: str,
) -> str:
    missing_artifacts = [
        artifact["path"]
        for artifact in artifact_statuses
        if artifact["required"] and not artifact["exists"]
    ]
    if missing_artifacts:
        return "필수 산출물 누락: " + ", ".join(missing_artifacts)
    if source["source_id"] == "roadview_image_files" and metrics.get("missing_requested_images", 0) > 0:
        return f"요청 이미지 {metrics.get('missing_requested_images', 0)}장 미수령"
    if request_status == "action_required" and source["acquisition_mode"] == "direct_public_api":
        return "무인증 API 호출 상태와 장애 대응 절차 확인 필요"
    return ""


def data_source_next_action(source: dict[str, Any], request_status: str) -> str:
    if source["source_id"] == "roadview_image_files":
        if request_status == "ready_to_submit":
            return "요청 문안과 CSV 3종을 공공데이터포털 활용신청 또는 제공기관 요청에 첨부"
        if request_status == "awaiting_receipt":
            return "누락 원본 이미지 복구 또는 대체 원본 수령을 제공기관에 요청"
        if request_status == "ready_to_use":
            return "수령 이미지 검수와 시각 검수 게이트 재생성"
        return "요청 패키지와 수령 검수 산출물 보강"
    if source["acquisition_mode"] == "direct_public_api":
        return "키 없이 호출 가능 확인됨. 정기 갱신 주기와 호출량·장애 대응 절차 정의"
    if request_status == "not_required_ready":
        return "정기 갱신 주기와 원본 변경 감지 절차 정의"
    return "필수 로컬 산출물 생성 또는 원본 재수집"


def summarize_data_request_tracker(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_sources": len(items),
        "ready_to_use_sources": sum(
            1 for item in items if item.get("request_status") in {"ready_to_use", "not_required_ready"}
        ),
        "action_required_sources": sum(
            1 for item in items if item.get("request_status") not in {"ready_to_use", "not_required_ready"}
        ),
        "by_request_status": dict(Counter(item.get("request_status", "unknown") for item in items)),
        "by_acquisition_mode": dict(Counter(item.get("acquisition_mode", "unknown") for item in items)),
        "next_action": tracker_next_action(items),
    }


def tracker_next_action(items: list[dict[str, Any]]) -> str:
    image_item = next((item for item in items if item.get("source_id") == "roadview_image_files"), None)
    if image_item and image_item.get("request_status") in {"ready_to_submit", "awaiting_receipt"}:
        return image_item.get("next_action", "")
    action_item = next((item for item in items if item.get("request_status") == "action_required"), None)
    if action_item:
        return action_item.get("next_action", "")
    return "정기 갱신 주기와 변경 감지 자동화를 설계"


def export_data_request_tracker_csv(tracker: dict[str, Any], output_path: str | Path) -> dict[str, int]:
    rows = [data_request_tracker_csv_row(item) for item in tracker.get("items", [])]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=data_request_tracker_csv_fields())
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": len(rows)}


def data_request_tracker_csv_fields() -> list[str]:
    return [
        "source_id",
        "dataset_name",
        "provider",
        "portal_url",
        "source_type",
        "acquisition_mode",
        "request_status",
        "gate_status",
        "blocking_reason",
        "next_action",
        "requested_images",
        "received_requested_images",
        "missing_requested_images",
        "service_usage",
    ]


def data_request_tracker_csv_row(item: dict[str, Any]) -> dict[str, Any]:
    counts = item.get("current_counts", {})
    return {
        "source_id": item.get("source_id", ""),
        "dataset_name": item.get("dataset_name", ""),
        "provider": item.get("provider", ""),
        "portal_url": item.get("portal_url", ""),
        "source_type": item.get("source_type", ""),
        "acquisition_mode": item.get("acquisition_mode", ""),
        "request_status": item.get("request_status", ""),
        "gate_status": item.get("gate_status", ""),
        "blocking_reason": item.get("blocking_reason", ""),
        "next_action": item.get("next_action", ""),
        "requested_images": counts.get("requested_images", ""),
        "received_requested_images": counts.get("received_requested_images", ""),
        "missing_requested_images": counts.get("missing_requested_images", ""),
        "service_usage": item.get("service_usage", ""),
    }
