"""Tests for realized bracket P&L snapshot (SKYNET context)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha.hud.skynet import build_skynet_context
from alpha.reporting.realized_pnl import build_realized_pnl_snapshot, format_realized_pnl_context_block


def _write_trades(path: Path, rows: list[str]) -> None:
    header = (
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after"
    )
    path.write_text("\n".join([header, *rows]), encoding="utf-8")


def test_build_realized_pnl_snapshot_tp_sl(tmp_path: Path) -> None:
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    t1 = (now - timedelta(hours=2)).isoformat()
    t2 = (now - timedelta(hours=1)).isoformat()
    _write_trades(
        tmp_path / "trades_2026-06.csv",
        [
            f"{t1},BUY,Y,mainnet,BUY,50,55,1.1,0,,1,alpha bracket buy abc,100,500",
            f"{t2},SELL,Y,mainnet,SELL,50,54.5,1.09,-0.5,,2,alpha bracket stop-loss abc entry=1.100000,50,450",
            f"{t2},SELL,Y,mainnet,SELL,10,11.2,1.12,0.2,,3,alpha bracket take-profit def entry=1.100000,40,440",
        ],
    )
    snap = build_realized_pnl_snapshot(logs_dir=tmp_path, hours=24, now=now, session_pnl_xrp=5.0)
    assert snap["available"] is True
    assert snap["taxable_buys"] == 1
    assert snap["taxable_sells"] == 2
    assert snap["tp_exits"] == 1
    assert snap["sl_exits"] == 1
    assert snap["realized_profit_xrp_equiv"] == -0.3
    assert snap["session_pnl_xrp_mtm"] == 5.0
    assert snap["mtm_vs_realized_delta"] == 5.3
    block = format_realized_pnl_context_block(snap)
    assert "realized_profit_xrp_equiv=-0.3" in block
    assert "session_pnl_xrp_mtm=5.0" in block


def test_build_realized_pnl_snapshot_rlusd_at_mid(tmp_path: Path) -> None:
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    t = (now - timedelta(hours=1)).isoformat()
    _write_trades(
        tmp_path / "trades_2026-06.csv",
        [
            f"{t},SELL,Y,mainnet,SELL,10,11.0,1.1,-0.1,,1,alpha bracket stop-loss abc,90,400",
        ],
    )
    snap = build_realized_pnl_snapshot(
        logs_dir=tmp_path,
        hours=24,
        now=now,
        mid_rlusd_per_xrp=1.1,
    )
    assert snap["realized_profit_xrp_equiv"] == -0.1
    assert snap["realized_profit_rlusd"] == -0.11
    assert snap["mid_rlusd_per_xrp"] == 1.1


def test_build_skynet_context_includes_realized_pnl(tmp_path: Path, monkeypatch) -> None:
    now = datetime.now(tz=timezone.utc)
    t = (now - timedelta(hours=1)).isoformat()
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_trades(
        logs / "trades_2026-06.csv",
        [
            f"{t},SELL,Y,mainnet,SELL,20,21.8,1.09,-0.2,,1,alpha bracket stop-loss xyz,80,400",
        ],
    )
    monkeypatch.chdir(tmp_path)
    ctx = build_skynet_context(
        {
            "risk": {"session_pnl_xrp": 3.0},
            "inventory": {},
            "decision": {},
            "recent_activity": [],
        },
        operator_config={"alpha_operator_phase": "trust"},
    )
    assert "Realized bracket P&L" in ctx
    assert "sl_exits=1" in ctx
    assert "session_pnl_xrp_mtm=3.0" in ctx
