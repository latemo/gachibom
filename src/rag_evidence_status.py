"""Synthesize honest RAG evidence status from existing repository reports."""

from __future__ import annotations

from datetime import date
from typing import Any


def build_rag_evidence_status(
    policy_report: dict[str, Any],
    explanation_report: dict[str, Any],
    human_report: dict[str, Any],
    goldset: dict[str, Any],
    goldset_evaluation: dict[str, Any],
    *,
    generated_at: date,
) -> dict[str, Any]:
    policy_summary = policy_report.get("summary", {})
    explanation_summary = explanation_report.get("summary", {})
    variants = explanation_summary.get("variants", {})
    before = variants.get("before", {})
    after = variants.get("after", {})
    before_metrics = before.get("metrics", {})
    after_metrics = after.get("metrics", {})
    human_coverage = human_report.get("coverage", {})
    gold_summary = goldset.get("summary", {})

    evidence_before = _number(before_metrics.get("expected_evidence_coverage"))
    evidence_after = _number(after_metrics.get("expected_evidence_coverage"))
    condition_before = _number(before_metrics.get("user_condition_coverage"))
    condition_after = _number(after_metrics.get("user_condition_coverage"))
    record_count = int(before.get("record_count") or 0) + int(after.get("record_count") or 0)
    case_count = max(int(before.get("case_count") or 0), int(after.get("case_count") or 0))

    final_metrics_reportable = goldset_evaluation.get("reportable") is True
    return {
        "schema_version": "1.0",
        "generated_at": generated_at.isoformat(),
        "status": "final_metrics_ready" if final_metrics_reportable else "evidence_in_progress",
        "source_dates": {
            "policy_regression": policy_report.get("generated_at"),
            "gpt_explanation_ab": explanation_report.get("generated_at"),
            "human_review": human_report.get("generated_at"),
            "goldset_draft": goldset.get("generated_at"),
            "goldset_evaluation": goldset_evaluation.get("generated_at"),
        },
        "current_evidence": {
            "policy_regression": {
                "label": "정책·랭킹 회귀검증",
                "passed_checks": policy_summary.get("with_rag_passed_checks"),
                "total_checks": policy_summary.get("with_rag_total_checks"),
                "case_count": policy_summary.get("scenario_cases"),
                "interpretation": "use_ai=false로 실행한 규칙·정책 검증이며 RAG 검색 정확도나 GPT 성능이 아니다.",
            },
            "controlled_fixture": {
                "label": "무RAG 통제 fixture",
                "passed_checks": policy_summary.get("without_rag_passed_checks"),
                "total_checks": policy_summary.get("without_rag_total_checks"),
                "case_count": policy_summary.get("without_rag_observed_cases"),
                "interpretation": "실제 외부 모델 호출 결과가 아니라 위험을 재현한 고정 fixture다.",
            },
            "gpt_explanation_ab": {
                "label": "GPT-5 mini 설명 컨텍스트 A/B 자동평가",
                "model": explanation_report.get("run", {}).get("model"),
                "case_count": case_count,
                "record_count": record_count,
                "fresh_records": explanation_report.get("run", {}).get("fresh_records"),
                "resumed_records": explanation_report.get("run", {}).get("resumed_records"),
                "expected_evidence_coverage": _metric_change(evidence_before, evidence_after),
                "user_condition_coverage": _metric_change(condition_before, condition_after),
                "interpretation": "동일 모델에 추천 컨텍스트를 주기 전후의 설명 자동평가이며 추천 순위 성능이 아니다.",
            },
            "human_review": {
                "status": human_report.get("human_review_status"),
                "completed_rows": human_coverage.get("completed_review_count"),
                "total_rows": human_coverage.get("input_review_row_count"),
                "coverage_rate": human_coverage.get("assignment_coverage_rate"),
                "interpretation": "사람 블라인드 검수가 완료되기 전까지 설명 품질은 잠정 결과다.",
            },
            "goldset": {
                "status": goldset.get("status"),
                "approved_cases": gold_summary.get("approved_case_count"),
                "total_cases": gold_summary.get("case_count"),
                "pending_cases": gold_summary.get("pending_case_count"),
                "final_metrics_reportable": final_metrics_reportable,
                "evaluation_status": goldset_evaluation.get("status"),
            },
        },
        "primary_metrics": {
            "recall_at_4": _final_metric(goldset_evaluation, "recall_at_4"),
            "grounded_claim_rate": _final_metric(goldset_evaluation, "grounded_claim_rate"),
            "hard_constraint_violation_rate": _final_metric(
                goldset_evaluation, "hard_constraint_violation_rate"
            ),
            "status": "final" if final_metrics_reportable else "pending_goldset_and_runs",
        },
        "case_matrix": _case_matrix(policy_report.get("cases", [])),
        "pipelines": {
            "online_recommendation": [
                "사용자 조건 입력",
                "의도·필수 조건 추출",
                "검증 상태·시설 조건 필터",
                "BM25·구조화 후보 검색",
                "룰 기반 점수·제외 정책",
                "최대 4곳·동선 결정",
                "출처·근거 번들 조립",
                "GPT-5 mini 근거 설명",
                "안전 검증·룰 기반 폴백",
                "화면 표시",
            ],
            "offline_data": [
                "공공·관광 원본 수집",
                "정규화",
                "스키마 검사",
                "이미지·출처 연결",
                "사람 검수",
                "verified·partial·needs_check 결정",
                "서비스 시드 생성",
                "검색·추천 반영",
                "평가·운영 리포트 생성",
            ],
        },
        "publication_guidance": {
            "use_now": [
                "정책·랭킹 회귀검증 59/59",
                "GPT-5 mini 추천 컨텍스트 전후 설명 자동평가",
                "기대 근거 커버리지와 사용자 조건 커버리지는 잠정 지표",
            ],
            "do_not_claim": [
                "RAG 성능 59/59",
                "실제 GPT-5 mini 대비 무RAG 5/59",
                "사람 검증이 끝난 최종 설명 품질",
                "Gold Set Recall@4 또는 Grounded Claim Rate 최종 수치",
            ],
        },
        "next_actions": [
            "Gold Set v1 60개 질문을 두 명이 독립 검수한다.",
            "불일치 케이스를 제3자가 확정한다.",
            "GPT 단독·룰 기반·하이브리드 실행 로그를 동일 기준일로 수집한다.",
            "Recall@4·Grounded Claim Rate·필수 조건 위반률을 다시 산출한다.",
            "사람 블라인드 설명 검수 90행을 완료한다.",
        ],
    }


def render_rag_evidence_status_markdown(report: dict[str, Any]) -> str:
    evidence = report["current_evidence"]
    gpt = evidence["gpt_explanation_ab"]
    lines = [
        "# 가치봄 제주 RAG 평가 증거 현황",
        "",
        f"생성일: {report['generated_at']}",
        f"상태: {report['status']}",
        "",
        "## 지금 말할 수 있는 결과",
        "",
        f"- 정책·랭킹 회귀검증: {evidence['policy_regression']['passed_checks']}/{evidence['policy_regression']['total_checks']} 체크 통과",
        f"- 무RAG 통제 fixture: {evidence['controlled_fixture']['passed_checks']}/{evidence['controlled_fixture']['total_checks']} 체크 통과",
        f"- GPT-5 mini 저장 응답: {gpt['case_count']}개 질문, {gpt['record_count']}개 응답",
        "- 기대 근거 커버리지: " + _metric_markdown(gpt["expected_evidence_coverage"]),
        "- 사용자 조건 커버리지: " + _metric_markdown(gpt["user_condition_coverage"]),
        f"- 사람 검수: {evidence['human_review']['completed_rows']}/{evidence['human_review']['total_rows']}행 완료",
        f"- Gold Set v1: {evidence['goldset']['approved_cases']}/{evidence['goldset']['total_cases']}개 승인",
        "",
        "## 해석 제한",
        "",
    ]
    lines.extend(f"- 사용 금지 표현: {item}" for item in report["publication_guidance"]["do_not_claim"])
    lines.extend(["", "## 다음 작업", ""])
    lines.extend(f"- {item}" for item in report["next_actions"])
    return "\n".join(lines) + "\n"


def _case_matrix(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        with_rag = case.get("with_rag", {})
        rows.append(
            {
                "id": case.get("id"),
                "label": case.get("label"),
                "intent": case.get("intent"),
                "passed_checks": with_rag.get("passed_checks"),
                "total_checks": with_rag.get("total_checks"),
                "route_names": with_rag.get("route_names", []),
                "classification": "policy_ranking_regression",
            }
        )
    return rows


def _metric_change(before: float | None, after: float | None) -> dict[str, Any]:
    delta = None if before is None or after is None else round(after - before, 4)
    return {
        "before": before,
        "after": after,
        "delta": delta,
        "status": "provisional_automatic_metric",
    }


def _final_metric(goldset_evaluation: dict[str, Any], metric_id: str) -> dict[str, Any]:
    if goldset_evaluation.get("reportable") is not True:
        return {"value": None, "status": "not_reportable"}
    systems = goldset_evaluation.get("systems", {})
    return {
        "value": {system: item.get("metrics", {}).get(metric_id) for system, item in systems.items()},
        "status": "final",
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _metric_markdown(metric: dict[str, Any]) -> str:
    before = metric.get("before")
    after = metric.get("after")
    delta = metric.get("delta")
    if before is None or after is None or delta is None:
        return "미측정"
    return f"{before * 100:.2f}% → {after * 100:.2f}% ({delta * 100:+.2f}%p, 자동평가·잠정)"
