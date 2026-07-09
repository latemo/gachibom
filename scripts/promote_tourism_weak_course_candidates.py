from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.place_locations import build_place_location_index, load_json_list
from src.tourism_weak_courses import build_promoted_course_place_cards, load_tourism_weak_courses


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote unmatched tourism-weak course stops as limited place cards.")
    parser.add_argument("--courses", type=Path, default=Path("data/tourism_weak_recommendation_courses.json"))
    parser.add_argument("--places", type=Path, default=Path("data/jeju_accessible_spots.json"))
    parser.add_argument("--output", type=Path, default=Path("data/jeju_accessible_spots.json"))
    parser.add_argument("--roadview-metadata", type=Path, default=Path("data/roadview_image_metadata.json"))
    parser.add_argument("--checked-at", default="2026-05-28")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    places = json.loads(args.places.read_text(encoding="utf-8"))
    course_dataset = load_tourism_weak_courses(args.courses)
    promoted_cards = build_promoted_course_place_cards(course_dataset, places, checked_at=args.checked_at)
    locatable_ids = set(
        build_place_location_index(
            promoted_cards,
            roadview_metadata=load_json_list(args.roadview_metadata),
            overrides=[],
        )
    )

    for card in promoted_cards:
        if card["id"] in locatable_ids:
            continue
        card["verification"]["status"] = "needs_check"
        missing_fields = set(card["verification"]["missing_fields"])
        missing_fields.add("location")
        card["verification"]["missing_fields"] = sorted(missing_fields)
        card["operator_notes"] += " 좌표 근거가 없어 코스 콘텐츠 우선 후보로 제한."

    output_places = places + promoted_cards
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_places, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "tourism_weak_promoted_places="
        f"{len(promoted_cards)}\nlocatable_promoted_places={len(locatable_ids)}\n"
        f"needs_check_promoted_places={len(promoted_cards) - len(locatable_ids)}\noutput={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
