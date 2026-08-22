"""Ingestion adapters for Macroscope (T-003).

One module per source. Each adapter returns a list of EventObjects with:
source_id, published_at (UTC publisher-stated), retrieved_at, url, raw_text,
language, source_tier, event_type enum, entities, direction_assertions,
numbers_extracted, novelty_score, extractor_confidence.

Structured feeds (#3,#5,#6,#7,#13) parse numeric fields from the feed directly —
the LLM handles narrative only (§5.2). No arithmetic in free-form text.
"""
