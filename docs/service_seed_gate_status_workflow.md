# 서비스 시드 통합 게이트 상태 워크플로우

## 목적

로드뷰 서비스 시드 17곳의 공개 승격 가능 여부를 하나의 리포트로 확인한다. 이미지 요청, 원본 수령, 자산 매니페스트, 시각 검수, active 후보 산출을 분리해 현재 병목을 명확히 기록한다.

## 입력 산출물

- 이미지 요청: `data/roadview_image_acquisition_request.json`
- 이미지 수령 검수: `data/roadview_image_receipt_report.json`
- 자산 매니페스트: `data/roadview_image_asset_manifest.json`
- 시각 검수 시트: `data/roadview_visual_review_sheet.json`
- 승격 준비 리포트: `data/roadview_service_seed_promotion_readiness.json`
- active 후보 리포트: `data/roadview_service_seed_active_candidate_report.json`

## 실행

```bash
python scripts/build_service_seed_gate_status.py --acquisition-request data/roadview_image_acquisition_request.json --receipt-report data/roadview_image_receipt_report.json --image-asset-manifest data/roadview_image_asset_manifest.json --visual-review-sheet data/roadview_visual_review_sheet.json --promotion-readiness data/roadview_service_seed_promotion_readiness.json --active-candidate-report data/roadview_service_seed_active_candidate_report.json --output data/roadview_service_seed_gate_status.json --generated-at 2026-07-09
```

## 핵심 판정

- `overall_status`: 전체 공개 승격 가능 여부
- `current_primary_stage`: 현재 가장 앞단의 병목
- `summary.next_action`: 다음 실행 작업
- `items[].primary_blocking_stage`: 장소별 최초 차단 단계

## 단계 순서

1. `awaiting_image_receipt`: 제공기관 이미지 원본 미수령
2. `resolving_duplicate_images`: 동일 파일명 후보 정리 필요
3. `preparing_visual_assets`: 우선 검수 샘플 파일 매칭 필요
4. `preparing_visual_review_sheet`: 시각 검수 시트 재생성 필요
5. `awaiting_visual_review`: 필수 동선 필드 수동 검수 필요
6. `resolving_visual_review_findings`: 충돌 또는 추가 확인 필요
7. `preparing_active_candidate_export`: active 후보 산출물 재생성 필요
8. `ready_for_service_activation`: 공개 서비스 반영 가능

## 현재 기준

현재 서비스 시드 17곳 기준으로 원본 1,023장 중 953장을 확보했고, 우선 검수 샘플 102장은 모두 사용 가능하다. 다만 70장은 이미지 서버가 `HTTP 404`를 반환하므로 전체 상태는 아직 `blocked`이며 `current_primary_stage`는 `awaiting_image_receipt`가 정상이다.

장소별 병목은 다음과 같다.

- `awaiting_image_receipt`: 4곳
- `awaiting_visual_review`: 13곳

이미지 수령 또는 제공기관 404 복구 후에는 수령 리포트, 자산 매니페스트, 시각 검수 시트, 통합 게이트 리포트를 순서대로 재생성한다.

공공데이터 출처별 요청·수령 상태는 `docs/data_request_tracker_workflow.md` 기준으로 관리한다.
