"""Import public Jeju place JSON/API data into the internal place catalog JSON."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.catalog import import_catalog_rows, summarize_catalog, write_catalog_json
from src.catalog_providers import SourceDefaults, normalize_public_place_rows
from src.json_records import (
    extract_records,
    fetch_json_payload,
    flatten_record,
    load_json_payload,
    parse_query_pairs,
    write_json_payload,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    imported_at = date.fromisoformat(args.imported_at) if args.imported_at else date.today()
    payload = load_payload(args)

    if args.raw_output:
        write_json_payload(payload, args.raw_output)

    raw_records = extract_records(payload, records_path=args.records_path)
    flattened_rows = [flatten_record(record) for record in raw_records]
    source_defaults = SourceDefaults(
        source_name=args.source_name,
        source_url=args.source_url,
        dataset_name=args.dataset_name,
        license=args.license,
        source_updated_at=args.source_updated_at,
    )
    normalized_rows = normalize_public_place_rows(
        flattened_rows,
        source_defaults=source_defaults,
        default_category=args.default_category,
    )
    skipped = len([row for row in normalized_rows if not row["name"]])
    normalized_rows = [row for row in normalized_rows if row["name"]]

    items = import_catalog_rows(
        normalized_rows,
        imported_at=imported_at,
        accessibility_cards=load_accessibility_cards(args.accessibility_cards),
    )
    write_catalog_json(items, args.output)

    summary = summarize_catalog(items)
    print(f"output={args.output}")
    if args.raw_output:
        print(f"raw_output={args.raw_output}")
    print(
        "summary="
        f"records:{len(raw_records)}, "
        f"imported:{summary.imported}, "
        f"matched:{summary.matched}, "
        f"candidates:{summary.candidates}, "
        f"unmatched:{summary.unmatched}, "
        f"skipped:{skipped}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-json", type=Path, help="Downloaded JSON response path.")
    source.add_argument("--url", help="API URL to fetch.")
    parser.add_argument("--output", type=Path, required=True, help="Output catalog JSON path.")
    parser.add_argument("--raw-output", type=Path, help="Optional raw API payload snapshot path.")
    parser.add_argument("--records-path", help="Dot path to the records list. Auto-detects if omitted.")
    parser.add_argument("--query", action="append", help="API query pair as KEY=VALUE. Repeatable.")
    parser.add_argument("--api-key-env", help="Environment variable containing the API key.")
    parser.add_argument("--api-key-param", default="apiKey", help="API key query parameter name.")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="HTTP timeout for URL fetch.")
    parser.add_argument("--source-name", required=True, help="Public data provider name.")
    parser.add_argument("--source-url", required=True, help="Dataset or API detail URL.")
    parser.add_argument("--dataset-name", required=True, help="Source dataset name.")
    parser.add_argument("--license", default="unknown", help="Source license label.")
    parser.add_argument("--source-updated-at", help="Source updated date in YYYY-MM-DD.")
    parser.add_argument("--default-category", help="Fallback category when source category is missing.")
    parser.add_argument("--accessibility-cards", type=Path, help="Accessibility card JSON path for matching.")
    parser.add_argument("--imported-at", help="Import date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


def load_payload(args: argparse.Namespace):
    if args.input_json:
        return load_json_payload(args.input_json)
    return fetch_json_payload(
        args.url,
        query=parse_query_pairs(args.query),
        api_key_env=args.api_key_env,
        api_key_param=args.api_key_param,
        timeout_seconds=args.timeout_seconds,
    )


def load_accessibility_cards(path: Path | None) -> list[dict]:
    if not path:
        return []
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
