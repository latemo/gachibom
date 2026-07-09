# 로드뷰 이미지 원본 수령 및 배치 가이드

## 대상 데이터

- 데이터명: 제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지
- 공공데이터포털 URL: https://www.data.go.kr/data/15110209/fileData.do
- 제공기관: 제주특별자치도
- 전체 이미지: 107개 관광지 4,748장
- 전체 용량: 약 23~25GB
- 비고: 공공데이터포털 설명은 전자매체 별도 제공을 안내하지만, 현재 GIS 이미지 URL 패턴으로 서비스 시드 원본 대부분을 키 없이 직접 확보할 수 있음이 확인됐다.

## 현재 서비스 시드 검수 범위

- 대상 장소: 17곳
- 대상 이미지 메타데이터: 1,023장
- 우선 검수 샘플: 102장
- 현재 로컬 보유 이미지: 953장
- 현재 로컬 보유 우선 검수 샘플: 102장
- 제공 서버 404 누락: 70장
- 현재 산출물: `data/roadview_image_asset_manifest.json`

## 요청 패키지 산출물

- 우선 검수 샘플 CSV: `data/roadview_image_acquisition_priority_samples.csv`
- 서비스 시드 전체 요청 CSV: `data/roadview_image_acquisition_full_request.csv`
- 장소별 요청 요약 CSV: `data/roadview_image_acquisition_place_summary.csv`
- 제공기관 요청 문안: `docs/roadview_image_data_request_message.md`
- 수령 검수 워크플로우: `docs/roadview_image_receipt_workflow.md`
- 서비스 시드 통합 게이트: `docs/service_seed_gate_status_workflow.md`
- 공공데이터 요청 추적대장: `docs/data_request_tracker_workflow.md`
- 다운로드 리포트: `data/roadview_image_download_report.all.json`
- 제공 서버 404 리포트: `data/roadview_provider_404_image_report.json`
- 제공기관 전달용 404 CSV: `data/roadview_provider_404_image_request.csv`
- 제공기관 복구 요청 문안: `docs/roadview_provider_404_recovery_request.md`

## 수령 후 배치 위치

이미지 파일은 아래 폴더에 배치한다.

```text
data/raw/roadview_images/
```

우선 샘플 검수는 파일명을 그대로 두는 것을 기준으로 한다.

```text
data/raw/roadview_images/JEJUNATIONALMU-1-001.jpg
data/raw/roadview_images/GIMNYEONGMAZEPA-1-001.jpg
data/raw/roadview_images/SAMSUNGHYEOL-1-001.jpg
```

확장자는 `.jpg`, `.JPG`, `.jpeg`, `.png`를 자동 탐지한다.

## 직접 다운로드 명령

서비스 시드 요청 목록의 이미지 URL은 `https://gis.jeju.go.kr/images/roadview/{tourist_name_en}/{image_file_name}.jpg` 패턴으로 생성한다.

우선 검수 샘플만 받을 때:

```bash
python scripts/download_roadview_requested_images.py --acquisition-request data/roadview_image_acquisition_request.json --target-root data/raw/roadview_images --tier priority --output data/roadview_image_download_report.priority.json --generated-at 2026-07-09 --timeout-seconds 90
```

서비스 시드 전체 1,023장 기준으로 받을 때:

```bash
python scripts/download_roadview_requested_images.py --acquisition-request data/roadview_image_acquisition_request.json --target-root data/raw/roadview_images --tier all --output data/roadview_image_download_report.all.json --generated-at 2026-07-09 --timeout-seconds 90
```

제공 서버가 404를 반환한 원본은 별도 리포트로 분리한다.

```bash
python scripts/build_roadview_provider_404_image_report.py --download-report data/roadview_image_download_report.all.json --output data/roadview_provider_404_image_report.json --generated-at 2026-07-09
```

제공기관에 보낼 복구 요청 패키지는 아래 명령으로 만든다.

```bash
python scripts/export_roadview_provider_404_request_package.py --provider-404-report data/roadview_provider_404_image_report.json --csv-output data/roadview_provider_404_image_request.csv --message-output docs/roadview_provider_404_recovery_request.md --generated-at 2026-07-09
```

현재 확인 결과 1,023장 중 953장은 로컬에 확보했고, 70장은 공공 API 메타데이터에는 존재하지만 이미지 서버가 `HTTP 404`를 반환한다. 이 70장은 제공기관에 복구 또는 대체 원본 수령을 요청해야 한다.

## 수령 검수 명령

```bash
python scripts/build_roadview_image_receipt_report.py --acquisition-request data/roadview_image_acquisition_request.json --receipt-root data/raw/roadview_images --output data/roadview_image_receipt_report.json --generated-at 2026-07-09
```

`data/roadview_image_receipt_report.json`에서 `missing_requested_images`가 0인지 먼저 확인한다.

## 자산 매니페스트 재검사 명령

```bash
python scripts/build_roadview_image_review.py --work-queue data/roadview_service_seed_work_queue.json --image-metadata data/roadview_image_metadata.json --asset-root data/raw/roadview_images --output data/roadview_image_review.json --generated-at 2026-07-09
python scripts/build_roadview_image_asset_manifest.py --roadview-image-review data/roadview_image_review.json --asset-root data/raw/roadview_images --output data/roadview_image_asset_manifest.json --generated-at 2026-07-09
```

샘플 이미지가 모두 배치되면 `ready_for_visual_review` 장소가 생기고, 그 다음 실제 시각 검수에서 다음 항목을 판정한다.

- 출입구 단차 또는 경사로
- 주요 관람 동선 경사
- 바닥 상태
- 주차장-출입구 연결 동선
