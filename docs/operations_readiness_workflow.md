# 운영 준비 점검 리포트 워크플로우

## 목적

상용 서비스 공개 전 자동으로 확인할 수 있는 운영 게이트를 한 리포트로 묶는다. 장소 데이터 품질, 공공데이터 요청 상태, 로드뷰 서비스 시드 상태, 운영 문서 준비 상태를 점검한다.

## 생성 산출물

- 운영 준비 리포트: `data/operations_readiness_report.json`
- 앱 표시용 운영 준비 리포트: `web/data/operations_readiness_report.json`
- 서비스 사전점검 리포트: `data/service_preflight_report.json`
- 운영자 확인용 사전점검 문서: `docs/service_preflight_report_20260709.md`

## 실행

```bash
python scripts/build_operations_readiness_report.py --place-cards data/jeju_accessible_spots.json --data-request-tracker data/data_request_tracker.json --service-seed-gate-status data/roadview_service_seed_gate_status.json --output data/operations_readiness_report.json --web-output web/data/operations_readiness_report.json --generated-at 2026-07-09
python scripts/build_service_preflight_report.py --workspace-root . --output data/service_preflight_report.json --output-md docs/service_preflight_report_20260709.md --generated-at 2026-07-09
```

기본 입력은 아래 산출물을 사용한다.

- `data/jeju_accessible_spots.json`
- `data/data_request_tracker.json`
- `data/roadview_service_seed_gate_status.json`

## 상태값

- `ready_for_full_service`: 자동 점검 blocker와 warning이 모두 없음
- `ready_with_warnings`: 전체 공개를 막는 blocker는 없지만 운영 보강 항목이 있음
- `blocked_for_full_service`: 상용 전체 공개 전 해소해야 할 blocker가 있음

## 자동 점검 범위

- 장소 카드 30개 이상
- 모든 장소 카드 출처 보유
- 모든 장소 카드 안전 메모 보유
- `verified` 또는 `partial` 장소 70% 이상
- 로드뷰 이미지 원본 수령 여부
- 로드뷰 서비스 시드 active 후보 준비 여부
- 핵심 운영 문서 존재 여부
- 서비스 실행 파일, 앱용 JSON 스키마, 환경 설정, 비밀값 노출 여부

## 수동 점검 범위

아래 항목은 `docs/jeju_maeum_launch_checklist.md` 기준으로 별도 수동 검수한다.

- 추천 결과 문구와 안전 문구
- 개인정보 입력·저장 정책
- 접근성 UI
- 외부 API 장애 처리
- 금지 표현 차단
- 사용자 조건별 제외/감점 동작

## 현재 기준

현재 로드뷰 이미지 원본은 1,023장 중 953장이 수령됐고, 70장은 제공 서버 `HTTP 404`로 남아 있다. 따라서 `blocked_for_full_service`가 정상이며, 다음 작업은 `data/roadview_provider_404_image_report.json`을 근거로 제공기관에 누락 원본 복구 또는 대체 원본 수령을 요청하는 것이다. 로드뷰 OpenAPI는 제주도청 활용가이드와 실제 호출 기준으로 인증키 없이 접근 가능한 상태이므로, 별도 키 발급이 아니라 정기 갱신 주기와 호출 장애 대응 절차를 정하면 된다.
