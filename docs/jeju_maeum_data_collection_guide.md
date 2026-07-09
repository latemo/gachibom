# 제주의마음 여행 AI 장소 데이터 수집 가이드

## 1. 목적

장소 데이터는 추천 품질의 핵심이다.

이 서비스는 "좋은 장소"를 많이 모으는 것이 아니라, 사용자가 방문 전 판단할 수 있도록 접근성 근거와 불확실성을 정확히 기록해야 한다.

## 2. 우선 출처

1순위:

- 이지제주 EASYJEJU
- VISIT JEJU 모두를 위한 제주
- 열린관광 모두의 여행
- 제주특별자치도, 제주관광공사, 한국관광공사 등 공공기관 자료
- 제주특별자치도 사회적약자 시설 데이터(로드뷰) 구축 관광지 현황
- 제주특별자치도 사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터

2순위:

- 장소 공식 홈페이지
- 공공기관 보도자료
- 시설 운영기관 공지

3순위:

- 블로그, 후기, SNS

3순위 자료는 추천 근거로 직접 쓰지 않는다. 현장 변화 가능성, 사용자 체감, 사진 참고 용도로만 사용한다.

## 3. 수집 필수 항목

장소마다 최소한 아래 항목을 확인한다.

- 장소명
- 지역
- 카테고리
- 상황 태그
- 핵심 경험
- 추천 사용자군
- 피해야 할 사용자군
- 휠체어 접근 가능성
- 장애인 화장실
- 주차와 장애인 전용 주차구역
- 경사, 계단, 단차
- 휴식 공간
- 휠체어 또는 유아차 대여
- 바닥 상태
- 혼잡도 또는 혼잡 확인 필요 여부
- 출처명
- 출처 URL
- 조사일 또는 정보 확인일
- 운영자 메모

카테고리는 관광지만으로 제한하지 않는다. 식사 제한, 혼잡 민감, 날씨 민감 같은 조건을 반영하기 위해 `restaurant`, `food_market`, `shopping`, `medical_support` 같은 보조 카테고리도 사용할 수 있다.

상황 태그 예시:

- `food_focused`: 식사, 음식, 카페, 먹거리 중심
- `crowded_possible`: 혼잡 가능성이 큰 장소
- `short_stay`: 짧은 체류에 적합
- `long_walk`: 긴 이동 가능성이 큰 장소
- `weather_sensitive`: 날씨 영향을 많이 받는 장소
- `sensory_intense`: 강한 조명, 소리, 어두운 전시장 등 자극 가능성
- `low_stimulation`: 조용하고 자극이 낮은 장소
- `restroom_important`: 화장실 확인이 특히 중요한 장소

## 4. 상태 판단 기준

### verified

다음 조건을 대부분 만족할 때 사용한다.

- 공식 또는 공공 출처가 있다.
- 장애인 화장실, 주차, 경사/단차, 대여 여부 등 핵심 항목이 확인된다.
- 정보가 비교적 최근이다.
- 사용자에게 큰 위험이 되는 누락 정보가 적다.

### partial

다음 경우에 사용한다.

- 공식 출처는 있으나 조사일이 오래되었다.
- 주요 항목은 확인되지만 일부 핵심 정보가 빠져 있다.
- 특정 구간은 접근 가능하지만 다른 구간은 제한이 있다.
- 추천은 가능하지만 감점과 확인 필요 항목을 반드시 표시해야 한다.

### needs_check

다음 경우에 사용한다.

- 조사일이 오래되었다.
- 주차, 화장실, 경사, 대여 같은 핵심 항목이 빠져 있다.
- 접근 가능하다는 표현은 있으나 세부 동선이 부족하다.
- 사용자의 조건에 따라 위험할 수 있는 구간이 있다.
- 현장 운영 상태에 따라 접근성이 크게 달라질 수 있다.

### unavailable

다음 경우에 사용한다.

- 접근성 판단에 필요한 정보가 거의 없다.
- 출처 URL이 없거나 신뢰하기 어렵다.
- 장소가 폐업, 공사, 운영 중단 상태다.

## 5. 작성 원칙

- 확인한 사실만 `yes`로 적는다.
- 애매하면 `partial` 또는 `needs_check`로 적는다.
- 모르면 `unknown`으로 적는다.
- 정보가 부족한 장소는 높은 점수를 받을 수 없게 한다.
- 오래된 조사 정보는 그대로 두지 말고 운영자 메모에 조사 시점을 적는다.
- 안전에 영향을 주는 정보는 `safety_notes`에 반복해서 적는다.

사회적약자 시설현황 CSV를 사용할 때:

- 장애인 화장실 수, 장애인 주차장 수, 휠체어 대여 여부, 수유실, 휴게실은 공식 공공데이터 근거로 기록할 수 있다.
- 경사, 계단, 단차, 바닥 상태, 혼잡도는 이 CSV만으로 확정하지 않는다.
- 자동 생성 카드는 기본적으로 `partial` 또는 `needs_check`로 시작한다.
- 로드뷰 이미지와 이미지 메타데이터를 확인한 뒤 `surface_condition`, `slope_or_stairs`를 보강한다.
- 현재 운영 여부는 관광지 공식 페이지나 전화 확인으로 갱신한다.

## 6. 금지 사항

- 출처 없는 접근성 보장 표현 금지
- "휠체어 100% 가능" 같은 단정 금지
- 블로그 후기만으로 `verified` 처리 금지
- 장애인 화장실이 있다는 말만 보고 실제 사용 가능하다고 단정 금지
- 주차장이 있다는 말만 보고 입구까지 가까운 것으로 단정 금지
- 오래된 조사 자료를 최신 정보처럼 표시 금지

## 7. 현재 1차 데이터 상태

`data/jeju_accessible_spots.json`에는 43개 장소 카드가 있다.

현재 상태:

- verified: 5개
- partial: 30개
- needs_check: 8개
- active: 43개

`partial`이 많은 이유는 의도적이다. 공식 출처에서 핵심 정보와 위험 요소는 확인되지만, 조사일이 오래되었거나 일부 동선 정보가 부족한 장소를 무리하게 `verified`로 처리하지 않기 위해서다.

## 8. 다음 보강 목표

1차 보강 목표:

- verified 또는 partial 비율을 70% 이상으로 올린다.
- 휠체어 이용자에게 적합한 실내·짧은 야외 장소를 우선 보강한다.
- 회복 중 여행자에게 적합한 짧은 체류·휴식 가능 장소를 보강한다.
- 각 장소의 장애인 화장실 운영 여부와 주차장-입구 거리를 추가 확인한다.

우선 보강해야 할 필드:

- `crowd_level`
- `rest_area`
- `parking`
- `rental_or_assistance`
- `slope_or_stairs`
- `surface_condition`

## 9. 검증 명령

장소 카드 작성 후 다음 검증을 실행한다.

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schema = json.loads(Path('data/schemas/accessibility_place_card.schema.json').read_text(encoding='utf-8'))
items = json.loads(Path('data/jeju_accessible_spots.json').read_text(encoding='utf-8'))
validator = Draft202012Validator(schema)

for i, item in enumerate(items):
    errors = sorted(validator.iter_errors(item), key=lambda e: list(e.path))
    if errors:
        print('FAILED', i, item.get('id'))
        for err in errors:
            loc = '.'.join(str(p) for p in err.path) or '<root>'
            print(' ', loc, err.message)
        raise SystemExit(1)

print('SCHEMA_VALIDATION_OK', len(items))
'@ | python -
```

## 10. 출시 전 데이터 기준

제한 공개 전 최소 기준:

- 장소 카드 30개 이상
- 모든 장소에 출처 URL 있음
- 모든 장소에 안전 메모 있음
- 모든 장소가 JSON Schema 검증 통과
- verified 또는 partial 장소가 70% 이상
- needs_check 장소는 결과에서 확인 필요로 명확히 표시

현재 1차 데이터는 구조 기준과 verified/partial 비율 기준을 통과했다. 다음 보강은 `needs_check` 8개를 줄이고, 음식 제한·혼잡 민감·날씨 민감 같은 상황 태그를 더 촘촘히 채우는 작업이다.

사회적약자 시설현황 데이터 반영 후 추가 검수:

- `data/roadview_accessibility_cards.draft.json`은 초안 파일로 두고 운영자가 기존 카드와 병합한다.
- 동일 장소가 이미 `data/jeju_accessible_spots.json`에 있으면 새 카드로 중복 추가하지 말고 기존 카드의 화장실·주차·대여·휴식 필드를 보강한다.
- 새로 추가하는 장소는 출처, 확인일, 안전 메모가 모두 포함되어야 한다.
- `scripts/review_roadview_merge.py`로 병합 검수 리포트를 먼저 만든 뒤 `scripts/apply_roadview_safe_updates.py`로 보수적 자동 반영을 수행한다.
- `field_updates_available`은 보강 후보이며, 자동 반영은 충돌 없는 `yes` 근거만 허용한다.
- `no` 근거는 시설 미보유와 데이터 누락을 구분하기 어려우므로 자동 반영하지 않고 검수 큐로 보낸다.
- `needs_manual_review`는 이름 매칭이 애매하거나 기존 카드와 시설현황 값이 충돌하는 항목이므로 운영자가 출처와 현장을 다시 확인한다.
- 충돌 해소 판단은 `data/roadview_conflict_resolutions.json`에 남기고 `scripts/apply_roadview_conflict_resolutions.py`로 카드 운영 메모와 오픈 검수 큐에 반영한다.
- 불확실 매칭 판단은 `data/roadview_match_resolutions.json`에 남기고 `scripts/apply_roadview_match_resolutions.py`로 중복 추가 여부와 오픈 검수 큐를 정리한다.
- 신규 후보는 `scripts/triage_roadview_new_candidates.py`로 서비스 시드 후보, 카탈로그 후보, 현장검수 우선 후보로 분류하고, 시드 후보도 공개 전까지 `status=hidden` 검수용 파일로 유지한다.
- 서비스 시드 후보는 `scripts/review_service_seed_cards.py`로 공식 상세 출처, 로드뷰 이미지 검수 가능 여부, 경사·단차·바닥 상태 차단 사유를 먼저 확인한다.
- 실제 처리 작업은 `scripts/build_service_seed_work_queue.py`로 생성한 큐에서 `official_source_review`와 `roadview_image_review`를 우선 처리한다.
