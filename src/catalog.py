"""Raw place catalog import and matching utilities.

The raw catalog can contain thousands of places from public tourism datasets.
It intentionally does not imply accessibility verification.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


CATEGORY_ALIASES = {
    "관광지": "other",
    "명소": "other",
    "문화": "culture",
    "문화시설": "culture",
    "실내": "indoor",
    "박물관": "indoor",
    "미술관": "indoor",
    "음식": "restaurant",
    "음식점": "restaurant",
    "식당": "restaurant",
    "카페": "cafe",
    "시장": "food_market",
    "쇼핑": "shopping",
    "숙박": "lodging",
    "호텔": "lodging",
    "교통": "transport",
    "공항": "transport",
    "병원": "medical_support",
    "약국": "medical_support",
    "행사": "event",
    "축제": "event",
    "체험": "experience",
    "바다": "sea",
    "해변": "sea",
    "숲": "forest",
    "오름": "oreum",
    "공원": "rest_area",
}


@dataclass(frozen=True)
class CatalogImportResult:
    imported: int
    matched: int
    candidates: int
    unmatched: int


def import_catalog_csv(
    csv_path: str | Path,
    *,
    imported_at: date | None = None,
    accessibility_cards: list[dict[str, Any]] | None = None,
    encoding: str = "utf-8-sig",
) -> list[dict[str, Any]]:
    """Import a normalized CSV into raw catalog items."""

    with Path(csv_path).open("r", encoding=encoding, newline="") as handle:
        rows = list(csv.DictReader(handle))

    return import_catalog_rows(rows, imported_at=imported_at, accessibility_cards=accessibility_cards)


def import_catalog_rows(
    rows: Iterable[dict[str, str]],
    *,
    imported_at: date | None = None,
    accessibility_cards: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Import normalized row dictionaries into raw catalog items."""

    imported_at = imported_at or date.today()
    cards = accessibility_cards or []
    items = []
    for row in rows:
        item = row_to_catalog_item(row, imported_at=imported_at)
        item["matching"] = match_accessibility_card(item, cards)
        items.append(item)
    return items


def row_to_catalog_item(row: dict[str, str], *, imported_at: date) -> dict[str, Any]:
    """Convert one normalized CSV row into a catalog schema object."""

    name = clean(row.get("name"))
    raw_category = clean(row.get("raw_category")) or clean(row.get("category"))
    category = normalize_category(clean(row.get("category")) or raw_category)
    source_name = clean(row.get("source_name")) or "unknown"
    source_url = clean(row.get("source_url")) or "https://example.com"
    dataset_name = clean(row.get("dataset_name")) or source_name
    raw_id = clean(row.get("raw_id"))
    raw_hash = stable_hash(row)

    return {
        "catalog_id": f"catalog_{slug(category)}_{raw_hash[:8]}",
        "name": name,
        "category": category,
        "region": clean(row.get("region")) or infer_region(clean(row.get("address"))),
        "address": clean(row.get("address")),
        "phone": clean(row.get("phone")),
        "homepage": clean(row.get("homepage")),
        "latitude": parse_float(row.get("latitude")),
        "longitude": parse_float(row.get("longitude")),
        "tags": split_tags(row.get("tags")),
        "description": clean(row.get("description")),
        "source": {
            "name": source_name,
            "url": source_url,
            "dataset_name": dataset_name,
            "license": clean(row.get("license")) or "unknown",
            "updated_at": clean(row.get("source_updated_at")),
        },
        "ingestion": {
            "imported_at": imported_at.isoformat(),
            "raw_category": raw_category,
            "raw_id": raw_id,
            "raw_hash": raw_hash,
        },
        "matching": {
            "accessibility_card_id": None,
            "match_status": "unmatched",
            "match_confidence": 0,
        },
        "status": "active",
    }


def match_accessibility_card(
    catalog_item: dict[str, Any], accessibility_cards: list[dict[str, Any]]
) -> dict[str, Any]:
    """Find an accessibility-card match by normalized name and region."""

    name = normalize_text(catalog_item.get("name", ""))
    region = normalize_text(catalog_item.get("region", ""))
    best: tuple[float, dict[str, Any] | None] = (0, None)

    for card in accessibility_cards:
        card_name = normalize_text(card.get("name", ""))
        card_region = normalize_text(card.get("region", ""))
        score = 0.0
        if name and name == card_name:
            score += 0.8
        elif name and (name in card_name or card_name in name):
            score += 0.55
        if region and card_region and (region in card_region or card_region in region):
            score += 0.2
        if score > best[0]:
            best = (score, card)

    confidence, card = best
    if not card:
        return {"accessibility_card_id": None, "match_status": "unmatched", "match_confidence": 0}
    if confidence >= 0.8:
        return {
            "accessibility_card_id": card.get("id"),
            "match_status": "matched",
            "match_confidence": round(min(confidence, 1), 2),
        }
    if confidence >= 0.55:
        return {
            "accessibility_card_id": card.get("id"),
            "match_status": "candidate",
            "match_confidence": round(confidence, 2),
        }
    return {"accessibility_card_id": None, "match_status": "unmatched", "match_confidence": 0}


def summarize_catalog(items: Iterable[dict[str, Any]]) -> CatalogImportResult:
    count = {"matched": 0, "candidate": 0, "unmatched": 0, "manual_review": 0}
    total = 0
    for item in items:
        total += 1
        count[item.get("matching", {}).get("match_status", "unmatched")] += 1
    return CatalogImportResult(
        imported=total,
        matched=count["matched"],
        candidates=count["candidate"] + count["manual_review"],
        unmatched=count["unmatched"],
    )


def write_catalog_json(items: list[dict[str, Any]], output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_category(value: str | None) -> str:
    text = clean(value)
    if not text:
        return "other"
    if text in {
        "sea",
        "forest",
        "oreum",
        "culture",
        "indoor",
        "cafe",
        "restaurant",
        "food_market",
        "shopping",
        "rest_area",
        "transport",
        "medical_support",
        "lodging",
        "event",
        "experience",
        "other",
    }:
        return text
    return CATEGORY_ALIASES.get(text, "other")


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_float(value: Any) -> float | None:
    text = clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def split_tags(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return sorted({part.strip() for part in text.replace(",", "|").split("|") if part.strip()})


def infer_region(address: str | None) -> str:
    if not address:
        return ""
    if "서귀포" in address:
        return "서귀포시"
    if "제주시" in address or "제주특별자치도" in address:
        return "제주시"
    return ""


def stable_hash(row: dict[str, str]) -> str:
    payload = "|".join(
        [
            clean(row.get("raw_id")) or "",
            clean(row.get("name")) or "",
            clean(row.get("address")) or "",
            clean(row.get("source_name")) or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_text(value: str | None) -> str:
    text = clean(value) or ""
    return "".join(ch for ch in text.lower() if ch.isalnum() or "\uac00" <= ch <= "\ud7a3")


def slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_") or "place"
