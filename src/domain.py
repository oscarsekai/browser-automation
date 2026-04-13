
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional


@dataclass
class PostRecord:
    id: str
    source: str
    timestamp: datetime
    author: str
    handle: str
    text: str
    url: Optional[str] = None
    followers: Optional[int] = None
    raw_html: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['timestamp'] = self.timestamp.isoformat()
        return payload


@dataclass
class DroppedRecord:
    record: PostRecord
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {'record': self.record.to_dict(), 'reason': self.reason}


@dataclass
class FilterResult:
    kept: list[PostRecord]
    dropped: list[DroppedRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            'kept': [item.to_dict() for item in self.kept],
            'dropped': [item.to_dict() for item in self.dropped],
        }


@dataclass
class ScoredPost:
    record: PostRecord
    score: float
    tier: str
    reasons: tuple[str, ...] = ()
    breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'record': self.record.to_dict(),
            'score': self.score,
            'tier': self.tier,
            'reasons': list(self.reasons),
            'breakdown': self.breakdown,
        }


@dataclass
class SummaryBundle:
    generated_at: datetime
    sentences: list[str]
    top_picks: list[ScoredPost]
    secondary: list[ScoredPost]
    archive: list[ScoredPost]
    source_count: int
    raw_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            'generated_at': self.generated_at.isoformat(),
            'sentences': self.sentences,
            'top_picks': [item.to_dict() for item in self.top_picks],
            'secondary': [item.to_dict() for item in self.secondary],
            'archive': [item.to_dict() for item in self.archive],
            'source_count': self.source_count,
            'raw_count': self.raw_count,
        }
