"""JSON record extraction helpers for public API ingestion."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def load_json_payload(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json_payload(payload: Any, path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_json_payload(
    url: str,
    *,
    query: Mapping[str, str] | None = None,
    api_key_env: str | None = None,
    api_key_param: str | None = None,
    timeout_seconds: int = 30,
) -> Any:
    """Fetch a JSON payload without logging or exposing API key values."""

    params = dict(query or {})
    if api_key_env:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {api_key_env}")
        params[api_key_param or "apiKey"] = api_key

    request_url = append_query(url, params)
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def extract_records(payload: Any, *, records_path: str | None = None) -> list[dict[str, Any]]:
    """Extract mapping records from common public API JSON response shapes."""

    if records_path:
        selected = select_path(payload, records_path)
        return coerce_records(selected)

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        records = coerce_records(payload)
        if records:
            return records

    candidates: list[list[dict[str, Any]]] = []
    collect_record_lists(payload, candidates)
    if candidates:
        return max(candidates, key=len)
    if isinstance(payload, Mapping) and looks_like_record(payload):
        return [dict(payload)]
    return []


def flatten_record(record: Mapping[str, Any]) -> dict[str, str]:
    """Flatten nested JSON objects while preserving useful leaf field names."""

    flattened: dict[str, str] = {}

    def visit(value: Any, path: list[str]) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                visit(child, [*path, str(key)])
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            flattened["".join(path)] = "|".join(stringify(part) for part in value if stringify(part))
            return

        text = stringify(value)
        if not text:
            return
        joined = "".join(path)
        flattened[joined] = text
        if path:
            flattened.setdefault(path[-1], text)

    visit(record, [])
    return flattened


def coerce_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(value)] if looks_like_record(value) else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        records = [dict(item) for item in value if isinstance(item, Mapping)]
        return records if len(records) == len(value) else []
    return []


def collect_record_lists(value: Any, candidates: list[list[dict[str, Any]]]) -> None:
    if isinstance(value, Mapping):
        for child in value.values():
            collect_record_lists(child, candidates)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        records = coerce_records(value)
        if records:
            candidates.append(records)
            return
        for child in value:
            collect_record_lists(child, candidates)


def looks_like_record(value: Mapping[str, Any]) -> bool:
    scalar_count = sum(1 for item in value.values() if not isinstance(item, (Mapping, list, tuple)))
    return scalar_count >= 2


def select_path(payload: Any, records_path: str) -> Any:
    current = payload
    for part in records_path.split("."):
        if not part:
            continue
        if isinstance(current, Mapping):
            current = current[part]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            current = current[int(part)]
        else:
            raise KeyError(f"Cannot select {part!r} from {type(current).__name__}")
    return current


def parse_query_pairs(pairs: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"Query pair must be KEY=VALUE: {pair}")
        key, value = pair.split("=", 1)
        result[key] = value
    return result


def append_query(url: str, params: Mapping[str, str]) -> str:
    if not params:
        return url
    parsed = urllib.parse.urlsplit(url)
    existing = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    existing.update(params)
    return urllib.parse.urlunsplit(
        parsed._replace(query=urllib.parse.urlencode(existing, doseq=True))
    )


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    return str(value).strip()
