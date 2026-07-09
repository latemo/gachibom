from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web" / "assets" / "jeju-final-map-panel-cardless-source.png"
OUTPUT = ROOT / "web" / "assets" / "jeju-final-map-panel-cardless.png"
TARGET_SIZE = (816, 931)


def build_cardless_background(source: Path = SOURCE, output: Path = OUTPUT) -> None:
    image = Image.open(source).convert("RGB").resize(TARGET_SIZE, Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the approved cardless Jeju map panel asset for the web app.",
    )
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_cardless_background(args.source, args.output)
