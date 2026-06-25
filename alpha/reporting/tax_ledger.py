"""Tax ledger — monthly files, yearly rollups, and operator summaries."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from monitoring.csv_logger import CSVLogger

_MONTH_RE = re.compile(r"^trades_(\d{4}-\d{2})\.csv$")
_YEAR_RE = re.compile(r"^trades_(\d{4})_annual\.csv$")
_TAX_SUBDIR = "tax"


@dataclass(frozen=True)
class TaxRowSummary:
    rows: int = 0
    taxable_rows: int = 0
    buys: int = 0
    sells: int = 0
    transfers: int = 0
    buy_xrp: float = 0.0
    sell_xrp: float = 0.0
    transfer_xrp: float = 0.0
    buy_rlusd: float = 0.0
    sell_rlusd: float = 0.0
    realized_profit_xrp: float = 0.0
    tp_exits: int = 0
    sl_exits: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rows": self.rows,
            "taxable_rows": self.taxable_rows,
            "buys": self.buys,
            "sells": self.sells,
            "transfers": self.transfers,
            "buy_xrp": round(self.buy_xrp, 6),
            "sell_xrp": round(self.sell_xrp, 6),
            "transfer_xrp": round(self.transfer_xrp, 6),
            "buy_rlusd": round(self.buy_rlusd, 4),
            "sell_rlusd": round(self.sell_rlusd, 4),
            "realized_profit_xrp_equiv": round(self.realized_profit_xrp, 6),
            "tp_exits": self.tp_exits,
            "sl_exits": self.sl_exits,
        }


def _tax_dir(logs_dir: Path) -> Path:
    return logs_dir / _TAX_SUBDIR


def trades_path_for_month(logs_dir: Path, month: str) -> Path:
    key = str(month).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", key):
        raise ValueError(f"Invalid month key: {month!r} (expected YYYY-MM)")
    return logs_dir / f"trades_{key}.csv"


def annual_csv_path(logs_dir: Path, year: int) -> Path:
    y = int(year)
    if y < 2000 or y > 2100:
        raise ValueError(f"Invalid year: {year}")
    return _tax_dir(logs_dir) / f"trades_{y}_annual.csv"


def list_trade_months(logs_dir: Path) -> List[str]:
    months: List[str] = []
    if not logs_dir.is_dir():
        return months
    for path in sorted(logs_dir.glob("trades_*.csv")):
        match = _MONTH_RE.match(path.name)
        if match:
            months.append(match.group(1))
    return sorted(months, reverse=True)


def list_trade_years(logs_dir: Path) -> List[int]:
    years = {int(m[:4]) for m in list_trade_months(logs_dir)}
    tax = _tax_dir(logs_dir)
    if tax.is_dir():
        for path in tax.glob("trades_*_annual.csv"):
            match = _YEAR_RE.match(path.name)
            if match:
                years.add(int(match.group(1)))
    return sorted(years, reverse=True)


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []


def _classify_exit(notes: str) -> str:
    n = (notes or "").lower()
    if "take-profit" in n or "take_profit" in n:
        return "tp"
    if "stop-loss" in n or "stop_loss" in n:
        return "sl"
    return "other"


def summarize_rows(rows: Sequence[Dict[str, str]]) -> TaxRowSummary:
    buys = sells = transfers = taxable = tp = sl = 0
    buy_xrp = sell_xrp = transfer_xrp = 0.0
    buy_rlusd = sell_rlusd = profit = 0.0
    for row in rows:
        if (row.get("taxable") or "").upper() == "Y":
            taxable += 1
        et = (row.get("event_type") or "").upper()
        side = (row.get("side") or et).upper()
        try:
            xrp = float(row.get("xrp_amount") or 0)
            rlusd = float(row.get("rlusd_amount") or 0)
            pnl = float(row.get("profit_xrp_equiv") or 0)
        except (TypeError, ValueError):
            xrp = rlusd = pnl = 0.0
        if et == "BUY" or side == "BUY":
            buys += 1
            buy_xrp += xrp
            buy_rlusd += rlusd
        elif et == "SELL" or side == "SELL":
            sells += 1
            sell_xrp += xrp
            sell_rlusd += rlusd
            profit += pnl
            kind = _classify_exit(str(row.get("notes") or ""))
            if kind == "tp":
                tp += 1
            elif kind == "sl":
                sl += 1
        elif et == "TRANSFER" or side == "OUT":
            transfers += 1
            transfer_xrp += xrp
    return TaxRowSummary(
        rows=len(rows),
        taxable_rows=taxable,
        buys=buys,
        sells=sells,
        transfers=transfers,
        buy_xrp=buy_xrp,
        sell_xrp=sell_xrp,
        transfer_xrp=transfer_xrp,
        buy_rlusd=buy_rlusd,
        sell_rlusd=sell_rlusd,
        realized_profit_xrp=profit,
        tp_exits=tp,
        sl_exits=sl,
    )


def load_month_rows(logs_dir: Path, month: str) -> List[Dict[str, str]]:
    return read_csv_rows(trades_path_for_month(logs_dir, month))


def load_year_rows(logs_dir: Path, year: int) -> List[Dict[str, str]]:
    y = int(year)
    rows: List[Dict[str, str]] = []
    for month in list_trade_months(logs_dir):
        if month.startswith(f"{y}-"):
            rows.extend(load_month_rows(logs_dir, month))
    rows.sort(key=lambda r: r.get("timestamp_utc") or "")
    return rows


def write_annual_csv(logs_dir: Path, year: int) -> Path:
    """Merge monthly ``trades_YYYY-MM.csv`` files into ``logs/tax/trades_YYYY_annual.csv``."""
    rows = load_year_rows(logs_dir, year)
    out_path = annual_csv_path(logs_dir, year)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = list(CSVLogger.HEADER)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in header})
    return out_path


def annual_csv_text(logs_dir: Path, year: int) -> str:
    path = write_annual_csv(logs_dir, year)
    return path.read_text(encoding="utf-8")


def tax_periods_payload(logs_dir: Path) -> Dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    current_month = now.strftime("%Y-%m")
    current_year = now.year
    months = list_trade_months(logs_dir)
    years = list_trade_years(logs_dir)
    if current_year not in years and (months or current_month):
        years = sorted(set(years) | {current_year}, reverse=True)
    month_summaries = []
    for month in months:
        path = trades_path_for_month(logs_dir, month)
        summary = summarize_rows(read_csv_rows(path))
        month_summaries.append(
            {
                "month": month,
                "path": f"logs/{path.name}",
                "exists": path.is_file(),
                **summary.as_dict(),
            }
        )
    year_summaries = []
    for year in years:
        rows = load_year_rows(logs_dir, year)
        summary = summarize_rows(rows)
        annual_path = annual_csv_path(logs_dir, year)
        year_summaries.append(
            {
                "year": year,
                "annual_csv_path": f"logs/{_TAX_SUBDIR}/{annual_path.name}",
                "annual_csv_exists": annual_path.is_file(),
                "months_in_year": [m for m in months if m.startswith(f"{year}-")],
                **summary.as_dict(),
            }
        )
    return {
        "current_month": current_month,
        "current_year": current_year,
        "months": months,
        "years": years,
        "month_summaries": month_summaries,
        "year_summaries": year_summaries,
        "transfers_path": "logs/transfers.csv",
        "tax_notes": [
            "Monthly source files: logs/trades_YYYY-MM.csv (never overwritten by rollup).",
            "Yearly export: logs/tax/trades_YYYY_annual.csv (merged on demand).",
            "Use realized_profit_xrp_equiv on SELL rows for bracket gain/loss; confirm fiat conversion with your tax advisor.",
        ],
    }


def format_monthly_report(logs_dir: Path, month: str) -> str:
    path = trades_path_for_month(logs_dir, month)
    rows = read_csv_rows(path)
    summary = summarize_rows(rows)
    lines = [
        "=== Monthly tax / trades log ===",
        f"month: {month}",
        f"path: logs/{path.name}",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "Summary:",
        *[f"  {k}={v}" for k, v in summary.as_dict().items()],
        "",
        "All taxable rows:",
        "",
    ]
    if not rows:
        lines.append("(no rows — file missing or empty)")
        return "\n".join(lines)
    cols = [
        "timestamp_utc",
        "event_type",
        "taxable",
        "side",
        "xrp_amount",
        "rlusd_amount",
        "price_rlusd_per_xrp",
        "profit_xrp_equiv",
        "tx_hash",
        "notes",
    ]
    lines.extend(_format_table(rows, columns=cols))
    return "\n".join(lines)


def format_yearly_report(logs_dir: Path, year: int) -> str:
    rows = load_year_rows(logs_dir, year)
    summary = summarize_rows(rows)
    annual_path = write_annual_csv(logs_dir, year)
    months = [m for m in list_trade_months(logs_dir) if m.startswith(f"{int(year)}-")]
    lines = [
        "=== Annual tax rollup ===",
        f"tax_year: {year}",
        f"annual_csv: logs/{_TAX_SUBDIR}/{annual_path.name}",
        f"source_months: {', '.join(months) if months else '(none)'}",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "Year totals (taxable activity):",
        *[f"  {k}={v}" for k, v in summary.as_dict().items()],
        "",
        "For tax prep:",
        "  • SELL rows: proceeds ≈ rlusd_amount; gain/loss ≈ profit_xrp_equiv (XRP terms at exit mid).",
        "  • BUY rows: cost basis lots — match to SELL via bracket id in notes.",
        "  • TRANSFER rows: outbound disposals — review with advisor (may be non-trade).",
        "  • Export CSV: open /report/alpha_tax_year.csv?year=YYYY or download from HUD.",
        "  • Fiat USD: convert each row at your preferred rate source (not stored automatically).",
        "",
        "Monthly breakdown:",
    ]
    for month in sorted(months):
        msum = summarize_rows(load_month_rows(logs_dir, month))
        lines.append(
            f"  {month}: buys={msum.buys} sells={msum.sells} "
            f"profit_xrp={msum.realized_profit_xrp:.6f}"
        )
    lines.extend(["", "All rows (chronological):", ""])
    cols = [
        "timestamp_utc",
        "event_type",
        "side",
        "xrp_amount",
        "rlusd_amount",
        "price_rlusd_per_xrp",
        "profit_xrp_equiv",
        "tx_hash",
        "notes",
    ]
    if rows:
        lines.extend(_format_table(rows, columns=cols))
    else:
        lines.append("(no rows for this year)")
    return "\n".join(lines)


def _format_table(rows: Sequence[Dict[str, str]], *, columns: List[str]) -> List[str]:
    if not rows:
        return ["(no rows)"]
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(str(row.get(col, ""))))
    header = "  ".join(col.ljust(widths[col]) for col in columns)
    sep = "  ".join("-" * widths[col] for col in columns)
    lines = [header, sep]
    for row in rows:
        lines.append("  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))
    return lines
