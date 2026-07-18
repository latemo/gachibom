"""Build a service preflight report without exposing secret values."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator


REQUIRED_APP_DATA = [
    {
        "check_id": "app_seed_schema",
        "label": "앱 추천 기본 데이터",
        "data_path": "web/data/app_recommendation_seed.json",
        "schema_path": "data/schemas/app_recommendation_seed.schema.json",
    },
    {
        "check_id": "case_validation_schema",
        "label": "상황별 추천 검증표",
        "data_path": "web/data/recommendation_case_validation_report.json",
        "schema_path": "data/schemas/recommendation_case_validation_report.schema.json",
    },
    {
        "check_id": "operations_readiness_schema",
        "label": "앱용 운영 준비도",
        "data_path": "web/data/operations_readiness_report.json",
        "schema_path": "data/schemas/operations_readiness_report.schema.json",
    },
    {
        "check_id": "service_launch_action_plan_schema",
        "label": "앱용 서비스 실행 계획",
        "data_path": "web/data/service_launch_action_plan.json",
        "schema_path": "data/schemas/service_launch_action_plan.schema.json",
    },
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"OPENAI_API_KEY\s*=\s*['\"]?sk-[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(
        r"KAKAO_MOBILITY_REST_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{20,}",
        re.IGNORECASE,
    ),
]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_service_preflight_report(
    *,
    workspace_root: str | Path = ".",
    generated_at: date | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root)
    effective_env = effective_environment(root, env or os.environ)
    sections = [
        environment_section(root, effective_env),
        runtime_section(root),
        map_location_section(root),
        api_contract_section(root),
        app_data_section(root),
        public_gate_section(root),
        secret_exposure_section(root),
    ]
    checks = [check for section in sections for check in section["checks"]]
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "overall_status": overall_status(checks),
        "summary": summarize_checks(checks),
        "sections": sections,
        "blockers": [check for check in checks if check["status"] == "block"],
        "warnings": [check for check in checks if check["status"] == "warn"],
        "next_actions": next_actions(checks),
        "secret_policy": "비밀값은 리포트에 기록하지 않고 설정 여부만 확인",
    }


def effective_environment(root: Path, env: Mapping[str, str]) -> dict[str, str]:
    values = dict(env)
    for key, value in read_env_file(root / ".env").items():
        values.setdefault(key, value)
    return values


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def environment_section(root: Path, env: Mapping[str, str]) -> dict[str, Any]:
    env_example = root / ".env.example"
    env_file = root / ".env"
    api_key_configured = bool(str(env.get("OPENAI_API_KEY", "")).strip())
    kakao_route_api_key_configured = bool(str(env.get("KAKAO_MOBILITY_REST_API_KEY", "")).strip())
    model = str(env.get("OPENAI_MODEL", "")).strip() or "gpt-5-mini"
    checks = [
        check(
            "env_example_exists",
            "pass" if env_example.exists() else "warn",
            "환경 예시 파일",
            ".env.example",
            "exists",
            "팀원이 키만 입력할 수 있는 예시 파일 필요",
            ".env.example 파일을 추가",
        ),
        check(
            "env_file_exists",
            "pass" if env_file.exists() else "warn",
            "로컬 환경 파일",
            ".env exists" if env_file.exists() else ".env missing",
            "exists for local service",
            "로컬 API 실행 시 .env에서 설정을 읽음",
            ".env.example을 복사해 .env 작성",
        ),
        check(
            "openai_api_key_configured",
            "pass" if api_key_configured else "warn",
            "AI 설명 키 설정",
            "configured" if api_key_configured else "missing",
            "configured",
            "마음동행 AI 설명 생성에 필요한 키 설정 여부. 값은 기록하지 않음",
            "OPENAI_API_KEY 값을 .env 또는 실행 환경에 설정",
        ),
        check(
            "openai_model_configured",
            "pass" if model == "gpt-5-mini" else "warn",
            "AI 모델 설정",
            model,
            "gpt-5-mini",
            "현재 서비스에서 쓰기로 한 모델명",
            "OPENAI_MODEL을 gpt-5-mini로 맞춤",
        ),
        check(
            "kakao_route_api_key_configured",
            "pass" if kakao_route_api_key_configured else "warn",
            "카카오 경로 API 키 설정",
            "configured" if kakao_route_api_key_configured else "missing",
            "configured",
            "서버 경로 API가 카카오모빌리티 길찾기를 우선 사용하기 위한 키 설정 여부. 값은 기록하지 않음",
            "KAKAO_MOBILITY_REST_API_KEY 값을 .env 또는 실행 환경에 설정",
        ),
    ]
    return section("environment", "환경 설정", checks)


def runtime_section(root: Path) -> dict[str, Any]:
    places_path = root / "data/jeju_accessible_spots.json"
    place_count = 0
    places_status = "block"
    places_detail = "장소 데이터를 읽을 수 없음"
    try:
        places = load_json(places_path)
        place_count = len(places) if isinstance(places, list) else 0
        places_status = "pass" if place_count >= 30 else "block"
        places_detail = f"{place_count}개 장소"
    except (OSError, json.JSONDecodeError):
        places_detail = "파일 없음 또는 JSON 오류"

    runtime_files = [
        ("api_server_script", "추천 API 실행 스크립트", "scripts/serve_recommendation_api.py"),
        ("api_handler", "추천 API 핸들러", "src/recommendation_api.py"),
        ("web_index", "앱 첫 화면", "web/index.html"),
        ("map_asset", "중앙 지도 배경 이미지", "web/assets/jeju-final-map-panel-cardless.png"),
    ]
    checks = [
        check(
            check_id,
            "pass" if (root / path).exists() else "block",
            label,
            path if (root / path).exists() else "missing",
            "exists",
            "서비스 실행에 필요한 파일",
            f"{path} 생성 또는 경로 수정",
        )
        for check_id, label, path in runtime_files
    ]
    checks.append(
        check(
            "place_catalog_loadable",
            places_status,
            "추천 장소 데이터",
            places_detail,
            ">= 30개 장소",
            "추천 API와 정적 seed의 원천 장소 데이터",
            "장소 데이터 JSON을 재생성하거나 누락 파일 복구",
        )
    )
    return section("runtime", "서버·앱 실행 파일", checks)


def map_location_section(root: Path) -> dict[str, Any]:
    seed = load_optional_json(root / "web/data/app_recommendation_seed.json") or {}
    route_places = [
        place
        for scenario in seed.get("scenarios", [])
        for place in scenario.get("places", [])
        if isinstance(place, dict)
    ]
    located_places = [place for place in route_places if isinstance(place.get("location"), dict)]
    app_js = read_text_if_exists(root / "web/app.js")
    overrides_valid = is_schema_valid(
        root / "data/place_location_overrides.json",
        root / "data/schemas/place_location_overrides.schema.json",
    )
    checks = [
        check(
            "map_location_overrides",
            "pass" if overrides_valid else "warn",
            "수동 좌표 보강 파일",
            "schema-valid" if overrides_valid else "missing or invalid",
            "schema-valid JSON",
            "로드뷰 메타데이터로 자동 매칭되지 않는 핵심 장소 좌표 보강",
            "data/place_location_overrides.json에 수동 좌표 보강값 추가",
        ),
        check(
            "app_seed_route_locations",
            "pass" if route_places and len(route_places) == len(located_places) else "block",
            "추천 경로 좌표",
            f"{len(located_places)}/{len(route_places)}곳",
            "추천 노출 장소 전체 좌표 보유",
            "중앙 지도에 표시되는 추천 장소가 실제 위도·경도를 갖는지 확인",
            "로드뷰 메타데이터 매칭 또는 수동 좌표 보강 후 앱 seed 재생성",
        ),
        check(
            "frontend_coordinate_projection",
            "pass" if all(token in app_js for token in ["projectMapCoordinate", "map-location-pin", "data-latitude"]) else "block",
            "중앙 지도 좌표 투영",
            "configured" if "projectMapCoordinate" in app_js else "missing",
            "lat/lng projection",
            "고정 픽셀 카드가 아니라 실제 좌표 기반으로 지도 핀과 카드를 배치",
            "web/app.js의 좌표 투영 로직 복구",
        ),
    ]
    return section("map_location", "중앙 지도 위치 계약", checks)


def api_contract_section(root: Path) -> dict[str, Any]:
    handler_path = root / "src/recommendation_api.py"
    test_path = root / "tests/test_recommendation_api.py"
    schema_path = root / "data/schemas/recommendation_result.schema.json"
    handler_text = read_text_if_exists(handler_path)
    test_text = read_text_if_exists(test_path)
    schema_loadable = is_loadable_json(schema_path)
    checks = [
        check(
            "api_contract_tests",
            "pass" if test_path.exists() and "RecommendationApiContractTests" in test_text else "block",
            "추천 API 계약 테스트",
            str(test_path.relative_to(root)).replace("\\", "/") if test_path.exists() else "missing",
            "exists",
            "health, 추천 응답, 오류 응답, 내부 예외 비노출 테스트",
            "tests/test_recommendation_api.py를 추가하고 전체 테스트 실행",
        ),
        check(
            "api_recommendation_schema_contract",
            "pass" if schema_loadable else "block",
            "추천 응답 스키마",
            "loadable" if schema_loadable else "missing or invalid",
            "schema-valid JSON",
            "API 추천 결과가 검증할 JSON 스키마",
            "data/schemas/recommendation_result.schema.json 복구",
        ),
        check(
            "api_structured_error_contract",
            "pass" if all(token in handler_text for token in ["ApiRequestError", "send_error_json", '"code"']) else "block",
            "API 오류 응답 형식",
            "configured" if "send_error_json" in handler_text else "missing",
            "JSON code/error",
            "클라이언트가 오류 원인을 한글 메시지와 code로 구분할 수 있는 계약",
            "추천 API 핸들러의 JSON 오류 응답 계약 복구",
        ),
        check(
            "api_request_body_limit",
            "pass" if all(token in handler_text for token in ["MAX_REQUEST_BODY_BYTES", "REQUEST_ENTITY_TOO_LARGE"]) else "block",
            "요청 본문 크기 제한",
            "configured" if "MAX_REQUEST_BODY_BYTES" in handler_text else "missing",
            "413 on oversized body",
            "비정상 대용량 요청으로 API가 멈추지 않도록 제한",
            "추천 API 본문 크기 제한과 413 응답 복구",
        ),
        check(
            "api_secret_safe_failure",
            "pass" if all(token in handler_text for token in ["recommendation_failed", "exc.__class__.__name__"]) else "block",
            "내부 오류 비노출",
            "configured" if "recommendation_failed" in handler_text else "missing",
            "no raw exception text",
            "실패 응답에 API 키나 내부 예외 원문이 노출되지 않도록 제한",
            "추천 API 내부 예외 응답을 일반화",
        ),
    ]
    return section("api_contract", "추천 API 계약", checks)


def app_data_section(root: Path) -> dict[str, Any]:
    checks = [schema_validation_check(root, target) for target in REQUIRED_APP_DATA]
    checks.append(json_pair_consistency_check(root, "operations_readiness_report.json", "overall_status"))
    checks.append(json_pair_consistency_check(root, "service_launch_action_plan.json", "overall_status"))
    return section("app_data", "앱용 데이터", checks)


def schema_validation_check(root: Path, target: dict[str, str]) -> dict[str, Any]:
    data_path = root / target["data_path"]
    schema_path = root / target["schema_path"]
    if not data_path.exists() or not schema_path.exists():
        return check(
            target["check_id"],
            "block",
            target["label"],
            "missing",
            "schema-valid JSON",
            f"{target['data_path']}와 스키마 존재 여부",
            "데이터 갱신 스크립트를 실행",
        )
    try:
        data = load_json(data_path)
        schema = load_json(schema_path)
        errors = list(Draft202012Validator(schema).iter_errors(data))
    except (OSError, json.JSONDecodeError) as exc:
        return check(
            target["check_id"],
            "block",
            target["label"],
            exc.__class__.__name__,
            "schema-valid JSON",
            "JSON 파싱 또는 파일 읽기 오류",
            "JSON 파일을 재생성",
        )

    return check(
        target["check_id"],
        "pass" if not errors else "block",
        target["label"],
        f"errors {len(errors)}",
        "errors 0",
        f"{target['data_path']} 스키마 검증",
        "데이터 생성 스크립트와 스키마 불일치 수정",
    )


def json_pair_consistency_check(root: Path, file_name: str, field: str) -> dict[str, Any]:
    data_path = root / "data" / file_name
    web_path = root / "web" / "data" / file_name
    label = f"{file_name} 앱 복사본"
    try:
        data_value = load_json(data_path).get(field)
        web_value = load_json(web_path).get(field)
        status = "pass" if data_value == web_value else "warn"
        actual = f"{data_value} / {web_value}"
    except (OSError, json.JSONDecodeError, AttributeError):
        status = "block"
        actual = "missing or invalid"
    return check(
        f"{Path(file_name).stem}_web_consistency",
        status,
        label,
        actual,
        "data와 web/data 동일 상태",
        f"data/{file_name}와 web/data/{file_name}의 {field} 일치 여부",
        "전체 파이프라인 또는 web-output 생성 옵션으로 앱용 JSON 재생성",
    )


def public_gate_section(root: Path) -> dict[str, Any]:
    operations = load_optional_json(root / "data/operations_readiness_report.json")
    action_plan = load_optional_json(root / "data/service_launch_action_plan.json")
    operations_status = operations.get("overall_status", "missing") if operations else "missing"
    action_summary = action_plan.get("summary", {}) if action_plan else {}
    checks = [
        check(
            "operations_public_gate",
            "pass" if operations_status == "ready_for_full_service" else "block",
            "상용 공개 게이트",
            operations_status,
            "ready_for_full_service",
            "운영 준비도 기준의 전체 공개 가능 여부",
            (operations.get("summary", {}) if operations else {}).get("next_action", "운영 준비도 리포트 재생성"),
        ),
        check(
            "missing_roadview_images",
            "pass" if int(action_summary.get("missing_roadview_images", 0)) == 0 else "block",
            "누락 로드뷰 원본",
            f"{int(action_summary.get('missing_roadview_images', 0))}장",
            "0장",
            "로드뷰 원본 1,023장 중 제공기관 404 누락분 해소 여부",
            "누락 원본 수령 후 전체 파이프라인 재실행",
        ),
        check(
            "visual_review_open_places",
            "pass" if int(action_summary.get("visual_review_open_places", 0)) == 0 else "block",
            "시각 검수 대기 장소",
            f"{int(action_summary.get('visual_review_open_places', 0))}곳",
            "0곳",
            "서비스 시드 장소의 출입구·경사·바닥·주차장 동선 검수 완료 여부",
            "팀 검수 CSV 회수 후 전체 파이프라인 재실행",
        ),
    ]
    return section("public_gate", "상용 공개 게이트", checks)


def secret_exposure_section(root: Path) -> dict[str, Any]:
    scanned_paths = [
        path
        for base in [root / "web", root / "docs", root / "src", root / "scripts", root / ".env.example"]
        for path in ([base] if base.is_file() else sorted(base.rglob("*")) if base.exists() else [])
        if path.is_file() and path.suffix.lower() in {"", ".html", ".js", ".css", ".md", ".py", ".json", ".txt"}
    ]
    findings = []
    for path in scanned_paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            findings.append(str(path.relative_to(root)).replace("\\", "/"))
    checks = [
        check(
            "no_frontend_secret_literal",
            "pass" if not findings else "block",
            "비밀값 노출 검사",
            f"{len(findings)}개 의심 파일",
            "0개",
            "web/docs/src/scripts/.env.example 안에 실제 API 키 형태가 없는지 검사. .env 실제 값은 읽어 기록하지 않음",
            "의심 키를 제거하고 키를 폐기·재발급",
        )
    ]
    return section("secret_exposure", "비밀값 노출 방지", checks)


def load_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def is_loadable_json(path: Path) -> bool:
    try:
        load_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    return True


def is_schema_valid(data_path: Path, schema_path: Path) -> bool:
    try:
        data = load_json(data_path)
        schema = load_json(schema_path)
    except (OSError, json.JSONDecodeError):
        return False
    return not list(Draft202012Validator(schema).iter_errors(data))


def section(name: str, label: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "status": overall_status(checks),
        "checks": checks,
    }


def check(
    check_id: str,
    status: str,
    label: str,
    actual: str,
    expected: str,
    detail: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "label": label,
        "actual": actual,
        "expected": expected,
        "detail": detail,
        "next_action": next_action,
    }


def overall_status(checks: list[dict[str, Any]]) -> str:
    if any(item["status"] == "block" for item in checks):
        return "block"
    if any(item["status"] == "warn" for item in checks):
        return "warn"
    return "pass"


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = Counter(item["status"] for item in checks)
    return {
        "total_checks": len(checks),
        "passed_checks": by_status.get("pass", 0),
        "warning_checks": by_status.get("warn", 0),
        "blocker_checks": by_status.get("block", 0),
        "by_status": dict(sorted(by_status.items())),
        "next_action": next_actions(checks)[0] if next_actions(checks) else "",
    }


def next_actions(checks: list[dict[str, Any]]) -> list[str]:
    ordered = [item["next_action"] for item in checks if item["status"] == "block"]
    ordered.extend(item["next_action"] for item in checks if item["status"] == "warn")
    deduped = []
    for action in ordered:
        if action and action not in deduped:
            deduped.append(action)
    return deduped


def render_service_preflight_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 제주의마음 서비스 사전점검 리포트",
        "",
        f"- 기준일: {report['generated_at']}",
        f"- 전체 상태: {status_label(report['overall_status'])}",
        f"- 점검 결과: 통과 {summary['passed_checks']} / 주의 {summary['warning_checks']} / 차단 {summary['blocker_checks']}",
        f"- 비밀값 정책: {report['secret_policy']}",
        "",
        "## 다음 실행",
        "",
    ]
    lines.extend([f"- {action}" for action in report.get("next_actions", [])[:8]] or ["- 추가 조치 없음"])
    for section_item in report["sections"]:
        lines.extend(["", f"## {section_item['label']}", ""])
        for item in section_item["checks"]:
            lines.append(
                f"- {status_label(item['status'])} · {item['label']}: "
                f"{item['actual']} / 기대값 {item['expected']}"
            )
    lines.append("")
    return "\n".join(lines)


def status_label(status: str) -> str:
    labels = {
        "pass": "통과",
        "warn": "주의",
        "block": "차단",
    }
    return labels.get(status, status)
