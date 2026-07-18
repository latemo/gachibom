# 가치봄 제주 RAG 서비스 고도화 명세

- 문서 상태: 구현 기준
- 기준일: 2026-07-14
- 적용 브랜치: `codex/rag-service-enhancement`
- 연계 문서: `jeju_maeum_travel_support_phase_spec.md`

## 1. 목표

기존의 `전체 장소 규칙 점수화 + 선택적 LLM 설명` 구조를 다음의 근거 기반 흐름으로 고도화한다.

```text
자연어 여행 요청
→ 제한된 QueryIntent 구조화
→ 검증 장소 Top-K 검색
→ 기존 접근성·안전 점수 재정렬
→ 출처 URL·확인일·검증 상태 묶음
→ 선택적 LLM 설명
→ 서버가 검증한 인용만 공개
```

벡터 데이터베이스 자체를 목표로 삼지 않는다. 현재 91개 정형 장소 카드에는 구조화 필터와 한국어 lexical 검색이 우선이며, 데이터와 평가셋이 커졌을 때 임베딩 검색을 추가한다.

## 2. 기존 상태와 변경 후 상태

| 구분 | 기존 | RAG Core 적용 후 |
|---|---|---|
| 입력 | 고정 프로필 선택 | 고정 프로필 + 선택적 자연어 요청 |
| 검색 | 모든 장소 전수 점수화 | 자연어가 있을 때 검증 장소 Top-K 검색 |
| 재정렬 | 접근성 규칙 점수 | 기존 접근성 규칙 점수를 그대로 최종 판정자로 사용 |
| 근거 | 장소별 요약 문자열 | 출처 URL, 정보 확인일, 검증 상태, 안정적 근거 ID |
| 생성 | 점수 결과를 LLM에 전달 | 검색 근거를 함께 전달하고 허용된 근거 ID만 인용 |
| 데이터 부족 | 관련성이 낮은 장소가 노출될 가능성 | 지원서비스 corpus가 없으면 추천 보류 |
| 기본 화면 | 정적 시드 | 정적 시드 유지, 자연어 요청 시 런타임 RAG 활성화 |

## 3. 공개 요청 계약

`POST /api/recommendations`

```json
{
  "query": "제주시에서 휠체어로 이용할 조용한 실내 문화 공간",
  "traveler_summary": {
    "traveler_type": ["wheelchair_user"],
    "mobility_conditions": ["짧은 이동"],
    "preferred_themes": ["실내", "문화"],
    "required_accessibility": ["장애인 화장실"],
    "avoid": ["계단", "혼잡"]
  },
  "limit": 4,
  "use_ai": true
}
```

규칙:

- `query`는 선택 항목이다.
- 공백 또는 생략 시 기존 추천 순서와 점수 흐름을 유지한다.
- 최대 2,000바이트까지만 API가 받고, 파서는 공백·제어문자를 정리한 최대 500자만 일시적으로 사용한다.
- 원문 질의는 응답, 로그, 저장 코스, 공유 링크에 남기지 않는다.
- 알 수 없는 프로필 필드와 별도 진단 정보는 QueryIntent로 승격하지 않는다.

## 4. QueryIntent 계약

내부 파서 `parse_query_intent()`는 다음 제한된 구조를 만든다.

```json
{
  "intent": "place_search",
  "query_text": "제주시에서 휠체어로 이용할 조용한 실내 문화 공간",
  "regions": ["제주시"],
  "categories": ["indoor", "culture"],
  "resource_types": [],
  "traveler_summary": {
    "traveler_type": ["wheelchair_user"],
    "mobility_conditions": [],
    "preferred_themes": ["실내", "문화", "휴식"],
    "required_accessibility": ["휠체어 접근"],
    "avoid": []
  },
  "signals": {
    "emergency": false,
    "charging": false
  }
}
```

`traveler_summary.required_accessibility`는 최종 점수와 안전 판정에 사용한다. 검색기의 hard filter로 그대로 복제하지 않는다. 검색 hard filter는 현재 지역·카테고리처럼 확신도가 높은 조건만 사용한다.

## 5. 검색과 재정렬

### 5.1 검색 후보 게이트

다음 장소는 검색 전에 제외한다.

- `status != active`
- `verification.status == unavailable`
- `visit_info.service_status`가 임시 또는 영구 폐업

### 5.2 검색 점수

초기 구현은 외부 의존성 없는 결정론적 검색기다.

- 한국어 토큰 BM25
- 장소명·지역·설명·접근성 메모 field match
- 지역·카테고리 구조화 조건
- 질의의 접근성 표현과 카드 상태 대조
- 검증 상태와 출처 URL 신뢰도
- 기준일 대비 최신성
- 입력 순서와 무관한 안정적 tie-break
- 내용 일치 점수가 0인 후보는 신뢰도 점수만으로 검색 결과에 진입할 수 없음

검색기는 기본 12개 후보를 만들고, 기존 `rank_places()`가 접근성·안전 점수로 최대 4개를 최종 선택한다.

### 5.3 실패 안전

- 검색 결과가 0개면 전체 장소로 fallback하지 않는다.
- `power_wheelchair_fast_charger`, `hospital`, `pharmacy`, `mobility_support_center`, `tourism_welfare_service`는 별도 공식 지원서비스 corpus가 구축되기 전까지 `resource_data_gap`으로 보류한다.
- 응급 요청은 의료 판단이나 대체 장소 추천으로 전환하지 않는다.
- 데이터 부족 응답은 관련 없는 관광지를 보여 주지 않는다.

## 6. 근거와 인용

각 최종 장소의 검색 근거에는 다음 정보가 포함된다.

```json
{
  "evidence_id": "ev_0123456789abcdef",
  "title": "공식 장소 정보",
  "url": "https://example.go.kr/place",
  "type": "public_agency",
  "checked_at": "2026-07-07",
  "status": "partial"
}
```

규칙:

- `evidence_id`는 장소 ID, 출처 순번, 검증된 URL 문자열을 해시해 서버가 결정적으로 만든다.
- LLM에는 허용 근거 목록을 전달한다.
- 모델은 근거 ID만 반환한다.
- 서버는 허용 목록에 없는 ID와 모델이 만든 URL을 제거한다.
- 공개 인용 URL·확인일·검증 상태는 항상 서버의 근거 인덱스에서 다시 결합한다.
- AI가 꺼져 있어도 검색 근거 링크는 `retrieval.matches`를 통해 화면에 표시한다.

## 7. 공개 응답 상태

| 상태 | 의미 | 화면 동작 |
|---|---|---|
| `not_requested` | 자연어 질의 없음 | 기존 정적/규칙 추천 유지 |
| `applied` | 검색 후보를 점수 재정렬함 | 장소와 공식 근거 표시 |
| `no_match` | 검증 corpus에서 관련 근거 없음 | 추천 보류 |
| `resource_data_gap` | 지원서비스 corpus 미구축 | 관련 없는 장소를 대체 노출하지 않음 |

응답에는 원문 질의를 제외한 `query_intent`, 최종 장소의 검색 점수·이유, 안전한 trace, 근거 묶음이 포함된다. trace에는 원문 토큰이나 intent 값 대신 개수와 적용 필터 코드만 남긴다.

## 8. Phase 계획

### Phase R0 — RAG Core

- QueryIntent 파서
- BM25 + 구조화 검색
- 기존 안전 점수 재정렬
- 검색 근거와 서버 검증 인용
- 자연어 입력 UI
- 데이터 부족 fail-closed

완료 조건:

- 질의 생략 시 기존 추천 결과가 변하지 않는다.
- 관련 질의에서 기대 장소가 Top-K와 최종 결과에 포함된다.
- 가짜 근거 ID와 비허용 URL이 공개되지 않는다.
- 지원서비스 데이터가 없을 때 관광지 fallback이 없다.

### Phase R1 — 공식 지원서비스 corpus

`jeju_maeum_travel_support_phase_spec.md`의 다섯 도메인을 독립 데이터셋과 검수 계약으로 연결한다.

1. 전동휠체어 급속충전기
2. 종합병원급 이상 의료기관과 운영 약국
3. 관광약자 콜택시 연계
4. 교통약자 이동지원센터
5. 관광 관련 복지서비스

완료 전에는 R0의 `resource_data_gap` 상태를 유지한다.

### Phase R2 — Hybrid Retrieval

- 공식 문서 단락 chunking
- 한국어 임베딩 검색
- 구조화 필터 + BM25 + vector RRF
- 장소/지원서비스별 reranker
- 필드 단위 source_ref 연결

도입 조건:

- 문서·서비스 레코드가 500개 이상이거나 lexical 검색의 recall이 목표 미달
- 고정 평가셋에서 임베딩 추가가 실제로 개선됨
- 운영 비용과 지연 시간 예산 충족

### Phase R3 — 운영 자동화

- 공식 API/파일 정기 수집
- TTL 만료와 상태 강등
- 변경 탐지 및 수동 검수 큐
- 검색 적중률·인용 정확도·무근거 문장률 모니터링
- 개인정보와 모델 전송 경계 고지

## 9. 평가 기준

기존의 코드 작성형 무RAG fixture 비교를 실제 RAG 품질 증거로 사용하지 않는다. 다음 고정 평가셋으로 같은 질문을 비교한다.

| 지표 | 목표 |
|---|---:|
| Recall@12 | 0.90 이상 |
| 최종 장소 적합 Top-4 | 0.85 이상 |
| 인용 ID 유효률 | 1.00 |
| 출처 URL 서버 결합률 | 1.00 |
| 무근거 장소·시설 주장률 | 0.00 |
| 지원서비스 데이터 부족 fail-closed | 1.00 |
| p95 검색 지연 | 200ms 이하 |

평가 케이스에는 정상 장소 검색, 지역·접근성 조합, 회피 조건, 무관 질의, 충전기·병원·콜택시 데이터 부족, 긴 입력, 개인정보 형태 입력을 포함한다.

## 10. 구현 파일

- `src/rag_query.py`: 자연어 QueryIntent 구조화
- `src/rag_retrieval.py`: 결정론적 Top-K 검색과 근거 묶음
- `src/recommendation_service.py`: 검색 → 점수 재정렬 → 인용 통합
- `src/recommendation_api.py`: 로컬 API query 계약
- `src/vercel_api.py`: 배포 API query 계약
- `web/index.html`, `web/app.js`, `web/styles.css`: 자연어 입력과 근거 표시
- `tests/test_rag_query.py`
- `tests/test_rag_retrieval.py`
- `tests/test_recommendation_service.py`
- `tests/test_recommendation_api.py`
- `tests/test_saved_trips_frontend.py`
