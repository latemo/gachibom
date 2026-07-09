# 로드뷰 누락 원본 이미지 회복 검증 리포트

- 기준일: 2026-07-09
- 현재 상태: 수령 대기
- 회복 대상: 70장
- 회복 확인: 0장
- 아직 누락: 70장
- 영향 장소: 4곳

## 다음 실행

- 아직 확인되지 않은 누락 원본 70장을 제공기관에 재요청 또는 대체 원본으로 수령
- 수령 파일명은 요청 CSV의 image_file_name과 동일하게 맞춰 data/raw/roadview_images에 배치
- 배치 후 누락 이미지 회복 리포트와 전체 수령 리포트를 재생성

## 장소별 상태

- 국립제주박물관: 수령 대기, 회복 0/2장, 남은 누락 2장 / 예시: JEJUNATIONALMU-2-068, JEJUNATIONALMU-2-071
- 삼성혈: 수령 대기, 회복 0/1장, 남은 누락 1장 / 예시: SAMSUNGHYEOL-1-013
- 제주4.3평화공원: 수령 대기, 회복 0/66장, 남은 누락 66장 / 예시: JEJU43PA-1-004, JEJU43PA-1-005, JEJU43PA-1-006, JEJU43PA-1-007, JEJU43PA-1-014
- 제주삼양동유적: 수령 대기, 회복 0/1장, 남은 누락 1장 / 예시: SAMYANGRUINS-1-001

## 재생성 순서

1. 누락 파일을 `data/raw/roadview_images/`에 배치
2. `scripts/build_roadview_missing_image_recovery_report.py` 실행
3. 회복 완료 후 `scripts/build_roadview_image_receipt_report.py` 실행
4. 자산 매니페스트, 시각 검수 시트, 서비스 게이트, 서비스 런칭 실행 계획 순서로 재생성
