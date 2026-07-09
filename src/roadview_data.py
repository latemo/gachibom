"""Import helpers for Jeju social-vulnerable roadview public datasets."""

from __future__ import annotations

import csv
import re
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.catalog import clean, infer_region, parse_float
from src.catalog_providers import read_value


FACILITY_STATUS_SOURCE_URL = "https://www.data.go.kr/data/15109153/fileData.do"
IMAGE_METADATA_SOURCE_URL = "https://www.data.go.kr/data/15109158/fileData.do"
ROADVIEW_IMAGE_SOURCE_URL = "https://www.data.go.kr/data/15110209/fileData.do"
ROADVIEW_API_SOURCE_URL = "https://www.data.go.kr/data/15109149/openapi.do?recommendDataYn=Y"


def load_csv_rows(path: str | Path, *, encoding: str = "utf-8-sig") -> list[dict[str, str]]:
    with Path(path).open("r", encoding=encoding, newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(items: list[dict[str, Any]], output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def facility_rows_to_accessibility_cards(
    rows: Iterable[Mapping[str, str]],
    *,
    checked_at: date,
    source_url: str = FACILITY_STATUS_SOURCE_URL,
) -> list[dict[str, Any]]:
    return [
        facility_row_to_accessibility_card(row, checked_at=checked_at, source_url=source_url)
        for row in rows
        if facility_name(row)
    ]


def facility_row_to_accessibility_card(
    row: Mapping[str, str],
    *,
    checked_at: date,
    source_url: str = FACILITY_STATUS_SOURCE_URL,
) -> dict[str, Any]:
    name = facility_name(row) or ""
    seq = parse_int(read_value(row, ["SEQ", "순번"])) or 0
    address = read_value(row, ["TOURIST_ADDR", "관광지 주소", "관광지주소", "주소"])
    toilet_count = parse_int(read_value(row, ["TOURIST_DTOIL", "장애인 화장실", "장애인화장실"]))
    parking_count = parse_int(read_value(row, ["TOURIST_DPARK", "장애인 주차장", "장애인주차장"]))
    wheelchair_rental = read_yes_no(row, ["TOURIST_LNET", "휠체어 대여 여부", "휠체어대여여부"])
    nursing_room = read_yes_no(row, ["TOURIST_NURSING", "관광지 수유실 보유", "수유실"])
    rest_room = read_yes_no(row, ["TOURIST_REST", "휴게실 보유", "휴게실"])

    missing_fields = ["slope_or_stairs", "surface_condition", "crowd_level"]
    if toilet_count is None:
        missing_fields.append("accessible_toilet")
    if parking_count is None:
        missing_fields.append("parking")
    if wheelchair_rental is None:
        missing_fields.append("rental_or_assistance")
    if rest_room is None:
        missing_fields.append("rest_area")

    return {
        "id": make_card_id(name, seq),
        "name": name,
        "region": infer_region(address) or "제주특별자치도",
        "category": infer_basic_category(name),
        "situation_tags": build_situation_tags(nursing_room, rest_room),
        "summary": build_facility_summary(name, toilet_count, parking_count, wheelchair_rental, nursing_room, rest_room),
        "recommended_for": ["wheelchair_user", "senior", "stroller_family", "caregiver_group"],
        "avoid_for": [
            "경사·단차·바닥 상태를 현장 확인하지 않고 방문하기 어려운 사용자",
            "최신 운영 여부 확인 없이 장애인 화장실이나 대여 서비스가 필수인 사용자",
        ],
        "accessibility": {
            "wheelchair_access": {
                "state": "partial",
                "note": "사회적약자 시설 로드뷰 구축 대상 관광지이나 실제 동선의 경사·단차·바닥 상태는 추가 확인 필요",
                "source_ref": "jeju_roadview_facility_status",
            },
            "accessible_toilet": count_field_state(
                toilet_count,
                "장애인 화장실 보유 수",
                "jeju_roadview_facility_status",
            ),
            "parking": count_field_state(
                parking_count,
                "장애인 주차장 보유 수",
                "jeju_roadview_facility_status",
            ),
            "slope_or_stairs": {
                "state": "needs_check",
                "note": "시설 현황 CSV에는 경사·계단·단차 세부 정보가 없어 로드뷰 이미지 또는 현장 확인 필요",
                "source_ref": None,
            },
            "rest_area": yes_no_field_state(rest_room, "휴게실 보유 여부", "jeju_roadview_facility_status"),
            "rental_or_assistance": yes_no_field_state(
                wheelchair_rental,
                "휠체어 대여 가능 여부",
                "jeju_roadview_facility_status",
            ),
            "surface_condition": {
                "state": "needs_check",
                "note": "바닥 상태는 이미지 메타데이터와 로드뷰 이미지 검수 후 판단 필요",
                "source_ref": "jeju_roadview_image_metadata",
            },
            "crowd_level": {
                "state": "unknown",
                "note": "혼잡도 정보는 이 데이터셋에 포함되지 않음",
                "source_ref": None,
            },
        },
        "effort": {
            "walking_level": "unknown",
            "recommended_duration_minutes": None,
            "outdoor_exposure": "unknown",
            "weather_sensitivity": "unknown",
        },
        "sources": [
            {
                "title": "제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
                "url": source_url,
                "type": "public_agency",
            }
        ],
        "verification": {
            "status": "partial" if len(missing_fields) <= 4 else "needs_check",
            "checked_at": checked_at.isoformat(),
            "checked_by": "public_data_import",
            "missing_fields": sorted(set(missing_fields)),
        },
        "status": "active",
        "safety_notes": [
            "이 데이터는 107개 관광지의 사회적약자 시설 현황으로, 현재 운영 여부와 현장 접근성을 보장하지 않음",
            "장애인 화장실, 장애인 주차장, 휠체어 대여는 방문 전 공식 문의로 재확인 필요",
            "경사·단차·바닥 상태는 로드뷰 이미지 또는 현장 검수 후 보강 필요",
        ],
        "operator_notes": (
            "공공데이터포털 15109153 시설 현황 기반 자동 생성 카드. "
            "사회적 약자 시설물 현황은 구역 단위로 수집되었으며 전화번호 누락 가능성이 있음."
        ),
    }


def metadata_rows_to_records(
    rows: Iterable[Mapping[str, str]],
    *,
    source_url: str = IMAGE_METADATA_SOURCE_URL,
) -> list[dict[str, Any]]:
    return [metadata_row_to_record(row, source_url=source_url) for row in rows if facility_name(row)]


def metadata_row_to_record(
    row: Mapping[str, str],
    *,
    source_url: str = IMAGE_METADATA_SOURCE_URL,
) -> dict[str, Any]:
    captured_date = read_value(row, ["IMG_MK_DATE", "촬영일자"])
    captured_time = read_value(row, ["IMG_MK_TIME", "촬영시간"])
    captured_at = None
    if captured_date and captured_time:
        captured_at = f"{captured_date} {captured_time}"
    elif captured_date:
        captured_at = captured_date

    return {
        "tourist_name": facility_name(row) or "",
        "tourist_name_en": read_value(row, ["TOURIST_EN", "관광지 영문명"]) or "",
        "image_file_name": read_value(row, ["IMG_FILE_NM", "이미지 파일명"]) or "",
        "captured_at": captured_at,
        "latitude": parse_coordinate(read_value(row, ["LAT", "위도"])),
        "longitude": parse_coordinate(read_value(row, ["LON", "경도"])),
        "resolution": read_value(row, ["RESOLUTION", "해상도"]) or "",
        "source": {
            "name": "제주특별자치도",
            "url": source_url,
            "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
            "license": "이용허락범위 제한 없음",
        },
    }


def facility_name(row: Mapping[str, str]) -> str | None:
    return read_value(row, ["TOURIST_NM", "관광지명", "관광지 명", "name"])


def parse_coordinate(value: Any) -> float | None:
    parsed = parse_float(value)
    if parsed is not None:
        return parsed

    text = clean(value)
    if text is None:
        return None

    parts = [part.strip() for part in re.split(r"[;°'′\"″]+", text) if part.strip()]
    if len(parts) != 3:
        return None

    try:
        degrees, minutes, seconds = (float(part) for part in parts)
    except ValueError:
        return None

    sign = -1 if degrees < 0 else 1
    return sign * (abs(degrees) + abs(minutes) / 60 + abs(seconds) / 3600)


def make_card_id(name: str, seq: int) -> str:
    number = seq if seq > 0 else abs(hash(name)) % 1000
    base = ascii_slug(name) or "place"
    return f"jeju_roadview_{base[:32]}_{number:03d}"


def ascii_slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return text


def infer_basic_category(name: str) -> str:
    if any(token in name for token in ["체험관", "체험", "레저", "액티비티"]):
        return "experience"
    if any(token in name for token in ["박물관", "미술관", "전시", "기념관", "문학관", "공연장", "홍보관", "센터"]):
        return "indoor"
    if any(token in name for token in ["삼성혈", "문화", "예술", "유적", "성지", "사찰", "민속"]):
        return "culture"
    if any(token in name for token in ["숲", "수목원", "휴양림", "곶자왈"]):
        return "forest"
    if "오름" in name or any(part.endswith("봉") for part in re.split(r"[\s,()/·_-]+", name) if part) or any(token in name for token in ["송악산", "산방산"]):
        return "oreum"
    if any(token in name for token in ["해변", "해수욕장", "해안", "포구", "폭포", "일출"]) or any(part.endswith("항") for part in re.split(r"[\s,()/·_-]+", name) if part):
        return "sea"
    if any(token in name for token in ["공원", "정원"]):
        return "rest_area"
    if any(token in name for token in ["쉼터", "산책", "둘레길", "전망대", "광장", "동산"]):
        return "rest_area"
    return "other"


def build_situation_tags(nursing_room: bool | None, rest_room: bool | None) -> list[str]:
    tags = ["restroom_important"]
    if rest_room:
        tags.append("short_stay")
    if nursing_room:
        tags.append("quiet")
    return sorted(set(tags))


def build_facility_summary(
    name: str,
    toilet_count: int | None,
    parking_count: int | None,
    wheelchair_rental: bool | None,
    nursing_room: bool | None,
    rest_room: bool | None,
) -> str:
    parts = [f"{name}의 사회적약자 시설 현황 데이터 기반 접근성 보강 후보."]
    parts.append(format_count("장애인 화장실", toilet_count))
    parts.append(format_count("장애인 주차장", parking_count))
    parts.append(format_yes_no("휠체어 대여", wheelchair_rental))
    parts.append(format_yes_no("수유실", nursing_room))
    parts.append(format_yes_no("휴게실", rest_room))
    return " ".join(parts)


def format_count(label: str, value: int | None) -> str:
    if value is None:
        return f"{label} 수 확인 필요."
    return f"{label} {value}개."


def format_yes_no(label: str, value: bool | None) -> str:
    if value is None:
        return f"{label} 여부 확인 필요."
    return f"{label} {'가능' if value else '정보상 없음'}."


def count_field_state(count: int | None, label: str, source_ref: str) -> dict[str, str | None]:
    if count is None:
        return {"state": "needs_check", "note": f"{label} 정보 없음", "source_ref": source_ref}
    if count > 0:
        return {"state": "yes", "note": f"{label}: {count}개", "source_ref": source_ref}
    return {"state": "no", "note": f"{label}: 0개", "source_ref": source_ref}


def yes_no_field_state(value: bool | None, label: str, source_ref: str) -> dict[str, str | None]:
    if value is None:
        return {"state": "needs_check", "note": f"{label} 정보 없음", "source_ref": source_ref}
    if value:
        return {"state": "yes", "note": label, "source_ref": source_ref}
    return {"state": "no", "note": f"{label}: N", "source_ref": source_ref}


def read_yes_no(row: Mapping[str, str], aliases: list[str]) -> bool | None:
    value = clean(read_value(row, aliases))
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"y", "yes", "1", "true", "o", "가능", "있음", "보유"}:
        return True
    if normalized in {"n", "no", "0", "false", "x", "없음", "미보유"}:
        return False
    return None


def parse_int(value: Any) -> int | None:
    text = clean(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None
