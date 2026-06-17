"""Tests for G3 performance metrics grades."""

from __future__ import annotations

from pathlib import Path

from experimental.ws_feed.performance_metrics import build_performance_metrics


def test_toxicity_attention_above_20pct_not_unknown(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "trades_2026-06.csv").write_text(
        "timestamp_utc,event_type,xrp_amount,profit_xrp_equiv,notes\n"
        + "\n".join(
            f"2026-06-17T12:00:0{i}+00:00,FILL,1.0,0.01,WS pure fill"
            for i in range(8)
        ),
        encoding="utf-8",
    )
    pm = build_performance_metrics(
        runtime={
            "toxic_fill_ratio_30s": 0.22,
            "balance_xrp": 200.0,
            "portfolio_value_xrp": 400.0,
            "inventory_target_xrp_ratio": 0.55,
        },
        logs_dir=logs,
    )
    tox = next(g for g in pm["grades"] if g["id"] == "toxicity")
    assert tox["grade"] == "attention"
    assert "22%" in tox["value"]


def test_toxicity_good_at_20pct(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "trades_2026-06.csv").write_text(
        "timestamp_utc,event_type,xrp_amount,profit_xrp_equiv,notes\n"
        + "\n".join(
            f"2026-06-17T12:00:0{i}+00:00,FILL,1.0,0.01,WS pure fill"
            for i in range(8)
        ),
        encoding="utf-8",
    )
    pm = build_performance_metrics(
        runtime={"toxic_fill_ratio_30s": 0.20},
        logs_dir=logs,
    )
    tox = next(g for g in pm["grades"] if g["id"] == "toxicity")
    assert tox["grade"] == "good"
