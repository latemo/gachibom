from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app_recommendations import build_app_recommendation_seed
from src.place_locations import load_json_list, build_place_location_index
from src.tourism_weak_courses import augment_places_with_tourism_weak_courses, load_tourism_weak_courses


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build app-facing recommendation seed data.")
    parser.add_argument("--places", default="data/jeju_accessible_spots.json")
    parser.add_argument("--output", default="web/data/app_recommendation_seed.json")
    parser.add_argument("--roadview-metadata", default="data/roadview_image_metadata.json")
    parser.add_argument("--location-overrides", default="data/place_location_overrides.json")
    parser.add_argument("--tourism-weak-courses", default="data/tourism_weak_recommendation_courses.json")
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    places = json.loads(Path(args.places).read_text(encoding="utf-8"))
    course_dataset_path = Path(args.tourism_weak_courses)
    course_dataset = {}
    if course_dataset_path.exists():
        course_dataset = load_tourism_weak_courses(course_dataset_path)
        places = augment_places_with_tourism_weak_courses(places, course_dataset)
    location_index = build_place_location_index(
        places,
        roadview_metadata=load_json_list(args.roadview_metadata),
        overrides=load_json_list(args.location_overrides),
    )
    seed = build_app_recommendation_seed(
        places,
        generated_at=generated_at,
        location_index=location_index,
        tourism_weak_course_dataset=course_dataset,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "app_recommendation_seed_output="
        f"{output_path}\nsummary=scenarios:{len(seed['scenarios'])}, "
        f"candidate_places:{seed['public_gate']['app_candidate_places']}, "
        f"locations:{len(location_index)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
