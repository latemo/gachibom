"""Conservative visit-information enrichment for accessibility place cards.

Raw catalog matches can provide useful address and phone candidates, but they do
not prove that current operating hours or booking details are correct.  This
module therefore keeps catalog-derived information in ``needs_check`` state.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from math import isfinite
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


VISIT_INFO_KEYS = (
    "address",
    "phone",
    "operating_hours",
    "official_url",
    "reservation_url",
    "service_status",
    "notice",
    "verification_status",
    "last_verified_at",
    "source_updated_at",
    "missing_fields",
    "evidence",
)

PUBLIC_FIELDS = (
    "address",
    "phone",
    "operating_hours",
    "official_url",
    "reservation_url",
)
EVIDENCE_FIELDS = (*PUBLIC_FIELDS, "service_status")

SERVICE_STATUSES = {"active", "temporarily_closed", "permanently_closed", "unknown"}
VERIFICATION_STATUSES = {"verified", "partial", "needs_check"}
EVIDENCE_STATUSES = {"verified", "partial", "needs_check", "not_applicable"}
EVIDENCE_SOURCE_TYPES = {
    "official",
    "public_agency",
    "operator_verified",
    "partner_verified",
    "user_feedback",
    "unknown",
}


def empty_visit_info() -> dict[str, Any]:
    """Return a new, fixed-shape visit-information placeholder."""

    return {
        "address": None,
        "phone": None,
        "operating_hours": None,
        "official_url": None,
        "reservation_url": None,
        "service_status": "unknown",
        "notice": None,
        "verification_status": "needs_check",
        "last_verified_at": None,
        "source_updated_at": None,
        "missing_fields": list(PUBLIC_FIELDS),
        "evidence": [],
    }


def build_visit_info_index(
    catalog_rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build visit info for high-confidence, active, exact catalog matches.

    When duplicate rows point at the same accessibility card, the newest valid
    ``source.updated_at`` wins.  Remaining ties use completeness and stable text
    fields, making the result independent of input ordering.
    """

    eligible: dict[str, list[Mapping[str, Any]]] = {}
    for row in catalog_rows:
        if not isinstance(row, Mapping):
            continue
        spot_id = _eligible_spot_id(row)
        if not spot_id:
            continue
        if not (_clean_text(row.get("address")) or _clean_text(row.get("phone"))):
            continue
        eligible.setdefault(spot_id, []).append(row)

    result: dict[str, dict[str, Any]] = {}
    for spot_id in sorted(eligible):
        selected = max(eligible[spot_id], key=_catalog_row_priority)
        result[spot_id] = _visit_info_from_catalog_row(selected)
    return result


def build_reviewed_visit_info_index(
    reviewed_rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build a manual-review index that requires a review date and evidence."""

    eligible: dict[str, list[dict[str, Any]]] = {}
    for row in reviewed_rows:
        if not isinstance(row, Mapping):
            continue
        spot_id = _clean_text(row.get("spot_id") or row.get("id"))
        raw_info = row.get("visit_info")
        if not spot_id or not isinstance(raw_info, Mapping):
            continue
        info = visit_info_for_place({"visit_info": raw_info})
        if not info["last_verified_at"] or not info["evidence"]:
            continue
        eligible.setdefault(spot_id, []).append(info)

    return {
        spot_id: max(items, key=_reviewed_info_priority)
        for spot_id, items in sorted(eligible.items())
    }


def enrich_places_with_visit_info(
    places: Iterable[Mapping[str, Any]],
    catalog_rows: Iterable[Mapping[str, Any]],
    reviewed_rows: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return deep-copied places with fixed-shape visit information attached."""

    visit_info_index = build_visit_info_index(catalog_rows)
    reviewed_info_index = build_reviewed_visit_info_index(reviewed_rows)
    enriched: list[dict[str, Any]] = []
    for source_place in places:
        place = deepcopy(dict(source_place))
        spot_id = _clean_text(place.get("id") or place.get("spot_id"))
        existing = visit_info_for_place(place)
        candidate = visit_info_index.get(spot_id or "")
        if candidate:
            existing = _merge_catalog_visit_info(existing, candidate)
        reviewed = reviewed_info_index.get(spot_id or "")
        if reviewed:
            existing = _merge_reviewed_visit_info(existing, reviewed)
        place["visit_info"] = existing
        enriched.append(place)
    return enriched


def visit_info_for_place(place: Mapping[str, Any]) -> dict[str, Any]:
    """Return a sanitized, fixed-shape copy of a place's visit information."""

    raw = place.get("visit_info")
    if not isinstance(raw, Mapping):
        return empty_visit_info()

    result = empty_visit_info()
    for field in ("address", "phone", "operating_hours", "notice"):
        result[field] = _clean_text(raw.get(field))
    for field in ("official_url", "reservation_url"):
        result[field] = _safe_http_url(raw.get(field))

    service_status = _clean_text(raw.get("service_status"))
    if service_status in SERVICE_STATUSES:
        result["service_status"] = service_status

    verification_status = _clean_text(raw.get("verification_status"))
    if verification_status in VERIFICATION_STATUSES:
        result["verification_status"] = verification_status

    result["last_verified_at"] = _iso_date(raw.get("last_verified_at"))
    result["source_updated_at"] = _iso_date(raw.get("source_updated_at"))
    if isinstance(raw.get("missing_fields"), (list, tuple)):
        result["missing_fields"] = _ordered_unique(
            field for field in raw["missing_fields"] if field in PUBLIC_FIELDS
        )
    else:
        result["missing_fields"] = [field for field in PUBLIC_FIELDS if not result[field]]

    evidence = raw.get("evidence")
    if isinstance(evidence, (list, tuple)):
        result["evidence"] = _normalized_evidence(evidence)
    return {key: result[key] for key in VISIT_INFO_KEYS}


def _eligible_spot_id(row: Mapping[str, Any]) -> str | None:
    matching = row.get("matching")
    if not isinstance(matching, Mapping):
        return None
    if row.get("status") != "active" or matching.get("match_status") != "matched":
        return None
    try:
        confidence = float(matching.get("match_confidence"))
    except (TypeError, ValueError):
        return None
    if not isfinite(confidence) or confidence < 0.99:
        return None
    return _clean_text(matching.get("accessibility_card_id"))


def _visit_info_from_catalog_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = empty_visit_info()
    result["address"] = _clean_text(row.get("address"))
    result["phone"] = _clean_text(row.get("phone"))

    source = row.get("source") if isinstance(row.get("source"), Mapping) else {}
    updated_at = _iso_date(source.get("updated_at"))
    result["source_updated_at"] = updated_at
    result["missing_fields"] = [field for field in PUBLIC_FIELDS if not result[field]]

    source_url = _safe_http_url(source.get("url"))
    fields = [field for field in ("address", "phone") if result[field]]
    if source_url and fields:
        result["evidence"] = [
            {
                "fields": fields,
                "status": "needs_check",
                "source_title": _clean_text(source.get("dataset_name") or source.get("name"))
                or "공공 장소 카탈로그",
                "source_url": source_url,
                "source_type": "public_agency",
                "checked_at": None,
                "observed_at": None,
                "note": (
                    (
                        f"공공 카탈로그 원본 갱신일은 {updated_at}이며, "
                        if updated_at
                        else "공공 카탈로그 자동 보강 값이며, "
                    )
                    + "실제 현장 확인일이 아니므로 방문 전 공식 정보 재확인이 필요합니다."
                ),
            }
        ]
    return result


def _merge_catalog_visit_info(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(existing)
    added_fields: list[str] = []
    for field in ("address", "phone"):
        if not result[field] and candidate[field]:
            result[field] = candidate[field]
            added_fields.append(field)

    if not added_fields:
        return result

    result["verification_status"] = "needs_check"
    result["source_updated_at"] = _latest_date(
        result.get("source_updated_at"), candidate.get("source_updated_at")
    )
    result["missing_fields"] = [field for field in PUBLIC_FIELDS if not result[field]]
    candidate_evidence = []
    for evidence in candidate.get("evidence", []):
        item = deepcopy(evidence)
        item["fields"] = [field for field in item.get("fields", []) if field in added_fields]
        if item["fields"]:
            candidate_evidence.append(item)
    result["evidence"] = _normalized_evidence(
        [*result.get("evidence", []), *candidate_evidence]
    )
    return result


def _merge_reviewed_visit_info(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(existing)
    for field in (*PUBLIC_FIELDS, "notice"):
        if candidate.get(field) is not None:
            result[field] = candidate[field]

    if candidate.get("service_status") != "unknown":
        result["service_status"] = candidate["service_status"]
    result["verification_status"] = candidate["verification_status"]
    result["last_verified_at"] = _latest_date(
        result.get("last_verified_at"), candidate.get("last_verified_at")
    )
    result["source_updated_at"] = _latest_date(
        result.get("source_updated_at"), candidate.get("source_updated_at")
    )
    result["missing_fields"] = [field for field in PUBLIC_FIELDS if not result[field]]
    result["evidence"] = _normalized_evidence(
        [*result.get("evidence", []), *candidate.get("evidence", [])]
    )
    return result


def _catalog_row_priority(row: Mapping[str, Any]) -> tuple[Any, ...]:
    source = row.get("source") if isinstance(row.get("source"), Mapping) else {}
    updated_at = _iso_date(source.get("updated_at")) or ""
    address = _clean_text(row.get("address")) or ""
    phone = _clean_text(row.get("phone")) or ""
    completeness = int(bool(address)) + int(bool(phone))
    source_url = _safe_http_url(source.get("url")) or ""
    source_title = _clean_text(source.get("dataset_name") or source.get("name")) or ""
    return (
        updated_at,
        completeness,
        int(bool(source_url)),
        _clean_text(row.get("catalog_id")) or "",
        address,
        phone,
        source_url,
        source_title,
    )


def _reviewed_info_priority(info: Mapping[str, Any]) -> tuple[Any, ...]:
    status_priority = {"needs_check": 0, "partial": 1, "verified": 2}
    return (
        _iso_date(info.get("last_verified_at")) or "",
        status_priority.get(str(info.get("verification_status") or ""), 0),
        sum(bool(info.get(field)) for field in PUBLIC_FIELDS),
        len(info.get("evidence") or []),
        tuple(str(info.get(field) or "") for field in PUBLIC_FIELDS),
    )


def _normalized_evidence(values: Iterable[Any]) -> list[dict[str, Any]]:
    normalized: dict[tuple[Any, ...], dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, Mapping):
            continue
        source_url = _safe_http_url(value.get("source_url"))
        if not source_url:
            continue
        fields = _ordered_unique(field for field in value.get("fields", []) if field in EVIDENCE_FIELDS)
        if not fields:
            continue
        status = _clean_text(value.get("status"))
        if status not in EVIDENCE_STATUSES:
            status = "needs_check"
        source_type = _clean_text(value.get("source_type"))
        if source_type not in EVIDENCE_SOURCE_TYPES:
            source_type = "unknown"
        item = {
            "fields": fields,
            "status": status,
            "source_title": _clean_text(value.get("source_title")) or "출처 확인 필요",
            "source_url": source_url,
            "source_type": source_type,
            "checked_at": _iso_date(value.get("checked_at")),
            "observed_at": _iso_date(value.get("observed_at")),
            "note": _clean_text(value.get("note")) or "",
        }
        key = (
            item["source_url"],
            tuple(item["fields"]),
            item["checked_at"] or "",
            item["observed_at"] or "",
            item["source_title"],
        )
        normalized[key] = item
    return [normalized[key] for key in sorted(normalized)]


def _safe_http_url(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed._replace(scheme=parsed.scheme.lower()).geturl()


def _iso_date(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _latest_date(left: Any, right: Any) -> str | None:
    values = [value for value in (_iso_date(left), _iso_date(right)) if value]
    return max(values) if values else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
