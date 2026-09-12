from __future__ import annotations

import unittest

from citedrift.normalize.url import canonicalize, is_resolvable, tld_class


class DistinctPairsTests(unittest.TestCase):
    """These must NOT collapse. Over-normalization hides real churn."""

    def test_path_case_preserved(self) -> None:
        a = canonicalize("https://example.com/Article")
        b = canonicalize("https://example.com/article")
        self.assertNotEqual(a, b)

    def test_content_id_params_distinct(self) -> None:
        a = canonicalize("https://example.com/a?id=1")
        b = canonicalize("https://example.com/a?id=2")
        self.assertNotEqual(a, b)

    def test_video_v_params_distinct(self) -> None:
        a = canonicalize("https://www.youtube.com/watch?v=abc")
        b = canonicalize("https://www.youtube.com/watch?v=xyz")
        self.assertNotEqual(a, b)


class RuleTests(unittest.TestCase):
    def test_lowercase_scheme_and_host(self) -> None:
        self.assertEqual(
            canonicalize("HTTPS://WWW.Example.COM/Path"),
            "https://example.com/Path",
        )

    def test_strip_www(self) -> None:
        self.assertEqual(
            canonicalize("https://www.cdc.gov/diabetes"),
            "https://cdc.gov/diabetes",
        )

    def test_drop_default_https_port(self) -> None:
        self.assertEqual(
            canonicalize("https://example.com:443/a"),
            "https://example.com/a",
        )

    def test_drop_default_http_port(self) -> None:
        self.assertEqual(
            canonicalize("http://example.com:80/a"),
            "http://example.com/a",
        )

    def test_drop_tracking_keep_id(self) -> None:
        self.assertEqual(
            canonicalize(
                "https://example.com/a?id=9&utm_source=x&gclid=1&fbclid=2"
                "&msclkid=3&ref=r&source=s&mc_cid=4"
            ),
            "https://example.com/a?id=9",
        )

    def test_unknown_param_kept(self) -> None:
        self.assertEqual(
            canonicalize("https://example.com/a?sid=keepme"),
            "https://example.com/a?sid=keepme",
        )

    def test_fragment_stripped(self) -> None:
        self.assertEqual(
            canonicalize("https://example.com/a#section"),
            canonicalize("https://example.com/a"),
        )

    def test_trailing_slash_stripped_except_host(self) -> None:
        self.assertEqual(canonicalize("https://example.com/a/"), "https://example.com/a")
        self.assertEqual(canonicalize("https://example.com/"), "https://example.com/")

    def test_amp_path_query_subdomain(self) -> None:
        self.assertEqual(
            canonicalize("https://example.com/foo/amp/bar"),
            "https://example.com/foo/bar",
        )
        self.assertEqual(
            canonicalize("https://example.com/a?amp=1&id=3"),
            "https://example.com/a?id=3",
        )
        self.assertEqual(
            canonicalize("https://amp.example.com/a"),
            "https://example.com/a",
        )


class TldAndGotoTests(unittest.TestCase):
    def test_tld_classes(self) -> None:
        self.assertEqual(tld_class("https://cdc.gov/x"), "gov")
        self.assertEqual(tld_class("https://harvard.edu/x"), "edu")
        self.assertEqual(tld_class("https://diabetes.org/x"), "org")
        self.assertEqual(tld_class("https://example.com/x"), "com")
        self.assertEqual(tld_class("https://example.io/x"), "com")
        self.assertEqual(tld_class("https://example.co.uk/x"), "intl")
        self.assertEqual(tld_class("https://example.org.au/x"), "intl")

    def test_google_goto_not_resolvable(self) -> None:
        link = "https://www.google.com/goto?url=CAES"
        self.assertFalse(is_resolvable(link))
        self.assertTrue(is_resolvable("https://www.mayoclinic.org/a"))
