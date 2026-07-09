from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tourism_weak_courses import (
    build_tourism_weak_course_dataset,
    read_course_csv,
    write_tourism_weak_courses,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import 제주관광공사 tourism-weak recommendation courses.")
    parser.add_argument("--input", type=Path, required=True, help="15117357 CSV path.")
    parser.add_argument("--places", type=Path, default=Path("data/jeju_accessible_spots.json"))
    parser.add_argument("--output", type=Path, default=Path("data/tourism_weak_recommendation_courses.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_course_csv(args.input)
    places = json.loads(args.places.read_text(encoding="utf-8"))
    dataset = build_tourism_weak_course_dataset(rows, places)
    write_tourism_weak_courses(dataset, args.output)
    summary = dataset["summary"]
    print(
        "tourism_weak_courses_output="
        f"{args.output}\nsummary=courses:{summary['courses']}, "
        f"stops:{summary['stops']}, matched_places:{summary['matched_places']}, "
        f"unmatched_places:{summary['unmatched_places']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
