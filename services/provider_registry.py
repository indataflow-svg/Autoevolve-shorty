"""Provider registry: one declaration per enrichment tool, zero branching code.

Every supplier of data (Hunter, Apollo, Prospeo, PDL, Resend, Buffer, …)
registers once: what data points it supplies, which env keys prove it is
configured, how to call it, which errors mean "this provider failed, move
on", and how to validate it for connect. Consumers (fan-out research,
waterfalls, connect/sync) read the registry instead of hardcoding provider
lists or ``if provider ==`` branches, so adding a tool is one ``register()``
call.

Thunks close over module globals lazily so tests can patch
``sales_service.research_*`` freely: resolution happens at call time, never
at registration time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ProviderSpec:
    """Everything the product knows about one tool."""

    name: str
    label: str
    datapoints: frozenset[str] = frozenset()
    keys: tuple[str, ...] = ()
    auth: str = "api_key"  # or "oauth" (owned by services.oauth)
    sync: str = "pull"
    cost_weight: int = 1
    catalog: bool = True  # False: usable in flows, no connect card
    search_companies: Callable[..., list[dict[str, Any]]] | None = None
    error_types: tuple[type[BaseException], ...] = (Exception,)
    validate: Callable[[], tuple[bool, str]] | None = None
    sync_check: Callable[[], None] | None = None


_REGISTRY: dict[str, ProviderSpec] = {}


def register(spec: ProviderSpec) -> ProviderSpec:
    """Declare a provider. Registering twice replaces the entry (tests)."""
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> ProviderSpec | None:
    return _REGISTRY.get(name)


def providers_for(datapoint: str, order: list[str] | None = None) -> list[ProviderSpec]:
    """Specs supplying a data point, in explicit order or cost order."""
    matching = [spec for spec in _REGISTRY.values() if datapoint in spec.datapoints]
    if order is not None:
        wanted = [name for name in order if name in {spec.name for spec in matching}]
        return [spec for name in wanted for spec in matching if spec.name == name]
    return sorted(matching, key=lambda spec: (spec.cost_weight, spec.name))


def run_waterfall(
    steps: list[tuple[str, Callable[[], list[dict[str, Any]]], tuple[type[BaseException], ...]]],
    target: int | None,
    key_fn: Callable[[dict[str, Any]], str | None],
    warn_fn: Callable[[str, Exception], str],
) -> dict[str, Any]:
    """Query suppliers in order until `target` unique results are held.

    `target=None` tries every supplier (the audited fan-out); an int stops
    early once enough unique records are held, so later providers' credits
    are never spent. Each step is tried at most once: a hit appends new
    unique items, a miss or a failure moves on. The log records every step
    so a founder can see exactly which tool produced what.
    """
    results: list[dict[str, Any]] = []
    providers: dict[str, int] = {}
    warnings: list[str] = []
    log: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources: dict[str, list[str]] = {}

    for name, fetch, error_types in steps:
        if target is not None and len(results) >= target:
            log.append({"provider": name, "status": "skipped", "count": 0})
            continue
        try:
            items = fetch()
        except error_types as exc:
            # A known provider failure moves on with a note. Anything else
            # propagates: unexpected errors must surface, not launder.
            providers[name] = 0
            warnings.append(warn_fn(name, exc))
            log.append({"provider": name, "status": "error", "count": 0})
            continue
        fresh = 0
        for item in items or []:
            key = key_fn(item)
            if key is None:
                continue
            if name not in sources.setdefault(key, []):
                sources[key].append(name)
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
            fresh += 1
        providers[name] = len(items or [])
        warnings_note = f"{fresh} new" if fresh else "no new records"
        log.append({"provider": name, "status": "hit" if fresh else "miss", "count": len(items or [])})
        if not fresh:
            warnings.append(f"{name}: {warnings_note} (tried; moving on)")
    return {"results": results, "providers": providers, "warnings": warnings, "waterfall": log, "sources": sources}
