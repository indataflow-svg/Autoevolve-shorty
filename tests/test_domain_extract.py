"""Bounded public website reads used by first-run company research."""

import asyncio
import socket
import unittest
from unittest.mock import patch

import httpx

from tools.domain_extract import (
    MAX_PAGE_BYTES,
    WebsiteUnavailableError,
    company_profile_from_evidence,
    extract_domain,
    normalize_domain_input,
)


PUBLIC_DNS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
PRIVATE_DNS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]


class DomainExtractTests(unittest.TestCase):
    def test_rejects_private_urls_and_dns(self):
        self.assertEqual(normalize_domain_input("http://www.example.com/about"), ("http://example.com", "example.com"))
        for value in ("http://127.0.0.1", "http://localhost", "https://studio.test", "https://user:pass@example.com", "https://example.com:8080"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_domain_input(value)
        with patch("socket.getaddrinfo", return_value=PRIVATE_DNS):
            with self.assertRaisesRegex(ValueError, "non-public"):
                asyncio.run(extract_domain("https://example.com"))
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("unavailable")):
            with self.assertRaises(WebsiteUnavailableError):
                asyncio.run(extract_domain("https://example.com"))

    def test_fetches_each_page_once_and_keeps_source(self):
        fetched = []

        def handle(request):
            fetched.append(str(request.url))
            if request.url.path == "/":
                return httpx.Response(200, headers={"content-type": "text/html"}, text=(
                    '<html><head><title>Example Studio</title><meta property="og:site_name" content="Example Studio">'
                    '<meta name="description" content="Example Studio builds practical operations software for growing teams.">'
                    '</head><body><a href="/about">About</a><a href="/pricing">Pricing</a></body></html>'
                ))
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<html><body><p>Our team builds operations tools.</p></body></html>")

        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS):
            evidence = asyncio.run(extract_domain("https://example.com", max_pages=2, transport=httpx.MockTransport(handle)))
        self.assertEqual(fetched, ["https://example.com", "https://example.com/about"])
        self.assertEqual(evidence["pages_crawled"], 2)
        profile = company_profile_from_evidence(evidence, "Example Studio")
        self.assertEqual(profile["sources"], [
            {"field": "name", "url": "https://example.com"},
            {"field": "description", "url": "https://example.com"},
        ])
        self.assertIn("practical operations software", profile["description"])

    def test_rejects_off_domain_redirect_and_oversized_page(self):
        requests = []

        def redirect(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS):
            result = asyncio.run(extract_domain("example.com", transport=httpx.MockTransport(redirect)))
        self.assertEqual(len(requests), 1)
        self.assertEqual(result["pages_ok"], 0)
        self.assertIn("outside its domain", result["pages"][0]["error"])

        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS):
            result = asyncio.run(extract_domain("example.com", transport=httpx.MockTransport(
                lambda request: httpx.Response(200, headers={"content-type": "text/html"}, content=b"a" * (MAX_PAGE_BYTES + 1))
            )))
        self.assertEqual(result["pages_ok"], 0)
        self.assertIn("fetch limit", result["pages"][0]["error"])


if __name__ == "__main__":
    unittest.main()
