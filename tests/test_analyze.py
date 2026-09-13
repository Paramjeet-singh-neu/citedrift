from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from citedrift.analyze.jaccard import jaccard
from citedrift.analyze.rbo import rbo
from citedrift.analyze.run import analyze_all, classify_manifest_row
from citedrift.analyze.survival import survival_curve


class JaccardTests(unittest.TestCase):
    def test_identical(self) -> None:
        value, note = jaccard({"a", "b"}, {"a", "b"})
        self.assertEqual(value, 1.0)
        self.assertIsNone(note)

    def test_disjoint(self) -> None:
        value, note = jaccard({"a"}, {"b"})
        self.assertEqual(value, 0.0)
        self.assertIsNone(note)

    def test_partial(self) -> None:
        value, note = jaccard({"a", "b"}, {"a", "c"})
        self.assertEqual(value, 1 / 3)
        self.assertIsNone(note)

    def test_both_empty_is_null(self) -> None:
        value, note = jaccard(set(), set())
        self.assertIsNone(value)
        self.assertEqual(note, "both_empty")

    def test_one_empty_is_zero(self) -> None:
        value, note = jaccard({"a"}, set())
        self.assertEqual(value, 0.0)
        self.assertIsNone(note)


class RboTests(unittest.TestCase):
    def test_identical_is_one(self) -> None:
        value, note = rbo(["a", "b", "c"], ["a", "b", "c"])
        self.assertIsNone(note)
        assert value is not None
        self.assertAlmostEqual(value, 1.0, places=12)

    def test_unequal_length_prefix(self) -> None:
        value, note = rbo(["a", "b", "c"], ["a", "b"])
        self.assertIsNone(note)
        assert value is not None
        self.assertAlmostEqual(value, 1.0, places=12)

    def test_unequal_length_disagreement(self) -> None:
        value, note = rbo(["a", "b", "c"], ["a", "x"])
        self.assertIsNone(note)
        assert value is not None
        self.assertGreater(value, 0.0)
        self.assertLess(value, 1.0)
        shorter, _ = rbo(["a", "x"], ["a", "b", "c", "d"])
        longer, _ = rbo(["a", "b", "c"], ["a", "b", "c", "d"])
        assert shorter is not None and longer is not None
        self.assertGreater(longer, shorter)

    def test_disjoint_is_zero(self) -> None:
        value, note = rbo(["a", "b"], ["c", "d"])
        self.assertIsNone(note)
        self.assertEqual(value, 0.0)

    def test_both_empty_is_null(self) -> None:
        value, note = rbo([], [])
        self.assertIsNone(value)
        self.assertEqual(note, "both_empty")

    def test_one_empty_is_zero(self) -> None:
        value, note = rbo(["a"], [])
        self.assertEqual(value, 0.0)
        self.assertIsNone(note)

    def test_first_rank_swap(self) -> None:
        value, note = rbo(list("abcdefg"), list("bacdefg"))
        self.assertIsNone(note)
        assert value is not None
        self.assertAlmostEqual(value, 0.9, places=12)


class SurvivalTests(unittest.TestCase):
    def test_lag_and_n(self) -> None:
        runs = [{"a", "b"}, {"a"}, {"a", "c"}]
        curve = survival_curve(runs)
        self.assertEqual(curve[1]["n_pairs"], 2)
        self.assertEqual(curve[1]["n_instances"], 3)
        self.assertEqual(curve[1]["n_survived"], 2)
        self.assertEqual(curve[1]["rate"], 2 / 3)
        self.assertEqual(curve[2]["n_pairs"], 1)
        self.assertEqual(curve[2]["n_instances"], 2)
        self.assertEqual(curve[2]["rate"], 0.5)


class ClassifyTests(unittest.TestCase):
    def test_complete_field(self) -> None:
        self.assertEqual(
            classify_manifest_row({"aio_complete": True, "error": None, "reference_count": 4}),
            "complete",
        )

    def test_failed_fetch(self) -> None:
        self.assertEqual(
            classify_manifest_row({"aio_complete": False, "error": "timeout", "reference_count": 0}),
            "failed_fetch",
        )

    def test_genuine_absence_derived(self) -> None:
        self.assertEqual(
            classify_manifest_row({"error": None, "reference_count": 0}),
            "genuine_absence",
        )

    def test_complete_derived(self) -> None:
        self.assertEqual(
            classify_manifest_row({"error": None, "reference_count": 3}),
            "complete",
        )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class AnalyzeAllTests(unittest.TestCase):
    def test_presence_and_empty_jaccard_and_skip_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            parsed = root / "parsed"
            out = root / "analysis" / "metrics.json"
            queries = [
                {
                    "id": "q1",
                    "text": "t",
                    "condition": "c",
                    "journey_stage": "branded",
                    "audience": "patient",
                    "target_drug": "x",
                },
                {
                    "id": "q2",
                    "text": "t2",
                    "condition": "c",
                    "journey_stage": "symptoms",
                    "audience": "hcp",
                    "target_drug": None,
                },
                {
                    "id": "q3",
                    "text": "t3",
                    "condition": "c",
                    "journey_stage": "treatment",
                    "audience": "patient",
                    "target_drug": None,
                },
            ]
            (root / "queries.json").write_text(json.dumps(queries), encoding="utf-8")

            run_a = raw / "20260101T000000Z"
            run_b = raw / "20260102T000000Z"
            run_c = raw / "20260103T000000Z"
            run_a.mkdir(parents=True)
            run_b.mkdir(parents=True)
            run_c.mkdir(parents=True)
            _write_jsonl(
                run_a / "manifest.jsonl",
                [
                    {
                        "query_id": "q1",
                        "fetched_at": "2026-01-01T00:00:00Z",
                        "aio_complete": True,
                        "delivery_mode": "inline",
                        "reference_count": 2,
                        "error": None,
                    },
                    {
                        "query_id": "q2",
                        "fetched_at": "2026-01-01T00:00:01Z",
                        "error": None,
                        "reference_count": 0,
                        "delivery_mode": "none",
                    },
                    {
                        "query_id": "q3",
                        "fetched_at": "2026-01-01T00:00:02Z",
                        "aio_complete": True,
                        "delivery_mode": "inline",
                        "reference_count": 1,
                        "error": None,
                    },
                ],
            )
            _write_jsonl(
                run_b / "manifest.jsonl",
                [
                    {
                        "query_id": "q1",
                        "fetched_at": "2026-01-02T00:00:00Z",
                        "aio_complete": False,
                        "delivery_mode": "none",
                        "reference_count": 0,
                        "error": "timeout",
                    },
                    {
                        "query_id": "q2",
                        "fetched_at": "2026-01-02T00:00:01Z",
                        "aio_complete": True,
                        "delivery_mode": "expanded",
                        "reference_count": 1,
                        "error": None,
                    },
                    {
                        "query_id": "q3",
                        "fetched_at": "2026-01-02T00:00:02Z",
                        "aio_complete": True,
                        "delivery_mode": "inline",
                        "reference_count": 1,
                        "error": None,
                    },
                ],
            )
            _write_jsonl(
                run_c / "manifest.jsonl",
                [
                    {
                        "query_id": "q1",
                        "fetched_at": "2026-01-03T00:00:00Z",
                        "aio_complete": True,
                        "delivery_mode": "inline",
                        "reference_count": 0,
                        "error": None,
                    },
                    {
                        "query_id": "q2",
                        "fetched_at": "2026-01-03T00:00:01Z",
                        "aio_complete": True,
                        "delivery_mode": "expanded",
                        "reference_count": 1,
                        "error": None,
                    },
                ],
            )
            _write_jsonl(
                parsed / "answers.jsonl",
                [
                    {
                        "run_id": "20260101T000000Z",
                        "query_id": "q1",
                        "delivery_mode": "inline",
                        "fetched_at": "2026-01-01T00:00:00Z",
                    },
                    {
                        "run_id": "20260102T000000Z",
                        "query_id": "q2",
                        "delivery_mode": "expanded",
                        "fetched_at": "2026-01-02T00:00:01Z",
                    },
                    {
                        "run_id": "20260103T000000Z",
                        "query_id": "q1",
                        "delivery_mode": "inline",
                        "fetched_at": "2026-01-03T00:00:00Z",
                    },
                    {
                        "run_id": "20260103T000000Z",
                        "query_id": "q2",
                        "delivery_mode": "expanded",
                        "fetched_at": "2026-01-03T00:00:01Z",
                    },
                ],
            )
            _write_jsonl(
                parsed / "citations_normalized.jsonl",
                [
                    {
                        "run_id": "20260101T000000Z",
                        "query_id": "q1",
                        "position": 0,
                        "url_canonical": "https://a.example/x",
                        "domain": "a.example",
                        "source_class": "manufacturer",
                    },
                    {
                        "run_id": "20260101T000000Z",
                        "query_id": "q1",
                        "position": 1,
                        "url_canonical": "https://b.example/y",
                        "domain": "b.example",
                        "source_class": "gov_health",
                    },
                    {
                        "run_id": "20260102T000000Z",
                        "query_id": "q2",
                        "position": 0,
                        "url_canonical": "https://c.example/z",
                        "domain": "c.example",
                        "source_class": "advocacy",
                    },
                    {
                        "run_id": "20260103T000000Z",
                        "query_id": "q2",
                        "position": 0,
                        "url_canonical": "https://c.example/z",
                        "domain": "c.example",
                        "source_class": "advocacy",
                    },
                    {
                        "run_id": "20260103T000000Z",
                        "query_id": "q2",
                        "position": 1,
                        "url_canonical": "https://d.example/w",
                        "domain": "d.example",
                        "source_class": "advocacy",
                    },
                ],
            )
            metrics = analyze_all(
                raw_root=raw,
                citations_path=parsed / "citations_normalized.jsonl",
                answers_path=parsed / "answers.jsonl",
                queries_path=root / "queries.json",
                out_path=out,
            )
            p1 = metrics["aio_presence"]["by_query"]["q1"]
            self.assertEqual(p1["runs_attempted"], 3)
            self.assertEqual(p1["runs_with_complete_aio"], 2)
            self.assertEqual(p1["runs_failed_fetch"], 1)
            self.assertEqual(p1["runs_genuine_absence"], 0)
            p2 = metrics["aio_presence"]["by_query"]["q2"]
            self.assertEqual(p2["runs_attempted"], 3)
            self.assertEqual(p2["runs_with_complete_aio"], 2)
            self.assertEqual(p2["runs_failed_fetch"], 0)
            self.assertEqual(p2["runs_genuine_absence"], 1)

            q1_pairs = metrics["jaccard"]["url_canonical"]["by_query"]["q1"]["pairs"]
            self.assertEqual(len(q1_pairs), 1)
            self.assertEqual(q1_pairs[0]["run_id_a"], "20260101T000000Z")
            self.assertEqual(q1_pairs[0]["run_id_b"], "20260103T000000Z")
            self.assertEqual(q1_pairs[0]["jaccard"], 0.0)
            self.assertIsNone(q1_pairs[0]["jaccard_note"])

            q3_pairs = metrics["jaccard"]["url_canonical"]["by_query"]["q3"]["pairs"]
            self.assertEqual(len(q3_pairs), 1)
            self.assertIsNone(q3_pairs[0]["jaccard"])
            self.assertEqual(q3_pairs[0]["jaccard_note"], "both_empty")
            self.assertEqual(metrics["jaccard"]["url_canonical"]["by_query"]["q3"]["n_null_excluded"], 1)
            self.assertEqual(metrics["jaccard"]["url_canonical"]["n_null_excluded"], 1)

            q2_pairs = metrics["jaccard"]["url_canonical"]["by_query"]["q2"]["pairs"]
            self.assertEqual(len(q2_pairs), 1)
            self.assertEqual(q2_pairs[0]["jaccard"], 0.5)

            man = metrics["manufacturer_presence"]["q1"]
            self.assertTrue(man["any_manufacturer"])
            self.assertEqual(man["n_manufacturer"], 1)

            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(written["n_answers"], 4)


if __name__ == "__main__":
    unittest.main()
