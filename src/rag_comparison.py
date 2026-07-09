"""Build structured RAG vs non-RAG comparison data."""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Any


NOT_MEASURED = "미측정"
BASELINE_STATUS = "미실행_기준선"


def build_rag_comparison_report(
    case_validation_report: dict[str, Any],
    tourism_weak_courses: dict[str, Any] | None = None,
    no_rag_validation_report: dict[str, Any] | None = None,
    *,
    generated_at: date,
) -> dict[str, Any]:
    cases = case_validation_report.get("cases", [])
    summary = case_validation_report.get("summary", {})
    total_cases = int(summary.get("total_cases") or len(cases))
    passed_cases = int(summary.get("passed_cases") or sum(1 for case in cases if case.get("status") == "통과"))
    failed_cases = int(summary.get("failed_cases") or max(0, total_cases - passed_cases))
    total_checks = sum(int(case.get("validation", {}).get("total_checks") or 0) for case in cases)
    passed_checks = sum(int(case.get("validation", {}).get("passed_checks") or 0) for case in cases)
    failed_checks = sum(int(case.get("validation", {}).get("failed_checks") or 0) for case in cases)
    course_summary = (tourism_weak_courses or {}).get("summary", {})
    no_rag_summary = (no_rag_validation_report or {}).get("summary", {})
    no_rag_cases = {
        case.get("id"): case
        for case in (no_rag_validation_report or {}).get("cases", [])
    }
    no_rag_observed_cases = int(no_rag_summary.get("total_cases") or 0)

    report = {
        "generated_at": generated_at.isoformat(),
        "scope": {
            "title": "RAG 사용/미사용 추천 검증 비교",
            "with_rag_definition": (
                "장소 카드, 상황별 정책, 공식 추천코스, 출처/검수 상태를 검색·조립해 "
                "추천과 설명의 근거로 사용하는 현재 서비스 방식"
            ),
            "without_rag_definition": (
                "동일 질문에 대해 근거 저장소 검색 없이 일반 모델 지식 또는 프롬프트만 사용하는 기준선"
            ),
            "measurement_note": (
                measurement_note(no_rag_validation_report)
            ),
        },
        "sources": {
            "case_validation_report": "data/recommendation_case_validation_report.json",
            "no_rag_baseline_validation_report": "data/no_rag_baseline_validation_report.json",
            "no_rag_baseline_responses": "data/no_rag_baseline_responses.json",
            "tourism_weak_courses": "data/tourism_weak_recommendation_courses.json",
            "recommendation_policy": "src/recommendation_case_validation.py",
            "runtime_service": "src/recommendation_service.py",
        },
        "summary": {
            "scenario_cases": total_cases,
            "with_rag_passed_cases": passed_cases,
            "with_rag_failed_cases": failed_cases,
            "with_rag_case_pass_rate": ratio(passed_cases, total_cases),
            "with_rag_total_checks": total_checks,
            "with_rag_passed_checks": passed_checks,
            "with_rag_failed_checks": failed_checks,
            "with_rag_check_pass_rate": ratio(passed_checks, total_checks),
            "without_rag_observed_cases": no_rag_observed_cases,
            "without_rag_passed_cases": no_rag_summary.get("passed_cases"),
            "without_rag_failed_cases": no_rag_summary.get("failed_cases"),
            "without_rag_case_pass_rate": ratio(no_rag_summary.get("passed_cases"), no_rag_summary.get("total_cases")),
            "without_rag_total_checks": no_rag_summary.get("total_checks"),
            "without_rag_passed_checks": no_rag_summary.get("passed_checks"),
            "without_rag_failed_checks": no_rag_summary.get("failed_checks"),
            "without_rag_check_pass_rate": no_rag_summary.get("check_pass_rate"),
            "without_rag_status": (
                (no_rag_validation_report or {}).get("method", {}).get("status")
                if no_rag_validation_report
                else BASELINE_STATUS
            ),
            "official_course_slots": {
                "courses": course_summary.get("courses"),
                "stops": course_summary.get("stops"),
                "matched_stops": course_summary.get("matched_stops"),
                "matched_places": course_summary.get("matched_places"),
                "unmatched_places": course_summary.get("unmatched_places"),
                "slot_match_rate": ratio(course_summary.get("matched_stops"), course_summary.get("stops")),
            },
            "key_findings": [
                f"근거 기반 현재 방식은 상황별 검증 {passed_cases}/{total_cases}건을 통과했다.",
                f"검증 체크는 {passed_checks}/{total_checks}개 통과로 집계됐다.",
                no_rag_key_finding(no_rag_summary),
                "무RAG 비교는 출처 연결, 제외 규칙, 방문 전 확인 항목의 실패 여부로 추적한다.",
            ],
        },
        "metrics": build_metrics(
            total_cases=total_cases,
            passed_cases=passed_cases,
            total_checks=total_checks,
            passed_checks=passed_checks,
            course_summary=course_summary,
            no_rag_summary=no_rag_summary,
        ),
        "cases": [build_case_comparison(case, no_rag_cases.get(case.get("id"))) for case in cases],
    }
    return report


def measurement_note(no_rag_validation_report: dict[str, Any] | None) -> str:
    if no_rag_validation_report:
        return (
            "무RAG 값은 실제 외부 모델 운영 로그가 아니라, 근거 저장소 없이 일반 제주 대표 관광지 중심으로 "
            "응답했을 때를 재현한 통제 기준선 검증 자료를 사용한다."
        )
    return (
        "현재 저장소에는 무RAG 추천 실행 로그가 없다. 따라서 무RAG 값은 성공 수치로 계산하지 않고 "
        "미실행 기준선과 검증 공백으로 데이터화한다."
    )


def no_rag_key_finding(no_rag_summary: dict[str, Any]) -> str:
    if not no_rag_summary:
        return "무RAG 기준선은 현재 구현/로그가 없어 직접 성능 수치로 비교하지 않는다."
    return (
        "무RAG 통제 기준선은 "
        f"{no_rag_summary.get('passed_cases')}/{no_rag_summary.get('total_cases')}건, "
        f"{no_rag_summary.get('passed_checks')}/{no_rag_summary.get('total_checks')}개 체크를 통과했다."
    )


def ratio(numerator: Any, denominator: Any) -> float | None:
    try:
        n_value = float(numerator)
        d_value = float(denominator)
    except (TypeError, ValueError):
        return None
    if d_value == 0:
        return None
    return round(n_value / d_value, 4)


def build_metrics(
    *,
    total_cases: int,
    passed_cases: int,
    total_checks: int,
    passed_checks: int,
    course_summary: dict[str, Any],
    no_rag_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        metric(
            "scenario_case_pass_rate",
            "상황별 추천 검증 통과율",
            ratio(passed_cases, total_cases),
            f"{passed_cases}/{total_cases} 케이스 통과",
            ratio(no_rag_summary.get("passed_cases"), no_rag_summary.get("total_cases")),
            no_rag_evidence(no_rag_summary, "cases"),
            "상황별 정책 반영 여부",
        ),
        metric(
            "validation_check_pass_rate",
            "검증 체크 통과율",
            ratio(passed_checks, total_checks),
            f"{passed_checks}/{total_checks} 체크 통과",
            no_rag_summary.get("check_pass_rate"),
            no_rag_evidence(no_rag_summary, "checks"),
            "근거 문구, 제외 정책, 방문 전 확인 항목",
        ),
        metric(
            "official_course_slot_match_rate",
            "공식 추천코스 슬롯 매칭률",
            ratio(course_summary.get("matched_stops"), course_summary.get("stops")),
            f"{course_summary.get('matched_stops')}/{course_summary.get('stops')} 슬롯 매칭",
            None,
            "근거 저장소를 사용하지 않으면 공식 코스 슬롯 대조 자체가 수행되지 않음",
            "제주관광공사 추천코스 데이터 매칭",
        ),
        metric(
            "unmatched_official_places",
            "공식 코스 미매칭 장소 수",
            course_summary.get("unmatched_places"),
            f"미매칭 {course_summary.get('unmatched_places')}건",
            None,
            "무RAG 기준선에는 장소명-내부카드 매칭 테이블이 없음",
            "공식 코스 누락 방지",
        ),
        measurement_gap_metric(no_rag_summary),
    ]


def no_rag_evidence(no_rag_summary: dict[str, Any], kind: str) -> str:
    if not no_rag_summary:
        return "무RAG 실행 결과가 없어 같은 기준의 통과율 미측정"
    if kind == "cases":
        return f"{no_rag_summary.get('passed_cases')}/{no_rag_summary.get('total_cases')} 케이스 통과"
    return f"{no_rag_summary.get('passed_checks')}/{no_rag_summary.get('total_checks')} 체크 통과"


def metric(
    metric_id: str,
    label: str,
    with_rag_value: Any,
    with_rag_evidence: str,
    without_rag_value: Any,
    without_rag_note: str,
    validation_target: str,
) -> dict[str, Any]:
    without_observed = without_rag_value is not None
    return {
        "metric_id": metric_id,
        "label": label,
        "validation_target": validation_target,
        "with_rag": {
            "observed": True,
            "value": with_rag_value,
            "status": "관측됨",
            "evidence": with_rag_evidence,
        },
        "without_rag": {
            "observed": without_observed,
            "value": without_rag_value,
            "status": "관측됨" if without_observed else NOT_MEASURED,
            "evidence": without_rag_note,
        },
        "interpretation": (
            f"{label}: 같은 평가표 기준으로 RAG/무RAG 통제 기준선을 비교한다."
            if without_observed
            else f"{label}: 현재 근거 기반 방식에서만 관측 가능하다."
        ),
    }


def measurement_gap_metric(no_rag_summary: dict[str, Any]) -> dict[str, Any]:
    observed_cases = no_rag_summary.get("total_cases") if no_rag_summary else 0
    return {
        "metric_id": "observable_no_rag_runs",
        "label": "무RAG 기준선 자료 수",
        "validation_target": "비교 데이터 신뢰도",
        "with_rag": {
            "observed": False,
            "value": None,
            "status": "해당 없음",
            "evidence": "RAG 사용 성능이 아니라 비교 실험 준비 상태 지표",
        },
        "without_rag": {
            "observed": bool(observed_cases),
            "value": observed_cases,
            "status": "통제기준선" if observed_cases else BASELINE_STATUS,
            "evidence": (
                f"무RAG 통제 기준선 {observed_cases}건 검증"
                if observed_cases
                else "현재 저장소에 무RAG 추천 실행 로그 없음"
            ),
        },
        "interpretation": "통제 기준선은 같은 평가표로 비교하되 실제 외부 모델 운영 로그와는 구분한다.",
    }


def build_case_comparison(case: dict[str, Any], no_rag_case: dict[str, Any] | None = None) -> dict[str, Any]:
    validation = case.get("validation", {})
    recommendation = case.get("recommendation", {})
    route = recommendation.get("route", [])
    expected_policy = case.get("expected_policy", {})
    excluded_categories = expected_policy.get("selected_exclude_categories", [])
    required_check_terms = expected_policy.get("required_check_terms", [])
    required_fit_terms = expected_policy.get("required_fit_terms", [])
    policy_effect_terms = expected_policy.get("policy_effect_terms", [])

    return {
        "id": case.get("id"),
        "label": case.get("label"),
        "title": case.get("title"),
        "intent": case.get("intent"),
        "with_rag": {
            "status": case.get("status"),
            "score_total": recommendation.get("score", {}).get("total"),
            "grade": recommendation.get("score", {}).get("grade"),
            "route_names": [place.get("name", "") for place in route],
            "route_categories": [place.get("category", "") for place in route],
            "total_checks": validation.get("total_checks"),
            "passed_checks": validation.get("passed_checks"),
            "failed_checks": validation.get("failed_checks"),
            "excluded_candidate_samples": len(case.get("excluded_candidates", [])),
            "deduction_samples": len(case.get("deduction_samples", [])),
        },
        "without_rag_baseline": build_without_rag_case(
            no_rag_case,
            excluded_categories=excluded_categories,
            required_check_terms=required_check_terms,
            required_fit_terms=required_fit_terms,
            policy_effect_terms=policy_effect_terms,
        ),
        "comparison": {
            "with_rag_advantage": [
                f"검증 체크 {validation.get('passed_checks')}/{validation.get('total_checks')} 통과",
                "추천 장소, 제외 후보, 감점 사유를 같은 데이터 구조로 추적",
                "방문 전 확인 항목을 상황별 정책어와 연결",
            ],
            "needs_no_rag_experiment": True,
        },
    }


def build_without_rag_case(
    no_rag_case: dict[str, Any] | None,
    *,
    excluded_categories: list[str],
    required_check_terms: list[str],
    required_fit_terms: list[str],
    policy_effect_terms: list[str],
) -> dict[str, Any]:
    failure_modes = without_rag_failure_modes(
        excluded_categories=excluded_categories,
        required_check_terms=required_check_terms,
        required_fit_terms=required_fit_terms,
        policy_effect_terms=policy_effect_terms,
    )
    validation_gap = [
        "장소별 검수 상태와 출처를 응답 근거로 대조할 수 없음",
        "정책 위반 후보가 왜 제외/감점됐는지 로그로 재현하기 어려움",
        "동일 입력 재실행 시 일반 지식 기반 설명이 바뀔 가능성이 있음",
    ]
    if not no_rag_case:
        return {
            "status": BASELINE_STATUS,
            "observed": False,
            "comparable": False,
            "expected_failure_modes": failure_modes,
            "validation_gap": validation_gap,
        }

    validation = no_rag_case.get("validation", {})
    route = no_rag_case.get("recommendation", {}).get("route", [])
    failed_checks = [
        f"{check.get('area')}:{check.get('name')}"
        for check in validation.get("checks", [])
        if check.get("status") == "실패"
    ]
    return {
        "status": no_rag_case.get("status"),
        "observed": True,
        "comparable": True,
        "prompt": no_rag_case.get("prompt", ""),
        "raw_response": no_rag_case.get("raw_response", ""),
        "route_names": [place.get("name", "") for place in route],
        "route_categories": [place.get("category", "") for place in route],
        "total_checks": validation.get("total_checks"),
        "passed_checks": validation.get("passed_checks"),
        "failed_checks": validation.get("failed_checks"),
        "failed_check_names": failed_checks,
        "expected_failure_modes": failure_modes,
        "validation_gap": validation_gap,
    }


def without_rag_failure_modes(
    *,
    excluded_categories: list[str],
    required_check_terms: list[str],
    required_fit_terms: list[str],
    policy_effect_terms: list[str],
) -> list[str]:
    modes = [
        "없는 편의시설이나 접근 가능성을 일반 지식으로 단정할 위험",
        "출처/검수 상태가 없는 설명을 근거처럼 제시할 위험",
    ]
    if excluded_categories:
        modes.append(f"제외 대상 카테고리({', '.join(excluded_categories)})를 일관되게 배제하지 못할 위험")
    if required_fit_terms:
        modes.append(f"추천 근거 필수어({', '.join(required_fit_terms)})가 누락될 위험")
    if required_check_terms:
        modes.append(f"방문 전 확인 항목({', '.join(required_check_terms)})이 누락될 위험")
    if policy_effect_terms:
        modes.append(f"감점/제외 정책 효과({', '.join(policy_effect_terms)})가 설명에 드러나지 않을 위험")
    return modes


def render_metrics_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    fieldnames = [
        "metric_id",
        "label",
        "validation_target",
        "with_rag_value",
        "with_rag_status",
        "with_rag_evidence",
        "without_rag_value",
        "without_rag_status",
        "without_rag_evidence",
        "interpretation",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for item in report.get("metrics", []):
        writer.writerow(
            {
                "metric_id": item.get("metric_id"),
                "label": item.get("label"),
                "validation_target": item.get("validation_target"),
                "with_rag_value": item.get("with_rag", {}).get("value"),
                "with_rag_status": item.get("with_rag", {}).get("status"),
                "with_rag_evidence": item.get("with_rag", {}).get("evidence"),
                "without_rag_value": item.get("without_rag", {}).get("value"),
                "without_rag_status": item.get("without_rag", {}).get("status"),
                "without_rag_evidence": item.get("without_rag", {}).get("evidence"),
                "interpretation": item.get("interpretation"),
            }
        )
    return output.getvalue()


def render_cases_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    fieldnames = [
        "case_id",
        "label",
        "with_rag_status",
        "with_rag_score",
        "with_rag_passed_checks",
        "with_rag_total_checks",
        "route_names",
        "route_categories",
        "without_rag_status",
        "without_rag_observed",
        "without_rag_passed_checks",
        "without_rag_total_checks",
        "without_rag_route_names",
        "without_rag_route_categories",
        "without_rag_failed_check_names",
        "without_rag_expected_failure_modes",
        "validation_gap",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for case in report.get("cases", []):
        with_rag = case.get("with_rag", {})
        without_rag = case.get("without_rag_baseline", {})
        writer.writerow(
            {
                "case_id": case.get("id"),
                "label": case.get("label"),
                "with_rag_status": with_rag.get("status"),
                "with_rag_score": with_rag.get("score_total"),
                "with_rag_passed_checks": with_rag.get("passed_checks"),
                "with_rag_total_checks": with_rag.get("total_checks"),
                "route_names": "; ".join(with_rag.get("route_names", [])),
                "route_categories": "; ".join(with_rag.get("route_categories", [])),
                "without_rag_status": without_rag.get("status"),
                "without_rag_observed": without_rag.get("observed"),
                "without_rag_passed_checks": without_rag.get("passed_checks"),
                "without_rag_total_checks": without_rag.get("total_checks"),
                "without_rag_route_names": "; ".join(without_rag.get("route_names", [])),
                "without_rag_route_categories": "; ".join(without_rag.get("route_categories", [])),
                "without_rag_failed_check_names": " | ".join(without_rag.get("failed_check_names", [])),
                "without_rag_expected_failure_modes": " | ".join(without_rag.get("expected_failure_modes", [])),
                "validation_gap": " | ".join(without_rag.get("validation_gap", [])),
            }
        )
    return output.getvalue()


def render_rag_comparison_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    course_slots = summary["official_course_slots"]
    lines = [
        "# RAG 사용/미사용 비교 데이터",
        "",
        f"작성일: {report['generated_at']}",
        "",
        "## 비교 범위",
        "",
        f"- RAG 사용: {report['scope']['with_rag_definition']}",
        f"- RAG 미사용: {report['scope']['without_rag_definition']}",
        f"- 주의: {report['scope']['measurement_note']}",
        "",
        "## 요약 지표",
        "",
        "| 항목 | RAG 사용 | RAG 미사용 | 해석 |",
        "| --- | --- | --- | --- |",
    ]
    for metric_item in report["metrics"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(metric_item["label"]),
                    str(metric_item["with_rag"]["evidence"]),
                    str(metric_item["without_rag"]["evidence"]),
                    str(metric_item["interpretation"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 공식 코스 데이터",
            "",
            f"- 공식 코스: {course_slots.get('courses')}개",
            f"- 코스 슬롯: {course_slots.get('stops')}개",
            f"- 매칭 슬롯: {course_slots.get('matched_stops')}개",
            f"- 고유 매칭 장소: {course_slots.get('matched_places')}개",
            f"- 미매칭 장소: {course_slots.get('unmatched_places')}개",
            "",
            "## 케이스별 비교",
            "",
            "| 케이스 | RAG 검증 | RAG 추천 경로 | 무RAG 검증 | 무RAG 추천 경로 | 주요 실패 항목 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in report["cases"]:
        with_rag = case["with_rag"]
        without_rag = case["without_rag_baseline"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(case["label"]),
                    f"{with_rag['passed_checks']}/{with_rag['total_checks']} 체크 통과",
                    ", ".join(with_rag["route_names"]),
                    no_rag_check_summary(without_rag),
                    ", ".join(without_rag.get("route_names", [])) or "미실행",
                    ", ".join(without_rag.get("failed_check_names", [])[:6])
                    or "검증 자료 없음",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 다음 비교 실험에 필요한 데이터",
            "",
            "- 같은 사용자 입력 5건에 대해 실제 외부 모델에서 근거 저장소를 주지 않고 받은 응답 원문",
            "- 장소명, 편의시설, 방문 전 확인 항목의 정답 대조표",
            "- 환각 여부, 제외 규칙 위반 여부, 출처 문구 유무를 사람이 채점한 컬럼",
        ]
    )
    return "\n".join(lines) + "\n"


def no_rag_check_summary(without_rag: dict[str, Any]) -> str:
    if not without_rag.get("observed"):
        return "미실행"
    return f"{without_rag.get('passed_checks')}/{without_rag.get('total_checks')} 체크 통과"
