# 로드뷰 이미지 원본 제공 요청 문안

## 요청 대상

- 데이터명: 제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지
- 공공데이터포털 URL: https://www.data.go.kr/data/15110209/fileData.do
- 제공기관: 제주특별자치도
- 요청 목적: 접근성 여행 추천 서비스의 장소별 시각 검수 및 접근 동선 정보 검증

## 첨부 CSV

- `data/roadview_image_acquisition_priority_samples.csv`
  - 우선 검수 샘플 이미지 102장
  - 17개 서비스 시드 장소별 시각 검수에 바로 필요한 파일 목록
- `data/roadview_image_acquisition_full_request.csv`
  - 서비스 시드 17개 장소에 필요한 전체 이미지 1,023장
  - 우선 샘플과 보조 이미지 전체 목록
- `data/roadview_image_acquisition_place_summary.csv`
  - 장소별 이미지 수, 촬영일 범위, 좌표 범위 요약 17건

## 요청 본문

안녕하세요.

공공데이터포털에 등록된 `제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지` 데이터 활용을 요청드립니다.

저희 서비스는 교통약자, 회복기 여행자, 고령자, 보호자 동반 여행자 등 다양한 접근성 상황을 고려해 제주 여행지를 추천하는 서비스입니다. 현재 공개 메타데이터를 기준으로 17개 후보 장소를 먼저 검수하고 있으며, 장소별 출입구 단차, 경사, 바닥 상태, 주차장-출입구 연결 동선 등을 이미지로 확인하려고 합니다.

우선 검수에 필요한 이미지 파일명 102장과, 이후 서비스 시드 검증에 필요한 전체 이미지 파일명 1,023장을 CSV로 정리해 첨부드립니다. 가능하다면 첨부 목록 기준으로 이미지 원본을 제공 부탁드립니다. 부분 제공이 어렵다면 해당 데이터셋 전체 이미지 원본 제공도 가능합니다.

파일 수령 후에는 공공데이터 출처와 제공기관을 명시하고, 접근성 정보 검수 및 서비스 품질 개선 목적 범위에서 활용하겠습니다. 이미지 파일명은 메타데이터와 매칭해야 하므로 가능하면 원본 파일명을 유지해 전달 부탁드립니다.

감사합니다.

## 수령 후 내부 배치 위치

수령한 이미지는 원본 파일명을 유지해 아래 경로에 배치한다.

```text
data/raw/roadview_images/
```

배치 후 다음 명령으로 보유 여부를 재검사한다.

```bash
python scripts/build_roadview_image_asset_manifest.py --roadview-image-review data/roadview_image_review.json --asset-root data/raw/roadview_images --output data/roadview_image_asset_manifest.json --generated-at 2026-07-08
```
