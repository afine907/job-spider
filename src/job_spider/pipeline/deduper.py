"""Deduplication stage for removing duplicate job entries."""

import hashlib
from typing import AsyncIterator

from .base import PipelineStage, PipelineContext


class DedupStage(PipelineStage):
    """Remove duplicate job entries."""

    def __init__(self, fields: list[str] = None):
        """Initialize dedup stage.

        Args:
            fields: Fields to use for fingerprinting.
                    Default: ["job_id", "source"]
        """
        self.fields = fields or ["job_id", "source"]
        self.seen: set[str] = set()

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        """Filter out duplicate items."""
        async for item in items:
            fingerprint = self._fingerprint(item)

            if fingerprint not in self.seen:
                self.seen.add(fingerprint)
                yield item
                ctx.metrics["unique"] = ctx.metrics.get("unique", 0) + 1
            else:
                ctx.metrics["duplicates"] = ctx.metrics.get("duplicates", 0) + 1

    def _fingerprint(self, item: dict) -> str:
        """Generate unique fingerprint for an item.

        Args:
            item: Job item dict

        Returns:
            MD5 hash fingerprint
        """
        parts = []
        for field in self.fields:
            value = item.get(field, "")
            parts.append(str(value))

        key = "|".join(parts)
        return hashlib.md5(key.encode()).hexdigest()

    def reset(self):
        """Reset the seen set for a new crawl session."""
        self.seen.clear()
