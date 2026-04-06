"""Metrics collection for monitoring."""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator


@dataclass
class MetricValue:
    """A single metric value."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float | None = None


# Prometheus metric buckets for histograms
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)


class MetricsCollector:
    """Simple metrics collector for spider operations."""

    _instance: "MetricsCollector | None" = None

    def __new__(cls) -> "MetricsCollector":
        """Singleton pattern for global metrics collector."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._counters = {}
            cls._instance._gauges = {}
            cls._instance._histograms = {}
            cls._instance._labels = {}
            cls._instance._histogram_buckets = {}
        return cls._instance

    def __init__(self):
        """Initialize metrics collector."""
        # Skip re-initialization for singleton
        pass

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
        self._histogram_buckets.clear()

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

    @contextmanager
    def timeit(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> Generator[None, None, None]:
        """Context manager to time a block of code.

        Args:
            name: Metric name
            labels: Optional labels

        Example:
            >>> with collector.timeit("request_duration", {"spider": "boss"}):
            ...     # do something
        """
        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            self.timing(name, duration, labels)

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format.

        Returns:
            Prometheus formatted metrics string

        Example:
            >>> metrics = collector.export_prometheus()
            >>> print(metrics)
            # HELP job_spider_requests_total Total requests count
            # TYPE job_spider_requests_total counter
            job_spider_requests_total{spider="boss",status="success"} 100.0
        """
        lines: list[str] = []
        processed_names: set[str] = set()

        # Export counters
        for key, value in sorted(self._counters.items()):
            name = key.split("|")[0]
            labels = self._labels.get(key, {})
            label_str = self._format_labels(labels)

            if name not in processed_names:
                lines.append(f"# HELP {name} Total count")
                lines.append(f"# TYPE {name} counter")
                processed_names.add(name)

            lines.append(f"{name}{label_str} {value}")

        # Export gauges
        processed_names.clear()
        for key, value in sorted(self._gauges.items()):
            name = key.split("|")[0]
            labels = self._labels.get(key, {})
            label_str = self._format_labels(labels)

            if name not in processed_names:
                lines.append(f"# HELP {name} Current value")
                lines.append(f"# TYPE {name} gauge")
                processed_names.add(name)

            lines.append(f"{name}{label_str} {value}")

        # Export histograms
        processed_names.clear()
        for key, values in sorted(self._histograms.items()):
            name = key.split("|")[0]
            labels = self._labels.get(key, {})
            label_str = self._format_labels(labels)

            if name not in processed_names:
                lines.append(f"# HELP {name} Duration histogram")
                lines.append(f"# TYPE {name} histogram")
                processed_names.add(name)

            # Calculate histogram buckets
            buckets = self._calculate_buckets(values)
            count = len(values)
            total_sum = sum(values)

            for bucket_upper, bucket_count in buckets:
                bucket_label = self._format_labels({**labels, "le": str(bucket_upper)})
                lines.append(f"{name}_bucket{bucket_label} {bucket_count}")

            # +Inf bucket
            inf_label = self._format_labels({**labels, "le": "+Inf"})
            lines.append(f"{name}_bucket{inf_label} {count}")

            # Sum and count
            lines.append(f"{name}_sum{label_str} {total_sum}")
            lines.append(f"{name}_count{label_str} {count}")

        return "\n".join(lines) + "\n"

    def _format_labels(self, labels: dict[str, str]) -> str:
        """Format labels for Prometheus output.

        Args:
            labels: Label dictionary

        Returns:
            Formatted label string like {spider="boss",status="success"}
        """
        if not labels:
            return ""

        pairs = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ", ".join(pairs) + "}"

    def _calculate_buckets(self, values: list[float]) -> list[tuple[float, int]]:
        """Calculate histogram bucket counts.

        Args:
            values: List of observed values

        Returns:
            List of (bucket_upper_bound, cumulative_count) tuples
        """
        buckets = DEFAULT_BUCKETS
        result: list[tuple[float, int]] = []
        cumulative = 0

        sorted_values = sorted(values)
        value_idx = 0

        for bucket_upper in buckets:
            while value_idx < len(sorted_values) and sorted_values[value_idx] <= bucket_upper:
                cumulative += 1
                value_idx += 1
            result.append((bucket_upper, cumulative))

        return result


# Global metrics collector instance
metrics = MetricsCollector()


# Pre-defined spider metrics
class SpiderMetrics:
    """Pre-defined metrics for spider operations."""

    @staticmethod
    def record_request(
        spider: str,
        status: str,
        duration: float,
    ) -> None:
        """Record a spider request.

        Args:
            spider: Spider name
            status: Request status (success/failed)
            duration: Request duration in seconds
        """
        metrics.increment(
            "job_spider_requests_total",
            labels={"spider": spider, "status": status},
        )
        metrics.timing(
            "job_spider_request_duration_seconds",
            duration,
            labels={"spider": spider},
        )

    @staticmethod
    def record_items(spider: str, count: int) -> None:
        """Record crawled items count.

        Args:
            spider: Spider name
            count: Number of items crawled
        """
        metrics.increment(
            "job_spider_items_total",
            value=float(count),
            labels={"spider": spider},
        )

    @staticmethod
    def record_error(spider: str, error_type: str) -> None:
        """Record an error.

        Args:
            spider: Spider name
            error_type: Error type (timeout/network/parse/etc)
        """
        metrics.increment(
            "job_spider_errors_total",
            labels={"spider": spider, "type": error_type},
        )

    @staticmethod
    def set_active_spiders(count: int) -> None:
        """Set the number of active spiders.

        Args:
            count: Number of active spiders
        """
        metrics.gauge("job_spider_active_spiders", float(count))

    @staticmethod
    def time_request(spider: str) -> "Generator[None, None, None]":
        """Time a request with context manager.

        Args:
            spider: Spider name

        Returns:
            Context manager

        Example:
            >>> with SpiderMetrics.time_request("boss"):
            ...     # do request
        """
        return metrics.timeit(
            "job_spider_request_duration_seconds",
            labels={"spider": spider},
        )
