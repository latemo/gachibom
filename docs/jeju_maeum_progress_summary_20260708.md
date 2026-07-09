# 제주의마음 서비스화 작업 진행 요약

작성일: 2026-07-08

## 1. 현재 결론

제주의마음 접근성 여행 인공지능은 데모가 아니라 서비스화를 전제로 데이터 검수, 공공데이터 수령, 로드뷰 이미지 검증, 운영 준비 게이트를 구축하는 방향으로 정리됐다.

현재 자동 점검 기준으로는 전체 공개 차단 상태다. 기본 장소 데이터는 제한 공개 기준을 상당 부분 충족하고, 로드뷰 우선 검수 샘플 102장은 모두 확보됐다. 다만 서비스 시드 전체 원본 1,023장 중 70장이 제공 서버 오류로 남아 있어 전체 공개 승격은 아직 차단 상태다.

현재 최우선 작업은 `data/roadview_provider_404_image_report.json`의 70건을 근거로 제공기관에 원본 복구 또는 대체 원본 수령을 요청하는 것이다. 동시에 확보된 102장 우선 샘플로 시각 검수는 시작할 수 있다.

## 2. 주요 기획 방향

- 단순 데모가 아니라 상용 서비스 기준으로 진행한다.
- 사용자 상황별 추천을 전제로 한다.
- 암환자, 회복기 여행자, 고령자, 휠체어 사용자, 보호자 동반 여행자, 음식 제한 사용자, 혼잡 민감 사용자 등 상황별로 추천 장소와 제외 장소가 달라질 수 있도록 데이터 구조와 정책을 잡았다.
- 식당, 음식 중심 장소, 실내 장소, 휴식 장소, 문화시설, 숲길, 시장 등 다양한 장소 유형을 수용하는 방향으로 정리했다.
- 제주 전체 관광지와 식당 등을 장기적으로 확장하되, 초기 서비스 공개에는 검증 가능한 장소부터 단계적으로 반영하는 정책을 유지한다.

## 3. 여행지 추천 및 점수 집계 방식

추천은 "좋은 관광지"를 고르는 방식이 아니라, 사용자가 입력한 제약과 장소별 접근성 카드가 얼마나 맞는지 계산하는 방식으로 설계했다.

사용자 입력은 다음 구조로 정리한다.

- `traveler_type`: 휠체어 사용자, 고령자, 회복기 여행자, 보호자 동반 등
- `mobility_conditions`: 긴 걷기 어려움, 체력 저하, 날씨 민감, 혼잡 회피 등
- `preferred_themes`: 바다, 숲, 실내, 문화, 휴식 등
- `required_accessibility`: 장애인 화장실, 주차, 휠체어 접근, 휴식 공간 등
- `avoid`: 식당 제외, 장시간 야외 체류 회피, 강한 조명 회피 등

장소 추천 처리 순서:

1. 검증 가능한 접근성 장소 카드에서 후보를 만든다.
2. 비공개, 차단, 폐기 상태이거나 운영자가 부적합으로 본 장소는 기본 추천 후보에서 제외한다.
3. 사용자 상황별 제외 규칙을 먼저 적용한다.
   - 음식 제한 사용자는 식당과 음식 중심 시장을 제외한다.
   - 혼잡·감염 민감 사용자는 시장, 쇼핑, 카페, 혼잡 가능 태그 장소를 감점한다.
   - 날씨 민감 사용자는 해안, 오름, 장시간 야외 장소를 감점한다.
   - 감각 민감 사용자는 강한 조명, 소리, 어두운 전시 등 자극 요소를 확인 필요로 둔다.
4. 제외되지 않은 장소에 100점 기준 적합도 점수를 계산한다.
5. 차단되지 않은 장소를 점수와 신뢰도 순으로 정렬한다.
6. 상위 장소를 최대 4곳까지 묶어 코스를 만든다.
7. 결과에는 점수만 보여주지 않고 추천 이유, 감점 이유, 방문 전 확인 항목, 출처, 안전 문구를 함께 표시한다.

장소별 100점 배점:

| 평가 항목 | 배점 | 판단 기준 |
| --- | ---: | --- |
| 정보 신뢰도 | 25 | 공식 출처, 운영자 검수, 정보 확인일, 출처 주소 |
| 이동 부담 적합성 | 25 | 도보 부담, 계단·경사, 바닥 상태, 주차장-입구 거리, 야외 체류 부담 |
| 편의시설 충족도 | 20 | 장애인 화장실, 주차, 휴식 공간, 휠체어 접근, 대여·보조 정보 |
| 선호 테마 적합성 | 15 | 바다, 숲, 실내, 문화, 휴식 등 사용자가 원하는 경험과의 일치 |
| 안전 안내 명확성 | 15 | 안전 메모, 피해야 할 사용자군, 확인 필요 항목, 운영자 메모 |

강제 감점과 등급 제한:

- 출처 주소가 없으면 `-15`
- 정보 확인일이 없으면 `-10`
- 장애인 화장실을 필수 요청했는데 정보가 부족하면 `-15`
- 가까운 주차를 요청했는데 정보가 부족하면 `-10`
- 휠체어 또는 유모차 사용자에게 중요한 경사·계단 정보가 부족하면 `-20`
- 긴 걷기가 어려운 사용자에게 도보 부담이 높은 장소는 `-25`
- 회복기 또는 체력 저하 사용자에게 장시간 야외 체류 가능성이 크면 `-15`
- `needs_check` 장소는 최대 B등급, `unavailable` 장소는 최대 C등급으로 제한한다.
- 차단 장소는 최대 49점으로 제한하고 기본 추천 결과에서는 제외한다.

코스 점수 집계:

- `rank_places`가 장소별 점수를 계산하고 차단 장소를 제외한 뒤 점수와 신뢰도 순으로 정렬한다.
- `build_recommendation_result`는 상위 장소를 최대 4곳까지 선택한다.
- 코스 총점은 선택된 장소 점수의 평균이다.
- 코스 등급은 평균 점수 기준으로 A/B/C/D/F를 다시 계산한다.
- 코스 신뢰도는 선택된 장소 중 가장 낮은 신뢰도를 따른다.
- 추천 이유, 감점 이유, 확인 필요 항목, 출처는 선택된 장소들의 값을 중복 제거해 합친다.
- 조건에 맞는 장소가 없으면 무리한 추천을 하지 않고 `추천 보류` 결과를 만든다.

관련 구현과 정책 문서:

- 구현: `src/scoring.py`
- 결과 스키마: `data/schemas/recommendation_result.schema.json`
- 점수 정책: `docs/jeju_maeum_scoring_policy.md`
- 상황별 추천 정책: `docs/jeju_maeum_situation_recommendation_policy.md`
- 검증 테스트: `tests/test_scoring.py`

## 4. 현재까지 개발한 근거

현재 구조는 다음 근거를 기준으로 개발했다.

기획 근거:

- 사용자가 "데모가 아니라 서비스화"라고 명확히 요구했기 때문에, 화면보다 데이터 품질, 출처, 검수, 운영 게이트를 먼저 잡았다.
- 암환자 예시처럼 사용자 상황에 따라 식당을 제외해야 하는 요구가 있어, 진단명이 아니라 여행 제약으로 처리하는 상황별 추천 정책을 만들었다.
- 제주 전체 관광지와 식당까지 확장하려는 방향이 있으므로, 초기 데이터만 하드코딩하지 않고 전체 장소 카탈로그와 접근성 카드가 분리되는 구조를 만들었다.
- 추천 결과가 과장되면 안 되므로 "추천보다 근거", "가능보다 부담", "의료 판단 금지" 원칙을 문서화했다.

데이터 근거:

- 공공데이터 `15109149`, `15110209`, `15109158`, `15109153`을 검토해 접근성 시설 현황, 로드뷰 이미지 메타데이터, 이미지 원본, 공개 연계 활용 가능성을 분리했다.
- 기존 기본 장소 카드 43개는 스키마 검증 대상이며, 출처, 안전 메모, 접근성 상태, 운영자 메모를 포함한다.
- 로드뷰 기반 서비스 시드 17곳은 공개 전 비공개로 유지하고, 이미지 수령과 시각 검수 전에는 활성 후보로 승격하지 않는다.
- 로드뷰 이미지 원본 1,023장을 요청 대상으로 만들고, 그중 102장을 우선 검수 샘플로 분리했다.
- 공간정보 이미지 주소 패턴으로 원본 직접 내려받기를 수행해 953장을 확보했고, 서버 404 70건을 별도 리포트로 분리했다.

기술 근거:

- `jsonschema` 검증을 전제로 장소 카드, 추천 결과, 운영 리포트, 로드뷰 검수 산출물의 스키마를 만들었다.
- `src/scoring.py`는 점수, 등급, 신뢰도, 차단 여부, 추천 이유, 감점 이유, 확인 항목, 출처 요약을 한 번에 계산한다.
- 공공데이터 수령 전에도 진행 상태를 판단할 수 있도록 데이터 요청 추적대장, 이미지 수령 리포트, 서비스 시드 게이트, 운영 준비 리포트를 만들었다.
- 전체 테스트 76개가 통과해 현재 기준의 스키마, 점수화, 공공데이터 변환, 로드뷰 검수 흐름이 깨지지 않는지 확인했다.

운영 근거:

- 이미지 원본은 저장소에 직접 넣지 않고, 외부 서비스키가 필요한 연계 정보는 환경변수로만 관리한다.
- 공식 출처 없는 장소나 안전 메모 없는 장소는 상용 추천 결과에 노출하지 않는다.
- 음식 제한, 혼잡 민감, 날씨 민감 같은 조건은 추천 이유가 아니라 제외 또는 감점 근거로 남긴다.
- 현재 전체 공개 차단 상태는 실패가 아니라, 상용 공개 전에 필요한 이미지 수령과 시각 검수가 아직 끝나지 않았다는 운영 게이트 결과다.

## 5. 현재 데이터 상태

기본 장소 카드:

- 파일: `data/jeju_accessible_spots.json`
- 장소 수: 43개
- 모든 카드가 스키마 검증 대상이다.
- 출처, 안전 메모, 접근성 상태, 운영자 메모를 포함한다.

로드뷰 서비스 시드:

- 파일: `data/roadview_service_seed_cards.review.json`
- 후보 장소: 17곳
- 공개 전까지 비공개 상태로 유지한다.
- 공식 출처, 혼잡 정책, 카테고리 정제는 대부분 정리됐고, 현재 차단 게이트는 로드뷰 이미지 시각 검수다.

로드뷰 이미지 요청 범위:

- 서비스 시드 대상 장소: 17곳
- 전체 요청 이미지: 1,023장
- 우선 검수 샘플: 102장
- 현재 수령 이미지: 953장
- 현재 누락 이미지: 70장
- 우선 검수 샘플 수령: 102장 완료

## 6. 공공데이터 분석 및 사용 판단

검토한 공공데이터:

- `15109149` 공개 연계: 제주특별자치도_사회적약자 시설데이터 로드뷰
- `15110209` 파일데이터: 로드뷰 구축 이미지 원본
- `15109158` 파일데이터: 로드뷰 이미지 메타데이터
- `15109153` 파일데이터: 로드뷰 관광지 시설 현황

사용 판단:

- 시설 현황과 이미지 메타데이터는 현재 로컬 산출물로 반영됐다.
- 이미지 원본은 공간정보 이미지 주소 패턴으로 직접 수령 가능하나, 일부 원본은 제공 서버 404로 별도 복구 요청이 필요하다.
- 공개 연계 활용가이드 원문 기준 `서비스 인증/권한`은 `없음`이며, 실제 호출 주소도 키 없이 정상 응답을 확인했다.
- 이미지 원본 70건 404 복구와 시각 검수가 현재 서비스 시드 승격의 1차 병목이다.

공개 연계 관련 정리:

- `15109149` 공공데이터포털 상세는 제주도청 활용가이드 페이지로 이동한다.
- 제주도청 페이지는 등록 화면이 아니라 `공개 연계 활용가이드(사회적약자 시설데이터 구축)V1.0` 참고 문서 페이지다.
- 화면의 `참고문서` 문서 파일에 실제 호출 방식과 파라미터가 있다.
- 호출 기본 주소는 `https://gis.jeju.go.kr/rest/JejuRoadViewTourList`다.
- 확인한 엔드포인트는 `getJejuTouristList`, `getJejuTouristMeta`, `getJejuTouristIMG`이며 모두 키 없이 `200` 응답을 반환했다.

## 7. 생성한 핵심 산출물

로드뷰 이미지 요청 패키지:

- `data/roadview_image_acquisition_request.json`
- `data/roadview_image_acquisition_priority_samples.csv`
- `data/roadview_image_acquisition_full_request.csv`
- `data/roadview_image_acquisition_place_summary.csv`
- `docs/roadview_image_data_request_message.md`

이미지 수령 검수:

- `data/roadview_image_receipt_report.json`
- `data/schemas/roadview_image_receipt_report.schema.json`
- `docs/roadview_image_receipt_workflow.md`
- `scripts/build_roadview_image_receipt_report.py`
- `scripts/download_roadview_requested_images.py`
- `src/roadview_image_download.py`
- `data/roadview_provider_404_image_report.json`
- `data/roadview_provider_404_image_request.csv`
- `data/schemas/roadview_provider_404_image_report.schema.json`
- `docs/roadview_provider_404_recovery_request.md`
- `scripts/build_roadview_provider_404_image_report.py`
- `scripts/export_roadview_provider_404_request_package.py`

서비스 시드 통합 게이트:

- `data/roadview_service_seed_gate_status.json`
- `data/schemas/roadview_service_seed_gate_status.schema.json`
- `docs/service_seed_gate_status_workflow.md`
- `scripts/build_service_seed_gate_status.py`

공공데이터 요청 추적대장:

- `data/data_request_tracker.json`
- `data/data_request_tracker.csv`
- `data/schemas/data_request_tracker.schema.json`
- `docs/data_request_tracker_workflow.md`
- `scripts/build_data_request_tracker.py`

운영 준비 점검:

- `data/operations_readiness_report.json`
- `data/schemas/operations_readiness_report.schema.json`
- `docs/operations_readiness_workflow.md`
- `scripts/build_operations_readiness_report.py`

시각 검수 워크플로우:

- `data/roadview_image_asset_manifest.json`
- `data/roadview_visual_review_sheet.json`
- `data/roadview_visual_review_decisions.csv`
- `data/schemas/roadview_visual_review_decision_import_report.schema.json`
- `data/roadview_visual_review_decision_import_report.json`
- `data/roadview_visual_review_pipeline_report.json`
- `data/roadview_visual_review_packet_report.json`
- `data/roadview_visual_review_share_package_report.json`
- `data/roadview_visual_review_share_validation_report.json`
- `data/roadview_visual_review_decisions_by_place/`
- `data/schemas/roadview_visual_review_pipeline_report.schema.json`
- `data/schemas/roadview_visual_review_share_validation_report.schema.json`
- `data/roadview_visual_review_apply_report.json`
- `docs/roadview_visual_review_board.html`
- `docs/roadview_visual_review_packets/index.html`
- `docs/roadview_visual_review_share.zip`
- `docs/roadview_visual_review_team_share_guide.md`
- `docs/roadview_visual_review_workflow.md`
- `scripts/build_roadview_image_asset_manifest.py`
- `scripts/build_roadview_visual_review_sheet.py`
- `scripts/build_roadview_visual_review_board.py`
- `scripts/build_roadview_visual_review_packets.py`
- `scripts/build_roadview_visual_review_share_package.py`
- `scripts/validate_roadview_visual_review_share_package.py`
- `scripts/export_roadview_visual_review_decisions_csv.py`
- `scripts/merge_roadview_visual_review_decision_csvs.py`
- `scripts/apply_roadview_visual_review_decisions_csv.py`
- `scripts/run_roadview_visual_review_pipeline.py`
- `scripts/apply_roadview_visual_review_sheet.py`

## 8. 현재 자동 점검 결과

운영 준비 리포트:

- 파일: `data/operations_readiness_report.json`
- 상태: 전체 공개 차단
- 총 점검: 15개
- 통과: 12개
- 경고: 0개
- 차단: 3개

차단 원인:

- 로드뷰 이미지 원본 70장이 제공 서버 404로 미수령
- 로드뷰 서비스 시드 17곳 활성 후보 0건
- 이미지 검수 미완료로 상용 전체 공개 보류

경고:

- 서비스키 경고는 제거됐다. 남은 과제는 키 발급이 아니라 무인증 공개 연계의 정기 갱신 주기, 호출량, 장애 대응 절차 정의다.

서비스 시드 통합 게이트:

- 파일: `data/roadview_service_seed_gate_status.json`
- 전체 상태: 차단
- 현재 1차 병목: `awaiting_image_receipt`
- 대상 장소: 17곳
- 수령 요청 이미지: 1,023장
- 수령 완료 이미지: 953장
- 누락 이미지: 70장
- 우선 검수 샘플: 102장 확보
- 장소별 병목: `awaiting_image_receipt` 4곳, `awaiting_visual_review` 13곳
- 활성 후보: 0건

공공데이터 요청 추적대장:

- 파일: `data/data_request_tracker.json`
- 전체 데이터 출처: 4건
- 사용 가능: 3건
- 추가 액션 필요: 1건
- `roadview_image_files`: `awaiting_receipt`
- 로드뷰 공개 연계: 키 발급 불필요, 사용 가능

## 9. 실행 명령

공공데이터 요청 추적대장 재생성:

```bash
python scripts/build_data_request_tracker.py --output data/data_request_tracker.json --csv-output data/data_request_tracker.csv --generated-at 2026-07-08
```

운영 준비 리포트 재생성:

```bash
python scripts/build_operations_readiness_report.py --output data/operations_readiness_report.json --generated-at 2026-07-08
```

이미지 수령 후 수령 리포트 재생성:

```bash
python scripts/build_roadview_image_receipt_report.py --acquisition-request data/roadview_image_acquisition_request.json --receipt-root data/raw/roadview_images --output data/roadview_image_receipt_report.json --generated-at 2026-07-08
```

로드뷰 이미지 직접 다운로드:

```bash
python scripts/download_roadview_requested_images.py --acquisition-request data/roadview_image_acquisition_request.json --target-root data/raw/roadview_images --tier all --output data/roadview_image_download_report.all.json --generated-at 2026-07-08 --timeout-seconds 90
```

제공 서버 404 리포트 재생성:

```bash
python scripts/build_roadview_provider_404_image_report.py --download-report data/roadview_image_download_report.all.json --output data/roadview_provider_404_image_report.json --generated-at 2026-07-08
```

제공기관 404 복구 요청 패키지 생성:

```bash
python scripts/export_roadview_provider_404_request_package.py --provider-404-report data/roadview_provider_404_image_report.json --csv-output data/roadview_provider_404_image_request.csv --message-output docs/roadview_provider_404_recovery_request.md --generated-at 2026-07-08
```

시각 검수 화면 생성:

```bash
python scripts/build_roadview_visual_review_board.py --visual-review-sheet data/roadview_visual_review_sheet.json --provider-404-report data/roadview_provider_404_image_report.json --output docs/roadview_visual_review_board.html --generated-at 2026-07-08
```

장소별 검수 패킷 생성:

```bash
python scripts/build_roadview_visual_review_packets.py --visual-review-sheet data/roadview_visual_review_sheet.json --contact-sheet-dir docs/roadview_visual_review_packets/contact_sheets --csv-dir data/roadview_visual_review_decisions_by_place --index-output docs/roadview_visual_review_packets/index.html --report-output data/roadview_visual_review_packet_report.json --generated-at 2026-07-08
```

팀 공유용 압축 파일 생성:

```bash
python scripts/build_roadview_visual_review_share_package.py --visual-review-sheet data/roadview_visual_review_sheet.json --package-dir docs/roadview_visual_review_share --zip-output docs/roadview_visual_review_share.zip --report-output data/roadview_visual_review_share_package_report.json --max-image-width 1600 --generated-at 2026-07-08
```

팀 공유용 압축 파일 검증:

```bash
python scripts/validate_roadview_visual_review_share_package.py --package-dir docs/roadview_visual_review_share --zip-path docs/roadview_visual_review_share.zip --output data/roadview_visual_review_share_validation_report.json --expected-assets 102 --expected-contact-sheets 17 --expected-place-csvs 17 --generated-at 2026-07-08
```

현재 공유 압축 파일 검증 결과:

- 상태: `pass`
- 점검: 14개 통과, 0개 실패
- 압축 파일 크기: 약 20.6메가바이트
- 검증 해시: `d1ac62b7f9fbec9583dd4c56d331d24352236bbfbb2b7319c5dc146e11fc2a26`
- 공유 검수 화면은 카드형 검수 화면으로 바뀌었고 `난해 항목 확인 가이드`에서 자동 판정이 애매하게 본 이유, 확인 포인트, 권장 처리를 보여준다. 현재 자동 판정 초안 68개 중 `자동 판정 확실` 20개, `난해 항목` 48개이며, 서비스 반영은 `human_final_status`가 입력된 행만 대상으로 한다.

시각 검수 판정 파일 생성:

```bash
python scripts/export_roadview_visual_review_decisions_csv.py --visual-review-sheet data/roadview_visual_review_sheet.json --output data/roadview_visual_review_decisions.csv
```

장소별 판정 파일 병합:

```bash
python scripts/merge_roadview_visual_review_decision_csvs.py --csv-dir data/roadview_visual_review_decisions_by_place --output data/roadview_visual_review_decisions.csv
```

시각 검수 판정 파일 반영:

```bash
python scripts/apply_roadview_visual_review_decisions_csv.py --visual-review-sheet data/roadview_visual_review_sheet.json --decisions-csv data/roadview_visual_review_decisions.csv --output data/roadview_visual_review_sheet.json --report-output data/roadview_visual_review_decision_import_report.json --reviewer operator --generated-at 2026-07-08
```

시각 검수 반영 전체 파이프라인:

```bash
python scripts/run_roadview_visual_review_pipeline.py --generated-at 2026-07-08
```

현재 파이프라인 실행 결과:

- 상태: `completed`
- 판정 파일 행: 68개
- 적용된 판정: 0개
- 대기 행: 68개
- 오류 행: 0개
- 서비스 시드 게이트: 준비 0곳, 차단 17곳

이미지 수령 후 자산 매니페스트 재생성:

```bash
python scripts/build_roadview_image_asset_manifest.py --roadview-image-review data/roadview_image_review.json --asset-root data/raw/roadview_images --output data/roadview_image_asset_manifest.json --generated-at 2026-07-08
```

이미지 수령 후 시각 검수 시트 재생성:

```bash
python scripts/build_roadview_visual_review_sheet.py --roadview-image-review data/roadview_image_review.json --image-asset-manifest data/roadview_image_asset_manifest.json --output data/roadview_visual_review_sheet.json --generated-at 2026-07-08
```

서비스 시드 통합 게이트 재생성:

```bash
python scripts/build_service_seed_gate_status.py --acquisition-request data/roadview_image_acquisition_request.json --receipt-report data/roadview_image_receipt_report.json --image-asset-manifest data/roadview_image_asset_manifest.json --visual-review-sheet data/roadview_visual_review_sheet.json --promotion-readiness data/roadview_service_seed_promotion_readiness.json --active-candidate-report data/roadview_service_seed_active_candidate_report.json --output data/roadview_service_seed_gate_status.json --generated-at 2026-07-08
```

전체 테스트:

```bash
python -m unittest discover -s tests
```

현재 마지막 검증 결과:

- `python -m unittest discover -s tests`
- 76개 테스트 통과

## 10. 다음 작업 순서

1. 제공기관에 로드뷰 원본 70건 복구 또는 대체 원본 수령 요청
   - 근거 리포트: `data/roadview_provider_404_image_report.json`
   - 전달 판정 파일: `data/roadview_provider_404_image_request.csv`
   - 요청 문안: `docs/roadview_provider_404_recovery_request.md`
   - 영향 장소: 국립제주박물관, 삼성혈, 제주4.3평화공원, 제주삼양동유적

2. 로드뷰 공개 연계 정기 갱신 정책 정의
   - 대상: `15109149`
   - 서비스키 없이 호출 가능 확인 완료
   - 호출량, 실패 재시도, 장애 시 캐시 사용 정책 정의

3. 확보된 우선 검수 샘플 102장으로 시각 검수 진행
   - 시트: `data/roadview_visual_review_sheet.json`
   - 입력 판정 파일: `data/roadview_visual_review_decisions.csv`
   - 장소별 판정 파일: `data/roadview_visual_review_decisions_by_place/`
   - 반영 파이프라인: `scripts/run_roadview_visual_review_pipeline.py`
   - 보기용 보드: `docs/roadview_visual_review_board.html`
   - 장소별 패킷: `docs/roadview_visual_review_packets/index.html`
   - 팀 공유 압축 파일: `docs/roadview_visual_review_share.zip`
   - 팀 공유 가이드: `docs/roadview_visual_review_team_share_guide.md`
   - 17곳 68개 필드 검수

4. 70건 복구 후 수령 검수와 시각 검수 재생성
   - 수령 리포트 재생성
   - 자산 매니페스트 재생성
   - 시각 검수 시트 재생성
   - 운영자가 필드별 검수 결과 입력

5. 활성 후보 승격
   - 시각 검수 적용
   - 승격 준비 리포트 재생성
   - 활성 후보 리포트 재생성
   - 운영 준비 리포트 재생성

## 11. 주의사항

- 이미지 원본은 저장소에 직접 커밋하지 않는다.
- `.env` 값이나 다른 외부 서비스키는 응답, 문서, 코드에 노출하지 않는다.
- 로드뷰 이미지 검수 전에는 서비스 시드 17곳을 공개 활성 카드로 승격하지 않는다.
- 음식 제한, 혼잡 민감, 날씨 민감 같은 사용자 상황은 추천 정책에서 제외/감점으로 반영해야 한다.
- 공식 출처 없는 장소나 안전 메모 없는 장소는 상용 추천 결과에 노출하지 않는다.
- 추천 점수는 여행 가능성 보장이 아니라 판단 보조 신호로 표시한다.
- 암환자, 회복기, 고령자 같은 표현은 의료 판단이 아니라 사용자가 직접 입력한 여행 제약을 정리하는 용도로만 사용한다.
