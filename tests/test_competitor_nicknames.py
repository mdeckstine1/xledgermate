"""Tests for F1 competitor nicknames."""

from pathlib import Path

from experimental.ws_feed.competitor_nicknames import (
    apply_nicknames_to_profiles,
    load_nicknames,
    remove_nickname,
    resolve_nickname,
    save_nicknames,
    set_nickname,
)


def test_set_and_resolve_nickname(tmp_path: Path) -> None:
    path = tmp_path / "nicknames.json"
    set_nickname("rTestAddress123456789", "Whale Bob", path=path)
    mapping = load_nicknames(path=path)
    assert mapping["rTestAddress123456789"] == "Whale Bob"
    assert resolve_nickname("rTestAddress123456789", mapping) == "Whale Bob"


def test_apply_nicknames_to_profiles() -> None:
    rows = [{"account": "rTest…", "account_full": "rTestAddress123456789", "last_spread": 0.1}]
    out = apply_nicknames_to_profiles(rows, {"rTestAddress123456789": "Bob"})
    assert out[0]["nickname"] == "Bob"


def test_remove_nickname(tmp_path: Path) -> None:
    path = tmp_path / "nicknames.json"
    save_nicknames({"rA": "One", "rB": "Two"}, path=path)
    remove_nickname("rA", path=path)
    assert load_nicknames(path=path) == {"rB": "Two"}
