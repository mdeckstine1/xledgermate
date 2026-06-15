#!/usr/bin/env python3
"""
Replay AI orchestrator for the initial-stage AI analysis placeholder.

Purpose (direct response to: "at the initial stage of ws development, how hard
would it be to add a placeholder for ai analysis? we need speed in decision
making... ultimatly mm is not about trending, but about making good rake,
competitive dominance is my goal"):

- Uses the *current long run data* (decisions.jsonl with hundreds of
  "Generated 0 quotes" + "Book L1 spread X%" + "edge thin / L1 too tight"
  cycles) as the sacred testing ground / labeled corpus.
- For each such hard "no presence" case, constructs the inputs a fast
  micro-structure analyzer would see: WS-fresh book state (low age), optional
  secondary (Anodos-style mid + liquidity_score), run context (toxicity,
  inventory skew inferred from reasons).
- Calls a pluggable AIAnalyzer (stub today; swap for LocalLLMAnalyzer or
  APIAIAnalyzer later).
- Outputs: how many of the original 0-quote / edge-blocked cycles the AI
  micro-signal would have marked "truly skimmable for rake" or suggested a
  negative min_edge adjustment (i.e. "quote near, this looks like a real
  spread-capture opportunity given secondary confirmation").
- This is *not* trend following. It is rapid triage on exactly the marginal
  thin-book situations the hard gate + policy are correctly protecting today.
  Goal: competitive dominance via more safe time on book (better Tier C
  presence) and more good rake (spread capture) when the combination of
  fresher WS book + secondary + fast AI says the edge is real.

How hard at initial stage: Trivial / low cost. The replay harness, BookState,
edge/policy logic, and the exact 985+ labeled "0 offers on thin L1" cases
already exist on this branch. The placeholder is just a protocol (AIAnalyzer
ABC) + one orchestrator that slots in at the decision points. No main engine
or hard-gate changes. Local for <100ms speed in the loop; API for batch
explanation of the full run offline.

Run (from repo root on grok-ws-feed):
  python -m experimental.ai_analysis.replay_ai_orchestrator --decisions logs/decisions.jsonl --analyzer stub
  (or --analyzer local-stub / api-stub for the other placeholders)

Later: wire the same analyzer into WsBookFeed hooks or a future perception
layer; measure real presence/rake delta once WS + Anodos are live.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Repo root for imports when run as -m
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experimental.ai_analysis.base import AIAnalyzer, AIAnalysis, StubAIAnalyzer
from experimental.ai_analysis.stub_llm import LocalLLMAnalyzer, APIAIAnalyzer

# Self-contained extractor (kept in sync with ws_feed/replay_long_run.py).
# We deliberately duplicate the minimal parser here so the AI orchestrator
# is runnable standalone during the initial placeholder stage. Later we can
# factor a shared "load_long_run_snapshots" if desired.
def _extract_historical_snapshots(decisions_path: Path) -> List[Dict[str, Any]]:
    snapshots: List[Dict[str, Any]] = []
    with decisions_path.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue

            cycle = d.get("cycle")
            events = d.get("events", [])
            book_spread = bid = ask = None
            edge_met = None
            gen_quotes = None
            reasons: List[str] = []

            for e in events:
                msg = e.get("message", "") or ""
                # Tolerant parser for the variety of log formats in the long-run data:
                # "Book L1 spread 0.125% (bid 1.322110 / ask 1.323760)"
                # or "Book L1 spread 0.05% (bid 1.23 ask 1.24)" (embedded in long policy strings)
                m = re.search(r"Book L1 spread ([\d.]+)% \(bid ([\d.]+)\s*/?\s*ask ([\d.]+)\)", msg)
                if m:
                    book_spread = float(m.group(1))
                    bid = float(m.group(2))
                    ask = float(m.group(3))
                else:
                    # Fallback: sometimes the L1 is mentioned without the exact paren form in the same event
                    m2 = re.search(r"Book L1 spread ([\d.]+)%", msg)
                    if m2 and book_spread is None:
                        # We still need bid/ask for the snapshot; try to pull from the same msg or the whole decision
                        mb = re.search(r"bid\s*([\d.]+)\s*/?\s*ask\s*([\d.]+)", msg, re.I)
                        if mb:
                            book_spread = float(m2.group(1))
                            bid = float(mb.group(1))
                            ask = float(mb.group(2))

                lower = msg.lower()
                if "market_edge_met" in lower or "edge thin" in lower or "l1 too tight" in lower or "market edge thin" in lower:
                    edge_met = ("false" not in lower) and ("thin" not in lower) and ("too tight" not in lower)
                    reasons.append(msg[:350])

                if "generated" in lower and "quote" in lower:
                    m2 = re.search(r"Generated\s+(\d+)", msg, re.I)
                    if m2:
                        gen_quotes = int(m2.group(1))
                    reasons.append(msg[:250])

            if book_spread is not None and bid is not None and ask is not None:
                snapshots.append({
                    "cycle": cycle,
                    "book_spread_pct": book_spread,
                    "best_bid": bid,
                    "best_ask": ask,
                    "original_edge_met": edge_met,
                    "original_gen_quotes": gen_quotes,
                    "reasons": reasons,
                })
    return snapshots


logger = logging.getLogger(__name__)


def _build_book_state_for_ai(snap: Dict[str, Any], simulated_age_s: float = 1.5) -> Dict[str, Any]:
    """Turn a historical poll snapshot into the 'fresh WS book' view an analyzer sees."""
    return {
        "book_spread_pct": snap["book_spread_pct"],
        "best_bid": snap["best_bid"],
        "best_ask": snap["best_ask"],
        "age_s": simulated_age_s,  # WS + deltas make this << poll age
        "bids": [{"price": snap["best_bid"], "size": 1.0}] if snap["best_bid"] else [],
        "asks": [{"price": snap["best_ask"], "size": 1.0}] if snap["best_ask"] else [],
        "source": "ws-simulated",
    }


def _build_secondary_for_ai(snap: Dict[str, Any], force_support: Optional[bool] = None) -> Dict[str, Any]:
    """
    Simulate an Anodos-style secondary view.
    In real use this would come from external_data.AnodosFinanceProvider.
    For the placeholder we occasionally "let secondary see value" on thin on-chain
    books — exactly the scenario the 150-fill run is hitting (on-chain L1 thin
    but secondary depth/mid suggests the edge may still be skimmable for rake).
    """
    spread = snap["book_spread_pct"]
    # Heuristic: on very thin on-chain books (<0.08%), sometimes secondary
    # still shows decent liquidity (the case where AI micro-signal helps most).
    liq = 0.72 if spread < 0.08 else 0.48
    mid = (snap["best_bid"] + snap["best_ask"]) / 2.0 if snap["best_bid"] and snap["best_ask"] else None

    if force_support is True:
        liq = max(liq, 0.68)
    elif force_support is False:
        liq = min(liq, 0.42)

    return {
        "mid_price": mid,
        "liquidity_score": round(liq, 2),
        "source": "anodos-sim",
        "age_s": 4.0,
    }


def _build_run_context(snap: Dict[str, Any]) -> Dict[str, Any]:
    """Infer lightweight context from the historical reasons (toxicity, skew)."""
    reasons = " ".join(snap.get("reasons", [])).lower()
    toxicity = 0.28 if "toxic" in reasons else (0.18 if "favorable" in reasons else 0.22)
    inv_skew = 0.35 if "xrp_heavy" in reasons else (-0.30 if "rlusd_heavy" in reasons else 0.0)
    return {
        "inventory_skew": round(inv_skew, 2),
        "toxicity": round(toxicity, 2),
        "profile": "tight_spread",
    }


def _is_zero_edge_case(snap: Dict[str, Any]) -> bool:
    """Any cycle where the original engine generated 0 quotes.
    This is the full set of low-presence moments from the testing ground.
    The AI micro-signal (WS fresh + secondary) is asked: 'could we have safely
    had a non-off posture here for better rake without increasing toxic risk?'
    We do not require the exact 'edge thin' string — many 0-quote cycles in the
    current log are inventory/momentum/toxic guards on thin-ish books; all are
    opportunities for competitive presence improvement."""
    return snap.get("original_gen_quotes", -1) == 0


async def run_ai_on_zero_edge_cases(
    decisions_path: Path,
    analyzer: AIAnalyzer,
    simulate_ws_age_s: float = 1.2,
    secondary_support_rate: float = 0.35,
) -> Dict[str, Any]:
    """
    Core: for every historical 0-quote / edge-blocked cycle from the current
    testing-ground run, ask the AI analyzer (WS-fresh book + secondary + context)
    whether this was a skimmable rake opportunity.

    Returns counts + examples so we can quantify "AI micro-signal for good rake
    and competitive presence" without ever touching the main hard gate.
    """
    snapshots = _extract_historical_snapshots(decisions_path)

    zero_cases = [s for s in snapshots if _is_zero_edge_case(s)]
    total_zero = len(zero_cases)

    ai_skimmable = 0
    ai_suggested_relax = 0
    ai_near_posture = 0
    examples: List[Dict[str, Any]] = []

    for snap in zero_cases:
        book_state = _build_book_state_for_ai(snap, simulated_age_s=simulate_ws_age_s)

        # Occasionally give the analyzer a "helpful" secondary view (simulates
        # Anodos confirming value when on-chain L1 is thin — the exact signal
        # the current 150-fill run needs for more safe presence).
        use_support = (hash(str(snap["cycle"])) % 100) < (secondary_support_rate * 100)
        secondary = _build_secondary_for_ai(snap, force_support=use_support if use_support else None)
        ctx = _build_run_context(snap)

        analysis: AIAnalysis = await analyzer.analyze(
            book_state=book_state,
            secondary_data=secondary,
            run_context=ctx,
        )

        if analysis.is_truly_skimmable:
            ai_skimmable += 1
        if analysis.suggested_min_edge_adjust_pct < -0.005:
            ai_suggested_relax += 1
        if analysis.quote_posture in ("near", "at_touch", "spread_mid"):
            ai_near_posture += 1

        if len(examples) < 6 and (analysis.is_truly_skimmable or analysis.suggested_min_edge_adjust_pct < -0.005):
            examples.append({
                "cycle": snap["cycle"],
                "orig_spread": snap["book_spread_pct"],
                "ai_edge_q": round(analysis.edge_quality_score, 3),
                "ai_skimmable": analysis.is_truly_skimmable,
                "ai_adjust": round(analysis.suggested_min_edge_adjust_pct, 4),
                "ai_posture": analysis.quote_posture,
                "ai_conf": round(analysis.confidence, 2),
                "ai_rationale": analysis.rationale[:160],
                "source": analysis.source,
            })

    rate_skimmable = (ai_skimmable / total_zero * 100.0) if total_zero > 0 else 0.0
    rate_relax = (ai_suggested_relax / total_zero * 100.0) if total_zero > 0 else 0.0
    rate_posture = (ai_near_posture / total_zero * 100.0) if total_zero > 0 else 0.0

    return {
        "total_zero_edge_0quote_cases": total_zero,
        "ai_marked_truly_skimmable": ai_skimmable,
        "ai_suggested_min_edge_relax": ai_suggested_relax,
        "ai_recommended_non_off_posture": ai_near_posture,
        "pct_skimmable": round(rate_skimmable, 1),
        "pct_relax": round(rate_relax, 1),
        "pct_non_off_posture": round(rate_posture, 1),
        "examples": examples,
        "note": (
            "AI (micro-structure only) run on exact historical 0-quote / edge-thin cycles "
            "from the current long-run testing ground. Inputs = simulated WS-fresh book "
            "(low age) + occasional Anodos secondary confirmation + run context. "
            "Not trend; only 'is this thin book paying real rake right now?' for better "
            "competitive presence and spread capture when safe."
        ),
        "analyzer": analyzer.__class__.__name__,
    }


def _get_analyzer(name: str) -> AIAnalyzer:
    name = (name or "stub").lower()
    if name in ("stub", "stubai", "heuristic"):
        return StubAIAnalyzer()
    if name in ("local", "local-llm", "local-stub"):
        return LocalLLMAnalyzer(model="phi3:mini")
    if name in ("api", "remote", "api-llm", "api-stub"):
        return APIAIAnalyzer()
    return StubAIAnalyzer()


async def _async_main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Run AI micro-structure analysis placeholder over the long-run 0-quote / hard-gate cases"
    )
    parser.add_argument("--decisions", default="logs/decisions.jsonl", help="Path to long-run decisions.jsonl")
    parser.add_argument(
        "--analyzer",
        default="stub",
        choices=["stub", "local", "local-stub", "api", "api-stub"],
        help="Which analyzer to use (stub = fast heuristic stand-in for local model; local/api for the real placeholders)",
    )
    parser.add_argument("--ws-age", type=float, default=1.2, help="Simulated WS book age in seconds (fresh)")
    parser.add_argument("--secondary-support-rate", type=float, default=0.35, help="Fraction of cases where secondary 'confirms' value")
    parser.add_argument("--export-training", action="store_true", help="Also write ai_training_examples.jsonl with features + hard gate labels + trade outcomes for real LLM training / Grok API labeling")
    args = parser.parse_args(argv)

    decisions_path = Path(args.decisions)
    if not decisions_path.exists():
        print(f"ERROR: {decisions_path} not found. Run from repo root.")
        sys.exit(1)

    analyzer = _get_analyzer(args.analyzer)
    print(f"Running AI analysis placeholder on {decisions_path} using {analyzer.__class__.__name__} ...")
    print("Focus: micro rake / edge quality on the exact 0-offer thin-book cycles from the current testing ground run.")
    print("Not trend following. Competitive dominance via better safe presence when secondary + fresh book support it.\n")

    result = await run_ai_on_zero_edge_cases(
        decisions_path,
        analyzer,
        simulate_ws_age_s=args.ws_age,
        secondary_support_rate=args.secondary_support_rate,
    )

    print("=== AI Analysis Placeholder — Replay on Current Long-Run Data ===")
    for k in [
        "total_zero_edge_0quote_cases",
        "ai_marked_truly_skimmable",
        "ai_suggested_min_edge_relax",
        "ai_recommended_non_off_posture",
        "pct_skimmable",
        "pct_relax",
        "pct_non_off_posture",
        "analyzer",
    ]:
        print(f"  {k}: {result.get(k)}")

    print("\nExample AI micro-signals on original hard 0-quote cases (first few where AI saw skimmable/relax):")
    for ex in result.get("examples", []):
        print(f"  cycle {ex['cycle']}: spread {ex['orig_spread']:.3f}% -> edge_q={ex['ai_edge_q']}, skimmable={ex['ai_skimmable']}, adjust={ex['ai_adjust']}, posture={ex['ai_posture']}, conf={ex['ai_conf']}")
        print(f"    rationale: {ex['ai_rationale']}")

    print("\n" + result.get("note", ""))
    print("\nInterpretation for speed + competitive MM (user goal: good rake, competitive dominance, not trending):")
    print("  - Local analyzer (small model via Ollama/llama.cpp) is suitable for in-loop / replay use (<100 ms on tiny context of L1 spread + age + secondary liq + skew + toxicity).")
    print("  - API analyzer is for offline batch ('explain the 984 cases from this run', richer rationales, training labels for a future distilled model).")
    print("  - Even a modest real % of safe flips on the marginal thin-book cycles = more good spread capture (rake) + higher safe presence (Tier C) on exactly the conditions the current long run is exposing.")
    print("  - The hard gate + policy on main (grok-tier-2-collab) stay the deterministic safety net. This is purely advisory micro-signal.")
    print("  - Next: pick local (speed) or api (power), replace the heuristic block inside LocalLLMAnalyzer with a real model call, re-run on the same 984-case corpus (and future 150-fill snapshots) to tune conservatism.")

    # Optional: export clean training examples for real LLM training / Grok API labeling
    if args.export_training:
        export_path = decisions_path.parent / "ai_training_examples.jsonl"
        export_training_examples(decisions_path, export_path)
        print(f"\nExported training-ready examples to {export_path} (features + hard_gate label + outcome proxies).")


def export_training_examples(decisions_path: Path, out_path: Path) -> None:
    """
    Export a clean JSONL of training examples from the long run.

    Each line has:
      - cycle, book features (l1_spread, best bid/ask, mid)
      - context (inventory from policy text, toxicity hints, momentum)
      - original_decision (hard_gate_fired, gen_quotes, full policy snippet)
      - outcome_proxy (did we later see a fill on/near this cycle? positive capture in trades)
      - suggested_for_ai (what the current placeholder thought)

    This is exactly the labeled data you can feed to Grok API (for high-quality
    chain-of-thought labels + feature ideas) or use to fine-tune / distill a local
    small model. The "how xledgermate is supposed to run" patterns live here:
    when the hard gate + guards were correct vs when a slightly more aggressive
    posture on a thin book would have produced good rake.
    """
    snapshots = _extract_historical_snapshots(decisions_path)

    # Very rough join to trades for outcome labels (cycle number is the link)
    trades_by_cycle: Dict[int, List[Dict]] = {}
    trades_file = decisions_path.parent / "trades_2026-06.csv"
    if trades_file.exists():
        with trades_file.open(newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    c = int(row.get("cycle") or 0)
                except Exception:
                    continue
                if c:
                    trades_by_cycle.setdefault(c, []).append({
                        "side": row.get("side"),
                        "profit_xrp_equiv": row.get("profit_xrp_equiv"),
                        "notes": row.get("notes", "")[:120],
                    })

    examples = []
    for snap in snapshots:
        reasons_blob = " ".join(snap.get("reasons", []))
        hard_gate = (
            "edge thin" in reasons_blob.lower()
            or "l1 too tight" in reasons_blob.lower()
            or "market_edge_met=false" in reasons_blob.lower()
            or "hard gate" in reasons_blob.lower()
            or snap.get("original_gen_quotes") == 0 and snap.get("original_edge_met") is False
        )

        ctx = _build_run_context(snap)
        trades = trades_by_cycle.get(snap.get("cycle", -1), [])
        positive_capture = any(
            (t.get("profit_xrp_equiv") or "0") > "0" or "spread capture ~+" in (t.get("notes") or "")
            for t in trades
        )
        any_fill_on_cycle = bool(trades)

        ex = {
            "cycle": snap.get("cycle"),
            "features": {
                "book_l1_spread_pct": snap["book_spread_pct"],
                "best_bid": snap["best_bid"],
                "best_ask": snap["best_ask"],
                "inventory_skew": ctx["inventory_skew"],
                "toxicity_proxy": ctx["toxicity"],
            },
            "original": {
                "gen_quotes": snap.get("original_gen_quotes"),
                "edge_met": snap.get("original_edge_met"),
                "hard_gate_fired": hard_gate,
                "policy_snippet": reasons_blob[:350],
            },
            "outcome": {
                "any_fill_on_this_cycle": any_fill_on_cycle,
                "positive_capture_seen": positive_capture,
                "trade_count": len(trades),
            },
            "ai_stub_view": {
                # What the current lightweight placeholder would have suggested
                # (you will replace this with real model output later)
            },
        }
        examples.append(ex)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    print(f"Exported {len(examples)} examples (including ~{sum(1 for e in examples if e['original']['hard_gate_fired'])} hard-gate-ish cases).")


def main(argv: Optional[List[str]] = None) -> None:
    asyncio.run(_async_main(argv))


if __name__ == "__main__":
    main()
