"""Tests for drawdown reload (sell-off acquisition funding lane)."""

from __future__ import annotations

from pathlib import Path

import pytest

from alpha.decision.drawdown_reload import (
    DrawdownReloadSessionTracker,
    compute_drawdown_sell_size_xrp,
    evaluate_drawdown_reload,
)
from alpha.types import BalanceSnapshot, InventorySnapshot
from config.settings import BotConfig


def _inv(*, xrp_ratio: float = 0.95, deviation: float = 0.05, portfolio: float = 1000.0) -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=xrp_ratio,
        target_xrp_ratio=0.90,
        deviation=deviation,
        label="xrp_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="test",
        portfolio_xrp_equiv=portfolio,
        xrp_allocation_pct=xrp_ratio * 100.0,
        rlusd_allocation_pct=(1.0 - xrp_ratio) * 100.0,
        buy_blocked_imbalance=False,
        sell_blocked_imbalance=False,
    )


def _bal(*, xrp: float = 950.0, rlusd: float = 50.0, mid: float = 1.05) -> BalanceSnapshot:
    return BalanceSnapshot(
        xrp=xrp,
        rlusd=rlusd,
        mid_rlusd_per_xrp=mid,
        portfolio_xrp_equiv=xrp + rlusd / mid,
    )


def _write_drop_history(path: Path, *, ref: float = 1.10, now: float = 1.07) -> None:
    """Synthetic series: older samples near ref, recent at now."""
    from alpha.decision.price_history import BookPrices, append_book_prices

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    for i in range(40):
        mid = ref if i < 30 else now
        append_book_prices(
            BookPrices(bid=mid * 0.999, ask=mid * 1.001, mid=mid),
            path=path,
            record_ohlc=False,
        )


def test_size_caps_to_stage_and_total(tmp_path: Path):
    cfg = BotConfig(
        alpha_drawdown_reload_stage1_bag_pct=2.0,
        alpha_drawdown_reload_stage2_bag_pct=2.0,
        alpha_drawdown_reload_total_bag_pct=4.0,
        xrp_reserve=12.0,
        min_order_size_xrp=1.0,
    )
    bal = _bal(xrp=1000.0, rlusd=0.0, mid=1.0)
    s1 = compute_drawdown_sell_size_xrp(
        cfg, stage=1, portfolio_xrp_equiv=1000.0, balances=bal, xrp_sold_in_window=0.0
    )
    assert s1 == pytest.approx(20.0, abs=0.01)
    s2 = compute_drawdown_sell_size_xrp(
        cfg, stage=2, portfolio_xrp_equiv=1000.0, balances=bal, xrp_sold_in_window=20.0
    )
    assert s2 == pytest.approx(20.0, abs=0.01)
    capped = compute_drawdown_sell_size_xrp(
        cfg, stage=2, portfolio_xrp_equiv=1000.0, balances=bal, xrp_sold_in_window=40.0
    )
    assert capped == 0.0


def test_idle_when_no_drop(tmp_path: Path):
    hist = tmp_path / "price_history.jsonl"
    _write_drop_history(hist, ref=1.10, now=1.095)  # ~−0.45%
    cfg = BotConfig(alpha_drawdown_reload_enabled=True, alpha_drawdown_reload_watch_pct=2.0)
    snap = evaluate_drawdown_reload(
        cfg,
        inventory=_inv(),
        mid=1.095,
        balances=_bal(mid=1.095),
        price_history_path=hist,
    )
    assert snap.phase == "idle"
    assert snap.armed is False


def test_watching_then_armed_stage1(tmp_path: Path):
    hist = tmp_path / "price_history.jsonl"
    _write_drop_history(hist, ref=1.10, now=1.072)  # ~−2.55%
    cfg = BotConfig(
        alpha_drawdown_reload_enabled=True,
        alpha_drawdown_reload_watch_pct=2.0,
        alpha_drawdown_reload_stage1_arm_pct=2.5,
        alpha_drawdown_reload_stage2_arm_pct=4.0,
        alpha_drawdown_reload_stage1_bag_pct=2.0,
        alpha_drawdown_reload_total_bag_pct=4.0,
        xrp_reserve=12.0,
        min_order_size_xrp=1.0,
        alpha_cycle_interval_seconds=60,
        alpha_price_sample_interval_seconds=60,
    )
    sess = DrawdownReloadSessionTracker(path=tmp_path / "dd.json")
    snap = evaluate_drawdown_reload(
        cfg,
        inventory=_inv(portfolio=1000.0),
        mid=1.072,
        balances=_bal(xrp=1000.0, rlusd=0.0, mid=1.072),
        session=sess,
        price_history_path=hist,
    )
    assert snap.phase == "armed"
    assert snap.armed is True
    assert snap.stage == 1
    assert snap.target_sell_xrp > 10.0


def test_session_stages(tmp_path: Path):
    cfg = BotConfig(alpha_drawdown_reload_max_sells_per_window=2, alpha_drawdown_reload_window_hours=48.0)
    sess = DrawdownReloadSessionTracker(path=tmp_path / "dd.json")
    assert sess.can_place_sell(cfg)
    sess.record_sell_placed(size_xrp=20.0, stage=1, mid=1.07, config=cfg)
    assert sess.stage1_placed(cfg)
    assert not sess.stage2_placed(cfg)
    sess.record_sell_placed(size_xrp=20.0, stage=2, mid=1.05, config=cfg)
    assert sess.stage2_placed(cfg)
    assert not sess.can_place_sell(cfg)
