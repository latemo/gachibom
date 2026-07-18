from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.help_chatbot_service import (  # noqa: E402
    HELP_CHATBOT_EXCLUSION_RULE_VERSION,
    HELP_CHATBOT_MODE_RULE_VERSION,
    HELP_CHATBOT_PRE_VISIT_RULE_VERSION,
    HELP_CHATBOT_PROMPT_VERSION,
    HelpChatbotClient,
    build_help_chatbot_reply,
    openai_help_chatbot_client_from_env,
)
from src.recommendation_service import DEFAULT_OPENAI_MODEL  # noqa: E402


DEFAULT_CASES_PATH = "data/explanation_eval_cases.json"
DEFAULT_SEED_PATH = "web/data/app_recommendation_seed.json"
DEFAULT_OUTPUT_JSON = "data/explanation_eval_results.json"
DEFAULT_OUTPUT_CSV = "data/explanation_eval_results.csv"
DEFAULT_OUTPUT_MD = "docs/explanation_quality_report.md"
DEFAULT_REVIEW_CSV = "data/explanation_eval_human_review.csv"
CHECKPOINT_SCHEMA_VERSION = 1
MAX_WORKERS = 16


class EvaluationInputError(ValueError):
    """Raised when an evaluation fixture is missing or internally inconsistent."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the help-chatbot explanation evaluation with and without recommendation context."
    )
    parser.add_argument("--cases", default=DEFAULT_CASES_PATH, help="Evaluation cases JSON file.")
    parser.add_argument("--seed", default=DEFAULT_SEED_PATH, help="Recommendation seed JSON used by the cases.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print the call plan without API calls or writes.")
    parser.add_argument("--limit", type=positive_int, default=None, help="Run only the first N cases.")
    parser.add_argument("--model", default=DEFAULT_OPENAI_MODEL, help="OpenAI model used for both A/B arms.")
    parser.add_argument("--output-json", default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-md", default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--review-csv", default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--reset-review", action="store_true", help="Replace an existing human-review CSV template.")
    parser.add_argument("--max-workers", type=positive_int, default=2, help=f"Concurrent API calls (maximum {MAX_WORKERS}).")
    parser.add_argument("--retries", type=retry_count, default=2, help="Retries per response when generation fails (0-5).")
    parser.add_argument("--no-resume", action="store_true", help="Ignore a compatible prior result or checkpoint.")
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def retry_count(value: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 5") from exc
    if not 0 <= number <= 5:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 5")
    return number


def validate_model(value: Any) -> str:
    model = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", model):
        raise EvaluationInputError("--model must be a non-empty OpenAI model identifier")
    return model


def load_case_document(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source = _load_json_object_or_list(path, label="cases")
    if isinstance(source, list):
        document: dict[str, Any] = {"cases": source}
    else:
        document = source

    raw_cases = document.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise EvaluationInputError("cases JSON must contain a non-empty 'cases' array")

    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, value in enumerate(raw_cases, start=1):
        if not isinstance(value, dict):
            raise EvaluationInputError(f"case #{index} must be an object")
        case = deepcopy(value)
        case_id = _case_id(case)
        question = _case_question(case)
        if not case_id:
            raise EvaluationInputError(f"case #{index} is missing id")
        if case_id in seen_ids:
            raise EvaluationInputError(f"duplicate case id: {case_id}")
        if not question:
            raise EvaluationInputError(f"case '{case_id}' is missing question")
        case["id"] = case_id
        case["question"] = question
        seen_ids.add(case_id)
        cases.append(case)
    return document, cases


def load_seed(path: str | Path) -> dict[str, Any]:
    seed = _load_json_object_or_list(path, label="seed")
    if not isinstance(seed, dict):
        raise EvaluationInputError("seed JSON must be an object")
    scenarios = seed.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise EvaluationInputError("seed JSON must contain a non-empty 'scenarios' array")
    return seed


def _load_json_object_or_list(path: str | Path, *, label: str) -> dict[str, Any] | list[Any]:
    source_path = Path(path)
    try:
        raw = source_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise EvaluationInputError(f"{label} JSON not found: {source_path}") from exc
    except OSError as exc:
        raise EvaluationInputError(f"could not read {label} JSON: {source_path}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvaluationInputError(
            f"invalid {label} JSON at line {exc.lineno}, column {exc.colno}: {source_path}"
        ) from exc
    if not isinstance(value, (dict, list)):
        raise EvaluationInputError(f"{label} JSON root must be an object or array")
    return value


def prepare_cases(cases: Iterable[dict[str, Any]], seed: dict[str, Any]) -> list[dict[str, Any]]:
    scenario_index = {
        str(item.get("id") or "").strip(): item
        for item in seed.get("scenarios", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    prepared: list[dict[str, Any]] = []
    for source_case in cases:
        case = deepcopy(source_case)
        scenario_id = str(case.get("scenario_id") or "").strip()
        if not scenario_id:
            raise EvaluationInputError(f"case '{case['id']}' is missing scenario_id")
        scenario = scenario_index.get(scenario_id)
        if scenario is None:
            raise EvaluationInputError(f"case '{case['id']}' references unknown scenario_id '{scenario_id}'")

        selected_place_id = _selected_place_id(case)
        if selected_place_id and not _scenario_contains_place(scenario, selected_place_id):
            raise EvaluationInputError(
                f"case '{case['id']}' references unknown selected_place_id '{selected_place_id}'"
            )

        embedded_context = case.get("recommendation_context")
        if embedded_context is not None and not isinstance(embedded_context, dict):
            raise EvaluationInputError(f"case '{case['id']}' recommendation_context must be an object")
        context = (
            deepcopy(embedded_context)
            if isinstance(embedded_context, dict) and embedded_context
            else build_context_from_seed(case, scenario, seed)
        )
        if not context:
            raise EvaluationInputError(f"case '{case['id']}' has no recommendation context for the After arm")
        case["recommendation_context"] = context
        prepared.append(case)
    return prepared


def build_context_from_seed(
    case: dict[str, Any],
    scenario: dict[str, Any],
    seed: dict[str, Any],
) -> dict[str, Any]:
    recommendation = scenario.get("recommendation") if isinstance(scenario.get("recommendation"), dict) else {}
    course = recommendation.get("course") if isinstance(recommendation.get("course"), dict) else {}
    context: dict[str, Any] = {
        "mode": str(case.get("expected_mode") or "static").strip().casefold() or "static",
        "generated_at": scenario.get("generated_at") or seed.get("generated_at") or "",
        "engine": scenario.get("engine") or {"scoring": "precomputed_recommendation_seed"},
        "traveler_summary": scenario.get("traveler_summary") or {},
        "recommendation": {
            "course": {
                "title": course.get("title") or scenario.get("title") or "추천 코스",
                "summary": course.get("summary") or "",
                "pace": course.get("pace") or "unknown",
                "route": [
                    {
                        key: item.get(key)
                        for key in ("order", "spot_id", "name", "purpose", "stay_tip")
                        if item.get(key) is not None
                    }
                    for item in course.get("route", [])[:4]
                    if isinstance(item, dict)
                ],
            },
            "score": recommendation.get("score") or {},
            "fit_reasons": list(recommendation.get("fit_reasons") or [])[:8],
            "deduction_reasons": list(recommendation.get("deduction_reasons") or [])[:8],
            "check_before_visit": list(recommendation.get("check_before_visit") or [])[:8],
        },
    }

    selected_place = _find_selected_place(case, scenario)
    if selected_place is not None:
        context["selected_place"] = {
            "spot_id": selected_place.get("spot_id") or selected_place.get("id"),
            "name": selected_place.get("name"),
            "score": selected_place.get("score") or {},
            "fit_reasons": list(selected_place.get("fit_reasons") or [])[:8],
            "deduction_reasons": list(selected_place.get("deduction_reasons") or [])[:8],
            "check_before_visit": list(selected_place.get("check_before_visit") or [])[:8],
            "source_summary": list(selected_place.get("source_summary") or [])[:3],
            "verification_status": selected_place.get("verification_status")
            or (selected_place.get("verification") or {}).get("status")
            or "needs_check",
            "blocked": bool(selected_place.get("blocked")),
            "block_reasons": list(selected_place.get("block_reasons") or [])[:4],
        }
    return context


def _scenario_contains_place(scenario: dict[str, Any], spot_id: str) -> bool:
    return any(_place_id(place) == spot_id for place in _scenario_places(scenario))


def _scenario_places(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    places = [item for item in scenario.get("places", []) if isinstance(item, dict)]
    route = (scenario.get("recommendation") or {}).get("course", {}).get("route", [])
    return places + [item for item in route if isinstance(item, dict)]


def _find_selected_place(case: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any] | None:
    requested = _selected_place_id(case)
    places = [item for item in scenario.get("places", []) if isinstance(item, dict)]
    if requested:
        return next((place for place in places if _place_id(place) == requested), None)
    if "selected_place_id" in case or "selected_spot" in case:
        return None
    return places[0] if places else None


def _selected_place_id(case: dict[str, Any]) -> str:
    direct = case.get("selected_place_id") or case.get("selected_spot_id")
    selected_spot = case.get("selected_spot")
    nested = selected_spot.get("spot_id") if isinstance(selected_spot, dict) else None
    return str(direct or nested or "").strip()


def _place_id(place: dict[str, Any]) -> str:
    return str(place.get("spot_id") or place.get("id") or "").strip()


def _case_id(case: dict[str, Any]) -> str:
    return str(case.get("id") or case.get("case_id") or "").strip()


def _case_question(case: dict[str, Any]) -> str:
    return str(case.get("question") or case.get("prompt") or "").strip()


def build_jobs(cases: list[dict[str, Any]], model: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for case in cases:
        for variant in ("before", "after"):
            context = case["recommendation_context"] if variant == "after" else None
            legacy_signature_source = {
                "case_id": case["id"],
                "question": case["question"],
                "history": case.get("history") or [],
                "variant": variant,
                "model": model,
                "recommendation_context": context,
            }
            signature_source = {
                **legacy_signature_source,
                "prompt_version": HELP_CHATBOT_PROMPT_VERSION,
            }
            behavior_version = None
            if variant == "after" and case.get("question_type") == "mode_distinction":
                behavior_version = HELP_CHATBOT_MODE_RULE_VERSION
                signature_source["behavior_version"] = behavior_version
            elif variant == "after" and case.get("question_type") == "pre_visit_check":
                behavior_version = HELP_CHATBOT_PRE_VISIT_RULE_VERSION
                signature_source["behavior_version"] = behavior_version
            elif variant == "after" and case.get("question_type") == "exclusion_or_alternative":
                behavior_version = HELP_CHATBOT_EXCLUSION_RULE_VERSION
                signature_source["behavior_version"] = behavior_version
            jobs.append(
                {
                    "case": case,
                    "variant": variant,
                    "behavior_version": behavior_version,
                    "signature": hashlib.sha256(_canonical_json(signature_source).encode("utf-8")).hexdigest(),
                    "legacy_signature": hashlib.sha256(
                        _canonical_json(legacy_signature_source).encode("utf-8")
                    ).hexdigest(),
                }
            )
    return jobs


def run_evaluation_jobs(
    cases: list[dict[str, Any]],
    *,
    model: str,
    client: HelpChatbotClient,
    max_workers: int,
    max_retries: int = 0,
    existing_records: Iterable[dict[str, Any]] = (),
    checkpoint: Callable[[list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    jobs = build_jobs(cases, model)
    reusable = {
        (record.get("case_id"), record.get("variant"), record.get("run_signature")): deepcopy(record)
        for record in existing_records
        if isinstance(record, dict) and record.get("status") == "success"
    }
    records_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    for job in jobs:
        key = (job["case"]["id"], job["variant"])
        resumed = reusable.get((key[0], key[1], job["signature"]))
        if resumed is None:
            legacy = reusable.get((key[0], key[1], job["legacy_signature"]))
            if legacy is not None and not legacy.get("prompt_version"):
                resumed = legacy
        if resumed is not None:
            resumed["resumed"] = True
            resumed["prompt_version"] = HELP_CHATBOT_PROMPT_VERSION
            resumed["run_signature"] = job["signature"]
            records_by_key[key] = resumed
        else:
            pending.append(job)

    safe_workers = min(max(1, int(max_workers)), MAX_WORKERS, max(1, len(pending)))
    if pending:
        with ThreadPoolExecutor(max_workers=safe_workers, thread_name_prefix="explanation-eval") as executor:
            future_jobs = {
                executor.submit(
                    _run_one_job,
                    job,
                    model=model,
                    client=client,
                    max_retries=max_retries,
                ): job
                for job in pending
            }
            for future in as_completed(future_jobs):
                job = future_jobs[future]
                key = (job["case"]["id"], job["variant"])
                try:
                    record = future.result()
                except Exception as exc:  # Defensive: service errors normally become bounded error replies.
                    record = {
                        "case_id": key[0],
                        "variant": key[1],
                        "condition": key[1],
                        "status": "error",
                        "model": model,
                        "prompt_version": HELP_CHATBOT_PROMPT_VERSION,
                        "latency_ms": None,
                        "attempts": max_retries + 1,
                        "run_signature": job["signature"],
                        "response": {
                            "status": "error",
                            "model": model,
                            "answer": f"평가 호출에 실패했습니다: {exc.__class__.__name__}",
                            "followups": [],
                            "handoff_checklist": [],
                        },
                        "completed_at": _utc_now(),
                        "resumed": False,
                    }
                records_by_key[key] = record
                print(f"completed={key[0]}:{key[1]} status={record['status']}")
                if checkpoint is not None:
                    checkpoint(_ordered_records(jobs, records_by_key))

    return _ordered_records(jobs, records_by_key)


def _run_one_job(
    job: dict[str, Any],
    *,
    model: str,
    client: HelpChatbotClient,
    max_retries: int,
) -> dict[str, Any]:
    case = job["case"]
    variant = job["variant"]
    history = case.get("history") if isinstance(case.get("history"), list) else []
    started = time.perf_counter()
    response: dict[str, Any] = {}
    attempts = 0
    for attempt in range(max(0, int(max_retries)) + 1):
        attempts = attempt + 1
        if variant == "after":
            response = build_help_chatbot_reply(
                case["question"],
                history=history,
                recommendation_context=case["recommendation_context"],
                model=model,
                client=client,
            )
        else:
            response = build_help_chatbot_reply(
                case["question"],
                history=history,
                model=model,
                client=client,
            )
        if response.get("status") == "success" or attempt >= max_retries:
            break
        time.sleep(min(1.0, 0.25 * (2**attempt)))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "case_id": case["id"],
        "variant": variant,
        "condition": variant,
        "status": response.get("status") or "error",
        "model": model,
        "prompt_version": HELP_CHATBOT_PROMPT_VERSION,
        "behavior_version": job.get("behavior_version"),
        "latency_ms": elapsed_ms,
        "attempts": attempts,
        "run_signature": job["signature"],
        "response": response,
        "completed_at": _utc_now(),
        "resumed": False,
    }


def _ordered_records(
    jobs: list[dict[str, Any]], records_by_key: dict[tuple[str, str], dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        records_by_key[(job["case"]["id"], job["variant"])]
        for job in jobs
        if (job["case"]["id"], job["variant"]) in records_by_key
    ]


def load_resume_records(paths: Iterable[Path]) -> list[dict[str, Any]]:
    for path in paths:
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        records = value.get("records") if isinstance(value, dict) else None
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    return []


def checkpoint_path(output_json: str | Path) -> Path:
    path = Path(output_json)
    return path.with_name(f"{path.name}.checkpoint.json")


def build_report(
    cases: list[dict[str, Any]],
    records: list[dict[str, Any]],
    *,
    model: str,
    cases_path: str,
    seed_path: str,
) -> tuple[dict[str, Any], str, str]:
    core = _load_eval_core()
    generated_at = _utc_now()
    if core is not None:
        report = core.build_explanation_evaluation_report(cases, records, generated_at=generated_at)
        if not isinstance(report, dict):
            raise RuntimeError("evaluation core returned a non-object report")
    else:
        report = _fallback_report(cases, records)

    report["run"] = {
        "status": "complete" if all(record.get("status") == "success" for record in records) else "completed_with_errors",
        "generated_at": generated_at,
        "model": model,
        "prompt_version": HELP_CHATBOT_PROMPT_VERSION,
        "fresh_records": sum(1 for record in records if not record.get("resumed")),
        "resumed_records": sum(1 for record in records if record.get("resumed")),
        "cases_path": cases_path,
        "seed_path": seed_path,
        "ab_definition": {
            "before": "질문과 대화 기록만 전달",
            "after": "동일 질문과 대화 기록에 recommendation_context 추가",
        },
    }
    report.setdefault("records", records)
    if core is not None:
        csv_text = core.render_evaluations_csv(report)
        markdown = core.render_explanation_evaluation_markdown(report)
        to_json_ready = getattr(core, "to_json_ready", None)
        if callable(to_json_ready):
            report = to_json_ready(report)
    else:
        csv_text = _fallback_csv(cases, records)
        markdown = _fallback_markdown(report)
    return report, csv_text, markdown


def _load_eval_core() -> Any | None:
    for module_name in ("src.explanation_eval", "src.explanation_evaluation", "src.explanation_eval_core"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        required = (
            "build_explanation_evaluation_report",
            "render_evaluations_csv",
            "render_explanation_evaluation_markdown",
        )
        if all(callable(getattr(module, name, None)) for name in required):
            return module
    return None


def _fallback_report(cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    successes = sum(record.get("status") == "success" for record in records)
    return {
        "schema_version": "1.0",
        "generated_at": _utc_now(),
        "summary": {
            "total_cases": len(cases),
            "total_responses": len(records),
            "successful_responses": successes,
            "failed_responses": len(records) - successes,
        },
        "records": records,
    }


def _fallback_csv(cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> str:
    case_index = {case["id"]: case for case in cases}
    output = StringIO()
    fields = ["case_id", "scenario_id", "question_type", "variant", "status", "model", "latency_ms", "answer"]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for record in records:
        case = case_index.get(record.get("case_id"), {})
        writer.writerow(
            {
                "case_id": record.get("case_id"),
                "scenario_id": case.get("scenario_id"),
                "question_type": case.get("question_type"),
                "variant": record.get("variant"),
                "status": record.get("status"),
                "model": record.get("model"),
                "latency_ms": record.get("latency_ms"),
                "answer": (record.get("response") or {}).get("answer", ""),
            }
        )
    return output.getvalue()


def _fallback_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return "\n".join(
        [
            "# 설명 품질 Before/After 평가",
            "",
            "자동 채점 모듈이 없는 환경에서 생성된 실행 결과입니다.",
            "",
            f"- 케이스: {summary['total_cases']}개",
            f"- 성공 응답: {summary['successful_responses']}/{summary['total_responses']}",
            "",
        ]
    )


def render_review_csv(cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> str:
    record_index = {(record.get("case_id"), record.get("variant")): record for record in records}
    output = StringIO()
    fields = [
        "case_id",
        "scenario_id",
        "question_type",
        "question",
        "expected_score",
        "expected_evidence",
        "expected_user_conditions",
        "before_answer",
        "after_answer",
        "before_correctness_1_5",
        "after_correctness_1_5",
        "before_understanding_1_5",
        "after_understanding_1_5",
        "before_decision_help_1_5",
        "after_decision_help_1_5",
        "before_previsit_clarity_yes_no",
        "after_previsit_clarity_yes_no",
        "before_hallucination_yes_no",
        "after_hallucination_yes_no",
        "before_safety_issue_yes_no",
        "after_safety_issue_yes_no",
        "reviewer_id",
        "review_status",
        "reviewer_notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for case in cases:
        before = record_index.get((case["id"], "before"), {})
        after = record_index.get((case["id"], "after"), {})
        writer.writerow(
            {
                "case_id": case["id"],
                "scenario_id": case.get("scenario_id", ""),
                "question_type": case.get("question_type", ""),
                "question": case["question"],
                "expected_score": case.get("expected_score", ""),
                "expected_evidence": json.dumps(case.get("expected_evidence", []), ensure_ascii=False),
                "expected_user_conditions": json.dumps(case.get("expected_user_conditions", []), ensure_ascii=False),
                "before_answer": (before.get("response") or {}).get("answer", ""),
                "after_answer": (after.get("response") or {}).get("answer", ""),
                "before_correctness_1_5": "",
                "after_correctness_1_5": "",
                "before_understanding_1_5": "",
                "after_understanding_1_5": "",
                "before_decision_help_1_5": "",
                "after_decision_help_1_5": "",
                "before_previsit_clarity_yes_no": "",
                "after_previsit_clarity_yes_no": "",
                "before_hallucination_yes_no": "",
                "after_hallucination_yes_no": "",
                "before_safety_issue_yes_no": "",
                "after_safety_issue_yes_no": "",
                "reviewer_id": "",
                "review_status": "pending",
                "reviewer_notes": "",
            }
        )
    return output.getvalue()


def write_outputs(
    *,
    report: dict[str, Any],
    csv_text: str,
    markdown: str,
    review_csv: str,
    output_json: str | Path,
    output_csv: str | Path,
    output_md: str | Path,
    review_csv_path: str | Path,
) -> None:
    _atomic_write(Path(output_json), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(Path(output_csv), csv_text)
    _atomic_write(Path(output_md), markdown)
    _atomic_write(Path(review_csv_path), review_csv)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None, *, client: HelpChatbotClient | None = None) -> int:
    args = parse_args(argv)
    try:
        model = validate_model(args.model)
        _, loaded_cases = load_case_document(args.cases)
        seed = load_seed(args.seed)
        selected_cases = loaded_cases[: args.limit] if args.limit else loaded_cases
        cases = prepare_cases(selected_cases, seed)
    except EvaluationInputError as exc:
        print(f"error={exc}", file=sys.stderr)
        return 2

    jobs = build_jobs(cases, model)
    if args.dry_run:
        print(f"dry_run=ok cases={len(cases)} calls={len(jobs)} model={model}")
        print("before_context=omitted after_context=included")
        return 0

    if client is None:
        client = openai_help_chatbot_client_from_env()
    if client is None:
        print(
            "error=OPENAI_API_KEY is required for an evaluation run; use --dry-run to validate without API calls",
            file=sys.stderr,
        )
        return 2

    output_json = Path(args.output_json)
    checkpoint_file = checkpoint_path(output_json)
    existing_records = [] if args.no_resume else load_resume_records([checkpoint_file, output_json])

    def save_checkpoint(records: list[dict[str, Any]]) -> None:
        payload = {
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "status": "in_progress",
            "model": model,
            "prompt_version": HELP_CHATBOT_PROMPT_VERSION,
            "updated_at": _utc_now(),
            "records": records,
        }
        _atomic_write(checkpoint_file, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    records = run_evaluation_jobs(
        cases,
        model=model,
        client=client,
        max_workers=min(args.max_workers, MAX_WORKERS),
        max_retries=args.retries,
        existing_records=existing_records,
        checkpoint=save_checkpoint,
    )
    report, csv_text, markdown = build_report(
        cases,
        records,
        model=model,
        cases_path=str(args.cases),
        seed_path=str(args.seed),
    )
    review_path = Path(args.review_csv)
    if review_path.exists() and not args.reset_review:
        review_csv_text = review_path.read_text(encoding="utf-8-sig")
    else:
        review_csv_text = render_review_csv(cases, records)
    write_outputs(
        report=report,
        csv_text=csv_text,
        markdown=markdown,
        review_csv=review_csv_text,
        output_json=args.output_json,
        output_csv=args.output_csv,
        output_md=args.output_md,
        review_csv_path=args.review_csv,
    )
    final_checkpoint = {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "status": "complete",
        "model": model,
        "prompt_version": HELP_CHATBOT_PROMPT_VERSION,
        "updated_at": _utc_now(),
        "records": records,
    }
    _atomic_write(checkpoint_file, json.dumps(final_checkpoint, ensure_ascii=False, indent=2) + "\n")

    success_count = sum(record.get("status") == "success" for record in records)
    print(f"output_json={args.output_json}")
    print(f"output_csv={args.output_csv}")
    print(f"output_md={args.output_md}")
    print(f"review_csv={args.review_csv}")
    print(f"summary=cases:{len(cases)}, responses:{success_count}/{len(records)}")
    return 0 if success_count == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
