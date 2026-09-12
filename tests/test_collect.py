from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from citedrift.collect.run import collect_one, load_queries, top_level_aio
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
        self.assertEqual(row["delivery_mode"], "inline")
        self.assertEqual(row["reference_count"], 1)
        self.assertEqual(row["searches_used"], 1)
        self.assertIsNone(row["error"])

    def test_inline_without_refs_sets_error(self) -> None:
        adapter = FakeAdapter({"ai_overview": {"text_blocks": [{"snippet": "x"}]}})
        with tempfile.TemporaryDirectory() as tmp:
            row = collect_one(
                adapter,  # type: ignore[arg-type]
                {"id": "q1", "text": "hello"},
                Path(tmp),
            )
        self.assertTrue(row["aio_present"])
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
        self.assertEqual(row["delivery_mode"], "none")
        self.assertEqual(row["reference_count"], 0)
        self.assertIsNone(row["error"])


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
        err = __import__("urllib.error").error.URLError("down")

        def boom(*_args, **_kwargs):
            raise err

        with patch("citedrift.collect.serpapi.time.sleep"), patch(
            "citedrift.collect.serpapi.urllib.request.urlopen",
            side_effect=boom,
        ):
            with self.assertRaises(RuntimeError):
                adapter.google_search("q")
        self.assertEqual(adapter.searches_used, 2)


if __name__ == "__main__":
    unittest.main()
