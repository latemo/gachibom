"""Verify recovery status for roadview images that previously returned provider 404."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from src.roadview_new_candidates import ROADVIEW_IMAGE_FILE_EXTENSIONS, normalize_image_key, sha256_file


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_roadview_missing_image_recovery_report(
    provider_404_report: dict[str, Any],
    *,
    receipt_root: str | Path = "data/raw/roadview_images",
    generated_at: date | None = None,
    hash_files: bool = True,
) -> dict[str, Any]:
    root = Path(receipt_root)
    file_index = roadview_image_file_index(root)
    items = [
        recovery_item(item, file_index, root, hash_files=hash_files)
        for item in provider_404_report.get("items", [])
    ]
    place_statuses = summarize_recovery_places(items)
    summary = summarize_recovery_items(items, place_statuses)
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_provider_404_report_generated_at": provider_404_report.get("generated_at"),
        "receipt_root": str(root).replace("\\", "/"),
        "hash_algorithm": "sha256" if hash_files else None,
        "criteria": {
            "complete_recovery": "제공기관 404 누락 목록의 모든 파일명이 receipt_root 아래에 존재하고 중복 파일명이 없음",
            "partial_recovery": "누락 목록 중 일부 파일만 receipt_root 아래에서 확인됨",
            "awaiting_recovery": "누락 목록 파일이 아직 receipt_root 아래에서 확인되지 않음",
            "needs_duplicate_resolution": "같은 이미지 파일명 후보가 여러 개 있어 어떤 파일을 정본으로 쓸지 정리 필요",
        },
        "overall_status": overall_recovery_status(summary),
        "summary": summary,
        "place_statuses": place_statuses,
        "items": items,
        "next_actions": recovery_next_actions(summary),
    }


def roadview_image_file_index(receipt_root: Path) -> dict[str, list[dict[str, Any]]]:
    if not receipt_root.exists():
        return {}
    index: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(receipt_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ROADVIEW_IMAGE_FILE_EXTENSIONS:
            continue
        key = normalize_image_key(path.name)
        index.setdefault(key, []).append(
            {
                "file_name": path.name,
                "relative_path": str(path.relative_to(receipt_root)).replace("\\", "/"),
                "file_size_bytes": path.stat().st_size,
                "_path": path,
            }
        )
    return index


def recovery_item(
    provider_item: dict[str, Any],
    file_index: dict[str, list[dict[str, Any]]],
    receipt_root: Path,
    *,
    hash_files: bool,
) -> dict[str, Any]:
    image_name = provider_item.get("image_file_name", "")
    matches = file_index.get(normalize_image_key(image_name), [])
    selected = matches[0] if matches else {}
    status = "missing"
    if len(matches) == 1:
        status = "recovered"
    elif len(matches) > 1:
        status = "duplicate_name"

    return {
        "card_id": provider_item.get("card_id", ""),
        "place_name": provider_item.get("place_name", ""),
        "image_file_name": image_name,
        "request_tier": provider_item.get("request_tier", ""),
        "tourist_name": provider_item.get("tourist_name", ""),
        "tourist_name_en": provider_item.get("tourist_name_en", ""),
        "captured_at": provider_item.get("captured_at"),
        "source_url": provider_item.get("source_url", ""),
        "status": status,
        "present_path": selected.get("relative_path"),
        "file_size_bytes": selected.get("file_size_bytes"),
        "sha256": selected_sha256(selected, hash_files=hash_files),
        "duplicate_candidate_paths": [match["relative_path"] for match in matches],
        "recommended_action": recovery_item_recommended_action(status, receipt_root),
    }


def selected_sha256(selected: dict[str, Any], *, hash_files: bool) -> str | None:
    path = selected.get("_path")
    if not hash_files or not path:
        return None
    return sha256_file(path)


def recovery_item_recommended_action(status: str, receipt_root: Path) -> str:
    if status == "recovered":
        return "수령 확인 완료. 전체 수령 리포트와 서비스 게이트를 재생성"
    if status == "duplicate_name":
        return "동일 파일명 후보 중 정본 1개만 남기고 중복 파일을 분리"
    return f"{receipt_root.as_posix()} 아래에 요청 파일명과 같은 이미지 원본 배치"


def summarize_recovery_places(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item.get("place_name", "")].append(item)

    place_statuses = []
    for place_name, place_items in sorted(grouped.items()):
        recovered_count = sum(1 for item in place_items if item["status"] == "recovered")
        duplicate_count = sum(1 for item in place_items if item["status"] == "duplicate_name")
        missing_items = [item for item in place_items if item["status"] == "missing"]
        if duplicate_count:
            status = "needs_duplicate_resolution"
        elif not missing_items:
            status = "complete_recovery"
        elif recovered_count:
            status = "partial_recovery"
        else:
            status = "awaiting_recovery"
        place_statuses.append(
            {
                "place_name": place_name,
                "expected_missing_image_count": len(place_items),
                "recovered_image_count": recovered_count,
                "still_missing_image_count": len(missing_items),
                "duplicate_name_count": duplicate_count,
                "status": status,
                "sample_missing_image_file_names": [item["image_file_name"] for item in missing_items[:8]],
            }
        )
    return place_statuses


def summarize_recovery_items(
    items: list[dict[str, Any]],
    place_statuses: list[dict[str, Any]],
) -> dict[str, Any]:
    by_status = Counter(item["status"] for item in items)
    place_by_status = Counter(place["status"] for place in place_statuses)
    return {
        "expected_recovery_images": len(items),
        "recovered_images": by_status.get("recovered", 0),
        "still_missing_images": by_status.get("missing", 0),
        "duplicate_name_images": by_status.get("duplicate_name", 0),
        "affected_places": len(place_statuses),
        "recovered_places": place_by_status.get("complete_recovery", 0),
        "partial_recovery_places": place_by_status.get("partial_recovery", 0),
        "still_missing_places": sum(
            count
            for status, count in place_by_status.items()
            if status in {"awaiting_recovery", "partial_recovery", "needs_duplicate_resolution"}
        ),
        "by_status": dict(sorted(by_status.items())),
        "by_place_status": dict(sorted(place_by_status.items())),
        "next_action": recovery_next_actions_from_counts(
            by_status.get("missing", 0),
            by_status.get("duplicate_name", 0),
        )[0],
    }


def overall_recovery_status(summary: dict[str, Any]) -> str:
    if summary.get("duplicate_name_images", 0):
        return "needs_duplicate_resolution"
    if summary.get("still_missing_images", 0) == 0:
        return "complete_recovery"
    if summary.get("recovered_images", 0):
        return "partial_recovery"
    return "awaiting_recovery"


def recovery_next_actions(summary: dict[str, Any]) -> list[str]:
    return recovery_next_actions_from_counts(
        int(summary.get("still_missing_images", 0)),
        int(summary.get("duplicate_name_images", 0)),
    )


def recovery_next_actions_from_counts(still_missing: int, duplicates: int) -> list[str]:
    if duplicates:
        return [
            "중복 파일명을 정리한 뒤 누락 이미지 회복 리포트를 재생성",
            "정본 1개만 data/raw/roadview_images에 남기고 나머지는 별도 보관",
        ]
    if still_missing:
        return [
            f"아직 확인되지 않은 누락 원본 {still_missing}장을 제공기관에 재요청 또는 대체 원본으로 수령",
            "수령 파일명은 요청 CSV의 image_file_name과 동일하게 맞춰 data/raw/roadview_images에 배치",
            "배치 후 누락 이미지 회복 리포트와 전체 수령 리포트를 재생성",
        ]
    return [
        "누락 이미지 회복 완료. 전체 수령 리포트, 자산 매니페스트, 서비스 게이트를 순서대로 재생성",
        "시각 검수 공유 HTML에서 17개 장소 판정을 진행",
    ]


def render_roadview_missing_image_recovery_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 로드뷰 누락 원본 이미지 회복 검증 리포트",
        "",
        f"- 기준일: {report['generated_at']}",
        f"- 현재 상태: {recovery_status_label(report['overall_status'])}",
        f"- 회복 대상: {summary['expected_recovery_images']}장",
        f"- 회복 확인: {summary['recovered_images']}장",
        f"- 아직 누락: {summary['still_missing_images']}장",
        f"- 영향 장소: {summary['affected_places']}곳",
        "",
        "## 다음 실행",
        "",
    ]
    lines.extend([f"- {action}" for action in report.get("next_actions", [])])
    lines.extend(["", "## 장소별 상태", ""])
    for place in report.get("place_statuses", []):
        missing_samples = ", ".join(place.get("sample_missing_image_file_names", [])[:5])
        suffix = f" / 예시: {missing_samples}" if missing_samples else ""
        lines.append(
            "- "
            f"{place['place_name']}: {recovery_status_label(place['status'])}, "
            f"회복 {place['recovered_image_count']}/{place['expected_missing_image_count']}장, "
            f"남은 누락 {place['still_missing_image_count']}장"
            f"{suffix}"
        )
    lines.extend(
        [
            "",
            "## 재생성 순서",
            "",
            "1. 누락 파일을 `data/raw/roadview_images/`에 배치",
            "2. `scripts/build_roadview_missing_image_recovery_report.py` 실행",
            "3. 회복 완료 후 `scripts/build_roadview_image_receipt_report.py` 실행",
            "4. 자산 매니페스트, 시각 검수 시트, 서비스 게이트, 서비스 런칭 실행 계획 순서로 재생성",
            "",
        ]
    )
    return "\n".join(lines)


def recovery_status_label(status: str) -> str:
    labels = {
        "complete_recovery": "회복 완료",
        "partial_recovery": "일부 회복",
        "awaiting_recovery": "수령 대기",
        "needs_duplicate_resolution": "중복 정리 필요",
        "recovered": "회복 확인",
        "missing": "아직 누락",
        "duplicate_name": "중복 파일명",
    }
    return labels.get(status, status)
