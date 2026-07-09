"""Download requested Jeju roadview image files from the public GIS endpoint."""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

ROADVIEW_IMAGE_BASE_URL = "https://gis.jeju.go.kr/images/roadview"
DEFAULT_USER_AGENT = "JejuMaeumAccessibilityService/1.0"


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class DownloadOptions:
    target_root: Path
    tier: str = "priority"
    overwrite: bool = False
    dry_run: bool = False
    timeout_seconds: int = 60
    limit: int | None = None
    base_url: str = ROADVIEW_IMAGE_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT


def build_roadview_image_download_report(
    acquisition_request: dict[str, Any],
    *,
    target_root: str | Path = "data/raw/roadview_images",
    tier: str = "priority",
    overwrite: bool = False,
    dry_run: bool = False,
    timeout_seconds: int = 60,
    limit: int | None = None,
    generated_at: date | None = None,
    opener: Callable[[urllib.request.Request, int], Any] | None = None,
) -> dict[str, Any]:
    """Download requested images and return a machine-readable report.

    `tier` can be `priority` for visual review samples, `supplemental` for the
    remaining place sequence images, or `all` for the full service-seed set.
    """

    options = DownloadOptions(
        target_root=Path(target_root),
        tier=tier,
        overwrite=overwrite,
        dry_run=dry_run,
        timeout_seconds=timeout_seconds,
        limit=limit,
    )
    entries = list(download_plan_entries(acquisition_request, options))
    results = [
        download_one(entry, options, opener=opener)
        for entry in entries
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_roadview_image_acquisition_request_generated_at": acquisition_request.get("generated_at"),
        "source_endpoint": ROADVIEW_IMAGE_BASE_URL,
        "target_root": str(options.target_root).replace("\\", "/"),
        "tier": tier,
        "dry_run": dry_run,
        "overwrite": overwrite,
        "summary": summarize_download_results(results),
        "items": results,
    }


def download_plan_entries(
    acquisition_request: dict[str, Any],
    options: DownloadOptions,
) -> Iterable[dict[str, Any]]:
    count = 0
    for item in acquisition_request.get("items", []):
        card = item.get("card", {})
        for image in acquisition_images_for_tier(item, options.tier):
            if options.limit is not None and count >= options.limit:
                return
            image_file_name = image.get("image_file_name", "")
            target_path = target_image_path(options.target_root, image_file_name)
            yield {
                "card_id": card.get("id", ""),
                "place_name": card.get("name", ""),
                "image_file_name": image_file_name,
                "request_tier": image.get("request_tier", ""),
                "tourist_name": image.get("tourist_name", ""),
                "tourist_name_en": image.get("tourist_name_en", ""),
                "captured_at": image.get("captured_at"),
                "source_url": roadview_image_url(image, base_url=options.base_url),
                "target_path": str(target_path).replace("\\", "/"),
            }
            count += 1


def acquisition_images_for_tier(item: dict[str, Any], tier: str) -> list[dict[str, Any]]:
    if tier == "priority":
        return item.get("priority_images", [])
    if tier == "supplemental":
        return item.get("supplemental_images", [])
    if tier == "all":
        return item.get("priority_images", []) + item.get("supplemental_images", [])
    raise ValueError("tier must be one of: priority, supplemental, all")


def roadview_image_url(image: dict[str, Any], *, base_url: str = ROADVIEW_IMAGE_BASE_URL) -> str:
    tourist_name_en = str(image.get("tourist_name_en", "")).strip()
    image_file_name = Path(str(image.get("image_file_name", "")).strip()).stem
    quoted_place = urllib.parse.quote(tourist_name_en)
    quoted_file = urllib.parse.quote(f"{image_file_name}.jpg")
    return f"{base_url.rstrip('/')}/{quoted_place}/{quoted_file}"


def target_image_path(target_root: Path, image_file_name: str) -> Path:
    return target_root / f"{Path(image_file_name).stem}.jpg"


def download_one(
    entry: dict[str, Any],
    options: DownloadOptions,
    *,
    opener: Callable[[urllib.request.Request, int], Any] | None = None,
) -> dict[str, Any]:
    target_path = Path(entry["target_path"])
    result = dict(entry)

    if target_path.exists() and not options.overwrite:
        result.update(
            {
                "status": "skipped_existing",
                "http_status": None,
                "file_size_bytes": target_path.stat().st_size,
                "error": "",
            }
        )
        return result

    if options.dry_run:
        result.update(
            {
                "status": "planned",
                "http_status": None,
                "file_size_bytes": None,
                "error": "",
            }
        )
        return result

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + ".part")
    request = urllib.request.Request(
        entry["source_url"],
        headers={"User-Agent": options.user_agent},
    )
    open_url = opener or default_urlopen

    try:
        with open_url(request, options.timeout_seconds) as response:
            status = getattr(response, "status", None) or getattr(response, "code", None)
            with temp_path.open("wb") as file:
                shutil.copyfileobj(response, file)
        temp_path.replace(target_path)
        result.update(
            {
                "status": "downloaded",
                "http_status": status,
                "file_size_bytes": target_path.stat().st_size,
                "error": "",
            }
        )
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        if temp_path.exists():
            temp_path.unlink()
        result.update(
            {
                "status": "failed",
                "http_status": http_error_status(error),
                "file_size_bytes": None,
                "error": str(error),
            }
        )
    return result


def default_urlopen(request: urllib.request.Request, timeout_seconds: int) -> Any:
    return urllib.request.urlopen(request, timeout=timeout_seconds)


def http_error_status(error: BaseException) -> int | None:
    return (
        getattr(error, "code", None)
        or getattr(getattr(error, "response", None), "status", None)
        or getattr(getattr(error, "response", None), "code", None)
    )


def summarize_download_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    bytes_downloaded = 0
    for result in results:
        status = result.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        if status == "downloaded":
            bytes_downloaded += int(result.get("file_size_bytes") or 0)
    return {
        "total_items": len(results),
        "downloaded": by_status.get("downloaded", 0),
        "skipped_existing": by_status.get("skipped_existing", 0),
        "planned": by_status.get("planned", 0),
        "failed": by_status.get("failed", 0),
        "bytes_downloaded": bytes_downloaded,
        "by_status": by_status,
    }


def build_roadview_provider_404_image_report(
    download_report: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> dict[str, Any]:
    provider_404_items = [
        provider_404_image_item(item)
        for item in download_report.get("items", [])
        if is_provider_404_failure(item)
    ]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "source_roadview_image_download_report_generated_at": download_report.get("generated_at"),
        "source_download_report_tier": download_report.get("tier"),
        "source_endpoint": download_report.get("source_endpoint"),
        "classification": "provider_image_server_404",
        "criteria": {
            "provider_404": "다운로드 요청 대상이 공공 API 메타데이터에는 있으나 이미지 서버가 HTTP 404를 반환한 원본",
            "gate_policy": "제공기관 복구 또는 별도 대체 원본 수령 전에는 전체 1,023장 수령 게이트를 통과시키지 않음",
        },
        "summary": summarize_provider_404_items(provider_404_items),
        "items": provider_404_items,
        "recommended_action": (
            "제공기관에 404 원본 이미지 복구 또는 대체 원본 수령을 요청하고, "
            "복구 전에는 전체 원본 수령 게이트를 차단 상태로 유지한다."
        ),
    }


def is_provider_404_failure(item: dict[str, Any]) -> bool:
    if item.get("status") != "failed":
        return False
    return item.get("http_status") == 404 or "HTTP Error 404" in str(item.get("error", ""))


def provider_404_image_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_id": item.get("card_id", ""),
        "place_name": item.get("place_name", ""),
        "image_file_name": item.get("image_file_name", ""),
        "request_tier": item.get("request_tier", ""),
        "tourist_name": item.get("tourist_name", ""),
        "tourist_name_en": item.get("tourist_name_en", ""),
        "captured_at": item.get("captured_at"),
        "source_url": item.get("source_url", ""),
        "error": item.get("error", ""),
    }


def summarize_provider_404_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_place: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    for item in items:
        place_name = item.get("place_name", "")
        request_tier = item.get("request_tier", "")
        by_place[place_name] = by_place.get(place_name, 0) + 1
        by_tier[request_tier] = by_tier.get(request_tier, 0) + 1
    return {
        "provider_404_images": len(items),
        "affected_places": len(by_place),
        "by_place": dict(sorted(by_place.items())),
        "by_request_tier": dict(sorted(by_tier.items())),
    }
