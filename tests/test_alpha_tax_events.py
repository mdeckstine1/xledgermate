"""Tests for Alpha taxable event CSV logging."""

from __future__ import annotations

from pathlib import Path

import pytest

from alpha.orders.types import BracketFillEvent, BracketLifecycleState
from alpha.reporting.tax_events import log_bracket_fill_tax_event, reset_tax_event_dedupe_for_tests


@pytest.fixture(autouse=True)
def _reset_dedupe():
    reset_tax_event_dedupe_for_tests()
    yield
    reset_tax_event_dedupe_for_tests()


def test_log_buy_fill_writes_taxable_row(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    event = BracketFillEvent(
        bracket_id="abc12345-uuid",
        leg="buy",
        filled_xrp=10.0,
        price_rlusd_per_xrp=2.0,
        partial=False,
        new_state=BracketLifecycleState.BRACKET_ACTIVE,
    )
    assert log_bracket_fill_tax_event(
        event=event,
        entry_price=2.0,
        network="mainnet",
        dry_run=False,
        mid=2.0,
    )
    csv_path = Path("logs") / f"trades_{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m')}.csv"
    text = csv_path.read_text(encoding="utf-8")
    assert "BUY" in text
    assert "Y" in text
    assert "alpha bracket buy" in text


def test_log_tp_fill_writes_sell_with_profit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    event = BracketFillEvent(
        bracket_id="abc12345-uuid",
        leg="tp",
        filled_xrp=10.0,
        price_rlusd_per_xrp=2.1,
        partial=False,
        new_state=BracketLifecycleState.TP_FILLED,
    )
    assert log_bracket_fill_tax_event(
        event=event,
        entry_price=2.0,
        network="mainnet",
        dry_run=False,
        mid=2.1,
    )
    csv_path = Path("logs") / f"trades_{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m')}.csv"
    text = csv_path.read_text(encoding="utf-8")
    assert "SELL" in text
    assert "take-profit" in text


def test_dry_run_skips_tax_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    event = BracketFillEvent(
        bracket_id="abc12345-uuid",
        leg="buy",
        filled_xrp=5.0,
        price_rlusd_per_xrp=2.0,
        partial=False,
        new_state=BracketLifecycleState.BRACKET_ACTIVE,
    )
    assert not log_bracket_fill_tax_event(
        event=event,
        entry_price=2.0,
        network="mainnet",
        dry_run=True,
    )
    assert not list(Path("logs").glob("trades_*.csv"))


def test_duplicate_fill_not_logged_twice(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    event = BracketFillEvent(
        bracket_id="abc12345-uuid",
        leg="buy",
        filled_xrp=5.0,
        price_rlusd_per_xrp=2.0,
        partial=False,
        new_state=BracketLifecycleState.BRACKET_ACTIVE,
    )
    kwargs = dict(event=event, entry_price=2.0, network="mainnet", dry_run=False, mid=2.0)
    assert log_bracket_fill_tax_event(**kwargs)
    assert not log_bracket_fill_tax_event(**kwargs)
    csv_path = Path("logs") / f"trades_{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m')}.csv"
    lines = [ln for ln in csv_path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("timestamp_utc")]
    assert len(lines) == 1
    assert ",BUY," in lines[0]
