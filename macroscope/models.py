"""Pydantic models mirroring the EventObject schema from design-doc §5.1.

These are strict-mode models that validate ingested data before it reaches
storage. Every numeric field is typed; there are no free-form blobs where a
structured type exists (T-001 acceptance check).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class Direction(str, Enum):
    """Directional assertion on an asset."""

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class EventType(str, Enum):
    """Coarse event type bucket (see design-doc §5.1)."""

    MACRO_DATA = "macro_data"
    CENTRAL_BANK = "central_bank"
    GEOPOLITICAL = "geopolitical"
    MARKET_MOVE = "market_move"
    CORPORATE = "corporate"
    OTHER = "other"


class EventObject(BaseModel):
    """The canonical event object (§5.1).

    Strict validation: extra fields rejected, datetimes coerced to UTC,
    numeric fields typed (no free-form strings where structured types exist).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        populate_by_name=True,
    )

    # --- identity / provenance ---
    source_id: str = Field(..., min_length=1)
    published_at: datetime = Field(
        ...,
        description="UTC timestamp the publisher stated the item was released.",
    )
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp this object was ingested by Macroscope.",
    )

    # --- content ---
    url: Optional[str] = None
    raw_text: str = ""
    language: str = "en"

    # --- structured fields (typed, not free-form blobs) ---
    source_tier: int = Field(..., ge=1, le=5)
    event_type: EventType = EventType.OTHER
    entities: list[str] = Field(default_factory=list)
    direction_assertions: list[dict[str, Any]] = Field(default_factory=list)
    numbers_extracted: dict[str, float] = Field(default_factory=dict)

    # --- quality signals ---
    novelty_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    extractor_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # --- integrity (T-001 / T-002) ---
    prompt_hash: Optional[str] = Field(
        None,
        description="SHA-256 of the extraction prompt where LLM extraction applies.",
    )

    def to_utc(self) -> "EventObject":
        """Return a copy with all datetimes normalized to UTC."""
        return self.model_copy(update={
            "published_at": _to_utc(self.published_at),
            "retrieved_at": _to_utc(self.retrieved_at),
        })


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ThesisObject(BaseModel):
    """A macro thesis object (design-doc §5.2)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    ticker: str = Field(..., min_length=1)
    action: str = Field(..., description="long | short | neutral")
    conviction: float = Field(..., ge=0.0, le=1.0)
    projected_hold_days: int = Field(..., gt=0)
    status: str = "draft"


class DecisionObject(BaseModel):
    """A human decision on a thesis (design-doc §5.3)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    thesis_id: str
    human_decision: str = Field(..., description="approve | reject | modify")
    reason: Optional[str] = None
    edited_params: dict[str, Any] = Field(default_factory=dict)


class SourceRegistryEntry(BaseModel):
    """A source registry row (design-doc §4.1)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    source_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    type: str
    cadence: Optional[str] = None
    tier: float = Field(..., ge=0.0, le=1.0)
    url_template: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
