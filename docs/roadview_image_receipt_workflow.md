# 로드뷰 이미지 수령 검수 워크플로우

## 목적

제공기관에서 받은 로드뷰 이미지 원본이 서비스 시드 요청 목록과 맞는지 검증한다. 이 단계는 이미지 파일을 실제 접근성 시각 검수에 쓰기 전의 품질 게이트다.

## 입력

- 요청 기준: `data/roadview_image_acquisition_request.json`
- 수령 이미지 폴더: `data/raw/roadview_images/`
- 다운로드 리포트: `data/roadview_image_download_report.all.json`
- 제공 서버 404 리포트: `data/roadview_provider_404_image_report.json`
- 제공기관 전달용 404 CSV: `data/roadview_provider_404_image_request.csv`
- 제공기관 복구 요청 문안: `docs/roadview_provider_404_recovery_request.md`
- 결과 리포트: `data/roadview_image_receipt_report.json`

## 실행

이미지 수령 후 원본 파일명을 유지해 `data/raw/roadview_images/` 아래에 배치한다. 하위 폴더가 있어도 파일명 기준으로 탐색한다. 현재 서비스 시드 원본은 GIS 이미지 URL 패턴으로 직접 다운로드할 수 있다.

```bash
python scripts/download_roadview_requested_images.py --acquisition-request data/roadview_image_acquisition_request.json --target-root data/raw/roadview_images --tier all --output data/roadview_image_download_report.all.json --generated-at 2026-07-09 --timeout-seconds 90
```

이미지 서버가 404를 반환한 항목은 제공기관 복구 요청 대상으로 분리한다.

```bash
python scripts/build_roadview_provider_404_image_report.py --download-report data/roadview_image_download_report.all.json --output data/roadview_provider_404_image_report.json --generated-at 2026-07-09
```

제공기관 전달용 누락 목록과 요청 문안은 아래 명령으로 생성한다.

```bash
python scripts/export_roadview_provider_404_request_package.py --provider-404-report data/roadview_provider_404_image_report.json --csv-output data/roadview_provider_404_image_request.csv --message-output docs/roadview_provider_404_recovery_request.md --generated-at 2026-07-09
```

```bash
python scripts/build_roadview_image_receipt_report.py --acquisition-request data/roadview_image_acquisition_request.json --receipt-root data/raw/roadview_images --output data/roadview_image_receipt_report.json --generated-at 2026-07-09
```

전체 데이터셋처럼 용량이 큰 원본을 처음 빠르게 확인할 때는 해시 계산을 생략할 수 있다.

```bash
python scripts/build_roadview_image_receipt_report.py --acquisition-request data/roadview_image_acquisition_request.json --receipt-root data/raw/roadview_images --output data/roadview_image_receipt_report.json --generated-at 2026-07-09 --skip-hash
```

## 판정 기준

- `complete`: 요청 이미지가 모두 존재한다.
- `partial`: 요청 이미지 일부만 존재한다.
- `empty`: 요청 이미지가 하나도 없다.
- `ready_for_visual_manifest`: 중복 파일명 없이 요청 이미지가 모두 존재한다.
- `needs_missing_files`: 누락 파일이 있어 추가 수령 또는 재요청이 필요하다.
- `needs_duplicate_resolution`: 같은 파일명 후보가 여러 개라 수동 정리가 필요하다.

## 현재 수령 상태

- 요청 이미지: 1,023장
- 로컬 확보 이미지: 953장
- 누락 이미지: 70장
- 우선 검수 샘플: 102장 모두 확보
- 404 영향 장소: 국립제주박물관 2장, 삼성혈 1장, 제주4.3평화공원 66장, 제주삼양동유적 1장

70장은 모두 `HTTP 404`로 확인되어 단순 재시도 대상이 아니라 제공기관 원본 복구 또는 대체 원본 수령 대상이다.

## 다음 단계

`summary.missing_requested_images`가 0이고 `summary.duplicate_requested_image_names`가 0이면 자산 매니페스트를 재생성한다.

```bash
python scripts/build_roadview_image_review.py --work-queue data/roadview_service_seed_work_queue.json --image-metadata data/roadview_image_metadata.json --asset-root data/raw/roadview_images --output data/roadview_image_review.json --generated-at 2026-07-09
python scripts/build_roadview_image_asset_manifest.py --roadview-image-review data/roadview_image_review.json --asset-root data/raw/roadview_images --output data/roadview_image_asset_manifest.json --generated-at 2026-07-09
```

그 다음 시각 검수 시트를 다시 생성한다.

```bash
python scripts/build_roadview_visual_review_sheet.py --roadview-image-review data/roadview_image_review.json --image-asset-manifest data/roadview_image_asset_manifest.json --output data/roadview_visual_review_sheet.json --generated-at 2026-07-09
```

마지막으로 통합 게이트 상태를 재생성한다.

```bash
python scripts/build_service_seed_gate_status.py --acquisition-request data/roadview_image_acquisition_request.json --receipt-report data/roadview_image_receipt_report.json --image-asset-manifest data/roadview_image_asset_manifest.json --visual-review-sheet data/roadview_visual_review_sheet.json --promotion-readiness data/roadview_service_seed_promotion_readiness.json --active-candidate-report data/roadview_service_seed_active_candidate_report.json --output data/roadview_service_seed_gate_status.json --generated-at 2026-07-09
```
