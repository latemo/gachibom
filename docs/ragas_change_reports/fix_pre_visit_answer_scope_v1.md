# RAGAS 변경 리포트: fix_pre_visit_answer_scope_v1

> 적용 전·적용 후의 답변, 근거, 점수 변화를 한 변경 단위로 기록한 잠정 자동평가 리포트입니다.

## 변경 개요

- 변경 이유: 방문 전 확인 답변을 selected_place.check_before_visit 근거 목록으로 제한
- 판단 근거: 기존 pre_visit_check 평균 0.6405이며 GPT 답변에 점수·모드·출처·운영시간 등 질문 밖 주장이 포함됨, 장소별 check_before_visit 원본 목록만 한 문장으로 반환하고 5건만 재평가
- 변경 파일: src/help_chatbot_service.py, scripts/run_explanation_ab_eval.py, tests/test_help_chatbot_service.py, tests/test_explanation_ab_eval_runner.py
- 이전 실행: `data/ragas_metric_runs/add_per_change_before_after_reports_v1.json`
- 이후 실행: `data/ragas_metric_runs/fix_pre_visit_answer_scope_v1.json`

## 핵심 지표 전후

| 지표 | 적용 전 | 적용 후 | 변화 |
| --- | ---: | ---: | ---: |
| 평균 Faithfulness | 0.7755 | 0.8354 | +0.0599 |
| 중앙값 | 0.7639 | 0.8571 | +0.0932 |
| 최저값 | 0.4211 | 0.4211 | +0.0000 |
| 최고값 | 1.0000 | 1.0000 | +0.0000 |
| 0.80 이상 건수 | 13 | 18 | +5.0000 |
| 0.95 이상 건수 | 5 | 10 | +5.0000 |

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
| mode_distinction | 0.9500 | 0.9500 | +0.0000 |
| pre_visit_check | 0.6406 | 1.0000 | +0.3594 |
| recommendation_reason | 0.9082 | 0.9082 | +0.0000 |
| score_calculation | 0.7336 | 0.7336 | +0.0000 |

## 변경·점수 변화 사례

| 사례 | 유형 | 점수 전 → 후 | 변화 | 답변 | 근거 |
| --- | --- | ---: | ---: | --- | --- |
| `weather_sensitive__pre_visit_check__after` | pre_visit_check | 0.5385 → 1.0000 | +0.4615 | 변경 | 동일 |
| `wheelchair_access__pre_visit_check__after` | pre_visit_check | 0.6250 → 1.0000 | +0.3750 | 변경 | 동일 |
| `recovery_quiet__pre_visit_check__after` | pre_visit_check | 0.6667 → 1.0000 | +0.3333 | 변경 | 동일 |
| `stroller_family__pre_visit_check__after` | pre_visit_check | 0.6667 → 1.0000 | +0.3333 | 변경 | 동일 |
| `diet_restricted__pre_visit_check__after` | pre_visit_check | 0.7059 → 1.0000 | +0.2941 | 변경 | 동일 |

## 대표 답변 전후

사례: `weather_sensitive__pre_visit_check__after`

### 적용 전

제주문학관은 사용자 조건(도보 부담 매우 낮음, 실내·문화 선호, 필요한 편의시설)과 잘 맞아 점수 98·등급 A·신뢰도 높음으로 평가되었습니다. 방문 전 반드시 확인할 항목은 휠체어 접근성(경사로·출입문 폭), 장애인 화장실·장애인 주차 유무, 휴식 공간과 의자 유무, 당일 혼잡도·운영시간, 강풍 등 방문 당일 날씨와 실내 대피 가능 여부입니다. 추천 근거는 도보 부담이 낮고 필수 편의시설 정보가 적합하다는 점이며, 제공된 출처(열린관광 모두의 여행 제주문학관, 제주특별자치도 사회적약자 시설 데이터)는 검증 완료 상태입니다. 이 결과는 mode가 static인 사전 계산 시나리오에 따른 것이며, 실시간 현장 상태(혼잡·공사·임시 폐쇄 등)는 방문 전 별도 확인이 필요합니다. 꼭 공식 운영 정보나 시설에 전화로 최신 상태를 확인하고 출발하세요.

### 적용 후

제주문학관 방문 전 확인 항목은 휴식 공간, 혼잡도, 그늘과 실내 대피 가능 여부, 강풍 여부, 방문 당일 날씨입니다.
