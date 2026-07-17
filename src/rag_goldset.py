"""Build a review-first draft gold set for Jeju accessibility RAG evaluation.

The generated document is deliberately not a final gold set.  Relevance labels
remain empty until two human reviewers and an adjudicator complete them.
"""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Any, Iterable


SEGMENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "wheelchair",
        "label": "휠체어 접근성",
        "required_accessibility_fields": ["wheelchair_access", "accessible_toilet", "parking"],
        "required_evidence_fields": ["wheelchair_access", "accessible_toilet", "parking", "slope_or_stairs", "surface_condition"],
        "required_check_before_visit_terms": ["경사", "바닥", "주차"],
        "must_exclude_categories": [],
        "allow_no_result": False,
        "questions": (
            "휠체어를 이용하고 긴 경사로를 피해야 해요. 제주에서 이동 부담이 낮은 코스를 추천해 주세요.",
            "전동휠체어를 쓰며 장애인 화장실과 주차가 확인된 장소를 찾고 있어요.",
            "계단 없이 들어갈 수 있고 실내에서 쉴 수 있는 제주 장소를 추천해 주세요.",
            "휠체어 사용자와 보호자가 함께 갈 수 있는 짧은 반나절 코스를 알려 주세요.",
            "바닥이 고르지 않은 길을 피하고 휠체어 접근 근거가 있는 장소만 추천해 주세요.",
            "비가 와도 휠체어로 이용하기 쉬운 실내 장소를 우선해 주세요.",
            "장애인 화장실 여부가 확인되지 않은 장소는 빼고 추천해 주세요.",
            "휠체어 대여 또는 이동 보조 정보를 확인할 수 있는 장소가 있나요?",
            "주차장에서 입구까지 이동 부담이 적은 제주 문화시설을 찾고 있어요.",
            "휠체어 접근 정보가 부족하면 추천하지 말고 확인 필요라고 알려 주세요.",
        ),
    },
    {
        "id": "stroller",
        "label": "아이·유모차",
        "required_accessibility_fields": ["slope_or_stairs", "surface_condition", "rest_area"],
        "required_evidence_fields": ["slope_or_stairs", "surface_condition", "rest_area", "parking"],
        "required_check_before_visit_terms": ["경사", "바닥", "휴식"],
        "must_exclude_categories": [],
        "allow_no_result": False,
        "questions": (
            "유모차를 쓰는 아이와 계단이 적은 제주 코스를 추천해 주세요.",
            "아이와 자주 쉬어야 해서 휴식 공간이 확인된 장소를 찾고 있어요.",
            "유모차 바퀴가 작은 편이라 비포장길을 피한 코스를 알려 주세요.",
            "아이 동반 가족이 비 오는 날 갈 수 있는 실내 장소를 추천해 주세요.",
            "주차 후 유모차로 짧게 이동할 수 있는 곳을 우선해 주세요.",
            "낮잠 시간이 있어 두 곳 정도만 짧게 둘러보는 코스를 원해요.",
            "유모차 접근과 화장실 정보를 같이 확인할 수 있는 장소가 있나요?",
            "강풍이 불 때 아이와 오래 밖에 있지 않는 코스를 추천해 주세요.",
            "계단이나 급경사가 확인되면 제외하고 아이와 갈 곳을 골라 주세요.",
            "유모차 정보가 불확실하면 단정하지 말고 방문 전 확인사항을 알려 주세요.",
        ),
    },
    {
        "id": "recovery",
        "label": "체력 저하·회복 여행",
        "required_accessibility_fields": ["rest_area"],
        "required_evidence_fields": ["rest_area", "crowd_level", "surface_condition"],
        "required_check_before_visit_terms": ["휴식", "혼잡", "도보"],
        "must_exclude_categories": [],
        "allow_no_result": False,
        "questions": (
            "수술 후 회복 중이라 오래 걷지 않는 조용한 제주 코스를 추천해 주세요.",
            "체력이 약해서 중간에 앉아 쉴 곳이 많은 장소를 찾고 있어요.",
            "붐비는 시장과 긴 야외 이동을 피한 반나절 코스를 알려 주세요.",
            "보호자와 함께 천천히 이동할 수 있는 실내 중심 코스를 추천해 주세요.",
            "한 장소에서 오래 머물 수 있고 휴식 공간이 확인된 곳을 골라 주세요.",
            "식사 장소를 제외하고 조용히 둘러볼 수 있는 두세 곳을 추천해 주세요.",
            "더위에 약하고 체력이 낮아 냉방 가능한 장소를 우선해 주세요.",
            "도보 부담이 낮다는 근거가 있는 장소만 추천해 주세요.",
            "혼잡 정보가 불확실하면 방문 전 확인하도록 안내해 주세요.",
            "회복 여행에 맞는 장소가 없으면 유명 관광지를 억지로 추천하지 마세요.",
        ),
    },
    {
        "id": "diet",
        "label": "음식·시설 제한",
        "required_accessibility_fields": ["rest_area"],
        "required_evidence_fields": ["rest_area", "accessible_toilet"],
        "required_check_before_visit_terms": ["식사", "운영"],
        "must_exclude_categories": ["restaurant", "food_market"],
        "allow_no_result": False,
        "questions": (
            "음식 제한이 있어 식당과 시장을 빼고 제주 코스를 추천해 주세요.",
            "알레르기가 있어 먹거리 체험 없이 둘러볼 수 있는 장소를 찾고 있어요.",
            "카페나 맛집 대신 문화시설과 휴식 장소를 우선해 주세요.",
            "식사 시간이 짧아 관광지만 두세 곳 묶은 코스를 추천해 주세요.",
            "시장처럼 냄새와 혼잡이 큰 장소를 제외한 코스를 알려 주세요.",
            "음식 섭취가 어려운 동행자와 갈 수 있는 실내 장소를 추천해 주세요.",
            "추천 이유에 식당을 제외했다는 점과 휴식 가능 여부를 설명해 주세요.",
            "운영 중인 비식음 장소가 없으면 결과가 부족하다고 알려 주세요.",
        ),
    },
    {
        "id": "weather",
        "label": "날씨·야외 활동",
        "required_accessibility_fields": ["rest_area"],
        "required_evidence_fields": ["weather_sensitivity", "rest_area", "surface_condition"],
        "required_check_before_visit_terms": ["날씨", "강풍", "바닥"],
        "must_exclude_categories": ["oreum", "sea"],
        "allow_no_result": False,
        "questions": (
            "비와 강풍을 피할 수 있는 제주 실내 코스를 추천해 주세요.",
            "더위에 민감해서 야외 체류가 짧은 장소를 우선해 주세요.",
            "비가 오면 미끄러운 길과 해변을 제외한 코스를 알려 주세요.",
            "강풍 예보가 있어 오름과 바다를 빼고 추천해 주세요.",
            "날씨가 바뀌어도 대피하기 쉬운 장소를 찾고 있어요.",
            "그늘과 휴식 공간 정보가 확인된 장소를 추천해 주세요.",
            "날씨 민감도가 높은 장소는 감점했다는 이유를 보여 주세요.",
            "실내 장소가 부족하면 야외 장소를 안전하다고 단정하지 마세요.",
        ),
    },
    {
        "id": "conflict",
        "label": "복수·충돌 조건",
        "required_accessibility_fields": ["wheelchair_access", "rest_area"],
        "required_evidence_fields": ["wheelchair_access", "rest_area", "slope_or_stairs", "weather_sensitivity"],
        "required_check_before_visit_terms": ["우선순위", "확인"],
        "must_exclude_categories": [],
        "allow_no_result": True,
        "questions": (
            "바다를 보고 싶지만 휠체어 경사와 강풍은 피해야 해요. 가능한 조건만 설명해 주세요.",
            "오름을 원하지만 계단을 이용할 수 없어요. 맞는 곳이 없으면 없다고 알려 주세요.",
            "아이와 야외에 가고 싶지만 비가 오고 오래 걸을 수 없어요.",
            "맛집은 제외하고 싶지만 동행자는 시장을 원해요. 안전 조건을 우선해 주세요.",
            "휠체어 접근, 실내, 바다 전망을 모두 원합니다. 충족하지 못한 조건도 알려 주세요.",
            "주차와 화장실이 필수지만 검증된 장소가 없으면 추천을 보류해 주세요.",
        ),
    },
    {
        "id": "ambiguous",
        "label": "오타·모호한 질문",
        "required_accessibility_fields": [],
        "required_evidence_fields": ["verification_status"],
        "required_check_before_visit_terms": ["조건 확인"],
        "must_exclude_categories": [],
        "allow_no_result": True,
        "questions": (
            "휠체어로 편한데 추천해줘",
            "유모차 가능하고 안힘든 제주곳",
            "비오고 몸 안좋음 어디감",
            "접근성 좋은 곳 아무데나 말고 근거 있는 곳",
        ),
    },
    {
        "id": "no_result",
        "label": "적합 장소 없음",
        "required_accessibility_fields": ["wheelchair_access", "accessible_toilet", "parking", "rest_area"],
        "required_evidence_fields": ["verification_status", "wheelchair_access", "accessible_toilet", "parking", "rest_area"],
        "required_check_before_visit_terms": ["결과 없음", "확인 필요"],
        "must_exclude_categories": [],
        "allow_no_result": True,
        "questions": (
            "모든 접근성 항목이 verified이고 24시간 운영하는 해변만 추천해 주세요.",
            "계단이 전혀 없고 경사도 없으며 모든 시설이 확정된 오름을 찾아 주세요.",
            "검증되지 않은 정보가 하나도 없는 야간 시장 코스만 알려 주세요.",
            "제 조건을 전부 충족하는 장소가 없으면 빈 결과와 부족한 근거를 알려 주세요.",
        ),
    },
)


def build_draft_goldset(*, generated_at: date) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    global_index = 0
    for segment in SEGMENTS:
        for segment_index, question in enumerate(segment["questions"], start=1):
            global_index += 1
            cases.append(
                {
                    "id": f"{segment['id']}_{segment_index:02d}",
                    "split": "test" if global_index % 3 == 0 else "dev",
                    "segment": segment["id"],
                    "segment_label": segment["label"],
                    "question": question,
                    "expected": {
                        "relevant_place_ids": [],
                        "acceptable_place_ids": [],
                        "must_exclude_place_ids": [],
                        "must_exclude_categories": list(segment["must_exclude_categories"]),
                        "required_accessibility_fields": list(segment["required_accessibility_fields"]),
                        "required_evidence_fields": list(segment["required_evidence_fields"]),
                        "required_check_before_visit_terms": list(segment["required_check_before_visit_terms"]),
                        "allow_no_result": bool(segment["allow_no_result"]),
                    },
                    "review": {
                        "status": "pending_human_review",
                        "required_reviewers": 2,
                        "reviewer_ids": [],
                        "adjudicated_by": None,
                        "approved_at": None,
                        "notes": "",
                    },
                }
            )

    return {
        "schema_version": "1.0",
        "goldset_id": "gachibom_rag_goldset_v1",
        "generated_at": generated_at.isoformat(),
        "status": "draft_pending_human_review",
        "methodology": {
            "minimum_reviewers_per_case": 2,
            "adjudication_required_on_disagreement": True,
            "metrics_unlocked_after_review": ["recall_at_4", "grounded_claim_rate"],
            "release_gate": "hard_constraint_violation_rate must equal 0",
            "warning": "자동 생성된 질문 초안이며, 사람 승인 전에는 최종 성능 수치 산출에 사용하지 않는다.",
        },
        "summary": _summary(cases),
        "cases": cases,
    }


def _summary(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(cases)
    segment_counts: dict[str, int] = {}
    split_counts: dict[str, int] = {}
    for case in rows:
        segment_counts[case["segment"]] = segment_counts.get(case["segment"], 0) + 1
        split_counts[case["split"]] = split_counts.get(case["split"], 0) + 1
    approved = sum(1 for case in rows if case["review"]["status"] == "approved")
    return {
        "case_count": len(rows),
        "segment_counts": segment_counts,
        "split_counts": split_counts,
        "approved_case_count": approved,
        "pending_case_count": len(rows) - approved,
        "reportable": approved == len(rows) and bool(rows),
    }


def render_goldset_csv(document: dict[str, Any]) -> str:
    output = StringIO()
    fieldnames = [
        "case_id",
        "split",
        "segment",
        "segment_label",
        "question",
        "relevant_place_ids",
        "acceptable_place_ids",
        "must_exclude_place_ids",
        "must_exclude_categories",
        "required_accessibility_fields",
        "required_evidence_fields",
        "required_check_before_visit_terms",
        "allow_no_result",
        "review_status",
        "reviewer_ids",
        "adjudicated_by",
        "review_notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for case in document.get("cases", []):
        expected = case["expected"]
        review = case["review"]
        writer.writerow(
            {
                "case_id": case["id"],
                "split": case["split"],
                "segment": case["segment"],
                "segment_label": case["segment_label"],
                "question": case["question"],
                "relevant_place_ids": ";".join(expected["relevant_place_ids"]),
                "acceptable_place_ids": ";".join(expected["acceptable_place_ids"]),
                "must_exclude_place_ids": ";".join(expected["must_exclude_place_ids"]),
                "must_exclude_categories": ";".join(expected["must_exclude_categories"]),
                "required_accessibility_fields": ";".join(expected["required_accessibility_fields"]),
                "required_evidence_fields": ";".join(expected["required_evidence_fields"]),
                "required_check_before_visit_terms": ";".join(expected["required_check_before_visit_terms"]),
                "allow_no_result": str(expected["allow_no_result"]).lower(),
                "review_status": review["status"],
                "reviewer_ids": ";".join(review["reviewer_ids"]),
                "adjudicated_by": review["adjudicated_by"] or "",
                "review_notes": review["notes"],
            }
        )
    return output.getvalue()
