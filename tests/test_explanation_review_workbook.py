from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from src.explanation_blind_review import build_blind_review_packet
from src.explanation_review_workbook import (
    ExplanationReviewWorkbookError,
    read_explanation_review_workbook,
    write_explanation_review_workbook,
)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "explanation_eval_results.json"
CASES = ROOT / "data" / "explanation_eval_cases.json"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class ExplanationReviewWorkbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packet = build_blind_review_packet(
            json.loads(RESULTS.read_text(encoding="utf-8")),
            seed="workbook-tests",
            cases=json.loads(CASES.read_text(encoding="utf-8")),
        )
        cls.master_rows = [dict(row) for row in packet["review_rows"]]
        cls.deblind_key = packet["deblind_key"]

    def test_blank_workbook_roundtrips_as_pending_with_locked_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review.xlsx"
            write_explanation_review_workbook(path, self.master_rows, reviewer_id="R01")

            rows = read_explanation_review_workbook(
                path, self.master_rows, expected_reviewer_id="R01"
            )

            self.assertEqual(len(rows), 30)
            self.assertTrue(all(row["reviewer_id"] == "R01" for row in rows))
            self.assertTrue(all(row["review_status"] == "pending" for row in rows))
            self.assertEqual(rows[0]["answer_a"], self.master_rows[0]["answer_a"])
            with zipfile.ZipFile(path) as package:
                review_xml = package.read("xl/worksheets/sheet1.xml")
                workbook_xml = package.read("xl/workbook.xml").decode("utf-8")
            self.assertIn(b"<sheetProtection", review_xml)
            self.assertIn(b"<dataValidations", review_xml)
            self.assertIn(b"<pane", review_xml)
            self.assertIn('name="_meta" sheetId="3" state="veryHidden"', workbook_xml)

    def test_completed_prefill_roundtrips_with_normalized_values(self):
        rows = self._completed_rows("R01")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "completed.xlsx"
            write_explanation_review_workbook(path, rows, reviewer_id="R01")

            extracted = read_explanation_review_workbook(
                path, self.master_rows, expected_reviewer_id="R01"
            )

            self.assertTrue(all(row["review_status"] == "complete" for row in extracted))
            self.assertTrue(all(row["reviewer_id"] == "R01" for row in extracted))
            self.assertEqual(extracted[0]["notes"], "독립 검토 완료")
            self.assertIn(extracted[0]["preference"], {"A", "B"})

    def test_reviewer_mismatch_and_immutable_answer_change_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review.xlsx"
            write_explanation_review_workbook(path, self.master_rows, reviewer_id="R01")
            with self.assertRaisesRegex(ExplanationReviewWorkbookError, "reviewer_id"):
                read_explanation_review_workbook(
                    path, self.master_rows, expected_reviewer_id="R02"
                )

            tampered = Path(temp_dir) / "tampered.xlsx"
            self._replace_sheet_cell(path, tampered, "D6", value="변조된 답변")
            with self.assertRaisesRegex(ExplanationReviewWorkbookError, "immutable"):
                read_explanation_review_workbook(
                    tampered, self.master_rows, expected_reviewer_id="R01"
                )

    def test_formula_in_editable_cell_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "review.xlsx"
            injected = Path(temp_dir) / "formula.xlsx"
            write_explanation_review_workbook(source, self.master_rows, reviewer_id="R01")
            self._replace_sheet_cell(source, injected, "E6", formula="1+1", value="2")

            with self.assertRaisesRegex(ExplanationReviewWorkbookError, "formula"):
                read_explanation_review_workbook(
                    injected, self.master_rows, expected_reviewer_id="R01"
                )

    def test_invalid_reviewer_and_non_xlsx_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.xlsx"
            with self.assertRaisesRegex(ExplanationReviewWorkbookError, "reviewer_id"):
                write_explanation_review_workbook(path, self.master_rows, reviewer_id="name@email")
            wrong = Path(temp_dir) / "bad.xls"
            wrong.write_bytes(b"not a workbook")
            with self.assertRaisesRegex(ExplanationReviewWorkbookError, "xlsx"):
                read_explanation_review_workbook(wrong, self.master_rows)

    def _completed_rows(self, reviewer_id: str) -> list[dict[str, str]]:
        assignments = {
            item["blind_id"]: item for item in self.deblind_key["assignments"]
        }
        rows = [dict(row) for row in self.master_rows]
        for row in rows:
            assignment = assignments[row["blind_id"]]
            for position in ("a", "b"):
                variant = assignment[f"answer_{position}_variant"]
                rating = "5" if variant == "after" else "4"
                row[f"answer_{position}_correctness_1_5"] = rating
                row[f"answer_{position}_understanding_1_5"] = rating
                row[f"answer_{position}_decision_help_1_5"] = rating
                row[f"answer_{position}_hallucination_yes_no"] = "no"
                row[f"answer_{position}_safety_issue_yes_no"] = "no"
                row[f"answer_{position}_previsit_clarity_yes_no"] = (
                    "yes" if row["previsit_applicable"] == "yes" else "n/a"
                )
            row["preference"] = "A" if assignment["answer_a_variant"] == "after" else "B"
            row["reviewer_id"] = reviewer_id
            row["review_status"] = "complete"
            row["notes"] = "독립 검토 완료"
        return rows

    @staticmethod
    def _replace_sheet_cell(
        source: Path,
        target: Path,
        reference: str,
        *,
        value: str,
        formula: str | None = None,
    ) -> None:
        with zipfile.ZipFile(source) as archive:
            parts = {item.filename: archive.read(item.filename) for item in archive.infolist()}
        root = ET.fromstring(parts["xl/worksheets/sheet1.xml"])
        cell = next(
            item for item in root.iter(f"{{{NS}}}c") if item.attrib.get("r") == reference
        )
        for child in list(cell):
            cell.remove(child)
        if formula is None:
            cell.attrib["t"] = "inlineStr"
            inline = ET.SubElement(cell, f"{{{NS}}}is")
            text = ET.SubElement(inline, f"{{{NS}}}t")
            text.text = value
        else:
            cell.attrib.pop("t", None)
            formula_node = ET.SubElement(cell, f"{{{NS}}}f")
            formula_node.text = formula
            value_node = ET.SubElement(cell, f"{{{NS}}}v")
            value_node.text = value
        parts["xl/worksheets/sheet1.xml"] = ET.tostring(
            root, encoding="utf-8", xml_declaration=True
        )
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in parts.items():
                archive.writestr(name, content)


if __name__ == "__main__":
    unittest.main()
