# 제주의마음 서비스 사전점검 리포트

- 기준일: 2026-07-09
- 전체 상태: 차단
- 점검 결과: 통과 24 / 주의 0 / 차단 3
- 비밀값 정책: 비밀값은 리포트에 기록하지 않고 설정 여부만 확인

## 다음 실행

- 누락 원본 이미지 복구 또는 대체 원본 수령을 제공기관에 요청
- 누락 원본 수령 후 전체 파이프라인 재실행
- 팀 검수 CSV 회수 후 전체 파이프라인 재실행

## 환경 설정

- 통과 · 환경 예시 파일: .env.example / 기대값 exists
- 통과 · 로컬 환경 파일: .env exists / 기대값 exists for local service
- 통과 · AI 설명 키 설정: configured / 기대값 configured
- 통과 · AI 모델 설정: gpt-5-mini / 기대값 gpt-5-mini

## 서버·앱 실행 파일

- 통과 · 추천 API 실행 스크립트: scripts/serve_recommendation_api.py / 기대값 exists
- 통과 · 추천 API 핸들러: src/recommendation_api.py / 기대값 exists
- 통과 · 앱 첫 화면: web/index.html / 기대값 exists
- 통과 · 중앙 지도 배경 이미지: web/assets/jeju-final-map-panel-cardless.png / 기대값 exists
- 통과 · 추천 장소 데이터: 43개 장소 / 기대값 >= 30개 장소

## 중앙 지도 위치 계약

- 통과 · 수동 좌표 보강 파일: schema-valid / 기대값 schema-valid JSON
- 통과 · 추천 경로 좌표: 20/20곳 / 기대값 추천 노출 장소 전체 좌표 보유
- 통과 · 중앙 지도 좌표 투영: configured / 기대값 lat/lng projection

## 추천 API 계약

- 통과 · 추천 API 계약 테스트: tests/test_recommendation_api.py / 기대값 exists
- 통과 · 추천 응답 스키마: loadable / 기대값 schema-valid JSON
- 통과 · API 오류 응답 형식: configured / 기대값 JSON code/error
- 통과 · 요청 본문 크기 제한: configured / 기대값 413 on oversized body
- 통과 · 내부 오류 비노출: configured / 기대값 no raw exception text

## 앱용 데이터

- 통과 · 앱 추천 기본 데이터: errors 0 / 기대값 errors 0
- 통과 · 상황별 추천 검증표: errors 0 / 기대값 errors 0
- 통과 · 앱용 운영 준비도: errors 0 / 기대값 errors 0
- 통과 · 앱용 서비스 실행 계획: errors 0 / 기대값 errors 0
- 통과 · operations_readiness_report.json 앱 복사본: blocked_for_full_service / blocked_for_full_service / 기대값 data와 web/data 동일 상태
- 통과 · service_launch_action_plan.json 앱 복사본: blocked_for_full_service / blocked_for_full_service / 기대값 data와 web/data 동일 상태

## 상용 공개 게이트

- 차단 · 상용 공개 게이트: blocked_for_full_service / 기대값 ready_for_full_service
- 차단 · 누락 로드뷰 원본: 70장 / 기대값 0장
- 차단 · 시각 검수 대기 장소: 17곳 / 기대값 0곳

## 비밀값 노출 방지

- 통과 · 비밀값 노출 검사: 0개 의심 파일 / 기대값 0개
