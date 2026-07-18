# RAGAS 변경 리포트: fix_mode_distinction_answer_scope_v1

> 적용 전·적용 후의 답변, 근거, 점수 변화를 한 변경 단위로 기록한 잠정 자동평가 리포트입니다.

## 변경 개요

- 변경 이유: 모드 구분 답변을 mode 필드 기반 2문장 규칙으로 제한
- 판단 근거: 교정 후 mode_distinction 평균 0.7995, recovery_quiet 사례 0.6364, 점수·출처·현장 상태 등 질문 밖 추가 주장을 제거
- 변경 파일: src/help_chatbot_service.py, scripts/run_explanation_ab_eval.py, tests/test_help_chatbot_service.py, tests/test_explanation_ab_eval_runner.py
- 이전 실행: `data/ragas_metric_runs/fix_ragas_mode_evidence_context_v1.json`
- 이후 실행: `data/ragas_metric_runs/fix_mode_distinction_answer_scope_v1.json`

## 핵심 지표 전후

| 지표 | 적용 전 | 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| 평균 Faithfulness | 0.7504 | 0.7755 | +0.0251 |
| 중앙값 | 0.7639 | 0.7639 | +0.0000 |
| 최저값 | 0.4211 | 0.4211 | +0.0000 |
| 최고값 | 0.9524 | 1.0000 | +0.0476 |
| 0.80 이상 건수 | 12 | 13 | +1.0000 |
| 0.95 이상 건수 | 1 | 5 | +4.0000 |

## 변경 범위와 회귀

- 답변 변경: 5건
- 검색 근거 변경: 0건
- 기준답안 변경: 0건
- 개선/회귀/동일: 5/0/25건
- 자동 판정: 통과

## 질문 유형별 평균 전후

| 질문 유형 | 적용 전 | 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| deduction_reason | 0.7522 | 0.7522 | +0.0000 |
| exclusion_or_alternative | 0.6683 | 0.6683 | +0.0000 |
| mode_distinction | 0.7995 | 0.9500 | +0.1505 |
| pre_visit_check | 0.6406 | 0.6406 | +0.0000 |
| recommendation_reason | 0.9082 | 0.9082 | +0.0000 |
| score_calculation | 0.7336 | 0.7336 | +0.0000 |

## 변경·점수 변화 사례

| 사례 | 유형 | 점수 전 → 후 | 변화 | 답변 | 근거 |
| --- | --- | ---: | ---: | --- | --- |
| `wheelchair_access__mode_distinction__after` | mode_distinction | 0.7857 → 1.0000 | +0.2143 | 변경 | 동일 |
| `diet_restricted__mode_distinction__after` | mode_distinction | 0.8182 → 1.0000 | +0.1818 | 변경 | 동일 |
| `weather_sensitive__mode_distinction__after` | mode_distinction | 0.8571 → 1.0000 | +0.1429 | 변경 | 동일 |
| `recovery_quiet__mode_distinction__after` | mode_distinction | 0.6364 → 0.7500 | +0.1136 | 변경 | 동일 |
| `stroller_family__mode_distinction__after` | mode_distinction | 0.9000 → 1.0000 | +0.1000 | 변경 | 동일 |

## 대표 답변 전후

사례: `wheelchair_access__mode_distinction__after`

### 적용 전

표시된 '제주문학관' 추천은 recommendation_context의 mode가 "static"으로 되어 있어 실시간 개인별 재계산이 아닌 사전 계산된(가장 근접한 사전 시나리오) 결과입니다. 생성일(2026-07-09)과 출처(verified)가 함께 제공되어 있으나, 이는 현장 상태를 실시간 반영하지 않습니다. 선택된 장소의 점수는 calculation_trace가 있어 기본 점수(base_total) →(해당 없음: 보너스/감점 세부 없음)→상한 적용→최종 점수 순서로 정리되어 있으며 이 케이스는 base_total과 final_total이 각각 93으로 표시됩니다. 실시간 상태(예: 공사·혼잡·임시 폐쇄)는 방문 전 기관 문의나 공식 웹·전화 확인이 필요합니다. 이 결과는 이동 가능성을 보장하지 않으니 현장 확인을 우선하세요.

### 적용 후

이 추천은 실시간 개인별 재계산 결과가 아니라, 입력 조건과 가장 가까운 사전 계산 시나리오 결과입니다. 근거는 recommendation_context.mode가 "static"으로 표시된 점입니다.
