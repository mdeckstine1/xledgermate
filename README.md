# xledgermate

XRPL XRP/RLUSD market-making bot focused on:
- strict risk-capital isolation (Bot Account only)
- transparent perception (volatility, liquidity, effective spreads)
- profile-based control (`safe`, `high_volatility`, `thin_liquidity`, `tight_spread`)

## Quick start

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Configure bot wallet in `config/config.yaml`:
   - `bot_account_address`
   - `bot_secret_key` (never commit real secrets)
3. Run:
   - `python main.py`
   - GUI: `streamlit run gui/streamlit_gui.py`

## Versioning

- Current version: `1.0.0`
- Canonical source: `VERSION`
- Runtime constant: `core/version.py` (`VERSION`)
