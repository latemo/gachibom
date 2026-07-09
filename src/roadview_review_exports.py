"""Export operator-facing roadview review and provider request artifacts."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import zipfile
from datetime import date
from pathlib import Path
from typing import Any


FIELD_LABELS = {
    "entrance_step_or_ramp": "출입구 단차/경사로",
    "main_path_slope": "주요 동선 경사",
    "surface_condition": "바닥 상태",
    "parking_to_entrance_route": "주차장-출입구 동선",
}

STATUS_LABELS = {
    "verified": "확인됨",
    "needs_follow_up": "추가 확인",
    "conflict": "정보 충돌",
    "missing": "근거 부족",
    "pending_visual_review": "미검수",
    "open": "진행 중",
    "blocked": "차단",
    "resolved": "완료",
    "asset_required": "이미지 필요",
    "pending_reviewer_input": "검수 대기",
    "visual_review_complete": "검수 완료",
}

CONFIDENCE_LABELS = {
    "high": "높음",
    "medium": "중간",
    "low": "낮음",
}

CATEGORY_LABELS = {
    "indoor": "실내",
    "outdoor": "실외",
}

VISUAL_REVIEW_STATUSES = {
    "pending_visual_review",
    "verified",
    "needs_follow_up",
    "conflict",
    "missing",
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(content: str, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def provider_404_csv_fields() -> list[str]:
    return [
        "place_name",
        "card_id",
        "tourist_name_en",
        "image_file_name",
        "captured_at",
        "request_tier",
        "source_url",
        "error",
    ]


def export_provider_404_image_request_csv(report: dict[str, Any], output_path: str | Path) -> dict[str, int]:
    rows = [provider_404_csv_row(item) for item in report.get("items", [])]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=provider_404_csv_fields())
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": len(rows)}


def provider_404_csv_row(item: dict[str, Any]) -> dict[str, Any]:
    return {field: item.get(field, "") for field in provider_404_csv_fields()}


def build_provider_404_recovery_request_markdown(
    report: dict[str, Any],
    *,
    generated_at: date | None = None,
) -> str:
    summary = report.get("summary", {})
    by_place = summary.get("by_place", {})
    generated = (generated_at or date.today()).isoformat()
    lines = [
        "# 로드뷰 원본 404 복구 요청서",
        "",
        f"작성일: {generated}",
        "",
        "## 요청 요약",
        "",
        "- 데이터명: 제주특별자치도_사회적약자 시설 데이터(로드뷰) 구축 이미지",
        "- 요청 사유: 공공 연계 메타데이터에는 존재하지만 이미지 서버에서 원본 파일이 서버 오류 404를 반환함",
        f"- 누락 원본: {summary.get('provider_404_images', 0)}장",
        f"- 영향 장소: {summary.get('affected_places', 0)}곳",
        f"- 확인 호출 주소: {report.get('source_endpoint', '')}",
        "",
        "## 요청 사항",
        "",
        "1. 아래 파일명이 이미지 서버에서 정상 접근되도록 원본 복구",
        "2. 복구가 어려운 파일은 동일 관광지·동일 촬영 구간을 대체할 수 있는 원본 제공",
        "3. 복구 또는 대체 제공 시 파일명, 관광지 코드, 촬영시각, 접근 주소 함께 회신",
        "",
        "## 장소별 누락 현황",
        "",
        "| 장소 | 누락 장수 |",
        "| --- | ---: |",
    ]
    for place_name, count in sorted(by_place.items()):
        lines.append(f"| {place_name} | {count} |")
    lines.extend(
        [
            "",
            "## 첨부 산출물",
            "",
            "- `data/roadview_provider_404_image_request.csv`: 제공기관 전달용 누락 파일 목록",
            "- `data/roadview_provider_404_image_report.json`: 시스템 재현용 원본 리포트",
            "",
            "## 운영 메모",
            "",
            "현재 서비스 시드 우선 검수 샘플 102장은 확보됐지만, 전체 1,023장 수령 게이트는 이 70장 복구 전까지 차단 상태로 유지한다.",
            "",
        ]
    )
    return "\n".join(lines)


def visual_review_ai_summary(sheet: dict[str, Any]) -> dict[str, int]:
    results = [result for item in sheet.get("items", []) for result in item.get("field_results", [])]
    high_verified = 0
    needs_attention = 0
    medium_verified = 0
    for result in results:
        ai = result.get("ai_suggestion") or {}
        status = ai.get("status", "")
        confidence = ai.get("confidence", "")
        if status == "verified" and confidence == "high":
            high_verified += 1
        if ai_needs_attention(result):
            needs_attention += 1
        if status == "verified" and confidence != "high":
            medium_verified += 1
    return {
        "ai_high_verified": high_verified,
        "ai_needs_attention": needs_attention,
        "ai_medium_verified": medium_verified,
    }


def ai_needs_attention(result: dict[str, Any]) -> bool:
    ai = result.get("ai_suggestion") or {}
    return ai.get("status") != "verified" or ai.get("confidence") != "high"


def visual_review_ambiguity_overview(sheet: dict[str, Any]) -> str:
    place_sections = []
    total_ambiguous = 0
    for item in sheet.get("items", []):
        ambiguous_fields = [result for result in item.get("field_results", []) if ai_needs_attention(result)]
        if not ambiguous_fields:
            continue
        total_ambiguous += len(ambiguous_fields)
        card = item.get("card", {})
        rows = "\n".join(visual_review_ambiguity_row(result) for result in ambiguous_fields)
        place_sections.append(
            f"""      <details class="ambiguity-place">
        <summary>{escape_html(card.get("name", ""))} <span>{len(ambiguous_fields)}개 확인 필요</span></summary>
        <div class="ambiguity-list">
{rows}
        </div>
      </details>"""
        )
    if not place_sections:
        return ""
    return f"""    <section class="review-guide" id="attentionGuide">
      <div class="guide-head">
        <div>
          <h2>난해 항목 확인 가이드</h2>
          <p>자동 판정이 확정하기 어려운 항목은 먼저 이유와 확인 포인트를 보고 최종 판정한다.</p>
        </div>
        <div class="guide-count">{total_ambiguous}개</div>
      </div>
      <div class="guide-grid">
        <div><strong>확인됨 + 높음</strong><span>빠른 승인 후보</span></div>
        <div><strong>확인됨 + 중간</strong><span>가능해 보이나 전체 동선 확인 필요</span></div>
        <div><strong>추가 확인</strong><span>원본 확대 또는 현장 자료 확인 필요</span></div>
      </div>
{''.join(place_sections)}
    </section>"""


def visual_review_ambiguity_row(result: dict[str, Any]) -> str:
    ai = result.get("ai_suggestion") or {}
    field = result.get("field", "")
    field_label = FIELD_LABELS.get(field, field)
    points = "".join(f"<li>{escape_html(point)}</li>" for point in ai_review_points(field))
    return f"""          <article>
            <div class="ambiguity-title">
              <strong>{escape_html(field_label)}</strong>
              <span class="ai-chip {escape_attr(ai.get("status", ""))}">{escape_html(status_label(ai.get("status", "")))}</span>
              <span class="confidence-chip {escape_attr(ai.get("confidence", ""))}">{escape_html(confidence_label(ai.get("confidence", "")))}</span>
            </div>
            <p><b>왜 애매한가</b> {escape_html(ai_uncertainty_explanation(result))}</p>
            <p><b>권장 처리</b> {escape_html(ai_recommendation(result))}</p>
            <ul>{points}</ul>
          </article>"""


def ai_uncertainty_explanation(result: dict[str, Any]) -> str:
    ai = result.get("ai_suggestion") or {}
    note = strip_ai_note_prefix(ai.get("note", ""))
    status = ai.get("status", "")
    confidence = ai.get("confidence", "")
    if status == "needs_follow_up":
        return note or "이미지상 확인되지 않는 구간이 있어 최종 판정 전 추가 확인이 필요하다."
    if confidence != "high":
        return f"{note} 다만 샘플 이미지가 전체 동선을 연속적으로 보여주지는 않아 사람이 한 번 더 확인해야 한다."
    return note or "자동 판정 초안은 명확하지만 서비스 반영 전 사람 최종 확인이 필요하다."


def ai_review_points(field: str) -> list[str]:
    points = {
        "entrance_step_or_ramp": [
            "출입문 바로 앞 문턱, 계단, 경사로 유무",
            "휠체어가 실제로 통과할 수 있는 대체 진입로 표시",
        ],
        "main_path_slope": [
            "주요 관람 구간의 급경사, 긴 오르막, 급회전 여부",
            "실내와 야외 동선이 끊기지 않고 이어지는지",
        ],
        "surface_condition": [
            "흙길, 자갈, 석재 틈, 목재데크 요철 여부",
            "비가 오면 미끄러울 수 있는 바닥인지",
        ],
        "parking_to_entrance_route": [
            "장애인 주차면에서 주출입구까지 턱 없는 연속 경로",
            "차도 횡단, 경계석, 좁은 보도 같은 단절 지점",
        ],
    }
    return points.get(field, ["이미지로 보이지 않는 구간", "공식 정보 또는 현장 자료와의 일치 여부"])


def ai_recommendation(result: dict[str, Any]) -> str:
    ai = result.get("ai_suggestion") or {}
    status = ai.get("status", "")
    confidence = ai.get("confidence", "")
    if status == "needs_follow_up":
        return "확대 이미지나 공식 시설 정보로 확인 전까지는 보류 유지가 안전하다."
    if status == "verified" and confidence != "high":
        return "이미지에서 같은 판단이 가능하면 자동 판정 승인, 연결 동선이 끊겨 보이면 보류로 바꾼다."
    if status == "missing":
        return "판정 가능한 이미지가 없으면 이미지 부족으로 처리한다."
    if status == "conflict":
        return "기존 정보와 이미지가 다르면 충돌로 남기고 근거를 짧게 기록한다."
    return "자동 판정 승인 후보지만 최종 반영은 사람 판정 입력 후에만 진행한다."


def strip_ai_note_prefix(note: str) -> str:
    text = str(note or "")
    for prefix in ["자동 판정 초안: "]:
        if text.startswith(prefix):
            return text.removeprefix(prefix).strip()
    return text.strip()


def display_ai_note(note: str) -> str:
    return str(note or "")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def confidence_label(confidence: str) -> str:
    return CONFIDENCE_LABELS.get(confidence, confidence)


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)


def build_roadview_visual_review_board_html(
    sheet: dict[str, Any],
    *,
    provider_404_report: dict[str, Any] | None = None,
    output_path: str | Path | None = None,
    generated_at: date | None = None,
) -> str:
    generated = (generated_at or date.today()).isoformat()
    summary = sheet.get("summary", {})
    ai_summary = visual_review_ai_summary(sheet)
    provider_summary = (provider_404_report or {}).get("summary", {})
    ambiguity_html = visual_review_ambiguity_overview(sheet)
    body = "\n".join(visual_review_place_section(item, output_path=output_path) for item in sheet.get("items", []))
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>로드뷰 시각 검수 보드</title>
  <link rel="icon" href="data:,">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --line: #d9dee5;
      --text: #17202a;
      --muted: #667085;
      --accent: #0f766e;
      --warn: #b45309;
      --block: #b42318;
      --ok-bg: #ecfdf5;
      --warn-bg: #fffbeb;
      --block-bg: #fff1f2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, "Noto Sans KR", sans-serif;
      line-height: 1.5;
    }}
    header {{
      padding: 28px 32px 18px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    .subtle {{ color: var(--muted); font-size: 14px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 10px;
      margin-top: 18px;
    }}
    .metric {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 12px;
    }}
    .metric strong {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .metric span {{
      display: block;
      margin-top: 4px;
      font-size: 24px;
      font-weight: 700;
    }}
    main {{
      max-width: 1680px;
      margin: 0 auto;
      padding: 20px 32px 40px;
    }}
    .review-guide {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 18px;
    }}
    .guide-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 14px;
    }}
    .guide-head h2 {{
      margin: 0 0 4px;
      font-size: 20px;
    }}
    .guide-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .guide-count {{
      min-width: 70px;
      border-radius: 8px;
      background: var(--warn-bg);
      color: var(--warn);
      text-align: center;
      font-size: 24px;
      font-weight: 700;
      padding: 8px 10px;
    }}
    .guide-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}
    .guide-grid div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #f9fafb;
    }}
    .guide-grid strong, .guide-grid span {{
      display: block;
    }}
    .guide-grid span {{
      margin-top: 3px;
      color: var(--muted);
      font-size: 13px;
    }}
    .ambiguity-place {{
      border-top: 1px solid var(--line);
      padding: 10px 0;
    }}
    .ambiguity-place summary {{
      cursor: pointer;
      font-weight: 700;
    }}
    .ambiguity-place summary span {{
      color: var(--warn);
      font-size: 13px;
      margin-left: 6px;
    }}
    .ambiguity-list {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }}
    .ambiguity-list article {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }}
    .ambiguity-title {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      margin-bottom: 7px;
    }}
    .ambiguity-list p {{
      margin: 6px 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .ambiguity-list ul {{
      margin: 8px 0 0 18px;
      padding: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .place {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 18px;
      overflow: hidden;
    }}
    .place-header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
    }}
    h2 {{
      margin: 0;
      font-size: 20px;
      letter-spacing: 0;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }}
    .tag {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      color: var(--muted);
      background: #f9fafb;
      white-space: nowrap;
    }}
    .tag.open {{ color: var(--accent); border-color: #99f6e4; background: #ecfdf5; }}
    .tag.pending {{ color: var(--warn); border-color: #fed7aa; background: #fffbeb; }}
    .place-body {{
      display: grid;
      grid-template-columns: minmax(320px, 0.9fr) minmax(520px, 1.4fr);
      gap: 18px;
      padding: 18px;
    }}
    .image-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 10px;
    }}
    figure {{
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }}
    figure img {{
      display: block;
      width: 100%;
      aspect-ratio: 2 / 1;
      object-fit: cover;
      background: #eef2f6;
    }}
    figcaption {{
      padding: 8px;
      font-size: 12px;
      color: var(--muted);
      word-break: break-word;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      background: #f9fafb;
    }}
    .evidence {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .evidence a {{
      color: var(--accent);
      text-decoration: none;
      border-bottom: 1px solid #99f6e4;
      word-break: break-all;
    }}
    .note {{
      color: var(--muted);
      line-height: 1.45;
      min-width: 220px;
    }}
    .review-toolbar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-top: 16px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f9fafb;
    }}
    .review-toolbar input {{
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 9px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }}
    button {{
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      padding: 0 10px;
      font: inherit;
      cursor: pointer;
      white-space: nowrap;
    }}
    button.primary {{
      border-color: #0f766e;
      background: #0f766e;
      color: #fff;
    }}
    button.warn {{
      border-color: #f59e0b;
      color: #92400e;
      background: #fffbeb;
    }}
    button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible {{
      outline: 2px solid #0f766e;
      outline-offset: 2px;
    }}
    .review-table-wrap {{
      overflow-x: auto;
    }}
    .field-list {{
      display: grid;
      gap: 12px;
    }}
    .field-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 13px;
    }}
    .field-card.needs-attention {{
      border-color: #fed7aa;
      background: #fffaf3;
    }}
    .field-card.done {{
      background: #f0fdfa;
      border-color: #99f6e4;
    }}
    .field-card-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 10px;
    }}
    .field-label {{
      font-size: 16px;
      font-weight: 700;
    }}
    .field-meta {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 3px;
    }}
    .chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      justify-content: flex-end;
    }}
    .ai-chip, .confidence-chip {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
      background: #f9fafb;
      white-space: nowrap;
    }}
    .ai-chip.verified {{
      color: var(--accent);
      border-color: #99f6e4;
      background: var(--ok-bg);
    }}
    .ai-chip.needs_follow_up {{
      color: var(--warn);
      border-color: #fed7aa;
      background: var(--warn-bg);
    }}
    .ai-chip.missing, .ai-chip.conflict {{
      color: var(--block);
      border-color: #fecdd3;
      background: var(--block-bg);
    }}
    .confidence-chip.high {{
      color: var(--accent);
      background: var(--ok-bg);
      border-color: #99f6e4;
    }}
    .confidence-chip.medium {{
      color: var(--warn);
      background: var(--warn-bg);
      border-color: #fed7aa;
    }}
    .confidence-chip.low {{
      color: var(--block);
      background: var(--block-bg);
      border-color: #fecdd3;
    }}
    .field-layout {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) minmax(280px, 0.85fr);
      gap: 12px;
    }}
    .detail-block {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
      margin-bottom: 8px;
    }}
    .field-card.needs-attention .detail-block.attention {{
      border-color: #fed7aa;
      background: #fff;
    }}
    .detail-block strong {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    .detail-block p {{
      margin: 0;
      font-size: 13px;
      color: var(--text);
    }}
    .detail-block ul {{
      margin: 6px 0 0 18px;
      padding: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .human-panel {{
      border-left: 1px solid var(--line);
      padding-left: 12px;
    }}
    .human-panel-title {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 7px;
    }}
    .review-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      min-width: 300px;
      margin-bottom: 7px;
    }}
    .human-status {{
      width: 100%;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 8px;
      background: #fff;
      color: var(--text);
      font: inherit;
      margin-bottom: 6px;
    }}
    .human-evidence, .human-note {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 8px;
      background: #fff;
      color: var(--text);
      font: inherit;
      margin-bottom: 6px;
    }}
    .human-note {{
      min-height: 68px;
      resize: vertical;
    }}
    .save-state {{
      color: var(--muted);
      font-size: 13px;
      min-height: 20px;
    }}
    .filter-toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .filter-toolbar button.active {{
      border-color: #0f766e;
      background: #ecfdf5;
      color: #0f766e;
      font-weight: 700;
    }}
    .evidence-details {{
      margin-top: 9px;
      color: var(--muted);
      font-size: 13px;
    }}
    .evidence-details summary {{
      cursor: pointer;
    }}
{image_lightbox_styles()}
    @media (max-width: 980px) {{
      header, main {{ padding-left: 16px; padding-right: 16px; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .place-body {{ grid-template-columns: 1fr; }}
      .field-layout {{ grid-template-columns: 1fr; }}
      .human-panel {{
        border-left: 0;
        padding-left: 0;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>로드뷰 시각 검수 보드</h1>
    <div class="subtle">생성일 {escape_html(generated)} · 원본 이미지는 로컬 <code>data/raw/roadview_images</code> 기준</div>
    <div class="metrics">
      <div class="metric"><strong>검수 장소</strong><span>{summary.get("total_places", 0)}</span></div>
      <div class="metric"><strong>필드</strong><span>{summary.get("total_field_results", 0)}</span></div>
      <div class="metric"><strong>대기 필드</strong><span>{summary.get("by_field_status", {}).get("pending_visual_review", 0)}</span></div>
      <div class="metric"><strong>우선 샘플</strong><span>{sum(len(item.get("review_image_samples", [])) for item in sheet.get("items", []))}</span></div>
      <div class="metric"><strong>서버 404</strong><span>{provider_summary.get("provider_404_images", 0)}</span></div>
      <div class="metric"><strong>자동 판정 확실</strong><span>{ai_summary.get("ai_high_verified", 0)}</span></div>
      <div class="metric"><strong>난해 항목</strong><span>{ai_summary.get("ai_needs_attention", 0)}</span></div>
      <div class="metric"><strong>중간 신뢰 승인</strong><span>{ai_summary.get("ai_medium_verified", 0)}</span></div>
    </div>
    <div class="review-toolbar" data-generated-at="{escape_attr(generated)}">
      <strong id="statusSummary">완료 0/{summary.get("total_field_results", 0)}</strong>
      <input id="reviewerInput" type="text" placeholder="검수자">
      <input id="reviewedAtInput" type="date" value="{escape_attr(generated)}">
      <button type="button" class="primary" id="approveVerifiedButton">확실한 자동 판정 승인</button>
      <button type="button" id="approveAllButton">전체 자동 판정 승인</button>
      <button type="button" id="connectCsvButton">판정 파일 연결</button>
      <button type="button" id="saveCsvButton">판정 파일 저장</button>
      <button type="button" id="downloadCsvButton">판정 파일 내려받기</button>
      <button type="button" class="warn" id="clearHumanButton">입력 초기화</button>
      <span class="save-state" id="saveState"></span>
    </div>
    <div class="filter-toolbar" aria-label="검수 항목 필터">
      <button type="button" class="active" data-filter="all">전체</button>
      <button type="button" data-filter="attention">난해 항목</button>
      <button type="button" data-filter="high">자동 판정 확실</button>
      <button type="button" data-filter="unfinished">미입력</button>
    </div>
  </header>
  <main>
{ambiguity_html}
{body}
  </main>
  {interactive_visual_review_script()}
  {image_lightbox_script()}
  {image_lightbox_html()}
</body>
</html>
"""


def visual_review_place_section(item: dict[str, Any], *, output_path: str | Path | None) -> str:
    card = item.get("card", {})
    images = item.get("review_image_samples", [])
    fields = item.get("field_results", [])
    image_html = "\n".join(visual_review_image_figure(image, output_path=output_path) for image in images)
    field_html = "\n".join(visual_review_field_row(card, field, images, output_path=output_path) for field in fields)
    return f"""    <section class="place" id="{escape_attr(card.get("id", ""))}">
      <div class="place-header">
        <div>
          <h2>{escape_html(card.get("name", ""))}</h2>
          <div class="tags">
            <span class="tag">{escape_html(card.get("region", ""))}</span>
            <span class="tag">{escape_html(category_label(card.get("category", "")))}</span>
            <span class="tag open">{escape_html(status_label(item.get("status", "")))}</span>
            <span class="tag pending">{escape_html(status_label(item.get("review_decision", "")))}</span>
          </div>
        </div>
        <div class="subtle">이미지 {len(images)}장 · 검수 항목 {len(fields)}개</div>
      </div>
      <div class="place-body">
        <div class="image-grid">
{image_html}
        </div>
        <div class="field-list">
{field_html}
        </div>
      </div>
    </section>"""


def visual_review_image_figure(image: dict[str, Any], *, output_path: str | Path | None) -> str:
    present_path = image.get("present_path") or ""
    href = html_asset_href(present_path, output_path=output_path)
    caption = f"{image.get('image_file_name', '')} · {image.get('captured_at', '')}"
    lat = image.get("latitude")
    lon = image.get("longitude")
    if lat is not None and lon is not None:
        caption = f"{caption} · {lat:.6f}, {lon:.6f}"
    return f"""          <figure>
            <a href="{escape_attr(href)}" data-lightbox-image data-lightbox-caption="{escape_attr(caption)}"><img loading="lazy" src="{escape_attr(href)}" alt="{escape_attr(image.get("image_file_name", ""))}"></a>
            <figcaption>{escape_html(caption)}</figcaption>
          </figure>"""


def visual_review_field_row(
    card: dict[str, Any],
    field: dict[str, Any],
    images: list[dict[str, Any]],
    *,
    output_path: str | Path | None,
) -> str:
    image_by_name = {image.get("image_file_name"): image for image in images}
    ai_suggestion = field.get("ai_suggestion") or {}
    field_name = field.get("field", "")
    field_label = FIELD_LABELS.get(field_name, field_name)
    ai_evidence = join_list(ai_suggestion.get("evidence_image_file_names", []))
    available_images = join_list(field.get("image_file_names", []))
    human_status = final_status_for_csv(field)
    human_evidence = join_list(field.get("evidence_image_file_names", []))
    human_note = field.get("reviewer_note", "")
    attention = ai_needs_attention(field)
    attention_class = " needs-attention" if attention else ""
    ai_status = ai_suggestion.get("status", "")
    ai_confidence = ai_suggestion.get("confidence", "")
    ai_note = ai_suggestion.get("note", "")
    displayed_ai_note = display_ai_note(ai_note)
    attention_html = visual_review_field_attention_html(field) if attention else ""
    evidence_links = []
    for image_file_name in field.get("image_file_names", []):
        image = image_by_name.get(image_file_name, {})
        href = html_asset_href(image.get("present_path") or "", output_path=output_path)
        evidence_links.append(f'<a href="{escape_attr(href)}">{escape_html(image_file_name)}</a>')
    done_class = " done" if human_status else ""
    return f"""          <article class="field-card review-row{attention_class}{done_class}"
                  data-card-id="{escape_attr(card.get("id", ""))}"
                  data-place-name="{escape_attr(card.get("name", ""))}"
                  data-field="{escape_attr(field_name)}"
                  data-field-label="{escape_attr(field_label)}"
                  data-ai-status="{escape_attr(ai_status)}"
                  data-ai-evidence="{escape_attr(ai_evidence)}"
                  data-ai-note="{escape_attr(ai_note)}"
                  data-ai-confidence="{escape_attr(ai_confidence)}"
                  data-attention="{str(attention).lower()}"
                  data-available="{escape_attr(available_images)}"
                  data-human-reviewer="{escape_attr(field.get("reviewer") or "")}"
                  data-human-reviewed-at="{escape_attr(field.get("reviewed_at") or "")}">
            <div class="field-card-head">
              <div>
                <div class="field-label">{escape_html(field_label)}</div>
                <div class="field-meta">{escape_html(card.get("name", ""))}</div>
              </div>
              <div class="chip-row">
                <span class="ai-chip {escape_attr(ai_status)}">{escape_html(status_label(ai_status))}</span>
                <span class="confidence-chip {escape_attr(ai_confidence)}">{escape_html(confidence_label(ai_confidence))}</span>
              </div>
            </div>
            <div class="field-layout">
              <div>
                <div class="detail-block">
                  <strong>자동 판정 근거</strong>
                  <p>{escape_html(displayed_ai_note)}</p>
                </div>
{attention_html}
                <details class="evidence-details">
                  <summary>근거 이미지 {len(field.get("image_file_names", []))}장 보기</summary>
                  <div class="evidence">{''.join(evidence_links)}</div>
                </details>
              </div>
              <div class="human-panel">
                <div class="human-panel-title">사람 최종 판정</div>
                <div class="review-actions">
                  <button type="button" data-row-action="approve-ai">자동 판정 승인</button>
                  <button type="button" data-row-action="needs-follow-up">보류</button>
                  <button type="button" data-row-action="missing">이미지 부족</button>
                  <button type="button" data-row-action="conflict">충돌</button>
                </div>
                {human_status_select_html(human_status)}
                <input class="human-evidence" type="text" value="{escape_attr(human_evidence)}" placeholder="근거 이미지명">
                <textarea class="human-note" placeholder="최종 메모">{escape_html(human_note)}</textarea>
              </div>
            </div>
          </article>"""


def visual_review_field_attention_html(field: dict[str, Any]) -> str:
    points = "".join(f"<li>{escape_html(point)}</li>" for point in ai_review_points(field.get("field", "")))
    return f"""                <div class="detail-block attention">
                  <strong>왜 사람이 다시 봐야 하나</strong>
                  <p>{escape_html(ai_uncertainty_explanation(field))}</p>
                </div>
                <div class="detail-block attention">
                  <strong>확인 포인트</strong>
                  <ul>{points}</ul>
                </div>
                <div class="detail-block attention">
                  <strong>권장 처리</strong>
                  <p>{escape_html(ai_recommendation(field))}</p>
                </div>"""


def human_status_select_html(current_status: str) -> str:
    options = [
        ("", "미입력"),
        ("verified", "확인됨"),
        ("needs_follow_up", "추가 확인"),
        ("conflict", "정보 충돌"),
        ("missing", "근거 부족"),
    ]
    option_html = "\n".join(
        f'<option value="{escape_attr(value)}"{selected_attr(value == current_status)}>{escape_html(label)}</option>'
        for value, label in options
    )
    return f'<select class="human-status">{option_html}</select>'


def selected_attr(is_selected: bool) -> str:
    return " selected" if is_selected else ""


def image_lightbox_styles() -> str:
    return """
    a[data-lightbox-image] {
      cursor: zoom-in;
    }
    body.lightbox-open {
      overflow: hidden;
    }
    .image-lightbox[hidden] {
      display: none;
    }
    .image-lightbox {
      position: fixed;
      inset: 0;
      z-index: 2000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .image-lightbox-backdrop {
      position: absolute;
      inset: 0;
      background: rgba(15, 23, 42, 0.82);
    }
    .image-lightbox-panel {
      position: relative;
      z-index: 1;
      display: grid;
      justify-items: center;
      gap: 10px;
      max-width: min(96vw, 1440px);
      max-height: 92vh;
    }
    .image-lightbox-close {
      justify-self: end;
      border-color: rgba(255, 255, 255, 0.35);
      background: #ffffff;
      color: #111827;
      font-weight: 700;
    }
    .image-lightbox img {
      display: block;
      max-width: 96vw;
      max-height: 82vh;
      object-fit: contain;
      border-radius: 8px;
      background: #0f172a;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
    }
    .image-lightbox-caption {
      max-width: 96vw;
      color: #fff;
      font-size: 13px;
      line-height: 1.45;
      text-align: center;
      word-break: break-word;
    }
"""


def image_lightbox_html() -> str:
    return """<div class="image-lightbox" id="imageLightbox" hidden role="dialog" aria-modal="true" aria-label="이미지 확대 보기">
    <div class="image-lightbox-backdrop" data-lightbox-close></div>
    <div class="image-lightbox-panel">
      <button type="button" class="image-lightbox-close" data-lightbox-close>닫기</button>
      <img id="imageLightboxImage" alt="">
      <div class="image-lightbox-caption" id="imageLightboxCaption"></div>
    </div>
  </div>"""


def image_lightbox_script() -> str:
    return """<script>
(function () {
  let activeTrigger = null;

  function lightboxElements() {
    return {
      modal: document.getElementById("imageLightbox"),
      image: document.getElementById("imageLightboxImage"),
      caption: document.getElementById("imageLightboxCaption"),
      closeButton: document.querySelector("[data-lightbox-close].image-lightbox-close")
    };
  }

  function openLightbox(link) {
    const { modal, image, caption, closeButton } = lightboxElements();
    if (!modal || !image || !caption) {
      return;
    }
    const sourceImage = link.querySelector("img");
    activeTrigger = link;
    image.src = link.href;
    image.alt = sourceImage?.alt || "확대 이미지";
    caption.textContent = link.dataset.lightboxCaption || sourceImage?.alt || "";
    modal.hidden = false;
    modal.classList.add("open");
    document.body.classList.add("lightbox-open");
    closeButton?.focus();
  }

  function closeLightbox() {
    const { modal, image, caption } = lightboxElements();
    if (!modal || modal.hidden) {
      return;
    }
    modal.hidden = true;
    modal.classList.remove("open");
    document.body.classList.remove("lightbox-open");
    if (image) {
      image.removeAttribute("src");
      image.alt = "";
    }
    if (caption) {
      caption.textContent = "";
    }
    activeTrigger?.focus();
    activeTrigger = null;
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-lightbox-close]")) {
      event.preventDefault();
      closeLightbox();
      return;
    }
    const imageLink = event.target.closest("a[data-lightbox-image]");
    if (!imageLink) {
      return;
    }
    event.preventDefault();
    openLightbox(imageLink);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeLightbox();
    }
  });
})();
</script>"""


def interactive_visual_review_script() -> str:
    return """<script>
(function () {
  const CSV_FIELDS = [
    "card_id",
    "place_name",
    "field",
    "field_label",
    "ai_suggested_status",
    "ai_suggested_evidence_image_file_names",
    "ai_suggested_note",
    "ai_confidence",
    "human_final_status",
    "human_evidence_image_file_names",
    "human_reviewer_note",
    "human_reviewer",
    "human_reviewed_at",
    "available_image_file_names"
  ];
  const DRAFT_KEY = "jeju_maeum_roadview_visual_review_draft_v1:" + window.location.pathname;
  const FOLLOW_UP_NOTES = {
    entrance_step_or_ramp: "출입구 단차 또는 경사로 확대 확인 필요",
    main_path_slope: "주요 관람 동선 경사 확인 필요",
    surface_condition: "노면 상태 확대 확인 필요",
    parking_to_entrance_route: "주차장-출입구 연속 동선 확인 필요"
  };
  let csvFileHandle = null;
  let autoSaveTimer = null;

  const rows = () => Array.from(document.querySelectorAll(".review-row"));
  const reviewerInput = document.getElementById("reviewerInput");
  const reviewedAtInput = document.getElementById("reviewedAtInput");
  const statusSummary = document.getElementById("statusSummary");
  const saveState = document.getElementById("saveState");

  function setSaveState(message) {
    if (saveState) {
      saveState.textContent = message || "";
    }
  }

  function rowKey(row) {
    return row.dataset.cardId + "\\u001f" + row.dataset.field;
  }

  function humanControls(row) {
    return {
      status: row.querySelector(".human-status"),
      evidence: row.querySelector(".human-evidence"),
      note: row.querySelector(".human-note")
    };
  }

  function stripAiPrefix(note) {
    return String(note || "").replace(/^자동 판정 초안:\\s*/, "");
  }

  function setRowHuman(row, status, evidence, note, options = {}) {
    const controls = humanControls(row);
    controls.status.value = status || "";
    controls.evidence.value = evidence || "";
    controls.note.value = note || "";
    row.classList.toggle("done", Boolean(controls.status.value));
    updateSummary();
    if (!options.silent) {
      persistDraft();
      scheduleAutoSave();
    }
  }

  function approveAi(row) {
    const status = row.dataset.aiStatus || "needs_follow_up";
    const evidence = row.dataset.aiEvidence || row.dataset.available || "";
    const note = stripAiPrefix(row.dataset.aiNote) || "자동 판정 초안 확인";
    setRowHuman(row, status, evidence, note);
  }

  function quickDecision(row, status) {
    let evidence = row.dataset.aiEvidence || row.dataset.available || "";
    let note = FOLLOW_UP_NOTES[row.dataset.field] || "이미지상 추가 확인 필요";
    if (status === "missing") {
      evidence = "";
      note = "판정 가능한 이미지 근거 부족";
    }
    if (status === "conflict") {
      note = "기존 정보와 이미지 내용 충돌 가능성 확인 필요";
    }
    setRowHuman(row, status, evidence, note);
  }

  function updateSummary() {
    const allRows = rows();
    const done = allRows.filter((row) => humanControls(row).status.value).length;
    if (statusSummary) {
      statusSummary.textContent = "완료 " + done + "/" + allRows.length;
    }
  }

  function recordFromRow(row) {
    const controls = humanControls(row);
    const status = controls.status.value;
    return {
      card_id: row.dataset.cardId || "",
      place_name: row.dataset.placeName || "",
      field: row.dataset.field || "",
      field_label: row.dataset.fieldLabel || "",
      ai_suggested_status: row.dataset.aiStatus || "",
      ai_suggested_evidence_image_file_names: row.dataset.aiEvidence || "",
      ai_suggested_note: row.dataset.aiNote || "",
      ai_confidence: row.dataset.aiConfidence || "",
      human_final_status: status,
      human_evidence_image_file_names: controls.evidence.value.trim(),
      human_reviewer_note: controls.note.value.trim(),
      human_reviewer: status ? (reviewerInput.value.trim() || row.dataset.humanReviewer || "") : "",
      human_reviewed_at: status ? (reviewedAtInput.value || row.dataset.humanReviewedAt || "") : "",
      available_image_file_names: row.dataset.available || ""
    };
  }

  function csvEscape(value) {
    const text = String(value ?? "");
    if (/[",\\r\\n]/.test(text)) {
      return '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
  }

  function buildCsv() {
    const lines = [CSV_FIELDS.join(",")];
    rows().forEach((row) => {
      const record = recordFromRow(row);
      lines.push(CSV_FIELDS.map((field) => csvEscape(record[field])).join(","));
    });
    return "\\ufeff" + lines.join("\\r\\n") + "\\r\\n";
  }

  function downloadCsv() {
    const blob = new Blob([buildCsv()], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "roadview_visual_review_decisions.reviewed.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setSaveState("판정 파일 내려받기 완료");
  }

  async function writeConnectedCsv() {
    if (!csvFileHandle) {
      return false;
    }
    const writable = await csvFileHandle.createWritable();
    await writable.write(buildCsv());
    await writable.close();
    setSaveState("판정 파일 저장 완료");
    return true;
  }

  function scheduleAutoSave() {
    if (!csvFileHandle) {
      setSaveState("임시 저장됨");
      return;
    }
    window.clearTimeout(autoSaveTimer);
    autoSaveTimer = window.setTimeout(async () => {
      try {
        await writeConnectedCsv();
      } catch (error) {
        setSaveState("자동 저장 실패: 판정 파일 저장 버튼 사용");
      }
    }, 450);
  }

  async function connectCsvFile() {
    if (!window.showOpenFilePicker) {
      setSaveState("브라우저가 파일 직접 저장을 지원하지 않음");
      return;
    }
    try {
      const handles = await window.showOpenFilePicker({
        multiple: false,
        types: [{ description: "판정 파일", accept: { "text/csv": [".csv"] } }]
      });
      csvFileHandle = handles[0];
      const file = await csvFileHandle.getFile();
      applyCsvText(await file.text());
      persistDraft();
      setSaveState("판정 파일 연결됨: 이후 변경은 자동 저장");
    } catch (error) {
      setSaveState("판정 파일 연결 취소");
    }
  }

  async function saveCsv() {
    if (window.showSaveFilePicker && !csvFileHandle) {
      try {
        csvFileHandle = await window.showSaveFilePicker({
          suggestedName: "roadview_visual_review_decisions.csv",
          types: [{ description: "판정 파일", accept: { "text/csv": [".csv"] } }]
        });
      } catch (error) {
        downloadCsv();
        return;
      }
    }
    try {
      if (!(await writeConnectedCsv())) {
        downloadCsv();
      }
    } catch (error) {
      downloadCsv();
    }
  }

  function persistDraft() {
    const draft = {
      reviewer: reviewerInput.value,
      reviewedAt: reviewedAtInput.value,
      rows: rows().map((row) => {
        const controls = humanControls(row);
        return {
          key: rowKey(row),
          status: controls.status.value,
          evidence: controls.evidence.value,
          note: controls.note.value
        };
      })
    };
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch (error) {
      return;
    }
  }

  function restoreDraft() {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) {
        return;
      }
      const draft = JSON.parse(raw);
      if (draft.reviewer && !reviewerInput.value) {
        reviewerInput.value = draft.reviewer;
      }
      if (draft.reviewedAt && !reviewedAtInput.value) {
        reviewedAtInput.value = draft.reviewedAt;
      }
      const byKey = new Map((draft.rows || []).map((item) => [item.key, item]));
      rows().forEach((row) => {
        const item = byKey.get(rowKey(row));
        if (item) {
          setRowHuman(row, item.status, item.evidence, item.note, { silent: true });
        }
      });
      setSaveState("임시 저장 복원됨");
    } catch (error) {
      return;
    }
  }

  function parseCsv(text) {
    const clean = String(text || "").replace(/^\\uFEFF/, "");
    const table = [];
    let row = [];
    let cell = "";
    let inQuotes = false;
    for (let index = 0; index < clean.length; index += 1) {
      const char = clean[index];
      const next = clean[index + 1];
      if (inQuotes) {
        if (char === '"' && next === '"') {
          cell += '"';
          index += 1;
        } else if (char === '"') {
          inQuotes = false;
        } else {
          cell += char;
        }
      } else if (char === '"') {
        inQuotes = true;
      } else if (char === ",") {
        row.push(cell);
        cell = "";
      } else if (char === "\\n") {
        row.push(cell.replace(/\\r$/, ""));
        table.push(row);
        row = [];
        cell = "";
      } else {
        cell += char;
      }
    }
    if (cell || row.length) {
      row.push(cell.replace(/\\r$/, ""));
      table.push(row);
    }
    return table;
  }

  function applyCsvText(text) {
    const table = parseCsv(text);
    if (!table.length) {
      return;
    }
    const headers = table[0];
    const records = table.slice(1).map((values) => {
      const record = {};
      headers.forEach((header, index) => {
        record[header] = values[index] || "";
      });
      return record;
    });
    const byKey = new Map(records.map((record) => [record.card_id + "\\u001f" + record.field, record]));
    rows().forEach((row) => {
      const record = byKey.get(rowKey(row));
      if (!record) {
        return;
      }
      row.dataset.humanReviewer = record.human_reviewer || "";
      row.dataset.humanReviewedAt = record.human_reviewed_at || "";
      setRowHuman(
        row,
        record.human_final_status || "",
        record.human_evidence_image_file_names || "",
        record.human_reviewer_note || "",
        { silent: true }
      );
    });
    updateSummary();
  }

  function clearHumanInputs() {
    if (!window.confirm("입력한 사람 최종 판정을 모두 지울까요?")) {
      return;
    }
    rows().forEach((row) => setRowHuman(row, "", "", "", { silent: true }));
    persistDraft();
    scheduleAutoSave();
  }

  function rowMatchesFilter(row, filter) {
    if (filter === "attention") {
      return row.dataset.attention === "true";
    }
    if (filter === "high") {
      return row.dataset.aiStatus === "verified" && row.dataset.aiConfidence === "high";
    }
    if (filter === "unfinished") {
      return !humanControls(row).status.value;
    }
    return true;
  }

  function applyFilter(filter) {
    rows().forEach((row) => {
      row.hidden = !rowMatchesFilter(row, filter);
    });
    document.querySelectorAll(".place").forEach((place) => {
      const visibleRows = Array.from(place.querySelectorAll(".review-row")).filter((row) => !row.hidden);
      place.hidden = visibleRows.length === 0;
    });
    document.querySelectorAll("[data-filter]").forEach((button) => {
      button.classList.toggle("active", button.dataset.filter === filter);
    });
  }

  document.addEventListener("click", (event) => {
    const actionButton = event.target.closest("[data-row-action]");
    if (actionButton) {
      const row = actionButton.closest(".review-row");
      const action = actionButton.dataset.rowAction;
      if (action === "approve-ai") {
        approveAi(row);
      } else if (action === "needs-follow-up") {
        quickDecision(row, "needs_follow_up");
      } else if (action === "missing") {
        quickDecision(row, "missing");
      } else if (action === "conflict") {
        quickDecision(row, "conflict");
      }
      return;
    }
  });

  document.addEventListener("change", (event) => {
    if (event.target.matches(".human-status, .human-evidence, .human-note, #reviewerInput, #reviewedAtInput")) {
      const row = event.target.closest(".review-row");
      if (row) {
        row.classList.toggle("done", Boolean(humanControls(row).status.value));
      }
      updateSummary();
      persistDraft();
      scheduleAutoSave();
    }
  });

  document.addEventListener("input", (event) => {
    if (event.target.matches(".human-evidence, .human-note, #reviewerInput, #reviewedAtInput")) {
      persistDraft();
      scheduleAutoSave();
    }
  });

  document.getElementById("approveVerifiedButton")?.addEventListener("click", () => {
    rows()
      .filter((row) => row.dataset.aiStatus === "verified" && row.dataset.aiConfidence === "high")
      .forEach(approveAi);
  });
  document.getElementById("approveAllButton")?.addEventListener("click", () => {
    if (window.confirm("자동 판정 초안 68개를 모두 사람 최종 판정으로 복사할까요?")) {
      rows().forEach(approveAi);
    }
  });
  document.getElementById("connectCsvButton")?.addEventListener("click", connectCsvFile);
  document.getElementById("saveCsvButton")?.addEventListener("click", saveCsv);
  document.getElementById("downloadCsvButton")?.addEventListener("click", downloadCsv);
  document.getElementById("clearHumanButton")?.addEventListener("click", clearHumanInputs);
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => applyFilter(button.dataset.filter || "all"));
  });

  restoreDraft();
  updateSummary();
})();
</script>"""


def html_asset_href(asset_path: str, *, output_path: str | Path | None) -> str:
    if not asset_path:
        return ""
    if output_path is None:
        return Path(asset_path).as_posix()
    relative_path = os.path.relpath(Path(asset_path), Path(output_path).parent)
    return Path(relative_path).as_posix()


def escape_html(value: Any) -> str:
    return html.escape(str(value), quote=False)


def escape_attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


def visual_review_decision_csv_fields() -> list[str]:
    return [
        "card_id",
        "place_name",
        "field",
        "field_label",
        "ai_suggested_status",
        "ai_suggested_evidence_image_file_names",
        "ai_suggested_note",
        "ai_confidence",
        "human_final_status",
        "human_evidence_image_file_names",
        "human_reviewer_note",
        "human_reviewer",
        "human_reviewed_at",
        "available_image_file_names",
    ]


def export_visual_review_decision_csv(sheet: dict[str, Any], output_path: str | Path) -> dict[str, int]:
    rows = [visual_review_decision_csv_row(item, result) for item in sheet.get("items", []) for result in item.get("field_results", [])]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=visual_review_decision_csv_fields())
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": len(rows)}


def visual_review_decision_csv_row(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    card = item.get("card", {})
    ai_suggestion = result.get("ai_suggestion") or {}
    return {
        "card_id": card.get("id", ""),
        "place_name": card.get("name", ""),
        "field": result.get("field", ""),
        "field_label": FIELD_LABELS.get(result.get("field", ""), result.get("field", "")),
        "ai_suggested_status": ai_suggestion.get("status", ""),
        "ai_suggested_evidence_image_file_names": join_list(ai_suggestion.get("evidence_image_file_names", [])),
        "ai_suggested_note": ai_suggestion.get("note", ""),
        "ai_confidence": ai_suggestion.get("confidence", ""),
        "human_final_status": final_status_for_csv(result),
        "human_evidence_image_file_names": join_list(result.get("evidence_image_file_names", [])),
        "human_reviewer_note": result.get("reviewer_note", ""),
        "human_reviewer": result.get("reviewer") or "",
        "human_reviewed_at": result.get("reviewed_at") or "",
        "available_image_file_names": join_list(result.get("image_file_names", [])),
    }


def final_status_for_csv(result: dict[str, Any]) -> str:
    status = result.get("status", "pending_visual_review")
    return "" if status == "pending_visual_review" else status


def apply_visual_review_decision_csv(
    sheet: dict[str, Any],
    csv_path: str | Path,
    *,
    reviewer: str = "operator",
    reviewed_at: date | None = None,
    generated_at: date | None = None,
) -> dict[str, Any]:
    rows = read_visual_review_decision_rows(csv_path)
    updated_sheet = json.loads(json.dumps(sheet, ensure_ascii=False))
    index = {
        (item.get("card", {}).get("id", ""), result.get("field", "")): result
        for item in updated_sheet.get("items", [])
        for result in item.get("field_results", [])
    }
    report_items = []
    for row in rows:
        key = (row.get("card_id", ""), row.get("field", ""))
        result = index.get(key)
        if result is None:
            report_items.append(visual_decision_import_report_item(row, "skipped_not_found", ""))
            continue
        action, reason = apply_visual_review_decision_row(
            result,
            row,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
        )
        report_items.append(visual_decision_import_report_item(row, action, reason))
    refresh_visual_review_sheet_summary(updated_sheet)
    return {
        "updated_visual_review_sheet": updated_sheet,
        "import_report": {
            "generated_at": (generated_at or date.today()).isoformat(),
            "source_visual_review_sheet_generated_at": sheet.get("generated_at"),
            "source_decision_csv": str(csv_path).replace("\\", "/"),
            "summary": summarize_visual_decision_import_report(report_items),
            "items": report_items,
        },
    }


def read_visual_review_decision_rows(csv_path: str | Path) -> list[dict[str, str]]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def apply_visual_review_decision_row(
    result: dict[str, Any],
    row: dict[str, str],
    *,
    reviewer: str,
    reviewed_at: date | None,
) -> tuple[str, str]:
    status = decision_row_status(row)
    if not status or status == "pending_visual_review":
        return "skipped_pending_input", "human_final_status_pending"
    if status not in VISUAL_REVIEW_STATUSES:
        return "invalid_status", f"unsupported_status:{status}"

    evidence = split_list(decision_row_value(row, "human_evidence_image_file_names", "evidence_image_file_names"))
    available = set(result.get("image_file_names", []))
    invalid_evidence = [name for name in evidence if name not in available]
    if invalid_evidence:
        return "invalid_evidence", "unknown_images:" + ",".join(invalid_evidence)

    note = normalize_text(decision_row_value(row, "human_reviewer_note", "reviewer_note"))
    if status in {"verified", "needs_follow_up", "conflict"} and not evidence:
        return "invalid_evidence", "evidence_required"
    if status in {"verified", "needs_follow_up", "conflict", "missing"} and not note:
        return "invalid_note", "reviewer_note_required"

    result["status"] = status
    result["evidence_image_file_names"] = evidence
    result["reviewer_note"] = note
    result["reviewer"] = normalize_text(decision_row_value(row, "human_reviewer", "reviewer")) or reviewer
    result["reviewed_at"] = normalize_text(decision_row_value(row, "human_reviewed_at", "reviewed_at")) or (reviewed_at or date.today()).isoformat()
    return "applied", ""


def visual_decision_import_report_item(row: dict[str, str], action: str, reason: str) -> dict[str, str]:
    return {
        "card_id": row.get("card_id", ""),
        "place_name": row.get("place_name", ""),
        "field": row.get("field", ""),
        "status": decision_row_status(row),
        "action": action,
        "reason": reason,
    }


def summarize_visual_decision_import_report(items: list[dict[str, str]]) -> dict[str, Any]:
    by_action: dict[str, int] = {}
    for item in items:
        action = item.get("action", "unknown")
        by_action[action] = by_action.get(action, 0) + 1
    return {
        "total_rows": len(items),
        "applied": by_action.get("applied", 0),
        "skipped": sum(count for action, count in by_action.items() if action.startswith("skipped")),
        "invalid": sum(count for action, count in by_action.items() if action.startswith("invalid")),
        "by_action": dict(sorted(by_action.items())),
    }


def refresh_visual_review_sheet_summary(sheet: dict[str, Any]) -> None:
    by_status: dict[str, int] = {}
    by_review_decision: dict[str, int] = {}
    by_field_status: dict[str, int] = {}
    total_field_results = 0
    for item in sheet.get("items", []):
        item_status = visual_review_item_status(item)
        item_decision = visual_review_item_decision(item)
        item["status"] = item_status
        item["review_decision"] = item_decision
        by_status[item_status] = by_status.get(item_status, 0) + 1
        by_review_decision[item_decision] = by_review_decision.get(item_decision, 0) + 1
        for result in item.get("field_results", []):
            total_field_results += 1
            field_status = result.get("status", "unknown")
            by_field_status[field_status] = by_field_status.get(field_status, 0) + 1
    sheet["summary"] = {
        "total_places": len(sheet.get("items", [])),
        "by_status": dict(sorted(by_status.items())),
        "by_review_decision": dict(sorted(by_review_decision.items())),
        "total_field_results": total_field_results,
        "by_field_status": dict(sorted(by_field_status.items())),
    }


def visual_review_item_status(item: dict[str, Any]) -> str:
    if item.get("image_asset_status") != "ready_for_visual_review":
        return "blocked"
    if all(result.get("status") != "pending_visual_review" for result in item.get("field_results", [])):
        return "resolved"
    return "open"


def visual_review_item_decision(item: dict[str, Any]) -> str:
    statuses = [result.get("status", "pending_visual_review") for result in item.get("field_results", [])]
    if not statuses or any(status == "pending_visual_review" for status in statuses):
        return "pending_reviewer_input"
    if all(status == "verified" for status in statuses):
        return "visual_review_complete"
    return "needs_follow_up"


def split_list(value: str) -> list[str]:
    return [part.strip() for part in value.replace(",", ";").split(";") if part.strip()]


def join_list(values: list[str]) -> str:
    return ";".join(values)


def normalize_text(value: str | None) -> str:
    return (value or "").strip()


def decision_row_status(row: dict[str, str]) -> str:
    return normalize_text(decision_row_value(row, "human_final_status", "status"))


def decision_row_value(row: dict[str, str], primary: str, legacy: str) -> str:
    return normalize_text(row.get(primary, "")) or normalize_text(row.get(legacy, ""))


def normalized_visual_review_decision_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {field: row.get(field, "") for field in visual_review_decision_csv_fields()}
    normalized["human_final_status"] = decision_row_status(row)
    normalized["human_evidence_image_file_names"] = decision_row_value(
        row,
        "human_evidence_image_file_names",
        "evidence_image_file_names",
    )
    normalized["human_reviewer_note"] = decision_row_value(row, "human_reviewer_note", "reviewer_note")
    normalized["human_reviewer"] = decision_row_value(row, "human_reviewer", "reviewer")
    normalized["human_reviewed_at"] = decision_row_value(row, "human_reviewed_at", "reviewed_at")
    return normalized


def build_visual_review_packets(
    sheet: dict[str, Any],
    *,
    contact_sheet_dir: str | Path,
    csv_dir: str | Path,
    index_output: str | Path,
    generated_at: date | None = None,
) -> dict[str, Any]:
    contact_dir = Path(contact_sheet_dir)
    csv_output_dir = Path(csv_dir)
    index_path = Path(index_output)
    contact_dir.mkdir(parents=True, exist_ok=True)
    csv_output_dir.mkdir(parents=True, exist_ok=True)
    generated = generated_at or date.today()
    packet_items = []
    for item in sheet.get("items", []):
        card = item.get("card", {})
        card_id = card.get("id", "")
        contact_path = contact_dir / f"{card_id}.jpg"
        csv_path = csv_output_dir / f"{card_id}.csv"
        build_visual_review_contact_sheet(item, contact_path)
        export_visual_review_place_decision_csv(item, csv_path)
        packet_items.append(
            {
                "card_id": card_id,
                "place_name": card.get("name", ""),
                "contact_sheet": str(contact_path).replace("\\", "/"),
                "decision_csv": str(csv_path).replace("\\", "/"),
                "image_count": len(item.get("review_image_samples", [])),
                "field_count": len(item.get("field_results", [])),
            }
        )
    write_text(build_visual_review_packet_index(packet_items, index_output=index_path, generated_at=generated), index_path)
    return {
        "generated_at": generated.isoformat(),
        "total_places": len(packet_items),
        "contact_sheet_count": len(packet_items),
        "decision_csv_count": len(packet_items),
        "index_output": str(index_path).replace("\\", "/"),
        "items": packet_items,
    }


def build_visual_review_contact_sheet(item: dict[str, Any], output_path: str | Path) -> None:
    from PIL import Image, ImageDraw

    images = item.get("review_image_samples", [])
    thumb_width = 420
    thumb_height = 210
    caption_height = 34
    padding = 14
    columns = 2 if len(images) <= 4 else 3
    rows = max(1, (len(images) + columns - 1) // columns)
    header_height = 56
    width = padding + columns * (thumb_width + padding)
    height = header_height + padding + rows * (thumb_height + caption_height + padding)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    card = item.get("card", {})
    draw.text((padding, 14), f"{card.get('id', '')} / 샘플 {len(images)}장", fill=(20, 30, 40))
    draw.text((padding, 34), str(card.get("name", "")).encode("ascii", "ignore").decode("ascii") or "place", fill=(95, 105, 115))
    for index, image in enumerate(images):
        column = index % columns
        row = index // columns
        x = padding + column * (thumb_width + padding)
        y = header_height + padding + row * (thumb_height + caption_height + padding)
        thumb = visual_review_thumbnail(image.get("present_path"), (thumb_width, thumb_height))
        canvas.paste(thumb, (x, y))
        caption = f"{image.get('image_file_name', '')}  {image.get('captured_at', '')}"
        draw.text((x, y + thumb_height + 7), caption[:64], fill=(55, 65, 75))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=88, optimize=True)


def visual_review_thumbnail(path: str | None, size: tuple[int, int]):
    from PIL import Image, ImageOps

    thumb_width, thumb_height = size
    if not path or not Path(path).exists():
        return Image.new("RGB", size, (235, 239, 244))
    with Image.open(path) as image:
        thumbnail = ImageOps.contain(image.convert("RGB"), size)
    background = Image.new("RGB", size, (245, 247, 250))
    x = (thumb_width - thumbnail.width) // 2
    y = (thumb_height - thumbnail.height) // 2
    background.paste(thumbnail, (x, y))
    return background


def export_visual_review_place_decision_csv(item: dict[str, Any], output_path: str | Path) -> dict[str, int]:
    rows = [visual_review_decision_csv_row(item, result) for result in item.get("field_results", [])]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=visual_review_decision_csv_fields())
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": len(rows)}


def merge_visual_review_decision_csvs(csv_dir: str | Path, output_path: str | Path) -> dict[str, int]:
    rows: list[dict[str, str]] = []
    for csv_path in sorted(Path(csv_dir).glob("*.csv")):
        rows.extend(read_visual_review_decision_rows(csv_path))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=visual_review_decision_csv_fields(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows([normalized_visual_review_decision_row(row) for row in rows])
    return {"files": len(list(Path(csv_dir).glob("*.csv"))), "rows": len(rows)}


def build_visual_review_packet_index(
    packet_items: list[dict[str, Any]],
    *,
    index_output: str | Path,
    generated_at: date,
) -> str:
    rows = "\n".join(visual_review_packet_index_row(item, index_output=index_output) for item in packet_items)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>로드뷰 시각 검수 패킷</title>
  <style>
    body {{ margin: 0; background: #f6f7f8; color: #17202a; font-family: Arial, "Noto Sans KR", sans-serif; }}
    header {{ padding: 24px 28px; background: #fff; border-bottom: 1px solid #d9dee5; }}
    h1 {{ margin: 0 0 6px; font-size: 26px; letter-spacing: 0; }}
    main {{ padding: 20px 28px 40px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }}
    article {{ border: 1px solid #d9dee5; border-radius: 8px; background: #fff; overflow: hidden; }}
    img {{ display: block; width: 100%; height: auto; background: #eef2f6; }}
    .body {{ padding: 12px; }}
    h2 {{ margin: 0 0 8px; font-size: 18px; letter-spacing: 0; }}
    a {{ color: #0f766e; text-decoration: none; }}
    .meta {{ color: #667085; font-size: 13px; }}
{image_lightbox_styles()}
  </style>
</head>
<body>
  <header>
    <h1>로드뷰 시각 검수 패킷</h1>
    <div class="meta">생성일 {escape_html(generated_at.isoformat())} · 장소별 이미지 묶음과 판정 파일</div>
  </header>
  <main>
    <div class="grid">
{rows}
    </div>
  </main>
  {image_lightbox_script()}
  {image_lightbox_html()}
</body>
</html>
"""


def visual_review_packet_index_row(item: dict[str, Any], *, index_output: str | Path) -> str:
    contact_href = html_asset_href(item.get("contact_sheet", ""), output_path=index_output)
    csv_href = html_asset_href(item.get("decision_csv", ""), output_path=index_output)
    caption = f"{item.get('place_name', '')} 이미지 묶음표"
    return f"""      <article>
        <a href="{escape_attr(contact_href)}" data-lightbox-image data-lightbox-caption="{escape_attr(caption)}"><img src="{escape_attr(contact_href)}" alt="{escape_attr(caption)}"></a>
        <div class="body">
          <h2>{escape_html(item.get("place_name", ""))}</h2>
          <div class="meta">{escape_html(item.get("card_id", ""))} · 이미지 {item.get("image_count", 0)}장 · 검수 항목 {item.get("field_count", 0)}개</div>
          <div><a href="{escape_attr(csv_href)}">장소별 판정 파일 열기</a></div>
        </div>
      </article>"""


def build_shareable_visual_review_package(
    sheet: dict[str, Any],
    *,
    package_dir: str | Path,
    provider_404_report: dict[str, Any] | None = None,
    generated_at: date | None = None,
    max_image_width: int = 1600,
) -> dict[str, Any]:
    package_path = Path(package_dir)
    assets_dir = package_path / "assets"
    csv_dir = package_path / "decisions_by_place"
    contact_dir = package_path / "contact_sheets"
    for directory in [assets_dir, csv_dir, contact_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    generated = generated_at or date.today()
    copied_images = copy_visual_review_package_images(sheet, assets_dir, max_width=max_image_width)
    package_sheet = visual_review_sheet_with_packaged_assets(sheet, assets_dir)
    export_visual_review_decision_csv(package_sheet, package_path / "roadview_visual_review_decisions.csv")
    packet_report = build_visual_review_packets(
        package_sheet,
        contact_sheet_dir=contact_dir,
        csv_dir=csv_dir,
        index_output=package_path / "packets.html",
        generated_at=generated,
    )
    share_index_html = build_roadview_visual_review_board_html(
        package_sheet,
        provider_404_report=provider_404_report,
        output_path=package_path / "index.html",
        generated_at=generated,
    ).replace(
        "원본 이미지는 로컬 <code>data/raw/roadview_images</code> 기준",
        "공유 패키지 <code>assets</code> 축소 이미지 기준",
    )
    write_text(share_index_html, package_path / "index.html")
    write_text(build_shareable_package_readme(generated), package_path / "README.md")
    return {
        "generated_at": generated.isoformat(),
        "package_dir": str(package_path).replace("\\", "/"),
        "index_output": str((package_path / "index.html")).replace("\\", "/"),
        "packet_index_output": str((package_path / "packets.html")).replace("\\", "/"),
        "master_decision_csv": str((package_path / "roadview_visual_review_decisions.csv")).replace("\\", "/"),
        "copied_image_count": copied_images,
        "total_places": len(package_sheet.get("items", [])),
        "packet_report": packet_report,
    }


def copy_visual_review_package_images(sheet: dict[str, Any], assets_dir: Path, *, max_width: int) -> int:
    from PIL import Image, ImageOps

    copied = 0
    seen: set[str] = set()
    for item in sheet.get("items", []):
        for image in item.get("review_image_samples", []):
            image_file_name = image.get("image_file_name", "")
            source = Path(image.get("present_path") or "")
            if not image_file_name or image_file_name in seen or not source.exists():
                continue
            target = assets_dir / f"{Path(image_file_name).stem}.jpg"
            with Image.open(source) as original:
                normalized = ImageOps.exif_transpose(original).convert("RGB")
                if normalized.width > max_width:
                    ratio = max_width / normalized.width
                    normalized = normalized.resize((max_width, int(normalized.height * ratio)))
                normalized.save(target, format="JPEG", quality=84, optimize=True)
            seen.add(image_file_name)
            copied += 1
    return copied


def visual_review_sheet_with_packaged_assets(sheet: dict[str, Any], assets_dir: Path) -> dict[str, Any]:
    package_sheet = json.loads(json.dumps(sheet, ensure_ascii=False))
    for item in package_sheet.get("items", []):
        for image in item.get("review_image_samples", []):
            image_file_name = image.get("image_file_name", "")
            if image_file_name:
                image["present_path"] = str((assets_dir / f"{Path(image_file_name).stem}.jpg")).replace("\\", "/")
    return package_sheet


def build_shareable_package_readme(generated_at: date) -> str:
    return f"""# 로드뷰 시각 검수 공유 패키지

생성일: {generated_at.isoformat()}

## 보는 방법

1. `index.html`을 브라우저로 연다.
2. 장소별 묶음으로 보려면 `packets.html`을 연다.
3. 상단 `난해 항목 확인 가이드`에서 자동 판정이 애매하게 본 이유와 확인 포인트를 먼저 본다.
4. 필터의 `난해 항목`을 눌러 사람이 먼저 봐야 할 48개 항목만 확인한다.
5. 각 항목에서 `자동 판정 승인`, `보류`, `이미지 부족`, `충돌` 버튼을 누르거나 직접 판정값을 선택한다.
6. 크롬 또는 엣지에서는 `판정 파일 연결`로 판정 파일을 선택하면 변경 사항을 같은 파일에 저장할 수 있다.
7. 파일 직접 저장이 안 되는 브라우저에서는 `판정 파일 내려받기`로 결과 파일을 내려받는다.

## 입력 규칙

- 자동 판정은 참고용이다. 서비스 반영에는 사용하지 않는다.
- 사람이 `확인됨`, `추가 확인`, `정보 충돌`, `근거 부족` 중 하나를 최종 판정으로 입력한다.
- 근거 이미지와 최종 메모는 버튼을 누르면 자동으로 채워지며, 필요하면 사람이 수정한다.
- 최종 검수자와 검수일을 입력한다.

이 패키지는 팀원 공유용 축소 이미지 패키지다. 고해상도 원본 이미지는 포함하지 않는다.
검수 화면은 브라우저 임시저장도 사용한다. 최종 회수 파일은 판정 파일이다.
서비스 반영은 사람이 최종 판정을 입력한 항목만 대상으로 한다.
"""


def validate_visual_review_share_package(
    *,
    package_dir: str | Path,
    zip_path: str | Path,
    expected_assets: int = 102,
    expected_contact_sheets: int = 17,
    expected_place_csvs: int = 17,
    generated_at: date | None = None,
) -> dict[str, Any]:
    package_path = Path(package_dir)
    zip_file = Path(zip_path)
    checks = [
        package_validation_check("package_dir_exists", package_path.exists(), str(package_path)),
        package_validation_check("index_exists", (package_path / "index.html").exists(), "index.html"),
        package_validation_check("packets_exists", (package_path / "packets.html").exists(), "packets.html"),
        package_validation_check("readme_exists", (package_path / "README.md").exists(), "README.md"),
        package_validation_check(
            "master_csv_exists",
            (package_path / "roadview_visual_review_decisions.csv").exists(),
            "roadview_visual_review_decisions.csv",
        ),
    ]
    assets = list((package_path / "assets").glob("*.jpg"))
    contacts = list((package_path / "contact_sheets").glob("*.jpg"))
    csvs = list((package_path / "decisions_by_place").glob("*.csv"))
    master_csv = package_path / "roadview_visual_review_decisions.csv"
    checks.extend(
        [
            package_validation_check("asset_count", len(assets) == expected_assets, f"{len(assets)}/{expected_assets}"),
            package_validation_check(
                "contact_sheet_count",
                len(contacts) == expected_contact_sheets,
                f"{len(contacts)}/{expected_contact_sheets}",
            ),
            package_validation_check(
                "place_csv_count",
                len(csvs) == expected_place_csvs,
                f"{len(csvs)}/{expected_place_csvs}",
            ),
        ]
    )
    checks.append(package_validation_check("master_csv_columns", csv_has_visual_review_columns(master_csv), str(master_csv)))
    checks.append(
        package_validation_check(
            "place_csv_columns",
            all(csv_has_visual_review_columns(path) for path in csvs),
            f"{len(csvs)} files",
        )
    )
    forbidden_refs = forbidden_share_package_refs(package_path)
    checks.append(package_validation_check("no_local_path_refs", not forbidden_refs, "; ".join(forbidden_refs[:5])))
    zip_entries = zip_package_entries(zip_file)
    checks.extend(
        [
            package_validation_check("zip_exists", zip_file.exists(), str(zip_file)),
            package_validation_check("zip_has_index", "index.html" in zip_entries, "index.html"),
            package_validation_check("zip_has_assets", zip_entry_count(zip_entries, "assets/") == expected_assets, str(zip_entry_count(zip_entries, "assets/"))),
        ]
    )
    summary = {
        "total_checks": len(checks),
        "passed_checks": sum(1 for check in checks if check["status"] == "pass"),
        "failed_checks": sum(1 for check in checks if check["status"] == "fail"),
        "asset_count": len(assets),
        "contact_sheet_count": len(contacts),
        "place_csv_count": len(csvs),
        "zip_size_bytes": zip_file.stat().st_size if zip_file.exists() else 0,
        "zip_sha256": sha256_file(zip_file) if zip_file.exists() else "",
    }
    return {
        "generated_at": (generated_at or date.today()).isoformat(),
        "status": "pass" if summary["failed_checks"] == 0 else "fail",
        "package_dir": str(package_path).replace("\\", "/"),
        "zip_path": str(zip_file).replace("\\", "/"),
        "summary": summary,
        "checks": checks,
    }


def package_validation_check(check_id: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "check_id": check_id,
        "status": "pass" if passed else "fail",
        "detail": detail,
    }


def forbidden_share_package_refs(package_path: Path) -> list[str]:
    forbidden_patterns = ["file:///", "C:/", "C:\\", "data/raw/roadview_images", "../data"]
    refs = []
    for path in package_path.rglob("*"):
        if path.suffix.lower() not in {".html", ".md", ".csv"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in forbidden_patterns:
            if pattern in text:
                refs.append(f"{path.relative_to(package_path)}:{pattern}")
    return refs


def zip_package_entries(zip_path: Path) -> set[str]:
    if not zip_path.exists():
        return set()
    with zipfile.ZipFile(zip_path) as archive:
        return set(archive.namelist())


def zip_entry_count(entries: set[str], prefix: str) -> int:
    return sum(1 for entry in entries if entry.startswith(prefix) and not entry.endswith("/"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_has_visual_review_columns(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
    return set(visual_review_decision_csv_fields()).issubset(fieldnames)
