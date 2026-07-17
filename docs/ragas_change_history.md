# RAGAS 변경 전후 지표 이력

> 모든 수정은 근거·답변·점수의 전후 변화를 함께 기록합니다. 자동평가 잠정 결과이며 사람 검수 전 최종 성능으로 발표하지 않습니다.

## 고정 기준선

- 실행 ID: `baseline_20260715_ragas_faithfulness_v1`
- 기록 시각: 2026-07-14T18:50:33Z
- 표본: 30건
- 평균 Faithfulness: 0.7071
- 중앙값: 0.7238
- 0.80 이상: 9건 (30.00%)
- 0.95 이상: 1건 (3.33%)

## 변경 이력

| 변경 ID | 이유 | 평균 전 → 후 | 변화 | 개선/회귀 | 근거 변경 | 판정 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `add_ragas_change_tracking_v1` | RAGAS 수정 전후 근거·답변·점수 이력 기능 추가 | 0.7071 → 0.7071 | +0.0000 | 0/0 | 0건 | 통과 |
| `preserve_ragas_evidence_content_v1` | 수정 전후 답변·근거 원문을 실행별로 보존 | 0.7071 → 0.7071 | +0.0000 | 0/0 | 0건 | 통과 |
| `fix_ragas_mode_evidence_context_v1` | 모드 질문 RAGAS 근거에서 recommendation_context.mode 누락 교정 | 0.7071 → 0.7504 | +0.0433 | 5/0 | 5건 | 통과 |
| `fix_mode_distinction_answer_scope_v1` | 모드 구분 답변을 mode 필드 기반 2문장 규칙으로 제한 | 0.7504 → 0.7755 | +0.0251 | 5/0 | 0건 | 통과 |
| `add_per_change_before_after_reports_v1` | 모든 변경마다 적용 전·적용 후 상세 리포트 자동 생성 | 0.7755 → 0.7755 | +0.0000 | 0/0 | 0건 | 통과 |
| `fix_pre_visit_answer_scope_v1` | 방문 전 확인 답변을 selected_place.check_before_visit 근거 목록으로 제한 | 0.7755 → 0.8354 | +0.0599 | 5/0 | 0건 | 통과 |
| `fix_exclusion_alternative_answer_scope_v1` | 제외·대안 답변을 입력 회피·감점 근거와 현재 코스 장소 목록으로 제한 | 0.8354 → 0.8907 | +0.0553 | 5/0 | 0건 | 통과 |

## 최근 변경 상세

- 변경 ID: `fix_exclusion_alternative_answer_scope_v1`
- 변경 이유: 제외·대안 답변을 입력 회피·감점 근거와 현재 코스 장소 목록으로 제한
- 판단 근거: 기존 exclusion_or_alternative 평균 0.6683이며 excluded_place_names가 비어 있는데도 GPT 답변이 특정 코스 장소를 덜 적합하다고 단정, 실제 제외 후보 목록·후보별 점수가 없음을 명시하고 회피·감점 근거와 allowed course 장소만 반환한 5건을 재평가
- 변경 파일: src/help_chatbot_service.py, scripts/run_explanation_ab_eval.py, tests/test_help_chatbot_service.py, tests/test_explanation_ab_eval_runner.py

### 질문 유형별 평균 변화

| 질문 유형 | 이전 | 이후 | 변화 |
| --- | ---: | ---: | ---: |
| deduction_reason | 0.7522 | 0.7522 | +0.0000 |
| exclusion_or_alternative | 0.6683 | 1.0000 | +0.3317 |
| mode_distinction | 0.9500 | 0.9500 | +0.0000 |
| pre_visit_check | 1.0000 | 1.0000 | +0.0000 |
| recommendation_reason | 0.9082 | 0.9082 | +0.0000 |
| score_calculation | 0.7336 | 0.7336 | +0.0000 |
