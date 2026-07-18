from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ragas_change_tracking import (  # noqa: E402
    RagasChangeTrackingError,
    build_change_detail_report,
    render_change_detail_markdown,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild per-change RAGAS before/after reports from immutable runs."
    )
    parser.add_argument("--history", default="data/ragas_change_history.json")
    parser.add_argument("--change-id", action="append", default=[])
    parser.add_argument("--output-root", default="data/ragas_change_reports")
    parser.add_argument("--markdown-root", default="docs/ragas_change_reports")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        history = _load_json(_path(args.history))
        changes = history.get("changes")
        if not isinstance(changes, list):
            raise RagasChangeTrackingError("history changes must be an array")
        requested = set(args.change_id)
        selected = [
            change
            for change in changes
            if isinstance(change, dict)
            and (not requested or str(change.get("change_id")) in requested)
        ]
        missing = requested - {str(change.get("change_id")) for change in selected}
        if missing:
            raise RagasChangeTrackingError(
                "unknown change ids: " + ", ".join(sorted(missing))
            )
        for change in selected:
            previous = _load_json(_path(str(change["previous_run"])))
            current = _load_json(_path(str(change["current_run"])))
            report = build_change_detail_report(
                change=change, previous=previous, current=current
            )
            change_id = str(change["change_id"])
            json_path = _path(args.output_root) / f"{change_id}.json"
            markdown_path = _path(args.markdown_root) / f"{change_id}.md"
            _atomic_write(
                json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            )
            _atomic_write(markdown_path, render_change_detail_markdown(report))
            print(f"report={_display(markdown_path)}")
    except (OSError, json.JSONDecodeError, RagasChangeTrackingError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 2
    print(f"reports={len(selected)}")
    return 0


def _path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RagasChangeTrackingError(f"JSON root must be an object: {path}")
    return value


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
