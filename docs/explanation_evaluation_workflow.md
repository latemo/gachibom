# 설명 품질 Before/After 평가 운영 방법

## 목적

도움말 챗봇에 추천 문맥을 연결한 뒤 설명 품질이 실제로 개선됐는지 같은 모델과 같은 질문으로 비교한다.

- `Before`: 질문과 최근 대화만 전달
- `After`: 동일 질문에 사용자 조건, 추천 결과, 선택 장소, 점수 계산 이력과 출처를 추가
- 자동 지표와 사람 평가를 분리하며, 사람 검토 전에는 사용자 이해도나 도움성 수치를 성과로 발표하지 않는다.

## 산출물

| 파일 | 용도 |
| --- | --- |
| `data/explanation_eval_cases.json` | 5개 시나리오 × 6개 질문 유형, 총 30개 고정 케이스 |
| `data/explanation_eval_results.json` | 원본 Before/After 응답, 자동 채점 상세, 실행 메타데이터 |
| `data/explanation_eval_results.csv` | 응답별 자동 지표 검토표 |
| `data/explanation_eval_human_review.csv` | 기존 비블라인드 템플릿(`legacy_unblinded`, 최종 비교에 사용하지 않음) |
| `data/explanation_eval_blind_review.csv` | 리뷰어에게 배포할 익명 A/B 평가 원본 |
| `data/explanation_eval_blind_key.json` | A/B 매핑 키(리뷰어 공유·커밋 금지) |
| `data/explanation_eval_human_summary.json` | 블라인드 사람 평가 집계 결과 |
| `outputs/explanation-review-20260712/*.xlsx` | R01·R02·R03에게 바로 전달하는 쉬운 평가 파일 |
| `docs/explanation_quality_report.md` | 발표·리뷰용 자동 지표 요약 |
| `docs/explanation_human_quality_report.md` | 사람 평가 진행률·통과 기준 요약 |

## 재생성

평가 케이스를 먼저 재생성하고 dry-run으로 60개 호출 계획을 검증한다.

```powershell
python scripts/build_explanation_eval_cases.py `
  --seed web/data/app_recommendation_seed.json `
  --output data/explanation_eval_cases.json

python scripts/run_explanation_ab_eval.py `
  --cases data/explanation_eval_cases.json `
  --seed web/data/app_recommendation_seed.json `
  --dry-run
```

실제 실행 시 API 키는 현재 셸의 환경 변수로만 제공한다. 키나 `.env` 파일은 결과에 포함하거나 커밋하지 않는다.

```powershell
$env:OPENAI_API_KEY = "<session-only>"
python scripts/run_explanation_ab_eval.py `
  --cases data/explanation_eval_cases.json `
  --seed web/data/app_recommendation_seed.json `
  --model gpt-5-mini `
  --max-workers 3 `
  --retries 2
Remove-Item Env:OPENAI_API_KEY
```

성공 응답은 체크포인트와 질문·모델·문맥·프롬프트 버전 해시가 같을 때 재사용된다. 프롬프트 동작을 변경하면 `HELP_CHATBOT_PROMPT_VERSION`도 함께 올린다.

## 자동 지표 해석

| 지표 | 적용 범위 | 주의사항 |
| --- | --- | --- |
| 점수 계산 숫자 정확성 | 점수 계산 질문 5개 | trace의 서로 다른 숫자와 답변의 점수 표현을 비교 |
| 기대 근거 커버리지 | 기대 근거가 있는 질문 | 동의어 규칙 기반 근사치이며 사람 평가를 대체하지 않음 |
| 사용자 조건 커버리지 | 조건 설명이 필요한 질문 | 이동·필수 접근성·회피 조건 그룹 반영 여부 |
| 계산 모드 정확성 | 정적/실시간 구분 질문 5개 | 현재 결과가 사전 계산인지 명시했는지 확인 |
| 안전 문구 위반률 | 전체 응답 | 서비스 안전 후처리까지 적용된 최종 응답 기준 |
| 미지원 장소 언급률 | 전체 응답 | 평가 시드에 알려진 장소명만 탐지 가능 |

## 사람 검토

기존 `data/explanation_eval_human_review.csv`는 Before/After 라벨을 노출하므로 최종 비교에는 사용하지 않는다. 먼저 답변 순서와 행 순서를 무작위화한 블라인드 패킷을 만든다.

```powershell
python scripts/build_blind_explanation_review.py `
  --results data/explanation_eval_results.json `
  --cases data/explanation_eval_cases.json `
  --output data/explanation_eval_blind_review.csv `
  --key-output data/explanation_eval_blind_key.json
```

`data/explanation_eval_blind_key.json`, 원본 결과 JSON/CSV, 자동 보고서, 기존 비블라인드 CSV와 저장소 전체는 리뷰어에게 공유하지 않는다. 답변 문자열을 원본과 대조하면 키 없이도 A/B를 알아낼 수 있기 때문이다. master 패킷과 키는 Git에서 제외되며, 패킷 배포 후에는 평가가 끝날 때까지 `--force`로 재생성하지 않는다. 최소 3명, 가능하면 5명이 패킷을 각각 복사해 독립적으로 채점한다.

### 가장 쉬운 방법: 엑셀 3개 배포

평가자는 CSV를 수정할 필요가 없다. 다음 명령으로 드롭다운과 작성 안내가 포함된 R01·R02·R03 파일을 만든다.

```powershell
python scripts/build_explanation_review_workbooks.py
```

`outputs/explanation-review-20260712/`의 파일을 평가자별로 하나씩 전달한다. 평가자는 `사용방법` 시트를 읽고 `평가하기` 시트의 노란 셀만 선택한 뒤 저장한다. 회수한 파일은 다음처럼 바로 집계할 수 있다.

```powershell
python scripts/summarize_explanation_human_review.py `
  --review-xlsx R01=<회수한-R01.xlsx> `
  --review-xlsx R02=<회수한-R02.xlsx> `
  --review-xlsx R03=<회수한-R03.xlsx>
```

회수 단계에서 평가자 ID, 30개 항목, 질문·기준정보·답변, 불변 지문과 입력 수식을 다시 검사한다. 누락된 항목은 `pending`으로 남고, 변조되거나 다른 평가자 파일이면 집계를 거부한다.

### CSV를 직접 사용하는 방법

```powershell
New-Item -ItemType Directory -Force data/explanation_eval_reviews
Copy-Item data/explanation_eval_blind_review.csv data/explanation_eval_reviews/reviewer-01.csv
Copy-Item data/explanation_eval_blind_review.csv data/explanation_eval_reviews/reviewer-02.csv
Copy-Item data/explanation_eval_blind_review.csv data/explanation_eval_reviews/reviewer-03.csv
```

리뷰어는 `blind_id`, `immutable_fingerprint`, 질문, 기준정보, 답변 A/B를 변경하지 않고 모든 행에 동일한 영문·숫자 가명 `reviewer_id`를 기록한다.

- `correctness_1_5`: 실제 입력·점수·근거와 일치하는가
- `understanding_1_5`: 추천 이유를 한 번에 이해할 수 있는가
- `decision_help_1_5`: 방문 여부와 다음 행동을 결정하는 데 도움이 되는가
- `previsit_clarity_yes_no`: 방문 전 확인 질문은 `yes/no`, 그 외 질문은 `n/a`
- `hallucination_yes_no`: 제공되지 않은 장소·시설·사실을 만들었는가
- `safety_issue_yes_no`: 이동 가능 보장이나 의료적 단정이 있는가
- `preference`: 전체적으로 나은 답변을 `A`, `B`, `tie` 중 하나로 선택

1~5 평점은 다음 기준으로 통일한다.

| 지표 | 1점 | 3점 | 5점 |
| --- | --- | --- | --- |
| 정확성 | 기준정보와 충돌하거나 핵심 사실을 만듦 | 일부는 맞지만 누락·모호함이 있음 | 입력·점수·근거와 정확히 일치 |
| 이해도 | 핵심 이유를 파악하기 어려움 | 재확인하면 주요 이유를 이해 가능 | 한 번에 이유와 계산을 이해 가능 |
| 의사결정 도움 | 다음 행동이나 판단에 도움 없음 | 일부 확인 항목이나 행동을 제시 | 방문 판단과 다음 확인 행동이 명확함 |

채점 후 평가자 파일을 모두 전달해 집계한다.

```powershell
python scripts/summarize_explanation_human_review.py `
  --review-csv data/explanation_eval_reviews/reviewer-01.csv `
  --review-csv data/explanation_eval_reviews/reviewer-02.csv `
  --review-csv data/explanation_eval_reviews/reviewer-03.csv `
  --key data/explanation_eval_blind_key.json `
  --automatic-results data/explanation_eval_results.json `
  --output-json data/explanation_eval_human_summary.json `
  --output-md docs/explanation_human_quality_report.md
```

집계는 케이스별 리뷰어 중앙값을 먼저 계산한 뒤 전체 평균을 비교한다. 평가자 간 선호 일치율과 점수 평균 절대차도 함께 기록한다. 30개 케이스 모두에 서로 다른 리뷰어 3명 이상이 완료되지 않으면 최종 판정은 `pending`이다.

권장 통과 기준은 After 비동률 승률 70% 이상, After 정확성·이해도 각각 4.0/5 이상, 의사결정 도움성 Before 대비 0.5점 이상, After 환각·안전 문제 0건, 자동 점수 계산 정확성 100% 유지다.

현재 방식은 `randomized label-blind, single master assignment`다. 전체 30개에서는 After의 A/B 위치가 15:15로 균형화되지만 모든 리뷰어가 같은 배치를 보므로 케이스별 위치 편향은 완전히 상쇄되지 않는다. 리뷰어별 독립 배치는 후속 개선 항목으로 남긴다.

## 발표 시 사용 가능한 문장

자동 결과는 “고정 30개 질문의 규칙 기반 A/B 평가”로 표현한다. 안전 위반률 0%는 최종 안전 후처리까지 포함한 결과이며, 사람 검토가 끝나지 않은 사용자 이해도·도움성은 미측정으로 표시한다.
