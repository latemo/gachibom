# 제주의마음 앱 뼈대

이 폴더는 실제 서비스 전환을 위한 첫 추천 화면이다. 정적 seed만으로도 열리지만, 추천 API 서버를 같이 실행하면 상세 조건을 서버 점수 엔진으로 다시 계산하고 `마음동행 AI` 설명을 보강한다.

## 서비스 실행 기준

실제 서비스 흐름 확인은 추천 API 서버를 기준으로 한다. 이번 경로 프록시 포함 검증은 `8792`에서 수행했다. `8780`은 정적 화면 미리보기 전용이다.

## 추천 API 포함 실행

```powershell
$env:OPENAI_API_KEY="발급받은 키"
$env:OPENAI_MODEL="gpt-5-mini"
python scripts/serve_recommendation_api.py --port 8790 --generated-at 2026-07-09
```

브라우저에서 실행한 포트 주소를 연다. 예: `http://127.0.0.1:8792/`

`OPENAI_API_KEY`가 없으면 API는 정상 동작하되 AI 설명만 생략하고 로컬 점수 근거를 사용한다. 화면에는 API 연결, AI 키 없음, 실패 후 정적 전환 상태가 별도로 표시된다.

## 정적 화면만 실행

```powershell
python -m http.server 8780 --bind 127.0.0.1 --directory web
```

브라우저에서 `http://127.0.0.1:8780/`을 연다.

## 데이터 갱신

```powershell
python scripts/build_clean_map_background.py --source web/assets/jeju-final-map-panel-cardless-source.png --output web/assets/jeju-final-map-panel-cardless.png
python scripts/build_app_recommendation_seed.py --places data/jeju_accessible_spots.json --output web/data/app_recommendation_seed.json --generated-at 2026-07-09
python scripts/build_recommendation_case_validation_report.py --places data/jeju_accessible_spots.json --output-json data/recommendation_case_validation_report.json --output-md docs/recommendation_case_validation_report_20260709.md --web-output-json web/data/recommendation_case_validation_report.json --generated-at 2026-07-09
python scripts/build_operations_readiness_report.py --place-cards data/jeju_accessible_spots.json --data-request-tracker data/data_request_tracker.json --service-seed-gate-status data/roadview_service_seed_gate_status.json --output data/operations_readiness_report.json --web-output web/data/operations_readiness_report.json --generated-at 2026-07-09
python scripts/build_service_launch_action_plan.py --operations-readiness data/operations_readiness_report.json --service-seed-gate-status data/roadview_service_seed_gate_status.json --provider-404-report data/roadview_provider_404_image_report.json --image-receipt-report data/roadview_image_receipt_report.json --visual-review-sheet data/roadview_visual_review_sheet.json --output-json data/service_launch_action_plan.json --output-md docs/service_launch_action_plan_20260709.md --web-output-json web/data/service_launch_action_plan.json --generated-at 2026-07-09
python scripts/build_service_preflight_report.py --workspace-root . --output data/service_preflight_report.json --output-md docs/service_preflight_report_20260709.md --generated-at 2026-07-09
```

추천 기본 데이터는 `web/data/app_recommendation_seed.json`에서 읽는다. 추천 계산은 `src/scoring.py`와 `src/app_recommendations.py`에서 수행한다.
추천 장소 좌표는 `data/roadview_image_metadata.json`의 관광지별 로드뷰 좌표 중심값과 `data/place_location_overrides.json`의 수동 보강 좌표를 결합해 `location` 필드로 내려간다.
검수 근거 영역은 `web/data/recommendation_case_validation_report.json`을 읽어 현재 상황의 제외 기준, 감점 근거, 검증 통과 항목을 표시한다.
좌측 서비스 공개 게이트는 `web/data/operations_readiness_report.json`을 읽어 상용 공개 보류/제한 공개/전체 공개 가능 상태를 표시한다.
서비스 런칭 다음 실행 영역은 `web/data/service_launch_action_plan.json`을 읽어 누락 원본 수령, 시각 검수, 활성 후보 승격 순서를 표시한다.
서비스 실행 전 사전점검은 `data/service_preflight_report.json`과 `docs/service_preflight_report_20260709.md`에서 환경 설정, 앱용 데이터, 공개 게이트, 비밀값 노출 여부를 확인한다.

## API 계약 검증

```powershell
python -m unittest tests.test_recommendation_api -v
python scripts/build_service_preflight_report.py --workspace-root . --output data/service_preflight_report.json --output-md docs/service_preflight_report_20260709.md --generated-at 2026-07-09
```

추천 API는 잘못된 JSON, 잘못된 `limit`, 과대 본문, 내부 예외를 JSON `code/error` 형식으로 반환한다. 내부 예외 원문과 비밀값은 응답에 노출하지 않는다.
경로 API는 `POST /api/routes`에서 추천 장소 좌표 배열을 받아 도로형 경로 좌표열, 예상 거리, 예상 시간을 반환한다. 프런트는 서버 health의 `features.route_proxy`가 확인될 때만 이 프록시를 호출하고, 구버전 서버에서는 브라우저 직접 경로 계산으로 자동 대체한다.

## 중앙 지도 위치 기준

중앙 지도 카드는 고정 픽셀 위치가 아니라 추천 장소의 `location.latitude`, `location.longitude`를 제주 지도 영역에 투영해 배치한다. 좌표가 있는 장소는 실제 위치 핀이 표시되고, 카드에는 `실제 위치 기반` 배지가 붙는다. 데스크톱에서는 같은 좌표 배열을 추천 순서대로 연결해 실제 장소 기반 동선 레이어도 함께 그린다.

중앙 지도 배경은 `web/assets/jeju-final-map-panel-cardless.png`를 사용한다. 이 이미지는 확정 시안 원본에서 추천 장소 카드 4개, 데모 경로선, 데모 벤치 아이콘, `쉬어가는 지점` 안내를 제거한 `web/assets/jeju-final-map-panel-cardless-source.png`를 앱 규격으로 리사이즈한 배경이다. 하단 통계 패널, 지도 제목, 지도 컨트롤은 시안의 인상을 유지하기 위해 그대로 둔다. 실제 장소 카드, 점수, 상태값, 위치 핀, 동선은 모두 `web/data/app_recommendation_seed.json` 또는 추천 API 응답의 `location` 값을 기준으로 앱에서 렌더링한다.

추천 API 응답이 들어오면 런타임 장소 목록을 그대로 교체하지 않고, 정적 seed의 장소 인덱스로 `location`을 보강한다. 따라서 API 응답에 좌표가 일시적으로 빠지거나 `route`에는 있지만 `places`에 누락된 장소가 있어도 기존 검증 좌표를 유지한다.

중앙 감성 지도 동선은 추천 순서와 실제 좌표를 빠르게 이해시키는 요약선이다. 상단 또는 우측 상세의 `실제 경로 보기`를 누르면 별도 상세 지도 모달이 열리고, 실제 지도 타일 위에 도로형 경로선, 핀 4개, 장소별 접근성 태그, 예상 이동거리/시간을 표시한다.

## 실제 경로 상세

상세 경로 모달은 Leaflet 지도 위에 실제 좌표 기반 장소 핀과 도로형 경로선을 표시한다. 우선순위는 다음과 같다.

1. 같은 서버의 `/api/routes` 프록시 사용
2. 프록시가 없으면 브라우저에서 공개 경로 API 직접 호출
3. 둘 다 실패하면 좌표 기반 요약 경로로 자동 대체

현재 검증된 기본 코스는 제주문학관 → 제주한란전시관 → 사려니숲길 무장애나눔길 → 제주국제컨벤션센터이며, `8792` 서버 기준 약 `95.0km`, 약 `2시간 2분`, 경로 좌표 `2,764`개를 반환했다.

```powershell
python -m unittest tests.test_place_locations tests.test_app_recommendations -v
```

현재 추천 시나리오에 노출되는 장소는 `20/20` 좌표 보유 상태다. 로드뷰 메타데이터로 자동 매칭되지 않는 핵심 장소는 `data/place_location_overrides.json`에 출처와 함께 보강한다.

## 이미지 표시 정책

- 우측 상세 대표 이미지는 서비스 표시용 이미지다.
- 로드뷰 원본 이미지는 접근성 검수 근거로 분리해서 다룬다.
- 장소별 대표 이미지가 준비된 경우 장소별 정책을 우선한다.
- 장소별 이미지가 없으면 카테고리 대체 이미지를 사용한다.
- 이미지 로딩에 실패하면 기본 제주 이미지로 전환한다.
- 이미지는 클릭하면 확대 모달로 확인하고, 닫기 버튼이나 배경 클릭으로 닫는다.
