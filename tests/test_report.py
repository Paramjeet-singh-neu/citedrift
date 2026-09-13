from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from citedrift.collect.serpapi import GL, HL, LOCATION
from citedrift.report.run import cadence_cron, render_html, report_all
from citedrift.report.svg import stacked_percent


ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "data" / "analysis" / "metrics.json"
QUERIES = ROOT / "config" / "queries.json"

EXTERNAL = re.compile(
    r"""(?is)(?:src|href)\s*=\s*['"]https?:|@import|url\(\s*['"]?https?:"""
)


def _render() -> str:
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))
    return render_html(metrics, queries, "0 14 * * *")


class SvgTests(unittest.TestCase):
    def test_stacked_includes_n(self) -> None:
        svg = stacked_percent(
            [("symptoms", 4, {"gov_health": 3, "video": 1})],
            title="test chart",
            n=4,
        )
        self.assertIn("<svg", svg)
        self.assertIn("n=4", svg)
        self.assertNotIn("gradient", svg.lower())


class CadenceTests(unittest.TestCase):
    def test_reads_cron(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "collect.yml"
            path.write_text('on:\n  schedule:\n    - cron: "0 14 * * *"\n', encoding="utf-8")
            self.assertEqual(cadence_cron(path), "0 14 * * *")

    def test_missing_file(self) -> None:
        self.assertIsNone(cadence_cron(Path("/no/such/workflow.yml")))


class ReportHtmlTests(unittest.TestCase):
    def test_sections_and_n(self) -> None:
        html = _render()
        for heading in (
            "1. Method",
            "2. AI Overview presence",
            "3. Authority composition by journey stage",
            "4. Patient vs HCP",
            "5. Citation stability",
            "6. Manufacturer presence on branded queries",
            "7. Limitations",
        ):
            self.assertIn(heading, html)
        self.assertNotIn("Citation stability by audience", html)
        self.assertIn("n=273", html)
        self.assertIn("n=105", html)
        self.assertIn("runs_genuine_absence", html)
        self.assertIn("runs_failed_fetch", html)
        self.assertIn("complete_fetch_rate", html)
        self.assertNotIn(">presence_rate<", html)
        self.assertIn("runs_genuine_absence summed across queries: 0", html)
        self.assertIn("Patient-only", html)
        self.assertIn("All queries (patient + HCP)", html)
        self.assertIn("Position concentration", html)
        self.assertIn("interval_minutes", html)
        self.assertIn("source_class by audience", html)
        self.assertEqual(html.count("jaccard url_canonical"), 1)
        self.assertEqual(html.count("rbo url_canonical"), 1)
        self.assertIn("Three things stand out in the data so far.", html)
        self.assertIn("config/source_classes.json", html)
        self.assertIn("The current window is hours, not weeks.", html)
        self.assertIn(LOCATION, html)
        self.assertIn(HL, html)
        self.assertIn(GL, html)
        self.assertIn("0 14 * * *", html)
        self.assertIn("configuration", html.lower())
        self.assertNotIn("only ones that moved", html.lower())
        self.assertNotIn("recommend", html.lower())
        self.assertIn("<svg", html)
        self.assertIn("jaccard url_canonical", html)
        self.assertIn("jaccard domain", html)
        self.assertIn("rbo url_canonical", html)
        self.assertIn("rbo domain", html)

    def test_self_contained(self) -> None:
        html = _render()
        self.assertIsNone(EXTERNAL.search(html))
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("<link", html.lower())
        self.assertIn("<style>", html)

    def test_presence_numbers_from_metrics(self) -> None:
        html = _render()
        self.assertIn("t2d_hcp", html)
        self.assertRegex(html, r"t2d_hcp</td><td class=\"num\">3</td>")

    def test_report_all_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.html"
            path = report_all(out_path=out)
            self.assertEqual(path, out)
            text = out.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("<!DOCTYPE html>"))
            self.assertIn("CiteDrift", text)


    def test_one_pair_table_has_interval_and_audience(self) -> None:
        html = _render()
        self.assertIn("interval_minutes", html)
        self.assertRegex(html, r"t2d_hcp</td><td>20260912T021246Z</td><td>20260912T033438Z</td><td>hcp</td>")
        self.assertIn("by_audience HCP", html)


if __name__ == "__main__":
    unittest.main()
