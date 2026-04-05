"""Metrics collection for monitoring."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricValue:
    """A single metric value."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float | None = None


class MetricsCollector:
    """Simple metrics collector for spider operations."""

    def __init__(self):
        """Initialize metrics collector."""
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._labels: dict[str, dict[str, str]] = {}

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name
            value: Value to add
            labels: Optional labels
        """
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value
        if labels:
            self._labels[key] = labels

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge metric.

        Args:
            name: Metric name
            value: Value to set
            labels: Optional labels
        """
        key = self._make_key(name, labels)
        self._gauges[key] = value
        if labels:
            self._labels[key] = labels

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram value.

        Args:
            name: Metric name
            value: Value to record
            labels: Optional labels
        """
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        if labels:
            self._labels[key] = labels

    def timing(
        self,
        name: str,
        duration: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a timing value (alias for histogram).

        Args:
            name: Metric name
            duration: Duration in seconds
            labels: Optional labels
        """
        self.histogram(name, duration, labels)

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get counter value.

        Args:
            name: Metric name
            labels: Optional labels

        Returns:
            Counter value or 0
        """
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get gauge value.

        Args:
            name: Metric name
            labels: Optional labels

        Returns:
            Gauge value or 0
        """
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0)

    def get_histogram_stats(
        self, name: str, labels: dict[str, str] | None = None
    ) -> dict[str, float]:
        """Get histogram statistics.

        Args:
            name: Metric name
            labels: Optional labels

        Returns:
            Dict with min, max, avg, count
        """
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])

        if not values:
            return {"min": 0, "max": 0, "avg": 0, "count": 0}

        return {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "count": len(values),
        }

    def export(self) -> dict[str, Any]:
        """Export all metrics as a dictionary.

        Returns:
            Dict containing all metrics
        """
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: self.get_histogram_stats(k.split("|")[0])
                for k in self._histograms
            },
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._labels.clear()

    def _make_key(self, name: str, labels: dict[str, str] | None = None) -> str:
        """Create a unique key for a metric.

        Args:
            name: Metric name
            labels: Optional labels

        Returns:
            Unique key string
        """
        if not labels:
            return name

        label_str = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}|{label_str}"
