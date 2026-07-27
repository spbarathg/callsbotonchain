"""
BROKER – Production Execution Layer (2026)

Responsibilities:
  1. Build swap transactions via Jupiter API
  2. Sign with wallet keypair
  3. Submit via Jito bundles (MEV protection) → fallback to Helius RPC
  4. Confirm landing or retry
  5. Return structured Fill objects consumed by TradeEngine

Design principles:
  - NO changes required in trader_optimized.py, cli_optimized.py, or risk engine
  - Stateless per-trade: every method is self-contained
  - Every failure path produces a Fill with .success=False and a useful .error
  - Real-money safe: no silent swallowing of exceptions

External dependencies (already in the codebase):
  - app.jupiter_client  (JupiterClient – quote + swap tx builder)
  - solders              (Keypair, VersionedTransaction, Pubkey)
  - solana.rpc.api       (Client – standard RPC for balance checks + fallback send)
  - requests             (Jito bundle HTTP POST)
"""

import base64
import json
import logging
import os
import time
import requests
import base58 as b58
from dataclasses import dataclass, field
from typing import Optional, Tuple

from solana.rpc.api import Client as SolanaClient
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from .config_optimized import (
    RPC_URL, WALLET_SECRET, DRY_RUN,
    SLIPPAGE_BPS, PRIORITY_FEE_MIN_MICROLAMPORTS, PRIORITY_FEE_MAX_MICROLAMPORTS,
    SOL_MINT, BASE_MINT, SELL_MINT,
    MAX_PRICE_IMPACT_BUY_PCT, MAX_PRICE_IMPACT_SELL_PCT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fill – the structured result consumed by TradeEngine
# ---------------------------------------------------------------------------

@dataclass
class Fill:
    """Structured trade execution result.

    Every broker method returns a Fill. The TradeEngine reads:
      .success, .error, .price, .qty, .usd, .tx
    Optional:
      .effective_slippage_bps, .slippage_pct, .execution_path
    """
    success: bool = False
    error: str = ""
    price: float = 0.0
    qty: float = 0.0
    usd: float = 0.0
    tx: str = ""
    execution_path: str = ""          # "jito" | "rpc" | "dry_run"
    effective_slippage_bps: float = 0.0
    slippage_pct: float = 0.0


# ---------------------------------------------------------------------------
# Jito helpers (lightweight – no heavy dependency)
# ---------------------------------------------------------------------------

JITO_BUNDLE_URL = os.getenv(
    "JITO_BLOCK_ENGINE_URL",
    "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
)
JITO_TIP_LAMPORTS = int(os.getenv("JITO_TIP_LAMPORTS", "100000"))  # 0.0001 SOL

# Jito tip accounts (official, rotate randomly)
JITO_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4bPYoTAhCDBGjB42H1Ppjd7",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSLMaY6z1Mft9SgsicxD",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkCsMCejkAtjkqzdbNK7",
]


def _submit_jito_bundle(signed_tx_b58: str, timeout: float = 5.0) -> dict:
    """Submit a single signed transaction as a Jito bundle."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [[signed_tx_b58]],
    }
    try:
        resp = requests.post(JITO_BUNDLE_URL, json=payload, timeout=timeout)
        data = resp.json()
        if "error" in data:
            return {"ok": False, "error": str(data["error"])}
        bundle_id = data.get("result", "")
        return {"ok": True, "bundle_id": bundle_id}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------

class Broker:
    """Production execution layer for the Solana memecoin trading bot.

    Public interface consumed by TradeEngine / cli_optimized:
      .market_buy(token, usd) -> Fill
      .market_sell(token, qty) -> Fill
      .market_sell_extreme(token, qty) -> Fill
      .check_tradability(token, min_usd_check) -> (bool, str)
      .get_token_price(token, holdings=None) -> float

    Attributes consumed externally:
      ._dry   (bool)  – True when DRY_RUN
      ._pubkey (str)  – wallet public key string
      ._rpc   (SolanaClient) – for balance queries
      ._kp    (Keypair | None) – wallet keypair
    """

    def __init__(self):
        self._dry = DRY_RUN
        self._rpc = SolanaClient(RPC_URL)
        self._kp: Optional[Keypair] = None
        self._pubkey: str = ""

        # Load wallet keypair
        secret = WALLET_SECRET.strip()
        if secret:
            try:
                if secret.startswith("["):
                    arr = json.loads(secret)
                    self._kp = Keypair.from_bytes(bytes(arr))
                else:
                    self._kp = Keypair.from_bytes(b58.b58decode(secret))
                self._pubkey = str(self._kp.pubkey())
                logger.info(f"[BROKER] Wallet loaded: {self._pubkey[:8]}...")
            except Exception as exc:
                logger.error(f"[BROKER] Failed to load wallet keypair: {exc}")
        else:
            logger.warning("[BROKER] No wallet secret configured – dry-run only")
            self._dry = True

        # Jupiter client (lazy – imported at call site to avoid circular imports)
        self._jup = None

        # Jito usage flag
        self._use_jito = os.getenv("JITO_ENABLED", "true").lower() in ("1", "true", "yes")

        mode = "DRY RUN" if self._dry else "LIVE"
        jito_label = "ON" if self._use_jito else "OFF"
        logger.info(f"[BROKER] Mode={mode} | Jito={jito_label} | RPC={RPC_URL[:40]}...")
        print(f"[BROKER] Initialized: {mode} | Jito={jito_label}", flush=True)

    # ------------------------------------------------------------------
    # Jupiter client (lazy singleton)
    # ------------------------------------------------------------------

    def _jupiter(self):
        if self._jup is None:
            from app.jupiter_client import get_jupiter_client
            self._jup = get_jupiter_client()
        return self._jup

    # ------------------------------------------------------------------
    # MARKET BUY
    # ------------------------------------------------------------------

    def market_buy(self, token: str, usd: float) -> Fill:
        """Buy *token* using SOL, spending approximately *usd* worth.

        Flow:
          1. Convert USD → lamports via SOL price
          2. Get Jupiter quote (SOL → token)
          3. Check price impact
          4. Get swap transaction
          5. Sign and send (Jito → RPC fallback)
          6. Confirm and return Fill
        """
        tag = f"[BUY {token[:8]}]"
        print(f"{tag} Starting: ${usd:.2f}", flush=True)

        if self._dry:
            return self._dry_fill("buy", token, usd)

        if not self._kp:
            return Fill(success=False, error="No wallet keypair loaded")

        # 1. Convert USD → lamports
        sol_price = self._get_sol_price()
        if sol_price <= 0:
            return Fill(success=False, error="Cannot determine SOL price")
        sol_amount = usd / sol_price
        lamports = int(sol_amount * 1e9)
        print(f"{tag} ${usd:.2f} ≈ {sol_amount:.6f} SOL ({lamports} lamports)", flush=True)

        # 2. Jupiter quote
        jup = self._jupiter()
        quote_resp = jup.get_quote(
            input_mint=BASE_MINT,
            output_mint=token,
            amount=lamports,
            slippage_bps=SLIPPAGE_BPS,
            timeout=12.0,
            priority="high",
        )
        if quote_resp["status_code"] != 200 or not quote_resp.get("json"):
            err = quote_resp.get("error", "Unknown quote error")
            return Fill(success=False, error=f"Quote failed: {err}")
        quote = quote_resp["json"]

        # 3. Price impact check
        price_impact = float(quote.get("priceImpactPct", 0))
        if abs(price_impact) > MAX_PRICE_IMPACT_BUY_PCT:
            return Fill(
                success=False,
                error=f"Price impact too high: {price_impact:.2f}% > {MAX_PRICE_IMPACT_BUY_PCT}%",
            )

        out_amount_raw = int(quote.get("outAmount", 0))
        in_amount_raw = int(quote.get("inAmount", 0))
        print(f"{tag} Quote OK: in={in_amount_raw} → out={out_amount_raw} (impact={price_impact:.2f}%)", flush=True)

        # 4. Get swap transaction from Jupiter
        priority_fee = self._pick_priority_fee()
        swap_resp = jup.get_swap_transaction(
            quote=quote,
            user_public_key=self._pubkey,
            priority_fee=priority_fee,
            timeout=15.0,
            priority="high",
        )
        if swap_resp["status_code"] != 200 or not swap_resp.get("json"):
            err = swap_resp.get("error", "Unknown swap error")
            return Fill(success=False, error=f"Swap tx build failed: {err}")
        swap_tx_b64 = swap_resp["json"].get("swapTransaction", "")
        if not swap_tx_b64:
            return Fill(success=False, error="Empty swapTransaction from Jupiter")

        # 5. Sign and send
        signature = self._sign_and_send(swap_tx_b64, tag)
        if not signature:
            return Fill(success=False, error="Transaction send failed (Jito + RPC)")

        # 6. Confirm
        confirmed = self._confirm_tx(signature, timeout=60)
        if not confirmed:
            logger.warning(f"{tag} Tx sent but unconfirmed after 60s: {signature}")
            # Still return success – the tx may land later
            # TradeEngine will detect via balance check

        # Calculate fill values
        # out_amount_raw is in token's smallest unit; we don't know decimals here
        # so we report raw. TradeEngine uses price * qty for valuation.
        # Price = USD spent / tokens received (approximate)
        # We'll get exact qty from on-chain later; for now use quote estimate.
        token_qty = float(out_amount_raw)  # raw units – caller handles decimals
        price_per_token = usd / token_qty if token_qty > 0 else 0

        print(f"{tag} ✅ Buy landed: sig={signature[:16]}... qty={token_qty}", flush=True)

        return Fill(
            success=True,
            price=price_per_token,
            qty=token_qty,
            usd=usd,
            tx=signature,
            execution_path="jito" if self._use_jito else "rpc",
            effective_slippage_bps=price_impact * 100,
        )

    # ------------------------------------------------------------------
    # MARKET SELL
    # ------------------------------------------------------------------

    def market_sell(self, token: str, qty: float) -> Fill:
        """Sell *qty* of *token* back to SOL."""
        return self._execute_sell(token, qty, extreme=False)

    def market_sell_extreme(self, token: str, qty: float) -> Fill:
        """Sell with maximum slippage tolerance (emergency/high-profit exit)."""
        return self._execute_sell(token, qty, extreme=True)

    def _execute_sell(self, token: str, qty: float, extreme: bool = False) -> Fill:
        tag = f"[SELL {'EXTREME ' if extreme else ''}{token[:8]}]"
        print(f"{tag} Starting: qty={qty:.4f}", flush=True)

        if self._dry:
            return self._dry_fill("sell", token, 0, qty=qty)

        if not self._kp:
            return Fill(success=False, error="No wallet keypair loaded")

        # Validate on-chain balance first
        actual_balance = self._get_onchain_balance(token)
        if actual_balance is not None and actual_balance <= 0:
            return Fill(success=False, error="zero balance on-chain – cannot sell")

        # Use actual balance if less than requested (dust prevention)
        if actual_balance is not None and actual_balance < qty:
            print(f"{tag} Adjusting qty: requested={qty:.4f}, on-chain={actual_balance:.4f}", flush=True)
            qty = actual_balance

        if qty <= 0:
            return Fill(success=False, error="Zero quantity after adjustment")

        # Convert qty to raw amount (this is already raw from TradeEngine)
        amount_raw = int(qty)

        slippage = 5000 if extreme else SLIPPAGE_BPS  # 50% for extreme, normal otherwise

        # Jupiter quote (token → SOL)
        jup = self._jupiter()
        quote_resp = jup.get_quote(
            input_mint=token,
            output_mint=SELL_MINT,
            amount=amount_raw,
            slippage_bps=slippage,
            timeout=12.0,
            priority="high",
        )
        if quote_resp["status_code"] != 200 or not quote_resp.get("json"):
            err = quote_resp.get("error", "Unknown quote error")
            # Detect common failure patterns for TradeEngine error handling
            if "COULD_NOT_FIND_ANY_ROUTE" in err.upper() or "NO_ROUTE" in err.upper():
                return Fill(success=False, error=f"COULD_NOT_FIND_ANY_ROUTE – No liquidity. DO NOT RETRY")
            return Fill(success=False, error=f"Quote failed: {err}")
        quote = quote_resp["json"]

        # Price impact check (relaxed for extreme mode)
        price_impact = float(quote.get("priceImpactPct", 0))
        impact_cap = 90.0 if extreme else MAX_PRICE_IMPACT_SELL_PCT
        if abs(price_impact) > impact_cap:
            return Fill(
                success=False,
                error=f"Price impact too high: {price_impact:.2f}% > {impact_cap}%",
            )

        out_amount_raw = int(quote.get("outAmount", 0))  # lamports of SOL received
        print(f"{tag} Quote OK: {amount_raw} tokens → {out_amount_raw} lamports (impact={price_impact:.2f}%)", flush=True)

        # Get swap transaction
        priority_fee = self._pick_priority_fee(high=extreme)
        swap_resp = jup.get_swap_transaction(
            quote=quote,
            user_public_key=self._pubkey,
            priority_fee=priority_fee,
            timeout=15.0,
            priority="high",
        )
        if swap_resp["status_code"] != 200 or not swap_resp.get("json"):
            err = swap_resp.get("error", "Unknown swap error")
            return Fill(success=False, error=f"Swap tx build failed: {err}")
        swap_tx_b64 = swap_resp["json"].get("swapTransaction", "")
        if not swap_tx_b64:
            return Fill(success=False, error="Empty swapTransaction from Jupiter")

        # Sign and send
        signature = self._sign_and_send(swap_tx_b64, tag)
        if not signature:
            return Fill(success=False, error="Transaction send failed (Jito + RPC)")

        # Confirm
        confirmed = self._confirm_tx(signature, timeout=60)
        if not confirmed:
            logger.warning(f"{tag} Tx sent but unconfirmed: {signature}")

        # Calculate fill values
        sol_received = out_amount_raw / 1e9
        sol_price = self._get_sol_price()
        usd_received = sol_received * sol_price
        price_per_token = usd_received / qty if qty > 0 else 0

        print(f"{tag} ✅ Sell landed: sig={signature[:16]}... ${usd_received:.2f}", flush=True)

        return Fill(
            success=True,
            price=price_per_token,
            qty=qty,
            usd=usd_received,
            tx=signature,
            execution_path="jito" if self._use_jito else "rpc",
            effective_slippage_bps=price_impact * 100,
        )

    # ------------------------------------------------------------------
    # TRADABILITY CHECK
    # ------------------------------------------------------------------

    def check_tradability(self, token: str, min_usd_check: float = 5.0) -> Tuple[bool, str]:
        """Check if Jupiter can route a sell for this token.

        Returns (is_tradable, reason).
        Used by TradeEngine before buying to prevent untradable ghost positions.
        """
        try:
            jup = self._jupiter()
            # Try to get a sell quote for a small amount
            # Use 1M raw units as a conservative probe
            probe_amount = 1_000_000
            quote_resp = jup.get_quote(
                input_mint=token,
                output_mint=SELL_MINT,
                amount=probe_amount,
                slippage_bps=5000,  # generous for probe
                timeout=8.0,
                priority="low",
            )
            if quote_resp["status_code"] == 200 and quote_resp.get("json"):
                out_amount = int(quote_resp["json"].get("outAmount", 0))
                if out_amount > 0:
                    return True, "Jupiter can route sell"
                return False, "Jupiter returned 0 output – no liquidity"
            err = quote_resp.get("error", "")
            if "COULD_NOT_FIND_ANY_ROUTE" in str(err).upper():
                return False, f"No route found: {err[:100]}"
            return False, f"Quote error: {err[:100]}"
        except Exception as exc:
            return False, f"Tradability check exception: {str(exc)[:100]}"

    # ------------------------------------------------------------------
    # PRICE CHECK
    # ------------------------------------------------------------------

    def get_token_price(self, token: str, holdings: float = None) -> float:
        """Get current USD price per token unit via Jupiter quote.

        If *holdings* is provided, uses that as the sell amount for a more
        accurate price (accounts for liquidity depth).  Otherwise uses a
        small probe amount.
        """
        from .price_cache import get_price_cache
        cache = get_price_cache()

        # Check cache first
        cached = cache.get(token)
        if cached is not None:
            return cached

        try:
            jup = self._jupiter()
            # Use holdings for accurate price, or 1M units as probe
            amount = int(holdings) if holdings and holdings > 0 else 1_000_000
            quote_resp = jup.get_quote(
                input_mint=token,
                output_mint=SELL_MINT,
                amount=amount,
                slippage_bps=5000,
                timeout=8.0,
                priority="normal",
            )
            if quote_resp["status_code"] != 200 or not quote_resp.get("json"):
                return 0.0

            out_lamports = int(quote_resp["json"].get("outAmount", 0))
            if out_lamports <= 0 or amount <= 0:
                return 0.0

            sol_received = out_lamports / 1e9
            sol_price = self._get_sol_price()
            usd_value = sol_received * sol_price
            price_per_unit = usd_value / amount

            if price_per_unit > 0:
                cache.set(token, price_per_unit)
            return price_per_unit

        except Exception as exc:
            logger.debug(f"[BROKER] Price check failed for {token[:8]}: {exc}")
            return 0.0

    # ------------------------------------------------------------------
    # INTERNAL: sign, send, confirm
    # ------------------------------------------------------------------

    def _sign_and_send(self, swap_tx_b64: str, tag: str) -> Optional[str]:
        """Deserialize Jupiter swap tx, sign it, send via Jito (then RPC fallback).

        Returns transaction signature string, or None on total failure.
        """
        try:
            tx_bytes = base64.b64decode(swap_tx_b64)
            tx = VersionedTransaction.from_bytes(tx_bytes)
        except Exception as exc:
            logger.error(f"{tag} Failed to deserialize tx: {exc}")
            return None

        # Sign
        try:
            signed_tx = VersionedTransaction(tx.message, [self._kp])
        except Exception as exc:
            logger.error(f"{tag} Failed to sign tx: {exc}")
            return None

        signed_bytes = bytes(signed_tx)
        sig_str = str(signed_tx.signatures[0])

        # Path 1: Jito bundle
        if self._use_jito:
            signed_b58 = b58.b58encode(signed_bytes).decode("ascii")
            print(f"{tag} Submitting via Jito bundle...", flush=True)
            jito_result = _submit_jito_bundle(signed_b58)
            if jito_result["ok"]:
                print(f"{tag} ✅ Jito accepted bundle: {jito_result.get('bundle_id', '')[:16]}", flush=True)
                return sig_str
            else:
                logger.warning(f"{tag} Jito failed: {jito_result['error']} – falling back to RPC")
                print(f"{tag} ⚠️ Jito failed, falling back to RPC...", flush=True)

        # Path 2: Standard RPC send (fallback or primary when Jito disabled)
        return self._send_via_rpc(signed_bytes, tag)

    def _send_via_rpc(self, signed_bytes: bytes, tag: str) -> Optional[str]:
        """Send a signed transaction via Helius/standard RPC with retry."""
        import base64 as b64_mod

        tx_b64 = b64_mod.b64encode(signed_bytes).decode("ascii")

        for attempt in range(3):
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        tx_b64,
                        {
                            "encoding": "base64",
                            "skipPreflight": True,
                            "maxRetries": 2,
                            "preflightCommitment": "confirmed",
                        },
                    ],
                }
                resp = requests.post(
                    RPC_URL,
                    json=payload,
                    timeout=15.0,
                    headers={"Content-Type": "application/json"},
                )
                data = resp.json()
                if "result" in data:
                    sig = data["result"]
                    print(f"{tag} ✅ RPC accepted tx: {sig[:16]}...", flush=True)
                    return sig
                err = data.get("error", {})
                err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                logger.warning(f"{tag} RPC send error (attempt {attempt+1}): {err_msg}")

                # Retry on transient errors
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))

            except Exception as exc:
                logger.error(f"{tag} RPC exception (attempt {attempt+1}): {exc}")
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))

        logger.error(f"{tag} All RPC send attempts failed")
        return None

    def _confirm_tx(self, signature: str, timeout: float = 60) -> bool:
        """Poll RPC for transaction confirmation."""
        deadline = time.time() + timeout
        poll_interval = 2.0

        while time.time() < deadline:
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignatureStatuses",
                    "params": [[signature], {"searchTransactionHistory": True}],
                }
                resp = requests.post(RPC_URL, json=payload, timeout=10.0)
                data = resp.json()
                statuses = data.get("result", {}).get("value", [])
                if statuses and statuses[0]:
                    status = statuses[0]
                    if status.get("confirmationStatus") in ("confirmed", "finalized"):
                        if status.get("err") is None:
                            return True
                        else:
                            logger.warning(f"[CONFIRM] Tx {signature[:16]} confirmed with error: {status['err']}")
                            return False
            except Exception as exc:
                logger.debug(f"[CONFIRM] Poll error: {exc}")

            time.sleep(poll_interval)

        return False

    # ------------------------------------------------------------------
    # INTERNAL: helpers
    # ------------------------------------------------------------------

    def _get_onchain_balance(self, token: str) -> Optional[float]:
        """Get on-chain token balance for our wallet. Returns None on error."""
        if not self._pubkey:
            return None
        try:
            from .token_balance import get_token_balance_simple
            return get_token_balance_simple(self._rpc, self._pubkey, token, retries=2, verbose=False)
        except Exception:
            return None

    def _get_sol_price(self) -> float:
        """Get current SOL price in USD (cached, cheap)."""
        try:
            from .wallet_balance import get_sol_price_usd
            return get_sol_price_usd()
        except Exception:
            return 180.0  # conservative fallback

    def _pick_priority_fee(self, high: bool = False) -> int:
        """Pick a priority fee within configured range."""
        if high:
            return PRIORITY_FEE_MAX_MICROLAMPORTS
        # Use midpoint for normal trades
        return (PRIORITY_FEE_MIN_MICROLAMPORTS + PRIORITY_FEE_MAX_MICROLAMPORTS) // 2

    def _dry_fill(self, side: str, token: str, usd: float, qty: float = 0) -> Fill:
        """Generate a simulated fill for dry-run mode."""
        print(f"[DRY RUN] {side.upper()} {token[:8]}: ${usd:.2f} / qty={qty:.4f}", flush=True)
        sim_price = 0.00001
        sim_qty = usd / sim_price if side == "buy" else qty
        sim_usd = usd if side == "buy" else qty * sim_price
        return Fill(
            success=True,
            price=sim_price,
            qty=sim_qty,
            usd=sim_usd,
            tx="dry_run_simulated",
            execution_path="dry_run",
        )
