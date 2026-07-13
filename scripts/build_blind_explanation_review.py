from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.explanation_blind_review import (  # noqa: E402
    BlindReviewInputError,
    build_blind_review_packet,
    render_blind_review_csv,
    render_deblind_key_json,
)


DEFAULT_RESULTS = "data/explanation_eval_results.json"
DEFAULT_CASES = "data/explanation_eval_cases.json"
DEFAULT_OUTPUT = "data/explanation_eval_blind_review.csv"
DEFAULT_KEY_OUTPUT = "data/explanation_eval_blind_key.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a balanced, blinded A/B review packet and a separate deblinding key."
    )
    parser.add_argument("--results", default=DEFAULT_RESULTS, help="Automatic evaluation result JSON.")
    parser.add_argument("--cases", default=DEFAULT_CASES, help="Evaluation case JSON used as reviewer reference facts.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Reviewer-facing blind CSV.")
    parser.add_argument("--key-output", default=DEFAULT_KEY_OUTPUT, help="Private deblinding key JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print counts without writing files.")
    parser.add_argument("--force", action="store_true", help="Replace both packet and key. Never use after review starts.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, seed: str | None = None) -> int:
    args = parse_args(argv)
    output_path = Path(args.output)
    key_path = Path(args.key_output)

    try:
        if output_path.resolve() == key_path.resolve():
            raise BlindReviewInputError("--output and --key-output must be different files")
        _require_private_key_path(key_path)
        if not args.dry_run and not args.force:
            existing = [str(path) for path in (output_path, key_path) if path.exists()]
            if existing:
                raise BlindReviewInputError(
                    "refusing to replace an existing blind packet or key; use --force only before review starts: "
                    + ", ".join(existing)
                )

        report = _load_json_object(Path(args.results), "results")
        cases = _load_json_object(Path(args.cases), "cases")
        packet = build_blind_review_packet(
            report,
            seed=seed if seed is not None else secrets.token_urlsafe(32),
            cases=cases,
        )
        csv_text = render_blind_review_csv(packet)
        key_text = render_deblind_key_json(packet)
    except (OSError, json.JSONDecodeError, BlindReviewInputError, ValueError) as exc:
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    counts = packet["deblind_key"]["answer_a_counts"]
    print(
        f"dry_run={'yes' if args.dry_run else 'no'} cases={packet['case_count']} "
        f"answer_a_before={counts['before']} answer_a_after={counts['after']}"
    )
    if args.dry_run:
        return 0

    try:
        _atomic_write(output_path, csv_text, encoding="utf-8-sig")
        _atomic_write(key_path, key_text, encoding="utf-8")
    except OSError as exc:
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"review_csv={output_path}")
    print(f"private_key={key_path}")
    print("warning=share only the review CSV; do not share or commit the private key")
    return 0


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise BlindReviewInputError(f"{label} JSON must be an object")
    return value


def _require_private_key_path(path: Path) -> None:
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError:
        return

    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", relative.as_posix()],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    if result.returncode == 1:
        raise BlindReviewInputError(
            f"private key path inside the repository must be git-ignored: {relative.as_posix()}"
        )
    raise BlindReviewInputError("could not verify that the private key path is git-ignored")


def _atomic_write(path: Path, content: str, *, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding=encoding)
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
