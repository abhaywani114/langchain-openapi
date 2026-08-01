"""In-memory operation search index for the Generic HTTP Toolkit.

Enables agents to discover API endpoints on-demand instead of embedding an
entire OpenAPI specification into the prompt. Supports keyword search,
lightweight fuzzy matching, and tag / method filters. No external vector
database required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from langchain_openapi_tools.models import Operation

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Split ``text`` into lower-case alphanumeric tokens."""
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class OperationEntry:
    """Indexable projection of an :class:`Operation`.

    Attributes:
        canonical_id: Stable identifier used by discovery tools
            (``describe_operation`` etc.). Defaults to the operation's
            ``operation_id`` when available, else a snake-cased fallback.
        method: HTTP method in upper case (``GET``, ``POST`` ...).
        path: URL path template (e.g. ``/pets/{petId}``).
        summary: Short human-readable summary.
        description: Longer description.
        tags: OpenAPI tags associated with the operation.
        operation: The underlying :class:`Operation` object.
    """

    canonical_id: str
    method: str
    path: str
    summary: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    operation: Operation | None = None

    def haystack(self) -> str:
        """Concatenated searchable text used for scoring."""
        parts = [
            self.canonical_id,
            self.operation.operation_id or "" if self.operation else "",
            self.summary or "",
            self.description or "",
            self.path,
            self.method,
            " ".join(self.tags),
        ]
        return " ".join(p for p in parts if p)


@dataclass
class SearchResult:
    """A ranked operation match returned by :meth:`OperationIndex.search`."""

    entry: OperationEntry
    score: float

    @property
    def canonical_id(self) -> str:
        return self.entry.canonical_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.entry.canonical_id,
            "method": self.entry.method,
            "path": self.entry.path,
            "summary": self.entry.summary,
            "tags": list(self.entry.tags),
            "score": round(self.score, 4),
        }


class OperationIndex:
    """In-memory searchable index of parsed OpenAPI operations."""

    def __init__(self, operations: list[Operation]) -> None:
        self._entries: list[OperationEntry] = []
        self._by_id: dict[str, OperationEntry] = {}

        # Import lazily to avoid circular imports at module load time.
        from langchain_openapi_tools.toolkit import format_tool_name

        seen: set[str] = set()
        for op in operations:
            canonical = op.operation_id or format_tool_name(op)
            base = canonical
            counter = 2
            while canonical in seen:
                canonical = f"{base}_{counter}"
                counter += 1
            seen.add(canonical)

            entry = OperationEntry(
                canonical_id=canonical,
                method=op.method.value.upper(),
                path=op.path,
                summary=op.summary,
                description=op.description,
                tags=list(op.tags or []),
                operation=op,
            )
            self._entries.append(entry)

            # Register the canonical id and every alias we can compute so
            # lookup is forgiving to LLM output variations.
            self._by_id[canonical] = entry
            self._by_id[canonical.lower()] = entry
            if op.operation_id:
                self._by_id[op.operation_id] = entry
                self._by_id[op.operation_id.lower()] = entry
            self._by_id[format_tool_name(op)] = entry
            self._by_id[f"{entry.method} {entry.path}".lower()] = entry
            self._by_id[f"{entry.method}:{entry.path}".lower()] = entry

    # ------------------------------------------------------------------ API

    @property
    def entries(self) -> list[OperationEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, operation_id: str) -> OperationEntry | None:
        """Return an entry by canonical id, ``operationId``, or ``METHOD PATH``."""
        if not operation_id:
            return None
        if operation_id in self._by_id:
            return self._by_id[operation_id]
        return self._by_id.get(operation_id.lower())

    def list_entries(
        self,
        tag: str | None = None,
        method: str | None = None,
    ) -> list[OperationEntry]:
        """List operations, optionally filtered by tag and/or HTTP method."""
        result = self._entries
        if tag:
            tag_lower = tag.lower()
            result = [
                e for e in result if any(t.lower() == tag_lower for t in e.tags)
            ]
        if method:
            method_upper = method.upper()
            result = [e for e in result if e.method == method_upper]
        return list(result)

    def tags(self) -> list[str]:
        """Return the sorted set of unique tags across all operations."""
        seen: set[str] = set()
        for entry in self._entries:
            for tag in entry.tags:
                seen.add(tag)
        return sorted(seen)

    def search(
        self,
        query: str,
        limit: int = 10,
        method: str | None = None,
        tag: str | None = None,
    ) -> list[SearchResult]:
        """Rank operations by relevance to ``query``.

        The scoring combines three signals:

        1. **Substring** — full query appearing verbatim inside the
           operation id / summary / path.
        2. **Token overlap** — how many query tokens appear anywhere in the
           entry's haystack.
        3. **Fuzzy ratio** — ``difflib.SequenceMatcher`` against the
           haystack, providing a semantic-friendly tiebreaker.
        """
        if not query or not query.strip():
            return []

        candidates = self.list_entries(tag=tag, method=method)
        query_lower = query.lower().strip()
        query_tokens = _tokenize(query_lower)

        scored: list[SearchResult] = []
        for entry in candidates:
            haystack = entry.haystack().lower()
            haystack_tokens = set(_tokenize(haystack))

            substring_score = 0.0
            if query_lower in haystack:
                substring_score = 1.0
                if query_lower in entry.canonical_id.lower():
                    substring_score += 0.5
                if entry.summary and query_lower in entry.summary.lower():
                    substring_score += 0.25

            overlap_hits = sum(
                1 for token in query_tokens if token in haystack_tokens
            )
            overlap_score = (
                overlap_hits / len(query_tokens) if query_tokens else 0.0
            )

            fuzzy_score = SequenceMatcher(None, query_lower, haystack).ratio()

            total = (
                (substring_score * 2.0)
                + (overlap_score * 1.5)
                + (fuzzy_score * 0.5)
            )

            if total <= 0:
                continue
            scored.append(SearchResult(entry=entry, score=total))

        scored.sort(key=lambda r: (-r.score, r.entry.canonical_id))
        return scored[: max(0, limit)]


__all__ = [
    "OperationEntry",
    "OperationIndex",
    "SearchResult",
]
