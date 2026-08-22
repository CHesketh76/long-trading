"""Ingestion layer for Macroscope (T-003).

Read-only adapters that return EventObject-shaped rows into T-001's schema with
source-tier metadata baked in. Adapters are registered by source_id and loaded
from the source_registry table so tiers apply at write time.
"""
