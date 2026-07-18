# RAGAS Faithfulness 자동검증 보고서

기준일: 2026-07-15

> 자동평가·잠정 결과입니다. 사람 검수 Gold Set 승인 전에는 최종 성능으로 발표할 수 없습니다.

## 결과 요약

| 항목 | 값 |
| --- | ---: |
| 평가 성공 | 30/30 |
| 평균 Faithfulness | 0.8907 |
| 중앙값 | 0.9392 |
| 최소값 | 0.4444 |
| 기준 통과율 | 0.5000 |

## 해석

- Faithfulness는 생성 답변의 주장 중 제공 근거로 뒷받침되는 비율을 0~1로 평가합니다.
- 이 보고서는 저장된 GPT 설명과 해당 케이스의 추천 근거를 비교합니다.
- 추천 순위 정확도는 별도의 사람 승인 Gold Set과 Recall@4로 검증해야 합니다.

## 우선 확인할 낮은 점수 사례

| 케이스 | 조건 | 질문 유형 | 점수 | 통과 |
| --- | --- | --- | ---: | --- |
| stroller_family__score_calculation | after | score_calculation | 0.4444 | 아니오 |
| recovery_quiet__deduction_reason | after | deduction_reason | 0.6000 | 아니오 |
| wheelchair_access__score_calculation | after | score_calculation | 0.7333 | 아니오 |
| wheelchair_access__deduction_reason | after | deduction_reason | 0.7333 | 아니오 |
| weather_sensitive__deduction_reason | after | deduction_reason | 0.7333 | 아니오 |
| recovery_quiet__mode_distinction | after | mode_distinction | 0.7500 | 아니오 |
| diet_restricted__deduction_reason | after | deduction_reason | 0.7778 | 아니오 |
| recovery_quiet__score_calculation | after | score_calculation | 0.8000 | 아니오 |
| weather_sensitive__score_calculation | after | score_calculation | 0.8333 | 아니오 |
| recovery_quiet__recommendation_reason | after | recommendation_reason | 0.8571 | 아니오 |

## 다음 단계

1. 기준 미달 사례의 문장과 근거를 대조합니다.
2. 사람 검수 Gold Set을 확정한 뒤 Recall@4와 필수 조건 위반률을 계산합니다.
3. 최종 발표에는 자동평가와 사람평가를 분리해 표시합니다.
