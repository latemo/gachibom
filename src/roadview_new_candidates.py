"""Triage roadview new candidates before promoting them to service cards."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Iterable


SERVICE_SEED_MIN_SCORE = 8
CATALOG_CANDIDATE_MIN_SCORE = 5
ACCESSIBILITY_FIELDS = [
    "wheelchair_access",
    "accessible_toilet",
    "parking",
    "slope_or_stairs",
    "rest_area",
    "rental_or_assistance",
    "surface_condition",
    "crowd_level",
]
SERVICE_RELEVANT_CATEGORIES = {"indoor", "culture", "rest_area", "forest", "sea"}
OFFICIAL_SOURCE_VISUAL_FALLBACK_FIELDS = {"slope_or_stairs", "surface_condition"}
ROADVIEW_FACILITY_SOURCE_URL = "https://www.data.go.kr/data/15109153/fileData.do"
ROADVIEW_IMAGE_SOURCE_URL = "https://www.data.go.kr/data/15110209/fileData.do"
ROADVIEW_IMAGE_FILE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
OFFICIAL_ACCESSIBILITY_SOURCE_TYPES = [
    "easyjeju_accessibility_detail",
    "open_tourism_accessibility_detail",
    "official_site",
    "public_agency",
    "visitjeju",
]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def triage_new_candidates(
    manual_review_queue: dict[str, Any],
    draft_cards: Iterable[dict[str, Any]],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    drafts_by_id = {card.get("id"): card for card in draft_cards}
    candidates = []

    for item in manual_review_queue.get("items", []):
        if item.get("review_type") != "new_candidate":
            continue

        draft_ref = item.get("draft", {})
        draft = drafts_by_id.get(draft_ref.get("id"))
        if not draft:
            candidates.append(missing_draft_candidate(draft_ref))
            continue

        candidates.append(triage_card(draft))

    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_queue_generated_at": manual_review_queue.get("generated_at"),
        "criteria": {
            "service_seed_candidate": (
                "accessible_toilet=yes, parking=yes, and total score >= "
                f"{SERVICE_SEED_MIN_SCORE}; output remains review-only before field/source hardening"
            ),
            "catalog_candidate": f"total score >= {CATALOG_CANDIDATE_MIN_SCORE}, but not enough for service seed",
            "field_review_required": "low facility score or missing essential accessibility evidence",
        },
        "summary": summarize_candidates(candidates),
        "candidates": candidates,
    }


def triage_card(card: dict[str, Any]) -> dict[str, Any]:
    states = field_states(card)
    score = score_candidate(card, states)
    decision = decide_candidate(score, states)
    return {
        "draft": card_ref(card),
        "score": score,
        "decision": decision,
        "priority": priority_for_decision(decision),
        "yes_fields": fields_with_state(states, "yes"),
        "no_fields": fields_with_state(states, "no"),
        "needs_check_fields": fields_with_state(states, "needs_check"),
        "unknown_fields": fields_with_state(states, "unknown"),
        "strengths": candidate_strengths(card, states),
        "risks": candidate_risks(card, states),
        "recommended_action": recommended_action(decision),
    }


def missing_draft_candidate(draft_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft": draft_ref,
        "score": 0,
        "decision": "field_review_required",
        "priority": "low",
        "yes_fields": [],
        "no_fields": [],
        "needs_check_fields": [],
        "unknown_fields": [],
        "strengths": [],
        "risks": ["draft_card_missing"],
        "recommended_action": "초안 카드 원본을 찾은 뒤 재검토",
    }


def score_candidate(card: dict[str, Any], states: dict[str, str]) -> int:
    score = 0
    if states.get("accessible_toilet") == "yes":
        score += 3
    if states.get("parking") == "yes":
        score += 3
    if states.get("rental_or_assistance") == "yes":
        score += 2
    if states.get("rest_area") == "yes":
        score += 1
    if card.get("category") in SERVICE_RELEVANT_CATEGORIES:
        score += 1
    if states.get("accessible_toilet") == "no":
        score -= 2
    if states.get("parking") == "no":
        score -= 1
    if card.get("category") == "other":
        score -= 1
    return score


def decide_candidate(score: int, states: dict[str, str]) -> str:
    has_essentials = states.get("accessible_toilet") == "yes" and states.get("parking") == "yes"
    if has_essentials and score >= SERVICE_SEED_MIN_SCORE:
        return "service_seed_candidate"
    if score >= CATALOG_CANDIDATE_MIN_SCORE:
        return "catalog_candidate"
    return "field_review_required"


def priority_for_decision(decision: str) -> str:
    if decision == "service_seed_candidate":
        return "high"
    if decision == "catalog_candidate":
        return "medium"
    return "low"


def recommended_action(decision: str) -> str:
    if decision == "service_seed_candidate":
        return "서비스 시드 후보 파일에 포함하고, 공식 상세 출처 또는 로드뷰 이미지 검수 후 공개 여부 결정"
    if decision == "catalog_candidate":
        return "장소 카탈로그 후보로 유지하고 상세 접근성 출처 확보 후 카드 승격 검토"
    return "현장 동선 또는 공식 접근성 상세 출처 확보 전 서비스 카드 승격 보류"


def candidate_strengths(card: dict[str, Any], states: dict[str, str]) -> list[str]:
    strengths = []
    if states.get("accessible_toilet") == "yes":
        strengths.append("accessible_toilet_confirmed")
    if states.get("parking") == "yes":
        strengths.append("parking_confirmed")
    if states.get("rental_or_assistance") == "yes":
        strengths.append("rental_or_assistance_confirmed")
    if states.get("rest_area") == "yes":
        strengths.append("rest_area_confirmed")
    if card.get("category") in SERVICE_RELEVANT_CATEGORIES:
        strengths.append(f"service_relevant_category:{card.get('category')}")
    return strengths


def candidate_risks(card: dict[str, Any], states: dict[str, str]) -> list[str]:
    risks = []
    if states.get("accessible_toilet") != "yes":
        risks.append("accessible_toilet_not_confirmed")
    if states.get("parking") != "yes":
        risks.append("parking_not_confirmed")
    if states.get("slope_or_stairs") in {"needs_check", "unknown"}:
        risks.append("slope_or_stairs_needs_review")
    if states.get("surface_condition") in {"needs_check", "unknown"}:
        risks.append("surface_condition_needs_review")
    if states.get("crowd_level") in {"needs_check", "unknown"}:
        risks.append("crowd_level_unknown")
    if card.get("category") == "other":
        risks.append("category_refinement_needed")
    return risks


def build_service_seed_cards(
    triage_report: dict[str, Any],
    draft_cards: Iterable[dict[str, Any]],
    *,
    seed_status: str = "hidden",
) -> list[dict[str, Any]]:
    drafts_by_id = {card.get("id"): card for card in draft_cards}
    selected_ids = {
        candidate.get("draft", {}).get("id")
        for candidate in triage_report.get("candidates", [])
        if candidate.get("decision") == "service_seed_candidate"
    }
    cards = []
    for card_id in selected_ids:
        draft = drafts_by_id.get(card_id)
        if not draft:
            continue
        card = deepcopy(draft)
        card["status"] = seed_status
        card["operator_notes"] = (
            f"{card.get('operator_notes', '')}\n"
            "roadview_new_candidate_triage: 서비스 시드 후보. 공개 전 공식 상세 출처 또는 로드뷰 이미지 검수 필요."
        ).strip()
        note = "서비스 공개 전 경사·단차·바닥 상태와 운영 여부를 추가 검수해야 함"
        if note not in card.get("safety_notes", []):
            card.setdefault("safety_notes", []).append(note)
        cards.append(card)
    return sorted(cards, key=lambda card: card.get("name", ""))


def build_service_seed_review(
    seed_cards: Iterable[dict[str, Any]],
    image_metadata: Iterable[dict[str, Any]],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    metadata_by_name = group_metadata_by_name(image_metadata)
    items = [service_seed_review_item(card, metadata_by_name.get(card.get("name", ""), [])) for card in seed_cards]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "criteria": {
            "publishable": "공식 상세 출처와 경사·단차·바닥 상태 검수 완료 후 active 전환 가능",
            "blocked": "공식 상세 출처 또는 현장/로드뷰 이미지 검수 필드가 부족하면 hidden 유지",
        },
        "summary": summarize_service_seed_review(items),
        "items": items,
    }


def build_service_seed_work_queue(
    seed_review: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    items = []
    for review_item in seed_review.get("items", []):
        card = review_item.get("card", {})
        blockers = set(review_item.get("blockers", []))
        required_checks = set(review_item.get("required_checks", []))

        if "official_detail_source_required" in blockers:
            items.append(official_source_task(review_item))
        if blockers.intersection({"slope_or_stairs_review_required", "surface_condition_review_required"}):
            items.append(roadview_image_task(review_item))
        if "crowd_level_policy_required" in blockers:
            items.append(crowd_policy_task(review_item))
        if "category_refinement" in required_checks:
            items.append(category_refinement_task(review_item))

        if not card.get("id"):
            continue

    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_review_generated_at": seed_review.get("generated_at"),
        "summary": summarize_work_items(items),
        "items": items,
    }


def build_official_source_review(
    work_queue: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    items = [
        official_source_review_item(task)
        for task in work_queue.get("items", [])
        if task.get("task_type") == "official_source_review"
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_work_queue_generated_at": work_queue.get("generated_at"),
        "criteria": {
            "usable_source": "장소명이 일치하고 접근성 세부 항목을 확인할 수 있는 공식/공공 출처만 verified 처리",
            "blocked": "공식/공공 상세 URL과 필드별 근거가 없으면 서비스 시드 카드는 hidden 유지",
        },
        "summary": summarize_official_source_review(items),
        "items": items,
    }


def build_roadview_image_review(
    work_queue: dict[str, Any],
    image_metadata: Iterable[dict[str, Any]],
    *,
    asset_root: str | Path | None = None,
    generated_at: date | None = None,
) -> dict[str, Any]:
    metadata_by_name = group_metadata_by_name(image_metadata)
    available_image_keys = available_roadview_image_keys(asset_root) if asset_root else None
    items = [
        roadview_image_review_item(
            task,
            metadata_by_name.get(task.get("card", {}).get("name", ""), []),
            available_image_keys=available_image_keys,
        )
        for task in work_queue.get("items", [])
        if task.get("task_type") == "roadview_image_review"
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_work_queue_generated_at": work_queue.get("generated_at"),
        "criteria": {
            "visual_review_required": "이미지 원본으로 출입구 단차·경사·바닥재·주차장-출입구 연결 동선을 검수",
            "blocked": "이미지 메타데이터가 없거나 동선 핵심 구간 이미지가 부족하면 hidden 유지",
        },
        "summary": summarize_roadview_image_review(items),
        "items": items,
    }


def build_roadview_image_asset_manifest(
    roadview_image_review: dict[str, Any],
    *,
    asset_root: str | Path = "data/raw/roadview_images",
    generated_at: date | None = None,
) -> dict[str, Any]:
    root = Path(asset_root)
    items = [
        roadview_image_asset_manifest_item(item, root)
        for item in roadview_image_review.get("items", [])
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_roadview_image_review_generated_at": roadview_image_review.get("generated_at"),
        "asset_root": str(root).replace("\\", "/"),
        "source_dataset": {
            "title": "제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지",
            "url": ROADVIEW_IMAGE_SOURCE_URL,
            "provider": "제주특별자치도",
            "application_required": True,
            "expected_full_dataset_image_count": 4748,
            "expected_full_dataset_size_gb": "23~25",
            "note": "공공데이터포털 페이지 기준 전체 이미지는 활용신청 후 전자매체로 별도 제공",
        },
        "summary": summarize_roadview_image_asset_manifest(items),
        "items": items,
    }


def build_roadview_image_acquisition_request(
    roadview_image_review: dict[str, Any],
    image_metadata: Iterable[dict[str, Any]],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    metadata_by_name = group_metadata_by_name(image_metadata)
    items = [
        roadview_image_acquisition_item(item, metadata_by_name.get(item.get("card", {}).get("name", ""), []))
        for item in roadview_image_review.get("items", [])
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_roadview_image_review_generated_at": roadview_image_review.get("generated_at"),
        "source_dataset": {
            "title": "제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지",
            "url": ROADVIEW_IMAGE_SOURCE_URL,
            "provider": "제주특별자치도",
            "application_required": True,
            "expected_full_dataset_image_count": 4748,
            "expected_service_seed_image_count": sum(item.get("image_count", 0) for item in roadview_image_review.get("items", [])),
            "expected_priority_sample_image_count": sum(
                len(item.get("review_image_samples", [])) for item in roadview_image_review.get("items", [])
            ),
            "note": "서비스 시드 17개 장소에 필요한 이미지 파일명을 우선 샘플과 전체 요청 목록으로 분리",
        },
        "summary": summarize_roadview_image_acquisition_request(items),
        "items": items,
    }


def build_roadview_image_receipt_report(
    acquisition_request: dict[str, Any],
    *,
    receipt_root: str | Path = "data/raw/roadview_images",
    generated_at: date | None = None,
    hash_files: bool = True,
) -> dict[str, Any]:
    root = Path(receipt_root)
    received_index, received_files = received_image_file_index(root, hash_files=hash_files)
    requested_keys = {
        normalize_image_key(image.get("image_file_name", ""))
        for item in acquisition_request.get("items", [])
        for image in acquisition_request_item_images(item)
    }
    items = [
        roadview_image_receipt_item(item, received_index)
        for item in acquisition_request.get("items", [])
    ]
    unexpected_files = [
        file_record
        for file_record in received_files
        if normalize_image_key(file_record.get("file_name", "")) not in requested_keys
    ]
    duplicate_file_name_groups = duplicate_received_file_name_groups(received_index)
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_roadview_image_acquisition_request_generated_at": acquisition_request.get("generated_at"),
        "receipt_root": str(root).replace("\\", "/"),
        "hash_algorithm": "sha256" if hash_files else None,
        "criteria": {
            "complete": "요청 이미지 파일명이 모두 receipt_root 아래에 존재하면 complete",
            "partial": "요청 이미지 일부만 존재하면 partial",
            "empty": "요청 이미지가 하나도 없으면 empty",
            "unexpected_files": "전체 데이터셋을 수령한 경우 서비스 시드 외 파일은 정상적으로 unexpected에 집계될 수 있음",
        },
        "summary": summarize_roadview_image_receipt_report(items, received_files, unexpected_files, duplicate_file_name_groups),
        "duplicate_file_name_groups": duplicate_file_name_groups,
        "unexpected_files_sample": unexpected_files[:100],
        "items": items,
    }


def export_roadview_image_acquisition_csvs(
    acquisition_request: dict[str, Any],
    *,
    priority_output: str | Path,
    full_output: str | Path,
    summary_output: str | Path,
) -> dict[str, Any]:
    priority_rows = []
    full_rows = []
    summary_rows = []

    for item in acquisition_request.get("items", []):
        card = item.get("card", {})
        summary_rows.append(acquisition_summary_csv_row(item))
        for image in item.get("priority_images", []):
            row = acquisition_image_csv_row(card, image)
            priority_rows.append(row)
            full_rows.append(row)
        for image in item.get("supplemental_images", []):
            full_rows.append(acquisition_image_csv_row(card, image))

    write_csv(priority_output, acquisition_image_csv_fields(), priority_rows)
    write_csv(full_output, acquisition_image_csv_fields(), full_rows)
    write_csv(summary_output, acquisition_summary_csv_fields(), summary_rows)
    return {
        "priority_rows": len(priority_rows),
        "full_rows": len(full_rows),
        "summary_rows": len(summary_rows),
    }


def acquisition_image_csv_fields() -> list[str]:
    return [
        "place_id",
        "place_name",
        "region",
        "category",
        "verification_status",
        "request_tier",
        "image_file_name",
        "tourist_name",
        "tourist_name_en",
        "captured_at",
        "latitude",
        "longitude",
        "resolution",
    ]


def acquisition_summary_csv_fields() -> list[str]:
    return [
        "place_id",
        "place_name",
        "region",
        "category",
        "verification_status",
        "image_count",
        "priority_sample_count",
        "supplemental_image_count",
        "captured_date_start",
        "captured_date_end",
        "min_latitude",
        "max_latitude",
        "min_longitude",
        "max_longitude",
    ]


def acquisition_image_csv_row(card: dict[str, Any], image: dict[str, Any]) -> dict[str, Any]:
    return {
        "place_id": card.get("id", ""),
        "place_name": card.get("name", ""),
        "region": card.get("region", ""),
        "category": card.get("category", ""),
        "verification_status": card.get("verification_status", ""),
        "request_tier": image.get("request_tier", ""),
        "image_file_name": image.get("image_file_name", ""),
        "tourist_name": image.get("tourist_name", ""),
        "tourist_name_en": image.get("tourist_name_en", ""),
        "captured_at": image.get("captured_at", ""),
        "latitude": image.get("latitude"),
        "longitude": image.get("longitude"),
        "resolution": image.get("resolution", ""),
    }


def acquisition_summary_csv_row(item: dict[str, Any]) -> dict[str, Any]:
    card = item.get("card", {})
    bounds = item.get("coordinate_bounds", {})
    return {
        "place_id": card.get("id", ""),
        "place_name": card.get("name", ""),
        "region": card.get("region", ""),
        "category": card.get("category", ""),
        "verification_status": card.get("verification_status", ""),
        "image_count": item.get("image_count", 0),
        "priority_sample_count": item.get("priority_sample_count", 0),
        "supplemental_image_count": item.get("supplemental_image_count", 0),
        "captured_date_start": item.get("captured_date_start"),
        "captured_date_end": item.get("captured_date_end"),
        "min_latitude": bounds.get("min_latitude"),
        "max_latitude": bounds.get("max_latitude"),
        "min_longitude": bounds.get("min_longitude"),
        "max_longitude": bounds.get("max_longitude"),
    }


def write_csv(path: str | Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def roadview_image_acquisition_item(review_item: dict[str, Any], metadata_rows: list[dict[str, Any]]) -> dict[str, Any]:
    sample_names = {sample.get("image_file_name", "") for sample in review_item.get("review_image_samples", [])}
    sorted_rows = sorted(metadata_rows, key=lambda row: row.get("image_file_name", ""))
    priority_images = [
        acquisition_image_entry(row, "priority_visual_review_sample")
        for row in sorted_rows
        if row.get("image_file_name", "") in sample_names
    ]
    supplemental_images = [
        acquisition_image_entry(row, "supplemental_place_sequence")
        for row in sorted_rows
        if row.get("image_file_name", "") not in sample_names
    ]
    return {
        "card": review_item.get("card", {}),
        "image_count": len(sorted_rows),
        "priority_sample_count": len(priority_images),
        "supplemental_image_count": len(supplemental_images),
        "captured_date_start": captured_date_start(sorted_rows),
        "captured_date_end": captured_date_end(sorted_rows),
        "coordinate_bounds": coordinate_bounds(sorted_rows),
        "priority_images": priority_images,
        "supplemental_images": supplemental_images,
        "requested_delivery": {
            "file_name_preservation_required": True,
            "accepted_extensions": [".jpg", ".JPG", ".jpeg", ".png"],
            "target_directory": "data/raw/roadview_images",
            "priority_first": True,
        },
        "recommended_action": "우선 샘플 이미지를 먼저 수령해 시각 검수 착수, 필요 시 전체 장소 시퀀스로 보강",
    }


def acquisition_image_entry(row: dict[str, Any], request_tier: str) -> dict[str, Any]:
    return {
        "image_file_name": row.get("image_file_name", ""),
        "request_tier": request_tier,
        "tourist_name": row.get("tourist_name", ""),
        "tourist_name_en": row.get("tourist_name_en", ""),
        "captured_at": row.get("captured_at"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "resolution": row.get("resolution", ""),
    }


def roadview_image_asset_manifest_item(review_item: dict[str, Any], asset_root: Path) -> dict[str, Any]:
    card = review_item.get("card", {})
    expected_images = [
        image_asset_entry(sample, asset_root)
        for sample in review_item.get("review_image_samples", [])
    ]
    available_count = sum(1 for image in expected_images if image["status"] == "available")
    missing_count = len(expected_images) - available_count
    status = "ready_for_visual_review" if expected_images and missing_count == 0 else "missing_assets"
    return {
        "card": card,
        "status": status,
        "expected_review_sample_count": len(expected_images),
        "available_review_sample_count": available_count,
        "missing_review_sample_count": missing_count,
        "total_place_image_count": review_item.get("image_count", 0),
        "review_decision": "ready_for_visual_review" if status == "ready_for_visual_review" else "asset_acquisition_required",
        "images": expected_images,
        "recommended_action": image_asset_recommended_action(missing_count),
    }


def image_asset_entry(sample: dict[str, Any], asset_root: Path) -> dict[str, Any]:
    image_file_name = sample.get("image_file_name", "")
    candidate_paths = image_candidate_paths(asset_root, image_file_name)
    present_path = next((path for path in candidate_paths if path.exists()), None)
    return {
        "image_file_name": image_file_name,
        "captured_at": sample.get("captured_at"),
        "latitude": sample.get("latitude"),
        "longitude": sample.get("longitude"),
        "resolution": sample.get("resolution", ""),
        "expected_relative_paths": [
            str(path).replace("\\", "/")
            for path in candidate_paths
        ],
        "present_path": str(present_path).replace("\\", "/") if present_path else None,
        "status": "available" if present_path else "missing",
    }


def image_candidate_paths(asset_root: Path, image_file_name: str) -> list[Path]:
    base_name = Path(image_file_name).stem
    return [
        asset_root / f"{base_name}.jpg",
        asset_root / f"{base_name}.JPG",
        asset_root / f"{base_name}.jpeg",
        asset_root / f"{base_name}.png",
    ]


def received_image_file_index(
    receipt_root: Path,
    *,
    hash_files: bool = True,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    if not receipt_root.exists():
        return {}, []

    records = [
        received_image_file_record(path, receipt_root, hash_files=hash_files)
        for path in sorted(receipt_root.rglob("*"))
        if path.is_file() and path.suffix.lower() in ROADVIEW_IMAGE_FILE_EXTENSIONS
    ]
    index: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        index.setdefault(normalize_image_key(record["file_name"]), []).append(record)
    return index, records


def received_image_file_record(path: Path, receipt_root: Path, *, hash_files: bool = True) -> dict[str, Any]:
    relative_path = path.relative_to(receipt_root)
    return {
        "file_name": path.name,
        "relative_path": str(relative_path).replace("\\", "/"),
        "file_size_bytes": path.stat().st_size,
        "sha256": sha256_file(path) if hash_files else None,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_image_key(image_file_name: str) -> str:
    return Path(image_file_name).stem.casefold()


def acquisition_request_item_images(item: dict[str, Any]) -> list[dict[str, Any]]:
    return item.get("priority_images", []) + item.get("supplemental_images", [])


def roadview_image_receipt_item(
    acquisition_item: dict[str, Any],
    received_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    images = [
        roadview_image_receipt_entry(image, received_index)
        for image in acquisition_request_item_images(acquisition_item)
    ]
    received_count = sum(1 for image in images if image["status"] != "missing")
    missing_count = len(images) - received_count
    duplicate_name_count = sum(1 for image in images if image["status"] == "duplicate_name")
    priority_images = [image for image in images if image.get("request_tier") == "priority_visual_review_sample"]
    received_priority_count = sum(1 for image in priority_images if image["status"] != "missing")
    status = roadview_image_receipt_status(len(images), received_count)
    receipt_decision = roadview_image_receipt_decision(status, duplicate_name_count)
    return {
        "card": acquisition_item.get("card", {}),
        "status": status,
        "receipt_decision": receipt_decision,
        "expected_image_count": len(images),
        "received_image_count": received_count,
        "missing_image_count": missing_count,
        "priority_sample_count": len(priority_images),
        "received_priority_sample_count": received_priority_count,
        "missing_priority_sample_count": len(priority_images) - received_priority_count,
        "duplicate_name_count": duplicate_name_count,
        "images": images,
        "recommended_action": roadview_image_receipt_recommended_action(receipt_decision),
    }


def roadview_image_receipt_entry(
    image: dict[str, Any],
    received_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    matches = received_index.get(normalize_image_key(image.get("image_file_name", "")), [])
    selected = matches[0] if matches else {}
    status = "missing"
    if len(matches) == 1:
        status = "received"
    elif len(matches) > 1:
        status = "duplicate_name"
    return {
        "image_file_name": image.get("image_file_name", ""),
        "request_tier": image.get("request_tier", ""),
        "tourist_name": image.get("tourist_name", ""),
        "tourist_name_en": image.get("tourist_name_en", ""),
        "captured_at": image.get("captured_at"),
        "latitude": image.get("latitude"),
        "longitude": image.get("longitude"),
        "resolution": image.get("resolution", ""),
        "status": status,
        "present_path": selected.get("relative_path"),
        "file_size_bytes": selected.get("file_size_bytes"),
        "sha256": selected.get("sha256"),
        "duplicate_candidate_paths": [match["relative_path"] for match in matches],
    }


def roadview_image_receipt_status(expected_count: int, received_count: int) -> str:
    if received_count == 0:
        return "empty"
    if received_count == expected_count:
        return "complete"
    return "partial"


def roadview_image_receipt_decision(status: str, duplicate_name_count: int) -> str:
    if duplicate_name_count > 0:
        return "needs_duplicate_resolution"
    if status == "complete":
        return "ready_for_visual_manifest"
    return "needs_missing_files"


def roadview_image_receipt_recommended_action(receipt_decision: str) -> str:
    if receipt_decision == "ready_for_visual_manifest":
        return "자산 매니페스트를 재생성하고 시각 검수 시트를 갱신"
    if receipt_decision == "needs_duplicate_resolution":
        return "동일 파일명 후보가 여러 개인 항목을 정리한 뒤 수령 리포트 재생성"
    return "누락 파일을 제공기관 수령 목록과 대조하고 추가 수령 또는 재요청"


def duplicate_received_file_name_groups(received_index: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {
            "image_key": image_key,
            "file_count": len(records),
            "paths": [record["relative_path"] for record in records],
        }
        for image_key, records in sorted(received_index.items())
        if len(records) > 1
    ]


def image_asset_recommended_action(missing_count: int) -> str:
    if missing_count == 0:
        return "대표 이미지 파일을 열어 출입구·경사·바닥·주차장 연결 동선 시각 검수 진행"
    return "공공데이터포털 이미지 원본 수령 후 asset_root에 파일을 배치하고 매니페스트 재생성"


def build_roadview_visual_review_sheet(
    roadview_image_review: dict[str, Any],
    image_asset_manifest: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    assets_by_card_id = review_items_by_card_id(image_asset_manifest)
    items = [
        roadview_visual_review_sheet_item(item, assets_by_card_id.get(item.get("card", {}).get("id", "")))
        for item in roadview_image_review.get("items", [])
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_roadview_image_review_generated_at": roadview_image_review.get("generated_at"),
        "source_image_asset_manifest_generated_at": image_asset_manifest.get("generated_at"),
        "criteria": {
            "verified": "모든 필수 동선 필드가 이미지 근거로 확인되면 roadview_image_verified 게이트 통과",
            "needs_follow_up": "하나라도 확인 불가, 충돌, 추가 촬영 필요이면 active 승격 보류",
        },
        "summary": summarize_roadview_visual_review_sheet(items),
        "items": items,
    }


def roadview_visual_review_sheet_item(
    review_item: dict[str, Any],
    asset_item: dict[str, Any] | None,
) -> dict[str, Any]:
    asset_status = asset_item.get("status", "missing_assets") if asset_item else "missing_assets"
    image_assets = asset_item.get("images", []) if asset_item else visual_review_missing_assets(review_item)
    status = "open" if asset_status == "ready_for_visual_review" else "blocked"
    review_decision = "pending_reviewer_input" if status == "open" else "asset_required"
    return {
        "task_id": review_item.get("task_id", "unknown"),
        "card": review_item.get("card", {}),
        "status": status,
        "review_decision": review_decision,
        "image_asset_status": asset_status,
        "review_image_samples": image_assets,
        "field_results": [
            visual_review_field_result(field, image_assets)
            for field in review_item.get("required_evidence", [])
        ],
        "reviewer_checklist": visual_reviewer_checklist(),
        "recommended_action": visual_review_sheet_recommended_action(status),
    }


def visual_review_missing_assets(review_item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "image_file_name": sample.get("image_file_name", ""),
            "captured_at": sample.get("captured_at"),
            "latitude": sample.get("latitude"),
            "longitude": sample.get("longitude"),
            "resolution": sample.get("resolution", ""),
            "expected_relative_paths": [],
            "present_path": None,
            "status": "missing",
        }
        for sample in review_item.get("review_image_samples", [])
    ]


def visual_review_field_result(field: str, image_assets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "field": field,
        "status": "pending_visual_review",
        "image_file_names": [image.get("image_file_name", "") for image in image_assets],
        "evidence_image_file_names": [],
        "reviewer_note": "",
        "reviewer": None,
        "reviewed_at": None,
    }


def visual_reviewer_checklist() -> list[str]:
    return [
        "대표 이미지 파일이 실제 장소와 일치하는지 확인",
        "주차장 또는 하차 지점에서 주출입구까지 끊김 없는 동선을 확인",
        "출입구 단차, 경사로, 문폭, 자동문 여부를 확인",
        "주요 관람 동선의 경사와 급경사 구간을 확인",
        "바닥 재질이 휠체어·유모차 이동에 부담되는지 확인",
        "불확실하면 verified로 처리하지 말고 needs_follow_up 또는 conflict로 남김",
    ]


def visual_review_sheet_recommended_action(status: str) -> str:
    if status == "open":
        return "이미지 원본을 열어 field_results의 status, evidence_image_file_names, reviewer_note를 입력"
    return "이미지 원본 수령·배치 후 자산 매니페스트를 재생성하고 검수 입력"


def apply_roadview_visual_review_sheet(
    roadview_image_review: dict[str, Any],
    visual_review_sheet: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    sheet_by_card_id = review_items_by_card_id(visual_review_sheet)
    updated_items = []
    report_items = []
    for item in roadview_image_review.get("items", []):
        sheet_item = sheet_by_card_id.get(item.get("card", {}).get("id", ""))
        updated_item, report_item = apply_visual_review_sheet_item(item, sheet_item)
        updated_items.append(updated_item)
        report_items.append(report_item)

    updated_review = deepcopy(roadview_image_review)
    updated_review["items"] = updated_items
    updated_review["summary"] = summarize_roadview_image_review(updated_items)

    apply_report = {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_roadview_image_review_generated_at": roadview_image_review.get("generated_at"),
        "source_visual_review_sheet_generated_at": visual_review_sheet.get("generated_at"),
        "summary": summarize_visual_review_apply_report(report_items),
        "items": report_items,
    }
    return {
        "updated_roadview_image_review": updated_review,
        "apply_report": apply_report,
    }


def apply_visual_review_sheet_item(
    review_item: dict[str, Any],
    sheet_item: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not sheet_item:
        return deepcopy(review_item), visual_review_apply_report_item(review_item, "skipped_no_sheet", review_item)

    results_by_field = {
        result.get("field", ""): result
        for result in sheet_item.get("field_results", [])
        if result.get("field")
    }
    if not results_by_field or all(
        result.get("status") == "pending_visual_review"
        for result in results_by_field.values()
    ):
        return deepcopy(review_item), visual_review_apply_report_item(review_item, "skipped_pending_input", review_item)

    updated_item = deepcopy(review_item)
    updated_item["field_evidence"] = [
        applied_visual_field_evidence(evidence, results_by_field.get(evidence.get("field", "")))
        for evidence in review_item.get("field_evidence", [])
    ]
    status, decision = roadview_visual_review_status(updated_item["field_evidence"])
    updated_item["status"] = status
    updated_item["review_decision"] = decision
    updated_item["recommended_action"] = roadview_visual_review_recommended_action(decision)
    return updated_item, visual_review_apply_report_item(review_item, "applied", updated_item)


def applied_visual_field_evidence(
    current_evidence: dict[str, Any],
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    if not result:
        return deepcopy(current_evidence)
    return {
        "field": current_evidence.get("field", ""),
        "status": result.get("status", "pending_visual_review"),
        "image_file_names": result.get("evidence_image_file_names") or result.get("image_file_names", []),
        "note": result.get("reviewer_note") or visual_field_default_note(result.get("status", "pending_visual_review")),
    }


def visual_field_default_note(status: str) -> str:
    if status == "verified":
        return "수동 이미지 검수로 확인"
    if status == "needs_follow_up":
        return "수동 이미지 검수 결과 추가 확인 필요"
    if status == "conflict":
        return "공식 출처 또는 기존 데이터와 이미지 검수 결과가 충돌"
    if status == "missing":
        return "이미지 근거 부족"
    return "수동 이미지 검수 대기"


def roadview_visual_review_status(field_evidence: list[dict[str, Any]]) -> tuple[str, str]:
    statuses = [evidence.get("status", "pending_visual_review") for evidence in field_evidence]
    if statuses and all(status == "verified" for status in statuses):
        return "resolved", "verified_accessible_route"
    if any(status in {"needs_follow_up", "conflict"} for status in statuses):
        return "in_progress", "needs_manual_escalation"
    if any(status == "missing" for status in statuses):
        return "blocked", "insufficient_images"
    return "open", "pending_visual_review"


def roadview_visual_review_recommended_action(decision: str) -> str:
    if decision == "verified_accessible_route":
        return "로드뷰 이미지 검수 완료. 공식 출처와 함께 active 승격 후보 평가 가능"
    if decision == "needs_manual_escalation":
        return "충돌 또는 추가 확인 필드를 운영자 검수로 보강"
    if decision == "insufficient_images":
        return "필수 동선 이미지 또는 현장 사진을 추가 확보"
    return "이미지 원본을 열어 필드별 수동 검수 계속 진행"


def visual_review_apply_report_item(
    before_item: dict[str, Any],
    action: str,
    after_item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "card": before_item.get("card", {}),
        "action": action,
        "previous_status": before_item.get("status", ""),
        "new_status": after_item.get("status", ""),
        "previous_review_decision": before_item.get("review_decision", ""),
        "new_review_decision": after_item.get("review_decision", ""),
        "field_statuses": {
            evidence.get("field", ""): evidence.get("status", "")
            for evidence in after_item.get("field_evidence", [])
        },
    }


def build_crowd_policy_review(
    work_queue: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    items = [
        crowd_policy_review_item(task)
        for task in work_queue.get("items", [])
        if task.get("task_type") == "crowd_policy_review"
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_work_queue_generated_at": work_queue.get("generated_at"),
        "criteria": {
            "policy_defined": "혼잡 민감 사용자를 위해 기본 회피 시간대와 확인 항목을 정의",
            "blocked": "장소별 운영 일정·행사 일정은 실제 방문 전 최신 출처로 재확인",
        },
        "summary": summarize_crowd_policy_review(items),
        "items": items,
    }


def crowd_policy_review_item(task: dict[str, Any]) -> dict[str, Any]:
    card = task.get("card", {})
    policy = crowd_policy_for_category(card.get("category", "other"), card.get("name", ""))
    return {
        "task_id": task.get("task_id", "unknown"),
        "card": card,
        "status": "resolved",
        "review_decision": "policy_defined",
        "required_evidence": task.get("required_evidence", []),
        "policy": policy,
        "source_queries": task.get("source_queries", []),
        "recommended_action": "방문 직전 운영시간·휴관일·행사 일정을 최신 공식 출처로 재확인",
    }


def crowd_policy_for_category(category: str, name: str) -> dict[str, Any]:
    if category == "indoor":
        return {
            "weekday_weekend_crowd_policy": "평일 개장 직후 또는 마감 1~2시간 전 우선, 주말·공휴일 한낮은 혼잡 가능으로 감점",
            "seasonal_event_crowd_policy": "특별전, 방학, 우천일 대체 실내 방문 수요가 있으면 혼잡 가능으로 표시",
            "quiet_time_recommendation": "평일 오전 첫 시간대 또는 단체 관람이 적은 늦은 오후",
            "check_before_visit": ["휴관일", "특별전 일정", "단체 관람 예약", "주차장 혼잡"],
            "avoid_conditions": ["주말 한낮", "방학 성수기", "비 오는 날 인기 실내 대체지 수요"],
            "operating_calendar_check_required": True,
        }
    if category in {"forest", "rest_area"}:
        return {
            "weekday_weekend_crowd_policy": "평일 오전 우선, 주말·꽃 시즌·축제 기간은 주차와 진입 동선 혼잡 가능으로 감점",
            "seasonal_event_crowd_policy": "꽃 축제, 단풍, 봄·가을 성수기, 수학여행 기간에는 혼잡 가능으로 표시",
            "quiet_time_recommendation": "평일 개장 직후, 더운 계절에는 한낮을 피한 오전 또는 늦은 오후",
            "check_before_visit": ["계절 행사", "주차 가능 여부", "단체 방문", "기상 상황"],
            "avoid_conditions": ["주말 한낮", "꽃 축제 피크", "폭염·강풍·우천"],
            "operating_calendar_check_required": True,
        }
    if category == "culture":
        return {
            "weekday_weekend_crowd_policy": "평일 오전 우선, 주말·기념일·단체 해설 시간은 혼잡 가능으로 감점",
            "seasonal_event_crowd_policy": "기념행사, 교육 프로그램, 문화행사 기간에는 동선 혼잡 가능으로 표시",
            "quiet_time_recommendation": "평일 개장 직후 또는 행사 없는 시간대",
            "check_before_visit": ["기념행사", "교육·해설 프로그램", "단체 관람", "휴관일"],
            "avoid_conditions": ["기념일 행사", "단체 해설 집중 시간", "주말 한낮"],
            "operating_calendar_check_required": True,
        }
    return {
        "weekday_weekend_crowd_policy": f"{name}은 시설 성격 확인 전까지 주말·공휴일 한낮을 혼잡 가능으로 감점",
        "seasonal_event_crowd_policy": "행사·공연·교육 일정이 있으면 혼잡 가능으로 표시",
        "quiet_time_recommendation": "평일 오전 또는 사전 예약·문의로 조용한 시간 확인 후 방문",
        "check_before_visit": ["운영시간", "행사 일정", "예약 필요 여부", "주차장 혼잡"],
        "avoid_conditions": ["주말 한낮", "행사 시작·종료 직전", "단체 방문 시간"],
        "operating_calendar_check_required": True,
    }


def build_category_refinement_review(
    work_queue: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    items = [
        category_refinement_review_item(task)
        for task in work_queue.get("items", [])
        if task.get("task_type") == "category_refinement"
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_work_queue_generated_at": work_queue.get("generated_at"),
        "criteria": {
            "category_refined": "추천 규칙에 쓰이는 1차 서비스 카테고리로 other를 해소",
            "blocked": "시설 성격이 복합적이면 대표 추천 목적 기준으로 카테고리 지정 후 보조 태그로 보완",
        },
        "summary": summarize_category_refinement_review(items),
        "items": items,
    }


def category_refinement_review_item(task: dict[str, Any]) -> dict[str, Any]:
    card = task.get("card", {})
    refinement = category_refinement_for_place(card.get("name", ""), card.get("category", "other"))
    return {
        "task_id": task.get("task_id", "unknown"),
        "card": card,
        "status": "resolved",
        "review_decision": "category_refined",
        "current_category": card.get("category", ""),
        "primary_place_type": refinement["primary_place_type"],
        "recommended_category": refinement["recommended_category"],
        "recommended_situation_tags": refinement["recommended_situation_tags"],
        "rationale": refinement["rationale"],
        "source_queries": task.get("source_queries", []),
        "recommended_action": "카드 승격 시 category와 situation_tags를 함께 갱신",
    }


def category_refinement_for_place(name: str, current_category: str) -> dict[str, Any]:
    refinements = {
        "스누피가든": {
            "primary_place_type": "theme_garden",
            "recommended_category": "rest_area",
            "recommended_situation_tags": ["outdoor", "indoor", "weather_sensitive", "crowded_possible"],
            "rationale": "실내 전시와 야외 정원이 결합된 테마형 정원으로, 서비스 추천에서는 휴식형 공원·정원 장소로 분류",
        },
        "제주아트센터": {
            "primary_place_type": "performing_arts_center",
            "recommended_category": "culture",
            "recommended_situation_tags": ["indoor", "crowded_possible", "requires_reservation"],
            "rationale": "공연·문화 관람 중심 시설이므로 문화 공간으로 분류",
        },
        "제주웰컴센터": {
            "primary_place_type": "tourism_information_support_center",
            "recommended_category": "transport",
            "recommended_situation_tags": ["indoor", "short_stay", "restroom_important"],
            "rationale": "관광정보, 상담, 휠체어 대여 등 여행 지원 기능이 핵심이므로 이동·여행 지원 거점으로 분류",
        },
    }
    return refinements.get(
        name,
        {
            "primary_place_type": "unknown",
            "recommended_category": current_category,
            "recommended_situation_tags": [],
            "rationale": "시설 성격을 추가 확인해야 함",
        },
    )


def build_service_seed_promotion_readiness(
    seed_cards: Iterable[dict[str, Any]],
    work_queue: dict[str, Any],
    official_source_review: dict[str, Any],
    roadview_image_review: dict[str, Any],
    crowd_policy_review: dict[str, Any] | None = None,
    category_refinement_review: dict[str, Any] | None = None,
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    official_by_card_id = review_items_by_card_id(official_source_review)
    image_by_card_id = review_items_by_card_id(roadview_image_review)
    crowd_by_card_id = review_items_by_card_id(crowd_policy_review or {})
    category_by_card_id = review_items_by_card_id(category_refinement_review or {})
    work_items_by_card_id = work_queue_items_by_card_id(work_queue)
    items = [
        promotion_readiness_item(
            card,
            official_by_card_id.get(card.get("id", "")),
            image_by_card_id.get(card.get("id", "")),
            crowd_by_card_id.get(card.get("id", "")),
            category_by_card_id.get(card.get("id", "")),
            work_items_by_card_id.get(card.get("id", ""), []),
        )
        for card in sorted(seed_cards, key=lambda card: card.get("name", ""))
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_work_queue_generated_at": work_queue.get("generated_at"),
        "source_official_review_generated_at": official_source_review.get("generated_at"),
        "source_roadview_image_review_generated_at": roadview_image_review.get("generated_at"),
        "criteria": {
            "ready_for_active_candidate": (
                "공식 출처 검증, 로드뷰 이미지 동선 검증, 혼잡도 정책, 카테고리 정제가 모두 완료된 hidden 카드"
            ),
            "blocked": "하나라도 미완료 게이트가 있으면 active 승격 금지",
        },
        "summary": summarize_promotion_readiness(items),
        "items": items,
    }


def build_service_seed_active_candidates(
    seed_cards: Iterable[dict[str, Any]],
    promotion_readiness: dict[str, Any],
    official_source_review: dict[str, Any],
    category_refinement_review: dict[str, Any] | None = None,
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    readiness_by_card_id = review_items_by_card_id(promotion_readiness)
    official_by_card_id = review_items_by_card_id(official_source_review)
    category_by_card_id = review_items_by_card_id(category_refinement_review or {})
    checked_at = (generated_at or date.today()).isoformat()
    candidates = []
    report_items = []

    for card in sorted(seed_cards, key=lambda item: item.get("name", "")):
        readiness = readiness_by_card_id.get(card.get("id", ""))
        if readiness and readiness.get("promotion_decision") == "ready_for_active_candidate":
            candidate = promoted_active_card(
                card,
                official_by_card_id.get(card.get("id", "")),
                category_by_card_id.get(card.get("id", "")),
                checked_at,
            )
            candidates.append(candidate)
            report_items.append(active_candidate_report_item(card, readiness, "promoted"))
        else:
            report_items.append(active_candidate_report_item(card, readiness, "blocked"))

    report = {
        "generated_at": checked_at,
        "source_promotion_readiness_generated_at": promotion_readiness.get("generated_at"),
        "summary": summarize_active_candidate_report(report_items),
        "items": report_items,
    }
    return {
        "active_candidates": candidates,
        "promotion_report": report,
    }


def build_service_seed_gate_status(
    acquisition_request: dict[str, Any],
    receipt_report: dict[str, Any],
    image_asset_manifest: dict[str, Any],
    visual_review_sheet: dict[str, Any],
    promotion_readiness: dict[str, Any],
    active_candidate_report: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    receipt_by_card_id = review_items_by_card_id(receipt_report)
    asset_by_card_id = review_items_by_card_id(image_asset_manifest)
    visual_by_card_id = review_items_by_card_id(visual_review_sheet)
    active_by_card_id = review_items_by_card_id(active_candidate_report)
    items = [
        service_seed_gate_status_item(
            readiness_item,
            receipt_by_card_id.get(readiness_item.get("card", {}).get("id", "")),
            asset_by_card_id.get(readiness_item.get("card", {}).get("id", "")),
            visual_by_card_id.get(readiness_item.get("card", {}).get("id", "")),
            active_by_card_id.get(readiness_item.get("card", {}).get("id", "")),
        )
        for readiness_item in promotion_readiness.get("items", [])
    ]
    summary = summarize_service_seed_gate_status(
        items,
        acquisition_request,
        receipt_report,
        image_asset_manifest,
        visual_review_sheet,
        promotion_readiness,
        active_candidate_report,
    )
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_roadview_image_acquisition_request_generated_at": acquisition_request.get("generated_at"),
        "source_roadview_image_receipt_report_generated_at": receipt_report.get("generated_at"),
        "source_image_asset_manifest_generated_at": image_asset_manifest.get("generated_at"),
        "source_visual_review_sheet_generated_at": visual_review_sheet.get("generated_at"),
        "source_promotion_readiness_generated_at": promotion_readiness.get("generated_at"),
        "source_active_candidate_report_generated_at": active_candidate_report.get("generated_at"),
        "criteria": {
            "ready_for_service_activation": "이미지 수령, 샘플 자산, 로드뷰 시각 검수, active 후보 산출이 모두 통과",
            "blocked": "어느 하나라도 실패하면 공개 서비스 데이터로 승격하지 않음",
        },
        "overall_status": service_seed_overall_status(summary),
        "current_primary_stage": service_seed_current_primary_stage(summary),
        "pipeline_gates": service_seed_pipeline_gates(
            acquisition_request,
            receipt_report,
            image_asset_manifest,
            visual_review_sheet,
            promotion_readiness,
            active_candidate_report,
        ),
        "summary": summary,
        "items": items,
    }


def promoted_active_card(
    card: dict[str, Any],
    official_item: dict[str, Any] | None,
    category_item: dict[str, Any] | None,
    checked_at: str,
) -> dict[str, Any]:
    candidate = deepcopy(card)
    candidate["status"] = "active"
    candidate["verification"] = {
        "status": "verified",
        "checked_at": checked_at,
        "checked_by": "roadview_promotion_pipeline",
        "missing_fields": [],
    }
    apply_category_refinement(candidate, category_item)
    apply_promotion_accessibility_hardening(candidate)
    candidate["sources"] = merged_promotion_sources(candidate.get("sources", []), official_item)
    candidate["operator_notes"] = (
        f"{candidate.get('operator_notes', '')}\n"
        "roadview_promotion_pipeline: 공식 출처, 혼잡 정책, 카테고리 정제, 로드뷰 이미지 검수 게이트 통과 후 active 후보."
    ).strip()
    final_note = "방문 전 운영시간, 공사, 현장 혼잡 여부는 최신 공식 출처로 재확인 필요"
    if final_note not in candidate.get("safety_notes", []):
        candidate.setdefault("safety_notes", []).append(final_note)
    return candidate


def apply_category_refinement(card: dict[str, Any], category_item: dict[str, Any] | None) -> None:
    if not category_refinement_resolved(category_item):
        return
    card["category"] = category_item.get("recommended_category", card.get("category", "other"))
    existing_tags = list(card.get("situation_tags", []))
    for tag in category_item.get("recommended_situation_tags", []):
        if tag not in existing_tags:
            existing_tags.append(tag)
    card["situation_tags"] = existing_tags


def apply_promotion_accessibility_hardening(card: dict[str, Any]) -> None:
    accessibility = card.setdefault("accessibility", {})
    for field in ["slope_or_stairs", "surface_condition"]:
        value = accessibility.get(field)
        if value and value.get("state") in {"needs_check", "unknown"}:
            value["state"] = "partial"
            value["source_ref"] = "roadview_visual_review"
            value["note"] = "로드뷰 이미지 수동 검수로 기본 동선 확인. 현장 상황은 방문 전 재확인 필요"
    crowd = accessibility.get("crowd_level")
    if crowd and crowd.get("state") in {"needs_check", "unknown"}:
        crowd["state"] = "partial"
        crowd["source_ref"] = "roadview_crowd_policy_review"
        crowd["note"] = "혼잡 민감 사용자를 위한 기본 회피 시간대 정책 적용. 방문 전 행사·단체 관람 여부 확인 필요"


def merged_promotion_sources(existing_sources: list[dict[str, Any]], official_item: dict[str, Any] | None) -> list[dict[str, Any]]:
    sources = deepcopy(existing_sources)
    seen_urls = {source.get("url") for source in sources}
    for candidate in (official_item or {}).get("source_candidates", []):
        if candidate.get("evidence_status") != "usable_accessibility_detail":
            continue
        url = candidate.get("url", "")
        if not url or url in seen_urls:
            continue
        sources.append(
            {
                "title": candidate.get("title", "공식/공공 접근성 출처"),
                "url": url,
                "type": card_source_type(candidate.get("source_type", "")),
            }
        )
        seen_urls.add(url)
    return sources


def card_source_type(source_type: str) -> str:
    if source_type == "official_site":
        return "official"
    if source_type in {
        "easyjeju_accessibility_detail",
        "open_tourism_accessibility_detail",
        "public_agency",
        "visitjeju",
    }:
        return "public_agency"
    return "unknown"


def active_candidate_report_item(
    card: dict[str, Any],
    readiness: dict[str, Any] | None,
    action: str,
) -> dict[str, Any]:
    return {
        "card": card_ref(card),
        "action": action,
        "promotion_decision": readiness.get("promotion_decision", "missing_readiness") if readiness else "missing_readiness",
        "blocking_gates": readiness.get("blocking_gates", []) if readiness else ["promotion_readiness_missing"],
        "recommended_action": (
            "active 후보 파일에 포함"
            if action == "promoted"
            else "차단 게이트 해소 후 active 후보 생성 재실행"
        ),
    }


def service_seed_gate_status_item(
    readiness_item: dict[str, Any],
    receipt_item: dict[str, Any] | None,
    asset_item: dict[str, Any] | None,
    visual_item: dict[str, Any] | None,
    active_item: dict[str, Any] | None,
) -> dict[str, Any]:
    gate_statuses = service_seed_item_gate_statuses(readiness_item, receipt_item, asset_item, visual_item, active_item)
    blocking_gates = [gate for gate, status in gate_statuses.items() if status == "fail"]
    primary_stage = service_seed_primary_blocking_stage(gate_statuses, receipt_item, visual_item)
    return {
        "card": readiness_item.get("card", {}),
        "primary_blocking_stage": primary_stage,
        "gate_statuses": gate_statuses,
        "blocking_gates": blocking_gates,
        "image_receipt_status": service_seed_receipt_status(receipt_item),
        "asset_manifest_status": service_seed_asset_status(asset_item),
        "visual_review_status": service_seed_visual_status(visual_item, readiness_item),
        "promotion_status": service_seed_promotion_status(readiness_item),
        "active_candidate_status": service_seed_active_status(active_item),
        "recommended_action": service_seed_gate_recommended_action(primary_stage),
    }


def service_seed_item_gate_statuses(
    readiness_item: dict[str, Any],
    receipt_item: dict[str, Any] | None,
    asset_item: dict[str, Any] | None,
    visual_item: dict[str, Any] | None,
    active_item: dict[str, Any] | None,
) -> dict[str, str]:
    readiness_gates = readiness_item.get("gate_statuses", {})
    return {
        "image_receipt_complete": gate_state(
            bool(
                receipt_item
                and receipt_item.get("receipt_decision") == "ready_for_visual_manifest"
                and receipt_item.get("missing_image_count", 0) == 0
                and receipt_item.get("duplicate_name_count", 0) == 0
            )
        ),
        "review_samples_available": gate_state(
            bool(asset_item and asset_item.get("review_decision") == "ready_for_visual_review")
        ),
        "visual_review_sheet_open": gate_state(
            bool(
                visual_item
                and (
                    visual_item.get("status") == "open"
                    or readiness_gates.get("roadview_image_verified") == "pass"
                )
            )
        ),
        "roadview_image_verified": gate_state(readiness_gates.get("roadview_image_verified") == "pass"),
        "active_candidate_ready": gate_state(
            bool(
                active_item
                and active_item.get("action") == "promoted"
                and readiness_item.get("promotion_decision") == "ready_for_active_candidate"
            )
        ),
    }


def service_seed_primary_blocking_stage(
    gate_statuses: dict[str, str],
    receipt_item: dict[str, Any] | None,
    visual_item: dict[str, Any] | None,
) -> str:
    if gate_statuses.get("image_receipt_complete") == "fail":
        if receipt_item and receipt_item.get("receipt_decision") == "needs_duplicate_resolution":
            return "resolving_duplicate_images"
        return "awaiting_image_receipt"
    if gate_statuses.get("review_samples_available") == "fail":
        return "preparing_visual_assets"
    if gate_statuses.get("visual_review_sheet_open") == "fail":
        return "preparing_visual_review_sheet"
    if gate_statuses.get("roadview_image_verified") == "fail":
        if visual_item and visual_item.get("review_decision") in {"needs_manual_escalation", "insufficient_images"}:
            return "resolving_visual_review_findings"
        return "awaiting_visual_review"
    if gate_statuses.get("active_candidate_ready") == "fail":
        return "preparing_active_candidate_export"
    return "ready_for_service_activation"


def service_seed_receipt_status(receipt_item: dict[str, Any] | None) -> dict[str, Any]:
    if not receipt_item:
        return {
            "status": "missing_report_item",
            "receipt_decision": "missing",
            "expected_image_count": 0,
            "received_image_count": 0,
            "missing_image_count": 0,
            "priority_sample_count": 0,
            "received_priority_sample_count": 0,
            "missing_priority_sample_count": 0,
            "duplicate_name_count": 0,
        }
    return {
        "status": receipt_item.get("status", ""),
        "receipt_decision": receipt_item.get("receipt_decision", ""),
        "expected_image_count": receipt_item.get("expected_image_count", 0),
        "received_image_count": receipt_item.get("received_image_count", 0),
        "missing_image_count": receipt_item.get("missing_image_count", 0),
        "priority_sample_count": receipt_item.get("priority_sample_count", 0),
        "received_priority_sample_count": receipt_item.get("received_priority_sample_count", 0),
        "missing_priority_sample_count": receipt_item.get("missing_priority_sample_count", 0),
        "duplicate_name_count": receipt_item.get("duplicate_name_count", 0),
    }


def service_seed_asset_status(asset_item: dict[str, Any] | None) -> dict[str, Any]:
    if not asset_item:
        return {
            "status": "missing_manifest_item",
            "review_decision": "missing",
            "expected_review_sample_count": 0,
            "available_review_sample_count": 0,
            "missing_review_sample_count": 0,
        }
    return {
        "status": asset_item.get("status", ""),
        "review_decision": asset_item.get("review_decision", ""),
        "expected_review_sample_count": asset_item.get("expected_review_sample_count", 0),
        "available_review_sample_count": asset_item.get("available_review_sample_count", 0),
        "missing_review_sample_count": asset_item.get("missing_review_sample_count", 0),
    }


def service_seed_visual_status(visual_item: dict[str, Any] | None, readiness_item: dict[str, Any]) -> dict[str, Any]:
    roadview_status = readiness_item.get("roadview_image_review_status", {})
    if not visual_item:
        return {
            "status": roadview_status.get("status", "missing_sheet_item"),
            "review_decision": roadview_status.get("review_decision", "missing"),
            "image_asset_status": "missing",
            "field_result_count": 0,
            "pending_field_count": len(roadview_status.get("pending_fields", [])),
        }
    field_results = visual_item.get("field_results", [])
    return {
        "status": visual_item.get("status", ""),
        "review_decision": visual_item.get("review_decision", ""),
        "image_asset_status": visual_item.get("image_asset_status", ""),
        "field_result_count": len(field_results),
        "pending_field_count": sum(1 for result in field_results if result.get("status") == "pending_visual_review"),
    }


def service_seed_promotion_status(readiness_item: dict[str, Any]) -> dict[str, Any]:
    return {
        "promotion_decision": readiness_item.get("promotion_decision", ""),
        "blocking_gates": readiness_item.get("blocking_gates", []),
    }


def service_seed_active_status(active_item: dict[str, Any] | None) -> dict[str, Any]:
    if not active_item:
        return {
            "action": "missing_report_item",
            "promotion_decision": "missing",
            "blocking_gates": [],
        }
    return {
        "action": active_item.get("action", ""),
        "promotion_decision": active_item.get("promotion_decision", ""),
        "blocking_gates": active_item.get("blocking_gates", []),
    }


def service_seed_gate_recommended_action(primary_stage: str) -> str:
    actions = {
        "awaiting_image_receipt": "누락 원본 이미지 복구 또는 대체 원본 수령 후 data/raw/roadview_images에 배치",
        "resolving_duplicate_images": "중복 파일명 후보를 정리하고 수령 리포트 재생성",
        "preparing_visual_assets": "자산 매니페스트를 재생성해 우선 검수 샘플 존재 여부 확인",
        "preparing_visual_review_sheet": "시각 검수 시트를 재생성해 운영자 입력 행 생성",
        "awaiting_visual_review": "로드뷰 이미지로 필수 동선 필드를 수동 검수",
        "resolving_visual_review_findings": "충돌·추가 확인 필드를 보강하고 검수 결과 재적용",
        "preparing_active_candidate_export": "승격 준비 리포트와 active 후보 산출물을 재생성",
        "ready_for_service_activation": "최종 문구와 운영 정책 확인 후 공개 서비스 데이터에 반영",
    }
    return actions.get(primary_stage, "차단 단계를 확인하고 관련 산출물을 재생성")


def promotion_readiness_item(
    card: dict[str, Any],
    official_item: dict[str, Any] | None,
    image_item: dict[str, Any] | None,
    crowd_item: dict[str, Any] | None,
    category_item: dict[str, Any] | None,
    work_items: list[dict[str, Any]],
) -> dict[str, Any]:
    unresolved_work_items = promotion_unresolved_work_items(work_items)
    gate_statuses = {
        "seed_card_hidden": gate_state(card.get("status") == "hidden"),
        "official_source_verified": gate_state(official_source_verified(official_item)),
        "roadview_image_verified": gate_state(roadview_image_verified(image_item)),
        "crowd_policy_resolved": gate_state(
            crowd_policy_resolved(crowd_item)
            or not has_unresolved_task_type(unresolved_work_items, "crowd_policy_review")
        ),
        "category_refinement_resolved": gate_state(
            category_refinement_resolved(category_item)
            or not has_unresolved_task_type(unresolved_work_items, "category_refinement")
        ),
    }
    blocking_gates = [gate for gate, status in gate_statuses.items() if status != "pass"]
    decision = "ready_for_active_candidate" if not blocking_gates else "blocked_pending_hardening"
    return {
        "card": card_ref(card),
        "current_status": card.get("status", ""),
        "promotion_decision": decision,
        "gate_statuses": gate_statuses,
        "blocking_gates": blocking_gates,
        "official_source_review_status": official_source_gate_summary(official_item),
        "roadview_image_review_status": roadview_image_gate_summary(image_item),
        "crowd_policy_review_status": crowd_policy_gate_summary(crowd_item, unresolved_work_items),
        "category_refinement_review_status": category_refinement_gate_summary(category_item, unresolved_work_items),
        "unresolved_work_items": unresolved_work_items,
        "recommended_action": promotion_recommended_action(blocking_gates),
    }


def review_items_by_card_id(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item.get("card", {}).get("id", ""): item
        for item in review.get("items", [])
        if item.get("card", {}).get("id")
    }


def work_queue_items_by_card_id(work_queue: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in work_queue.get("items", []):
        card_id = item.get("card", {}).get("id", "")
        if card_id:
            grouped.setdefault(card_id, []).append(item)
    return grouped


def promotion_unresolved_work_items(work_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unresolved_statuses = {"open", "in_progress", "blocked"}
    return [
        {
            "task_id": item.get("task_id", ""),
            "task_type": item.get("task_type", ""),
            "priority": item.get("priority", ""),
            "status": item.get("status", ""),
        }
        for item in work_items
        if item.get("task_type") in {"crowd_policy_review", "category_refinement"}
        and item.get("status") in unresolved_statuses
    ]


def official_source_verified(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    if item.get("status") == "resolved" and item.get("review_decision") == "verified_usable_source":
        return True
    return bool(item.get("source_candidates")) and not blocking_official_missing_fields(item)


def roadview_image_verified(item: dict[str, Any] | None) -> bool:
    return bool(
        item
        and item.get("status") == "resolved"
        and item.get("review_decision") == "verified_accessible_route"
    )


def crowd_policy_resolved(item: dict[str, Any] | None) -> bool:
    return bool(item and item.get("status") == "resolved" and item.get("review_decision") == "policy_defined")


def category_refinement_resolved(item: dict[str, Any] | None) -> bool:
    return bool(
        item
        and item.get("status") == "resolved"
        and item.get("review_decision") == "category_refined"
        and item.get("recommended_category")
    )


def has_unresolved_task_type(work_items: list[dict[str, Any]], task_type: str) -> bool:
    return any(item.get("task_type") == task_type for item in work_items)


def gate_state(passed: bool) -> str:
    return "pass" if passed else "fail"


def official_source_gate_summary(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {
            "status": "missing",
            "review_decision": "missing",
            "source_candidate_count": 0,
            "missing_fields": [],
            "visual_fallback_fields": [],
            "blocking_missing_fields": [],
        }
    missing_fields = missing_evidence_fields(item)
    return {
        "status": item.get("status", ""),
        "review_decision": item.get("review_decision", ""),
        "source_candidate_count": len(item.get("source_candidates", [])),
        "missing_fields": missing_fields,
        "visual_fallback_fields": visual_fallback_official_fields(item),
        "blocking_missing_fields": blocking_official_missing_fields(item),
    }


def roadview_image_gate_summary(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {
            "status": "missing",
            "review_decision": "missing",
            "image_count": 0,
            "pending_fields": [],
        }
    return {
        "status": item.get("status", ""),
        "review_decision": item.get("review_decision", ""),
        "image_count": item.get("image_count", 0),
        "pending_fields": pending_image_fields(item),
    }


def crowd_policy_gate_summary(item: dict[str, Any] | None, work_items: list[dict[str, Any]]) -> dict[str, Any]:
    if not has_unresolved_task_type(work_items, "crowd_policy_review") and not item:
        return {
            "status": "not_required",
            "review_decision": "not_required",
            "quiet_time_recommendation": None,
        }
    if not item:
        return {
            "status": "missing",
            "review_decision": "missing",
            "quiet_time_recommendation": None,
        }
    return {
        "status": item.get("status", ""),
        "review_decision": item.get("review_decision", ""),
        "quiet_time_recommendation": item.get("policy", {}).get("quiet_time_recommendation"),
    }


def category_refinement_gate_summary(item: dict[str, Any] | None, work_items: list[dict[str, Any]]) -> dict[str, Any]:
    if not has_unresolved_task_type(work_items, "category_refinement") and not item:
        return {
            "status": "not_required",
            "review_decision": "not_required",
            "recommended_category": None,
        }
    if not item:
        return {
            "status": "missing",
            "review_decision": "missing",
            "recommended_category": None,
        }
    return {
        "status": item.get("status", ""),
        "review_decision": item.get("review_decision", ""),
        "recommended_category": item.get("recommended_category"),
    }


def missing_evidence_fields(item: dict[str, Any]) -> list[str]:
    return [
        evidence.get("field", "")
        for evidence in item.get("field_evidence", [])
        if evidence.get("status") == "missing"
    ]


def visual_fallback_official_fields(item: dict[str, Any]) -> list[str]:
    return sorted(
        field
        for field in missing_evidence_fields(item)
        if field in OFFICIAL_SOURCE_VISUAL_FALLBACK_FIELDS
    )


def blocking_official_missing_fields(item: dict[str, Any]) -> list[str]:
    return sorted(
        field
        for field in missing_evidence_fields(item)
        if field not in OFFICIAL_SOURCE_VISUAL_FALLBACK_FIELDS
    )


def pending_image_fields(item: dict[str, Any]) -> list[str]:
    return [
        evidence.get("field", "")
        for evidence in item.get("field_evidence", [])
        if evidence.get("status") in {"pending_visual_review", "missing", "needs_follow_up", "conflict"}
    ]


def promotion_recommended_action(blocking_gates: list[str]) -> str:
    if not blocking_gates:
        return "active 후보 파일로 분리 가능. 최종 문구와 운영정책 확인 후 공개 승격"
    if "roadview_image_verified" in blocking_gates:
        return "로드뷰 원본 이미지로 출입구·경사·바닥·주차장 연결 동선을 먼저 검수"
    if "official_source_verified" in blocking_gates:
        return "공식/공공 접근성 상세 출처의 누락 필드를 보강"
    if "crowd_policy_resolved" in blocking_gates:
        return "혼잡 민감 사용자용 회피 시간대와 운영 정책을 정의"
    if "category_refinement_resolved" in blocking_gates:
        return "서비스 추천 카테고리를 정제"
    return "차단 게이트를 해소한 뒤 active 승격 재평가"


def roadview_image_review_item(
    task: dict[str, Any],
    metadata_rows: list[dict[str, Any]],
    *,
    available_image_keys: set[str] | None = None,
) -> dict[str, Any]:
    required_evidence = list(task.get("required_evidence", []))
    sorted_rows = sorted(metadata_rows, key=lambda row: row.get("image_file_name", ""))
    status = "open" if sorted_rows else "blocked"
    decision = "pending_visual_review" if sorted_rows else "metadata_missing"
    return {
        "task_id": task.get("task_id", "unknown"),
        "card": task.get("card", {}),
        "status": status,
        "review_decision": decision,
        "required_evidence": required_evidence,
        "image_count": len(sorted_rows),
        "captured_date_start": captured_date_start(sorted_rows),
        "captured_date_end": captured_date_end(sorted_rows),
        "coordinate_bounds": coordinate_bounds(sorted_rows),
        "review_image_samples": review_image_samples(sorted_rows, available_image_keys=available_image_keys),
        "field_evidence": [
            roadview_field_evidence(field, sorted_rows, available_image_keys=available_image_keys)
            for field in required_evidence
        ],
        "recommended_action": roadview_image_recommended_action(sorted_rows),
    }


def roadview_field_evidence(
    field: str,
    metadata_rows: list[dict[str, Any]],
    *,
    available_image_keys: set[str] | None = None,
) -> dict[str, Any]:
    if not metadata_rows:
        return {
            "field": field,
            "status": "missing",
            "image_file_names": [],
            "note": "로드뷰 이미지 메타데이터 없음",
        }
    return {
        "field": field,
        "status": "pending_visual_review",
        "image_file_names": [
            row.get("image_file_name", "")
            for row in review_image_samples(metadata_rows, available_image_keys=available_image_keys)[:3]
        ],
        "note": "대표 이미지와 원본 이미지 시퀀스를 열어 시각 검수 필요",
    }


def captured_date_start(metadata_rows: list[dict[str, Any]]) -> str | None:
    dates = captured_dates(metadata_rows)
    return dates[0] if dates else None


def captured_date_end(metadata_rows: list[dict[str, Any]]) -> str | None:
    dates = captured_dates(metadata_rows)
    return dates[-1] if dates else None


def captured_dates(metadata_rows: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(row.get("captured_at", ""))[:10]
            for row in metadata_rows
            if row.get("captured_at")
        }
    )


def coordinate_bounds(metadata_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    coordinates = [
        (row.get("latitude"), row.get("longitude"))
        for row in metadata_rows
        if isinstance(row.get("latitude"), (int, float)) and isinstance(row.get("longitude"), (int, float))
    ]
    if not coordinates:
        return {
            "min_latitude": None,
            "max_latitude": None,
            "min_longitude": None,
            "max_longitude": None,
        }
    latitudes = [coordinate[0] for coordinate in coordinates]
    longitudes = [coordinate[1] for coordinate in coordinates]
    return {
        "min_latitude": min(latitudes),
        "max_latitude": max(latitudes),
        "min_longitude": min(longitudes),
        "max_longitude": max(longitudes),
    }


def review_image_samples(
    metadata_rows: list[dict[str, Any]],
    *,
    limit: int = 6,
    available_image_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = sorted(metadata_rows, key=lambda row: row.get("image_file_name", ""))
    if len(rows) <= limit:
        sampled = rows
    else:
        indexes = sorted({round(index * (len(rows) - 1) / (limit - 1)) for index in range(limit)})
        if available_image_keys:
            indexes = replace_missing_sample_indexes_with_available(rows, indexes, available_image_keys)
        sampled = [rows[index] for index in indexes]
    return [
        {
            "image_file_name": row.get("image_file_name", ""),
            "captured_at": row.get("captured_at"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "resolution": row.get("resolution", ""),
        }
        for row in sampled
    ]


def available_roadview_image_keys(asset_root: str | Path | None) -> set[str]:
    if not asset_root:
        return set()
    root = Path(asset_root)
    if not root.exists():
        return set()
    return {
        normalize_image_key(path.name)
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in ROADVIEW_IMAGE_FILE_EXTENSIONS
    }


def replace_missing_sample_indexes_with_available(
    rows: list[dict[str, Any]],
    indexes: list[int],
    available_image_keys: set[str],
) -> list[int]:
    selected = set(indexes)
    available_indexes = [
        index
        for index, row in enumerate(rows)
        if normalize_image_key(row.get("image_file_name", "")) in available_image_keys
    ]
    if not available_indexes:
        return indexes

    replaced = []
    for index in indexes:
        image_key = normalize_image_key(rows[index].get("image_file_name", ""))
        if image_key in available_image_keys:
            replaced.append(index)
            continue
        replacement = nearest_available_sample_index(index, available_indexes, selected)
        if replacement is None:
            replaced.append(index)
        else:
            selected.discard(index)
            selected.add(replacement)
            replaced.append(replacement)
    return sorted(set(replaced))


def nearest_available_sample_index(
    target_index: int,
    available_indexes: list[int],
    selected: set[int],
) -> int | None:
    candidates = [index for index in available_indexes if index not in selected]
    if not candidates:
        return None
    return min(candidates, key=lambda index: (abs(index - target_index), index))


def roadview_image_recommended_action(metadata_rows: list[dict[str, Any]]) -> str:
    if not metadata_rows:
        return "로드뷰 이미지 원본 또는 현장 사진 확보 전 active 전환 보류"
    return "대표 이미지와 전체 이미지 시퀀스로 단차·경사·바닥재·주차장 연결 동선을 검수"


def official_source_review_item(task: dict[str, Any]) -> dict[str, Any]:
    required_evidence = list(task.get("required_evidence", []))
    return {
        "task_id": task.get("task_id", "unknown"),
        "card": task.get("card", {}),
        "status": "open",
        "review_decision": "pending_source_verification",
        "required_evidence": required_evidence,
        "search_queries": task.get("source_queries", []),
        "accepted_source_types": OFFICIAL_ACCESSIBILITY_SOURCE_TYPES,
        "source_candidates": [],
        "field_evidence": [missing_field_evidence(field) for field in required_evidence],
        "recommended_action": "공식/공공 URL 후보를 확인한 뒤 장소명 일치 여부와 필드별 근거를 기록",
    }


def missing_field_evidence(field: str) -> dict[str, Any]:
    return {
        "field": field,
        "status": "missing",
        "source_url": None,
        "note": "공식/공공 상세 출처 확인 전",
    }


def official_source_task(review_item: dict[str, Any]) -> dict[str, Any]:
    card = review_item.get("card", {})
    return {
        "task_id": f"{card.get('id', 'unknown')}_official_source_review",
        "card": card,
        "task_type": "official_source_review",
        "priority": "high",
        "status": "open",
        "required_evidence": [
            "official_or_public_accessibility_url",
            "operating_status",
            "accessible_toilet",
            "parking",
            "wheelchair_or_stroller_rental",
            "slope_or_stairs",
            "surface_condition",
        ],
        "source_queries": review_item.get("official_source_queries", []),
        "image_samples": [],
        "recommended_action": "공식/공공 상세 출처 URL을 확인하고 접근성 필드별 근거를 기록",
    }


def roadview_image_task(review_item: dict[str, Any]) -> dict[str, Any]:
    card = review_item.get("card", {})
    evidence = review_item.get("roadview_image_evidence", {})
    return {
        "task_id": f"{card.get('id', 'unknown')}_roadview_image_review",
        "card": card,
        "task_type": "roadview_image_review",
        "priority": "high",
        "status": "open",
        "required_evidence": [
            "entrance_step_or_ramp",
            "main_path_slope",
            "surface_condition",
            "parking_to_entrance_route",
        ],
        "source_queries": [],
        "image_samples": evidence.get("sample_image_file_names", []),
        "image_count": evidence.get("image_count", 0),
        "captured_date_start": evidence.get("captured_date_start"),
        "captured_date_end": evidence.get("captured_date_end"),
        "recommended_action": "로드뷰 원본 이미지에서 경사·단차·바닥 상태와 주차장-출입구 연결 동선을 검수",
    }


def crowd_policy_task(review_item: dict[str, Any]) -> dict[str, Any]:
    card = review_item.get("card", {})
    return {
        "task_id": f"{card.get('id', 'unknown')}_crowd_policy_review",
        "card": card,
        "task_type": "crowd_policy_review",
        "priority": "medium",
        "status": "open",
        "required_evidence": [
            "weekday_weekend_crowd_policy",
            "seasonal_event_crowd_policy",
            "quiet_time_recommendation",
        ],
        "source_queries": [
            f"{card.get('name', '')} 운영시간 행사 혼잡",
            f"{card.get('name', '')} 단체관람 예약",
        ],
        "image_samples": [],
        "recommended_action": "혼잡 민감 사용자에게 표시할 혼잡도 정책과 회피 시간대를 정의",
    }


def category_refinement_task(review_item: dict[str, Any]) -> dict[str, Any]:
    card = review_item.get("card", {})
    return {
        "task_id": f"{card.get('id', 'unknown')}_category_refinement",
        "card": card,
        "task_type": "category_refinement",
        "priority": "medium",
        "status": "open",
        "required_evidence": ["primary_place_type", "recommended_category"],
        "source_queries": [
            f"{card.get('name', '')} 공식",
            f"{card.get('name', '')} 시설 유형",
        ],
        "image_samples": [],
        "recommended_action": "other 카테고리를 indoor, culture, rest_area 등 서비스 추천 카테고리로 정제",
    }


def service_seed_review_item(card: dict[str, Any], metadata_rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing_fields = list(card.get("verification", {}).get("missing_fields", []))
    blockers = seed_blockers(card, missing_fields, metadata_rows)
    return {
        "card": card_ref(card),
        "current_status": card.get("status", ""),
        "decision": "blocked_pending_detail_review" if blockers else "publishable_after_final_review",
        "blockers": blockers,
        "required_checks": required_seed_checks(card, missing_fields),
        "roadview_image_evidence": image_evidence(metadata_rows),
        "official_source_queries": official_source_queries(card.get("name", "")),
        "recommended_action": seed_recommended_action(blockers),
    }


def seed_blockers(card: dict[str, Any], missing_fields: list[str], metadata_rows: list[dict[str, Any]]) -> list[str]:
    blockers = []
    if not has_detail_source(card):
        blockers.append("official_detail_source_required")
    for field in ["slope_or_stairs", "surface_condition"]:
        if field in missing_fields:
            blockers.append(f"{field}_review_required")
    if "crowd_level" in missing_fields:
        blockers.append("crowd_level_policy_required")
    if not metadata_rows:
        blockers.append("roadview_image_metadata_missing")
    if card.get("status") != "hidden":
        blockers.append("seed_card_must_remain_hidden_before_publish")
    return blockers


def required_seed_checks(card: dict[str, Any], missing_fields: list[str]) -> list[str]:
    checks = ["official_detail_source_review", "operating_status_review"]
    if "slope_or_stairs" in missing_fields:
        checks.append("slope_or_stairs_review")
    if "surface_condition" in missing_fields:
        checks.append("surface_condition_review")
    if "crowd_level" in missing_fields:
        checks.append("crowd_level_policy_review")
    if card.get("category") == "other":
        checks.append("category_refinement")
    return sorted(set(checks))


def image_evidence(metadata_rows: list[dict[str, Any]]) -> dict[str, Any]:
    dates = sorted(
        {
            str(row.get("captured_at", ""))[:10]
            for row in metadata_rows
            if row.get("captured_at")
        }
    )
    return {
        "image_count": len(metadata_rows),
        "captured_date_start": dates[0] if dates else None,
        "captured_date_end": dates[-1] if dates else None,
        "sample_image_file_names": [row.get("image_file_name", "") for row in metadata_rows[:3]],
        "review_status": "ready_for_image_review" if metadata_rows else "metadata_missing",
    }


def official_source_queries(name: str) -> list[str]:
    return [
        f"이지제주 {name}",
        f"열린관광 모두의 여행 {name}",
        f"{name} 공식 홈페이지 장애인 화장실 주차 휠체어",
    ]


def seed_recommended_action(blockers: list[str]) -> str:
    if blockers:
        return "hidden 유지. 공식 상세 출처와 로드뷰 이미지로 차단 사유를 해소한 뒤 active 전환 검토"
    return "최종 문구 검토 후 active 전환 가능"


def has_detail_source(card: dict[str, Any]) -> bool:
    for source in card.get("sources", []):
        url = source.get("url", "")
        if url and url != ROADVIEW_FACILITY_SOURCE_URL:
            return True
    return False


def group_metadata_by_name(image_metadata: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in image_metadata:
        grouped.setdefault(row.get("tourist_name", ""), []).append(row)
    return grouped


def summarize_service_seed_review(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "by_decision": dict(Counter(item.get("decision", "unknown") for item in items)),
        "by_image_review_status": dict(
            Counter(item.get("roadview_image_evidence", {}).get("review_status", "unknown") for item in items)
        ),
        "total_roadview_images": sum(item.get("roadview_image_evidence", {}).get("image_count", 0) for item in items),
        "blocker_counts": dict(Counter(blocker for item in items for blocker in item.get("blockers", []))),
    }


def summarize_work_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "by_task_type": dict(Counter(item.get("task_type", "unknown") for item in items)),
        "by_priority": dict(Counter(item.get("priority", "unknown") for item in items)),
        "by_status": dict(Counter(item.get("status", "unknown") for item in items)),
    }


def summarize_official_source_review(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "by_status": dict(Counter(item.get("status", "unknown") for item in items)),
        "by_review_decision": dict(Counter(item.get("review_decision", "unknown") for item in items)),
        "required_evidence_counts": dict(
            Counter(field for item in items for field in item.get("required_evidence", []))
        ),
    }


def summarize_roadview_image_review(items: list[dict[str, Any]]) -> dict[str, Any]:
    image_counts = [item.get("image_count", 0) for item in items]
    return {
        "total": len(items),
        "by_status": dict(Counter(item.get("status", "unknown") for item in items)),
        "by_review_decision": dict(Counter(item.get("review_decision", "unknown") for item in items)),
        "total_roadview_images": sum(image_counts),
        "min_images_per_place": min(image_counts) if image_counts else 0,
        "max_images_per_place": max(image_counts) if image_counts else 0,
        "required_evidence_counts": dict(
            Counter(field for item in items for field in item.get("required_evidence", []))
        ),
    }


def summarize_roadview_image_asset_manifest(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_places": len(items),
        "total_place_images": sum(item.get("total_place_image_count", 0) for item in items),
        "expected_review_sample_images": sum(item.get("expected_review_sample_count", 0) for item in items),
        "available_review_sample_images": sum(item.get("available_review_sample_count", 0) for item in items),
        "missing_review_sample_images": sum(item.get("missing_review_sample_count", 0) for item in items),
        "by_status": dict(Counter(item.get("status", "unknown") for item in items)),
        "by_review_decision": dict(Counter(item.get("review_decision", "unknown") for item in items)),
    }


def summarize_roadview_image_acquisition_request(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_places": len(items),
        "total_requested_images": sum(item.get("image_count", 0) for item in items),
        "priority_sample_images": sum(item.get("priority_sample_count", 0) for item in items),
        "supplemental_images": sum(item.get("supplemental_image_count", 0) for item in items),
        "min_images_per_place": min((item.get("image_count", 0) for item in items), default=0),
        "max_images_per_place": max((item.get("image_count", 0) for item in items), default=0),
        "by_region": dict(Counter(item.get("card", {}).get("region", "unknown") for item in items)),
        "by_category": dict(Counter(item.get("card", {}).get("category", "unknown") for item in items)),
    }


def summarize_roadview_image_receipt_report(
    items: list[dict[str, Any]],
    received_files: list[dict[str, Any]],
    unexpected_files: list[dict[str, Any]],
    duplicate_file_name_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "total_places": len(items),
        "expected_images": sum(item.get("expected_image_count", 0) for item in items),
        "received_requested_images": sum(item.get("received_image_count", 0) for item in items),
        "missing_requested_images": sum(item.get("missing_image_count", 0) for item in items),
        "expected_priority_sample_images": sum(item.get("priority_sample_count", 0) for item in items),
        "received_priority_sample_images": sum(item.get("received_priority_sample_count", 0) for item in items),
        "missing_priority_sample_images": sum(item.get("missing_priority_sample_count", 0) for item in items),
        "duplicate_requested_image_names": sum(item.get("duplicate_name_count", 0) for item in items),
        "received_file_count": len(received_files),
        "unexpected_file_count": len(unexpected_files),
        "duplicate_file_name_group_count": len(duplicate_file_name_groups),
        "by_status": dict(Counter(item.get("status", "unknown") for item in items)),
        "by_receipt_decision": dict(Counter(item.get("receipt_decision", "unknown") for item in items)),
    }


def summarize_roadview_visual_review_sheet(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_places": len(items),
        "by_status": dict(Counter(item.get("status", "unknown") for item in items)),
        "by_review_decision": dict(Counter(item.get("review_decision", "unknown") for item in items)),
        "total_field_results": sum(len(item.get("field_results", [])) for item in items),
        "by_field_status": dict(
            Counter(result.get("status", "unknown") for item in items for result in item.get("field_results", []))
        ),
    }


def summarize_visual_review_apply_report(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "by_action": dict(Counter(item.get("action", "unknown") for item in items)),
        "by_new_status": dict(Counter(item.get("new_status", "unknown") for item in items)),
        "by_new_review_decision": dict(
            Counter(item.get("new_review_decision", "unknown") for item in items)
        ),
    }


def summarize_crowd_policy_review(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "by_status": dict(Counter(item.get("status", "unknown") for item in items)),
        "by_review_decision": dict(Counter(item.get("review_decision", "unknown") for item in items)),
        "by_category": dict(Counter(item.get("card", {}).get("category", "unknown") for item in items)),
        "operating_calendar_check_required": sum(
            1 for item in items if item.get("policy", {}).get("operating_calendar_check_required") is True
        ),
    }


def summarize_category_refinement_review(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "by_status": dict(Counter(item.get("status", "unknown") for item in items)),
        "by_review_decision": dict(Counter(item.get("review_decision", "unknown") for item in items)),
        "by_recommended_category": dict(Counter(item.get("recommended_category", "unknown") for item in items)),
    }


def summarize_promotion_readiness(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "ready_count": sum(
            1 for item in items if item.get("promotion_decision") == "ready_for_active_candidate"
        ),
        "blocked_count": sum(
            1 for item in items if item.get("promotion_decision") != "ready_for_active_candidate"
        ),
        "by_promotion_decision": dict(
            Counter(item.get("promotion_decision", "unknown") for item in items)
        ),
        "blocking_gate_counts": dict(
            Counter(gate for item in items for gate in item.get("blocking_gates", []))
        ),
    }


def summarize_active_candidate_report(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "promoted_count": sum(1 for item in items if item.get("action") == "promoted"),
        "blocked_count": sum(1 for item in items if item.get("action") != "promoted"),
        "by_action": dict(Counter(item.get("action", "unknown") for item in items)),
        "blocking_gate_counts": dict(
            Counter(gate for item in items for gate in item.get("blocking_gates", []))
        ),
    }


def summarize_service_seed_gate_status(
    items: list[dict[str, Any]],
    acquisition_request: dict[str, Any],
    receipt_report: dict[str, Any],
    image_asset_manifest: dict[str, Any],
    visual_review_sheet: dict[str, Any],
    promotion_readiness: dict[str, Any],
    active_candidate_report: dict[str, Any],
) -> dict[str, Any]:
    acquisition_summary = acquisition_request.get("summary", {})
    receipt_summary = receipt_report.get("summary", {})
    asset_summary = image_asset_manifest.get("summary", {})
    visual_summary = visual_review_sheet.get("summary", {})
    promotion_summary = promotion_readiness.get("summary", {})
    active_summary = active_candidate_report.get("summary", {})
    return {
        "total_places": len(items),
        "ready_for_service_activation_count": sum(
            1 for item in items if item.get("primary_blocking_stage") == "ready_for_service_activation"
        ),
        "blocked_count": sum(
            1 for item in items if item.get("primary_blocking_stage") != "ready_for_service_activation"
        ),
        "expected_images": acquisition_summary.get("total_requested_images", receipt_summary.get("expected_images", 0)),
        "received_requested_images": receipt_summary.get("received_requested_images", 0),
        "missing_requested_images": receipt_summary.get("missing_requested_images", 0),
        "expected_priority_sample_images": receipt_summary.get(
            "expected_priority_sample_images",
            acquisition_summary.get("priority_sample_images", 0),
        ),
        "received_priority_sample_images": receipt_summary.get("received_priority_sample_images", 0),
        "missing_priority_sample_images": receipt_summary.get("missing_priority_sample_images", 0),
        "available_review_sample_images": asset_summary.get("available_review_sample_images", 0),
        "missing_review_sample_images": asset_summary.get("missing_review_sample_images", 0),
        "open_visual_review_places": visual_summary.get("by_status", {}).get("open", 0),
        "verified_roadview_places": promotion_summary.get("ready_count", 0),
        "promoted_active_candidates": active_summary.get("promoted_count", 0),
        "by_primary_blocking_stage": dict(
            Counter(item.get("primary_blocking_stage", "unknown") for item in items)
        ),
        "blocking_gate_counts": dict(
            Counter(gate for item in items for gate in item.get("blocking_gates", []))
        ),
        "next_action": service_seed_gate_recommended_action(service_seed_current_primary_stage_from_items(items)),
    }


def service_seed_pipeline_gates(
    acquisition_request: dict[str, Any],
    receipt_report: dict[str, Any],
    image_asset_manifest: dict[str, Any],
    visual_review_sheet: dict[str, Any],
    promotion_readiness: dict[str, Any],
    active_candidate_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    acquisition_summary = acquisition_request.get("summary", {})
    receipt_summary = receipt_report.get("summary", {})
    asset_summary = image_asset_manifest.get("summary", {})
    visual_summary = visual_review_sheet.get("summary", {})
    promotion_summary = promotion_readiness.get("summary", {})
    active_summary = active_candidate_report.get("summary", {})
    total_places = promotion_summary.get("total", 0)
    return {
        "image_acquisition_request_prepared": service_seed_pipeline_gate(
            "pass" if acquisition_summary.get("total_requested_images", 0) > 0 else "fail",
            "서비스 시드 이미지 요청 목록 생성 여부",
            {
                "requested_images": acquisition_summary.get("total_requested_images", 0),
                "priority_sample_images": acquisition_summary.get("priority_sample_images", 0),
            },
        ),
        "image_receipt_complete": service_seed_pipeline_gate(
            "pass"
            if receipt_summary.get("expected_images", 0) > 0
            and receipt_summary.get("missing_requested_images", 0) == 0
            and receipt_summary.get("duplicate_requested_image_names", 0) == 0
            else "fail",
            "요청 이미지 원본 수령 완료 여부",
            {
                "expected_images": receipt_summary.get("expected_images", 0),
                "received_requested_images": receipt_summary.get("received_requested_images", 0),
                "missing_requested_images": receipt_summary.get("missing_requested_images", 0),
            },
        ),
        "review_samples_available": service_seed_pipeline_gate(
            "pass"
            if asset_summary.get("expected_review_sample_images", 0) > 0
            and asset_summary.get("missing_review_sample_images", 0) == 0
            else "fail",
            "우선 시각 검수 샘플 파일 준비 여부",
            {
                "expected_review_sample_images": asset_summary.get("expected_review_sample_images", 0),
                "available_review_sample_images": asset_summary.get("available_review_sample_images", 0),
                "missing_review_sample_images": asset_summary.get("missing_review_sample_images", 0),
            },
        ),
        "visual_review_ready_or_verified": service_seed_pipeline_gate(
            "pass"
            if visual_summary.get("by_status", {}).get("open", 0) + promotion_summary.get("ready_count", 0) == total_places
            and total_places > 0
            else "fail",
            "시각 검수 입력 가능 또는 검증 완료 여부",
            {
                "open_visual_review_places": visual_summary.get("by_status", {}).get("open", 0),
                "verified_roadview_places": promotion_summary.get("ready_count", 0),
                "total_places": total_places,
            },
        ),
        "active_candidate_export_ready": service_seed_pipeline_gate(
            "pass"
            if active_summary.get("promoted_count", 0) == total_places and total_places > 0
            else "fail",
            "active 후보 산출 완료 여부",
            {
                "promoted_count": active_summary.get("promoted_count", 0),
                "blocked_count": active_summary.get("blocked_count", 0),
                "total_places": total_places,
            },
        ),
    }


def service_seed_pipeline_gate(status: str, detail: str, metrics: dict[str, int]) -> dict[str, Any]:
    return {
        "status": status,
        "detail": detail,
        "metrics": metrics,
    }


def service_seed_overall_status(summary: dict[str, Any]) -> str:
    if summary.get("total_places", 0) > 0 and summary.get("ready_for_service_activation_count", 0) == summary.get("total_places", 0):
        return "ready_for_service_activation"
    return "blocked"


def service_seed_current_primary_stage(summary: dict[str, Any]) -> str:
    return service_seed_first_blocking_stage(summary.get("by_primary_blocking_stage", {}))


def service_seed_current_primary_stage_from_items(items: list[dict[str, Any]]) -> str:
    return service_seed_first_blocking_stage(
        dict(Counter(item.get("primary_blocking_stage", "unknown") for item in items))
    )


def service_seed_first_blocking_stage(stage_counts: dict[str, int]) -> str:
    stage_order = [
        "awaiting_image_receipt",
        "resolving_duplicate_images",
        "preparing_visual_assets",
        "preparing_visual_review_sheet",
        "awaiting_visual_review",
        "resolving_visual_review_findings",
        "preparing_active_candidate_export",
        "ready_for_service_activation",
    ]
    for stage in stage_order:
        if stage_counts.get(stage, 0) > 0:
            return stage
    return "unknown"


def summarize_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(candidates),
        "by_decision": dict(Counter(candidate.get("decision", "unknown") for candidate in candidates)),
        "by_priority": dict(Counter(candidate.get("priority", "unknown") for candidate in candidates)),
        "by_category": dict(Counter(candidate.get("draft", {}).get("category", "unknown") for candidate in candidates)),
        "by_region": dict(Counter(candidate.get("draft", {}).get("region", "unknown") for candidate in candidates)),
    }


def field_states(card: dict[str, Any]) -> dict[str, str]:
    accessibility = card.get("accessibility", {})
    return {
        field: accessibility.get(field, {}).get("state", "unknown")
        for field in ACCESSIBILITY_FIELDS
    }


def fields_with_state(states: dict[str, str], state: str) -> list[str]:
    return sorted(field for field, value in states.items() if value == state)


def card_ref(card: dict[str, Any]) -> dict[str, Any]:
    verification = card.get("verification", {})
    return {
        "id": card.get("id", ""),
        "name": card.get("name", ""),
        "region": card.get("region", ""),
        "category": card.get("category", ""),
        "verification_status": verification.get("status", ""),
    }
