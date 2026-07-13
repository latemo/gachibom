"""Bounded, deterministic query parsing for the local RAG retrieval layer.

The parser deliberately performs no logging, persistence, network access, or
model calls.  It keeps only a bounded ``query_text`` and coarse search signals;
diagnoses and other health details are not promoted to separate output fields.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


MAX_QUERY_TEXT_LENGTH = 500
MAX_SUMMARY_ITEMS = 12
MAX_SUMMARY_ITEM_LENGTH = 120

TRAVELER_SUMMARY_KEYS = (
    "traveler_type",
    "mobility_conditions",
    "preferred_themes",
    "required_accessibility",
    "avoid",
)


_REGION_ALIASES = (
    ("애월읍", ("애월읍", "애월")),
    ("한림읍", ("한림읍", "한림")),
    ("조천읍", ("조천읍", "조천")),
    ("구좌읍", ("구좌읍", "구좌")),
    ("성산읍", ("성산읍", "성산")),
    ("표선면", ("표선면", "표선")),
    ("남원읍", ("남원읍", "남원")),
    ("안덕면", ("안덕면", "안덕")),
    ("대정읍", ("대정읍", "대정")),
    ("우도면", ("우도면", "우도")),
    ("중문", ("중문관광단지", "중문")),
    ("제주시", ("제주시", "제주 시내", "제주공항")),
    ("서귀포시", ("서귀포시", "서귀포")),
)

_JEJU_PROVINCE_ALIASES = ("제주특별자치도", "제주도", "제주")

_CATEGORY_ALIASES = (
    ("medical_support", ("응급실", "종합병원", "대형병원", "병원", "의원", "약국", "보건소")),
    ("transport", ("교통약자", "이동지원센터", "이동 지원 센터", "콜택시", "콜 택시", "대중교통", "버스")),
    ("indoor", ("실내", "박물관", "미술관", "전시관", "기념관")),
    ("culture", ("문화", "박물관", "미술관", "전시", "역사", "유적")),
    ("forest", ("숲", "수목원", "정원", "치유의 숲")),
    ("sea", ("바다", "해변", "해안", "올레")),
    ("oreum", ("오름",)),
    ("rest_area", ("공원", "휴식", "쉼터")),
    ("cafe", ("카페", "찻집")),
    ("restaurant", ("식당", "음식점", "맛집")),
    ("food_market", ("시장", "먹거리")),
    ("shopping", ("쇼핑", "상점")),
)

_RESOURCE_TYPE_ALIASES = (
    (
        "hospital",
        ("상급종합병원", "종합병원", "대형병원", "응급실", "병원"),
    ),
    ("pharmacy", ("약국",)),
    (
        "mobility_support_center",
        (
            "교통약자 이동지원센터",
            "교통 약자 이동 지원 센터",
            "이동지원센터",
            "이동 지원 센터",
            "관광약자 콜택시",
            "관광 약자 콜택시",
            "장애인 콜택시",
            "콜택시",
            "콜 택시",
            "행복콜",
        ),
    ),
    (
        "tourism_welfare_service",
        (
            "관광복지서비스",
            "관광 복지 서비스",
            "관광 관련 복지서비스",
            "관광 관련 복지 서비스",
            "관광약자 복지",
            "관광 약자 복지",
            "복지서비스",
            "복지 서비스",
        ),
    ),
)

_TRAVELER_TYPE_ALIASES = (
    ("wheelchair_user", ("전동휠체어", "전동 휠체어", "휠체어", "지체장애")),
    ("visual_impairment", ("시각장애", "시각 장애")),
    ("hearing_impairment", ("청각장애", "청각 장애")),
    ("senior", ("어르신", "노인", "고령자", "고령", "노약자")),
    ("pregnant_traveler", ("임산부", "임신부", "임신 중")),
    ("stroller_family", ("유모차", "유아차", "영유아", "아이 동반")),
    ("caregiver_group", ("보호자 동행", "보호자와", "간병인")),
    ("recovery_traveler", ("회복기", "재활 중", "수술 후")),
    ("slow_walker", ("보행이 느", "천천히 걷", "걷는 속도가 느")),
)

_PREFERRED_THEME_ALIASES = (
    ("실내", ("실내", "박물관", "미술관", "전시관")),
    ("문화", ("문화", "역사", "유적", "박물관", "미술관")),
    ("숲", ("숲", "수목원", "정원")),
    ("바다", ("바다", "해변", "해안")),
    ("공원", ("공원", "산책로")),
    ("휴식", ("휴식", "조용한", "한적한", "쉼")),
    ("카페", ("카페", "찻집")),
    ("쇼핑", ("쇼핑", "상점")),
    ("음식", ("음식", "식당", "맛집", "먹거리")),
)

_AVOID_ALIASES = (
    ("계단", ("계단",)),
    ("경사", ("경사", "오르막", "가파른")),
    ("혼잡", ("혼잡", "사람 많은", "붐비는", "대기줄")),
    ("비포장", ("비포장", "울퉁불퉁", "요철")),
    ("긴 걷기", ("긴 걷기", "오래 걷", "많이 걷", "장거리 보행")),
    ("장시간 야외 체류", ("장시간 야외", "오래 야외", "야외 체류")),
    ("식당 제외", ("식당", "음식점", "맛집", "먹거리")),
    ("강풍", ("강풍", "센 바람")),
    ("더위", ("더위", "폭염")),
    ("비", ("비 오는", "우천")),
    ("소음", ("소음", "시끄러운")),
    ("바다", ("바다", "해변", "해안")),
    ("숲", ("숲", "수목원")),
    ("실내", ("실내",)),
)

_MOBILITY_ALIASES = (
    ("긴 걷기 어려움", ("긴 걷기", "오래 걷", "많이 걷", "장거리 보행", "걷기 힘", "보행이 어려")),
    ("짧은 이동", ("짧은 이동", "이동 거리가 짧", "가까운 곳", "근처")),
    ("휴식 필요", ("휴식 필요", "쉬어야", "자주 쉬", "벤치", "쉼터")),
    ("체력 저하", ("체력 저하", "쉽게 지", "회복기")),
    ("비", ("비 오는", "우천")),
    ("바람", ("강풍", "바람이 강", "센 바람")),
    ("더위", ("더위", "폭염")),
)

_REQUIRED_ACCESSIBILITY_ALIASES = (
    ("장애인 화장실", ("장애인 화장실", "휠체어 화장실", "무장애 화장실")),
    ("주차", ("장애인 주차", "주차장", "주차 필요", "주차 가능")),
    ("휴식 공간", ("휴식 공간", "쉴 곳", "벤치", "쉼터")),
    ("엘리베이터", ("엘리베이터", "승강기")),
    ("경사로", ("경사로", "램프", "무단차")),
    ("수어 안내", ("수어", "수화 안내")),
    ("음성 안내", ("음성 안내", "오디오 가이드", "점자")),
)

_AVOID_AFTER_MARKERS = (
    "회피",
    "피하",
    "피해",
    "피하고",
    "빼",
    "제외",
    "말고",
    "싫",
    "없",
    "어렵",
    "힘들",
    "불편",
    "원하지",
    "안 가",
    "가지 않",
    "못 가",
)

_AVOID_BEFORE_PATTERN = re.compile(
    r"(?:피할|피하고 싶은|빼고 싶은|제외할|원하지 않는|싫은|안 갈|가지 않을)\s*$"
)

_EMERGENCY_ALIASES = ("응급실", "응급 상황", "응급상황", "위급", "긴급 의료", "구급")
_POWERED_MOBILITY_ALIASES = ("전동휠체어", "전동 휠체어", "전동스쿠터", "전동 스쿠터", "보장구")
_CHARGING_ALIASES = ("급속충전기", "급속 충전기", "휠체어 충전", "보장구 충전")


def parse_query_intent(
    query: Any,
    traveler_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse a Korean search query into a bounded, JSON-safe retrieval contract.

    ``traveler_summary`` is copied and normalized before inferred values are
    appended, so callers can safely reuse their input object.  Unknown profile
    keys and non-string values are ignored.
    """

    query_text = _clean_text(query, MAX_QUERY_TEXT_LENGTH)
    normalized_summary = _normalize_traveler_summary(traveler_summary)
    inferred_summary = _extract_traveler_summary(query_text)
    merged_summary = {
        key: _merge_unique(normalized_summary[key], inferred_summary[key], MAX_SUMMARY_ITEMS)
        for key in TRAVELER_SUMMARY_KEYS
    }

    emergency = _has_emergency_signal(query_text)
    charging = _has_charging_signal(query_text)
    regions = _extract_regions(query_text)
    categories = _extract_categories(query_text)
    resource_types = _extract_resource_types(query_text, emergency=emergency, charging=charging)

    if emergency and "medical_support" not in categories:
        categories.append("medical_support")
    if resource_types and any(item == "mobility_support_center" for item in resource_types):
        if "transport" not in categories:
            categories.append("transport")

    return {
        "intent": _intent_name(
            query_text,
            regions=regions,
            categories=categories,
            resource_types=resource_types,
            traveler_summary=merged_summary,
            emergency=emergency,
        ),
        "query_text": query_text,
        "regions": regions,
        "categories": categories,
        "resource_types": resource_types,
        "traveler_summary": merged_summary,
        "signals": {
            "emergency": emergency,
            "charging": charging,
        },
    }


def _clean_text(value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    without_controls = "".join(
        " " if unicodedata.category(character) in {"Cc", "Cf"} else character
        for character in normalized
    )
    compact = " ".join(without_controls.split()).strip()
    return compact[:max_length].rstrip()


def _normalize_traveler_summary(value: Any) -> dict[str, list[str]]:
    source = value if isinstance(value, dict) else {}
    normalized: dict[str, list[str]] = {}
    for key in TRAVELER_SUMMARY_KEYS:
        raw_items = source.get(key, [])
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        if not isinstance(raw_items, (list, tuple)):
            raw_items = []
        cleaned = (
            _clean_text(item, MAX_SUMMARY_ITEM_LENGTH)
            for item in raw_items
            if isinstance(item, str)
        )
        normalized[key] = _merge_unique([], cleaned, MAX_SUMMARY_ITEMS)
    return normalized


def _extract_regions(text: str) -> list[str]:
    if not text:
        return []
    regions = [canonical for canonical, aliases in _REGION_ALIASES if _contains_any(text, aliases)]
    if not regions and _contains_any(text, _JEJU_PROVINCE_ALIASES):
        regions.append("제주특별자치도")
    return regions


def _extract_categories(text: str) -> list[str]:
    categories = []
    for canonical, aliases in _CATEGORY_ALIASES:
        if any(alias in text and not _alias_is_avoided(text, alias) for alias in aliases):
            categories.append(canonical)
    return categories


def _extract_resource_types(text: str, *, emergency: bool, charging: bool) -> list[str]:
    resource_types = []
    for canonical, aliases in _RESOURCE_TYPE_ALIASES:
        if any(alias in text and not _alias_is_avoided(text, alias) for alias in aliases):
            resource_types.append(canonical)
    if emergency and "hospital" not in resource_types:
        resource_types.insert(0, "hospital")
    if charging and "power_wheelchair_fast_charger" not in resource_types:
        resource_types.append("power_wheelchair_fast_charger")
    return resource_types


def _extract_traveler_summary(text: str) -> dict[str, list[str]]:
    summary = {key: [] for key in TRAVELER_SUMMARY_KEYS}
    if not text:
        return summary

    for canonical, aliases in _TRAVELER_TYPE_ALIASES:
        if _contains_any(text, aliases):
            summary["traveler_type"].append(canonical)

    for canonical, aliases in _MOBILITY_ALIASES:
        if _contains_any(text, aliases):
            summary["mobility_conditions"].append(canonical)

    if "계단" in text:
        condition = "계단 회피" if _alias_is_avoided(text, "계단") else "경사와 계단 확인"
        summary["mobility_conditions"].append(condition)
    if _contains_any(text, ("경사", "오르막", "가파른")):
        summary["mobility_conditions"].append("경사와 계단 확인")

    for canonical, aliases in _PREFERRED_THEME_ALIASES:
        if any(alias in text and not _alias_is_avoided(text, alias) for alias in aliases):
            summary["preferred_themes"].append(canonical)

    for canonical, aliases in _REQUIRED_ACCESSIBILITY_ALIASES:
        if _contains_any(text, aliases):
            summary["required_accessibility"].append(canonical)

    if _contains_any(text, ("휠체어", "전동휠체어", "전동 휠체어", "지체장애")):
        summary["required_accessibility"].append("휠체어 접근")
    if _has_charging_signal(text):
        summary["required_accessibility"].append("전동휠체어 충전")

    for canonical, aliases in _AVOID_ALIASES:
        if any(alias in text and _alias_is_avoided(text, alias) for alias in aliases):
            summary["avoid"].append(canonical)

    return {
        key: _merge_unique([], values, MAX_SUMMARY_ITEMS)
        for key, values in summary.items()
    }


def _has_emergency_signal(text: str) -> bool:
    if any(alias in text and not _alias_is_avoided(text, alias) for alias in _EMERGENCY_ALIASES):
        return True
    for match in re.finditer(r"(?<!\d)119(?!\d)", text):
        if not _span_is_avoided(text, match.start(), match.end()):
            return True
    return False


def _has_charging_signal(text: str) -> bool:
    if any(alias in text and not _alias_is_avoided(text, alias) for alias in _CHARGING_ALIASES):
        return True
    has_powered_mobility = _contains_any(text, _POWERED_MOBILITY_ALIASES)
    return has_powered_mobility and "충전" in text and not _alias_is_avoided(text, "충전")


def _alias_is_avoided(text: str, alias: str) -> bool:
    start = 0
    while True:
        index = text.find(alias, start)
        if index < 0:
            return False
        if _span_is_avoided(text, index, index + len(alias)):
            return True
        start = index + len(alias)


def _span_is_avoided(text: str, start: int, end: int) -> bool:
    after = text[end : end + 18]
    if any(marker in after for marker in _AVOID_AFTER_MARKERS):
        return True
    before = text[max(0, start - 16) : start]
    return bool(_AVOID_BEFORE_PATTERN.search(before))


def _intent_name(
    query_text: str,
    *,
    regions: list[str],
    categories: list[str],
    resource_types: list[str],
    traveler_summary: dict[str, list[str]],
    emergency: bool,
) -> str:
    if emergency:
        return "emergency_support"
    if resource_types:
        return "support_resource_search"
    has_profile = any(traveler_summary[key] for key in TRAVELER_SUMMARY_KEYS)
    if regions or categories or has_profile:
        return "place_search"
    if query_text:
        return "general_search"
    return "unknown"


def _contains_any(text: str, aliases: Iterable[str]) -> bool:
    return any(alias in text for alias in aliases)


def _merge_unique(existing: Iterable[str], additions: Iterable[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in (*existing, *additions):
        if not value:
            continue
        dedupe_key = value.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        merged.append(value)
        if len(merged) >= limit:
            break
    return merged
