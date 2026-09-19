import asyncio
import unittest
from unittest.mock import AsyncMock, patch


class ResearcherSplitTests(unittest.TestCase):
    def test_unwrap_search_url(self):
        from tools.research import unwrap_search_url

        self.assertEqual(
            unwrap_search_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F&rut=abc"),
            "https://example.com/",
        )
        self.assertEqual(unwrap_search_url("https://example.com/x"), "https://example.com/x")
        self.assertEqual(unwrap_search_url(""), "")

    def test_search_web_returns_direct_urls(self):
        import asyncio

        from tools.research import search_web

        async def fake_get(url, **kwargs):
            class FakeResponse:
                status_code = 200

                text = (
                    '<div class="result"><a class="result__a" '
                    'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=1">'
                    "Title</a><span class=\"result__snippet\">snip</span></div>"
                )

            return FakeResponse()

        async def run():
            with patch("tools.research.httpx.AsyncClient") as client_cls:
                client = AsyncMock()
                client.__aenter__.return_value = client
                client.get.side_effect = fake_get
                client_cls.return_value = client
                return await search_web("test")

        results = asyncio.run(run())
        self.assertEqual(results[0]["url"], "https://example.com/page")

    def test_gather_evidence_dedupes_and_caps(self):
        import agents.researcher as researcher

        async def fake_search(query):
            return [
                {"title": "A", "url": "https://example.com/a", "snippet": "s"},
                {"title": "B", "url": "https://example.com/a", "snippet": "s"},
                {"title": "C", "url": "https://example.com/b", "snippet": "s"},
            ]

        async def fake_read(url):
            return {"ok": True, "url": url, "title": "T", "text": "x" * 100}

        async def run():
            with patch.object(researcher, "search_web", side_effect=fake_search), \
                 patch.object(researcher, "read_web_page", side_effect=fake_read):
                return await researcher.gather_evidence(["q1", "q2"], max_pages=1)

        evidence = asyncio.run(run())
        self.assertEqual(len(evidence), 1)
        self.assertTrue(evidence[0]["url"].startswith("https://example.com/"))

    def test_gather_evidence_skips_failed_pages(self):
        import agents.researcher as researcher

        async def fake_search(query):
            return [{"title": "A", "url": "https://example.com/a", "snippet": "s"}]

        async def fake_read(url):
            return {"ok": False, "url": url, "text": "", "error": "blocked"}

        async def run():
            with patch.object(researcher, "search_web", side_effect=fake_search), \
                 patch.object(researcher, "read_web_page", side_effect=fake_read):
                return await researcher.gather_evidence(["q1"], max_pages=2)

        self.assertEqual(asyncio.run(run()), [])

    def test_search_plan_bounds(self):
        import agents.researcher as researcher

        with self.assertRaises(Exception):
            researcher.SearchPlan(queries=[])
        with self.assertRaises(Exception):
            researcher.SearchPlan(queries=["q"] * 9)
        plan = researcher.SearchPlan(queries=["a", "b", "c"])
        self.assertEqual(len(plan.queries), 3)
