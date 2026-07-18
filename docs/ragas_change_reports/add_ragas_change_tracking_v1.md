# RAGAS 변경 리포트: add_ragas_change_tracking_v1

> 적용 전·적용 후의 답변, 근거, 점수 변화를 한 변경 단위로 기록한 잠정 자동평가 리포트입니다.

## 변경 개요

- 변경 이유: RAGAS 수정 전후 근거·답변·점수 이력 기능 추가
- 판단 근거: 기존에는 현재 점수만 있고 변경 전후 비교 이력이 없었음, 기준선 평균 0.7071과 30개 개별 사례를 보존해야 함
- 변경 파일: src/ragas_change_tracking.py, scripts/record_ragas_change.py, tests/test_ragas_change_tracking.py, docs/ragas_metric_change_process.md
- 이전 실행: `data/ragas_metric_runs/baseline_20260715_ragas_faithfulness_v1.json`
- 이후 실행: `data/ragas_metric_runs/add_ragas_change_tracking_v1.json`

## 핵심 지표 전후

| 지표 | 적용 전 | 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| 평균 Faithfulness | 0.7071 | 0.7071 | +0.0000 |
| 중앙값 | 0.7238 | 0.7238 | +0.0000 |
| 최저값 | 0.4211 | 0.4211 | +0.0000 |
| 최고값 | 0.9524 | 0.9524 | +0.0000 |
| 0.80 이상 건수 | 9 | 9 | +0.0000 |
| 0.95 이상 건수 | 1 | 1 | +0.0000 |

## 변경 범위와 회귀

- 답변 변경: 0건
- 검색 근거 변경: 0건
- 기준답안 변경: 0건
- 개선/회귀/동일: 0/0/30건
- 자동 판정: 통과

## 질문 유형별 평균 전후

| 질문 유형 | 적용 전 | 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| deduction_reason | 0.7522 | 0.7522 | +0.0000 |
| exclusion_or_alternative | 0.6683 | 0.6683 | +0.0000 |
| mode_distinction | 0.5397 | 0.5397 | +0.0000 |
| pre_visit_check | 0.6406 | 0.6406 | +0.0000 |
| recommendation_reason | 0.9082 | 0.9082 | +0.0000 |
| score_calculation | 0.7336 | 0.7336 | +0.0000 |

## 변경·점수 변화 사례

| 사례 | 유형 | 점수 전 → 후 | 변화 | 답변 | 근거 |
| --- | --- | ---: | ---: | --- | --- |
| - | - | - | - | 변경 없음 | 변경 없음 |
