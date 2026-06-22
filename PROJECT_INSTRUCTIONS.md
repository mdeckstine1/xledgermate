# xLedgerMate - Project Instructions

**Project Name**: xLedgerMate (Trading Bot Alpha)  
**Version**: 1.0.0 (new strategy)  
**Branch**: `alpha`  
**Strategy**: Automated Value Accumulation System (Balanced Aggressive)  
**Network**: Mainnet from start (dry_run defaults to true)  
**Deployment**: Cursor-managed VPS

## Core Goals
Build a clean, maintainable trading bot that buys XRP on relative weakness and sells into RLUSD on strength using limit orders and bracket management. Goal is to grow total portfolio value (XRP + RLUSD) over time.

Key features from the Technical Specification:
- Limit orders only
- Application-level bracket (TP + SL) with selective trailing on breakouts
- Liquidity-aware sizing (depth checks)
- Strong operator control via YAML config
- Telegram as primary reporting channel
- Dry-run / live trading switch in config (easy to flip)
- Preserve existing XRPL address, RLUSD trustline, secret key loading hooks, and YAML config location/pattern

## Coding Standards (Follow Strictly)
- Clean, readable, Pythonic code with type hints everywhere.
- Use modern Python (3.11+), dataclasses or Pydantic for models.
- Follow the existing code style and structure from Ashigaru-Shoshin where we are reusing components (connectors, config, Telegram, risk).
- Never log or expose secret keys / seeds.
- Use xrpl-py properly for offers, account monitoring, and async WebSocket.
- Prioritize security, error handling, and dry-run safety.
- Structured logging for all decisions, orders, fills, and cancellations.
- Make functions focused and well-documented.

## Config & Secrets Rules
- Keep the existing YAML config file location and loading pattern unchanged.
- Preserve the secret key / wallet loading hooks exactly as they currently exist.
- Add a clear boolean switch (e.g. `dry_run: true` or `live_trading_enabled: false`) in the config.
- Operator should be able to flip between dry-run and live without code changes.

## Reuse Guidelines
- Reuse: wallet loading, connectors, Telegram reporting, risk/kill-switch framework, logging, YAML config system.
- New / Replace: Strategy logic, DecisionEngine, OrderManager (bracket + OCO), liquidity depth calculations, new report formats.

## Safety Rules (Mainnet)
- Dry-run must be the safe default.
- All order submission paths must respect the dry-run switch.
- Strong pre-flight checks and kill switches must be present.
- Conservative default sizing until operator tunes the config.

## Cursor / Development Workflow
- Keep all work on the `alpha` branch.
- When in doubt, prioritize safety, clarity, and reuse of existing solid components.
- Always produce clean, type-hinted, production-grade code.

You are Grok helping build xLedgerMate (Trading Bot Alpha). Stay strictly on track with these instructions. When the user gives a new task, reference these rules and the original Technical Specification for the strategy.
