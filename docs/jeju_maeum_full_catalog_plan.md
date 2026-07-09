# 제주의마음 여행 AI 전체 장소 카탈로그 계획

## 1. 목적

제주도 전체 여행지, 음식점, 카페, 숙박, 쇼핑, 문화시설, 교통 거점 등을 서비스에 넣으려면 접근성 검증 데이터와 원본 장소 데이터를 분리해야 한다.

모든 장소를 접근성 카드로 직접 만들면 운영이 불가능하다. 대신 전체 장소 카탈로그를 먼저 만들고, 그중 접근성 검증이 된 장소만 접근성 카드와 연결한다.

## 2. 데이터 레이어

### raw place catalog

제주 전체 장소 원본 데이터다.

예:

- 관광지
- 음식점
- 카페
- 숙박
- 쇼핑
- 문화시설
- 축제·행사
- 체험관광
- 교통 거점
- 공항, 병원, 약국 같은 지원 지점

이 레이어는 장소의 존재와 기본 정보만 의미한다. 접근 가능하다는 뜻이 아니다.

### accessibility place cards

접근성 검증이 된 장소 카드다.

예:

- 휠체어 접근성
- 장애인 화장실
- 주차
- 경사/계단
- 휴식 공간
- 대여 가능 여부
- 정보 확인일
- 안전 메모

### matching layer

원본 장소와 접근성 카드를 연결한다.

상태:

- `matched`: 접근성 카드와 확실히 연결됨
- `candidate`: 이름이나 지역이 비슷해 검수 후보
- `unmatched`: 아직 접근성 검증 없음
- `manual_review`: 사람이 확인해야 함

## 3. 추천 처리 원칙

전체 카탈로그에 있다고 해서 추천하면 안 된다.

추천 순서:

1. 사용자 조건을 분석한다.
2. 전체 카탈로그에서 장소 후보를 넓게 찾는다.
3. 접근성 카드와 연결된 장소를 우선한다.
4. 연결되지 않은 장소는 `needs_check` 또는 `정보 부족`으로 표시한다.
5. 음식 제한, 혼잡 민감, 날씨 민감 등 상황 규칙으로 제외/감점한다.
6. 최종 결과에는 출처와 확인 필요 항목을 표시한다.

## 4. 현재 구현 파일

스키마:

- `data/schemas/place_catalog.schema.json`

CSV 템플릿:

- `data/templates/place_catalog.template.csv`

샘플 변환 결과:

- `data/place_catalog.sample.json`

import/matching 코드:

- `src/catalog.py`
- `src/catalog_providers.py`
- `src/json_records.py`
- `src/roadview_data.py`
- `src/roadview_merge.py`

import CLI:

- `scripts/import_place_catalog.py`
- `scripts/import_place_catalog_json.py`
- `scripts/import_roadview_facility_cards.py`
- `scripts/import_roadview_metadata.py`
- `scripts/review_roadview_merge.py`
- `scripts/apply_roadview_safe_updates.py`
- `scripts/apply_roadview_conflict_resolutions.py`
- `scripts/apply_roadview_match_resolutions.py`
- `scripts/triage_roadview_new_candidates.py`
- `scripts/review_service_seed_cards.py`
- `scripts/build_service_seed_work_queue.py`

테스트:

- `tests/test_catalog.py`
- `tests/test_catalog_providers.py`
- `tests/test_json_records.py`
- `tests/test_roadview_data.py`
- `tests/test_roadview_merge.py`

## 5. 공공 데이터 후보

우선 활용할 데이터:

- 제주관광공사_비짓제주 관광정보 오픈 API
- 제주관광정보시스템(VISIT JEJU)_음식점콘텐츠
- 제주관광정보시스템(VISIT JEJU)_콘텐츠
- 제주데이터허브 음식점·관광 데이터
- 제주국제공항 공식 안내
- 열린관광 모두의 여행
- 이지제주 EASYJEJU
- 제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 관광지 현황
- 제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터
- 제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지
- 제주특별자치도_사회적약자 시설데이터 로드뷰 API

확인된 접근 조건:

- `제주관광공사_비짓제주 관광정보 오픈 API`
  - 관광지, 숙박시설, 음식점, 쇼핑, 문화시설, 축제·행사, 체험관광 등 전체 관광 콘텐츠를 JSON API로 제공한다.
  - 공공데이터포털 기준 수정일은 2026-06-23이고 업데이트 주기는 실시간이다.
  - 비짓제주 API 페이지 기준 API 키 신청과 승인이 필요하다.

- `제주관광정보시스템(VISIT JEJU)_음식점콘텐츠`
  - 공공데이터포털 기준 CSV 파일 데이터이며 전체 행은 2,884건이다.
  - 공공데이터포털 기준 수정일은 2026-03-11, 업데이트 주기는 연간, 차기 등록 예정일은 2027-03-31이다.
  - 로그인 없이 파일 다운로드가 가능하지만, 자동변환 Open API는 활용신청이 필요하다.

- `제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 관광지 현황`
  - 공공데이터포털 기준 제주도 내 107개 관광지 목록과 장애인 화장실 수, 장애인 주차장 수, 휠체어 대여 가능 여부, 수유실, 휴게실 정보를 제공한다.
  - CSV 파일 데이터이며 로그인 없이 다운로드 가능하다.
  - 공공데이터포털 기준 수정일은 2025-07-30이고, 업데이트 주기는 수시(1회성 데이터)다.
  - 이 데이터는 접근성 카드 초안과 기존 카드 보강에 사용한다.

- `제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터`
  - 로드뷰 이미지의 관광지명, 이미지 파일명, 촬영일자, 촬영시간, 위도, 경도, 해상도를 제공한다.
  - 전체 행은 4,748건이며 CSV 파일 데이터다.
  - 이 데이터는 접근성 카드 본문이 아니라 로드뷰 근거 이미지 연결용 보조 데이터로 사용한다.

- `제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지`
  - 107개 관광지 4,748장의 360도 로드뷰 이미지 데이터다.
  - 전체 용량은 약 23~25GB로 안내되어 있어 repository에 직접 저장하지 않는다.
  - 활용신청 후 전자매체로 별도 제공되는 데이터이므로 Object Storage에 저장하고 썸네일·메타데이터만 DB에 연결한다.

- `제주특별자치도_사회적약자 시설데이터 로드뷰 API`
  - JSON 형식 LINK API다.
  - 공공데이터포털 기준 비용 무료, 이용허락범위 제한 없음이다.
  - 실제 응답 구조는 제주도 제공 API 문서 확인 후 `scripts/import_place_catalog_json.py` 또는 별도 adapter로 연결한다.

주의:

- 음식점 콘텐츠는 기본 정보 중심이며 접근성 검증 데이터가 아니다.
- 연간 업데이트 데이터는 폐업, 이전, 임시휴업을 실시간 보장하지 않는다.
- 접근성 정보는 별도 출처로 보강해야 한다.
- 사회적약자 시설현황 데이터는 유용하지만 경사·단차·바닥·혼잡·현재 운영 여부를 보장하지 않으므로 자동 생성 카드는 기본적으로 `partial` 또는 `needs_check`로 시작한다.

## 6. 실제 import 명령

공공데이터포털 또는 비짓제주에서 받은 CSV/JSON/API 응답을 내부 카탈로그 JSON으로 변환한다.

원칙:

- 원본 API 응답은 `data/raw/` 아래에 날짜가 포함된 파일명으로 보존한다.
- API 키는 코드, 문서, 채팅에 적지 않는다.
- API 키는 환경변수로만 전달한다.
- import 산출물은 `place_catalog` JSON이고, 접근성 검증은 별도 카드와의 매칭 결과로만 판단한다.

예시:

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

음식점콘텐츠처럼 원본에 분류 컬럼이 없거나 음식점 전용 파일이면 기본 분류를 지정한다.

```powershell
python scripts/import_place_catalog.py `
  --input data/raw/visitjeju_restaurants.csv `
  --output data/place_catalog.restaurants.json `
  --source-name "제주관광공사" `
  --source-url "https://www.data.go.kr/data/15041984/fileData.do" `
  --dataset-name "제주관광정보시스템(VISIT JEJU)_음식점콘텐츠" `
  --license "이용허락범위 제한 없음" `
  --source-updated-at "2026-03-11" `
  --default-category restaurant `
  --accessibility-cards data/jeju_accessible_spots.json
```

비짓제주 API 승인 후 URL에서 직접 가져오는 예시:

```powershell
$env:VISIT_JEJU_API_KEY="발급받은 값을 로컬 환경변수로만 설정"

python scripts/import_place_catalog_json.py `
  --url "https://api.visitjeju.net/vsjApi/contents/searchlist" `
  --query "locale=kr" `
  --query "page=1" `
  --query "category=c1" `
  --api-key-env VISIT_JEJU_API_KEY `
  --api-key-param apiKey `
  --raw-output data/raw/visitjeju_places_20260707_page1.json `
  --output data/place_catalog.visitjeju_page1.json `
  --source-name "제주관광공사" `
  --source-url "https://www.data.go.kr/data/15076361/openapi.do" `
  --dataset-name "비짓제주 관광정보 오픈 API" `
  --license "이용허락범위 제한 없음" `
  --source-updated-at "2026-06-23" `
  --accessibility-cards data/jeju_accessible_spots.json
```

이미 다운로드한 JSON 응답을 import하는 예시:

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

API 응답 구조가 자동 감지되지 않으면 record 목록 위치를 직접 지정한다.

```powershell
python scripts/import_place_catalog_json.py `
  --input-json data/raw/example.json `
  --records-path response.body.items.item `
  --output data/place_catalog.example.json `
  --source-name "제주관광공사" `
  --source-url "https://www.data.go.kr/data/15076361/openapi.do" `
  --dataset-name "비짓제주 관광정보 오픈 API"
```

사회적약자 시설현황 CSV를 접근성 카드 초안과 raw catalog로 변환하는 예시:

```powershell
python scripts/import_roadview_facility_cards.py `
  --input data/raw/jeju_roadview_facility_status_20250730.csv `
  --output-cards data/roadview_accessibility_cards.draft.json `
  --output-catalog data/place_catalog.roadview_facility.json `
  --accessibility-cards data/jeju_accessible_spots.json `
  --checked-at 2026-07-07
```

로드뷰 이미지 메타데이터 CSV를 보조 JSON으로 변환하는 예시:

```powershell
python scripts/import_roadview_metadata.py `
  --input data/raw/jeju_roadview_image_metadata_20250730.csv `
  --output data/roadview_image_metadata.json
```

roadview 접근성 카드 초안과 기존 43개 접근성 카드를 비교하는 예시:

```powershell
python scripts/review_roadview_merge.py `
  --existing data/jeju_accessible_spots.json `
  --draft data/roadview_accessibility_cards.draft.json `
  --output data/roadview_merge_report.json `
  --generated-at 2026-07-07
```

병합 검수 리포트 분류:

- `matched_existing`: 기존 카드와 이름이 확실히 일치하는 초안
- `field_updates_available`: 기존 카드의 `unknown`, `needs_check`, `partial` 필드를 roadview 초안 값으로 보강할 수 있는 후보
- `new_candidate`: 기존 카드와 충분히 일치하지 않는 신규 장소 후보
- `needs_manual_review`: 이름이 애매하게 비슷하거나 기존 카드와 roadview 초안의 `yes/no` 값이 충돌하는 항목

리포트만으로는 실제 병합을 수행하지 않는다. 자동 반영은 보수적으로 별도 apply 단계를 사용한다.

```powershell
python scripts/apply_roadview_safe_updates.py `
  --existing data/jeju_accessible_spots.json `
  --report data/roadview_merge_report.json `
  --output data/jeju_accessible_spots.roadview_safe_merged.json `
  --manual-review-output data/roadview_manual_review_queue.json `
  --apply-report-output data/roadview_apply_report.json `
  --applied-at 2026-07-07
```

자동 반영 조건:

- 기존 카드와 확정 매칭되어야 한다.
- `field_conflicts`가 없어야 한다.
- 기존 필드가 `unknown`, `needs_check`, `partial` 또는 비어 있어야 한다.
- roadview 초안 값이 `yes`인 경우만 반영한다.
- `no` 값은 시설 미보유와 데이터 누락을 구분하기 어려우므로 수동 검수 큐로 넘긴다.

충돌 항목은 운영자가 `data/roadview_conflict_resolutions.json`에 판단을 남긴 뒤 아래 명령으로 카드 운영 메모와 오픈 검수 큐에 반영한다.

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

불확실 매칭은 `data/roadview_match_resolutions.json`에 동일 장소, 같은 접근성 범위, 하위 지점 포함 여부를 판단한 뒤 아래 명령으로 반영한다.

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

신규 후보는 바로 기준 카드에 병합하지 않고 서비스 시드 후보, 카탈로그 후보, 현장검수 우선 후보로 분류한다.

```powershell
python scripts/triage_roadview_new_candidates.py `
  --queue data/roadview_manual_review_queue.json `
  --draft data/roadview_accessibility_cards.draft.json `
  --output data/roadview_new_candidate_triage.json `
  --seed-output data/roadview_service_seed_cards.review.json `
  --generated-at 2026-07-08
```

서비스 시드 후보는 `status=hidden` 상태의 검수용 카드로 생성한다. 공개 전 공식 상세 출처, 로드뷰 이미지, 경사·단차·바닥 상태 검수를 거쳐야 한다.

서비스 시드 후보 공개 전 검수 리포트:

```powershell
python scripts/review_service_seed_cards.py `
  --seed-cards data/roadview_service_seed_cards.review.json `
  --image-metadata data/roadview_image_metadata.json `
  --output data/roadview_service_seed_review.json `
  --generated-at 2026-07-08
```

공개 전 실제 운영 작업 큐:

```powershell
python scripts/build_service_seed_work_queue.py `
  --review data/roadview_service_seed_review.json `
  --output data/roadview_service_seed_work_queue.json `
  --generated-at 2026-07-08
```

큐 우선순위는 `official_source_review`, `roadview_image_review`를 high로 처리하고, `crowd_policy_review`, `category_refinement`를 medium으로 처리한다.

시설현황 CSV 매핑:

- `SEQ` → 원본 순번과 접근성 카드 ID 번호
- `TOURIST_NM` → 장소명
- `TOURIST_EN` → 영문 장소명
- `TOURIST_ADDR` → 주소와 지역 추론
- `TOURIST_TEL` → 전화번호
- `TOURIST_DTOIL` → 장애인 화장실 보유 수
- `TOURIST_DPARK` → 장애인 주차장 보유 수
- `TOURIST_LNET` → 휠체어 대여 가능 여부
- `TOURIST_NURSING` → 수유실 보유 여부
- `TOURIST_REST` → 휴게실 보유 여부

자동 생성 접근성 카드의 보수적 처리:

- 장애인 화장실 수가 1 이상이면 `accessible_toilet.state = yes`
- 장애인 주차장 수가 1 이상이면 `parking.state = yes`
- 휠체어 대여가 `Y`이면 `rental_or_assistance.state = yes`
- 휴게실이 `Y`이면 `rest_area.state = yes`
- 경사·계단, 바닥 상태, 혼잡도는 자동으로 확정하지 않고 `needs_check` 또는 `unknown` 처리
- 전체 카드 상태는 `partial` 또는 `needs_check`로 시작

현재 importer가 인식하는 대표 원본 컬럼:

- 이름: `콘텐츠명`, `상호명`, `업소명`, `관광지명`, `시설명`, `name`, `title`
- 원본 ID: `콘텐츠아이디`, `contentsid`, `contentid`, `id`
- 분류: `콘텐츠분류`, `카테고리`, `분류`, `업종`, `유형`, `category`, `contentscd.label`
- 주소: `주소`, `도로명주소`, `지번주소`, `소재지`, `address`, `roadaddress`, `jibunaddress`
- 연락처: `전화번호`, `연락처`, `문의전화`, `tel`, `phone`, `phoneno`
- 좌표: `위도`, `경도`, `latitude`, `longitude`, `mapy`, `mapx`
- 설명·태그: `소개`, `상세설명`, `키워드`, `태그`, `alltag`, `대표메뉴기타`
- 사회적약자 시설현황: `TOURIST_NM`, `TOURIST_ADDR`, `TOURIST_TEL`, `TOURIST_DTOIL`, `TOURIST_DPARK`, `TOURIST_LNET`, `TOURIST_NURSING`, `TOURIST_REST`

CSV import 결과는 모든 장소를 `place_catalog`로 넣되, 접근성 카드와 연결된 장소만 `matched`로 표시한다. 연결되지 않은 장소는 추천 결과에서 정보 부족 또는 확인 필요로 다뤄야 한다.

## 7. 운영 기준

전체 장소 카탈로그는 수천 개가 될 수 있다.

운영 기준:

- 원본 출처와 업데이트일을 반드시 저장한다.
- 같은 장소 중복을 이름, 주소, 전화번호로 병합한다.
- 접근성 카드와 자동 매칭하되 확신이 낮으면 `candidate`로 둔다.
- `unmatched` 장소는 추천 결과에서 정보 부족으로 표시한다.
- 음식점과 카페는 음식 제한 상황에서 제외/감점 가능해야 한다.
- 의료지원 지점은 위치 확인용이지 의료 판단용이 아니다.

## 8. 다음 작업

실제 대량 데이터 import 단계:

1. 공공데이터포털 CSV 다운로드 또는 VISIT JEJU API 키 확보
2. 관광지, 음식점, 숙박, 쇼핑 CSV 또는 API 응답 저장
3. CSV는 `scripts/import_place_catalog.py`, JSON/API는 `scripts/import_place_catalog_json.py`로 카탈로그 생성
4. 접근성 카드와 자동 매칭
5. `candidate`, `unmatched` 목록을 운영자 검수 큐로 분리
6. `unmatched` 장소를 추천 결과에 노출할 때 정보 부족 문구와 출처를 함께 표시
