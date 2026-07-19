"""Prometheus metrics — a small, dependency-free registry (T9.1).

Renders the Prometheus **text exposition format** from in-process ``Counter`` /
``Histogram`` / ``Gauge`` metrics, so the API is observable without adding a
runtime dependency (consistent with the codebase's adapter philosophy — a swap to
``prometheus_client`` multiprocess / OpenTelemetry is an isolated, documented
change). Metrics are **per-process**; a scraper aggregates across workers.

Labels carry only bounded, non-identifying dimensions (method, route template,
status) — never a user id, path-parameter value or any PII. ``GET /metrics`` is
unauthenticated by convention and should be exposed only on a protected network in
production. See ``specs/domain/platform/metrics.md``.
"""

import re
import threading
from collections.abc import Sequence
from typing import Final

CONTENT_TYPE: Final = "text/plain; version=0.0.4; charset=utf-8"
DEFAULT_BUCKETS: Final = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_NAME_RE: Final = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid metric/label name: {name!r}")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_value(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


def _labels_str(pairs: Sequence[tuple[str, str]]) -> str:
    if not pairs:
        return ""
    body = ",".join(f'{name}="{_escape(value)}"' for name, value in pairs)
    return "{" + body + "}"


class _Metric:
    _type = ""

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Sequence[str] = (),
        *,
        registry: "CollectorRegistry | None" = None,
    ) -> None:
        _validate_name(name)
        for label in labelnames:
            _validate_name(label)
        self.name = name
        self.documentation = documentation
        self.labelnames = tuple(labelnames)
        self._lock = threading.Lock()
        (registry if registry is not None else REGISTRY).register(self)

    def _labelkey(self, labelvalues: Sequence[str]) -> tuple[str, ...]:
        if len(labelvalues) != len(self.labelnames):
            raise ValueError(f"{self.name} expects {len(self.labelnames)} labels")
        return tuple(str(value) for value in labelvalues)

    def _resolve(self, labelvalues: Sequence[str], labelkwargs: dict[str, str]) -> tuple[str, ...]:
        if labelkwargs:
            labelvalues = tuple(labelkwargs[name] for name in self.labelnames)
        return self._labelkey(labelvalues)

    def _render_samples(self) -> list[str]:  # pragma: no cover - overridden
        raise NotImplementedError


class _CounterChild:
    def __init__(self, parent: "Counter", key: tuple[str, ...]) -> None:
        self._parent = parent
        self._key = key

    def inc(self, amount: float = 1.0) -> None:
        self._parent._add(self._key, amount)


class Counter(_Metric):
    """A monotonically increasing counter."""

    _type = "counter"

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Sequence[str] = (),
        *,
        registry: "CollectorRegistry | None" = None,
    ) -> None:
        super().__init__(name, documentation, labelnames, registry=registry)
        self._values: dict[tuple[str, ...], float] = {}
        if not self.labelnames:
            self._values[()] = 0.0

    def labels(self, *labelvalues: str, **labelkwargs: str) -> _CounterChild:
        return _CounterChild(self, self._resolve(labelvalues, labelkwargs))

    def inc(self, amount: float = 1.0) -> None:
        if self.labelnames:
            raise ValueError(f"{self.name} is labelled; use .labels(...).inc()")
        self._add((), amount)

    def value(self, *labelvalues: str) -> float:
        """Return the current value for a label set (mainly for tests)."""
        return self._values.get(self._labelkey(labelvalues), 0.0)

    def _add(self, key: tuple[str, ...], amount: float) -> None:
        if amount < 0:
            raise ValueError("counters cannot decrease")
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def _render_samples(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
        return [
            f"{self.name}{_labels_str(list(zip(self.labelnames, key, strict=True)))} "
            f"{_format_value(value)}"
            for key, value in items
        ]


class _GaugeChild:
    def __init__(self, parent: "Gauge", key: tuple[str, ...]) -> None:
        self._parent = parent
        self._key = key

    def inc(self, amount: float = 1.0) -> None:
        self._parent._add(self._key, amount)

    def dec(self, amount: float = 1.0) -> None:
        self._parent._add(self._key, -amount)

    def set(self, value: float) -> None:
        self._parent._set(self._key, value)


class Gauge(_Metric):
    """A value that can go up or down."""

    _type = "gauge"

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Sequence[str] = (),
        *,
        registry: "CollectorRegistry | None" = None,
    ) -> None:
        super().__init__(name, documentation, labelnames, registry=registry)
        self._values: dict[tuple[str, ...], float] = {}
        if not self.labelnames:
            self._values[()] = 0.0

    def labels(self, *labelvalues: str, **labelkwargs: str) -> _GaugeChild:
        return _GaugeChild(self, self._resolve(labelvalues, labelkwargs))

    def inc(self, amount: float = 1.0) -> None:
        self._add((), amount)

    def dec(self, amount: float = 1.0) -> None:
        self._add((), -amount)

    def set(self, value: float) -> None:
        self._set((), value)

    def value(self, *labelvalues: str) -> float:
        """Return the current value (mainly for tests)."""
        return self._values.get(self._labelkey(labelvalues), 0.0)

    def _add(self, key: tuple[str, ...], amount: float) -> None:
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def _set(self, key: tuple[str, ...], value: float) -> None:
        with self._lock:
            self._values[key] = value

    def _render_samples(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
        return [
            f"{self.name}{_labels_str(list(zip(self.labelnames, key, strict=True)))} "
            f"{_format_value(value)}"
            for key, value in items
        ]


class _Bucket:
    __slots__ = ("counts", "sum", "count")

    def __init__(self, size: int) -> None:
        self.counts = [0] * size
        self.sum = 0.0
        self.count = 0


class _HistogramChild:
    def __init__(self, parent: "Histogram", key: tuple[str, ...]) -> None:
        self._parent = parent
        self._key = key

    def observe(self, value: float) -> None:
        self._parent._observe(self._key, value)


class Histogram(_Metric):
    """A cumulative histogram with fixed buckets."""

    _type = "histogram"

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Sequence[str] = (),
        *,
        buckets: Sequence[float] = DEFAULT_BUCKETS,
        registry: "CollectorRegistry | None" = None,
    ) -> None:
        super().__init__(name, documentation, labelnames, registry=registry)
        self.buckets = tuple(sorted(buckets))
        self._series: dict[tuple[str, ...], _Bucket] = {}
        if not self.labelnames:
            self._series[()] = _Bucket(len(self.buckets))

    def labels(self, *labelvalues: str, **labelkwargs: str) -> _HistogramChild:
        return _HistogramChild(self, self._resolve(labelvalues, labelkwargs))

    def observe(self, value: float) -> None:
        if self.labelnames:
            raise ValueError(f"{self.name} is labelled; use .labels(...).observe()")
        self._observe((), value)

    def _observe(self, key: tuple[str, ...], value: float) -> None:
        with self._lock:
            bucket = self._series.get(key)
            if bucket is None:
                bucket = self._series[key] = _Bucket(len(self.buckets))
            for index, boundary in enumerate(self.buckets):
                if value <= boundary:
                    bucket.counts[index] += 1
                    break
            bucket.sum += value
            bucket.count += 1

    def _render_samples(self) -> list[str]:
        with self._lock:
            items = sorted(self._series.items())
        lines: list[str] = []
        for key, bucket in items:
            base = list(zip(self.labelnames, key, strict=True))
            cumulative = 0
            for index, boundary in enumerate(self.buckets):
                cumulative += bucket.counts[index]
                pairs = [*base, ("le", _format_value(boundary))]
                lines.append(f"{self.name}_bucket{_labels_str(pairs)} {cumulative}")
            lines.append(f"{self.name}_bucket{_labels_str([*base, ('le', '+Inf')])} {bucket.count}")
            lines.append(f"{self.name}_sum{_labels_str(base)} {_format_value(bucket.sum)}")
            lines.append(f"{self.name}_count{_labels_str(base)} {bucket.count}")
        return lines


class CollectorRegistry:
    """Holds metrics and renders them in the Prometheus text exposition format."""

    def __init__(self) -> None:
        self._metrics: list[_Metric] = []
        self._lock = threading.Lock()

    def register(self, metric: _Metric) -> None:
        with self._lock:
            self._metrics.append(metric)

    def render(self) -> str:
        with self._lock:
            metrics = list(self._metrics)
        lines: list[str] = []
        for metric in metrics:
            lines.append(f"# HELP {metric.name} {metric.documentation}")
            lines.append(f"# TYPE {metric.name} {metric._type}")
            lines.extend(metric._render_samples())
        return "\n".join(lines) + "\n"


REGISTRY: Final = CollectorRegistry()

# Default HTTP metrics, recorded by ``MetricsMiddleware``.
REQUESTS_TOTAL: Final = Counter(
    "http_requests_total", "Total HTTP requests.", ("method", "route", "status")
)
REQUEST_DURATION: Final = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route", "status"),
)
REQUESTS_IN_FLIGHT: Final = Gauge("http_requests_in_flight", "In-flight HTTP requests.")

# Domain metric: every context flows through the event store, so one counter here
# observes the whole import → normalize → insight → forecast pipeline by type.
EVENTS_APPENDED: Final = Counter(
    "mylife_events_appended_total", "Life Events appended, by event type.", ("event_type",)
)


def render_latest() -> str:
    """Render the default registry's metrics."""
    return REGISTRY.render()
