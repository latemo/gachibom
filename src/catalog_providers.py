"""Provider-specific normalization for public Jeju place datasets."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping

from src.catalog import clean, infer_region, normalize_category, split_tags


@dataclass(frozen=True)
class SourceDefaults:
    source_name: str
    source_url: str
    dataset_name: str
    license: str = "unknown"
    source_updated_at: str | None = None


NORMALIZED_FIELDS = [
    "name",
    "category",
    "region",
    "address",
    "phone",
    "homepage",
    "latitude",
    "longitude",
    "tags",
    "description",
    "source_name",
    "source_url",
    "dataset_name",
    "license",
    "source_updated_at",
    "raw_category",
    "raw_id",
]


COLUMN_ALIASES = {
    "raw_id": [
        "raw_id",
        "id",
        "콘텐츠아이디",
        "콘텐츠ID",
        "컨텐츠아이디",
        "콘텐츠id",
        "contentid",
        "content_id",
        "contents_id",
        "contentsid",
        "seq",
        "순번",
        "번호",
        "관리번호",
    ],
    "name": [
        "name",
        "title",
        "콘텐츠명",
        "콘텐츠명국문",
        "상호명",
        "업소명",
        "업체명",
        "명칭",
        "관광지명",
        "touristnm",
        "tourist_nm",
        "시설명",
        "장소명",
        "이름",
    ],
    "category": [
        "category",
        "카테고리",
        "분류",
        "콘텐츠분류",
        "콘텐츠분류명",
        "콘텐츠카테고리",
        "대분류",
        "중분류",
        "업종",
        "업태",
        "업태명",
        "유형",
        "콘텐츠구분",
        "contentscd",
        "contentscdlabel",
        "contentscdvalue",
        "contentscdrefid",
    ],
    "region": [
        "region",
        "area",
        "지역",
        "행정구역",
        "시군구",
        "읍면동",
        "법정동",
        "동",
        "region1cdlabel",
        "region2cdlabel",
        "regionlabel",
    ],
    "address": [
        "address",
        "addr",
        "주소",
        "관광지주소",
        "touristaddr",
        "tourist_addr",
        "도로명주소",
        "지번주소",
        "소재지",
        "소재지주소",
        "위치",
        "newaddress",
        "roadaddress",
        "jibunaddress",
    ],
    "phone": [
        "phone",
        "tel",
        "phoneno",
        "전화번호",
        "관광지전화번호",
        "touristtel",
        "tourist_tel",
        "연락처",
        "문의전화",
        "문의",
        "repPhone",
        "rep_phone",
    ],
    "homepage": [
        "homepage",
        "website",
        "url",
        "홈페이지",
        "웹사이트",
        "상세URL",
        "바로가기",
        "externalurl",
        "external_url",
    ],
    "latitude": [
        "latitude",
        "lat",
        "mapy",
        "y",
        "위도",
        "위도값",
    ],
    "longitude": [
        "longitude",
        "lng",
        "lon",
        "mapx",
        "x",
        "경도",
        "경도값",
    ],
    "tags": [
        "tags",
        "tag",
        "keyword",
        "keywords",
        "alltag",
        "키워드",
        "태그",
        "해시태그",
        "검색키워드",
    ],
    "description": [
        "description",
        "overview",
        "introduction",
        "소개",
        "설명",
        "상세설명",
        "개요",
        "요약",
        "내용",
        "콘텐츠",
    ],
    "source_updated_at": [
        "source_updated_at",
        "updated_at",
        "데이터기준일자",
        "기준일자",
        "수정일",
        "등록일",
    ],
}


CATEGORY_KEYWORDS = [
    ("food_market", ["전통시장", "오일장", "시장", "먹거리"]),
    ("cafe", ["카페", "커피", "디저트", "베이커리", "찻집"]),
    ("restaurant", ["음식", "음식점", "식당", "맛집", "한식", "양식", "일식", "중식", "분식", "해산물"]),
    ("lodging", ["숙박", "호텔", "펜션", "게스트하우스", "리조트", "민박"]),
    ("shopping", ["쇼핑", "면세점", "기념품", "상점", "소품샵", "몰"]),
    ("experience", ["체험관", "체험", "레저", "액티비티", "프로그램"]),
    ("indoor", ["박물관", "미술관", "전시", "기념관", "문학관", "공연장", "도서관", "홍보관", "센터", "실내"]),
    ("culture", ["삼성혈", "문화", "역사", "예술", "유적", "성지", "사찰", "민속"]),
    ("event", ["축제", "행사", "이벤트"]),
    ("sea", ["바다", "해변", "해수욕장", "해안", "폭포", "포구", "항", "일출"]),
    ("forest", ["숲", "수목원", "휴양림", "생태숲", "곶자왈"]),
    ("oreum", ["오름", "봉", "송악산", "산방산"]),
    ("rest_area", ["공원", "정원", "쉼터", "산책", "산책로", "둘레길", "전망대", "광장", "동산"]),
    ("transport", ["교통", "공항", "항만", "터미널", "버스", "정류장", "렌터카"]),
    ("medical_support", ["병원", "의원", "약국", "보건소", "응급"]),
]


YES_VALUES = {"1", "y", "yes", "true", "o", "가능", "있음", "예", "운영"}


def normalize_public_place_rows(
    rows: Iterable[Mapping[str, str]],
    *,
    source_defaults: SourceDefaults,
    default_category: str | None = None,
) -> list[dict[str, str]]:
    """Normalize public CSV rows to the internal place catalog CSV shape."""

    return [
        normalize_public_place_row(row, source_defaults=source_defaults, default_category=default_category)
        for row in rows
    ]


def normalize_public_place_row(
    row: Mapping[str, str],
    *,
    source_defaults: SourceDefaults,
    default_category: str | None = None,
) -> dict[str, str]:
    """Normalize one public dataset row to the internal catalog row shape."""

    name = read_value(row, COLUMN_ALIASES["name"])
    fallback_category = effective_default_category(default_category)
    raw_category = read_value(row, COLUMN_ALIASES["category"]) or fallback_category
    address = read_value(row, COLUMN_ALIASES["address"])
    region = read_value(row, COLUMN_ALIASES["region"]) or infer_region(address)
    tags = build_tags(row, read_value(row, COLUMN_ALIASES["tags"]))
    description = build_description(row, read_value(row, COLUMN_ALIASES["description"]))
    category = infer_category(raw_category, fallback_category, source_defaults.dataset_name, tags, name)

    normalized = {
        "name": name or "",
        "category": category,
        "region": region or "",
        "address": address or "",
        "phone": read_value(row, COLUMN_ALIASES["phone"]) or "",
        "homepage": read_value(row, COLUMN_ALIASES["homepage"]) or "",
        "latitude": read_value(row, COLUMN_ALIASES["latitude"]) or "",
        "longitude": read_value(row, COLUMN_ALIASES["longitude"]) or "",
        "tags": tags,
        "description": description,
        "source_name": source_defaults.source_name,
        "source_url": source_defaults.source_url,
        "dataset_name": source_defaults.dataset_name,
        "license": source_defaults.license,
        "source_updated_at": read_value(row, COLUMN_ALIASES["source_updated_at"])
        or source_defaults.source_updated_at
        or "",
        "raw_category": raw_category or category,
        "raw_id": read_value(row, COLUMN_ALIASES["raw_id"]) or "",
    }
    return {field: normalized.get(field, "") for field in NORMALIZED_FIELDS}


def infer_category(*texts: str | None) -> str:
    """Infer an internal category from source category/name/tag text."""

    for text in texts:
        value = clean(text)
        if not value:
            continue
        normalized = normalize_category(value)
        if normalized != "other" or normalize_header(value) == "other":
            return normalized

    combined = " ".join(clean(text) or "" for text in texts)
    for category, keywords in CATEGORY_KEYWORDS:
        if any(category_keyword_matches(combined, keyword) for keyword in keywords):
            return category
    return "other"


def category_keyword_matches(text: str, keyword: str) -> bool:
    if keyword == "봉":
        return any(part.endswith("봉") for part in re.split(r"[\s,()/·_-]+", text) if part)
    if keyword == "항":
        return any(part.endswith("항") for part in re.split(r"[\s,()/·_-]+", text) if part)
    return keyword in text


def effective_default_category(default_category: str | None) -> str | None:
    """Treat explicit fallback categories as hints, except the non-informative other bucket."""

    category = normalize_category(clean(default_category))
    if not category or category == "other":
        return None
    return category


def read_value(row: Mapping[str, str], aliases: list[str]) -> str | None:
    """Read a value by exact or loose-normalized header aliases."""

    indexed = {normalize_header(key): value for key, value in row.items() if key is not None}
    alias_keys = [normalize_header(alias) for alias in aliases]

    for alias in alias_keys:
        value = clean(indexed.get(alias))
        if value:
            return value

    for header, value in indexed.items():
        if any(alias and alias in header for alias in alias_keys):
            cleaned = clean(value)
            if cleaned:
                return cleaned
    return None


def normalize_header(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    return "".join(ch for ch in text if ch.isalnum() or "\uac00" <= ch <= "\ud7a3")


def build_tags(row: Mapping[str, str], base_tags: str | None) -> str:
    tags = split_tags(base_tags)
    if is_yes(read_value(row, ["노키즈존"])):
        tags.append("노키즈존")
    if is_yes(read_value(row, ["예약가능여부", "예약가능"])):
        tags.append("예약가능")
    if is_yes(read_value(row, ["룸보유여부", "룸보유"])):
        tags.append("룸보유")
    if read_value(row, ["유아서비스기타", "유아서비스"]):
        tags.append("유아서비스")
    return "|".join(sorted(set(tags)))


def build_description(row: Mapping[str, str], base_description: str | None) -> str:
    parts = [base_description] if base_description else []
    menu = read_value(row, ["대표메뉴기타", "대표메뉴", "메뉴"])
    weekday_open = read_value(row, ["평일오픈시간"])
    weekday_close = read_value(row, ["평일클로즈시간", "평일마감시간"])
    weekend_open = read_value(row, ["주말오픈시간"])
    weekend_close = read_value(row, ["주말클로즈시간", "주말마감시간"])
    break_start = read_value(row, ["휴식시작시간", "브레이크타임시작"])
    break_end = read_value(row, ["휴식종료시간", "브레이크타임종료"])
    child_service = read_value(row, ["유아서비스기타", "유아서비스"])

    if menu:
        parts.append(f"대표메뉴: {menu}")
    if weekday_open or weekday_close:
        parts.append(f"평일 운영: {format_time_range(weekday_open, weekday_close)}")
    if weekend_open or weekend_close:
        parts.append(f"주말 운영: {format_time_range(weekend_open, weekend_close)}")
    if break_start or break_end:
        parts.append(f"휴식시간: {format_time_range(break_start, break_end)}")
    if child_service:
        parts.append(f"유아서비스: {child_service}")
    return " / ".join(part for part in parts if part)


def format_time_range(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start}-{end}"
    return start or end or "확인 필요"


def is_yes(value: str | None) -> bool:
    text = clean(value)
    if not text:
        return False
    return re.sub(r"\s+", "", text).lower() in YES_VALUES
