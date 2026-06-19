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


def test_capture_grade_excludes_incoherent_artifact_rows(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    rows = [
        "timestamp_utc,side,xrp_amount,rlusd_amount,price_rlusd_per_xrp,profit_xrp_equiv,notes",
        "2026-06-18T13:00:00+00:00,SELL,10.0,11.6,1.16,0.01,WS pure fill @ mid 1.160000",
        "2026-06-18T14:00:00+00:00,SELL,1.0,27.8,27.85,23.0,WS pure fill @ mid 1.160000",
    ]
    rows.extend(
        f"2026-06-18T12:00:0{i}+00:00,SELL,10.0,11.6,1.16,0.01,WS pure fill @ mid 1.160000"
        for i in range(8)
    )
    (logs / "trades_2026-06.csv").write_text("\n".join(rows), encoding="utf-8")
    pm = build_performance_metrics(runtime={"toxic_fill_ratio_30s": 0.1}, logs_dir=logs)
    cap = pm["capture"]
    assert cap["ws_fills"] == 9
    assert cap["total_capture_xrp"] == 0.09
    spread = next(g for g in pm["grades"] if g["id"] == "spread_capture")
    assert spread["grade"] == "good"


def test_capture_grade_mid_bps_band_is_thin_edge(tmp_path: Path) -> None:
    """5–8 bps with strong positive % → thin_edge (G6 v1.1), not attention."""
    logs = tmp_path / "logs"
    logs.mkdir()
    rows = [
        "timestamp_utc,event_type,xrp_amount,profit_xrp_equiv,notes",
    ]
    rows.extend(
        f"2026-06-18T12:00:0{i}+00:00,FILL,10.0,0.0054,WS pure fill @ mid 1.160000"
        for i in range(8)
    )
    (logs / "trades_2026-06.csv").write_text("\n".join(rows), encoding="utf-8")
    pm = build_performance_metrics(runtime={}, logs_dir=logs)
    spread = next(g for g in pm["grades"] if g["id"] == "spread_capture")
    assert spread["grade"] == "thin_edge"
    assert pm["activation"]["tier"] == "thin_edge"
    assert pm["activation"]["gate_pass"] is True
    assert "bps" in spread["value"]


def test_session_boot_scopes_g6_to_warming_up_not_cumulative_hold(tmp_path: Path) -> None:
    """Fresh engine session must not inherit hold from pre-boot CSV fills."""
    logs = tmp_path / "logs"
    logs.mkdir()
    rows = [
        "timestamp_utc,event_type,xrp_amount,profit_xrp_equiv,notes",
    ]
    rows.extend(
        f"2026-06-17T12:00:0{i}+00:00,FILL,10.0,0.0054,WS pure fill @ mid 1.160000"
        for i in range(20)
    )
    (logs / "trades_2026-06.csv").write_text("\n".join(rows), encoding="utf-8")
    pm_cum = build_performance_metrics(runtime={}, logs_dir=logs)
    assert pm_cum["activation"]["tier"] == "thin_edge"
    assert pm_cum["activation"]["gate_pass"] is True

    pm_sess = build_performance_metrics(
        runtime={
            "session_boot_utc": "2026-06-18T20:00:00+00:00",
            "fills_session": 0,
        },
        logs_dir=logs,
    )
    assert pm_sess["metrics_scope"] == "session"
    assert pm_sess["capture"]["ws_fills"] == 0
    assert pm_sess["activation"]["tier"] == "warming_up"
    assert pm_sess["activation"]["scope"] == "session"
