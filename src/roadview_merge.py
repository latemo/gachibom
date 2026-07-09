"""Review report generation for roadview accessibility card drafts."""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from src.catalog import normalize_text


MATCHED_THRESHOLD = 0.9
MANUAL_REVIEW_THRESHOLD = 0.65
UPDATABLE_FIELDS = ["accessible_toilet", "parking", "rest_area", "rental_or_assistance"]
LOW_CONFIDENCE_STATES = {"unknown", "needs_check", "partial"}
DECISIVE_STATES = {"yes", "no"}
SAFE_AUTO_UPDATE_STATES = {"yes"}
ROADVIEW_FACILITY_SOURCE = {
    "title": "제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
    "url": "https://www.data.go.kr/data/15109153/fileData.do",
    "type": "public_agency",
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_merge_review_report(
    existing_cards: Iterable[dict[str, Any]],
    draft_cards: Iterable[dict[str, Any]],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    """Classify roadview draft cards against existing accessibility cards."""

    existing = list(existing_cards)
    drafts = list(draft_cards)
    matched_existing = []
    new_candidate = []
    needs_manual_review = []
    field_updates_available = []

    for draft in drafts:
        match = find_best_match(draft, existing)
        if match["confidence"] >= MATCHED_THRESHOLD:
            existing_card = match["card"]
            updates = find_field_updates(existing_card, draft)
            conflicts = find_field_conflicts(existing_card, draft)
            matched_entry = {
                "existing": card_ref(existing_card),
                "draft": card_ref(draft),
                "match_confidence": match["confidence"],
                "match_reasons": match["reasons"],
                "field_updates": updates,
                "field_conflicts": conflicts,
            }
            matched_existing.append(matched_entry)
            if updates and not conflicts:
                field_updates_available.append(matched_entry)
            if conflicts:
                needs_manual_review.append(
                    {
                        "review_type": "field_conflict",
                        "existing": card_ref(existing_card),
                        "draft": card_ref(draft),
                        "match_confidence": match["confidence"],
                        "match_reasons": match["reasons"],
                        "field_conflicts": conflicts,
                    }
                )
        elif match["confidence"] >= MANUAL_REVIEW_THRESHOLD:
            needs_manual_review.append(
                {
                    "review_type": "uncertain_match",
                    "existing": card_ref(match["card"]),
                    "draft": card_ref(draft),
                    "match_confidence": match["confidence"],
                    "match_reasons": match["reasons"],
                    "field_conflicts": [],
                }
            )
        else:
            new_candidate.append(
                {
                    "draft": card_ref(draft),
                    "recommended_action": "review_before_adding",
                    "reason": "기존 접근성 카드와 충분히 일치하는 이름/지역 매칭이 없음",
                }
            )

    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "summary": {
            "existing_count": len(existing),
            "draft_count": len(drafts),
            "matched_existing": len(matched_existing),
            "new_candidate": len(new_candidate),
            "needs_manual_review": len(needs_manual_review),
            "field_updates_available": len(field_updates_available),
        },
        "matched_existing": matched_existing,
        "new_candidate": new_candidate,
        "needs_manual_review": needs_manual_review,
        "field_updates_available": field_updates_available,
    }


def apply_safe_roadview_updates(
    existing_cards: Iterable[dict[str, Any]],
    merge_report: dict[str, Any],
    *,
    applied_at: date | None = None,
) -> dict[str, Any]:
    """Apply only conservative roadview field updates and return review artifacts."""

    applied_on = applied_at or date.today()
    cards = deepcopy(list(existing_cards))
    cards_by_id = {card.get("id"): card for card in cards}
    applied_updates: list[dict[str, Any]] = []
    skipped_updates: list[dict[str, Any]] = []
    updated_fields_by_card: dict[str, set[str]] = {}
    review_items = build_manual_review_items(merge_report)

    for entry in merge_report.get("field_updates_available", []):
        existing_ref = entry.get("existing", {})
        card_id = existing_ref.get("id", "")
        card = cards_by_id.get(card_id)
        if card is None:
            skipped_item = skipped_update_item(
                entry,
                {},
                "기존 카드 ID를 찾을 수 없어 자동 병합하지 않음",
            )
            skipped_updates.append(skipped_item)
            review_items.append(skipped_item)
            continue

        for update in entry.get("field_updates", []):
            if not is_safe_auto_update(update):
                skipped_item = skipped_update_item(
                    entry,
                    update,
                    "자동 병합 정책은 공공데이터의 yes 근거만 반영하며 no 값은 운영 검수 후 반영",
                )
                skipped_updates.append(skipped_item)
                review_items.append(skipped_item)
                continue

            field = update.get("field", "")
            previous_field = deepcopy(card.get("accessibility", {}).get(field, {}))
            card.setdefault("accessibility", {})[field] = {
                "state": update.get("draft_state"),
                "note": update.get("draft_note", ""),
                "source_ref": update.get("draft_source_ref"),
            }
            updated_fields_by_card.setdefault(card_id, set()).add(field)
            applied_updates.append(
                {
                    "existing": existing_ref,
                    "draft": entry.get("draft", {}),
                    "field": field,
                    "previous": previous_field,
                    "applied": card["accessibility"][field],
                }
            )

    for card_id, fields in updated_fields_by_card.items():
        card = cards_by_id[card_id]
        append_roadview_source(card)
        remove_missing_fields(card, fields)
        append_operator_note(card, fields, applied_on)

    manual_review_queue = {
        "generated_at": applied_on.isoformat(),
        "source_report_generated_at": merge_report.get("generated_at"),
        "summary": summarize_manual_review_items(review_items),
        "items": review_items,
    }
    apply_report = {
        "applied_at": applied_on.isoformat(),
        "policy": {
            "auto_apply_states": sorted(SAFE_AUTO_UPDATE_STATES),
            "auto_apply_requires": [
                "field_updates_available",
                "no_field_conflicts",
                "existing field is unknown, needs_check, partial, or empty",
            ],
            "manual_review_states": ["no", "unknown", "needs_check", "partial"],
        },
        "summary": {
            "input_cards": len(cards),
            "output_cards": len(cards),
            "cards_updated": len(updated_fields_by_card),
            "safe_field_updates_applied": len(applied_updates),
            "skipped_field_updates": len(skipped_updates),
            "manual_review_items": len(review_items),
            "source_report_matched_existing": merge_report.get("summary", {}).get("matched_existing", 0),
            "source_report_new_candidate": merge_report.get("summary", {}).get("new_candidate", 0),
            "source_report_needs_manual_review": merge_report.get("summary", {}).get("needs_manual_review", 0),
        },
        "applied_updates": applied_updates,
        "skipped_updates": skipped_updates,
    }
    return {
        "cards": cards,
        "manual_review_queue": manual_review_queue,
        "apply_report": apply_report,
    }


def apply_manual_conflict_resolutions(
    existing_cards: Iterable[dict[str, Any]],
    manual_review_queue: dict[str, Any],
    resolution_report: dict[str, Any],
    *,
    applied_at: date | None = None,
) -> dict[str, Any]:
    """Apply reviewed field-conflict decisions without changing resolved field states."""

    applied_on = applied_at or date.today()
    cards = deepcopy(list(existing_cards))
    cards_by_id = {card.get("id"): card for card in cards}
    resolutions = list(resolution_report.get("resolutions", []))
    resolution_keys = {resolution_key(resolution) for resolution in resolutions}
    applied_resolutions = []
    skipped_resolutions = []

    for resolution in resolutions:
        card = cards_by_id.get(resolution.get("existing_id"))
        if card is None:
            skipped_resolutions.append({**resolution, "skip_reason": "기존 카드 ID를 찾을 수 없음"})
            continue
        append_roadview_source(card)
        append_conflict_resolution_note(card, resolution, applied_on)
        append_resolution_safety_note(card, resolution)
        applied_resolutions.append(resolution)

    open_items = []
    resolved_items = []
    for item in manual_review_queue.get("items", []):
        if item.get("review_type") != "field_conflict":
            open_items.append(item)
            continue

        unresolved_conflicts = []
        for conflict in item.get("field_conflicts", []):
            key = conflict_key(item, conflict)
            if key not in resolution_keys:
                unresolved_conflicts.append(conflict)

        if unresolved_conflicts:
            open_item = deepcopy(item)
            open_item["field_conflicts"] = unresolved_conflicts
            open_items.append(open_item)
        else:
            resolved_items.append(item)

    open_queue = {
        "generated_at": applied_on.isoformat(),
        "source_report_generated_at": manual_review_queue.get("source_report_generated_at"),
        "summary": summarize_manual_review_items(open_items),
        "items": open_items,
    }
    apply_report = {
        "applied_at": applied_on.isoformat(),
        "resolution_report_generated_at": resolution_report.get("generated_at"),
        "summary": {
            "input_cards": len(cards),
            "output_cards": len(cards),
            "resolutions_requested": len(resolutions),
            "resolutions_applied": len(applied_resolutions),
            "resolutions_skipped": len(skipped_resolutions),
            "manual_review_items_before": len(manual_review_queue.get("items", [])),
            "manual_review_items_after": len(open_items),
            "resolved_field_conflict_items": len(resolved_items),
        },
        "applied_resolutions": applied_resolutions,
        "skipped_resolutions": skipped_resolutions,
    }
    return {
        "cards": cards,
        "open_manual_review_queue": open_queue,
        "resolution_apply_report": apply_report,
    }


def apply_manual_match_resolutions(
    existing_cards: Iterable[dict[str, Any]],
    manual_review_queue: dict[str, Any],
    resolution_report: dict[str, Any],
    *,
    applied_at: date | None = None,
) -> dict[str, Any]:
    """Apply reviewed uncertain-match decisions without changing accessibility field states."""

    applied_on = applied_at or date.today()
    cards = deepcopy(list(existing_cards))
    cards_by_id = {card.get("id"): card for card in cards}
    resolutions = list(resolution_report.get("resolutions", []))
    resolution_keys = {match_resolution_key(resolution) for resolution in resolutions}
    applied_resolutions = []
    skipped_resolutions = []

    for resolution in resolutions:
        card = cards_by_id.get(resolution.get("existing_id"))
        if card is None:
            skipped_resolutions.append({**resolution, "skip_reason": "기존 카드 ID를 찾을 수 없음"})
            continue
        append_roadview_source(card)
        append_match_resolution_note(card, resolution, applied_on)
        append_resolution_safety_note(card, resolution)
        applied_resolutions.append(resolution)

    open_items = []
    resolved_items = []
    for item in manual_review_queue.get("items", []):
        if item.get("review_type") != "uncertain_match":
            open_items.append(item)
            continue
        if uncertain_match_key(item) in resolution_keys:
            resolved_items.append(item)
        else:
            open_items.append(item)

    open_queue = {
        "generated_at": applied_on.isoformat(),
        "source_report_generated_at": manual_review_queue.get("source_report_generated_at"),
        "summary": summarize_manual_review_items(open_items),
        "items": open_items,
    }
    apply_report = {
        "applied_at": applied_on.isoformat(),
        "resolution_report_generated_at": resolution_report.get("generated_at"),
        "summary": {
            "input_cards": len(cards),
            "output_cards": len(cards),
            "resolutions_requested": len(resolutions),
            "resolutions_applied": len(applied_resolutions),
            "resolutions_skipped": len(skipped_resolutions),
            "manual_review_items_before": len(manual_review_queue.get("items", [])),
            "manual_review_items_after": len(open_items),
            "resolved_uncertain_match_items": len(resolved_items),
        },
        "applied_resolutions": applied_resolutions,
        "skipped_resolutions": skipped_resolutions,
    }
    return {
        "cards": cards,
        "open_manual_review_queue": open_queue,
        "match_resolution_apply_report": apply_report,
    }


def build_manual_review_items(merge_report: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in merge_report.get("needs_manual_review", []):
        review_type = entry.get("review_type", "manual_review")
        items.append(
            {
                "review_type": review_type,
                "priority": "high" if review_type == "field_conflict" else "medium",
                "reason": manual_review_reason(review_type),
                "existing": entry.get("existing", {}),
                "draft": entry.get("draft", {}),
                "match_confidence": entry.get("match_confidence", 0),
                "match_reasons": entry.get("match_reasons", []),
                "field_conflicts": entry.get("field_conflicts", []),
            }
        )
    for entry in merge_report.get("new_candidate", []):
        items.append(
            {
                "review_type": "new_candidate",
                "priority": "medium",
                "reason": entry.get("reason", "기존 카드와 확정 매칭되지 않아 신규 장소 등록 전 검수 필요"),
                "draft": entry.get("draft", {}),
                "recommended_action": entry.get("recommended_action", "review_before_adding"),
            }
        )
    return items


def manual_review_reason(review_type: str) -> str:
    if review_type == "field_conflict":
        return "기존 카드의 yes/no 값과 roadview 초안 값이 충돌하므로 출처 재확인 필요"
    if review_type == "uncertain_match":
        return "장소명이 부분 일치하여 동일 장소 여부 확인 필요"
    return "운영자 검수 필요"


def is_safe_auto_update(update: dict[str, Any]) -> bool:
    return (
        update.get("draft_state") in SAFE_AUTO_UPDATE_STATES
        and update.get("existing_state") in LOW_CONFIDENCE_STATES.union({None, ""})
    )


def skipped_update_item(entry: dict[str, Any], update: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "review_type": "auto_skipped_field_update",
        "priority": "medium",
        "reason": reason,
        "existing": entry.get("existing", {}),
        "draft": entry.get("draft", {}),
        "field_update": update,
    }


def summarize_manual_review_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "by_review_type": dict(Counter(item.get("review_type", "unknown") for item in items)),
        "by_priority": dict(Counter(item.get("priority", "unknown") for item in items)),
    }


def append_roadview_source(card: dict[str, Any]) -> None:
    sources = card.setdefault("sources", [])
    if any(source.get("url") == ROADVIEW_FACILITY_SOURCE["url"] for source in sources):
        return
    sources.append(deepcopy(ROADVIEW_FACILITY_SOURCE))


def remove_missing_fields(card: dict[str, Any], fields: set[str]) -> None:
    verification = card.get("verification", {})
    missing_fields = verification.get("missing_fields")
    if not isinstance(missing_fields, list):
        return
    verification["missing_fields"] = sorted({field for field in missing_fields if field not in fields})


def append_operator_note(card: dict[str, Any], fields: set[str], applied_at: date) -> None:
    field_list = ", ".join(sorted(fields))
    note = (
        f"roadview_safe_merge {applied_at.isoformat()}: "
        f"{field_list} 필드를 제주특별자치도 사회적약자 시설현황 공공데이터로 보강."
    )
    current = card.get("operator_notes", "")
    if note in current:
        return
    card["operator_notes"] = f"{current}\n{note}" if current else note


def append_conflict_resolution_note(card: dict[str, Any], resolution: dict[str, Any], applied_at: date) -> None:
    field = resolution.get("field", "")
    decision = resolution.get("decision", "")
    reason = resolution.get("reason", "")
    note = (
        f"roadview_conflict_resolution {applied_at.isoformat()}: "
        f"{field}={resolution.get('kept_state')} 유지({decision}). {reason}"
    )
    current = card.get("operator_notes", "")
    if note in current:
        return
    card["operator_notes"] = f"{current}\n{note}" if current else note


def append_match_resolution_note(card: dict[str, Any], resolution: dict[str, Any], applied_at: date) -> None:
    decision = resolution.get("decision", "")
    draft_name = resolution.get("draft_name", "")
    reason = resolution.get("reason", "")
    note = (
        f"roadview_match_resolution {applied_at.isoformat()}: "
        f"{draft_name} 매칭을 {decision}로 처리. {reason}"
    )
    current = card.get("operator_notes", "")
    if note in current:
        return
    card["operator_notes"] = f"{current}\n{note}" if current else note


def append_resolution_safety_note(card: dict[str, Any], resolution: dict[str, Any]) -> None:
    safety_note = resolution.get("safety_note")
    if not safety_note:
        return
    safety_notes = card.setdefault("safety_notes", [])
    if safety_note not in safety_notes:
        safety_notes.append(safety_note)


def resolution_key(resolution: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(resolution.get("existing_id", "")),
        str(resolution.get("field", "")),
        str(resolution.get("draft_id", "")),
    )


def conflict_key(item: dict[str, Any], conflict: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("existing", {}).get("id", "")),
        str(conflict.get("field", "")),
        str(item.get("draft", {}).get("id", "")),
    )


def match_resolution_key(resolution: dict[str, Any]) -> tuple[str, str]:
    return (
        str(resolution.get("existing_id", "")),
        str(resolution.get("draft_id", "")),
    )


def uncertain_match_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("existing", {}).get("id", "")),
        str(item.get("draft", {}).get("id", "")),
    )


def find_best_match(draft: dict[str, Any], existing_cards: list[dict[str, Any]]) -> dict[str, Any]:
    best = {"card": None, "confidence": 0.0, "reasons": []}
    draft_name = normalize_text(draft.get("name", ""))
    draft_region = normalize_text(draft.get("region", ""))
    draft_category = draft.get("category")

    for card in existing_cards:
        card_name = normalize_text(card.get("name", ""))
        card_region = normalize_text(card.get("region", ""))
        confidence = 0.0
        reasons: list[str] = []

        if draft_name and draft_name == card_name:
            confidence += 0.9
            reasons.append("name_exact")
        elif draft_name and card_name and (draft_name in card_name or card_name in draft_name):
            confidence += 0.65
            reasons.append("name_contains")

        if draft_region and card_region and (draft_region in card_region or card_region in draft_region):
            confidence += 0.08
            reasons.append("region_overlap")

        if draft_category and draft_category == card.get("category"):
            confidence += 0.02
            reasons.append("category_match")

        confidence = round(min(confidence, 1.0), 2)
        if confidence > best["confidence"]:
            best = {"card": card, "confidence": confidence, "reasons": reasons}

    if best["card"] is None:
        return {"card": {}, "confidence": 0.0, "reasons": []}
    return best


def find_field_updates(existing: dict[str, Any], draft: dict[str, Any]) -> list[dict[str, Any]]:
    updates = []
    for field in UPDATABLE_FIELDS:
        existing_field = get_accessibility_field(existing, field)
        draft_field = get_accessibility_field(draft, field)
        existing_state = existing_field.get("state")
        draft_state = draft_field.get("state")
        if draft_state not in DECISIVE_STATES:
            continue
        if existing_state in LOW_CONFIDENCE_STATES or not existing_state:
            updates.append(field_update(field, existing_field, draft_field))
    return updates


def find_field_conflicts(existing: dict[str, Any], draft: dict[str, Any]) -> list[dict[str, Any]]:
    conflicts = []
    for field in UPDATABLE_FIELDS:
        existing_field = get_accessibility_field(existing, field)
        draft_field = get_accessibility_field(draft, field)
        existing_state = existing_field.get("state")
        draft_state = draft_field.get("state")
        if existing_state in DECISIVE_STATES and draft_state in DECISIVE_STATES and existing_state != draft_state:
            conflicts.append(field_update(field, existing_field, draft_field))
    return conflicts


def field_update(field: str, existing_field: dict[str, Any], draft_field: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": field,
        "existing_state": existing_field.get("state"),
        "existing_note": existing_field.get("note", ""),
        "draft_state": draft_field.get("state"),
        "draft_note": draft_field.get("note", ""),
        "draft_source_ref": draft_field.get("source_ref"),
        "recommended_action": "review_and_update_existing_card",
    }


def get_accessibility_field(card: dict[str, Any], field: str) -> dict[str, Any]:
    value = card.get("accessibility", {}).get(field)
    return value if isinstance(value, dict) else {}


def card_ref(card: dict[str, Any]) -> dict[str, Any]:
    verification = card.get("verification", {})
    return {
        "id": card.get("id", ""),
        "name": card.get("name", ""),
        "region": card.get("region", ""),
        "category": card.get("category", ""),
        "verification_status": verification.get("status", ""),
    }
