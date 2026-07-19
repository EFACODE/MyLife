"""Retrieval-grounded query (T7.2).

Answers a question **only from the user's own data**, via least-privilege,
read-only **tools** that surface candidate evidence events. A grounded answer is
recorded as an ``InsightGenerated`` (T7.1, evidence enforced); when evidence is
insufficient the service **refuses** with a calibrated fallback — never a
fabricated claim. Rule-based; a model later slots in behind the same tools and
the evidence contract. See ``specs/domain/assistant/grounded-query.md``.
"""

import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from mylife.assistant.insight import Insight, InsightService
from mylife.core.events import EventBus, InProcessEventBus
from mylife.knowledge.models import DOCUMENT_INGESTED
from mylife.knowledge.retrieval import RetrievalService
from mylife.timeline import TimelineEvent, TimelineQueryFilter, TimelineQueryService

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "what",
        "did",
        "do",
        "does",
        "i",
        "my",
        "me",
        "the",
        "a",
        "an",
        "to",
        "on",
        "of",
        "in",
        "is",
        "are",
        "was",
        "were",
        "how",
        "much",
        "many",
        "for",
        "and",
        "or",
        "you",
    }
)
_MAX_EVENTS = 500
_TOP_K = 5
_MIN_SCORE = 0.1
_GENERATOR = "grounded-query-v1"
_REFUSAL = "I don't have enough evidence in your data to answer that yet."


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOPWORDS}


class EvidenceCandidate(BaseModel):
    """A candidate grounding event surfaced by a tool."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID
    score: float
    tool: str
    snippet: str


@runtime_checkable
class Tool(Protocol):
    """A read-only, user-scoped retriever of candidate evidence."""

    name: str

    def gather(
        self, session: Session, user_id: uuid.UUID, question: str
    ) -> list[EvidenceCandidate]:
        """Return scored candidate evidence for ``question`` from the user's data."""
        ...


def _payload_text(payload: Mapping[str, object]) -> str:
    return " ".join(
        str(value) for value in payload.values() if isinstance(value, str | int | float)
    )


class TimelineKeywordTool:
    """Scores the user's events by keyword overlap with the question."""

    name = "timeline-keyword"

    def gather(
        self, session: Session, user_id: uuid.UUID, question: str
    ) -> list[EvidenceCandidate]:
        q_tokens = _tokens(question)
        if not q_tokens:
            return []
        page = TimelineQueryService(session).query(
            TimelineQueryFilter(user_id=user_id, limit=_MAX_EVENTS)
        )
        candidates: list[EvidenceCandidate] = []
        for event in page.items:
            if event.event_type.startswith("assistant."):
                continue  # never ground on the assistant's own output
            e_tokens = _tokens(f"{event.event_type} {event.source} {_payload_text(event.payload)}")
            overlap = q_tokens & e_tokens
            if not overlap:
                continue
            score = len(overlap) / len(q_tokens)
            candidates.append(
                EvidenceCandidate(
                    event_id=event.event_id,
                    score=score,
                    tool=self.name,
                    snippet=self._snippet(event),
                )
            )
        return candidates

    @staticmethod
    def _snippet(event: TimelineEvent) -> str:
        return f"{event.event_type} from {event.source}"


class DocumentMemoryTool:
    """Scores the user's documents by semantic search (T6.3)."""

    name = "document-memory"

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus or InProcessEventBus()

    def gather(
        self, session: Session, user_id: uuid.UUID, question: str
    ) -> list[EvidenceCandidate]:
        if not _tokens(question):
            return []
        hits = RetrievalService(session, self._bus).search(user_id, question, limit=_TOP_K)
        if not hits:
            return []
        # Map each document to its DocumentIngested event (the evidence).
        ingest_events = TimelineQueryService(session).query(
            TimelineQueryFilter(
                user_id=user_id, event_types=(DOCUMENT_INGESTED,), limit=_MAX_EVENTS
            )
        )
        event_by_document = {
            str(event.payload.get("document_id")): event.event_id for event in ingest_events.items
        }
        candidates: list[EvidenceCandidate] = []
        for hit in hits:
            if hit.score <= 0.0:
                continue
            event_id = event_by_document.get(str(hit.document_id))
            if event_id is None:
                continue
            candidates.append(
                EvidenceCandidate(
                    event_id=event_id, score=hit.score, tool=self.name, snippet=hit.preview
                )
            )
        return candidates


_DEFAULT_TOOLS: list[Tool] = [TimelineKeywordTool(), DocumentMemoryTool()]


class Answer(BaseModel):
    """The outcome of a grounded query — a grounded insight or a refusal."""

    model_config = ConfigDict(frozen=True)

    grounded: bool
    answer: str
    insight: Insight | None
    tools_used: list[str]
    evidence_count: int


class AssistantQueryService:
    """Answers questions grounded in the user's own data — or refuses."""

    def __init__(self, session: Session, bus: EventBus, tools: list[Tool] | None = None) -> None:
        self._session = session
        self._bus = bus
        self._tools = tools if tools is not None else _DEFAULT_TOOLS

    def answer(
        self, user_id: uuid.UUID, question: str, *, now: datetime, correlation_id: str
    ) -> Answer:
        """Answer ``question`` from the user's data, or refuse if evidence is thin."""
        best: dict[uuid.UUID, EvidenceCandidate] = {}
        contributing: set[str] = set()
        for tool in self._tools:
            for candidate in tool.gather(self._session, user_id, question):
                current = best.get(candidate.event_id)
                if current is None or candidate.score > current.score:
                    best[candidate.event_id] = candidate
                contributing.add(candidate.tool)

        ranked = sorted(best.values(), key=lambda c: (-c.score, str(c.event_id)))[:_TOP_K]
        tool_names = [tool.name for tool in self._tools]
        if not ranked or ranked[0].score < _MIN_SCORE:
            return Answer(
                grounded=False,
                answer=_REFUSAL,
                insight=None,
                tools_used=tool_names,
                evidence_count=0,
            )

        confidence = min(1.0, sum(candidate.score for candidate in ranked) / _TOP_K)
        evidence = [candidate.event_id for candidate in ranked]
        used = sorted(contributing)
        claim = f"Found {len(ranked)} record(s) in your data relevant to: {question!r}."
        insight = InsightService(self._session, self._bus).generate(
            user_id,
            claim,
            f"Grounded by {', '.join(used)} over your own events.",
            evidence,
            confidence,
            "Rule-based keyword/similarity match over your own data; "
            "it reports what was found and is not professional advice.",
            next_safe_action="Review the cited events.",
            generator=_GENERATOR,
            now=now,
            correlation_id=correlation_id,
        )
        return Answer(
            grounded=True,
            answer=claim,
            insight=insight,
            tools_used=used,
            evidence_count=len(evidence),
        )
