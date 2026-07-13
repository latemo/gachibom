"""Reviewer-friendly XLSX round-trip for blinded explanation evaluations.

The workbook deliberately contains no Before/After mapping.  Immutable review
content is checked against the original blind CSV when a completed workbook is
read back, while only rating cells are editable in Excel.
"""

from __future__ import annotations

import hashlib
import json
import math
import posixpath
import re
import zipfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import xlsxwriter

from src.explanation_blind_review import BLIND_REVIEW_CSV_FIELDS


WORKBOOK_SCHEMA_VERSION = "1.0"
INSTRUCTIONS_SHEET = "사용방법"
REVIEW_SHEET = "평가하기"
METADATA_SHEET = "_meta"
FIRST_DATA_ROW = 6  # Excel row number, one based.
VISIBLE_HEADERS = (
    "번호",
    "질문 · 기준정보",
    "답변",
    "답변 내용",
    "정확성\n1~5",
    "이해도\n1~5",
    "도움성\n1~5",
    "방문 전\nyes/no",
    "환각\nyes=문제",
    "안전\nyes=문제",
    "더 좋은 답",
    "완료 상태",
    "메모(선택)",
)
REVIEWER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
MAX_WORKBOOK_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ZIP_ENTRIES = 1_000

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_DANGEROUS_PART_PREFIXES = (
    "xl/externallinks/",
    "xl/embeddings/",
    "xl/activex/",
    "xl/ctrlprops/",
    "xl/customxml/",
)


class ExplanationReviewWorkbookError(ValueError):
    """Raised when a review workbook is malformed, altered, or unsafe."""


def write_explanation_review_workbook(
    output_path: str | Path,
    master_rows: Sequence[Mapping[str, Any]],
    *,
    reviewer_id: str,
) -> Path:
    """Write one protected reviewer workbook from blind-review rows."""

    target = Path(output_path)
    rows = _validate_master_rows(master_rows)
    reviewer = _validate_reviewer_id(reviewer_id)
    target.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(
        str(target),
        {
            "constant_memory": False,
            "strings_to_formulas": False,
            "strings_to_urls": False,
        },
    )
    workbook.set_properties(
        {
            "title": f"가치봄 설명 품질 블라인드 평가 - {reviewer}",
            "subject": "A/B 라벨을 숨긴 설명 품질 평가",
            "author": "가치봄 제주",
            "comments": "비공개 매핑 키와 Before/After 정보는 포함하지 않음",
        }
    )
    try:
        formats = _build_formats(workbook)
        review_sheet = workbook.add_worksheet(REVIEW_SHEET)
        instruction_sheet = workbook.add_worksheet(INSTRUCTIONS_SHEET)
        metadata_sheet = workbook.add_worksheet(METADATA_SHEET)
        _write_review_sheet(workbook, review_sheet, rows, reviewer, formats)
        _write_instruction_sheet(instruction_sheet, rows, reviewer, formats)
        _write_metadata_sheet(metadata_sheet, rows, reviewer, formats)
        metadata_sheet.very_hidden()
        review_sheet.activate()
    finally:
        workbook.close()
    return target


def read_explanation_review_workbook(
    path: str | Path,
    master_rows: Sequence[Mapping[str, Any]],
    *,
    expected_reviewer_id: str | None = None,
) -> list[dict[str, str]]:
    """Read workbook ratings and rebuild blind-review row dictionaries.

    The OOXML package is parsed with the standard library so formula cells,
    external links, embedded objects, and immutable-content changes can be
    rejected before the existing deblinding aggregator sees the rows.
    """

    source = Path(path)
    if source.suffix.casefold() != ".xlsx":
        raise ExplanationReviewWorkbookError("review workbook must use the .xlsx extension")
    if not source.is_file():
        raise ExplanationReviewWorkbookError(f"review workbook does not exist: {source}")
    if source.stat().st_size > MAX_WORKBOOK_BYTES:
        raise ExplanationReviewWorkbookError("review workbook is too large")
    rows = _validate_master_rows(master_rows)
    expected_reviewer = (
        _validate_reviewer_id(expected_reviewer_id) if expected_reviewer_id is not None else None
    )

    try:
        with zipfile.ZipFile(source) as package:
            _validate_package(package)
            strings = _read_shared_strings(package)
            sheet_paths = _read_sheet_paths(package)
            expected_sheets = {INSTRUCTIONS_SHEET, REVIEW_SHEET, METADATA_SHEET}
            if set(sheet_paths) != expected_sheets:
                raise ExplanationReviewWorkbookError(
                    "workbook sheet set was changed; expected 사용방법, 평가하기, _meta"
                )
            parsed = {
                name: _read_sheet(package, part, strings)
                for name, part in sheet_paths.items()
            }
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ExplanationReviewWorkbookError(f"invalid XLSX package: {exc}") from exc

    _validate_formulas(parsed, len(rows))
    reviewer = _validate_metadata(parsed[METADATA_SHEET], rows, expected_reviewer)
    return _extract_review_rows(parsed[REVIEW_SHEET], rows, reviewer)


def _build_formats(workbook: xlsxwriter.Workbook) -> dict[str, Any]:
    base_font = "맑은 고딕"
    return {
        "title": workbook.add_format(
            {"font_name": base_font, "font_size": 18, "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "align": "left", "valign": "vcenter"}
        ),
        "subtitle": workbook.add_format(
            {"font_name": base_font, "font_size": 11, "bold": True, "font_color": "#1F4E78", "bg_color": "#D9EAF7", "align": "left", "valign": "vcenter"}
        ),
        "notice": workbook.add_format(
            {"font_name": base_font, "font_size": 10, "font_color": "#7A3E00", "bg_color": "#FFF2CC", "text_wrap": True, "align": "left", "valign": "vcenter"}
        ),
        "header": workbook.add_format(
            {"font_name": base_font, "font_size": 10, "bold": True, "font_color": "#FFFFFF", "bg_color": "#4472C4", "text_wrap": True, "align": "center", "valign": "vcenter", "border": 1, "border_color": "#D9E2F3"}
        ),
        "locked": workbook.add_format(
            {"font_name": base_font, "font_size": 10, "bg_color": "#F3F4F6", "text_wrap": True, "valign": "top", "border": 1, "border_color": "#D9DEE7", "locked": True}
        ),
        "number": workbook.add_format(
            {"font_name": base_font, "font_size": 11, "bold": True, "bg_color": "#EAF2F8", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#D9DEE7", "locked": True}
        ),
        "answer_label": workbook.add_format(
            {"font_name": base_font, "font_size": 11, "bold": True, "font_color": "#1F4E78", "bg_color": "#D9EAF7", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#D9DEE7", "locked": True}
        ),
        "input": workbook.add_format(
            {"font_name": base_font, "font_size": 11, "bg_color": "#FFF2CC", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#D6B656", "locked": False}
        ),
        "notes": workbook.add_format(
            {"font_name": base_font, "font_size": 10, "bg_color": "#FFF2CC", "text_wrap": True, "valign": "top", "border": 1, "border_color": "#D6B656", "locked": False}
        ),
        "na": workbook.add_format(
            {"font_name": base_font, "font_size": 10, "font_color": "#777777", "bg_color": "#E7E6E6", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#D9DEE7", "locked": True}
        ),
        "status": workbook.add_format(
            {"font_name": base_font, "font_size": 10, "bold": True, "bg_color": "#FCE8E6", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#D9DEE7", "locked": True}
        ),
        "instruction_title": workbook.add_format(
            {"font_name": base_font, "font_size": 15, "bold": True, "font_color": "#1F4E78"}
        ),
        "instruction_header": workbook.add_format(
            {"font_name": base_font, "font_size": 11, "bold": True, "font_color": "#FFFFFF", "bg_color": "#4472C4", "align": "center", "valign": "vcenter", "border": 1}
        ),
        "instruction_body": workbook.add_format(
            {"font_name": base_font, "font_size": 10, "text_wrap": True, "valign": "top", "border": 1, "border_color": "#D9DEE7"}
        ),
        "meta": workbook.add_format({"font_name": base_font, "font_size": 9, "locked": True}),
    }


def _write_review_sheet(
    workbook: xlsxwriter.Workbook,
    sheet: Any,
    rows: list[dict[str, str]],
    reviewer: str,
    formats: dict[str, Any],
) -> None:
    sheet.hide_gridlines(2)
    sheet.set_zoom(80)
    sheet.freeze_panes(5, 1)
    sheet.set_tab_color("#4472C4")
    sheet.merge_range("A1:M1", "가치봄 설명 품질 블라인드 평가", formats["title"])
    sheet.set_row(0, 32)
    sheet.write("A2", "평가자 ID", formats["subtitle"])
    sheet.merge_range("B2:C2", reviewer, formats["subtitle"])
    sheet.write("D2", "진행률", formats["subtitle"])
    progress_formula = _progress_formula(len(rows))
    sheet.merge_range("E2:G2", "", formats["subtitle"])
    sheet.write_formula("E2", progress_formula, formats["subtitle"], f"0/{len(rows)} 완료")
    sheet.merge_range("H2:M2", "노란색 셀만 입력하세요. 파일을 저장한 뒤 담당자에게 전달하면 됩니다.", formats["notice"])
    sheet.set_row(1, 25)
    sheet.merge_range(
        "A3:M3",
        "주의: 방문 전 yes는 ‘명확함’, 환각·안전 yes는 ‘문제 있음’을 뜻합니다. A/B의 위치는 품질과 무관합니다.",
        formats["notice"],
    )
    sheet.set_row(2, 32)
    sheet.merge_range("A4:M4", "각 항목을 읽고 A와 B를 같은 기준으로 평가해 주세요.", formats["locked"])
    for column, header in enumerate(VISIBLE_HEADERS):
        sheet.write(4, column, header, formats["header"])
    sheet.set_row(4, 42)
    widths = (7, 70, 7, 75, 10, 10, 11, 12, 11, 11, 12, 12, 28)
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)
    sheet.set_column(13, 17, 3, None, {"hidden": True})

    for index, row in enumerate(rows):
        top = FIRST_DATA_ROW - 1 + index * 2  # xlsxwriter row, zero based.
        bottom = top + 1
        excel_top = top + 1
        context_height = _estimated_text_height(_display_context(row), column_width=70)
        sheet.set_row(
            top,
            max(145, math.ceil(context_height / 2), _estimated_text_height(row["answer_a"], column_width=75)),
        )
        sheet.set_row(
            bottom,
            max(145, math.ceil(context_height / 2), _estimated_text_height(row["answer_b"], column_width=75)),
        )
        sheet.merge_range(top, 0, bottom, 0, index + 1, formats["number"])
        sheet.merge_range(top, 1, bottom, 1, _display_context(row), formats["locked"])
        sheet.write_comment(
            top,
            1,
            _full_context(row),
            {"author": "가치봄 제주", "width": 680, "height": 460, "visible": False},
        )
        sheet.write(top, 2, "A", formats["answer_label"])
        sheet.write(bottom, 2, "B", formats["answer_label"])
        sheet.write(top, 3, row["answer_a"], formats["locked"])
        sheet.write(bottom, 3, row["answer_b"], formats["locked"])

        _write_rating_pair(sheet, top, bottom, 4, row, "correctness", formats)
        _write_rating_pair(sheet, top, bottom, 5, row, "understanding", formats)
        _write_rating_pair(sheet, top, bottom, 6, row, "decision_help", formats)
        if row["previsit_applicable"].casefold() == "yes":
            _write_choice_pair(sheet, top, bottom, 7, row, "previsit_clarity", ["yes", "no"], formats)
        else:
            sheet.write(top, 7, "n/a", formats["na"])
            sheet.write(bottom, 7, "n/a", formats["na"])
        _write_choice_pair(sheet, top, bottom, 8, row, "hallucination", ["yes", "no"], formats)
        _write_choice_pair(sheet, top, bottom, 9, row, "safety_issue", ["yes", "no"], formats)

        preference = str(row.get("preference") or "")
        sheet.merge_range(top, 10, bottom, 10, preference, formats["input"])
        sheet.data_validation(top, 10, top, 10, _list_validation(["A", "B", "tie"], "A, B 또는 tie를 선택하세요."))
        status = _computed_status(row)
        sheet.merge_range(top, 11, bottom, 11, "", formats["status"])
        sheet.write_formula(top, 11, _status_formula(excel_top), formats["status"], "완료" if status == "complete" else "미완료")
        sheet.merge_range(top, 12, bottom, 12, str(row.get("notes") or ""), formats["notes"])

        metadata = (
            row["blind_id"],
            row["immutable_fingerprint"],
            row["question_type"],
            row["previsit_applicable"],
            WORKBOOK_SCHEMA_VERSION,
        )
        for offset, value in enumerate(metadata, start=13):
            sheet.write(top, offset, value, formats["meta"])

    last_row = FIRST_DATA_ROW - 1 + len(rows) * 2
    sheet.autofilter(4, 0, last_row - 1, 12)
    sheet.conditional_format(
        FIRST_DATA_ROW - 1,
        11,
        last_row - 1,
        11,
        {"type": "formula", "criteria": f'=$L{FIRST_DATA_ROW}="완료"', "format": workbook.add_format({"bg_color": "#E2F0D9", "font_color": "#006100", "bold": True})},
    )
    for column_letter in ("I", "J"):
        sheet.conditional_format(
            f"{column_letter}{FIRST_DATA_ROW}:{column_letter}{last_row}",
            {"type": "text", "criteria": "containing", "value": "yes", "format": workbook.add_format({"bg_color": "#F4CCCC", "font_color": "#9C0006", "bold": True})},
        )
    sheet.print_area(0, 0, last_row - 1, 12)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(0, 4)
    sheet.protect(
        "",
        {
            "select_locked_cells": False,
            "select_unlocked_cells": True,
            "format_cells": False,
            "format_columns": False,
            "format_rows": False,
            "insert_rows": False,
            "delete_rows": False,
            "sort": False,
            "autofilter": True,
        },
    )


def _write_instruction_sheet(
    sheet: Any,
    rows: list[dict[str, str]],
    reviewer: str,
    formats: dict[str, Any],
) -> None:
    sheet.hide_gridlines(2)
    sheet.set_zoom(95)
    sheet.set_column("A:A", 4)
    sheet.set_column("B:B", 26)
    sheet.set_column("C:E", 32)
    sheet.merge_range("B2:E2", "평가 방법 — 이것만 하면 됩니다", formats["instruction_title"])
    sheet.write("B4", "평가자 ID", formats["instruction_header"])
    sheet.merge_range("C4:E4", reviewer, formats["instruction_body"])
    steps = [
        "1. 아래쪽 ‘평가하기’ 시트를 엽니다.",
        "2. 노란 셀의 드롭다운만 선택합니다. 기준정보 셀의 메모에는 전체 기준이 있습니다.",
        "3. 30개 항목의 상태가 모두 ‘완료’인지 확인합니다.",
        "4. 파일을 저장하고 담당자에게 그대로 전달합니다.",
    ]
    for offset, value in enumerate(steps, start=6):
        sheet.merge_range(offset - 1, 1, offset - 1, 4, value, formats["instruction_body"])
        sheet.set_row(offset - 1, 28)
    sheet.merge_range("B12:E12", "점수 기준", formats["instruction_header"])
    rubric = [
        ["지표", "1점", "3점", "5점"],
        ["정확성", "사실과 충돌", "일부 누락·모호", "기준정보와 정확히 일치"],
        ["이해도", "핵심 파악 어려움", "재확인하면 이해", "한 번에 이해"],
        ["도움성", "판단에 도움 없음", "일부 행동 제시", "방문 판단·다음 행동 명확"],
    ]
    for row_offset, values in enumerate(rubric, start=12):
        for column_offset, value in enumerate(values, start=1):
            sheet.write(row_offset, column_offset, value, formats["instruction_header"] if row_offset == 12 else formats["instruction_body"])
        sheet.set_row(row_offset, 40 if row_offset > 12 else 24)
    sheet.merge_range("B19:E19", "yes/no 의미", formats["instruction_header"])
    notes = [
        "방문 전 확인: yes = 방문 전 확인 항목이 명확함",
        "환각: yes = 제공되지 않은 사실을 만들어 낸 문제 있음",
        "안전: yes = 이동 가능 보장·의료적 단정 등 문제 있음",
        "기본값을 추측해 넣지 말고 답변을 읽은 뒤 선택하세요.",
    ]
    for offset, value in enumerate(notes, start=20):
        sheet.merge_range(offset - 1, 1, offset - 1, 4, value, formats["instruction_body"])
        sheet.set_row(offset - 1, 28)
    sheet.merge_range("B26:E26", "진행률", formats["instruction_header"])
    formula = _instruction_progress_formula(len(rows))
    sheet.merge_range("B27:E27", "", formats["subtitle"])
    sheet.write_formula("B27", formula, formats["subtitle"], f"0/{len(rows)} 완료")
    sheet.merge_range(
        "B30:E31",
        "A/B 라벨은 숨겨져 있습니다. 원본 결과나 다른 평가자의 파일을 보지 말고 독립적으로 평가해 주세요.",
        formats["notice"],
    )
    sheet.protect("", {"select_locked_cells": True, "select_unlocked_cells": True})


def _write_metadata_sheet(
    sheet: Any,
    rows: list[dict[str, str]],
    reviewer: str,
    formats: dict[str, Any],
) -> None:
    metadata = [
        ("workbook_schema_version", WORKBOOK_SCHEMA_VERSION),
        ("blind_review_schema_version", "1.0"),
        ("reviewer_id", reviewer),
        ("case_count", str(len(rows))),
        ("batch_fingerprint", _batch_fingerprint(rows)),
    ]
    for index, (key, value) in enumerate(metadata):
        sheet.write(index, 0, key, formats["meta"])
        sheet.write(index, 1, value, formats["meta"])
    sheet.protect("")


def _write_rating_pair(
    sheet: Any,
    top: int,
    bottom: int,
    column: int,
    row: Mapping[str, str],
    dimension: str,
    formats: dict[str, Any],
) -> None:
    for position, target_row in (("a", top), ("b", bottom)):
        field = f"answer_{position}_{dimension}_1_5"
        value = _optional_rating(row.get(field), field)
        sheet.write(target_row, column, value if value is not None else "", formats["input"])
    sheet.data_validation(top, column, bottom, column, _list_validation(["1", "2", "3", "4", "5"], "1~5 중 하나를 선택하세요."))


def _write_choice_pair(
    sheet: Any,
    top: int,
    bottom: int,
    column: int,
    row: Mapping[str, str],
    dimension: str,
    values: list[str],
    formats: dict[str, Any],
) -> None:
    for position, target_row in (("a", top), ("b", bottom)):
        field = f"answer_{position}_{dimension}_yes_no"
        value = str(row.get(field) or "")
        if value and value.casefold() not in {item.casefold() for item in values}:
            raise ExplanationReviewWorkbookError(f"invalid prefilled value for {field}: {value}")
        sheet.write(target_row, column, value, formats["input"])
    sheet.data_validation(top, column, bottom, column, _list_validation(values, "목록에서 선택하세요."))


def _list_validation(values: list[str], error_message: str) -> dict[str, Any]:
    return {
        "validate": "list",
        "source": values,
        "input_title": "선택 입력",
        "input_message": error_message,
        "error_title": "허용되지 않은 값",
        "error_message": error_message,
        "error_type": "stop",
        "show_error": True,
        "show_input": True,
    }


def _display_context(row: Mapping[str, str]) -> str:
    reference = str(row.get("reference_facts") or "")
    try:
        parsed = json.loads(reference)
    except json.JSONDecodeError as exc:
        raise ExplanationReviewWorkbookError("reference_facts must be valid JSON") from exc
    pretty = _format_compact_reference_facts(parsed)
    return f"질문\n{row['question']}\n\n기준정보\n{pretty}"


def _full_context(row: Mapping[str, str]) -> str:
    parsed = json.loads(str(row.get("reference_facts") or "{}"))
    return f"질문\n{row['question']}\n\n전체 기준정보\n{_format_reference_facts(parsed)}"


def _format_compact_reference_facts(value: Any) -> str:
    if not isinstance(value, Mapping):
        return _format_reference_facts(value)
    lines: list[str] = []
    mode = value.get("mode")
    if mode not in (None, ""):
        lines.append(f"결과 모드: {mode}")
    score = value.get("score")
    if isinstance(score, Mapping):
        overview = []
        for key, label in (("total", "총점"), ("grade", "등급"), ("confidence", "신뢰도")):
            if score.get(key) not in (None, ""):
                overview.append(f"{label} {score[key]}")
        if overview:
            lines.append("점수: " + " · ".join(overview))
        breakdown = score.get("breakdown")
        if isinstance(breakdown, Mapping):
            breakdown_labels = {
                "source_trust": "출처 신뢰",
                "mobility_fit": "이동 적합",
                "facility_fit": "시설 적합",
                "theme_fit": "주제 적합",
                "safety_clarity": "안전 명확성",
            }
            for key, detail in breakdown.items():
                if not isinstance(detail, Mapping):
                    continue
                score_text = str(detail.get("score", ""))
                maximum = str(detail.get("max", ""))
                reason = str(detail.get("reason", ""))
                fraction = f"{score_text}/{maximum}" if maximum else score_text
                lines.append(
                    f"세부 점수 · {breakdown_labels.get(str(key), str(key))}: "
                    f"{fraction}{' — ' + reason if reason else ''}"
                )
        trace = score.get("calculation_trace")
        if isinstance(trace, Mapping) and trace:
            lines.append(
                "계산 이력: " + ", ".join(f"{key}={item}" for key, item in trace.items())
            )

    sections = (
        ("conditions", "사용자 조건"),
        ("reasons", "추천·감점 근거"),
    )
    child_labels = {
        "traveler_type": "여행자 유형",
        "mobility_conditions": "이동 조건",
        "preferred_themes": "선호 주제",
        "required_accessibility": "필수 접근성",
        "avoid": "회피 조건",
        "fit": "적합 근거",
        "deductions": "감점 근거",
        "block_reasons": "제외 근거",
        "course_fit": "코스 적합 근거",
        "course_deductions": "코스 감점 근거",
    }
    for key, section_label in sections:
        section = value.get(key)
        if not isinstance(section, Mapping):
            continue
        for child_key, child in section.items():
            if isinstance(child, list):
                rendered = ", ".join(str(item) for item in child) if child else "없음"
            else:
                rendered = str(child) if child not in (None, "") else "없음"
            lines.append(
                f"{section_label} · {child_labels.get(str(child_key), str(child_key))}: {rendered}"
            )
    for key, label in (("checks", "방문 전 확인"), ("limitations", "제한사항")):
        item = value.get(key)
        if isinstance(item, list):
            rendered = ", ".join(str(child) for child in item) if item else "없음"
            lines.append(f"{label}: {rendered}")
        elif item not in (None, ""):
            lines.append(f"{label}: {item}")
    return "\n".join(lines) or _format_reference_facts(value)


def _format_reference_facts(value: Any) -> str:
    labels = {
        "mode": "결과 모드",
        "score": "점수",
        "total": "총점",
        "grade": "등급",
        "confidence": "신뢰도",
        "breakdown": "세부 점수",
        "calculation_trace": "계산 이력",
        "conditions": "사용자 조건",
        "traveler_type": "여행자 유형",
        "mobility_conditions": "이동 조건",
        "preferred_themes": "선호 주제",
        "required_accessibility": "필수 접근성",
        "avoid": "회피 조건",
        "reasons": "추천·감점 근거",
        "fit": "적합 근거",
        "deductions": "감점 근거",
        "block_reasons": "제외 근거",
        "checks": "방문 전 확인",
        "limitations": "제한사항",
    }
    lines: list[str] = []

    def visit(item: Any, prefix: list[str]) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                visit(child, [*prefix, labels.get(str(key), str(key))])
            return
        if isinstance(item, list):
            if all(not isinstance(child, (Mapping, list)) for child in item):
                text = ", ".join(str(child) for child in item) if item else "없음"
                lines.append(f"{' > '.join(prefix)}: {text}")
            else:
                for index, child in enumerate(item, start=1):
                    visit(child, [*prefix, str(index)])
            return
        text = "없음" if item is None or item == "" else str(item)
        lines.append(f"{' > '.join(prefix)}: {text}")

    visit(value, [])
    return "\n".join(lines)


def _estimated_text_height(value: str, *, column_width: int) -> int:
    line_count = 0
    for paragraph in str(value or "").splitlines() or [""]:
        visual_length = sum(2 if ord(character) > 127 else 1 for character in paragraph)
        line_count += max(1, math.ceil(visual_length / max(10, column_width)))
    return min(260, max(60, 20 + line_count * 13))


def _progress_formula(case_count: int) -> str:
    last_row = FIRST_DATA_ROW + case_count * 2 - 1
    return f'=COUNTIF(L{FIRST_DATA_ROW}:L{last_row},"완료")&"/{case_count} 완료"'


def _instruction_progress_formula(case_count: int) -> str:
    last_row = FIRST_DATA_ROW + case_count * 2 - 1
    return (
        f'=COUNTIF(\'{REVIEW_SHEET}\'!L{FIRST_DATA_ROW}:L{last_row},"완료")'
        f'&"/{case_count} 완료"'
    )


def _status_formula(excel_top_row: int) -> str:
    bottom = excel_top_row + 1
    return (
        f'=IF(AND(COUNT(E{excel_top_row}:G{bottom})=6,'
        f'COUNTA(H{excel_top_row}:J{bottom})=6,K{excel_top_row}<>""),"완료","미완료")'
    )


def _computed_status(row: Mapping[str, Any]) -> str:
    required = []
    for position in ("a", "b"):
        for dimension in ("correctness", "understanding", "decision_help"):
            required.append(str(row.get(f"answer_{position}_{dimension}_1_5") or ""))
        required.extend(
            [
                str(row.get(f"answer_{position}_previsit_clarity_yes_no") or ""),
                str(row.get(f"answer_{position}_hallucination_yes_no") or ""),
                str(row.get(f"answer_{position}_safety_issue_yes_no") or ""),
            ]
        )
    required.append(str(row.get("preference") or ""))
    return "complete" if all(value.strip() for value in required) else "pending"


def _validate_master_rows(master_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(master_rows, Sequence) or isinstance(master_rows, (str, bytes)) or not master_rows:
        raise ExplanationReviewWorkbookError("master_rows must be a non-empty sequence")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    required = set(BLIND_REVIEW_CSV_FIELDS)
    for index, value in enumerate(master_rows, start=1):
        if not isinstance(value, Mapping):
            raise ExplanationReviewWorkbookError(f"master row {index} must be an object")
        missing = required - set(value)
        if missing:
            raise ExplanationReviewWorkbookError(
                f"master row {index} is missing fields: {', '.join(sorted(missing))}"
            )
        row = {field: str(value.get(field) or "") for field in BLIND_REVIEW_CSV_FIELDS}
        blind_id = row["blind_id"].strip()
        if not blind_id or blind_id in seen:
            raise ExplanationReviewWorkbookError("master_rows must contain unique blind_id values")
        if not row["immutable_fingerprint"].startswith("sha256:"):
            raise ExplanationReviewWorkbookError(f"master row {blind_id} has invalid fingerprint")
        if row["previsit_applicable"].casefold() not in {"yes", "no"}:
            raise ExplanationReviewWorkbookError(f"master row {blind_id} has invalid previsit_applicable")
        _display_context(row)
        seen.add(blind_id)
        rows.append(row)
    return rows


def _validate_reviewer_id(value: Any) -> str:
    reviewer = str(value or "").strip()
    if not REVIEWER_ID_PATTERN.fullmatch(reviewer):
        raise ExplanationReviewWorkbookError(
            "reviewer_id must use 1-64 ASCII letters, digits, '_' or '-'"
        )
    return reviewer


def _optional_rating(value: Any, field: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise ExplanationReviewWorkbookError(f"{field} must be an integer from 1 to 5") from exc
    if not number.is_integer() or not 1 <= int(number) <= 5:
        raise ExplanationReviewWorkbookError(f"{field} must be an integer from 1 to 5")
    return int(number)


def _batch_fingerprint(rows: Sequence[Mapping[str, str]]) -> str:
    payload = [
        {"blind_id": row["blind_id"], "immutable_fingerprint": row["immutable_fingerprint"]}
        for row in rows
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_package(package: zipfile.ZipFile) -> None:
    infos = package.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ExplanationReviewWorkbookError("XLSX package contains too many entries")
    if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
        raise ExplanationReviewWorkbookError("XLSX package expands beyond the allowed size")
    for info in infos:
        normalized = info.filename.replace("\\", "/").lstrip("/")
        lowered = normalized.casefold()
        if "../" in normalized or normalized.startswith("../"):
            raise ExplanationReviewWorkbookError("XLSX package contains an unsafe path")
        if lowered.endswith("vbaproject.bin") or any(
            lowered.startswith(prefix) for prefix in _DANGEROUS_PART_PREFIXES
        ):
            raise ExplanationReviewWorkbookError("XLSX package contains external or embedded content")
    content_types = package.read("[Content_Types].xml").decode("utf-8", errors="replace").casefold()
    if "macroenabled" in content_types or "vba" in content_types or "oleobject" in content_types:
        raise ExplanationReviewWorkbookError("XLSX package contains unsupported active content")


def _read_shared_strings(package: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in package.namelist():
        return []
    root = ET.fromstring(package.read("xl/sharedStrings.xml"))
    result: list[str] = []
    for item in root.findall(f"{{{_NS_MAIN}}}si"):
        result.append("".join(node.text or "" for node in item.iter(f"{{{_NS_MAIN}}}t")))
    return result


def _read_sheet_paths(package: zipfile.ZipFile) -> dict[str, str]:
    workbook_root = ET.fromstring(package.read("xl/workbook.xml"))
    relationships_root = ET.fromstring(package.read("xl/_rels/workbook.xml.rels"))
    relationships = {
        item.attrib["Id"]: item.attrib["Target"]
        for item in relationships_root.findall(f"{{{_NS_PACKAGE_REL}}}Relationship")
    }
    result: dict[str, str] = {}
    sheets = workbook_root.find(f"{{{_NS_MAIN}}}sheets")
    if sheets is None:
        raise ExplanationReviewWorkbookError("workbook has no sheets")
    for sheet in sheets.findall(f"{{{_NS_MAIN}}}sheet"):
        name = sheet.attrib.get("name", "")
        relation_id = sheet.attrib.get(f"{{{_NS_REL}}}id", "")
        target = relationships.get(relation_id)
        if not target:
            raise ExplanationReviewWorkbookError(f"sheet relationship is missing: {name}")
        if target.startswith("/"):
            part = target.lstrip("/")
        else:
            part = posixpath.normpath(posixpath.join("xl", target))
        result[name] = part
    return result


def _read_sheet(
    package: zipfile.ZipFile,
    part: str,
    shared_strings: list[str],
) -> dict[str, Any]:
    root = ET.fromstring(package.read(part))
    cells: dict[str, str] = {}
    formulas: dict[str, str] = {}
    types: dict[str, str] = {}
    for cell in root.iter(f"{{{_NS_MAIN}}}c"):
        reference = cell.attrib.get("r", "")
        if not reference:
            continue
        formula = cell.find(f"{{{_NS_MAIN}}}f")
        if formula is not None:
            formulas[reference] = formula.text or ""
        cell_type = cell.attrib.get("t", "")
        types[reference] = cell_type
        if cell_type == "inlineStr":
            inline = cell.find(f"{{{_NS_MAIN}}}is")
            cells[reference] = (
                "" if inline is None else "".join(node.text or "" for node in inline.iter(f"{{{_NS_MAIN}}}t"))
            )
            continue
        value_node = cell.find(f"{{{_NS_MAIN}}}v")
        raw = "" if value_node is None else (value_node.text or "")
        if cell_type == "s" and raw:
            try:
                cells[reference] = shared_strings[int(raw)]
            except (ValueError, IndexError) as exc:
                raise ExplanationReviewWorkbookError(f"invalid shared string index at {reference}") from exc
        else:
            cells[reference] = raw
    return {"cells": cells, "formulas": formulas, "types": types}


def _validate_formulas(parsed: Mapping[str, Mapping[str, Any]], case_count: int) -> None:
    allowed: dict[str, dict[str, str]] = {
        INSTRUCTIONS_SHEET: {"B27": _instruction_progress_formula(case_count).lstrip("=")},
        REVIEW_SHEET: {"E2": _progress_formula(case_count).lstrip("=")},
        METADATA_SHEET: {},
    }
    for index in range(case_count):
        excel_top = FIRST_DATA_ROW + index * 2
        allowed[REVIEW_SHEET][f"L{excel_top}"] = _status_formula(excel_top).lstrip("=")
    for sheet_name, sheet in parsed.items():
        actual = sheet.get("formulas", {})
        expected = allowed[sheet_name]
        if set(actual) != set(expected):
            raise ExplanationReviewWorkbookError(
                f"formula cells were changed in sheet {sheet_name}"
            )
        for reference, formula in actual.items():
            if re.sub(r"\s+", "", formula).casefold() != re.sub(
                r"\s+", "", expected[reference]
            ).casefold():
                raise ExplanationReviewWorkbookError(
                    f"formula was changed at {sheet_name}!{reference}"
                )


def _validate_metadata(
    sheet: Mapping[str, Any],
    rows: list[dict[str, str]],
    expected_reviewer: str | None,
) -> str:
    cells = sheet["cells"]
    metadata = {cells.get(f"A{index}", ""): cells.get(f"B{index}", "") for index in range(1, 6)}
    if metadata.get("workbook_schema_version") != WORKBOOK_SCHEMA_VERSION:
        raise ExplanationReviewWorkbookError("workbook schema version does not match")
    if metadata.get("blind_review_schema_version") != "1.0":
        raise ExplanationReviewWorkbookError("blind review schema version does not match")
    reviewer = _validate_reviewer_id(metadata.get("reviewer_id"))
    if expected_reviewer is not None and reviewer.casefold() != expected_reviewer.casefold():
        raise ExplanationReviewWorkbookError("workbook reviewer_id does not match the expected reviewer")
    if metadata.get("case_count") != str(len(rows)):
        raise ExplanationReviewWorkbookError("workbook case_count does not match the master review")
    if metadata.get("batch_fingerprint") != _batch_fingerprint(rows):
        raise ExplanationReviewWorkbookError("workbook batch fingerprint does not match the master review")
    return reviewer


def _extract_review_rows(
    sheet: Mapping[str, Any],
    master_rows: list[dict[str, str]],
    reviewer: str,
) -> list[dict[str, str]]:
    cells: Mapping[str, str] = sheet["cells"]
    types: Mapping[str, str] = sheet["types"]
    if cells.get("B2", "") != reviewer:
        raise ExplanationReviewWorkbookError("visible reviewer_id does not match workbook metadata")
    for column, header in enumerate(VISIBLE_HEADERS, start=1):
        reference = f"{_column_name(column)}5"
        if cells.get(reference, "") != header:
            raise ExplanationReviewWorkbookError(f"review header was changed at {reference}")

    extracted: list[dict[str, str]] = []
    for index, master in enumerate(master_rows):
        top = FIRST_DATA_ROW + index * 2
        bottom = top + 1
        immutable_expected = {
            f"A{top}": str(index + 1),
            f"B{top}": _display_context(master),
            f"C{top}": "A",
            f"C{bottom}": "B",
            f"D{top}": master["answer_a"],
            f"D{bottom}": master["answer_b"],
            f"N{top}": master["blind_id"],
            f"O{top}": master["immutable_fingerprint"],
            f"P{top}": master["question_type"],
            f"Q{top}": master["previsit_applicable"],
            f"R{top}": WORKBOOK_SCHEMA_VERSION,
        }
        for reference, expected in immutable_expected.items():
            if cells.get(reference, "") != expected:
                raise ExplanationReviewWorkbookError(
                    f"immutable workbook content was changed at {REVIEW_SHEET}!{reference}"
                )

        row = deepcopy(master)
        row["reviewer_id"] = reviewer
        for position, excel_row in (("a", top), ("b", bottom)):
            for column, dimension in (("E", "correctness"), ("F", "understanding"), ("G", "decision_help")):
                field = f"answer_{position}_{dimension}_1_5"
                row[field] = _read_rating(cells, types, f"{column}{excel_row}", field)
            previsit_field = f"answer_{position}_previsit_clarity_yes_no"
            previsit = _read_choice(cells, types, f"H{excel_row}", {"yes", "no", "n/a"}, previsit_field)
            if master["previsit_applicable"].casefold() == "yes":
                if previsit == "n/a":
                    raise ExplanationReviewWorkbookError(f"{previsit_field} cannot be n/a")
            elif previsit != "n/a":
                raise ExplanationReviewWorkbookError(f"{previsit_field} must remain n/a")
            row[previsit_field] = previsit
            for column, dimension in (("I", "hallucination"), ("J", "safety_issue")):
                field = f"answer_{position}_{dimension}_yes_no"
                row[field] = _read_choice(cells, types, f"{column}{excel_row}", {"yes", "no"}, field)

        row["preference"] = _read_choice(cells, types, f"K{top}", {"A", "B", "tie"}, "preference")
        notes_reference = f"M{top}"
        _reject_unsafe_cell_type(types.get(notes_reference, ""), "notes")
        row["notes"] = cells.get(notes_reference, "")
        if len(row["notes"]) > 2_000:
            raise ExplanationReviewWorkbookError("notes must not exceed 2,000 characters")
        row["review_status"] = _computed_status(row)
        extracted.append({field: str(row.get(field) or "") for field in BLIND_REVIEW_CSV_FIELDS})
    return extracted


def _read_rating(
    cells: Mapping[str, str],
    types: Mapping[str, str],
    reference: str,
    field: str,
) -> str:
    _reject_unsafe_cell_type(types.get(reference, ""), field)
    raw = cells.get(reference, "").strip()
    if not raw:
        return ""
    try:
        number = float(raw)
    except ValueError as exc:
        raise ExplanationReviewWorkbookError(f"{field} must be an integer from 1 to 5") from exc
    if not math.isfinite(number) or not number.is_integer() or not 1 <= int(number) <= 5:
        raise ExplanationReviewWorkbookError(f"{field} must be an integer from 1 to 5")
    return str(int(number))


def _read_choice(
    cells: Mapping[str, str],
    types: Mapping[str, str],
    reference: str,
    allowed: set[str],
    field: str,
) -> str:
    _reject_unsafe_cell_type(types.get(reference, ""), field)
    value = cells.get(reference, "").strip()
    if not value:
        return ""
    lookup = {item.casefold(): item for item in allowed}
    normalized = lookup.get(value.casefold())
    if normalized is None:
        raise ExplanationReviewWorkbookError(
            f"{field} must be one of: {', '.join(sorted(allowed))}"
        )
    return normalized


def _reject_unsafe_cell_type(cell_type: str, field: str) -> None:
    if cell_type in {"b", "e", "d"}:
        raise ExplanationReviewWorkbookError(f"{field} uses an unsupported Excel cell type")


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result
