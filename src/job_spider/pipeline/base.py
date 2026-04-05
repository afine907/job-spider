"""Pipeline base classes for data processing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Any


@dataclass
class PipelineContext:
    """Pipeline execution context."""
    task_id: str
    spider_name: str
    start_time: datetime = field(default_factory=datetime.now)
    metrics: dict[str, Any] = field(default_factory=dict)


class PipelineStage(ABC):
    """Abstract base class for pipeline stages."""

    @abstractmethod
    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        """Process items through this stage.

        Args:
            items: Async iterator of items to process
            ctx: Pipeline context

        Yields:
            Processed items
        """
        pass


class Pipeline:
    """Data processing pipeline."""

    def __init__(self):
        self.stages: list[PipelineStage] = []

    def add_stage(self, stage: PipelineStage) -> "Pipeline":
        """Add a processing stage.

        Args:
            stage: Stage to add

        Returns:
            Self for chaining
        """
        self.stages.append(stage)
        return self

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        """Process items through all stages.

        Args:
            items: Async iterator of items
            ctx: Pipeline context

        Yields:
            Processed items
        """
        current = items

        for stage in self.stages:
            current = stage.process(current, ctx)

        async for item in current:
            yield item
