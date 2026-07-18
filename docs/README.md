# 가치봄 제주 여행 AI 문서 안내

이 폴더는 가치봄 제주 여행 AI를 서비스로 만들기 위한 기준 문서 모음이다.

읽는 순서:

1. `jeju_maeum_integrated_commercialization_plan.md`
   - 새 상용화 기획안과 기존 실행 기준을 통합한 최종 기준 문서

2. `rag_service_enhancement_phase_spec.md`
   - 자연어 질의, 검색, 접근성 재정렬, 공식 근거 인용, RAG 평가의 구현 기준

3. `jeju_maeum_travel_support_phase_spec.md`
   - 충전기, 종합병원급 이상·약국, 이동지원센터 연계, 관광 복지서비스의 단계별 구현 명세

4. `jeju_maeum_service_foundation.md`
   - 서비스 원칙, 경계, 신뢰도, 개인정보, 운영 기준

5. `jeju_maeum_service_plan.md`
   - 서비스화 방향, 출시 범위, 운영 계획, 로드맵

6. `jeju_maeum_mvp_plan.md`
   - 1차 서비스 화면과 기능 흐름

7. `jeju_maeum_app_basic_structure.md`
   - 앱 입력, 추천 결과, 데이터 공개 게이트, 화면 상태 구조

8. `jeju_maeum_app_recommendation_screen.html`
   - 첫 추천 화면 정적 시안

9. `jeju_maeum_scoring_policy.md`
   - 적합도 점수, 강제 감점, 차단 규칙

10. `jeju_maeum_launch_checklist.md`
   - 출시 전 검수 기준과 출시 보류 조건

11. `jeju_maeum_data_collection_guide.md`
   - 장소 카드 수집, 검수, 상태 판단 기준

12. `jeju_maeum_situation_recommendation_policy.md`
   - 음식 제한, 혼잡 민감, 체력 저하, 날씨 민감 등 상황별 제외·감점 기준

13. `jeju_maeum_full_catalog_plan.md`
   - 제주 전체 장소 카탈로그와 접근성 카드 연결 구조

14. `jeju_maeum_color_swatch_revised.png`
   - 브랜드 컬러 팔레트 이미지

관련 데이터:

- `../data/jeju_accessible_spots.json`
- `../data/place_catalog.sample.json`
- `../data/schemas/place_catalog.schema.json`
- `../data/schemas/accessibility_place_card.schema.json`
- `../data/schemas/recommendation_result.schema.json`
- `../data/schemas/recommendation_case_validation_report.schema.json`
- `../data/place_location_overrides.json`
- `../data/schemas/place_location_overrides.schema.json`
- `../data/schemas/roadview_image_metadata.schema.json`
- `../data/schemas/roadview_merge_report.schema.json`
- `../data/schemas/roadview_apply_report.schema.json`
- `../data/schemas/roadview_manual_review_queue.schema.json`
- `../data/schemas/roadview_conflict_resolutions.schema.json`
- `../data/schemas/roadview_resolution_apply_report.schema.json`
- `../data/schemas/roadview_match_resolutions.schema.json`
- `../data/schemas/roadview_match_resolution_apply_report.schema.json`
- `../data/schemas/roadview_new_candidate_triage.schema.json`
- `../data/schemas/roadview_service_seed_review.schema.json`
- `../data/schemas/roadview_service_seed_work_queue.schema.json`
- `../data/templates/place_catalog.template.csv`
- `../data/templates/accessibility_place_cards.template.json`
- `../data/templates/roadview_facility_status.template.csv`
- `../data/templates/roadview_image_metadata.template.csv`
- `../data/safety_rules.json`
- `../data/situation_rules.json`
- `../data/test_inputs.json`

관련 코드:

- `../web/index.html`
  - 실제 추천 데이터 파일을 읽는 정적 앱 첫 화면

- `../web/data/app_recommendation_seed.json`
  - 앱 화면이 읽는 추천 시드 데이터. 추천 노출 장소의 `location` 좌표를 포함

- `../web/assets/jeju-final-map-panel-cardless.png`
  - 확정 시안 기반 중앙 지도 배경. 시안 원본에서 추천 장소 카드 4개와 데모 경로선을 제거하고, 추천 카드·위치 핀·동선은 앱에서 데이터 기반으로 별도 렌더링

- `../web/assets/jeju-final-map-panel-cardless-source.png`
  - 카드와 데모 경로선 제거 지도 배경의 고해상도 편집 원본. 앱 자산은 이 파일을 816x931로 리사이즈해 생성

- `../data/recommendation_case_validation_report.json`
  - 회복 중, 음식 제한, 휠체어, 아이 동반, 날씨 민감 추천 검증 결과

- `../web/data/recommendation_case_validation_report.json`
  - 앱 우측 검수 근거 영역에서 읽는 상황별 검증 결과 사본

- `../web/data/operations_readiness_report.json`
  - 앱 좌측 서비스 공개 게이트에서 읽는 운영 준비도 결과 사본

- `../data/service_preflight_report.json`
  - 환경 설정, 앱용 데이터, 공개 게이트, 비밀값 노출 여부를 확인하는 서비스 실행 전 사전점검 결과

- `../src/recommendation_api.py`
  - 추천 API 서버 핸들러. `/api/health`, `/api/recommendations`, 구조화된 오류 응답, 요청 본문 제한을 담당

- `../src/place_locations.py`
  - 로드뷰 이미지 메타데이터와 수동 보강 파일을 결합해 추천 장소 위도·경도 인덱스를 생성

- `service_preflight_report_20260709.md`
  - 운영자가 읽기 쉬운 서비스 사전점검 요약 문서

- `recommendation_case_validation_report_20260709.md`
  - 상황별 추천 방향, 제외 기준, 감점 근거, 방문 전 확인 항목을 팀 검토용 표로 정리한 문서

- `../src/app_recommendations.py`
  - 앱 화면용 추천 시드 데이터 생성 로직

- `../scripts/build_app_recommendation_seed.py`
  - 앱 추천 시드 데이터 생성 명령

- `../scripts/build_clean_map_background.py`
  - 확정 시안 원본에서 추천 장소 카드 4개만 제거한 중앙 지도 배경을 생성하는 명령

- `../src/recommendation_case_validation.py`
  - 상황별 추천 결과를 검증표로 판정하고 팀 검토용 Markdown을 생성

- `../scripts/build_recommendation_case_validation_report.py`
  - 상황별 추천 검증 JSON과 Markdown 생성 명령

- `../scripts/build_operations_readiness_report.py`
  - 상용 공개 전 운영 준비도 JSON 생성 명령. 앱 표시용 `web/data` 사본도 생성 가능

- `../scripts/build_service_preflight_report.py`
  - 서비스 실행 전 사전점검 JSON과 Markdown 생성 명령

- `../src/scoring.py`
  - 장소별 적합도 점수, 등급, 감점 이유, 확인사항 계산

- `../src/catalog.py`
  - 전체 장소 카탈로그 CSV import, 접근성 카드 자동 매칭

- `../src/catalog_providers.py`
  - 공공데이터/VISIT JEJU CSV 헤더를 내부 장소 카탈로그 형식으로 정규화

- `../src/json_records.py`
  - 공공 API JSON 응답에서 record 목록을 추출하고 중첩 필드를 평탄화

- `../src/roadview_data.py`
  - 제주특별자치도 사회적약자 시설현황과 로드뷰 이미지 메타데이터 변환

- `../src/roadview_merge.py`
  - roadview 접근성 카드 초안과 기존 접근성 카드의 병합 검수 리포트 생성 및 보수적 자동 반영

- `../scripts/import_place_catalog.py`
  - 실제 공공데이터 CSV를 `place_catalog` JSON으로 변환하는 CLI

- `../scripts/import_place_catalog_json.py`
  - 다운로드한 JSON 또는 API URL 응답을 `place_catalog` JSON으로 변환하는 CLI

- `../scripts/import_roadview_facility_cards.py`
  - 107개 관광지 사회적약자 시설현황 CSV를 접근성 카드 초안과 카탈로그로 변환하는 CLI

- `../scripts/import_roadview_metadata.py`
  - 4,748건 로드뷰 이미지 메타데이터 CSV를 보조 JSON으로 변환하는 CLI

- `../scripts/review_roadview_merge.py`
  - roadview 접근성 카드 초안을 기존 카드와 비교해 매칭·신규·수동검수·보강가능 항목으로 분류

- `../scripts/apply_roadview_safe_updates.py`
  - 충돌 없는 `yes` 근거만 기존 접근성 카드에 반영하고 신규·충돌·`no` 근거는 수동 검수 큐로 분리

- `../scripts/apply_roadview_conflict_resolutions.py`
  - 운영자가 확정한 roadview 충돌 해소 판단을 카드 운영 메모와 오픈 검수 큐에 반영

- `../scripts/apply_roadview_match_resolutions.py`
  - 운영자가 확정한 roadview 불확실 매칭 판단을 카드 운영 메모와 오픈 검수 큐에 반영

- `../scripts/triage_roadview_new_candidates.py`
  - roadview 신규 후보를 서비스 시드 후보, 카탈로그 후보, 현장검수 우선 후보로 분류

- `../scripts/review_service_seed_cards.py`
  - 서비스 시드 후보의 공개 전 차단 사유, 로드뷰 이미지 메타데이터, 공식 출처 검색 키를 생성

- `../scripts/build_service_seed_work_queue.py`
  - 서비스 시드 후보 공개 전 검수 리포트에서 공식 출처, 로드뷰 이미지, 혼잡도, 카테고리 보정 작업 큐를 생성

- `../tests/test_scoring.py`
  - 장소 카드 스키마, 추천 결과 스키마, 주요 점수화 규칙 테스트

- `../tests/test_recommendation_case_validation.py`
  - 상황별 추천 검증표 스키마, 제외 기준, 아이 동반·음식 제한·날씨 민감 정책 테스트

- `../tests/test_recommendation_api.py`
  - 추천 API health, 추천 응답 스키마, 잘못된 요청, 과대 본문, 내부 예외 비노출 계약 테스트

- `../tests/test_place_locations.py`
  - 로드뷰 좌표 중심값, 수동 좌표 보강, 현재 추천 경로 좌표 커버리지 테스트

- `../tests/test_catalog.py`
  - 전체 장소 카탈로그 스키마와 매칭 로직 테스트

- `../tests/test_catalog_providers.py`
  - 한국어 공공데이터 헤더 정규화와 import CLI 테스트

- `../tests/test_json_records.py`
  - 공공 API JSON record 추출, 중첩 필드 평탄화, JSON import CLI 테스트

- `../tests/test_roadview_data.py`
  - 사회적약자 시설현황 카드 초안 생성, 로드뷰 메타데이터 변환, CLI 테스트

- `../tests/test_roadview_merge.py`
  - roadview 초안과 기존 접근성 카드 병합 검수 리포트 테스트

테스트 실행:

```powershell
python -m unittest discover -s tests -v
```

다음 작업은 실제 공공데이터 CSV 또는 VISIT JEJU API 응답을 `place_catalog` 형식으로 import하는 것이다.

공공데이터 CSV import 예시:

```powershell
python scripts/import_place_catalog.py `
  --input data/raw/visitjeju_places.csv `
  --output data/place_catalog.imported.json `
  --source-name "제주관광공사" `
  --source-url "https://www.data.go.kr/data/15076361/openapi.do" `
  --dataset-name "비짓제주 관광정보 오픈 API" `
  --license "이용허락범위 제한 없음" `
  --source-updated-at "2026-06-23" `
  --accessibility-cards data/jeju_accessible_spots.json
```

공공 API JSON import 예시:

```powershell
python scripts/import_place_catalog_json.py `
  --input-json data/raw/visitjeju_places_20260707_page1.json `
  --output data/place_catalog.visitjeju_page1.json `
  --source-name "제주관광공사" `
  --source-url "https://www.data.go.kr/data/15076361/openapi.do" `
  --dataset-name "비짓제주 관광정보 오픈 API" `
  --license "이용허락범위 제한 없음" `
  --source-updated-at "2026-06-23" `
  --accessibility-cards data/jeju_accessible_spots.json
```

사회적약자 시설현황 CSV import 예시:

```powershell
python scripts/import_roadview_facility_cards.py `
  --input data/raw/jeju_roadview_facility_status_20250730.csv `
  --output-cards data/roadview_accessibility_cards.draft.json `
  --output-catalog data/place_catalog.roadview_facility.json `
  --accessibility-cards data/jeju_accessible_spots.json `
  --checked-at 2026-07-07
```

로드뷰 이미지 메타데이터 import 예시:

```powershell
python scripts/import_roadview_metadata.py `
  --input data/raw/jeju_roadview_image_metadata_20250730.csv `
  --output data/roadview_image_metadata.json
```

roadview 접근성 카드 초안 병합 검수 리포트 예시:

```powershell
python scripts/review_roadview_merge.py `
  --existing data/jeju_accessible_spots.json `
  --draft data/roadview_accessibility_cards.draft.json `
  --output data/roadview_merge_report.json `
  --generated-at 2026-07-07
```

roadview 병합 리포트의 보수적 자동 반영 예시:

```powershell
python scripts/apply_roadview_safe_updates.py `
  --existing data/jeju_accessible_spots.json `
  --report data/roadview_merge_report.json `
  --output data/jeju_accessible_spots.roadview_safe_merged.json `
  --manual-review-output data/roadview_manual_review_queue.json `
  --apply-report-output data/roadview_apply_report.json `
  --applied-at 2026-07-07
```

자동 반영은 확정 매칭, 충돌 없음, 기존 필드가 `unknown`/`needs_check`/`partial`, roadview 초안 값이 `yes`인 경우로 제한한다. `no` 값은 시설 미보유와 데이터 누락을 구분하기 어려우므로 수동 검수 큐로 보낸다.

roadview 충돌 해소 판단 반영 예시:

```powershell
python scripts/apply_roadview_conflict_resolutions.py `
  --existing data/jeju_accessible_spots.json `
  --manual-review data/roadview_manual_review_queue.json `
  --resolutions data/roadview_conflict_resolutions.json `
  --output data/jeju_accessible_spots.conflict_resolved.json `
  --open-manual-review-output data/roadview_manual_review_queue.open.json `
  --apply-report-output data/roadview_conflict_resolution_apply_report.json `
  --applied-at 2026-07-07
```

roadview 불확실 매칭 해소 판단 반영 예시:

```powershell
python scripts/apply_roadview_match_resolutions.py `
  --existing data/jeju_accessible_spots.json `
  --manual-review data/roadview_manual_review_queue.json `
  --resolutions data/roadview_match_resolutions.json `
  --output data/jeju_accessible_spots.match_resolved.json `
  --open-manual-review-output data/roadview_manual_review_queue.match_open.json `
  --apply-report-output data/roadview_match_resolution_apply_report.json `
  --applied-at 2026-07-08
```

roadview 신규 후보 triage 예시:

```powershell
python scripts/triage_roadview_new_candidates.py `
  --queue data/roadview_manual_review_queue.json `
  --draft data/roadview_accessibility_cards.draft.json `
  --output data/roadview_new_candidate_triage.json `
  --seed-output data/roadview_service_seed_cards.review.json `
  --generated-at 2026-07-08
```

`roadview_service_seed_cards.review.json`은 공개 카드가 아니라 검수용 시드 파일이다. 서비스 공개 전 공식 상세 출처 또는 로드뷰 이미지 검수를 거쳐 `status`와 필드 신뢰도를 다시 판단한다.

서비스 시드 후보 공개 전 검수 리포트 예시:

```powershell
python scripts/review_service_seed_cards.py `
  --seed-cards data/roadview_service_seed_cards.review.json `
  --image-metadata data/roadview_image_metadata.json `
  --output data/roadview_service_seed_review.json `
  --generated-at 2026-07-08
```

서비스 시드 후보 운영 작업 큐 생성 예시:

```powershell
python scripts/build_service_seed_work_queue.py `
  --review data/roadview_service_seed_review.json `
  --output data/roadview_service_seed_work_queue.json `
  --generated-at 2026-07-08
```

작업 큐는 `official_source_review`와 `roadview_image_review`를 high 우선순위로 둔다. 두 작업이 끝나기 전에는 `status=hidden`을 유지한다.
