"""Bulk world-data ingest: free public sources -> core.worlddata_store.

EDGAR tickers and Common Crawl need no key. Companies House needs
COMPANIES_HOUSE_API_KEY and is skipped with a note when absent.

Usage:
    .venv/bin/python scripts/ingest_worlddata.py --sources edgar,commoncrawl \
        --domains autoevolve.site,safaricom.co.ke --edgar-limit 10000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import worlddata_store  # noqa: E402


def ingest_edgar(limit: int) -> int:
    from services.worlddata import edgar

    records = edgar.ingest(limit=limit)
    for record in records:
        worlddata_store.upsert_record(
            record["source"], record["kind"], record["ref"],
            record["name"], record["data"], record["vintage"])
    return len(records)


def ingest_commoncrawl(domains: list[str]) -> tuple[int, str]:
    from services.worlddata import commoncrawl

    records = commoncrawl.ingest(domains)
    for record in records:
        worlddata_store.upsert_record(
            record["source"], record["kind"], record["ref"],
            record["name"], record["data"], record["vintage"])
    crawl = records[0]["vintage"] if records else commoncrawl.latest_crawl_id()
    return len(records), crawl


def ingest_companieshouse(queries: list[str]) -> int:
    from services.worlddata import companieshouse

    records = companieshouse.ingest(queries)
    for record in records:
        worlddata_store.upsert_record(
            record["source"], record["kind"], record["ref"],
            record["name"], record["data"], record["vintage"])
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default="edgar,commoncrawl",
                        help="comma list: edgar,commoncrawl,companieshouse")
    parser.add_argument("--edgar-limit", type=int, default=10000)
    parser.add_argument("--domains", default="",
                        help="comma-separated domains for Common Crawl presence")
    parser.add_argument("--companies", default="",
                        help="comma-separated names for Companies House search")
    args = parser.parse_args(argv)
    worlddata_store.init_worlddata_db()

    wanted = {s.strip().lower() for s in args.sources.split(",") if s.strip()}
    if "edgar" in wanted:
        try:
            count = ingest_edgar(args.edgar_limit)
            print(f"edgar: {count} listed companies stored")
        except Exception as exc:
            print(f"edgar: skipped ({exc})")
    if "commoncrawl" in wanted:
        domains = [d.strip() for d in args.domains.split(",") if d.strip()]
        if not domains:
            print("commoncrawl: skipped (no --domains given)")
        else:
            try:
                count, crawl = ingest_commoncrawl(domains)
                print(f"commoncrawl: {count}/{len(domains)} domains seen in {crawl}")
            except Exception as exc:
                print(f"commoncrawl: skipped ({exc})")
    if "companieshouse" in wanted:
        queries = [q.strip() for q in args.companies.split(",") if q.strip()]
        if not queries:
            print("companieshouse: skipped (no --companies given)")
        else:
            try:
                count = ingest_companieshouse(queries)
                print(f"companieshouse: {count} registered companies stored")
            except Exception as exc:
                print(f"companieshouse: skipped ({exc})")
    summary = worlddata_store.sources_summary()
    print(f"world store: {summary['records']} records across {len(summary['sources'])} source(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
