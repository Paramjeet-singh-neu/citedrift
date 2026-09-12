from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from citedrift.parse.blocks import answer_hash, assemble_answer
from citedrift.parse.refs import keep_references
from citedrift.parse.run import parse_all, resolve_aio_complete


class CompleteTests(unittest.TestCase):
    def test_field_false_is_skipped_source(self) -> None:
        complete, source = resolve_aio_complete(
            {"aio_complete": False, "error": None, "reference_count": 10}
        )
        self.assertFalse(complete)
        self.assertEqual(source, "field")

    def test_derived_from_error_and_count(self) -> None:
        complete, source = resolve_aio_complete({"error": None, "reference_count": 10})
        self.assertTrue(complete)
        self.assertEqual(source, "derived")
        complete, source = resolve_aio_complete(
            {"error": "timeout", "reference_count": 0}
        )
        self.assertFalse(complete)
        self.assertEqual(source, "derived")


class RefsTests(unittest.TestCase):
    def test_inline_keeps_titled_half(self) -> None:
        refs = [
            {"link": "https://a.example/x", "source": "a.example", "index": 0},
            {"link": "https://b.example/y", "source": "b.example", "index": 1},
            {
                "title": "A",
                "link": "https://a.example/x",
                "source": "A Site",
                "snippet": "sa",
                "index": 2,
            },
            {
                "title": "B",
                "link": "https://b.example/y",
                "source": "B Site",
                "snippet": "sb",
                "index": 3,
            },
        ]
        kept = keep_references(refs, "inline")
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["title"], "A")
        self.assertEqual(kept[1]["title"], "B")
        self.assertEqual(kept[0]["link"], "https://a.example/x")

    def test_expanded_untouched(self) -> None:
        refs = [
            {"title": "A", "link": "https://a.example/x", "source": "A", "index": 0},
            {"title": "B", "link": "https://b.example/y", "source": "B", "index": 1},
        ]
        kept = keep_references(refs, "expanded")
        self.assertEqual(kept, refs)


class AnswerTests(unittest.TestCase):
    def test_join_rule_and_stable_hash(self) -> None:
        blocks = [
            {"type": "paragraph", "snippet": " Intro. "},
            {"type": "heading", "snippet": "Heading"},
            {
                "type": "list",
                "list": [{"snippet": "one"}, {"snippet": "two"}],
            },
            {"type": "table", "snippet": "ignored"},
        ]
        with self.assertLogs("citedrift.parse", level="WARNING") as cm:
            text = assemble_answer(blocks)
        self.assertTrue(any("table" in m for m in cm.output))
        self.assertEqual(text, "Intro. \nHeading\none\ntwo")
        h1 = answer_hash(text)
        h2 = answer_hash(assemble_answer(blocks))
        self.assertEqual(h1, h2)
        self.assertEqual(h1, answer_hash("Intro. \nHeading\none\ntwo"))


class ParseAllTests(unittest.TestCase):
    def test_skips_incomplete_and_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            parsed = Path(tmp) / "parsed"
            run = raw / "20260101T000000Z"
            run.mkdir(parents=True)
            aio = {
                "ai_overview": {
                    "text_blocks": [{"type": "paragraph", "snippet": "hello"}],
                    "references": [
                        {"link": "https://a.example", "source": "a.example"},
                        {
                            "title": "A",
                            "link": "https://a.example",
                            "source": "A Site",
                            "snippet": "snip",
                        },
                    ],
                }
            }
            (run / "q1_main.json").write_text(json.dumps(aio), encoding="utf-8")
            (run / "manifest.jsonl").write_text(
                json.dumps(
                    {
                        "query_id": "q1",
                        "fetched_at": "2026-01-01T00:00:00Z",
                        "delivery_mode": "inline",
                        "reference_count": 2,
                        "error": None,
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "query_id": "q2",
                        "fetched_at": "2026-01-01T00:00:01Z",
                        "aio_complete": False,
                        "delivery_mode": "none",
                        "reference_count": 0,
                        "error": "timeout",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            stats = parse_all(raw, parsed)
            self.assertEqual(stats["runs"], 1)
            self.assertEqual(stats["observations"], 1)
            self.assertEqual(stats["citations"], 1)
            self.assertEqual(stats["skipped_incomplete"], 1)
            self.assertEqual(stats["derived"], 1)
            answers = [
                json.loads(line)
                for line in (parsed / "answers.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(answers[0]["aio_complete_source"], "derived")
            self.assertEqual(answers[0]["answer_text"], "hello")
            cites = [
                json.loads(line)
                for line in (parsed / "citations.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(cites[0]["position"], 0)
            self.assertEqual(cites[0]["title"], "A")


if __name__ == "__main__":
    unittest.main()
