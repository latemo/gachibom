# 설명 품질 Before/After 평가

생성일: 2026-07-14T19:49:49Z

> 아래 수치는 고정 질문과 규칙 기반 자동 채점으로 계산한 비교 지표입니다. 사용자 이해도와 도움성은 사람 검토 CSV 입력 전까지 미측정입니다.
> 안전 위반률은 후처리된 최종 응답 기준이며, 근거·조건 커버리지와 미지원 장소 탐지는 제한된 규칙 기반 근사치입니다.

## 결과 메트릭

| 메트릭 | Before | After | 개선도 | 방향 |
| --- | ---: | ---: | ---: | --- |
| 점수 계산 숫자 정확성 | 0.0% | 100.0% | +100.0%p | 높을수록 좋음 |
| 기대 근거 커버리지 | 48.8% | 95.2% | +46.4%p | 높을수록 좋음 |
| 사용자 조건 커버리지 | 63.9% | 75.0% | +11.1%p | 높을수록 좋음 |
| 계산 모드 설명 정확성 | 0.0% | 100.0% | +100.0%p | 높을수록 좋음 |
| 안전 문구 위반률 | 0.0% | 0.0% | -0.0%p | 낮을수록 좋음 |
| 지원되지 않은 장소 언급률 | 0.0% | 0.0% | -0.0%p | 낮을수록 좋음 |

## 실행 요약

| 구분 | 성공 응답 | 평균 시도 | 평균 지연 | p95 지연 |
| --- | ---: | ---: | ---: | ---: |
| Before | 30/30 | 1.07회 | 11041.8ms | 30269.5ms |
| After | 30/30 | 1.03회 | 5503.2ms | 13372.3ms |

## 응답별 검토

| 케이스 | 구분 | 숫자 정확성 | 근거 | 조건 | 모드 | 안전 위반 | 미지원 장소 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| recovery_quiet__recommendation_reason | before | 미측정 | 0.0% | 33.3% | 미측정 | 0.0% | 없음 |
| recovery_quiet__recommendation_reason | after | 미측정 | 66.7% | 100.0% | 미측정 | 0.0% | 없음 |
| recovery_quiet__score_calculation | before | 0.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| recovery_quiet__score_calculation | after | 100.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| recovery_quiet__deduction_reason | before | 미측정 | 0.0% | 0.0% | 미측정 | 0.0% | 없음 |
| recovery_quiet__deduction_reason | after | 미측정 | 100.0% | 50.0% | 미측정 | 0.0% | 없음 |
| recovery_quiet__pre_visit_check | before | 미측정 | 0.0% | 33.3% | 미측정 | 0.0% | 없음 |
| recovery_quiet__pre_visit_check | after | 미측정 | 100.0% | 100.0% | 미측정 | 0.0% | 없음 |
| recovery_quiet__exclusion_or_alternative | before | 미측정 | 50.0% | 0.0% | 미측정 | 0.0% | 없음 |
| recovery_quiet__exclusion_or_alternative | after | 미측정 | 100.0% | 50.0% | 미측정 | 0.0% | 없음 |
| recovery_quiet__mode_distinction | before | 미측정 | 100.0% | 미측정 | 0.0% | 0.0% | 없음 |
| recovery_quiet__mode_distinction | after | 미측정 | 100.0% | 미측정 | 100.0% | 0.0% | 없음 |
| wheelchair_access__recommendation_reason | before | 미측정 | 0.0% | 100.0% | 미측정 | 0.0% | 없음 |
| wheelchair_access__recommendation_reason | after | 미측정 | 33.3% | 100.0% | 미측정 | 0.0% | 없음 |
| wheelchair_access__score_calculation | before | 0.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| wheelchair_access__score_calculation | after | 100.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| wheelchair_access__deduction_reason | before | 미측정 | 100.0% | 100.0% | 미측정 | 0.0% | 없음 |
| wheelchair_access__deduction_reason | after | 미측정 | 100.0% | 100.0% | 미측정 | 0.0% | 없음 |
| wheelchair_access__pre_visit_check | before | 미측정 | 66.7% | 100.0% | 미측정 | 0.0% | 없음 |
| wheelchair_access__pre_visit_check | after | 미측정 | 100.0% | 100.0% | 미측정 | 0.0% | 없음 |
| wheelchair_access__exclusion_or_alternative | before | 미측정 | 50.0% | 100.0% | 미측정 | 0.0% | 없음 |
| wheelchair_access__exclusion_or_alternative | after | 미측정 | 100.0% | 100.0% | 미측정 | 0.0% | 없음 |
| wheelchair_access__mode_distinction | before | 미측정 | 100.0% | 미측정 | 0.0% | 0.0% | 없음 |
| wheelchair_access__mode_distinction | after | 미측정 | 100.0% | 미측정 | 100.0% | 0.0% | 없음 |
| stroller_family__recommendation_reason | before | 미측정 | 0.0% | 100.0% | 미측정 | 0.0% | 없음 |
| stroller_family__recommendation_reason | after | 미측정 | 100.0% | 66.7% | 미측정 | 0.0% | 없음 |
| stroller_family__score_calculation | before | 0.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| stroller_family__score_calculation | after | 100.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| stroller_family__deduction_reason | before | 미측정 | 0.0% | 33.3% | 미측정 | 0.0% | 없음 |
| stroller_family__deduction_reason | after | 미측정 | 100.0% | 66.7% | 미측정 | 0.0% | 없음 |
| stroller_family__pre_visit_check | before | 미측정 | 25.0% | 100.0% | 미측정 | 0.0% | 없음 |
| stroller_family__pre_visit_check | after | 미측정 | 100.0% | 66.7% | 미측정 | 0.0% | 없음 |
| stroller_family__exclusion_or_alternative | before | 미측정 | 50.0% | 50.0% | 미측정 | 0.0% | 없음 |
| stroller_family__exclusion_or_alternative | after | 미측정 | 100.0% | 50.0% | 미측정 | 0.0% | 없음 |
| stroller_family__mode_distinction | before | 미측정 | 100.0% | 미측정 | 0.0% | 0.0% | 없음 |
| stroller_family__mode_distinction | after | 미측정 | 100.0% | 미측정 | 100.0% | 0.0% | 없음 |
| weather_sensitive__recommendation_reason | before | 미측정 | 0.0% | 66.7% | 미측정 | 0.0% | 없음 |
| weather_sensitive__recommendation_reason | after | 미측정 | 66.7% | 100.0% | 미측정 | 0.0% | 없음 |
| weather_sensitive__score_calculation | before | 0.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| weather_sensitive__score_calculation | after | 100.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| weather_sensitive__deduction_reason | before | 미측정 | 미측정 | 미측정 | 미측정 | 0.0% | 없음 |
| weather_sensitive__deduction_reason | after | 미측정 | 미측정 | 미측정 | 미측정 | 0.0% | 없음 |
| weather_sensitive__pre_visit_check | before | 미측정 | 0.0% | 66.7% | 미측정 | 0.0% | 없음 |
| weather_sensitive__pre_visit_check | after | 미측정 | 100.0% | 66.7% | 미측정 | 0.0% | 없음 |
| weather_sensitive__exclusion_or_alternative | before | 미측정 | 0.0% | 50.0% | 미측정 | 0.0% | 없음 |
| weather_sensitive__exclusion_or_alternative | after | 미측정 | 100.0% | 50.0% | 미측정 | 0.0% | 없음 |
| weather_sensitive__mode_distinction | before | 미측정 | 100.0% | 미측정 | 0.0% | 0.0% | 없음 |
| weather_sensitive__mode_distinction | after | 미측정 | 100.0% | 미측정 | 100.0% | 0.0% | 없음 |
| diet_restricted__recommendation_reason | before | 미측정 | 0.0% | 66.7% | 미측정 | 0.0% | 없음 |
| diet_restricted__recommendation_reason | after | 미측정 | 100.0% | 100.0% | 미측정 | 0.0% | 없음 |
| diet_restricted__score_calculation | before | 0.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| diet_restricted__score_calculation | after | 100.0% | 100.0% | 미측정 | 미측정 | 0.0% | 없음 |
| diet_restricted__deduction_reason | before | 미측정 | 미측정 | 미측정 | 미측정 | 0.0% | 없음 |
| diet_restricted__deduction_reason | after | 미측정 | 미측정 | 미측정 | 미측정 | 0.0% | 없음 |
| diet_restricted__pre_visit_check | before | 미측정 | 25.0% | 100.0% | 미측정 | 0.0% | 없음 |
| diet_restricted__pre_visit_check | after | 미측정 | 100.0% | 33.3% | 미측정 | 0.0% | 없음 |
| diet_restricted__exclusion_or_alternative | before | 미측정 | 0.0% | 50.0% | 미측정 | 0.0% | 없음 |
| diet_restricted__exclusion_or_alternative | after | 미측정 | 100.0% | 50.0% | 미측정 | 0.0% | 없음 |
| diet_restricted__mode_distinction | before | 미측정 | 100.0% | 미측정 | 0.0% | 0.0% | 없음 |
| diet_restricted__mode_distinction | after | 미측정 | 100.0% | 미측정 | 100.0% | 0.0% | 없음 |
