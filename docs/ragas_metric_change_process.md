# RAGAS 수정 전후 지표 기록 절차

## 현재 기준선

- 실행 ID: `baseline_20260715_ragas_faithfulness_v1`
- 평가 표본: 30건
- 평균 Faithfulness: 0.7071
- 중앙값: 0.7238
- 0.80 이상: 9건(30.00%)
- 0.95 이상: 1건(3.33%)
- 자동평가 상태: 잠정, 사람 검수 대기

## 수정 우선순위

| 순서 | 질문 유형 | 현재 평균 | 수정 기준 |
| ---: | --- | ---: | --- |
| 1 | 실시간·사전 계산 구분 | 0.5397 | `mode` 근거만 사용하고 2~3문장으로 제한 |
| 2 | 방문 전 확인 | 0.6405 | `check_before_visit`에 있는 항목만 출력 |
| 3 | 제외·대안 | 0.6683 | 코스 감점을 특정 장소에 연결하지 않음 |
| 4 | 점수 계산 | 0.7337 | 누락된 보너스·감점·상한을 0으로 단정하지 않음 |
| 유지 | 추천 이유 | 0.9082 | 현재 데이터 직접 인용 구조를 기준 템플릿으로 유지 |

## 변경 1건의 필수 기록

모든 수정은 다음 항목을 한 변경 ID에 묶는다.

1. 변경 이유: 어떤 문제를 해결하는지
2. 판단 근거: 수정 전 지표와 실패 사례
3. 변경 파일: 프롬프트·후처리·데이터 파일
4. 질문 변화: 평가 질문이 바뀌었는지
5. 답변 변화: 생성 답변이 바뀐 사례 수
6. 근거 변화: 검색 문맥·기준답안이 바뀐 사례 수
7. 지표 변화: 전체·질문 유형·상황·개별 사례의 전후 점수
8. 회귀 여부: 0.02 이상 하락한 사례

## 수정 후 실행 순서

### 1. 설명 답변 재생성

프롬프트 동작을 수정했으면 `src/help_chatbot_service.py`의
`HELP_CHATBOT_PROMPT_VERSION`도 반드시 올린다.

```powershell
python scripts/run_explanation_ab_eval.py `
  --cases data/explanation_eval_cases.json `
  --seed web/data/app_recommendation_seed.json `
  --model gpt-5-mini `
  --max-workers 3 `
  --retries 2
```

### 2. RAGAS 재평가

답변·근거 해시가 바뀐 사례만 새로 평가하고, 동일한 사례는 기존 점수를 재사용한다.

```powershell
python scripts/run_ragas_faithfulness_eval.py --max-workers 4
```

### 3. 전후 변화 기록

변경 ID는 재사용할 수 없다. 근거 데이터나 기준답안을 의도적으로 바꾼 경우에만
`--allow-evidence-change`를 추가한다.

```powershell
python scripts/record_ragas_change.py `
  --change-id fix_mode_distinction_v1 `
  --reason "사전 계산 여부 질문에서 불필요한 추가 주장 제거" `
  --evidence "mode_distinction 평균 0.5397" `
  --evidence "wheelchair_access mode 사례 0.4286" `
  --changed-file src/help_chatbot_service.py
```

근거를 의도적으로 수정했다면 다음처럼 실행한다.

```powershell
python scripts/record_ragas_change.py `
  --change-id update_place_evidence_v1 `
  --reason "장소별 근거와 코스 전체 근거 분리" `
  --evidence "제외·대안 답변에서 코스 감점이 장소 감점으로 오인됨" `
  --changed-file data/explanation_eval_cases.json `
  --allow-evidence-change
```

## 자동 판정 규칙

다음 조건을 모두 만족해야 `passed`로 기록한다.

- 이전과 이후의 평가 표본이 동일함
- 전체 평균이 하락하지 않음
- 개별 사례가 0.02 이상 하락하지 않음
- 근거 변경이 있다면 명시적으로 승인함

판정이 `review_required`여도 결과는 삭제하지 않는다. 회귀를 숨기지 않기 위해 해당
실행과 비교 결과를 그대로 이력에 남긴다.

## 누적 산출물

| 파일 | 역할 |
| --- | --- |
| `data/ragas_metric_runs/<change-id>.json` | 실행별 30건 점수, 질문·답변·근거 원문과 해시 |
| `data/ragas_change_history.json` | 전체 변경의 기계 판독 가능한 누적 이력 |
| `docs/ragas_change_history.md` | 사람이 읽는 전후 지표 표 |

절대 지표 목표는 사람 검수 표본과 자동평가의 일치도를 확인한 뒤 확정한다. 그전에는
현재 기준선 대비 개선과 회귀 방지를 운영 기준으로 사용한다.
