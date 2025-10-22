#!/usr/bin/env python3
"""
Force-sell a token balance held by the wallet using the Broker.
Usage:
  python scripts/force_sell.py <token_mint>
"""
import sys
import json
from typing import Optional

from tradingSystem.broker_optimized import Broker
from tradingSystem.config_optimized import RPC_URL, WALLET_SECRET

from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey

try:
    from spl.token.instructions import get_associated_token_address
except Exception:
    get_associated_token_address = None  # Container should have spl-token; fallback available


def load_keypair(secret: str) -> Keypair:
    sec = secret.strip()
    try:
        if sec.startswith("["):
            arr = json.loads(sec)
            return Keypair.from_bytes(bytes(arr))
        import base58 as b58
        return Keypair.from_bytes(b58.b58decode(sec))
    except Exception as e:
        raise RuntimeError(f"Invalid TS_WALLET_SECRET: {e}")


def get_token_ui_amount(rpc: Client, owner: Pubkey, mint: Pubkey) -> float:
    # Preferred: get associated token account and read balance
    try:
        if get_associated_token_address is not None:
            ata = get_associated_token_address(owner, mint)
            resp = rpc.get_token_account_balance(ata)
            if hasattr(resp, "value") and resp.value and hasattr(resp.value, "ui_amount"):
                return float(resp.value.ui_amount or 0)
    except Exception:
        pass

    # Fallback: enumerate token accounts by owner and pick max uiAmount
    try:
        accts = rpc.get_token_accounts_by_owner(owner, {"mint": str(mint)})
        vals = getattr(accts, "value", []) or []
        best = 0.0
        for v in vals:
            data = getattr(v.account, "data", None)
            parsed = getattr(data, "parsed", None) if data else None
            if isinstance(parsed, dict):
                amt = parsed.get("info", {}).get("tokenAmount", {}).get("uiAmount", 0)
                best = max(best, float(amt or 0))
        return best
    except Exception:
        return 0.0


def main() -> int:
    if len(sys.argv) < 2:
        print("ERR: missing token mint argument")
        return 2
    token_mint_str = sys.argv[1].strip()

    rpc = Client(RPC_URL)
    kp = load_keypair(WALLET_SECRET)
    owner = kp.pubkey()
    mint = Pubkey.from_string(token_mint_str)

    ui_amount = get_token_ui_amount(rpc, owner, mint)
    print(f"[FORCE-SELL] {token_mint_str[:8]} balance={ui_amount}")
    if ui_amount <= 0:
        print("[FORCE-SELL] No balance to sell. Done.")
        return 0

    br = Broker()
    fill = br.market_sell(token_mint_str, ui_amount)
    print(f"[FORCE-SELL] result: success={fill.success} usd={fill.usd} price={fill.price} tx={fill.tx} err={fill.error}")
    return 0 if fill.success else 1


if __name__ == "__main__":
    raise SystemExit(main())


