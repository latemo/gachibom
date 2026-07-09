from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.recommendation_api import (
    DEFAULT_LOCATION_OVERRIDES_PATH,
    DEFAULT_PLACES_PATH,
    DEFAULT_ROADVIEW_METADATA_PATH,
    DEFAULT_TOURISM_WEAK_COURSES_PATH,
    DEFAULT_WEB_DIR,
    run_server,
)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Jeju Maeum web app and recommendation API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--web-dir", type=Path, default=DEFAULT_WEB_DIR)
    parser.add_argument("--places", type=Path, default=DEFAULT_PLACES_PATH)
    parser.add_argument("--roadview-metadata", type=Path, default=DEFAULT_ROADVIEW_METADATA_PATH)
    parser.add_argument("--location-overrides", type=Path, default=DEFAULT_LOCATION_OVERRIDES_PATH)
    parser.add_argument("--tourism-weak-courses", type=Path, default=DEFAULT_TOURISM_WEAK_COURSES_PATH)
    parser.add_argument("--generated-at", default=date.today().isoformat())
    args = parser.parse_args()

    load_env_file(ROOT / ".env")
    run_server(
        host=args.host,
        port=args.port,
        web_dir=args.web_dir,
        places_path=args.places,
        roadview_metadata_path=args.roadview_metadata,
        location_overrides_path=args.location_overrides,
        tourism_weak_courses_path=args.tourism_weak_courses,
        generated_at=date.fromisoformat(args.generated_at),
    )


if __name__ == "__main__":
    main()
