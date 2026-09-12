from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from citedrift.collect.run import collect_one, load_queries, runner_label, top_level_aio
from citedrift.collect.serpapi import SEARCH_CAP, SerpApiAdapter


class FakeAdapter:
    def __init__(
        self,
        main: dict,
        aio: dict | BaseException | None = None,
        *,
        search_cap: int = 30,
    ) -> None:
        self.main = main
        self.aio = aio
        self.search_cap = search_cap
        self.searches_used = 0

    def remaining(self) -> int:
        return self.search_cap - self.searches_used

    def google_search(self, query: str) -> dict:
        self.searches_used += 1
        return self.main

    def google_ai_overview(self, page_token: str) -> dict:
        self.searches_used += 1
        if isinstance(self.aio, BaseException):
            raise self.aio
        assert isinstance(self.aio, dict)
        return self.aio


class CollectorLogicTests(unittest.TestCase):
    def test_queries_json_has_twelve_ids(self) -> None:
        queries = load_queries()
        self.assertEqual(len(queries), 12)
        self.assertEqual(queries[0]["id"], "t2d_symptoms")

    def test_ignores_related_questions_aio(self) -> None:
        payload = {
            "related_questions": [{"ai_overview": {"references": [{"link": "x"}]}}],
        }
        self.assertIsNone(top_level_aio(payload))

    def test_inline_delivery(self) -> None:
        adapter = FakeAdapter(
            {"ai_overview": {"references": [{"index": 0, "link": "https://a.example"}]}}
        )
        with tempfile.TemporaryDirectory() as tmp:
            row = collect_one(
                adapter,  # type: ignore[arg-type]
                {"id": "q1", "text": "hello"},
                Path(tmp),
            )
        self.assertTrue(row["aio_present"])
        self.assertTrue(row["aio_complete"])
        self.assertEqual(row["delivery_mode"], "inline")
        self.assertEqual(row["reference_count"], 1)
        self.assertEqual(row["searches_used"], 1)
        self.assertIsNone(row["error"])
        self.assertEqual(row["runner"], "local")

    def test_inline_without_refs_sets_error(self) -> None:
        adapter = FakeAdapter({"ai_overview": {"text_blocks": [{"snippet": "x"}]}})
        with tempfile.TemporaryDirectory() as tmp:
            row = collect_one(
                adapter,  # type: ignore[arg-type]
                {"id": "q1", "text": "hello"},
                Path(tmp),
            )
        self.assertTrue(row["aio_present"])
        self.assertFalse(row["aio_complete"])
        self.assertEqual(row["delivery_mode"], "inline")
        self.assertEqual(row["reference_count"], 0)
        self.assertEqual(row["error"], "aio_without_references")

    def test_expanded_delivery(self) -> None:
        adapter = FakeAdapter(
            {"ai_overview": {"page_token": "tok"}},
            {"ai_overview": {"references": [{}, {}]}},
        )
        with tempfile.TemporaryDirectory() as tmp:
            row = collect_one(
                adapter,  # type: ignore[arg-type]
                {"id": "q1", "text": "hello"},
                Path(tmp),
            )
            self.assertTrue((Path(tmp) / "q1_aio.json").is_file())
        self.assertEqual(row["delivery_mode"], "expanded")
        self.assertTrue(row["aio_present"])
        self.assertTrue(row["aio_complete"])
        self.assertEqual(row["reference_count"], 2)
        self.assertIsNone(row["error"])
        self.assertEqual(row["searches_used"], 2)

    def test_expanded_empty_is_none_with_error(self) -> None:
        adapter = FakeAdapter(
            {"ai_overview": {"page_token": "tok"}},
            {"ai_overview": {"text_blocks": []}},
        )
        with tempfile.TemporaryDirectory() as tmp:
            row = collect_one(
                adapter,  # type: ignore[arg-type]
                {"id": "q1", "text": "hello"},
                Path(tmp),
            )
        self.assertEqual(row["delivery_mode"], "none")
        self.assertTrue(row["aio_present"])
        self.assertFalse(row["aio_complete"])
        self.assertEqual(row["reference_count"], 0)
        self.assertEqual(row["error"], "expanded_aio_empty")

    def test_expanded_failure_is_none_with_error(self) -> None:
        adapter = FakeAdapter(
            {"ai_overview": {"page_token": "tok"}},
            RuntimeError("token expired"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            row = collect_one(
                adapter,  # type: ignore[arg-type]
                {"id": "q1", "text": "hello"},
                Path(tmp),
            )
        self.assertEqual(row["delivery_mode"], "none")
        self.assertTrue(row["aio_present"])
        self.assertFalse(row["aio_complete"])
        self.assertEqual(row["reference_count"], 0)
        self.assertEqual(row["error"], "token expired")

    def test_no_aio(self) -> None:
        adapter = FakeAdapter({"organic_results": []})
        with tempfile.TemporaryDirectory() as tmp:
            row = collect_one(
                adapter,  # type: ignore[arg-type]
                {"id": "q1", "text": "hello"},
                Path(tmp),
            )
        self.assertFalse(row["aio_present"])
        self.assertFalse(row["aio_complete"])
        self.assertEqual(row["delivery_mode"], "none")
        self.assertEqual(row["reference_count"], 0)
        self.assertIsNone(row["error"])

    def test_expand_timeout_keeps_aio_present(self) -> None:
        adapter = FakeAdapter(
            {"ai_overview": {"page_token": "tok"}},
            TimeoutError("The read operation timed out"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            row = collect_one(
                adapter,  # type: ignore[arg-type]
                {"id": "q1", "text": "hello"},
                Path(tmp),
            )
            self.assertTrue((Path(tmp) / "q1_main.json").is_file())
            self.assertFalse((Path(tmp) / "q1_aio.json").is_file())
        self.assertTrue(row["aio_present"])
        self.assertFalse(row["aio_complete"])
        self.assertEqual(row["delivery_mode"], "none")
        self.assertEqual(row["reference_count"], 0)
        self.assertIn("timed out", row["error"])

    def test_runner_actions_from_env(self) -> None:
        with patch.dict(os.environ, {"CITEDRIFT_RUNNER": "actions"}):
            self.assertEqual(runner_label(), "actions")
        with patch.dict(os.environ, {"CITEDRIFT_RUNNER": ""}, clear=False):
            os.environ.pop("CITEDRIFT_RUNNER", None)
            self.assertEqual(runner_label(), "local")


class CapTests(unittest.TestCase):
    def test_remaining_requires_two_to_start(self) -> None:
        adapter = SerpApiAdapter("fake", search_cap=5)
        adapter.searches_used = 4
        self.assertEqual(adapter.remaining(), 1)
        self.assertFalse(adapter.remaining() >= 2)
        adapter.searches_used = 3
        self.assertTrue(adapter.remaining() >= 2)

    def test_retry_counts_as_search(self) -> None:
        adapter = SerpApiAdapter("fake", search_cap=SEARCH_CAP)

        with patch("citedrift.collect.serpapi.time.sleep"), patch(
            "citedrift.collect.serpapi._https_get",
            side_effect=TimeoutError("The read operation timed out"),
        ):
            with self.assertRaises(RuntimeError):
                adapter.google_search("q")
        self.assertEqual(adapter.searches_used, 2)

    def test_expand_timeout_does_not_retry(self) -> None:
        adapter = SerpApiAdapter("fake", search_cap=SEARCH_CAP)
        with patch("citedrift.collect.serpapi.time.sleep") as slept, patch(
            "citedrift.collect.serpapi._https_get",
            side_effect=TimeoutError("The read operation timed out"),
        ):
            with self.assertRaises(RuntimeError):
                adapter.google_ai_overview("tok")
        slept.assert_not_called()
        self.assertEqual(adapter.searches_used, 1)


if __name__ == "__main__":
    unittest.main()
