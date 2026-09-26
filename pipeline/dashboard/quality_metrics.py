"""Quality helpers: field-level failures and batch throughput."""

from __future__ import annotations

import pandas as pd

FAIL_PREFIX = "fail_"


def throughput_summary(quality_log: pd.DataFrame) -> dict:
    """Aggregate batch throughput from the quality log."""
    if quality_log is None or quality_log.empty:
        return {
            "batches": 0,
            "rows_in": 0,
            "rows_out": 0,
            "rows_dropped": 0,
            "drop_rate": 0.0,
            "avg_rows_in_per_batch": 0.0,
            "avg_rows_out_per_batch": 0.0,
        }
    rows_in = int(quality_log["rows_in"].sum())
    rows_out = int(quality_log["rows_out"].sum())
    batches = int(len(quality_log))
    dropped = rows_in - rows_out
    return {
        "batches": batches,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "rows_dropped": dropped,
        "drop_rate": float(dropped / rows_in) if rows_in else 0.0,
        "avg_rows_in_per_batch": float(rows_in / batches) if batches else 0.0,
        "avg_rows_out_per_batch": float(rows_out / batches) if batches else 0.0,
    }


def field_failure_totals(quality_log: pd.DataFrame) -> dict[str, int]:
    """Sum field-level failure counts across batches."""
    if quality_log is None or quality_log.empty:
        return {}
    totals: dict[str, int] = {}
    for col in quality_log.columns:
        if col.startswith(FAIL_PREFIX):
            field = col[len(FAIL_PREFIX) :]
            totals[field] = int(quality_log[col].fillna(0).sum())
    return totals
