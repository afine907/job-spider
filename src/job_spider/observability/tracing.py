"""Simple tracing for request tracking."""

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generator


@dataclass
class Span:
    """A single span in a trace."""

    trace_id: str
    span_id: str
    name: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    duration_ms: float | None = None
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span.

        Args:
            name: Event name
            attributes: Event attributes
        """
        self.events.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "attributes": attributes or {},
        })

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute.

        Args:
            key: Attribute key
            value: Attribute value
        """
        self.attributes[key] = value

    def finish(self) -> None:
        """Mark the span as finished."""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000


class Tracer:
    """Simple tracer for distributed tracing."""

    def __init__(self, name: str = "job_spider"):
        """Initialize tracer.

        Args:
            name: Tracer name
        """
        self.name = name
        self._spans: list[Span] = []
        self._current_span: Span | None = None

    def generate_trace_id(self) -> str:
        """Generate a unique trace ID.

        Returns:
            UUID-based trace ID
        """
        return uuid.uuid4().hex[:16]

    def generate_span_id(self) -> str:
        """Generate a unique span ID.

        Returns:
            UUID-based span ID
        """
        return uuid.uuid4().hex[:8]

    @contextmanager
    def span(
        self,
        name: str,
        trace_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Span, None, None]:
        """Create a new span context manager.

        Args:
            name: Span name
            trace_id: Optional trace ID (will create new if not provided)
            attributes: Optional span attributes

        Yields:
            Span instance
        """
        parent_span = self._current_span

        span = Span(
            trace_id=trace_id or parent_span.trace_id if parent_span else self.generate_trace_id(),
            span_id=self.generate_span_id(),
            name=name,
            parent_span_id=parent_span.span_id if parent_span else None,
            attributes=attributes or {},
        )

        self._spans.append(span)
        self._current_span = span

        try:
            yield span
        finally:
            span.finish()
            self._current_span = parent_span

    def get_spans(self) -> list[Span]:
        """Get all recorded spans.

        Returns:
            List of spans
        """
        return self._spans.copy()

    def get_trace(self, trace_id: str) -> list[Span]:
        """Get all spans for a specific trace.

        Args:
            trace_id: Trace ID to filter by

        Returns:
            List of spans in the trace
        """
        return [s for s in self._spans if s.trace_id == trace_id]

    def export(self) -> list[dict[str, Any]]:
        """Export all spans as dictionaries.

        Returns:
            List of span dictionaries
        """
        return [
            {
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "name": span.name,
                "start_time": span.start_time.isoformat(),
                "end_time": span.end_time.isoformat() if span.end_time else None,
                "duration_ms": span.duration_ms,
                "attributes": span.attributes,
                "events": span.events,
            }
            for span in self._spans
        ]

    def clear(self) -> None:
        """Clear all recorded spans."""
        self._spans.clear()
        self._current_span = None
