# 제주의마음 관광약자 여행 지원 디렉터리 단계별 구현 명세

- 문서 버전: 1.0
- 확정일: 2026-07-14
- 상태: 구현 기준 확정
- 상위 기준: `jeju_maeum_integrated_commercialization_plan.md`, `jeju_maeum_service_foundation.md`

## 1. 목적

이 문서는 다음 다섯 요구사항을 현재 서비스에 안전하게 추가하기 위한 구현 기준이다.

1. 전동휠체어 급속충전기 위치정보
2. 가까운 종합병원급 이상 의료기관과 약국
3. 관광약자 이동지원 접수 연계
4. 제주특별자치도 교통약자 이동지원센터 이용 안내
5. 관광약자를 위한 복지·여행 지원 서비스

기존 1차 출시 범위는 병원 연계, 예약, 실시간 교통을 제외한다. 따라서 이 기능은 기존 추천 엔진의 범위를 조용히 넓히지 않고, 추천과 분리된 `여행 지원 디렉터리` 확장 기능으로 구현한다.

## 2. 핵심 결정

### 2.1 추천 장소와 지원 정보를 분리한다

신규 정보는 `data/jeju_accessible_spots.json`이나 추천 결과의 장소 배열에 넣지 않는다. 별도 `travel_support_directory` 계층을 사용한다.

분리 이유:

- 병원, 약국, 충전기, 지원센터는 여행 목적지가 아니라 안전·이동 지원 정보다.
- 현재 점수 엔진은 지원시설을 명시적으로 제외하지 않으므로 기존 장소 배열에 넣으면 추천 코스와 점수에 섞일 수 있다.
- 지원시설 핀이 기존 경유지 번호, 경로선, 지도 맞춤 범위에 영향을 주면 안 된다.

### 2.2 “대형병원”을 “종합병원급 이상”으로 정의한다

`대형병원`은 공식 의료기관 분류가 아니다. 내부 데이터와 화면 필터는 `종합병원급 이상`을 사용한다.

- HIRA `clCd=01`: 상급종합병원
- HIRA `clCd=11`: 종합병원
- 그 외 병원, 의원, 요양병원은 이 필터에 포함하지 않는다.

화면 제목은 `가까운 종합병원급 이상`으로 표시한다. 응급의료기관 여부는 병원 등급과 별도 속성으로 보여준다.

### 2.3 콜택시 연계와 이동지원센터는 같은 공식 서비스를 사용한다

별도의 공공 `관광약자 콜택시` 서비스는 확인되지 않았다. 공식 원장은 `제주특별자치도 교통약자 이동지원센터` 하나로 관리하고 화면 기능만 나눈다.

- `이동지원 접수 연결`: 코스 구간의 출발지·목적지를 확인하고 공식 전화·문자·웹 접수 채널로 인계
- `이동지원센터 안내`: 이용 대상, 회원등록, 준비서류, 요금, 운행범위, 제한사항 안내

동일 기관을 두 개의 서비스 레코드로 복제하지 않는다.

### 2.4 “근처” 기준을 고정한다

- 기본 기준점: 사용자가 선택한 관광지 또는 코스 경유지
- 코스 기준: 각 지원시설과 모든 코스 경유지의 직선거리 중 최솟값
- 현재 위치: 사용자가 `내 위치 기준`을 누르고 브라우저 권한을 허용한 경우만 사용
- 거리 계산: Haversine 직선거리
- 기본 반경: 20km
- 허용 반경: 1~50km
- 유형별 기본 노출: 최대 3개
- 반경 안에 결과가 없으면 유형별 가장 가까운 1개를 `설정 반경 밖`으로 명확히 표시할 수 있다.

도로거리나 예상 이동시간이 아니므로 모든 거리 옆에 `직선거리`를 표시한다.

### 2.5 현재 위치와 민감정보를 저장하지 않는다

- 위치 권한을 자동 요청하지 않는다.
- 현재 위치는 메모리에서 거리 계산에만 사용한다.
- localStorage, 공유 URL, 분석 이벤트, 서버 원문 로그에 좌표를 남기지 않는다.
- 이동지원 신청에 필요한 장애정보, 증빙서류, 진단서, 복지카드를 이 서비스가 수집하거나 업로드받지 않는다.
- API 요청 본문을 애플리케이션 로그에 기록하지 않는다.

### 2.6 실시간이라고 보장하지 않는다

- 충전기 데이터에는 고장, 점유, 실제 사용 가능 상태가 없다.
- HIRA 기본정보는 신고 반영 시차가 있을 수 있다.
- 약국 운영시간은 임시휴무와 현장 변경을 보장하지 않는다.
- 이동지원센터 접수 링크는 배차 완료나 예약 확정을 의미하지 않는다.

화면은 `사용 가능`, `예약 완료`, `배차 확정`을 근거 없이 표시하지 않는다.

## 3. 요구사항별 제품 범위

| 요구사항 | 사용자 기능 | 데이터 원장 | 현재 범위 |
| --- | --- | --- | --- |
| 전동휠체어 급속충전기 | 위치, 상세 설치장소, 운영시간, 관리기관, 전화 | 전국전동휠체어급속충전기표준데이터 | 등록 위치 안내, 실시간 고장·점유 제외 |
| 종합병원급 이상 | 가까운 순, 병원 분류, 전화, 주소, 응급기관 여부 | HIRA 병원정보 + 검수된 E-Gen 연결 | 의료 추천·진단 제외 |
| 약국 | 가까운 순, 전화, 주소, 운영시간, 확인 필요 상태 | HIRA 약국정보 + E-Gen 운영시간 | 유효한 당일 시간표가 있을 때만 `시간표상 영업 예정/종료` 계산 |
| 이동지원 접수 연결 | 코스 구간 확인 후 공식 전화·문자·웹 접수로 이동 | 제주 교통약자 이동지원센터 | 앱 내 예약·배차·결제 제외 |
| 이동지원센터 안내 | 자격, 등록절차, 서류, 요금, 운행범위, 제한 | 제주 교통약자 이동지원센터 | 자격 확정 판정과 서류 수집 제외 |
| 관광 복지·지원 | 여행 코디, 보장구 대여, 휠체어 대여, 기간형 혜택 | 이지제주·제주관광공사 등 공식 기관 | 공식 신청 채널 안내, 신청 대행 제외 |

## 4. 비범위

현재 명세에 포함하지 않는다.

- 앱 내부 콜택시 예약, 배차, 취소, 결제
- 배차 대기시간 또는 도착시간 예측
- 충전기 실시간 고장·점유 상태
- 병원 선택 추천, 의료 상담, 증상 분류, 응급도 판단
- 의료기관이나 약국의 영업·진료 가능 보장
- 이동지원센터 이용 자격 자동 승인
- 장애·건강 증빙서류 업로드 또는 보관
- 도로거리와 자동차 이동시간 계산
- 지원시설을 관광지 적합도 점수나 추천 순위에 반영
- 공식 협약이 없는 외부 서비스의 비공개 API 연동

응급환자나 긴급상황에는 지원 목록보다 `119` 안내를 우선한다.

## 5. 데이터 구조

### 5.1 저장 파일

```text
data/schemas/travel_support_directory.internal.schema.json
data/schemas/travel_support_directory.public.schema.json
data/travel_support_sources/chargers.json
data/travel_support_sources/medical.json
data/travel_support_sources/mobility_and_welfare.json
data/travel_support_directory.json
web/data/travel_support_directory.json
```

- `travel_support_sources/*`: 출처, 원본 식별자, 검수 메모를 포함한 내부 정규화 데이터
- `data/travel_support_directory.json`: 전체 통합 결과
- `web/data/travel_support_directory.json`: 비밀값과 내부 메모를 제거한 공개용 투영본
- 내부본과 공개본은 서로 다른 스키마로 검증한다. 공개본은 재귀적 필드 allowlist로 생성한다.
- 원본 API 키는 파일에 저장하지 않고 서버 환경변수로만 주입한다.

### 5.2 최상위 계약

```json
{
  "schema_version": "1.0.0",
  "generated_at": "2026-07-14T00:00:00+09:00",
  "coverage": {
    "region": "제주특별자치도",
    "status": "complete",
    "notes": []
  },
  "items": []
}
```

`coverage.status` 값:

- `complete`: 목표 출처를 정상 수집하고 필수 검사를 통과
- `partial`: 일부 출처 실패 또는 일부 지역·유형만 확보
- `unavailable`: 안전하게 공개할 데이터가 없음

형식 규칙:

- `schema_version`은 `^[0-9]+\.[0-9]+\.[0-9]+$` 형식이다.
- `generated_at`, `retrieved_at` 등 date-time은 timezone을 반드시 포함한다.
- 스키마 테스트는 JSON Schema format 검사를 활성화한다.

### 5.3 내부 공통 항목 계약

```json
{
  "id": "support:source:record-id",
  "resource_type": "power_wheelchair_fast_charger",
  "resource_kind": "facility",
  "name": "시설명",
  "summary": "사용자에게 보여줄 짧은 설명",
  "region": {
    "sido": "제주특별자치도",
    "sigungu": "제주시"
  },
  "service_area": ["제주특별자치도"],
  "location": {
    "latitude": 33.0,
    "longitude": 126.0,
    "point_role": "facility",
    "source_title": "좌표 출처명",
    "source_url": "https://example.go.kr",
    "match_method": "source_coordinate",
    "evidence_count": 1
  },
  "visit_info": {
    "address": null,
    "phone": null,
    "operating_hours": null,
    "official_url": null,
    "reservation_url": null,
    "service_status": "unknown",
    "notice": null,
    "verification_status": "needs_check",
    "last_verified_at": null,
    "source_updated_at": null,
    "missing_fields": [
      "address",
      "phone",
      "operating_hours",
      "official_url",
      "reservation_url"
    ],
    "evidence": []
  },
  "resource_verification": {
    "status": "needs_check",
    "checked_at": null,
    "source_updated_at": null,
    "stale_after_days": 30,
    "missing_fields": [],
    "evidence": []
  },
  "eligibility": [],
  "usage_steps": [],
  "cautions": [],
  "details": {},
  "sources": [
    {
      "provider": "기관명",
      "dataset_name": "데이터셋명",
      "record_id": "원본 식별자",
      "url": "https://example.go.kr",
      "license": null,
      "source_updated_at": null,
      "retrieved_at": "2026-07-14T00:00:00+09:00"
    }
  ]
}
```

고정 enum:

- `resource_type`: `power_wheelchair_fast_charger`, `hospital`, `pharmacy`, `mobility_support_center`, `tourism_welfare_service`
- `resource_kind`: `facility`, `service`, `program`
- `location.point_role`: `facility`
- `visit_info.service_status`: 기존 계약의 `active`, `temporarily_closed`, `permanently_closed`, `unknown`
- `visit_info.verification_status`: 기존 계약의 `verified`, `partial`, `needs_check`
- `resource_verification.status`: `verified`, `partial`, `needs_check`

조건부 필수 규칙:

- 충전기, 병원, 약국은 유효한 `location`이 필수다.
- 센터와 제주 전역 지원서비스는 `location=null`을 허용하되 `service_area`, 공식 연락처 또는 신청 URL이 필수다.
- 모든 항목은 `sources` 1개 이상, `retrieved_at`, `visit_info.verification_status`가 필수다.
- 제주 좌표 범위는 현재 프로젝트 기준과 동일한 위도 `32.8~34.0`, 경도 `125.8~127.2`를 사용한다.
- `id`는 빌드 간 안정적으로 유지하며 공개 후 원본 이름 변경만으로 재발급하지 않는다.
- `id`는 `^[A-Za-z0-9:_-]{1,120}$` 형식이다.
- 충전기·병원·약국은 `resource_kind=facility`, 이동지원센터는 `service`, 복지지원은 허용 subtype에 따라 `service` 또는 `program`만 허용한다.
- `visit_info` 검증은 주소·전화·운영시간·공식 URL 등 방문정보에 사용한다.
- `resource_verification`은 좌표, 병원 등급, 충전기 사양, 센터 자격·요금, 복지사업 기간처럼 유형별 핵심정보의 근거를 관리한다.
- `resource_verification.evidence[].fields`에는 `location`, `details.institution_class` 같은 공개 필드 경로를 넣고 출처 URL·확인일을 함께 저장한다.

### 5.4 공개 투영 계약

`web/data/travel_support_directory.json`과 API 응답의 `resource`는 공개 스키마를 따른다.

공개 허용:

- 안정 공개 ID, 이름, 유형, 요약, 지역, 서비스 범위
- 공개 좌표와 좌표 근거
- 공개 연락처·운영정보·공식 URL
- 이용자가 판단하는 데 필요한 자격·절차·주의사항
- 유형별 공개 `details`
- 출처명, 데이터셋명, URL, 라이선스, 갱신·수집 시각
- 공개 가능한 검증 상태와 근거

공개 금지:

- API 키와 환경변수 값
- 원본 응답 전문과 내부 검수 메모
- `sources.record_id`, HIRA 암호화 요양기호, E-Gen 내부 기관 ID
- 수동 검수 담당자 정보와 비공개 연결 판단
- 사용자의 위치·장애·회원등록 입력

유형별 공개 `details` allowlist:

- 충전기: 설치 위치 설명, 요일별 운영시간, 동시 사용 대수, 공기주입·휴대전화 충전, 관리기관
- 병원: `institution_class`, 검수된 `emergency.has_er`; `hira_id`, `egen_hpid`, `available_beds` 제외
- 약국: 요일별 시간표, `open_status`, `hours_retrieved_at`; 내부 요양기호 제외
- 이동지원센터: 공개 자격·절차·접수 채널·운영 모드·요금 원문·제한
- 관광 복지·지원: 공개 subtype·기간·신청 선행기간·준비사항·제한

공개 투영은 제거할 필드를 나열하는 denylist가 아니라 공개 스키마의 필드만 복사하는 재귀적 allowlist로 구현한다. 내부본과 공개본의 `generated_at`은 같아야 한다.

### 5.5 유형별 `details`

#### 전동휠체어 급속충전기

```json
{
  "installation_detail": null,
  "hours": {
    "weekday": { "open": null, "close": null },
    "saturday": { "open": null, "close": null },
    "holiday": { "open": null, "close": null }
  },
  "simultaneous_capacity": null,
  "air_injector": null,
  "phone_charging": null,
  "operator_name": null
}
```

충전기 장비의 실시간 상태 필드는 1차 계약에 두지 않는다. 시설 운영 상태는 `visit_info.service_status`로 관리하되 장비 고장·점유·충전 가능 상태를 뜻하지 않는다. `00:00~00:00`은 24시간 운영으로 자동 해석하지 않고 `운영시간 확인 필요`로 처리한다.

#### 종합병원급 이상

```json
{
  "hira_id": "암호화 요양기호",
  "institution_class": {
    "code": "11",
    "name": "종합병원"
  },
  "emergency": {
    "has_er": null,
    "egen_hpid": null,
    "available_beds": null,
    "observed_at": null
  }
}
```

- `institution_class.code`는 `01` 또는 `11`만 허용한다.
- HIRA와 E-Gen에는 공통 기관 ID가 없으므로 자동 유사명 매칭 결과를 바로 공개하지 않는다.
- 병원명·주소·전화 정규화 후 사람이 승인한 연결표만 `egen_hpid`에 반영한다.
- 실시간 가용병상은 1차 UI 비범위다. 향후 노출할 때는 조회 후 5분이 지나면 숨긴다.

#### 약국

```json
{
  "hira_id": "암호화 요양기호",
  "hours_by_day": {
    "mon": [], "tue": [], "wed": [], "thu": [],
    "fri": [], "sat": [], "sun": [], "holiday": []
  },
  "open_status": "unknown",
  "hours_retrieved_at": null
}
```

- `open_status`: `scheduled_open`, `scheduled_closed`, `unknown`
- 이 상태는 실시간 관측이 아니라 등록 시간표에 따른 계산임을 화면에 `시간표상 영업 예정/종료`로 표시한다.
- `scheduled_open` 또는 `scheduled_closed`는 E-Gen 시간표를 가져온 한국시간 날짜가 현재 날짜와 같고 가져온 지 24시간 이내인 실행에서만 계산한다.
- 한국시간 날짜가 바뀌거나 24시간 TTL이 먼저 끝나면 즉시 `unknown`으로 되돌린다.
- 정적 공개 JSON에는 `open_status=unknown`만 저장하고 서버·브라우저가 동일 규칙으로 계산한다.
- `00:00~00:00`은 24시간과 휴무 중 어느 뜻인지 자동 해석하지 않는다.
- 시간표 상태를 계산해도 `운영시간은 변경될 수 있으니 전화 확인`을 함께 표시한다.

#### 교통약자 이동지원센터

```json
{
  "preregistration_required": true,
  "required_documents": [],
  "intake_channels": [
    { "type": "phone", "value": "1899-6884" },
    { "type": "sms", "value": "010-6641-6884" },
    { "type": "web", "value": "https://www.jejuhappycall.com/" }
  ],
  "operating_area": ["제주특별자치도"],
  "excluded_areas": ["섬 지역"],
  "operation_modes": [
    {
      "mode": "immediate_call",
      "vehicle_hours": "365일 연중무휴 24시간 운행",
      "intake_hours": "당일 이용시간대 전화 및 웹 실시간 접수",
      "booking_lead_time": "당일",
      "limitations": []
    },
    {
      "mode": "multi_passenger",
      "vehicle_hours": "09:00~18:00",
      "intake_hours": "평일 월~금 09:00~18:00",
      "booking_lead_time": "이용일 7~2일 전",
      "limitations": [
        "휠체어 이용자 2명 이상",
        "1일 1회",
        "왕복 불가",
        "휠체어 미사용 단체 접수 불가"
      ]
    }
  ],
  "office_hours": null,
  "fare_display_text": "기본 10km 1,200원, 10~30km 거리요금 100원, 30~45km 거리요금 50원, 45km 초과 상한 4,000원. 거리요금 부과 단위는 공식 페이지에 명확하지 않아 센터 확인 필요.",
  "wheelchair_modes": [],
  "capacity_notes": [
    "휠체어 이용 시 본인 포함 최대 5명",
    "휠체어 미사용 시 본인 포함 최대 4명"
  ],
  "limitations": [
    "완전한 도움이 필요한 이용자는 보호자 또는 활동보조인 동승 필요",
    "왕복·경유 이용 조건과 중간 대기 제한은 공식 준수사항 확인 필요"
  ]
}
```

`vehicle_hours`, `intake_hours`, `office_hours`를 분리해 24시간 차량 운행을 센터 사무실 운영시간으로 오인하지 않게 한다. 일반 이용은 사전 회원등록 후 가능하며 관광객도 관광객이라는 이유만으로 자동 이용 대상이 아니다. 완전한 도움이 필요한 이용자는 보호자 또는 활동보조인 동승이 필요하다는 제한을 포함한다.

요금은 공식 표기문만 저장한다. 공식 페이지에서 거리요금 부과 단위가 명확하지 않으므로 앱이 예상요금을 계산하지 않는다.

#### 관광 복지·여행 지원

```json
{
  "provider_name": "기관명",
  "service_subtype": "travel_coordination",
  "valid_from": null,
  "valid_to": null,
  "program_status": "unknown",
  "application_lead_time": null,
  "required_documents": [],
  "limitations": []
}
```

- `program_status`: `planned`, `active`, `ended`, `unknown`
- `service_subtype`: `travel_coordination`, `power_mobility_aid_rental`, `wheelchair_rental`, `temporary_benefit`, `accessible_travel_information`, `publication`
- 기간형 사업은 `valid_from`, `valid_to`를 기준으로 자동 판정한다.
- 종료된 사업은 기본 목록에서 숨기고 `종료된 지원` 필터에서만 확인할 수 있다.
- 자격은 `해당 가능성이 있는 대상`으로 안내하며 서비스가 대상 여부를 확정하지 않는다.

초기 서비스 레코드의 고정 조건:

- 이지제주 여행 코디: 여행 시작 최소 15일 전 신청, 홈페이지 또는 `1566-4669`, 맞춤 코스 2~3안 제공, 실제 시설·차량 예약 대행 아님
- 이지제주 전동보장구 대여: 관광 목적 관광약자 대상, 전화 사전예약, 신분증·복지카드 지참, 센터 방문 후 약 15분 사용교육, 재고·비용·대여기간·운영시간은 전화 확인
- 제주관광정보센터 휠체어 무상 대여: 제주웰컴센터, 연중무휴 09:00~18:00, `064-740-6000`; 외부 반출 범위·재고·예약 가능 여부는 전화 확인

## 6. API 계약

### 6.1 엔드포인트

`POST /api/travel-support`

정적 기본 모드에서도 기능이 작동해야 하므로 API와 같은 계산을 `web/travel-support.js`에서 공개 JSON을 대상으로 수행한다.

### 6.2 요청

```json
{
  "points": [
    {
      "spot_id": "jeju_indoor_literature_022",
      "name": "제주문학관",
      "latitude": 33.4813072,
      "longitude": 126.5179884,
      "region": {
        "sido": "제주특별자치도",
        "sigungu": "제주시"
      }
    }
  ],
  "types": [
    "power_wheelchair_fast_charger",
    "hospital",
    "pharmacy",
    "mobility_support_center",
    "tourism_welfare_service"
  ],
  "radius_km": 20,
  "limit_per_type": 3
}
```

검증 규칙:

- `points`: 1~8개
- 각 `spot_id`: 1~80자 안전한 식별자
- 좌표: 제주 범위 안의 유한 숫자
- `region`: 선택값. 시군구 한정 서비스의 지역 매칭에 사용할 때 검증된 값이 필요
- `types`: 허용 enum의 중복 없는 비어 있지 않은 배열
- `radius_km`: 1~50, 기본 20
- `limit_per_type`: 1~5, 기본 3
- 지원하지 않는 필드와 과대 본문은 거부

현재 위치를 기준으로 요청하더라도 `points`에 임시 ID만 넣고 요청 본문을 기록하지 않는다. 1차 공개 데이터는 제주도 전역 서비스만 자동 매칭하며, 시군구 정보가 없을 때 좁은 지역 서비스의 `service_area_match`를 추정하지 않는다. 역지오코딩은 현재 범위에서 사용하지 않는다.

### 6.3 응답

```json
{
  "generated_at": "2026-07-14T00:00:00+09:00",
  "coverage": { "status": "complete", "notes": [] },
  "distance_method": "straight_line",
  "items": [
    {
      "resource": {
        "id": "support:public-id",
        "resource_type": "pharmacy",
        "resource_kind": "facility",
        "name": "약국명",
        "summary": "공개용 전체 항목",
        "region": {
          "sido": "제주특별자치도",
          "sigungu": "제주시"
        },
        "service_area": [],
        "location": {
          "latitude": 33.48,
          "longitude": 126.52,
          "point_role": "facility",
          "source_title": "공식 약국 위치정보",
          "source_url": "https://www.data.go.kr/data/15001673/openapi.do",
          "match_method": "source_coordinate",
          "evidence_count": 1
        },
        "visit_info": {
          "address": "제주특별자치도 제주시 예시로 1",
          "phone": "064-000-0000",
          "operating_hours": "공식 시간표 확인",
          "official_url": null,
          "reservation_url": null,
          "service_status": "active",
          "notice": "운영시간은 전화로 확인하세요.",
          "verification_status": "partial",
          "last_verified_at": "2026-07-14",
          "source_updated_at": "2026-07-14",
          "missing_fields": ["official_url", "reservation_url"],
          "evidence": []
        },
        "resource_verification": {
          "status": "partial",
          "checked_at": "2026-07-14",
          "source_updated_at": "2026-07-14",
          "stale_after_days": 7,
          "missing_fields": [],
          "evidence": []
        },
        "eligibility": [],
        "usage_steps": [],
        "cautions": [],
        "details": {
          "hours_by_day": {
            "mon": [], "tue": [], "wed": [], "thu": [],
            "fri": [], "sat": [], "sun": [], "holiday": []
          },
          "open_status": "unknown",
          "hours_retrieved_at": null
        },
        "sources": [
          {
            "provider": "건강보험심사평가원",
            "dataset_name": "약국정보서비스",
            "url": "https://www.data.go.kr/data/15001673/openapi.do",
            "license": "공공누리 제1유형",
            "source_updated_at": "2026-07-14",
            "retrieved_at": "2026-07-14T00:00:00+09:00"
          }
        ]
      },
      "proximity": {
        "distance_km": 1.2,
        "nearest_spot_id": "jeju_indoor_literature_022",
        "in_radius": true,
        "fallback_nearest": false,
        "service_area_match": null
      }
    }
  ],
  "warnings": []
}
```

처리 규칙:

- `resource`는 공개 스키마를 통과한 카드 전체 본문이며 API와 정적 계산이 동일한 결과 shape를 반환한다.
- 시설형은 모든 기준점까지 Haversine 거리를 다시 계산하고 최솟값을 사용한다.
- 같은 시설이 여러 경유점과 가까워도 한 번만 반환한다.
- 정렬은 `distance_km → id` 순으로 안정적으로 수행한다.
- 반경 결과가 없는 유형은 가장 가까운 1개를 `fallback_nearest=true`, `in_radius=false`로 반환할 수 있다.
- 지역 서비스형은 거리 대신 `service_area_match`를 반환한다.
- 영구 폐쇄와 종료 사업은 기본 응답에서 제외한다.
- malformed 선택 데이터 때문에 서버 전체가 중단되면 안 된다. 해당 기능만 비활성화하고 health에 상태를 표시한다.

거리 계산 상수:

- 평균 지구 반지름: `6371.0088km`
- 내부 계산: 반올림하지 않은 배정밀도
- API `distance_km`: 소수 셋째 자리 반올림
- 화면 표시: 소수 첫째 자리
- 반경 경계: `distance_km <= radius_km` 포함
- 유형별 처리 순서: 유효 항목 → 폐쇄 제외 → 중복 제거 → 거리 계산 → 반경 분리 → 안정 정렬 → limit → 결과가 없을 때 fallback 1개

### 6.4 오류와 fallback

- 잘못된 타입, 좌표, 반경, 개수: `400 invalid_request`
- 지원 데이터 준비 안 됨: `503 travel_support_unavailable`
- 내부 예외, 파일 경로, API 키는 응답에 노출하지 않는다.
- API 실패 시 `web/data/travel_support_directory.json`과 동일한 클라이언트 계산으로 전환한다.
- 마지막 성공본을 사용할 때 `최종 갱신 시각`과 `일부 정보가 오래되었을 수 있음`을 표시한다.

## 7. 화면 명세

### 7.1 진입점

1. 장소 상세의 `가까운 여행 지원`
2. 실제 경로 모달의 `지원시설 보기`
3. 저장 코스의 `여행 지원 체크`
4. 관광공사 코스의 `코스 주변 지원정보`

### 7.2 지원 패널

탭:

- `충전기`
- `종합병원급 이상`
- `약국`
- `이동지원`
- `여행 복지·지원`

시설 카드 필수 표시:

- 이름과 유형
- 기준 장소와 직선거리
- 주소와 전화
- 상세 설치 위치 또는 의료기관 공식 분류
- 운영시간과 정보 기준일
- 검증 상태
- 공식 출처
- `전화 확인`, `공식 정보 보기` 행동

지원서비스 카드 필수 표시:

- 공식 기관명
- 대상과 사전등록 필요 여부
- 신청 절차와 준비서류
- 운영범위·제한·예약 선행기간
- 전화·문자·공식 웹 행동
- 확인일과 공식 출처

### 7.3 지도 불변조건

- 지원 핀은 별도 Leaflet layer에 렌더링한다.
- 추천 경유지 숫자를 지원 핀에 사용하지 않는다.
- 지원 핀은 `selectedRoute`, 도로 geometry, 코스 점수, 추천 순서에 넣지 않는다.
- 지원 핀을 켜거나 꺼도 기존 경로선과 추천 마커 좌표가 변하지 않는다.
- 지도 `fitBounds`는 기존 추천 경유지를 기준으로 유지한다.
- 지도 타일이 실패해도 텍스트 목록은 계속 제공한다.
- 핀은 색상뿐 아니라 아이콘, 텍스트, 스크린리더 레이블로 구분한다.

### 7.4 이동지원 접수 인계

구간별 `이동지원 연결` 버튼을 누르면 다음 임시 정보를 보여준다.

- 출발지와 목적지
- 센터 회원등록 여부
- 휠체어 유형: 없음, 수동, 전동
- 이용자 수와 동행인 수
- 필요한 도움 여부

행동 버튼:

- `전화로 공식 접수`
- `공식 웹 접수로 이동`
- `문자 문의 작성`

금지:

- 버튼명을 `예약하기`로 표시
- 공식 응답 전 `예약 완료`, `배차 확정` 표시
- 문자 양식이 공식 확인되지 않은 상태에서 자동 발송
- 입력 내용을 URL, 저장 코스, 분석 로그에 보존

필수 문구:

> 이 기능은 예약·배차 확정이 아니라 공식 기관 접수 채널로 연결합니다. 이용 전 사전 회원등록과 이용 자격 확인이 필요합니다. 관광객도 자동 이용 대상이 아닙니다. 배차 가능 여부와 대기시간은 이동지원센터에서 최종 확인하세요.

### 7.5 의료·약국 안전 문구

> 이 정보는 의료기관·약국 위치 확인을 돕기 위한 것이며 의료 판단이나 진료·영업 가능을 보장하지 않습니다. 운영 여부를 전화로 확인하고, 응급환자·긴급상황은 119에 연락하세요.

### 7.6 접근성 기준

- 모든 행동은 키보드로 접근 가능
- 포커스 순서가 탭 → 목록 → 외부 행동 순으로 예측 가능
- 터치 영역 최소 44×44px
- 새 창·전화·문자 행동을 접근성 이름에 명시
- 거리, 상태, 경고를 색상만으로 구분하지 않음
- 데이터가 없을 때 `없음`이 아니라 `현재 데이터 범위에서 확인되지 않음`으로 표시

## 8. 공식 출처와 갱신 정책

| 데이터 | 1차 출처 | 보강 출처 | 제품 갱신 목표 | 오래됨 판정 |
| --- | --- | --- | --- | --- |
| 전동휠체어 급속충전기 | [전국 표준데이터](https://www.data.go.kr/data/15034533/standard.do) | [제주장애인자립생활센터 목록](https://jcil.or.kr/mobile/pgm/charger.php), 검수 참고만 | 주 1회 수집, 월별 변경 탐지 | 원본 기준일 210일 초과 |
| 종합병원급 이상 | [HIRA 병원정보서비스](https://www.data.go.kr/data/15001698/openapi.do) | [E-Gen 응급기관 기본정보](https://www.data.go.kr/data/15096291/standard.do); 실시간 가용병상은 [별도 OpenAPI](https://www.data.go.kr/data/15000563/openapi.do)이며 1차 비노출 | 일 1회 기본정보 수집 | 마지막 성공 7일 초과 |
| 약국 | [HIRA 약국정보서비스](https://www.data.go.kr/data/15001673/openapi.do) | [국립중앙의료원 약국 정보](https://www.data.go.kr/data/15000576/openapi.do) | 일 1회, 운영시간 당일 동기화 시 상태 계산 | 마지막 성공 7일 초과 |
| 이동지원센터 | [센터 메인](https://www.jejuhappycall.com/), [이용 안내](https://www.jejuhappycall.com/?mcode=guide01), [회원등록](https://www.jejuhappycall.com/?mcode=guide02) | [접수 방법](https://www.jejuhappycall.com/?mcode=guide03) | 주 1회 변경 확인, 월 1회 수동 검수 | 검수 30일 초과 |
| 관광 복지·지원 | [이지제주](https://easyjeju.net/), [여행 코디](https://easyjeju.net/pages.php?p=3_2_1_1), [전동보장구 대여](https://easyjeju.net/pages.php?p=3_1_1_1) | [제주관광공사](https://www.visitjeju.net/), [제주관광정보센터](https://www.ijto.or.kr/korean/index.php?cid=38) | 주 1회, 기간형은 매일 상태 계산 | 활성 사업 검수 14일 초과 |

운영 주기는 공급기관의 공식 갱신주기와 별개인 우리 서비스의 점검 목표다.

수집 엔드포인트:

```text
충전기  https://api.data.go.kr/openapi/tn_pubr_public_electr_whlchairhgh_spdchrgr_api
병원    https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList
약국    https://apis.data.go.kr/B551182/pharmacyInfoService/getParmacyBasisList
약국시간 https://apis.data.go.kr/B552657/ErmctInsttInfoInqireService/getParmacyListInfoInqire
응급정보 https://apis.data.go.kr/B552657/ErmctInfoInqireService
```

`Parmacy`는 공식 경로의 오탈자이므로 수정하지 않는다.

출처별 주의사항:

- 전국 충전기 표준데이터는 반기 갱신이며 개별기관 등록분이 매월 초 통합되어 시차가 생길 수 있다.
- 통합 충전기 페이지에는 이용허락범위가 명확하지 않다. 공개 전 통합 API와 제주 제공기관의 이용조건을 확인하며, 확인 전에는 `license=null`과 출처표시를 유지한다.
- 충전기 보완 목록은 API·라이선스·갱신일이 명확하지 않아 기본 원장으로 사용하지 않는다.
- HIRA 병원·약국은 운영계정 심의와 공공누리 제1유형 출처표시가 필요하다.
- HIRA와 E-Gen의 기관 ID가 달라 연결표 검수가 필요하다.
- E-Gen 기본 응급기관 표준데이터와 실시간 가용병상 OpenAPI를 구분한다. E-Gen 미매칭은 `has_er=false`가 아니라 `null`이다.
- 이지제주에는 여행 코디, 전동보장구 대여, 접근성 관광정보가 있으나 실제 재고·비용·운영시간이 없는 항목은 전화 확인으로 표시한다.
- 2026 열린관광 페스타처럼 종료일이 지난 혜택은 현재 혜택으로 노출하지 않는다.

## 9. Phase별 작업 명세

### Phase 0 — 계약과 공개 게이트 고정

목표: 병렬 구현 전에 데이터·용어·안전 경계를 하나로 고정한다.

작업:

- `docs/jeju_maeum_travel_support_phase_spec.md` 승인
- 내부용·공개용 `travel_support_directory` 스키마 작성
- 다섯 `resource_type`별 유효·무효 fixture 작성
- 출처, 최신성, 폐쇄·종료 상태, 공개 투영 규칙 작성
- API 요청·응답 계약 테스트 골격 작성
- API 개발키 신청과 운영계정 심의 일정 등록
- 비밀키 환경변수 이름만 문서화하고 값은 저장하지 않음

예정 파일:

```text
data/schemas/travel_support_directory.internal.schema.json
data/schemas/travel_support_directory.public.schema.json
data/fixtures/travel_support/valid/*.json
data/fixtures/travel_support/invalid/*.json
tests/test_travel_support_schema.py
```

완료 기준:

- 모든 타입의 유효·무효 fixture가 예상대로 판별된다.
- 시설형과 지역 서비스형의 위치 조건이 구분된다.
- `종합병원급 이상`, `급속충전기`, `시간표상 영업 예정`, `접수 연결`의 의미가 모호하지 않다.
- 모든 공개 항목에 출처와 확인 상태가 존재한다.
- 내부 핵심정보는 `resource_verification`으로 검증되고 공개본은 재귀적 allowlist를 통과한다.
- 추천 장소·점수·경로 계약을 바꾸지 않는다.

Phase 0가 통과하기 전 Phase 1의 통합 JSON과 UI를 만들지 않는다.

### Phase 1 — 데이터 수집·정규화 병렬 배치

목표: 세 데이터 묶음을 충돌 없이 동시에 구축한다.

#### Agent A — 충전기

- 전국 표준 API 응답을 제주 데이터로 필터링
- 주소, 좌표, 상세 설치 위치, 운영시간, 관리기관 정규화
- 좌표를 `latitude → latitude`, `longitude → longitude`로 고정 매핑
- 공급원에 존재하는 운영시간 오탈자 필드(`weekdayOperColseHhmm`, `satOperOperOpenHhmm`, `holidayCloseOpenHhmm` 등)까지 fixture로 고정하고 `00:00~00:00`을 24시간으로 해석하지 않음
- 정규화 이름+주소 또는 50m 이내 중복 탐지
- 기준일이 오래된 레코드 경고
- 주요 지점 최소 10곳 표본 검수 큐 작성

소유 파일:

```text
scripts/import_wheelchair_chargers.py
data/travel_support_sources/chargers.json
tests/test_wheelchair_charger_import.py
```

#### Agent B — 병원·약국

- HIRA `clCd in {01, 11}`만 병원으로 정규화
- 제주 약국 기본정보 정규화
- HIRA 좌표를 `XPos → longitude`, `YPos → latitude`로 고정 매핑
- E-Gen 좌표를 `wgs84Lon → longitude`, `wgs84Lat → latitude`로 고정 매핑
- E-Gen 약국 시간을 `dutyTime1s/c`부터 `dutyTime8s/c`까지 월~일·공휴일로 명시 매핑
- E-Gen 시간표 보강과 모호한 병합의 수동 검수 큐 생성
- HIRA↔E-Gen 검수 연결표 작성
- 시간표 상태와 응급 속성의 시간 유효성 검사

소유 파일:

```text
scripts/import_medical_support.py
data/travel_support_sources/medical.json
data/travel_support_sources/medical_source_links.json
tests/test_medical_support_import.py
```

#### Agent C — 이동·복지서비스

- 이동지원센터 공식 레코드 1개 작성
- 자격, 등록절차, 준비서류, 요금 원문, 운행범위, 접수 채널 정규화
- 이지제주 여행 코디·전동보장구 대여 등 이용자 대상 서비스 정규화
- 기간형 사업의 예정·진행·종료 판정
- 사업자 대상 지원과 관광객 대상 지원을 구분

소유 파일:

```text
data/travel_support_sources/mobility_and_welfare.json
tests/test_mobility_welfare_sources.py
```

#### 통합 담당

- 세 source 파일을 읽는 결정적 빌더 작성
- 내부 데이터와 공개 투영본을 함께 생성
- 공개본에서 내부 메모, API 키, 비공개 식별자 제거
- ID 중복, 좌표 범위, 필수 출처, 타입별 필드 검사
- 수집·정규화·두 스키마 검증을 모두 통과한 뒤 임시 파일을 원자적으로 교체
- 실패한 실행은 기존 source·통합본·공개본을 덮어쓰지 않음
- 동일 입력은 안정 정렬을 거쳐 byte 수준으로 동일한 JSON을 생성
- 네트워크 의존 테스트 대신 저장된 fixture만 사용

소유 파일:

```text
src/travel_support.py
scripts/build_travel_support_directory.py
data/travel_support_directory.json
web/data/travel_support_directory.json
tests/test_travel_support.py
```

완료 기준:

- ID 중복 0건
- 제주 범위 밖 공개 좌표 0건
- 이름·타입·출처 누락 0건
- 병원 `clCd`가 01 또는 11이 아닌 결과 0건
- 내부 메모와 비밀값의 공개 JSON 노출 0건
- 공개 JSON의 모든 중첩 필드가 공개 스키마 allowlist 안에 있음
- 부분 수집이면 `coverage=partial` 표시
- 수집 실패 시 마지막 성공본을 보존
- 충전기 공개 전 통합 API와 제주 제공기관 이용조건 확인 또는 `license=null`과 출처표시 유지

### Phase 2 — 도메인 로직과 API

목표: 정적 모드와 서버 모드가 같은 최근접 결과를 반환한다.

작업:

- Haversine 거리, 경로 전체 최근접, 중복 제거, 반경, 안정 정렬 구현
- `POST /api/travel-support` 구현
- 로컬 서버와 Vercel 어댑터의 동일 응답 계약 구현
- health에 `features.travel_support`와 데이터 갱신 상태 추가
- 정적 공개본을 위한 순수 클라이언트 계산 함수 작성
- 지원 디렉터리를 추천 런타임과 분리된 optional loader로 로드
- 지원 데이터가 malformed여도 추천·경로·기존 health는 정상 유지하고 지원 API만 503 처리
- 정적 지원 JSON도 별도 `try/catch`로 로드해 실패가 앱 전체 초기화를 막지 않게 함
- Vercel 하이픈 URL을 밑줄 파일로 명시 매핑하고 런타임 데이터 포함 규칙 갱신

예정 파일:

```text
src/travel_support.py
api/travel_support.py
src/recommendation_api.py
src/vercel_api.py
vercel.json
.vercelignore
web/travel-support.js
tests/test_travel_support_api.py
tests/test_travel_support_frontend.py
tests/test_deployment_config.py
```

Vercel 필수 설정:

```json
{ "src": "/api/travel-support", "dest": "/api/travel_support.py" }
```

- `vercel.json`의 `includeFiles`에 `data/travel_support_directory.json` 추가
- `.vercelignore`에 `!data/travel_support_directory.json` 예외 추가
- 배포 테스트의 런타임 파일 allowlist 갱신

완료 기준:

- 서버와 브라우저 계산 거리 차이가 1% 또는 20m 이내다.
- 같은 시설은 코스당 한 번만 반환된다.
- 잘못된 타입·좌표·반경·개수는 400을 반환한다.
- 로컬과 Vercel 응답이 동일하다.
- API 실패 시 정적 데이터 계산으로 전환된다.
- 비밀값과 내부 예외가 응답에 노출되지 않는다.
- malformed 지원 데이터에서는 `features.travel_support=false`, 지원 API 503, 기존 추천·경로 API 정상 상태가 된다.
- health에는 `coverage`, `generated_at`, `load_status`가 표시된다.
- 정적 지원 JSON 로드 실패가 추천 화면을 오류 상태로 바꾸지 않는다.

### Phase 3 — 추천 지도·장소 상세·경로 모달

목표: 지원정보를 기존 추천 경험을 깨지 않고 노출한다.

작업:

- 장소 상세에 가까운 충전기·병원·약국 각 최대 3개 표시
- 경로 모달에 지원시설 핀 레이어와 필터 추가
- 이동지원센터와 관광 복지서비스 카드 추가
- 코스 구간별 공식 접수 인계 화면 추가
- 출처, 확인일, 직선거리, 운영 재확인 문구 표시
- API/정적/지도 타일 실패 상태 구현

예정 파일:

```text
web/index.html
web/app.js
web/styles.css
web/travel-support.js
tests/test_saved_trips_frontend.py
tests/test_travel_support_frontend.py
```

완료 기준:

- 지원 핀을 켜도 기존 경로선과 추천 마커 위치가 변하지 않는다.
- 지원 핀이 추천 경유지 번호를 받지 않는다.
- 지원정보가 코스 점수와 순서를 바꾸지 않는다.
- 정적 모드와 API 모드 모두 표시된다.
- 지도 타일 실패 시 목록은 표시된다.
- 외부 URL, 전화, 마크업이 안전하게 렌더링된다.
- 접수 전 `예약 완료`나 `배차 확정`을 표시하지 않는다.
- 390px 모바일과 키보드·스크린리더 흐름을 통과한다.

현재 `web/app.js`, `web/index.html`, `web/styles.css`, `tests/test_saved_trips_frontend.py`에는 기존 지도 정렬 작업 변경이 있다. Phase 3에서는 이 파일들을 한 명이 전담하고 기존 변경을 보존한다.

Phase 3 시작 전 기존 지도 정렬 변경을 먼저 검토·테스트하고 체크포인트 커밋으로 분리한다. 이후 `web/travel-support.js`는 Agent C 한 명, 기존 `app.js`·HTML·CSS는 메인 담당 한 명만 수정한다.

### Phase 4 — 저장 코스·관광공사 코스 통합

목표: 저장·공유 계약을 늘리지 않고 코스마다 최신 지원정보를 계산한다.

작업:

- 저장 코스를 열 때 현재 경유지 좌표로 지원정보 재계산
- 저장 체크리스트에 충전기 확인, 이동지원 등록·접수, 복지서비스 확인 추가
- 관광공사 코스의 경유지 ID를 기존 seed 좌표와 조인해 지원 패널 표시
- 코스 순서 변경 시 최근접 결과 재계산

고정 규칙:

- 지원시설 ID와 상세정보를 localStorage에 복제하지 않는다.
- 공유 URL에는 기존처럼 관광지 ID만 포함한다.
- 오래된 지원정보는 열 때 최신 공개본에서 다시 읽는다.

완료 기준:

- 저장 코스 순서를 바꾸면 기준 장소와 최근접 결과가 갱신된다.
- 기존 저장·공유 URL 계약이 변하지 않는다.
- 사용할 수 없는 관광지가 있어도 지원 목록 계산은 계속된다.
- 관광공사 코스 검색·필터·이전·다음 동작에 회귀가 없다.

### Phase 5 — 품질·브라우저·운영 게이트

목표: 고위험 정보와 기존 지도 기능을 함께 검증한 뒤 공개한다.

자동 검증:

- 데이터 스키마와 조건부 필수값
- import 결정성·중복·좌표 범위·오래됨 판정
- API 입력 검증·거리·반경·정렬·fallback
- 정적 모드와 API 모드 동일성
- 저장 코스·추천 지도 회귀
- URL·HTML 안전성
- 현재 위치 비저장 정책
- 공개 지원 JSON의 존재·스키마·내부본과 생성시각 일치 사전점검
- Vercel 런타임 파일 allowlist와 정적 스크립트 캐시 버전

운영 문서·점검:

- `src/service_preflight.py`에 공개 지원 JSON 검사를 추가한다.
- `data_request_tracker`에 공식 데이터 개발·운영 승인 상태를 기록한다.
- `web/README.md`에 정적 데이터와 API 모드 실행 기준을 추가한다.
- 지원 스크립트·JSON 변경 시 캐시 버전을 갱신하는 규칙을 고정한다.

브라우저 시나리오:

1. 추천 장소 상세에서 가까운 충전기·병원·약국을 확인한다.
2. 코스 지도에서 지원 레이어를 켜고 기존 경로선·4개 마커가 변하지 않는지 확인한다.
3. 위치 권한을 거부해도 선택 장소 기준 기능이 작동하는지 확인한다.
4. API를 실패시켜 정적 fallback과 최종 갱신 시각을 확인한다.
5. 종료된 기간형 혜택이 활성 혜택에 노출되지 않는지 확인한다.
6. 미등록 사용자가 이동지원 접수 전에 회원등록 안내를 보는지 확인한다.
7. 데스크톱과 390px 모바일에서 키보드·포커스·터치 영역을 확인한다.
8. 지도 타일 실패 시 지원 목록이 남는지 확인한다.

출시 기준:

- 출처 표시율 100%
- 확인일 또는 확인 필요 문구 표시율 100%
- 추천 경로·점수 오염 0건
- 현재 위치 영구 저장 0건
- 종료된 혜택의 활성 오표시 0건
- 근거 없는 `영업 중`, `사용 가능`, `예약 완료`, `배차 확정` 0건
- 전체 자동 테스트 통과
- 데스크톱·모바일 브라우저 수용 시나리오 통과

## 10. 병렬 작업 운영안

4개 동시 작업 슬롯 기준으로 다음 순서를 사용한다.

### Wave 0 — 계약 고정

- 메인 담당: Phase 0 스키마·fixture·안전 문구 확정
- 서브 에이전트: 공식 API 샘플과 필드 매핑 재확인

### Wave 1 — 데이터 3개 트랙 병렬

- Agent A: 충전기
- Agent B: 병원·약국
- Agent C: 이동지원·복지
- 메인 담당: 통합 빌더, 공개 투영, 리뷰

### Wave 2 — 구현 3개 트랙 병렬

- Agent A: `src/travel_support.py`, `tests/test_travel_support.py`
- Agent B: API wrapper, 로컬 서버, Vercel·배포 설정, `tests/test_travel_support_api.py`, `tests/test_deployment_config.py`
- Agent C: `web/travel-support.js`, `tests/test_travel_support_frontend.py`
- 메인 담당: 기존 `web/app.js`, `web/index.html`, `web/styles.css`, 저장 코스 회귀 테스트

### Wave 3 — 검증 3개 트랙 병렬

- Agent A: 데이터·API 회귀
- Agent B: 저장·관광공사 코스 회귀
- Agent C: 데스크톱·모바일 브라우저 검증
- 메인 담당: 이슈 통합, 전체 테스트, 출시 게이트 판정

충돌 방지 규칙:

- 각 데이터 에이전트는 자기 source 파일만 수정한다.
- 통합 JSON은 손으로 편집하지 않고 빌더만 생성한다.
- `web/app.js`, `web/index.html`, `web/styles.css`는 한 Wave에서 한 명만 수정한다.
- 에이전트 결과는 테스트와 출처를 포함해야 하며 메인 담당이 통합 전 diff를 검토한다.

## 11. 바로 다음 실행 배치

다음 작업은 Phase 0이며 순서는 고정한다.

1. 내부용·공개용 `travel_support_directory` 스키마 작성
2. 다섯 타입의 유효·무효 fixture 작성
3. 조건부 필수값과 공개 투영 테스트 작성
4. 세 source 파일의 빈 골격과 책임 경계 작성
5. 공공데이터 개발키 신청 항목과 운영 심의 의존성 기록
6. Phase 0 테스트 통과 후 Wave 1의 세 에이전트 시작

Phase 0에서는 실제 지도 UI를 수정하지 않는다. 데이터 계약을 먼저 고정한 뒤 Phase 1부터 병렬 구현한다.
