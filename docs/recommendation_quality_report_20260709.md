# 추천 품질 검증 리포트

작성일: 2026-07-09

## 목적

상황별 여행 조건에 따라 추천 장소가 실제로 달라지는지 확인했다. 특히 회복 중, 음식 제한, 휠체어 접근, 아이 동반, 날씨 민감 조건을 기준으로 장소 제외와 점수 변화가 의도대로 작동하는지 검증했다.

## 반영한 보강

- 아이 동반 조건에서 숲·산책형, 공원·휴식형 중 도보 부담이 낮고 휴식 정보가 있는 장소에 상황별 가점을 부여한다.
- 휠체어 접근 코스와 아이 동반 코스가 같은 실내 장소만 반복되지 않도록 했다.
- 음식 제한 조건은 기존처럼 `restaurant`, `food_market`을 추천에서 제외한다.
- 날씨 민감 조건은 날씨 영향이 큰 해안/야외 고노출 장소를 상위 추천에서 배제한다.

## 현재 추천 결과

휠체어 접근:

- 제주문학관 `indoor`
- 제주국제컨벤션센터 `indoor`
- 제주한란전시관 `indoor`
- 김만덕기념관 `indoor`

아이 동반:

- 제주문학관 `indoor`
- 제주국제컨벤션센터 `indoor`
- 사려니숲길 무장애나눔길 `forest`
- 신산공원 `rest_area`

음식 제한:

- 제주문학관 `indoor`
- 사려니숲길 무장애나눔길 `forest`
- 서귀포 치유의숲 `forest`
- 제주한란전시관 `indoor`

날씨 민감:

- 제주문학관 `indoor`
- 제주국제컨벤션센터 `indoor`
- 제주한란전시관 `indoor`
- 제주세계자연유산센터 `indoor`

## 검증 기준

- 음식 제한 코스에는 `restaurant`, `food_market` 카테고리가 없어야 한다.
- 날씨 민감 코스에는 `sea` 카테고리와 `weather_sensitivity=high` 장소가 없어야 한다.
- 휠체어 접근 코스와 아이 동반 코스는 서로 달라야 한다.
- 아이 동반 코스에는 숲·산책형 또는 공원·휴식형 장소가 포함되어야 한다.
- 런타임 API도 seed 생성 결과와 같은 정책을 따라야 한다.

## 검증 결과

- `web/data/app_recommendation_seed.json` 생성일: 2026-07-09
- `http://127.0.0.1:8790/api/health`: 정상
- 8790 API 런타임 아이 동반 요청 결과: `제주문학관`, `제주국제컨벤션센터`, `사려니숲길 무장애나눔길`, `신산공원`
- 프론트 화면에 `아이 동반` 시나리오 카드를 추가했고, 클릭 시 아이 동반 코스로 전환됨을 확인했다.
- 상황별 검증표: `docs/recommendation_case_validation_report_20260709.md`
- 검증 데이터: `data/recommendation_case_validation_report.json`
- 전체 테스트: 114개 통과

## 관련 변경 파일

- `src/scoring.py`
- `tests/test_app_recommendations.py`
- `tests/test_recommendation_service.py`
- `tests/test_recommendation_case_validation.py`
- `web/data/app_recommendation_seed.json`
- `web/app.js`
- `web/styles.css`
- `web/index.html`
