# 로드뷰 시각 검수 팀 공유 가이드

## 공유 파일

- 압축 파일: `docs/roadview_visual_review_share.zip`
- 검증 리포트: `data/roadview_visual_review_share_validation_report.json`
- 검증 해시: `922a2889411852fe1c7f92480ba577b22b6f065d000e8bdd0340fd59b0fef920`

## 팀원이 보는 방법

1. `roadview_visual_review_share.zip`을 전달받는다.
2. 압축을 푼다.
3. `index.html`을 브라우저로 연다.
4. 장소별 묶음으로 보려면 `packets.html`을 연다.
5. 상단 `난해 항목 확인 가이드`에서 자동 판정이 애매하게 본 이유와 확인 포인트를 먼저 확인한다.
6. 필터의 `난해 항목`을 눌러 사람이 먼저 봐야 할 48개 항목만 확인한다.
7. 항목별 `자동 판정 승인`, `보류`, `이미지 부족`, `충돌` 버튼을 누르거나 직접 판정값을 선택한다.
8. 크롬 또는 엣지에서는 `판정 파일 연결`로 `roadview_visual_review_decisions.csv`를 선택하면 이후 변경 사항이 같은 판정 파일에 저장된다.
9. 파일 직접 저장이 안 되는 브라우저에서는 `판정 파일 내려받기`로 결과 파일을 내려받는다.

## 정적 호스팅에 올리는 방법

압축 파일 내부 파일을 그대로 정적 호스팅 루트에 올린다.

필수 구조:

```text
index.html
packets.html
assets/
contact_sheets/
decisions_by_place/
roadview_visual_review_decisions.csv
README.md
```

`index.html`과 `packets.html`은 상대 경로만 사용하므로 정적 호스팅 서비스에 그대로 올릴 수 있다.

## 배포 전 검증

```bash
python scripts/validate_roadview_visual_review_share_package.py --package-dir docs/roadview_visual_review_share_20260709 --zip-path docs/roadview_visual_review_share.zip --output data/roadview_visual_review_share_validation_report.json --expected-assets 102 --expected-contact-sheets 17 --expected-place-csvs 17 --generated-at 2026-07-09
```

검증 기준:

- `index.html`, `packets.html`, `README.md`, 전체 판정 파일 존재
- 축소 이미지 102장 존재
- 이미지 묶음표 17장 존재
- 장소별 판정 파일 17개 존재
- 전체 판정 파일과 장소별 판정 파일에 자동 판정/사람 최종 판정 컬럼 존재
- 압축 파일 내부에 `index.html`과 이미지 포함
- `file:///`, `C:\`, `data/raw/roadview_images` 같은 로컬 의존 경로 없음

## 판정 입력 규칙

- 자동 판정은 참고용이며 서비스 반영에는 사용하지 않는다.
- 사람 최종 판정은 `확인됨`, `추가 확인`, `정보 충돌`, `근거 부족` 중 하나로 입력한다.
- 근거 이미지와 최종 메모는 버튼을 누르면 자동으로 채워지며, 필요하면 사람이 수정한다.
- 최종 검수자와 검수일을 입력한다.

현재 공유 검수 화면과 판정 파일에는 자동 판정 초안이 미리 채워져 있다. `난해 항목`은 48개이며, 이 중 `추가 확인` 33개와 `확인됨`이지만 신뢰도 `중간`인 15개를 사람이 먼저 확인한다. 서비스 반영은 사람이 최종 판정을 입력한 항목만 대상으로 한다. 최종 판정이 비어 있으면 자동 판정 초안이 있어도 검수 대기 상태로 남는다.

## 검수 결과 회수

팀원이 검수 화면에서 저장하거나 내려받은 판정 파일을 돌려주면 다음 순서로 반영한다.

```bash
python scripts/merge_roadview_visual_review_decision_csvs.py --csv-dir data/roadview_visual_review_decisions_by_place --output data/roadview_visual_review_decisions.csv
python scripts/run_roadview_visual_review_pipeline.py --generated-at 2026-07-09
```

파이프라인은 판정 반영 전에 `data/roadview_missing_image_recovery_report.json`을 먼저 갱신한다. 누락 원본 70장이 새로 들어온 경우 이 리포트에서 회복 수량과 중복 파일명 여부를 확인한 뒤 전체 수령 리포트와 서비스 게이트 상태를 본다. 정상 완료 시 `web/data/operations_readiness_report.json`과 `web/data/service_launch_action_plan.json`도 함께 갱신되어 앱 좌측 공개 게이트의 다음 실행 항목까지 최신화된다.
