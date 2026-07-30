"""Unit tests for the metrics registry (T9.1)."""

import pytest

from mylife.core.metrics import CollectorRegistry, Counter, Gauge, Histogram


def test_counter_renders_help_type_and_sample() -> None:
    reg = CollectorRegistry()
    counter = Counter("things_total", "Total things.", registry=reg)
    counter.inc()
    counter.inc(2)
    text = reg.render()
    assert "# HELP things_total Total things." in text
    assert "# TYPE things_total counter" in text
    assert "things_total 3" in text


def test_counter_labels_and_no_negative() -> None:
    reg = CollectorRegistry()
    counter = Counter("hits_total", "Hits.", ("route",), registry=reg)
    counter.labels(route="/a").inc()
    counter.labels(route="/b").inc(5)
    text = reg.render()
    assert 'hits_total{route="/a"} 1' in text
    assert 'hits_total{route="/b"} 5' in text
    with pytest.raises(ValueError, match="cannot decrease"):
        counter.labels(route="/a").inc(-1)


def test_histogram_buckets_are_cumulative_with_sum_and_count() -> None:
    reg = CollectorRegistry()
    hist = Histogram("lat_seconds", "Latency.", buckets=(0.1, 0.5, 1.0), registry=reg)
    for value in (0.05, 0.2, 0.2, 2.0):
        hist.observe(value)
    text = reg.render()
    assert 'lat_seconds_bucket{le="0.1"} 1' in text  # only 0.05
    assert 'lat_seconds_bucket{le="0.5"} 3' in text  # 0.05, 0.2, 0.2
    assert 'lat_seconds_bucket{le="1"} 3' in text
    assert 'lat_seconds_bucket{le="+Inf"} 4' in text  # incl. the 2.0 overflow
    assert "lat_seconds_count 4" in text
    assert "lat_seconds_sum 2.45" in text


def test_gauge_set_inc_dec_and_value() -> None:
    reg = CollectorRegistry()
    gauge = Gauge("in_flight", "In flight.", registry=reg)
    gauge.inc()
    gauge.inc()
    gauge.dec()
    assert gauge.value() == 1.0
    gauge.set(0)
    assert gauge.value() == 0.0
    assert "in_flight 0" in reg.render()


def test_label_values_are_escaped() -> None:
    reg = CollectorRegistry()
    counter = Counter("weird_total", "Weird.", ("name",), registry=reg)
    counter.labels(name='a"b\\c').inc()
    assert 'weird_total{name="a\\"b\\\\c"} 1' in reg.render()


def test_invalid_metric_name_rejected() -> None:
    reg = CollectorRegistry()
    with pytest.raises(ValueError, match="invalid metric"):
        Counter("1bad-name", "Nope.", registry=reg)
