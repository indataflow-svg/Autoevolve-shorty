from pathlib import Path

import asyncio

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from core.models import cloud_model
from tools.research import search_web, fetch_page, unwrap_search_url


PROMPT = (
    Path(__file__).parent.parent
    / "prompts"
    / "researcher.md"
).read_text()


class Source(BaseModel):
    title: str
    url: str
    supports: str


class ResearchReport(BaseModel):
    title: str
    executive_summary: str

    problem: str

    target_users: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)

    verified_findings: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)

    technical_requirements: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)

    recommended_mvp: list[str] = Field(default_factory=list)

    sources: list[Source] = Field(default_factory=list)

    decision: str
    decision_reason: str


research_agent = Agent(
    cloud_model("reasoning"),
    instructions=PROMPT,
    output_type=ResearchReport,
)


class SearchPlan(BaseModel):
    """Planner output: bounded fan-out of focused queries (cheap fast model)."""

    queries: list[str] = Field(min_length=1, max_length=8)


planner_agent = Agent(
    cloud_model("fast"),
    instructions=(
        "You plan web research. Given a question, produce 3 to 6 focused search "
        "queries covering: the core claim, counter-evidence that could invalidate it, "
        "and authoritative sources (regulators, official docs, standards bodies). "
        "Prefer specific queries over broad ones. No tools, output queries only."
    ),
    output_type=SearchPlan,
)


synthesis_agent = Agent(
    cloud_model("reasoning"),
    instructions=PROMPT,
    output_type=ResearchReport,
)


async def plan_queries(question: str) -> list[str]:
    """Stage 1 (planner): cheap fast-model query fan-out."""
    result = await planner_agent.run(f"Plan search queries for:\n\n{question}")
    queries = [q.strip() for q in result.output.queries if q.strip()]
    return queries[:8] or [question]


async def gather_evidence(queries: list[str], max_pages: int = 8) -> list[dict]:
    """Stage 2 (reader/verifier): no-LLM fetch + verify. Latency tail lives here."""
    semaphore = asyncio.Semaphore(4)
    seen_urls: set[str] = set()
    evidence: list[dict] = []

    async def _search(query: str) -> list[dict]:
        try:
            return await search_web(query)
        except Exception:
            return []
    search_results = await asyncio.gather(*[_search(q) for q in queries[:8]])

    candidates: list[str] = []
    for results in search_results:
        for item in results or []:
            url = unwrap_search_url((item.get("url") or "").strip())
            if url and url not in seen_urls:
                seen_urls.add(url)
                candidates.append(url)
            if len(candidates) >= max_pages * 2:
                break

    async def _read(url: str) -> dict:
        async with semaphore:
            try:
                return await read_web_page(url)
            except Exception as exc:
                return {"ok": False, "url": url, "text": "", "error": f"{type(exc).__name__}: {exc}"}

    pages = await asyncio.gather(*[_read(url) for url in candidates[: max_pages * 2]])
    for page in pages:
        if page.get("ok") and (page.get("text") or "").strip():
            evidence.append({
                "url": page.get("url"),
                "title": page.get("title", ""),
                "text": (page.get("text") or "")[:6000],
            })
        if len(evidence) >= max_pages:
            break
    return evidence


@research_agent.tool_plain
async def web_search(query: str) -> list[dict]:
    """
    Search the public web.

    Use multiple focused queries instead of one very broad query.

    Search-result snippets are discovery aids only.
    They must not be treated as verified evidence.

    If a search fails, continue with another query where possible.
    """
    return await search_web(query)


@research_agent.tool_plain
async def read_web_page(url: str) -> dict:
    """
    Read a source discovered during web research.

    The returned dictionary contains:

    - ok: whether the page was successfully read
    - url: final resolved URL
    - status_code: HTTP status code when available
    - title: extracted page title
    - content_type: response content type
    - text: extracted readable text
    - error: failure reason when ok=false

    IMPORTANT:

    A failed source is normal and MUST NOT stop the research task.

    If ok=true:
    - inspect the returned text
    - use the source as evidence only for claims actually supported by it
    - include the final returned URL in the report's sources

    If ok=false:
    - do not cite the source as verified evidence
    - do not retry the exact same URL repeatedly
    - search for another authoritative source covering the same claim
    - continue the research
    - if no reliable alternative can be found, record the issue under unknowns

    Search snippets alone are not evidence.

    A source must be successfully read before it can support a verified finding.

    PDF, blocked, stale, missing, timed-out, and unsupported sources may return
    ok=false. Treat these as recoverable research failures rather than agent errors.
    """
    result = await fetch_page(url)

    return {
        "ok": result.get("ok", False),
        "url": result.get("url", url),
        "status_code": result.get("status_code"),
        "title": result.get("title", ""),
        "content_type": result.get("content_type", ""),
        "text": result.get("text", ""),
        "error": result.get("error"),
    }


async def run_research(question: str) -> ResearchReport:
    """Orchestrates planner -> reader/verifier -> synthesizer.

    Contract preserved: web evidence required, snippets are not evidence,
    failures continue with alternatives, uncertainties go under unknowns.
    """
    queries = await plan_queries(question)
    evidence = await gather_evidence(queries)
    return await synthesize_report(question, evidence)


async def synthesize_report(question: str, evidence: list[dict]) -> ResearchReport:
    """Stage 3 (synthesizer): reasoning model over gathered evidence, no tools."""
    if evidence:
        evidence_block = "\n\n".join(
            f"SOURCE: {item.get('url')}\nTITLE: {item.get('title', '')}\n"
            f"{(item.get('text') or '')[:5000]}"
            for item in evidence
        )[:22000]
    else:
        evidence_block = ("No source could be read successfully. Treat every material "
                          "claim as unverified and record the gaps under unknowns.")
    prompt = f"""
Research this question:

{question}

Evidence was already gathered by the reader stage (below). Do NOT call web tools;
use only what each listed source supports.

Gathered evidence (already read, use only what each source supports):

{evidence_block}

For important claims:

1. Rely on the gathered evidence block above.
2. Prefer primary and authoritative sources.
3. Only treat claims as verified when the underlying source was successfully read.
4. Distinguish verified findings from inference.
5. Include successfully inspected source URLs in sources.
6. Explain what each source supports.

Prefer:

- government sources
- regulators
- official institutions
- official company documentation
- international organizations
- standards bodies
- academic and research institutions
- established industry publications
- reputable news organizations

Do not invent statistics.

Do not use search snippets as verified evidence.

If a source fails:
- continue the research
- search for an alternative
- do not crash or abandon the task

If a number or factual claim cannot be verified:
- do not guess
- place the uncertainty under unknowns

Actively search for evidence that could weaken or invalidate the proposed idea.

The final decision must be exactly one of:

Proceed
Proceed with conditions
Do not proceed
Need more research
"""

    result = await synthesis_agent.run(prompt)

    return result.output


# Legacy combined agent (planner + tools + synthesis in one loop). Kept for
# backwards compatibility; run_research() now uses the split pipeline above.
legacy_research_agent = research_agent
