# RAGAS 변경 리포트: fix_ragas_mode_evidence_context_v1

> 적용 전·적용 후의 답변, 근거, 점수 변화를 한 변경 단위로 기록한 잠정 자동평가 리포트입니다.

## 변경 개요

- 변경 이유: 모드 질문 RAGAS 근거에서 recommendation_context.mode 누락 교정
- 판단 근거: 제품 답변 변경 없이 전체 평균 0.7071에서 0.7504로 상승, 모드 질문 5건에만 mode 원본 필드와 static/runtime 의미를 추가
- 변경 파일: src/ragas_faithfulness_evaluation.py, tests/test_ragas_faithfulness_evaluation.py
- 이전 실행: `data/ragas_metric_runs/preserve_ragas_evidence_content_v1.json`
- 이후 실행: `data/ragas_metric_runs/fix_ragas_mode_evidence_context_v1.json`

## 핵심 지표 전후

| 지표 | 적용 전 | 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| 평균 Faithfulness | 0.7071 | 0.7504 | +0.0433 |
| 중앙값 | 0.7238 | 0.7639 | +0.0401 |
| 최저값 | 0.4211 | 0.4211 | +0.0000 |
| 최고값 | 0.9524 | 0.9524 | +0.0000 |
| 0.80 이상 건수 | 9 | 12 | +3.0000 |
| 0.95 이상 건수 | 1 | 1 | +0.0000 |

## 변경 범위와 회귀

- 답변 변경: 0건
- 검색 근거 변경: 5건
- 기준답안 변경: 0건
- 개선/회귀/동일: 5/0/25건
- 자동 판정: 통과

## 질문 유형별 평균 전후

| 질문 유형 | 적용 전 | 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| deduction_reason | 0.7522 | 0.7522 | +0.0000 |
| exclusion_or_alternative | 0.6683 | 0.6683 | +0.0000 |
| mode_distinction | 0.5397 | 0.7995 | +0.2598 |
| pre_visit_check | 0.6406 | 0.6406 | +0.0000 |
| recommendation_reason | 0.9082 | 0.9082 | +0.0000 |
| score_calculation | 0.7336 | 0.7336 | +0.0000 |

## 변경·점수 변화 사례

| 사례 | 유형 | 점수 전 → 후 | 변화 | 답변 | 근거 |
| --- | --- | ---: | ---: | --- | --- |
| `wheelchair_access__mode_distinction__after` | mode_distinction | 0.4286 → 0.7857 | +0.3571 | 동일 | 변경 |
| `weather_sensitive__mode_distinction__after` | mode_distinction | 0.5455 → 0.8571 | +0.3116 | 동일 | 변경 |
| `diet_restricted__mode_distinction__after` | mode_distinction | 0.5556 → 0.8182 | +0.2626 | 동일 | 변경 |
| `stroller_family__mode_distinction__after` | mode_distinction | 0.7143 → 0.9000 | +0.1857 | 동일 | 변경 |
| `recovery_quiet__mode_distinction__after` | mode_distinction | 0.4545 → 0.6364 | +0.1819 | 동일 | 변경 |
