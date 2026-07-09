# 공공데이터 요청·수령 추적대장 워크플로우

## 목적

서비스화 단계에서는 어떤 공공데이터가 이미 확보됐고, 어떤 원본은 요청만 준비됐으며, 어떤 자료는 수령 후 검수가 필요한지 분리해서 관리해야 한다. 이 추적대장은 데이터 출처별 요청, 수령, 로컬 산출물, 서비스 반영 가능 상태를 한 번에 확인하기 위한 운영 자료다.

## 생성 산출물

- 자동화/검증용 JSON: `data/data_request_tracker.json`
- 운영자 확인용 CSV: `data/data_request_tracker.csv`

## 실행

```bash
python scripts/build_data_request_tracker.py --output data/data_request_tracker.json --csv-output data/data_request_tracker.csv --generated-at 2026-07-08
```

기본 입력은 아래 산출물을 사용한다.

- `data/roadview_image_acquisition_request.json`
- `data/roadview_image_receipt_report.json`
- `data/roadview_service_seed_gate_status.json`

## 상태값

- `not_required_ready`: 별도 요청 없이 현재 로컬 산출물을 서비스 데이터 근거로 사용할 수 있음
- `ready_to_submit`: 요청 문안과 첨부 산출물은 준비됐지만 수령 기록이 없음
- `awaiting_receipt`: 일부 원본은 수령됐지만 누락 원본이 남아 있어 제공기관 복구 또는 추가 수령이 필요함
- `ready_to_use`: 요청 대상 원본이 수령돼 다음 검수 단계로 이동 가능
- `action_required`: 필수 산출물 생성, 원본 수령 등 추가 작업 필요

## 현재 우선순위

1. `roadview_image_files`가 `awaiting_receipt`이면 `data/roadview_provider_404_image_report.json`을 근거로 제공기관에 누락 원본 복구 또는 대체 원본 수령을 요청한다.
2. `roadview_image_files`가 `ready_to_submit`이면 공공데이터포털 또는 제공기관에 요청 문안과 CSV 3종을 제출한다.
3. 이미지 원본 수령 후 `data/raw/roadview_images/`에 배치한다.
4. `scripts/build_roadview_missing_image_recovery_report.py`로 누락 70장 회복 여부를 먼저 확인한다.
5. 회복 완료 또는 대체 원본 확정 후 수령 리포트, 자산 매니페스트, 시각 검수 시트, 통합 게이트 리포트, 요청 추적대장을 순서대로 재생성한다.
6. `roadview_api`는 제주도청 활용가이드 기준 인증/권한 없음으로 확인됐으므로, 정기 갱신 주기와 호출량·장애 대응 절차를 정의한다.

상용 공개 전 최종 자동 점검은 `docs/operations_readiness_workflow.md` 기준으로 실행한다.

## 운영 메모

CSV에는 실제 제출일, 담당자, 접수번호 같은 수동 운영 필드를 추가해도 된다. 다만 자동 재생성 시 덮어쓰일 수 있으므로 장기 운영용 수동 기록은 별도 문서나 스프레드시트에 복제해 관리한다.
