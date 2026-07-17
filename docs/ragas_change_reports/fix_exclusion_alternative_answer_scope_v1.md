# RAGAS 변경 리포트: fix_exclusion_alternative_answer_scope_v1

> 적용 전·적용 후의 답변, 근거, 점수 변화를 한 변경 단위로 기록한 잠정 자동평가 리포트입니다.

## 변경 개요

- 변경 이유: 제외·대안 답변을 입력 회피·감점 근거와 현재 코스 장소 목록으로 제한
- 판단 근거: 기존 exclusion_or_alternative 평균 0.6683이며 excluded_place_names가 비어 있는데도 GPT 답변이 특정 코스 장소를 덜 적합하다고 단정, 실제 제외 후보 목록·후보별 점수가 없음을 명시하고 회피·감점 근거와 allowed course 장소만 반환한 5건을 재평가
- 변경 파일: src/help_chatbot_service.py, scripts/run_explanation_ab_eval.py, tests/test_help_chatbot_service.py, tests/test_explanation_ab_eval_runner.py
- 이전 실행: `data/ragas_metric_runs/fix_pre_visit_answer_scope_v1.json`
- 이후 실행: `data/ragas_metric_runs/fix_exclusion_alternative_answer_scope_v1.json`

## 핵심 지표 전후

| 지표 | 적용 전 | 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| 평균 Faithfulness | 0.8354 | 0.8907 | +0.0553 |
| 중앙값 | 0.8571 | 0.9391 | +0.0820 |
| 최저값 | 0.4211 | 0.4444 | +0.0233 |
| 최고값 | 1.0000 | 1.0000 | +0.0000 |
| 0.80 이상 건수 | 18 | 23 | +5.0000 |
| 0.95 이상 건수 | 10 | 15 | +5.0000 |

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
| exclusion_or_alternative | 0.6683 | 1.0000 | +0.3317 |
| mode_distinction | 0.9500 | 0.9500 | +0.0000 |
| pre_visit_check | 1.0000 | 1.0000 | +0.0000 |
| recommendation_reason | 0.9082 | 0.9082 | +0.0000 |
| score_calculation | 0.7336 | 0.7336 | +0.0000 |

## 변경·점수 변화 사례

| 사례 | 유형 | 점수 전 → 후 | 변화 | 답변 | 근거 |
| --- | --- | ---: | ---: | --- | --- |
| `recovery_quiet__exclusion_or_alternative__after` | exclusion_or_alternative | 0.4211 → 1.0000 | +0.5789 | 변경 | 동일 |
| `weather_sensitive__exclusion_or_alternative__after` | exclusion_or_alternative | 0.6667 → 1.0000 | +0.3333 | 변경 | 동일 |
| `wheelchair_access__exclusion_or_alternative__after` | exclusion_or_alternative | 0.7143 → 1.0000 | +0.2857 | 변경 | 동일 |
| `diet_restricted__exclusion_or_alternative__after` | exclusion_or_alternative | 0.7500 → 1.0000 | +0.2500 | 변경 | 동일 |
| `stroller_family__exclusion_or_alternative__after` | exclusion_or_alternative | 0.7895 → 1.0000 | +0.2105 | 변경 | 동일 |

## 대표 답변 전후

사례: `recovery_quiet__exclusion_or_alternative__after`

### 적용 전

추천 코스 안에서 입력하신 조건(긴 걷기 어려움, 혼잡 회피, 장시간 야외 회피)에 덜 적합할 수 있는 장소는 사려니숲길 무장애나눔길과 제주국제컨벤션센터입니다. 사려니숲길은 야외·날씨(우천·강풍)와 비교적 장시간 걷기 가능성 때문에 체력 저하와 야외 회피 조건에 감점 요인이 됩니다. 제주국제컨벤션센터는 대규모 행사 시 혼잡·대기와 실내 이동거리가 늘어날 수 있어 휴식 필요·혼잡 회피 조건에 불리할 수 있습니다. 제주문학관과 제주한란전시관은 도보 부담이 낮고 편의시설이 잘 맞아 적합도로 평가되었습니다. 이 평가는 mode이 "static"인 사전 계산 시나리오에 기반한 설명이며, 실시간 혼잡·날씨는 반영되지 않았습니다. 방문 전 현장 확인을 권합니다.

### 적용 후

입력된 회피·감점 근거: 식당 제외 / 혼잡 / 장시간 야외 체류 / 날씨 영향을 받을 수 있어 우천·강풍 여부 확인이 필요합니다 / 혼잡 또는 감염 우려 조건이 있어 사람이 몰릴 수 있는 장소를 감점합니다. 현재 추천 문맥에는 실제 제외 후보 목록과 후보별 점수가 없어 특정 코스 장소를 덜 적합하다고 단정할 수 없습니다. 현재 코스에서 함께 고려할 장소는 제주문학관, 제주한란전시관, 사려니숲길 무장애나눔길, 제주국제컨벤션센터입니다.
