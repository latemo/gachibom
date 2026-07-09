"""Build operational summaries for Jeju Maeum place data."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


PUBLIC_VERIFICATION_STATUSES = {"verified", "partial"}
BLOCKED_VERIFICATION_STATUSES = {"needs_check", "unavailable"}

ACCESSIBILITY_FIELDS = {
    "wheelchair_access": "휠체어 접근",
    "accessible_toilet": "장애인 화장실",
    "parking": "주차",
    "slope_or_stairs": "경사·계단",
    "rest_area": "휴식 공간",
    "rental_or_assistance": "대여·보조",
    "surface_condition": "바닥 상태",
    "crowd_level": "혼잡도",
}

CATEGORY_POLICY = {
    "sea": "바다·해안·전망 장소. 날씨와 강풍 민감 조건에서 감점 또는 확인 필요.",
    "forest": "숲·수목원·자연휴양림. 도보 부담, 바닥 상태, 날씨 영향을 함께 확인.",
    "oreum": "오름. 경사와 장거리 보행 가능성이 커 기본 추천 전 정밀 검수 필요.",
    "culture": "문화·역사·공연 공간. 실내외 동선과 화장실 접근성 확인.",
    "indoor": "실내 전시·박물관·기념관. 회복 중·날씨 민감 조건에서 우선 후보.",
    "cafe": "카페·차·디저트 장소. 음식 제한·혼잡 민감 조건에서 감점.",
    "restaurant": "식당. 음식 제한 조건에서는 기본 제외.",
    "food_market": "시장·음식 중심 상권. 음식 제한 조건에서는 제외, 혼잡 민감 조건에서는 감점.",
    "shopping": "쇼핑 중심 장소. 혼잡 민감 조건에서 감점.",
    "rest_area": "공원·휴식 공간. 휴식 가능 여부와 야외 노출을 함께 확인.",
    "transport": "공항·터미널 등 교통 거점. 여행 보조 정보로 사용.",
    "medical_support": "병원·응급 대응 참고 지점. 추천 여행지가 아니라 지원 정보로 분리.",
    "lodging": "숙박. 접근 객실, 욕실, 주차, 엘리베이터 검수 전까지 추천 제외.",
    "event": "축제·행사. 기간, 혼잡도, 임시 동선 검수 전까지 추천 제외.",
    "experience": "체험 관광. 프로그램별 접근성 검수 후 노출.",
    "other": "기타 장소. 분류 확정 전 추천 후보에서 보수적으로 처리.",
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_place_data_operations_summary(
    places: list[dict[str, Any]],
    situation_rules: list[dict[str, Any]] | None = None,
    *,
    raw_catalog_items: list[dict[str, Any]] | None = None,
    generated_at: date | None = None,
) -> dict[str, Any]:
    """Build the current operating view of place-card data."""

    situation_rules = situation_rules or []
    status_counts = Counter(place.get("status", "unknown") for place in places)
    verification_counts = Counter(verification_status(place) for place in places)
    category_counts = Counter(place.get("category", "other") for place in places)
    public_candidates = [place for place in places if is_public_candidate(place)]
    review_only_places = [place for place in places if is_review_only(place)]
    blocked_from_default = [place for place in places if not is_public_candidate(place)]

    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "summary": {
            "total_places": len(places),
            "public_candidate_places": len(public_candidates),
            "review_only_places": len(review_only_places),
            "blocked_from_default_recommendation": len(blocked_from_default),
            "needs_check_places": verification_counts.get("needs_check", 0),
        },
        "counts": {
            "by_status": dict(sorted(status_counts.items())),
            "by_verification_status": dict(sorted(verification_counts.items())),
            "by_category": dict(sorted(category_counts.items())),
        },
        "raw_catalog": raw_catalog_summary(raw_catalog_items or []),
        "public_gate": public_gate_policy(),
        "category_policy": category_policy_summary(category_counts),
        "accessibility_field_coverage": accessibility_field_coverage(places),
        "scenario_rule_summary": scenario_rule_summary(situation_rules),
        "operating_policies": operating_policies(),
        "next_actions": next_actions(places, verification_counts),
    }


def verification_status(place: dict[str, Any]) -> str:
    verification = place.get("verification") or {}
    if not isinstance(verification, dict):
        return "needs_check"
    return str(verification.get("status") or "needs_check")


def is_public_candidate(place: dict[str, Any]) -> bool:
    return (
        place.get("status") == "active"
        and verification_status(place) in PUBLIC_VERIFICATION_STATUSES
        and bool(place.get("sources"))
        and bool(place.get("safety_notes"))
    )


def is_review_only(place: dict[str, Any]) -> bool:
    if place.get("status") != "active":
        return False
    return verification_status(place) in BLOCKED_VERIFICATION_STATUSES


def public_gate_policy() -> dict[str, Any]:
    return {
        "public_default_recommendation": [
            "status가 active",
            "verification.status가 verified 또는 partial",
            "공식 또는 준공식 출처가 1개 이상 존재",
            "방문 전 주의사항 또는 안전 메모가 존재",
            "상황별 제외 규칙에 걸리지 않음",
        ],
        "review_only": [
            "verification.status가 needs_check 또는 unavailable",
            "필수 접근성 필드가 비어 있음",
            "장소 분류가 other 또는 신규 분류로 아직 확정되지 않음",
            "로드뷰·이미지 근거가 사람 검수 전 상태",
        ],
        "never_default_recommendation": [
            "status가 hidden, blocked, deprecated",
            "사용자 회피 조건과 장소 주의사항이 강하게 충돌",
            "음식 제한 조건에서 restaurant 또는 food_market",
            "의료적 효과를 이유로 추천해야만 하는 요청",
        ],
    }


def raw_catalog_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(item.get("status", "unknown") for item in items)
    category_counts = Counter(item.get("category", "other") for item in items)
    match_counts = Counter(item.get("matching", {}).get("match_status", "unmatched") for item in items)
    return {
        "total_items": len(items),
        "matched_items": match_counts.get("matched", 0),
        "candidate_match_items": match_counts.get("candidate", 0) + match_counts.get("manual_review", 0),
        "unmatched_items": match_counts.get("unmatched", 0),
        "by_status": dict(sorted(status_counts.items())),
        "by_category": dict(sorted(category_counts.items())),
        "by_match_status": dict(sorted(match_counts.items())),
        "policy": [
            "원본 카탈로그에 있다는 사실만으로 접근성 추천 대상이 되지 않음",
            "matched 항목은 접근성 카드 근거와 연결 가능",
            "candidate 또는 manual_review 항목은 이름·지역 유사도 기반 검수 필요",
            "unmatched 항목은 접근성 카드 생성 또는 외부 접근성 출처 보강 전까지 기본 추천 제외",
        ],
    }


def category_policy_summary(category_counts: Counter[str]) -> list[dict[str, Any]]:
    categories = sorted(set(CATEGORY_POLICY) | set(category_counts))
    return [
        {
            "category": category,
            "current_count": category_counts.get(category, 0),
            "policy": CATEGORY_POLICY.get(category, CATEGORY_POLICY["other"]),
        }
        for category in categories
    ]


def accessibility_field_coverage(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage = []
    total = len(places)
    for field, label in ACCESSIBILITY_FIELDS.items():
        states = Counter()
        missing = 0
        for place in places:
            accessibility = place.get("accessibility") or {}
            value = accessibility.get(field) if isinstance(accessibility, dict) else None
            if isinstance(value, dict):
                states[str(value.get("state") or "unknown")] += 1
            else:
                missing += 1
        usable = states.get("yes", 0) + states.get("partial", 0)
        coverage.append(
            {
                "field": field,
                "label": label,
                "total_places": total,
                "usable_count": usable,
                "missing_count": missing,
                "state_counts": dict(sorted(states.items())),
            }
        )
    return coverage


def scenario_rule_summary(situation_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(rule.get("id") or ""),
            "description": str(rule.get("description") or ""),
            "trigger_terms_count": len(rule.get("trigger_terms") or []),
            "exclude_categories": list(rule.get("exclude_categories") or []),
            "penalize_categories": list(rule.get("penalize_categories") or []),
            "check_before_visit": list(rule.get("check_before_visit") or []),
        }
        for rule in situation_rules
    ]


def operating_policies() -> dict[str, Any]:
    return {
        "status": {
            "active": "추천 후보로 계산할 수 있는 장소. 단, 상황별 제외 규칙과 검증 상태를 다시 적용.",
            "hidden": "내부 보존용. 사용자 추천 결과에는 노출하지 않음.",
            "blocked": "운영상 부적합 또는 오류가 있어 노출 금지.",
            "deprecated": "폐업·이전·대체 등으로 더 이상 주 추천 데이터로 사용하지 않음.",
        },
        "verification": {
            "verified": "출처와 핵심 접근성 필드가 충분해 기본 추천 후보로 사용 가능.",
            "partial": "추천 후보로 사용 가능하지만 화면에 확인 필요 문구와 근거를 함께 표시.",
            "needs_check": "기본 추천에서 제외하고 검수 큐로 보냄.",
            "unavailable": "접근성 판단 정보가 거의 없어 추천 제외.",
        },
        "service_expansion": {
            "raw_catalog": "제주 전체 관광지·식당·카페·숙박·행사 원본 목록.",
            "accessibility_cards": "추천 점수 계산에 쓰는 접근성 검증 카드.",
            "matching_layer": "원본 장소와 접근성 카드를 연결하는 검수 레이어.",
            "manual_review": "AI 초안 이후 사람이 실제 노출 여부와 근거 이미지를 판정하는 단계.",
        },
    }


def next_actions(places: list[dict[str, Any]], verification_counts: Counter[str]) -> list[str]:
    actions = []
    needs_check = verification_counts.get("needs_check", 0)
    if needs_check:
        actions.append(f"needs_check 장소 {needs_check}곳은 기본 추천에서 보류하고 출처·접근성 필드를 보강")

    missing_required_fields = [
        item
        for item in accessibility_field_coverage(places)
        if item["missing_count"] > 0 or item["state_counts"].get("unknown", 0) > 0
    ]
    if missing_required_fields:
        labels = ", ".join(item["label"] for item in missing_required_fields[:4])
        actions.append(f"접근성 필드 정보 부족 항목 보강: {labels}")

    categories = Counter(place.get("category", "other") for place in places)
    if categories.get("restaurant", 0) < 20:
        actions.append("식당·카페·시장 데이터는 전체 카탈로그로 확대하되 음식 제한 조건에서는 제외·감점 규칙 유지")
    if categories.get("lodging", 0) == 0:
        actions.append("숙박 데이터는 별도 검수 기준을 만든 뒤 raw catalog부터 수집")

    actions.append("로드뷰 이미지와 공개 API 근거를 접근성 카드의 source_ref와 검수 화면에 연결")
    return actions
