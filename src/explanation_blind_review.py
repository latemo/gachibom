"""Build deterministic, balanced blind-review packets for explanation A/B tests.

The functions in this module are intentionally pure: callers provide the
evaluation report (and, optionally, the source evaluation cases) and decide
where to persist the returned CSV and JSON strings.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from io import StringIO
from typing import Any


BLIND_REVIEW_SCHEMA_VERSION = "1.0"

BLIND_REVIEW_CSV_FIELDS = (
    "blind_id",
    "immutable_fingerprint",
    "question_type",
    "previsit_applicable",
    "question",
    "reference_facts",
    "answer_a",
    "answer_b",
    "answer_a_correctness_1_5",
    "answer_b_correctness_1_5",
    "answer_a_understanding_1_5",
    "answer_b_understanding_1_5",
    "answer_a_decision_help_1_5",
    "answer_b_decision_help_1_5",
    "answer_a_previsit_clarity_yes_no",
    "answer_b_previsit_clarity_yes_no",
    "answer_a_hallucination_yes_no",
    "answer_b_hallucination_yes_no",
    "answer_a_safety_issue_yes_no",
    "answer_b_safety_issue_yes_no",
    "preference",
    "reviewer_id",
    "review_status",
    "notes",
)

_VARIANTS = ("before", "after")


class BlindReviewInputError(ValueError):
    """Raised when an evaluation report cannot form an unambiguous A/B pair."""


def compute_source_fingerprint(report: Mapping[str, Any]) -> str:
    """Return a stable fingerprint of the question/response material under review.

    Volatile report metadata such as ``generated_at``, latency, and aggregate
    metrics is deliberately excluded.  Entries are normalized and sorted by
    case id and variant before hashing.
    """

    prepared = _prepare_report(report)
    return _fingerprint_prepared(prepared)


def compute_review_row_fingerprint(row: Mapping[str, Any]) -> str:
    """Fingerprint the immutable reviewer-visible portion of one review row.

    Rating, preference, reviewer, status, and note fields are intentionally
    excluded so reviewers can fill them in.  ``reference_facts`` is parsed and
    canonically re-serialized, making harmless JSON whitespace changes stable
    while detecting semantic changes.
    """

    if not isinstance(row, Mapping):
        raise BlindReviewInputError("review row must be an object")
    required_text_fields = (
        "blind_id",
        "question_type",
        "previsit_applicable",
        "question",
        "answer_a",
        "answer_b",
    )
    immutable: dict[str, Any] = {}
    for field in required_text_fields:
        value = _normalize_text(row.get(field))
        if not value:
            raise BlindReviewInputError(f"review row is missing immutable field: {field}")
        immutable[field] = value

    reference_value = row.get("reference_facts")
    if isinstance(reference_value, str):
        try:
            reference_value = json.loads(reference_value)
        except json.JSONDecodeError as exc:
            raise BlindReviewInputError(f"review row reference_facts is not valid JSON: {exc}") from exc
    if not isinstance(reference_value, Mapping):
        raise BlindReviewInputError("review row reference_facts must encode a JSON object")
    immutable["reference_facts"] = reference_value

    digest = hashlib.sha256(_canonical_json(immutable).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_blind_review_packet(
    report: Mapping[str, Any],
    *,
    seed: str | int | bytes,
    cases: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create reviewer rows and a separate deblinding key.

    ``seed`` controls both case order and the balanced A/B assignment.  It is
    never stored in the returned packet.  For an even number of cases, Before
    and After each occupy answer A exactly half the time; for an odd number the
    difference is at most one.

    When ``cases`` is supplied, each report case is joined by ``id`` (or
    ``case_id``) and only ``expected.mode``, ``score``, ``conditions``,
    ``reasons``, ``checks``, and ``limitations`` are exposed as reference
    facts.  A case document containing a top-level ``cases`` list is accepted
    as a convenience.
    """

    seed_key = _seed_key(seed)
    prepared = _prepare_report(report)
    source_fingerprint = _fingerprint_prepared(prepared)
    case_index = _prepare_case_index(cases, prepared)

    ordered = sorted(
        prepared,
        key=lambda item: (
            _keyed_rank(seed_key, "row-order", source_fingerprint, item["case_id"]),
            item["case_id"],
        ),
    )

    case_count = len(ordered)
    after_a_count = case_count // 2
    if case_count % 2:
        extra = _keyed_rank(seed_key, "odd-balance", source_fingerprint, "packet")[0] & 1
        after_a_count += extra

    assignment_order = sorted(
        prepared,
        key=lambda item: (
            _keyed_rank(seed_key, "a-assignment", source_fingerprint, item["case_id"]),
            item["case_id"],
        ),
    )
    after_in_a = {item["case_id"] for item in assignment_order[:after_a_count]}

    review_rows: list[dict[str, Any]] = []
    assignments: list[dict[str, str]] = []
    id_width = max(3, len(str(case_count)))
    answer_a_counts = {"before": 0, "after": 0}

    for position, item in enumerate(ordered, start=1):
        blind_id = f"BR-{position:0{id_width}d}"
        answer_a_variant = "after" if item["case_id"] in after_in_a else "before"
        answer_b_variant = "before" if answer_a_variant == "after" else "after"
        answer_a_counts[answer_a_variant] += 1

        source_case = case_index.get(item["case_id"])
        reference_facts = (
            _reference_facts_from_case(source_case)
            if source_case is not None
            else _reference_facts_from_evaluations(item["evaluations"], item["question_type"])
        )
        previsit_applicable = _is_previsit_question(item["question_type"])

        review_row = {
            "blind_id": blind_id,
            "question_type": item["question_type"],
            "previsit_applicable": "yes" if previsit_applicable else "no",
            "question": item["question"],
            "reference_facts": _canonical_json(reference_facts),
            "answer_a": item["answers"][answer_a_variant],
            "answer_b": item["answers"][answer_b_variant],
            "answer_a_correctness_1_5": "",
            "answer_b_correctness_1_5": "",
            "answer_a_understanding_1_5": "",
            "answer_b_understanding_1_5": "",
            "answer_a_decision_help_1_5": "",
            "answer_b_decision_help_1_5": "",
            "answer_a_previsit_clarity_yes_no": "" if previsit_applicable else "n/a",
            "answer_b_previsit_clarity_yes_no": "" if previsit_applicable else "n/a",
            "answer_a_hallucination_yes_no": "",
            "answer_b_hallucination_yes_no": "",
            "answer_a_safety_issue_yes_no": "",
            "answer_b_safety_issue_yes_no": "",
            "preference": "",
            "reviewer_id": "",
            "review_status": "",
            "notes": "",
        }
        immutable_fingerprint = compute_review_row_fingerprint(review_row)
        review_row["immutable_fingerprint"] = immutable_fingerprint
        review_rows.append(review_row)
        assignments.append(
            {
                "blind_id": blind_id,
                "case_id": item["case_id"],
                "answer_a_variant": answer_a_variant,
                "answer_b_variant": answer_b_variant,
                "immutable_fingerprint": immutable_fingerprint,
            }
        )

    deblind_key = {
        "schema_version": BLIND_REVIEW_SCHEMA_VERSION,
        "source_fingerprint": source_fingerprint,
        "case_count": case_count,
        "randomization": "keyed-sha256-balanced-v1",
        "answer_a_counts": answer_a_counts,
        "assignments": assignments,
    }
    return {
        "schema_version": BLIND_REVIEW_SCHEMA_VERSION,
        "source_fingerprint": source_fingerprint,
        "case_count": case_count,
        "review_rows": review_rows,
        "deblind_key": deblind_key,
    }


def render_blind_review_csv(packet_or_rows: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> str:
    """Render a packet's reviewer rows (or an iterable of rows) as UTF-8 CSV text."""

    if isinstance(packet_or_rows, Mapping):
        rows_value = packet_or_rows.get("review_rows")
        if not _is_list_like(rows_value):
            raise BlindReviewInputError("packet must contain a review_rows list")
        rows = list(rows_value)
    else:
        rows = list(packet_or_rows)

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=BLIND_REVIEW_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise BlindReviewInputError(f"review_rows[{index}] must be an object")
        writer.writerow({field: row.get(field, "") for field in BLIND_REVIEW_CSV_FIELDS})
    return output.getvalue()


def render_deblind_key_json(packet_or_key: Mapping[str, Any]) -> str:
    """Render a packet's deblinding key (or the key itself) as JSON text."""

    key = packet_or_key.get("deblind_key", packet_or_key)
    if not isinstance(key, Mapping) or not _is_list_like(key.get("assignments")):
        raise BlindReviewInputError("deblind key must contain an assignments list")
    return json.dumps(key, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _prepare_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(report, Mapping):
        raise BlindReviewInputError("report must be an object")
    evaluations = _require_object_list(report, "evaluations")
    records = _require_object_list(report, "records")
    if not evaluations:
        raise BlindReviewInputError("report.evaluations must not be empty")
    if not records:
        raise BlindReviewInputError("report.records must not be empty")

    evaluation_index = _index_variant_rows(evaluations, "evaluations")
    record_index = _index_variant_rows(records, "records")
    if set(evaluation_index) != set(record_index):
        missing_records = sorted(set(evaluation_index) - set(record_index))
        missing_evaluations = sorted(set(record_index) - set(evaluation_index))
        detail = []
        if missing_records:
            detail.append(f"missing records for {missing_records}")
        if missing_evaluations:
            detail.append(f"missing evaluations for {missing_evaluations}")
        raise BlindReviewInputError("evaluation/record pairs do not match: " + "; ".join(detail))

    case_ids = sorted({case_id for case_id, _variant in evaluation_index})
    prepared: list[dict[str, Any]] = []
    for case_id in case_ids:
        missing = [variant for variant in _VARIANTS if (case_id, variant) not in evaluation_index]
        if missing:
            raise BlindReviewInputError(f"case '{case_id}' is missing variants: {', '.join(missing)}")

        paired_evaluations = {variant: evaluation_index[(case_id, variant)] for variant in _VARIANTS}
        question_values = [
            _normalize_text(paired_evaluations[variant].get("question")) for variant in _VARIANTS
        ]
        if not all(question_values) or len(set(question_values)) != 1:
            raise BlindReviewInputError(f"case '{case_id}' must have one non-empty shared question")
        question = question_values[0]

        question_types = {
            _normalize_text(evaluation.get("question_type"))
            for evaluation in paired_evaluations.values()
            if _normalize_text(evaluation.get("question_type"))
        }
        if len(question_types) > 1:
            raise BlindReviewInputError(f"case '{case_id}' has inconsistent question_type values")
        question_type = next(iter(question_types), "")

        answers: dict[str, str] = {}
        for variant in _VARIANTS:
            evaluation = paired_evaluations[variant]
            record = record_index[(case_id, variant)]
            _require_success(case_id, variant, evaluation, record)
            evaluation_answer = _normalize_text(evaluation.get("response_text"))
            response = record.get("response")
            record_answer = _normalize_text(response.get("answer")) if isinstance(response, Mapping) else ""
            if not record_answer:
                record_answer = _normalize_text(record.get("answer"))
            if evaluation_answer and record_answer and evaluation_answer != record_answer:
                raise BlindReviewInputError(
                    f"case '{case_id}' variant '{variant}' has mismatched evaluation and record responses"
                )
            answer = record_answer or evaluation_answer
            if not answer:
                raise BlindReviewInputError(f"case '{case_id}' variant '{variant}' has no response text")
            answers[variant] = answer

        prepared.append(
            {
                "case_id": case_id,
                "question_type": question_type,
                "question": question,
                "answers": answers,
                "evaluations": paired_evaluations,
            }
        )
    return prepared


def _require_object_list(report: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = report.get(key)
    if not _is_list_like(value):
        raise BlindReviewInputError(f"report.{key} must be a list")
    rows = list(value)
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise BlindReviewInputError(f"report.{key}[{index}] must be an object")
    return rows


def _index_variant_rows(
    rows: Iterable[Mapping[str, Any]], label: str
) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        case_id = _normalize_text(row.get("case_id"))
        variant = _normalize_text(row.get("variant")).lower()
        if not case_id:
            raise BlindReviewInputError(f"report.{label}[{index}] is missing case_id")
        if variant not in _VARIANTS:
            raise BlindReviewInputError(
                f"report.{label}[{index}] has unsupported variant: {variant or '<empty>'}"
            )
        key = (case_id, variant)
        if key in result:
            raise BlindReviewInputError(f"duplicate {label} pair: {case_id}/{variant}")
        result[key] = row
    return result


def _require_success(
    case_id: str,
    variant: str,
    evaluation: Mapping[str, Any],
    record: Mapping[str, Any],
) -> None:
    record_status = _normalize_text(record.get("status")).lower()
    evaluation_status = _normalize_text(evaluation.get("record_status")).lower()
    if record_status and record_status != "success":
        raise BlindReviewInputError(f"case '{case_id}' variant '{variant}' record is not successful")
    if evaluation_status and evaluation_status != "success":
        raise BlindReviewInputError(f"case '{case_id}' variant '{variant}' evaluation is not successful")
    if evaluation.get("has_response") is False:
        raise BlindReviewInputError(f"case '{case_id}' variant '{variant}' has_response is false")


def _fingerprint_prepared(prepared: Sequence[Mapping[str, Any]]) -> str:
    exposed: list[dict[str, str]] = []
    for item in prepared:
        for variant in _VARIANTS:
            exposed.append(
                {
                    "case_id": _normalize_text(item["case_id"]),
                    "variant": variant,
                    "question": _normalize_text(item["question"]),
                    "response_text": _normalize_text(item["answers"][variant]),
                }
            )
    exposed.sort(key=lambda item: (item["case_id"], _VARIANTS.index(item["variant"])))
    digest = hashlib.sha256(_canonical_json(exposed).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _prepare_case_index(
    cases: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
    prepared: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if cases is None:
        return {}
    if isinstance(cases, Mapping):
        value = cases.get("cases")
        if not _is_list_like(value):
            raise BlindReviewInputError("case document must contain a cases list")
        case_rows = list(value)
    elif _is_list_like(cases):
        case_rows = list(cases)
    else:
        raise BlindReviewInputError("cases must be a list or a case document object")

    result: dict[str, Mapping[str, Any]] = {}
    for index, source_case in enumerate(case_rows):
        if not isinstance(source_case, Mapping):
            raise BlindReviewInputError(f"cases[{index}] must be an object")
        case_id = _normalize_text(source_case.get("id") or source_case.get("case_id"))
        if not case_id:
            raise BlindReviewInputError(f"cases[{index}] is missing id")
        if case_id in result:
            raise BlindReviewInputError(f"duplicate source case id: {case_id}")
        result[case_id] = source_case

    for item in prepared:
        case_id = item["case_id"]
        source_case = result.get(case_id)
        if source_case is None:
            raise BlindReviewInputError(f"source cases are missing report case: {case_id}")
        source_question = _normalize_text(source_case.get("question"))
        if source_question and source_question != item["question"]:
            raise BlindReviewInputError(f"source case '{case_id}' question does not match report")
        source_type = _normalize_text(source_case.get("question_type"))
        if source_type and item["question_type"] and source_type != item["question_type"]:
            raise BlindReviewInputError(f"source case '{case_id}' question_type does not match report")
    return result


def _reference_facts_from_case(source_case: Mapping[str, Any]) -> dict[str, Any]:
    expected = source_case.get("expected")
    expected = expected if isinstance(expected, Mapping) else {}

    mode = expected.get("mode", source_case.get("expected_mode"))
    score = expected.get("score")
    if score is None and source_case.get("expected_score") is not None:
        score = {"total": source_case.get("expected_score")}
        trace = source_case.get("calculation_trace")
        if isinstance(trace, Mapping):
            score["calculation_trace"] = deepcopy(trace)

    conditions = expected.get("conditions")
    if conditions is None:
        conditions = _condition_labels(source_case.get("expected_user_conditions"))
    reasons = expected.get("reasons")
    if reasons is None:
        reasons = {"expected": deepcopy(source_case.get("expected_evidence") or [])}
    checks = expected.get("checks")
    if checks is None:
        checks = deepcopy(source_case.get("expected_evidence") or []) if _is_previsit_question(
            _normalize_text(source_case.get("question_type"))
        ) else []

    selected = {
        "mode": deepcopy(mode),
        "score": deepcopy(score),
        "conditions": deepcopy(conditions if conditions is not None else []),
        "reasons": deepcopy(reasons if reasons is not None else []),
        "checks": deepcopy(checks if checks is not None else []),
        "limitations": deepcopy(expected.get("limitations") or []),
    }
    _canonical_json(selected)  # Validate that the whitelisted values are JSON-safe.
    return selected


def _reference_facts_from_evaluations(
    evaluations: Mapping[str, Mapping[str, Any]], question_type: str
) -> dict[str, Any]:
    check_sets = []
    for variant in _VARIANTS:
        checks = evaluations[variant].get("checks")
        check_sets.append(checks if isinstance(checks, Mapping) else {})

    expected_numbers: dict[str, dict[str, Any]] = {}
    evidence: set[str] = set()
    conditions: set[str] = set()
    expected_modes: set[str] = set()
    score_applicable = False
    for checks in check_sets:
        score_trace = checks.get("score_trace")
        if isinstance(score_trace, Mapping):
            score_applicable = score_applicable or score_trace.get("applicable") is True
            values = score_trace.get("expected_numbers")
            if _is_list_like(values):
                for value in values:
                    if isinstance(value, Mapping):
                        stable = {
                            key: deepcopy(value.get(key))
                            for key in ("path", "label", "value")
                            if value.get(key) is not None
                        }
                        expected_numbers[_canonical_json(stable)] = stable

        expected_evidence = checks.get("expected_evidence")
        if isinstance(expected_evidence, Mapping) and expected_evidence.get("applicable") is True:
            evidence.update(_text_items(expected_evidence.get("matched")))
            evidence.update(_text_items(expected_evidence.get("missing")))

        user_conditions = checks.get("user_conditions")
        if isinstance(user_conditions, Mapping) and user_conditions.get("applicable") is True:
            conditions.update(_text_items(user_conditions.get("matched")))
            conditions.update(_text_items(user_conditions.get("missing")))

        mode = checks.get("mode")
        if isinstance(mode, Mapping) and mode.get("applicable") is True:
            expected_mode = _normalize_text(mode.get("expected"))
            if expected_mode:
                expected_modes.add(expected_mode)

    if len(expected_modes) > 1:
        raise BlindReviewInputError("paired evaluations contain conflicting expected modes")
    evidence_list = sorted(evidence)
    return {
        "mode": next(iter(expected_modes), None),
        "score": {
            "expected_numbers": sorted(
                expected_numbers.values(), key=lambda value: _canonical_json(value)
            )
        }
        if score_applicable
        else None,
        "conditions": sorted(conditions),
        "reasons": evidence_list,
        "checks": evidence_list if _is_previsit_question(question_type) else [],
        "limitations": ["원본 case 없이 자동 평가 checks에서 재구성한 제한적 기준정보입니다."],
    }


def _condition_labels(value: Any) -> list[str]:
    if not _is_list_like(value):
        return []
    labels: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            label = _normalize_text(item.get("label"))
        else:
            label = _normalize_text(item)
        if label:
            labels.append(label)
    return labels


def _text_items(value: Any) -> set[str]:
    if not _is_list_like(value):
        return set()
    return {text for item in value if (text := _normalize_text(item))}


def _seed_key(seed: str | int | bytes) -> bytes:
    if isinstance(seed, bool) or not isinstance(seed, (str, int, bytes)):
        raise BlindReviewInputError("seed must be a non-empty string, integer, or bytes")
    if isinstance(seed, bytes):
        material = seed
    else:
        material = str(seed).encode("utf-8")
    if not material:
        raise BlindReviewInputError("seed must not be empty")
    return hashlib.sha256(b"blind-review-seed-v1\0" + material).digest()


def _keyed_rank(seed_key: bytes, domain: str, fingerprint: str, value: str) -> bytes:
    message = "\0".join((domain, fingerprint, value)).encode("utf-8")
    return hmac.new(seed_key, message, hashlib.sha256).digest()


def _is_previsit_question(question_type: str) -> bool:
    normalized = "".join(character for character in question_type.lower() if character.isalnum())
    return normalized == "previsitcheck"


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BlindReviewInputError(f"value is not JSON serializable: {exc}") from exc


def _is_list_like(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
