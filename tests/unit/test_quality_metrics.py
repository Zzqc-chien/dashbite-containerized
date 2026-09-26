"""Unit tests for throughput and field-failure helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.dashboard.quality_metrics import field_failure_totals, throughput_summary


@pytest.mark.unit
def test_throughput_and_field_failures():
    log = pd.DataFrame(
        {
            "rows_in": [10, 10],
            "rows_out": [8, 7],
            "rows_dropped": [2, 3],
            "fail_distance_km": [2, 1],
            "fail_was_late": [0, 2],
        }
    )
    tp = throughput_summary(log)
    assert tp["batches"] == 2
    assert tp["rows_in"] == 20
    assert tp["rows_out"] == 15
    assert tp["drop_rate"] == pytest.approx(0.25)

    fails = field_failure_totals(log)
    assert fails["distance_km"] == 3
    assert fails["was_late"] == 2
