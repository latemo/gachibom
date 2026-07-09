# 로드뷰 시각 검수 워크플로

## 입력 파일

- `data/roadview_visual_review_sheet.json`
- `data/roadview_visual_review_decisions.csv`
- `data/roadview_visual_review_decision_import_report.json`
- `data/roadview_visual_review_pipeline_report.json`
- `data/roadview_visual_review_decisions_by_place/`
- `docs/roadview_visual_review_packets/index.html`
- `docs/roadview_visual_review_board.html`
- `docs/roadview_visual_review_share.zip`
- `data/roadview_visual_review_share_validation_report.json`
- `docs/roadview_visual_review_team_share_guide.md`
- 검수 대상: 17개 장소, 필드 68개
- 현재 상태: 우선 검수 샘플 102장 확보, 17개 장소 모두 검수 진행 중
- 남은 원본 이슈: 전체 1,023장 중 70장은 제공 서버 404로 별도 복구 요청 필요

## 검수 필드

각 장소의 `field_results`에서 다음 4개 필드를 채운다.

- `entrance_step_or_ramp`: 출입구 단차 또는 경사로
- `main_path_slope`: 주요 관람 동선 경사
- `surface_condition`: 바닥 상태
- `parking_to_entrance_route`: 주차장-출입구 연결 동선

## 판정값

- 확인됨: 이미지 근거로 이용 가능성이 확인됨
- 추가 확인: 이미지상 추가 확인 또는 현장 확인 필요
- 정보 충돌: 공식 출처 또는 기존 데이터와 이미지가 충돌
- 근거 부족: 필수 이미지 근거가 부족함
- 미검수: 아직 검수하지 않음

시스템 저장값은 판정 파일 안에 남아 있지만, 검수 화면과 팀 문서에서는 위 한글 판정값으로 표시한다.

## 검수 입력 구조

자동 판정 초안은 참고 컬럼에만 기록한다. 사람이 확정한 판정은 사람 최종 판정 컬럼에 입력한다.
파이프라인과 서비스 승격 게이트는 `human_final_status`만 최종 판정으로 사용한다.
`human_final_status`가 비어 있으면 자동 판정 초안이 있어도 해당 필드는 미검수로 남는다.
현재 공유 산출물은 검수 화면에 자동 판정 초안, 신뢰도, 메모와 `난해 항목 확인 가이드`를 표시한다. `난해 항목` 48개는 자동 판정이 확정하기 어려운 이유, 확인 포인트, 권장 처리를 함께 보여준다. 버튼 또는 직접 입력으로 사람 최종 판정을 채운 뒤 판정 파일 저장 또는 내려받기가 가능하다.

내부 JSON 시트에는 사람이 확정한 최종 판정만 아래 구조로 반영된다.

```json
{
  "status": "verified",
  "evidence_image_file_names": ["JEJUNATIONALMU-1-001"],
  "reviewer_note": "주출입구까지 단차 없는 포장 동선 확인",
  "reviewer": "operator",
  "reviewed_at": "2026-07-09"
}
```

## 검수 이미지 리포트 재생성

로컬에 실제 확보된 이미지 파일을 기준으로 우선 검수 샘플을 재선정한다. 제공 서버 404로 비어 있는 샘플은 같은 장소의 확보된 이미지로 대체된다.

```bash
python scripts/build_roadview_image_review.py --work-queue data/roadview_service_seed_work_queue.json --image-metadata data/roadview_image_metadata.json --asset-root data/raw/roadview_images --output data/roadview_image_review.json --generated-at 2026-07-09
```

## 검수 보드 생성

로컬 이미지 원본을 바로 볼 수 있는 검수 화면을 생성한다.

```bash
python scripts/build_roadview_visual_review_board.py --visual-review-sheet data/roadview_visual_review_sheet.json --provider-404-report data/roadview_provider_404_image_report.json --output docs/roadview_visual_review_board.html --generated-at 2026-07-09
```

브라우저에서 `docs/roadview_visual_review_board.html`을 열면 장소별 샘플 이미지와 필드별 근거 이미지 목록을 함께 확인할 수 있다. 실제 판정값은 `data/roadview_visual_review_sheet.json`의 `field_results`에 기록한다.

## 장소별 검수 묶음

전체 68행 판정 파일을 한 번에 다루기 어렵다면 장소별 이미지 묶음표와 장소별 판정 파일을 생성한다.

```bash
python scripts/build_roadview_visual_review_packets.py --visual-review-sheet data/roadview_visual_review_sheet.json --contact-sheet-dir docs/roadview_visual_review_packets/contact_sheets --csv-dir data/roadview_visual_review_decisions_by_place --index-output docs/roadview_visual_review_packets/index.html --report-output data/roadview_visual_review_packet_report.json --generated-at 2026-07-09
```

브라우저에서 `docs/roadview_visual_review_packets/index.html`을 열면 17개 장소별 검수 묶음을 볼 수 있다. 장소별 판정 파일을 수정한 뒤 전체 판정 파일로 병합한다.

```bash
python scripts/merge_roadview_visual_review_decision_csvs.py --csv-dir data/roadview_visual_review_decisions_by_place --output data/roadview_visual_review_decisions.csv
```

## 팀 공유용 패키지

`file:///C:/...` 로컬 경로는 다른 팀원이 볼 수 없으므로, 검수 화면과 축소 이미지 102장, 장소별 판정 파일을 한 폴더에 담은 압축 파일을 생성한다.

```bash
python scripts/build_roadview_visual_review_share_package.py --visual-review-sheet data/roadview_visual_review_sheet.json --provider-404-report data/roadview_provider_404_image_report.json --package-dir docs/roadview_visual_review_share_20260709 --zip-output docs/roadview_visual_review_share.zip --report-output data/roadview_visual_review_share_package_report.json --max-image-width 1600 --generated-at 2026-07-09
```

팀원에게는 `docs/roadview_visual_review_share.zip`을 공유한다. 압축을 푼 뒤 `index.html`을 열면 로컬 프로젝트 없이도 축소 이미지 기준 검수 화면을 볼 수 있다. 화면 상단의 `난해 항목 확인 가이드`, `난해 항목` 필터, `서버 404` 요약으로 먼저 확인해야 할 항목을 줄인 뒤, `자동 판정 승인`, `보류`, `이미지 부족`, `충돌` 버튼으로 최종 판정을 채우고 판정 파일을 저장하거나 내려받는다. 정적 호스팅에 올릴 경우 압축 파일 안의 폴더 구조를 그대로 업로드한다.

공유 전 검증 리포트를 생성한다.

```bash
python scripts/validate_roadview_visual_review_share_package.py --package-dir docs/roadview_visual_review_share_20260709 --zip-path docs/roadview_visual_review_share.zip --output data/roadview_visual_review_share_validation_report.json --expected-assets 102 --expected-contact-sheets 17 --expected-place-csvs 17 --generated-at 2026-07-09
```

팀원 전달 방법과 정적 호스팅 방법은 `docs/roadview_visual_review_team_share_guide.md`를 기준으로 한다.

## 판정 파일 입력

운영자가 스프레드시트에서 입력할 수 있는 68행 판정 파일을 생성한다.

```bash
python scripts/export_roadview_visual_review_decisions_csv.py --visual-review-sheet data/roadview_visual_review_sheet.json --output data/roadview_visual_review_decisions.csv
```

판정 파일에서 아래 열을 채운다.

- `ai_suggested_status`: 자동 판정 1차 제안. 서비스 반영에는 사용하지 않음
- `ai_suggested_evidence_image_file_names`: 자동 판정이 참고한 근거 이미지 파일명. 여러 개면 `;`로 구분
- `ai_suggested_note`: 자동 판정 초안 근거
- `ai_confidence`: 신뢰도. 화면에는 높음, 중간, 낮음으로 표시
- `human_final_status`: 사람이 확정한 최종 판정. 확인됨, 추가 확인, 정보 충돌, 근거 부족 중 하나
- `human_evidence_image_file_names`: 사람이 확정한 근거 이미지 파일명. 여러 개면 `;`로 구분
- `human_reviewer_note`: 사람이 남긴 최종 판정 근거
- `human_reviewer`: 검수자
- `human_reviewed_at`: 검수일 `YYYY-MM-DD`

서비스 반영은 `human_final_status`가 입력된 행만 대상으로 한다.
확인됨, 추가 확인, 정보 충돌은 근거 이미지 파일명과 최종 판정 근거가 필수다.
근거 부족은 최종 판정 근거가 필수다.

판정 파일을 다시 검수 시트에 반영한다.

```bash
python scripts/apply_roadview_visual_review_decisions_csv.py --visual-review-sheet data/roadview_visual_review_sheet.json --decisions-csv data/roadview_visual_review_decisions.csv --output data/roadview_visual_review_sheet.json --report-output data/roadview_visual_review_decision_import_report.json --reviewer operator --generated-at 2026-07-09
```

반영 리포트 `data/roadview_visual_review_decision_import_report.json`에서 오류 행이 0개인지 확인한다.

## 전체 파이프라인 실행

검수 판정 파일을 반영한 뒤 누락 원본 회복 상태, 이미지 검수, 승격 준비, 활성 후보, 통합 게이트, 데이터 요청 추적, 운영 준비 리포트, 앱용 공개 게이트 데이터, 서비스 런칭 실행 계획까지 한 번에 재계산한다.

```bash
python scripts/run_roadview_visual_review_pipeline.py --generated-at 2026-07-09
```

이 명령은 먼저 `data/roadview_missing_image_recovery_report.json`과 `docs/roadview_missing_image_recovery_report_20260709.md`를 생성해 제공기관 404 누락 70장의 회복 여부를 확인한다. 판정 파일에 잘못된 상태값, 근거 이미지명, 필수 메모 누락이 있으면 회복 검증 산출물, `data/roadview_visual_review_decision_import_report.json`, `data/roadview_visual_review_pipeline_report.json`만 생성하고 후속 갱신을 중단한다. 정상 입력이면 아래 산출물을 함께 갱신한다.

- `data/roadview_missing_image_recovery_report.json`
- `docs/roadview_missing_image_recovery_report_20260709.md`
- `data/roadview_visual_review_sheet.json`
- `data/roadview_image_review.json`
- `data/roadview_visual_review_apply_report.json`
- `data/roadview_service_seed_promotion_readiness.json`
- `data/roadview_service_seed_active_candidates.json`
- `data/roadview_service_seed_active_candidate_report.json`
- `data/roadview_service_seed_gate_status.json`
- `data/data_request_tracker.json`
- `data/data_request_tracker.csv`
- `data/operations_readiness_report.json`
- `web/data/operations_readiness_report.json`
- `data/service_launch_action_plan.json`
- `docs/service_launch_action_plan_20260709.md`
- `web/data/service_launch_action_plan.json`
- `docs/roadview_visual_review_board.html`

## 적용 명령

판정 파일 반영 후, 채워진 시각 검수 시트를 원본 이미지 검수 리포트에 적용한다.

```bash
python scripts/apply_roadview_visual_review_sheet.py --roadview-image-review data/roadview_image_review.json --visual-review-sheet data/roadview_visual_review_sheet.json --output data/roadview_image_review.json --report-output data/roadview_visual_review_apply_report.json --generated-at 2026-07-09
```

## 승격 게이트 재계산

```bash
python scripts/build_service_seed_promotion_readiness.py --seed-cards data/roadview_service_seed_cards.review.json --work-queue data/roadview_service_seed_work_queue.json --official-source-review data/roadview_official_source_review.json --roadview-image-review data/roadview_image_review.json --crowd-policy-review data/roadview_crowd_policy_review.json --category-refinement-review data/roadview_category_refinement_review.json --output data/roadview_service_seed_promotion_readiness.json --generated-at 2026-07-09
```

모든 이미지 필드가 확인됨으로 판정된 장소만 `roadview_image_verified` 게이트를 통과한다.
