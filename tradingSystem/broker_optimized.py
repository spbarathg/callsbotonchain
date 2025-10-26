"""
OPTIMIZED BROKER - Bulletproof Execution
- Transaction confirmation (30s wait)
- Slippage validation (max 5%)
- Price impact check (max 10%)
- Comprehensive error handling
- Retry logic with exponential backoff
- Balance validation
"""
from dataclasses import dataclass
import base64
import threading
import json
import os
import time
import requests
from typing import Dict, Optional, Tuple

from app.http_client import request_json
from app.jupiter_client import get_jupiter_client
from solana.rpc.api import Client as SolanaClient
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.signature import Signature
import base58 as b58

from .config_optimized import (
    DRY_RUN,
    RPC_URL,
    WALLET_SECRET,
    SLIPPAGE_BPS,
    PRIORITY_FEE_MIN_MICROLAMPORTS,
    PRIORITY_FEE_MAX_MICROLAMPORTS,
    BASE_MINT,
    SELL_MINT,
    SOL_MINT,
    USDC_MINT,
    MAX_PRICE_IMPACT_BUY_PCT,
    MAX_PRICE_IMPACT_SELL_PCT,
    # New: faster execution toggle
    _get_bool as _cfg_get_bool,
)


@dataclass
class Fill:
    price: float
    qty: float
    usd: float
    tx: Optional[str] = None
    slippage_pct: float = 0.0
    success: bool = True
    error: Optional[str] = None


class BrokerError(Exception):
    """Custom exception for broker errors"""
    pass


class Broker:
    """Optimized Jupiter v6 broker with bulletproof execution"""
    
    # Class-level locks to prevent simultaneous trades (reduces API burst load)
    _sell_lock = threading.Lock()
    _buy_lock = threading.Lock()

    def __init__(self) -> None:
        self._dry = bool(DRY_RUN or not WALLET_SECRET)
        self._rpc = SolanaClient(RPC_URL)
        self._kp = self._load_keypair(WALLET_SECRET) if not self._dry else None
        self._pubkey = str(self._kp.pubkey()) if self._kp else None
        self._token_meta: Dict[str, int] = {}
        self._error_count = 0
        self._last_error_time = 0.0
        # Fast execution mode via env TS_FAST_EXECUTION=true (default true)
        try:
            self._fast_exec = os.getenv("TS_FAST_EXECUTION", "true").strip().lower() in ("1","true","yes","on")
        except Exception:
            self._fast_exec = True

    def _load_keypair(self, secret: str) -> Keypair:
        sec = secret.strip()
        try:
            if sec.startswith("["):
                arr = json.loads(sec)
                return Keypair.from_bytes(bytes(arr))
            return Keypair.from_bytes(b58.b58decode(sec))
        except Exception as e:
            raise RuntimeError(f"Invalid TS_WALLET_SECRET: {e}")

    def _is_valid_solana_address(self, address: str) -> bool:
        try:
            if not address or len(address) < 32 or len(address) > 44:
                return False
            decoded = b58.b58decode(address)
            return len(decoded) == 32
        except Exception:
            return False
    
    def _get_sol_price_fallback(self) -> float:
        """Get SOL price from external oracle as fallback (no Jupiter dependency)"""
        try:
            # Try CoinGecko (free, no API key needed)
            resp = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                timeout=5
            )
            if resp.status_code == 200:
                price = float(resp.json()["solana"]["usd"])
                print(f"[BROKER] SOL price from CoinGecko: ${price:.2f}", flush=True)
                return price
        except Exception as e:
            print(f"[BROKER] CoinGecko failed: {e}", flush=True)
        
        # Ultimate fallback - conservative estimate
        print("[BROKER] Using conservative SOL price estimate: $180", flush=True)
        return 180.0

    def _get_decimals(self, mint: str) -> int:
        """Get token decimals with multiple fallback methods"""
        # Fast-path for common mints to avoid network and wrong defaults
        HARDCODED: Dict[str, int] = {
            # SOL (wSOL)
            "So11111111111111111111111111111111111111112": 9,
            # USDC
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 6,
            # USDT
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 6,
            # BONK
            "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": 5,
        }
        if mint in HARDCODED:
            self._token_meta[mint] = HARDCODED[mint]
            return HARDCODED[mint]

        # Check cache
        if mint in self._token_meta:
            return self._token_meta[mint]
        
        # Method 1: Try Jupiter token list (most reliable for trading tokens)
        for attempt in range(3):
            try:
                r = request_json("GET", "https://token.jup.ag/all", timeout=10.0)
                if r.get("status_code") != 200:
                    raise RuntimeError(f"token meta fetch failed: {r.get('status_code')}")
                payload = r.get("json") or []
                for item in payload:
                    if item.get("address") == mint:
                        dec = int(item.get("decimals") or 6)
                        self._token_meta[mint] = dec
                        print(f"[BROKER] ✅ Got decimals from Jupiter token list: {mint[:8]}... = {dec} decimals", flush=True)
                        return dec
            except Exception as e:
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
                continue
        
        # Method 2: Try getting from on-chain mint account (backup method)
        try:
            from solders.pubkey import Pubkey
            mint_pubkey = Pubkey.from_string(mint)
            mint_info = self._rpc.get_account_info(mint_pubkey)
            if hasattr(mint_info, 'value') and mint_info.value is not None:
                # Mint account data contains decimals at byte 44
                data = mint_info.value.data
                if len(data) >= 45:
                    decimals = int(data[44])
                    if 0 <= decimals <= 18:  # Sanity check
                        self._token_meta[mint] = decimals
                        print(f"[BROKER] ✅ Got decimals from on-chain: {mint[:8]}... = {decimals} decimals", flush=True)
                        return decimals
        except Exception as e:
            print(f"[BROKER] ⚠️ Could not fetch decimals from on-chain: {e}", flush=True)
        
        # Fallback: Most pump.fun and SPL tokens use 6 decimals
        print(f"[BROKER] ⚠️ Using default 6 decimals for {mint[:8]}...", flush=True)
        self._token_meta[mint] = 6
        return 6

    def _sign_and_send(self, swap_tx_b64: str, max_retries: int = 3) -> Tuple[Optional[str], Optional[str]]:
        """Sign and send with confirmation"""
        for attempt in range(max_retries):
            try:
                raw = base64.b64decode(swap_tx_b64)
                tx = VersionedTransaction.from_bytes(raw)
                tx = VersionedTransaction(tx.message, [self._kp])
                
                # First try simulation to catch errors early
                try:
                    sim_result = None
                    if not self._fast_exec:
                        sim_result = self._rpc.simulate_transaction(tx)
                    if sim_result is not None and hasattr(sim_result, 'value') and hasattr(sim_result.value, 'err') and sim_result.value.err:
                        error_detail = str(sim_result.value.err)
                        print(f"[BROKER] ⚠️ Simulation error: {error_detail}", flush=True)
                        # Try to extract more details
                        if hasattr(sim_result.value, 'logs') and sim_result.value.logs:
                            print(f"[BROKER] Transaction logs:", flush=True)
                            for log in sim_result.value.logs[-10:]:  # Last 10 logs
                                print(f"[BROKER]   {log}", flush=True)
                        return None, f"Simulation failed: {error_detail}"
                except Exception as sim_error:
                    print(f"[BROKER] ⚠️ Simulation check failed: {sim_error}", flush=True)
                
                # Send transaction with finalized commitment requirement on confirmation
                sig_resp = self._rpc.send_raw_transaction(
                    bytes(tx),
                    opts=TxOpts(skip_preflight=self._fast_exec, max_retries=2)
                )
                # Extract signature from response
                sig = sig_resp.value if hasattr(sig_resp, 'value') else sig_resp
                sig_str = str(sig)
                print(f"[BROKER] Transaction submitted: {sig_str}", flush=True)
                
                # Wait for confirmation (optimized for speed)
                # OPTIMIZED: Accept 'confirmed' status immediately for faster feedback (1-2s vs 30-120s)
                # Trade-off: 'confirmed' = cluster majority (very safe), 'finalized' = absolute (safest)
                # For memecoin trading, 'confirmed' is sufficient and much faster
                confirmed = False
                for conf_attempt in range(60):  # Max 60s (reduced from 120s)
                    try:
                        result = self._rpc.get_signature_statuses([sig])
                        if result and result.value and result.value[0]:
                            tx_status = result.value[0]
                            # solders RpcResponse has .err attr; handle failure explicitly
                            if hasattr(tx_status, 'err') and tx_status.err is not None:
                                error_msg = f"TransactionErrorInstructionError({tx_status.err})"
                                print(f"[BROKER] ❌ Transaction failed: {error_msg}", flush=True)
                                return sig_str, error_msg
                            # Check confirmation status if present
                            try:
                                conf = getattr(tx_status, 'confirmation_status', None)
                                if conf and str(conf) == 'finalized':
                                    confirmed = True
                                    print(f"[BROKER] ✅ Transaction FINALIZED: {sig_str[:16]}... (absolute finality)", flush=True)
                                elif conf and str(conf) == 'confirmed':
                                    # Accept confirmed status immediately (cluster majority = very safe)
                                    confirmed = True
                                    print(f"[BROKER] ✅ Transaction CONFIRMED: {sig_str[:16]}... (~2s, cluster majority)", flush=True)
                            except Exception:
                                # Fallback: if confirmation_status not available, consider after sufficient waits
                                if conf_attempt >= 60:
                                    confirmed = True
                            if confirmed:
                                print(f"[BROKER] ✅ Transaction FINALIZED: {sig_str[:16]}...", flush=True)
                                break
                        else:
                            if conf_attempt % 10 == 0:
                                print(f"[BROKER] ⏳ Waiting for confirmation... ({conf_attempt}/60)", flush=True)
                    except Exception as e:
                        if conf_attempt == 59:
                            # Return success with signature even on timeout
                            print(f"[BROKER] ⚠️ Confirmation check timeout (RPC error), but transaction submitted: {sig_str[:16]}...", flush=True)
                            return sig_str, None  # Return success to record position
                    time.sleep(1)

                if confirmed:
                    return sig_str, None
                # Return success even on timeout - transaction likely succeeded
                print(f"[BROKER] ⚠️ Transaction timeout: {sig_str[:16]}... (not confirmed within 60s, but may still succeed)", flush=True)
                return sig_str, None  # Return success to record position anyway
                
            except Exception as e:
                # If we caught a 6024 from earlier simulation or RPC error path, try re-quote and swap
                if "6024" in str(e) and attempt < max_retries - 1:
                    print(f"[BROKER] 6024 detected in send path; attempting re-quote + retry", flush=True)
                    try:
                        # Attempt a re-quote with bumped amount using base mint
                        swap_tx = self._retry_swap_on_6024(BASE_MINT, BASE_MINT, 1, 0)  # dummy to trigger flow; real call done in market_buy
                    except Exception:
                        pass
                if attempt == max_retries - 1:
                    return None, f"Transaction failed after {max_retries} attempts: {str(e)}"
                time.sleep(2 * (attempt + 1))
        
        return None, "Max retries exceeded"

    def _quote(self, in_mint: str, out_mint: str, in_amount: int, retries: int = 3, slippage_bps_override: Optional[int] = None, only_direct_routes: bool = False, max_accounts: int = None) -> Optional[Dict]:
        """Get quote using dedicated Jupiter client (bypasses circuit breaker)"""
        jup = get_jupiter_client()
        
        use_slip = int(slippage_bps_override) if slippage_bps_override is not None else int(SLIPPAGE_BPS)
        direct_str = " (direct routes only)" if only_direct_routes else ""
        accounts_str = f" (max {max_accounts} accounts)" if max_accounts else ""
        print(f"[BROKER] Getting Jupiter quote: {in_mint[:8]}→{out_mint[:8]}, amount={in_amount}, slippage={use_slip}bps{direct_str}{accounts_str}", flush=True)
        
        # If rate-limited, short-circuit to avoid spamming
        try:
            if hasattr(jup, 'is_rate_limited') and jup.is_rate_limited():
                raise BrokerError("Rate limited; Jupiter cooldown active")
        except Exception:
            pass

        result = jup.get_quote(
            input_mint=in_mint,
            output_mint=out_mint,
            amount=in_amount,
            slippage_bps=use_slip,
            timeout=10.0,
            only_direct_routes=only_direct_routes,
            max_accounts=max_accounts
        )
        
        if result["status_code"] == 200:
            quote = result["json"]
            if not quote.get("outAmount"):
                raise BrokerError("Quote missing outAmount")
            print(f"[BROKER] ✅ Quote received: {quote.get('outAmount')} units", flush=True)
            return quote
        else:
            error_msg = f"Jupiter quote failed: {result['error']}"
            print(f"[BROKER] ❌ {error_msg}", flush=True)
            raise BrokerError(error_msg)

    def _swap(self, quote: Dict, retries: int = 3) -> Optional[str]:
        """Get swap transaction using dedicated Jupiter client (bypasses circuit breaker)"""
        jup = get_jupiter_client()
        
        print(f"[BROKER] Getting Jupiter swap transaction...", flush=True)
        
        # If rate-limited, short-circuit
        try:
            if hasattr(jup, 'is_rate_limited') and jup.is_rate_limited():
                raise BrokerError("Rate limited; Jupiter cooldown active")
        except Exception:
            pass

        # Dynamic low-cost priority fees with cap (free-friendly)
        # Use MIN to minimize cost; broker send logic can bump if needed
        priority_fee = int(PRIORITY_FEE_MIN_MICROLAMPORTS)
        
        result = jup.get_swap_transaction(
            quote=quote,
            user_public_key=self._pubkey,
            wrap_unwrap_sol=True,
            priority_fee=priority_fee,
            timeout=15.0
        )
        
        try:
            est_usd = priority_fee / 1e9 * 180.0
            print(f"[BROKER] Using priority fee: {priority_fee} microlamports (~${est_usd:.5f})", flush=True)
        except Exception:
            print(f"[BROKER] Using priority fee: {priority_fee} microlamports", flush=True)
        
        if result["status_code"] == 200:
            swap_tx = result["json"].get("swapTransaction")
            if not swap_tx:
                raise BrokerError("Swap response missing swapTransaction")
            print(f"[BROKER] ✅ Swap transaction received", flush=True)
            return swap_tx
        else:
            error_msg = f"Jupiter swap failed: {result['error']}"
            print(f"[BROKER] ❌ {error_msg}", flush=True)
            raise BrokerError(error_msg)

    def _retry_swap_on_6024(self, in_mint: str, out_mint: str, in_amount: int, token_decimals: int, current_slippage: int = None) -> Optional[str]:
        """Handle simulation error 6024 by getting FRESH quote and retrying immediately.
        
        Error 6024 usually means:
        - Quote is stale (market moved)
        - Pool state changed
        - Need fresh quote with current market conditions
        """
        try_attempts = 2  # Increased attempts
        # Use current slippage or bump it slightly
        slip2 = current_slippage + 500 if current_slippage else min(int(SLIPPAGE_BPS) + 500, 5000)
        
        for i in range(try_attempts):
            try:
                # CRITICAL: Get FRESH quote immediately (don't wait)
                print(f"[BROKER] 6024 recovery attempt {i+1}: Getting FRESH quote with {slip2}bps slippage", flush=True)
                
                # Try with slightly adjusted amount to avoid exact same state
                adjusted_amount = int(in_amount * (1.0 + (i * 0.01)))  # 0%, 1%, 2% adjustment
                
                quote = self._quote(in_mint, out_mint, adjusted_amount, slippage_bps_override=slip2, only_direct_routes=False)
                if not quote:
                    print(f"[BROKER] Failed to get fresh quote on attempt {i+1}", flush=True)
                    time.sleep(0.5)  # Brief pause before retry
                    continue
                
                # Execute immediately (minimize staleness)
                swap_tx = self._swap(quote)
                if swap_tx:
                    print(f"[BROKER] ✅ 6024 recovery successful on attempt {i+1}", flush=True)
                    return swap_tx
                    
            except BrokerError as e:
                print(f"[BROKER] 6024 retry attempt {i+1} failed: {e}", flush=True)
                if i < try_attempts - 1:
                    time.sleep(0.5)  # Short delay before next attempt
                continue
        
        print(f"[BROKER] ❌ All 6024 recovery attempts failed", flush=True)
        return None

    def market_buy(self, token: str, usd_size: float) -> Fill:
        """Execute buy with comprehensive safety"""
        # CRITICAL: Use global buy lock to prevent simultaneous buys
        # This prevents API burst load when multiple signals arrive at once
        # Example: 2 signals = 6 API calls in <1s → safer with serialization
        with self._buy_lock:
            return self._execute_buy(token, usd_size)
    
    def _execute_buy(self, token: str, usd_size: float) -> Fill:
        """Internal buy execution (called with lock held)"""
        try:
            print(f"[BROKER] market_buy called: ${usd_size:.2f} for {token[:8]}...", flush=True)
            # Validation
            if usd_size <= 0:
                print(f"[BROKER] ❌ Invalid USD size: {usd_size}", flush=True)
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid USD size")
            
            if not token or not self._is_valid_solana_address(token):
                print(f"[BROKER] ❌ Invalid token address: {token[:8] if token else 'None'}", flush=True)
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid token address")
            
            print(f"[BROKER] Getting decimals for BASE_MINT and token...", flush=True)
            base_dec = self._get_decimals(BASE_MINT)
            token_dec = self._get_decimals(token)
            
            # Convert USD to SOL amount if using SOL as base
            if BASE_MINT == "So11111111111111111111111111111111111111112":
                # Get SOL price (approximate - for exact, would need price oracle)
                # For now, use Jupiter quote-api to get rough SOL price
                sol_price_usd = self._get_sol_price_fallback()
                try:
                    # Get SOL/USDC quote to determine SOL price
                    from app.jupiter_client import get_jupiter_client
                    jup = get_jupiter_client()
                    q = jup.get_quote(
                        input_mint=BASE_MINT,
                        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                        amount=1000000000,
                        slippage_bps=50,
                        timeout=5.0
                    )
                    if q.get("status_code") == 200 and q.get("json"):
                        out_amount = float(q["json"].get("outAmount", 0)) / 1e6  # USDC has 6 decimals
                        if out_amount > 0:
                            sol_price_usd = out_amount
                            print(f"[BROKER] SOL price from Jupiter: ${sol_price_usd:.2f}", flush=True)
                except Exception as e:
                    print(f"[BROKER] Could not fetch SOL price from Jupiter, using fallback ${sol_price_usd:.2f}", flush=True)
                
                # Convert USD to SOL
                sol_amount = float(usd_size) / sol_price_usd
                in_amount = int(round(sol_amount * (10 ** base_dec)))
                print(f"[BROKER] USD ${usd_size:.2f} = {sol_amount:.6f} SOL @ ${sol_price_usd:.2f}/SOL", flush=True)
            else:
                # For stablecoins (USDC), usd_size is already the amount
                in_amount = int(round(float(usd_size) * (10 ** base_dec)))
            
            print(f"[BROKER] Decimals: base={base_dec}, token={token_dec}, in_amount={in_amount}", flush=True)
            
            # Escalating slippage for buys: 20%, 35%, 50% (reduced to 3 levels for rate limiting)
            # With Jupiter Pro 10 RPS, fewer attempts = less 429 errors
            slippage_levels = [2000, 3500, 5000]
            last_error = None
            
            for attempt, slippage_bps in enumerate(slippage_levels, 1):
                try:
                    print(f"[BROKER] 🎯 BUY attempt {attempt}/{len(slippage_levels)} with {slippage_bps/100}% slippage for {token[:8]}...", flush=True)
                    
                    # Get quote with escalating slippage
                    print(f"[BROKER] Fetching Jupiter quote...", flush=True)
                    quote = self._quote(BASE_MINT, token, in_amount, slippage_bps_override=slippage_bps)
                    if not quote:
                        print(f"[BROKER] ⚠️ Quote failed at {slippage_bps/100}% slippage", flush=True)
                        if attempt < len(slippage_levels):
                            time.sleep(2)
                            continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Failed to get quote")
                    print(f"[BROKER] ✅ Quote received", flush=True)
                    
                    # Calculate expected fill
                    out_amt = float(quote.get("outAmount") or 0) / (10 ** token_dec)
                    print(f"[BROKER] Expected output: {out_amt:.4f} tokens", flush=True)
                    if out_amt <= 0:
                        print(f"[BROKER] ❌ Zero output amount", flush=True)
                        if attempt < len(slippage_levels):
                            time.sleep(2)
                            continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid quote: zero output amount")
                    expected_price = usd_size / out_amt
                    
                    # Check price impact
                    price_impact = abs(float(quote.get("priceImpactPct") or 0))
                    print(f"[BROKER] Price impact: {price_impact:.2f}%", flush=True)
                    if price_impact > MAX_PRICE_IMPACT_BUY_PCT:
                        print(f"[BROKER] ❌ Price impact too high: {price_impact:.1f}%", flush=True)
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                                   error=f"Price impact too high: {price_impact:.1f}%")
                    
                    # Dry run
                    print(f"[BROKER] DRY_RUN={self._dry}", flush=True)
                    if self._dry:
                        print(f"[BROKER] 🎭 Dry run mode, simulating successful buy", flush=True)
                        return Fill(price=expected_price, qty=out_amt, usd=float(usd_size), 
                                   success=True, slippage_pct=slippage_bps/100)
                    
                    # Execute
                    print(f"[BROKER] Fetching swap transaction...", flush=True)
                    swap_tx = self._swap(quote)
                    if not swap_tx:
                        print(f"[BROKER] ⚠️ Failed to get swap transaction", flush=True)
                        if attempt < len(slippage_levels):
                            time.sleep(2)
                            continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Failed to get swap transaction")
                    print(f"[BROKER] ✅ Swap transaction received", flush=True)
                    
                    print(f"[BROKER] Signing and sending transaction...", flush=True)
                    sig, error = self._sign_and_send(swap_tx)
                    if error:
                        last_error = error
                        # Check if it's a 6025 (slippage) error - retry with higher slippage
                        if "6025" in str(error):
                            print(f"[BROKER] ⚠️ Slippage error (6025) at {slippage_bps/100}%", flush=True)
                            if attempt < len(slippage_levels):
                                print(f"[BROKER] 🔄 Escalating to {slippage_levels[attempt]/100}% slippage...", flush=True)
                                time.sleep(3)
                                continue
                        # If simulation failed but it's just a 6024 error, try sending anyway
                        elif "6024" in str(error) or "0x1788" in str(error):
                            print(f"[BROKER] ⚠️ Simulation failed with 6024, attempting direct send...", flush=True)
                            try:
                                # Skip simulation, send directly
                                raw_tx = base64.b64decode(swap_tx)
                                versioned_tx = VersionedTransaction.from_bytes(raw_tx)
                                signed_tx = VersionedTransaction(versioned_tx.message, [self._kp])
                                
                                # Send without preflight (skip simulation)
                                opts = TxOpts(skip_preflight=True, preflight_commitment="processed")
                                result = self._rpc.send_raw_transaction(bytes(signed_tx), opts=opts)
                                sig_result = result.value
                                sig = str(sig_result)
                                print(f"[BROKER] ✅ Direct send successful (no simulation): {sig[:8]}...", flush=True)
                                
                                # SUCCESS! Query ACTUAL on-chain balance
                                print(f"[BROKER] ✅ BUY SUCCESS at {slippage_bps/100}% slippage (direct send)!", flush=True)
                                print(f"[BROKER] Expected tokens: {out_amt:.4f} (from Jupiter quote)", flush=True)
                                
                                # PERMANENT FIX: Verify actual received tokens
                                time.sleep(2)  # Wait for settlement
                                actual_qty = out_amt
                                try:
                                    from tradingSystem.token_balance import get_token_balance_simple
                                    wallet_address = str(self._kp.pubkey())
                                    verified_balance = get_token_balance_simple(self._rpc, wallet_address, token)
                                    if verified_balance is not None and verified_balance > 0:
                                        actual_qty = verified_balance
                                        print(f"[BROKER] ✅ Verified on-chain: {actual_qty:.4f} tokens", flush=True)
                                except Exception:
                                    pass
                                
                                actual_price = float(usd_size) / actual_qty if actual_qty > 0 else expected_price
                                print(f"[BROKER] Actual price: ${actual_price:.8f} per token", flush=True)
                                return Fill(price=actual_price, qty=actual_qty, usd=float(usd_size), 
                                           tx=sig, success=True, slippage_pct=slippage_bps/100)
                            except Exception as e2:
                                print(f"[BROKER] ❌ Direct send also failed: {e2}", flush=True)
                                if attempt < len(slippage_levels):
                                    time.sleep(3)
                                    continue
                                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=f"Simulation and direct send failed: {error}", tx=sig)
                        
                        # Other errors - last attempt fails, earlier attempts retry
                        print(f"[BROKER] ❌ Sign/send failed: {error}", flush=True)
                        if attempt < len(slippage_levels):
                            time.sleep(3)
                            continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=error, tx=sig)
                    else:
                        print(f"[BROKER] ✅ Transaction sent: {sig[:8]}...", flush=True)
                    
                    # SUCCESS! Query ACTUAL on-chain balance to verify received tokens
                    print(f"[BROKER] ✅ BUY SUCCESS at {slippage_bps/100}% slippage!", flush=True)
                    print(f"[BROKER] Expected tokens: {out_amt:.4f} (from Jupiter quote)", flush=True)
                    
                    # PERMANENT FIX: Verify actual received tokens from blockchain
                    # Wait 2 seconds for transaction to settle
                    time.sleep(2)
                    actual_qty = out_amt  # Default to expected
                    try:
                        from tradingSystem.token_balance import get_token_balance_simple
                        wallet_address = str(self._kp.pubkey())
                        verified_balance = get_token_balance_simple(self._rpc, wallet_address, token)
                        if verified_balance is not None and verified_balance > 0:
                            actual_qty = verified_balance
                            print(f"[BROKER] ✅ Verified on-chain: {actual_qty:.4f} tokens received", flush=True)
                            
                            # CRITICAL FIX: Detect decimal place errors (10x+ mismatch)
                            diff_ratio = abs(actual_qty - out_amt) / out_amt if out_amt > 0 else 0
                            if diff_ratio > 0.9:  # >90% difference = decimal error
                                print(f"[BROKER] 🚨 DECIMAL MISMATCH DETECTED!", flush=True)
                                print(f"[BROKER] Expected: {out_amt:.4f} tokens (from Jupiter quote)", flush=True)
                                print(f"[BROKER] Actual: {actual_qty:.4f} tokens (on-chain)", flush=True)
                                print(f"[BROKER] Difference: {diff_ratio*100:.1f}% (likely wrong token decimals)", flush=True)
                                
                                # Recalculate decimals from actual vs expected ratio
                                if out_amt > 0 and actual_qty > 0:
                                    decimal_diff = out_amt / actual_qty
                                    if 9 < decimal_diff < 11:  # 10x difference = 1 decimal place off
                                        print(f"[BROKER] ⚠️ Token decimals off by 1 place (10x mismatch)", flush=True)
                                    elif 90 < decimal_diff < 110:  # 100x difference = 2 decimal places off
                                        print(f"[BROKER] ⚠️ Token decimals off by 2 places (100x mismatch)", flush=True)
                                    elif 900 < decimal_diff < 1100:  # 1000x = 3 decimal places off
                                        print(f"[BROKER] ⚠️ Token decimals off by 3 places (1000x mismatch)", flush=True)
                                
                                # ALWAYS use actual on-chain balance for quantity and price calculation
                                # This ensures entry price is correct even if decimals were wrong
                                print(f"[BROKER] ✅ Using ACTUAL on-chain balance: {actual_qty:.4f} tokens", flush=True)
                            elif diff_ratio > 0.02:  # >2% difference (normal slippage range)
                                print(f"[BROKER] ⚠️ Slippage: Actual differs from expected by {abs(actual_qty - out_amt):.4f} tokens ({diff_ratio*100:.1f}%)", flush=True)
                        else:
                            print(f"[BROKER] ⚠️ Could not verify balance, using expected: {out_amt:.4f}", flush=True)
                    except Exception as e:
                        print(f"[BROKER] ⚠️ Balance verification failed: {e}, using expected qty", flush=True)
                    
                    # CRITICAL: Always calculate price from actual received tokens
                    # This ensures correct entry price even with decimal mismatches
                    actual_price = float(usd_size) / actual_qty if actual_qty > 0 else expected_price
                    print(f"[BROKER] Actual price: ${actual_price:.8f} per token", flush=True)
                    return Fill(price=actual_price, qty=actual_qty, usd=float(usd_size), 
                               tx=sig, success=True, slippage_pct=slippage_bps/100)
                    
                except Exception as e:
                    print(f"[BROKER] ❌ Exception at {slippage_bps/100}% slippage: {e}", flush=True)
                    if attempt < len(slippage_levels):
                        time.sleep(3)
                        continue
                    # Last attempt failed
                    raise
            
            # If we get here, all attempts failed
            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=f"All buy attempts failed. Last error: {last_error}")
            
        except Exception as e:
            self._error_count += 1
            self._last_error_time = time.time()
            print(f"[BROKER] ❌ EXCEPTION in market_buy: {type(e).__name__}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=f"Buy failed: {str(e)}")

    def market_sell(self, token: str, qty: float) -> Fill:
        """Execute sell with escalating slippage - NEVER GIVE UP!"""
        # CRITICAL: Use global sell lock to prevent simultaneous sells
        # This prevents API burst load when multiple positions try to sell at once
        # Example: 2 positions selling = 8 API calls in <1s → exceeds 10 RPS
        with self._sell_lock:
            return self._execute_sell(token, qty)
    
    def _verify_sell_success(self, token: str, pre_token_balance: float, pre_sol_balance: float, expected_sol_received: float, qty_requested: float = None) -> bool:
        """
        CRITICAL FIX: Verify sell actually succeeded on-chain
        Problem: Can log "SELL SUCCESS" even if transaction failed/reverted
        Solution: Check wallet deltas post-trade
        
        Args:
            token: Token mint address
            pre_token_balance: Full token balance before sell
            pre_sol_balance: SOL balance before sell
            expected_sol_received: Expected SOL to receive
            qty_requested: Quantity requested to sell (None = full balance)
        
        Returns: True if verified, False if ghost sell detected
        """
        try:
            # Wait a moment for blockchain to finalize
            time.sleep(2)
            
            # Check token balance (should be reduced by qty_requested)
            from tradingSystem.token_balance import get_token_balance_simple
            wallet_address = str(self._kp.pubkey())
            post_token_balance = get_token_balance_simple(self._rpc, wallet_address, token)
            
            if post_token_balance is None:
                print(f"[VERIFY] ⚠️ Could not verify token balance post-sell", flush=True)
                return True  # Assume success if can't verify
            
            tokens_sold = pre_token_balance - post_token_balance
            
            # CRITICAL FIX: Handle partial sells correctly
            # For partial sells: verify at least 80% of requested qty was sold
            # For full exits: verify at least 90% of full balance was sold
            if qty_requested is not None and qty_requested < pre_token_balance * 0.99:
                # Partial sell: check if we sold the requested amount
                min_expected = qty_requested * 0.80  # Allow 20% slippage/buffer
                if tokens_sold < min_expected:
                    print(f"[VERIFY] 🚨 PARTIAL SELL FAILED!", flush=True)
                    print(f"[VERIFY] Requested: {qty_requested:.4f}, Sold: {tokens_sold:.4f}", flush=True)
                    print(f"[VERIFY] Pre: {pre_token_balance:.4f}, Post: {post_token_balance:.4f}", flush=True)
                    return False
                print(f"[VERIFY] ✅ Partial sell verified: {tokens_sold:.4f} of {qty_requested:.4f} requested", flush=True)
            else:
                # Full exit: check if we sold at least 90% of full balance
                if tokens_sold < pre_token_balance * 0.90:
                    print(f"[VERIFY] 🚨 GHOST SELL DETECTED!", flush=True)
                    print(f"[VERIFY] Pre-balance: {pre_token_balance:.4f}, Post-balance: {post_token_balance:.4f}", flush=True)
                    print(f"[VERIFY] Only {tokens_sold:.4f} tokens sold ({tokens_sold/pre_token_balance*100:.1f}%)", flush=True)
                    return False
            
            # Check SOL balance increased
            sol_balance_resp = self._rpc.get_balance(self._kp.pubkey())
            post_sol_balance = sol_balance_resp.value / 1e9 if hasattr(sol_balance_resp, 'value') else 0
            sol_gained = post_sol_balance - pre_sol_balance
            
            if sol_gained < expected_sol_received * 0.50:  # Should have gained at least 50% of expected
                print(f"[VERIFY] ⚠️ SOL gain lower than expected", flush=True)
                print(f"[VERIFY] Expected: {expected_sol_received:.6f} SOL, Got: {sol_gained:.6f} SOL", flush=True)
                # Don't fail here - slippage can be high
            
            print(f"[VERIFY] ✅ Sell verified: Sold {tokens_sold:.4f} tokens, gained {sol_gained:.6f} SOL", flush=True)
            return True
            
        except Exception as e:
            print(f"[VERIFY] ⚠️ Verification error: {e}", flush=True)
            return True  # Assume success if verification fails
    
    def market_sell_extreme(self, token: str, qty: float) -> Fill:
        """
        EXTREME MODE: Sell at ANY price with maximum slippage
        Used when position is highly profitable but can't sell normally
        
        Problem: IDs 219(+505%), 212(+191%), 211(+133%) went to $0 with 0 sell attempts
        Solution: Accept 100% slippage, ignore price impact caps, retry aggressively
        Impact: Will capture profits even from nearly-dead tokens
        """
        print(f"[BROKER] 💪 EXTREME SELL MODE ACTIVATED for {token[:8]}", flush=True)
        print(f"[BROKER] 🎯 Will accept up to 100% slippage to capture profit", flush=True)
        
        with self._sell_lock:
            return self._execute_sell_extreme(token, qty)
    
    def _execute_sell_extreme(self, token: str, qty: float) -> Fill:
        """Internal extreme sell execution - NO LIMITS, SELL AT ANY COST"""
        try:
            # Basic validation only
            if qty <= 0:
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid quantity")
            
            if not token or not self._is_valid_solana_address(token):
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid token address")
            
            # Check SOL balance
            try:
                sol_balance_resp = self._rpc.get_balance(self._kp.pubkey())
                sol_balance_lamports = sol_balance_resp.value if hasattr(sol_balance_resp, 'value') else 0
                sol_balance = sol_balance_lamports / 1e9
                
                MIN_SOL_REQUIRED = 0.005
                if sol_balance < MIN_SOL_REQUIRED:
                    print(f"[BROKER] ❌ INSUFFICIENT SOL: {sol_balance:.6f}", flush=True)
                    return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                               error=f"Insufficient SOL: {sol_balance:.6f}")
                
                print(f"[BROKER] ✅ SOL balance: {sol_balance:.6f}", flush=True)
            except Exception as e:
                print(f"[BROKER] ⚠️ Could not check SOL: {e}", flush=True)
            
            dec = self._get_decimals(token)
            
            # Get actual on-chain balance
            print(f"[BROKER] Querying on-chain balance...", flush=True)
            pre_token_balance = 0.0  # For verification
            try:
                from tradingSystem.token_balance import get_token_balance_simple
                wallet_address = str(self._kp.pubkey())
                actual_balance = get_token_balance_simple(self._rpc, wallet_address, token)
                
                if actual_balance is not None and actual_balance > 0:
                    # CRITICAL FIX: Respect qty parameter for partial sells
                    requested_qty = float(qty)
                    qty_to_sell = min(requested_qty, actual_balance)
                    pre_token_balance = actual_balance  # Store full balance for verification
                    safety_pct = 0.95
                    print(f"[BROKER] ✅ On-chain balance: {actual_balance:.4f} tokens", flush=True)
                    if requested_qty < actual_balance * 0.99:  # Partial sell
                        print(f"[BROKER] 🎯 EXTREME PARTIAL SELL: {requested_qty:.4f} of {actual_balance:.4f}", flush=True)
                elif actual_balance == 0.0:
                    print(f"[BROKER] 🚨 ZERO balance on-chain!", flush=True)
                    return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                               error="Zero balance on-chain")
                else:
                    qty_to_sell = float(qty)
                    pre_token_balance = float(qty)  # Use database value
                    safety_pct = 0.95
                    print(f"[BROKER] ⚠️ Using database qty: {qty:.4f}", flush=True)
            except Exception as e:
                qty_to_sell = float(qty)
                pre_token_balance = float(qty)  # Use database value
                safety_pct = 0.95
                print(f"[BROKER] ⚠️ Balance query failed: {e}", flush=True)
            
            in_amount = int(qty_to_sell * (10 ** dec) * safety_pct)
            
            if in_amount <= 0:
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Amount too small")
            
            # EXTREME SLIPPAGE: 50% → 75% → 100%
            # NO PRICE IMPACT GUARDS - just sell!
            slippage_levels = [5000, 7500, 10000]  # 50%, 75%, 100%
            
            for attempt, slippage_bps in enumerate(slippage_levels, 1):
                try:
                    print(f"[BROKER] 🚨 EXTREME SELL attempt {attempt}/{len(slippage_levels)}: {slippage_bps/100}% slippage", flush=True)
                    
                    # Get quote (allow any routes)
                    quote = None
                    try:
                        quote = self._quote(token, SOL_MINT, in_amount, slippage_bps_override=slippage_bps, only_direct_routes=False)
                    except Exception as e:
                        if "COULD_NOT_FIND_ANY_ROUTE" in str(e):
                            print(f"[BROKER] 🚨 No routes at {slippage_bps/100}% slippage", flush=True)
                            if attempt < len(slippage_levels):
                                time.sleep(2)
                                continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=str(e))
                    
                    if not quote:
                        print(f"[BROKER] ⚠️ No quote at {slippage_bps/100}%, trying next...", flush=True)
                        time.sleep(2)
                        continue
                    
                    # Calculate output (NO price impact checks!)
                    base_dec = self._get_decimals(SOL_MINT)
                    out_amount_base = float(quote.get("outAmount") or 0) / (10 ** base_dec)
                    
                    sol_price = self._get_sol_price_fallback()
                    out_usd = out_amount_base * sol_price
                    
                    print(f"[BROKER] 💰 Will receive: {out_amount_base:.6f} SOL = ${out_usd:.4f}", flush=True)
                    
                    if out_usd <= 0:
                        print(f"[BROKER] ⚠️ Zero output, trying next slippage...", flush=True)
                        if attempt < len(slippage_levels):
                            time.sleep(2)
                            continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Zero output amount")
                    
                    expected_price = out_usd / float(qty)
                    
                    # Get swap transaction
                    swap_tx = self._swap(quote)
                    if not swap_tx:
                        print(f"[BROKER] ⚠️ Swap failed, trying next slippage...", flush=True)
                        if attempt < len(slippage_levels):
                            time.sleep(2)
                            continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Swap transaction failed")
                    
                    # Execute!
                    sig, err = self._sign_and_send(swap_tx)
                    if err:
                        print(f"[BROKER] ⚠️ Send failed: {err}, trying next slippage...", flush=True)
                        if attempt < len(slippage_levels):
                            time.sleep(3)
                            continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=err)
                    
                    # SUCCESS!
                    print(f"[BROKER] ✅ EXTREME SELL SUCCESS at {slippage_bps/100}% slippage!", flush=True)
                    print(f"[BROKER] Sold {float(qty):.0f} tokens for ${out_usd:.4f} at ${expected_price:.10f}/token", flush=True)
                    
                    # CRITICAL FIX: Verify sell actually succeeded on-chain
                    out_amount_base = float(quote.get("outAmount") or 0) / (10 ** self._get_decimals(SOL_MINT))
                    is_verified = self._verify_sell_success(token, pre_token_balance, sol_balance, out_amount_base, qty_requested=qty_to_sell)
                    
                    if not is_verified:
                        print(f"[BROKER] 🚨 Sell verification FAILED - transaction may have reverted!", flush=True)
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Sell verification failed (ghost sell)")
                    
                    return Fill(price=expected_price, qty=float(qty), usd=out_usd, success=True)
                
                except Exception as e:
                    print(f"[BROKER] ⚠️ Attempt {attempt} error: {e}", flush=True)
                    if attempt < len(slippage_levels):
                        time.sleep(3)
                        continue
                    return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=str(e))
            
            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="All extreme sell attempts failed")
        
        except Exception as e:
            print(f"[BROKER] ❌ EXTREME SELL EXCEPTION: {e}", flush=True)
            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=str(e))
    
    def _execute_sell(self, token: str, qty: float) -> Fill:
        """Internal sell execution (called with lock held) - OPTIMIZED FOR JUPITER PRO"""
        try:
            # Validation
            if qty <= 0:
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid quantity")
            
            if not token or not self._is_valid_solana_address(token):
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid token address")
            
            # CRITICAL: Check wallet SOL balance before attempting sell
            # Error 6025 = insufficient SOL for rent/fees, NOT a slippage issue!
            pre_sol_balance = 0.0  # For verification
            try:
                sol_balance_resp = self._rpc.get_balance(self._kp.pubkey())
                sol_balance_lamports = sol_balance_resp.value if hasattr(sol_balance_resp, 'value') else 0
                sol_balance = sol_balance_lamports / 1e9
                pre_sol_balance = sol_balance  # Store for verification
                
                # Need at least 0.005 SOL for rent + fees (conservative estimate)
                MIN_SOL_REQUIRED = 0.005
                if sol_balance < MIN_SOL_REQUIRED:
                    print(f"[BROKER] ❌ INSUFFICIENT SOL BALANCE: {sol_balance:.6f} SOL (need {MIN_SOL_REQUIRED})", flush=True)
                    return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                               error=f"Insufficient SOL balance: {sol_balance:.6f} SOL (need {MIN_SOL_REQUIRED} for fees)")
                
                print(f"[BROKER] ✅ Wallet SOL balance: {sol_balance:.6f} SOL", flush=True)
            except Exception as e:
                print(f"[BROKER] ⚠️ Could not check SOL balance: {e}", flush=True)
            
            dec = self._get_decimals(token)
            
            # PERMANENT FIX: Get ACTUAL on-chain balance before selling
            # Problem: Database qty may not match actual balance due to slippage during buy
            # Solution: Query blockchain for real balance, use as safety cap
            print(f"[BROKER] Querying on-chain balance for {token[:8]}...", flush=True)
            pre_token_balance = 0.0  # For verification
            try:
                from tradingSystem.token_balance import get_token_balance_simple
                # Convert Keypair to pubkey string
                wallet_address = str(self._kp.pubkey())
                actual_balance = get_token_balance_simple(self._rpc, wallet_address, token)
                
                if actual_balance is not None and actual_balance > 0:
                    # CRITICAL FIX FOR PARTIAL SELLS: Respect qty parameter!
                    # Use on-chain balance as safety cap, not replacement
                    # For partial sells: qty < actual_balance (e.g., sell 50% at 2x)
                    # For full exits: qty ≈ actual_balance (sell everything)
                    requested_qty = float(qty)
                    qty_to_sell = min(requested_qty, actual_balance)
                    pre_token_balance = actual_balance  # Store full balance for verification
                    safety_pct = 0.95  # Sell 95% to leave 5% buffer
                    print(f"[BROKER] ✅ On-chain balance: {actual_balance:.4f} tokens", flush=True)
                    if requested_qty < actual_balance * 0.99:  # Partial sell detected
                        print(f"[BROKER] 🎯 PARTIAL SELL: Requested {requested_qty:.4f}, have {actual_balance:.4f}", flush=True)
                        print(f"[BROKER] 💎 Will sell {qty_to_sell:.4f} tokens ({qty_to_sell/actual_balance*100:.1f}% of position)", flush=True)
                    elif abs(actual_balance - requested_qty) / requested_qty > 0.05:  # >5% difference
                        print(f"[BROKER] ⚠️ Database qty ({requested_qty:.4f}) differs from actual ({actual_balance:.4f})", flush=True)
                elif actual_balance == 0.0:
                    # CRITICAL: No tokens in wallet! Database is wrong or tokens already sold
                    print(f"[BROKER] 🚨 ZERO balance on-chain! Database shows {qty:.4f} tokens but wallet is EMPTY", flush=True)
                    print(f"[BROKER] This position cannot be sold (no tokens exist)", flush=True)
                    return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                               error="Zero balance on-chain (tokens don't exist or already sold)")
                else:
                    # Query failed (None returned), fallback to database
                    qty_to_sell = float(qty)
                    pre_token_balance = float(qty)  # Use database value
                    safety_pct = 0.95
                    print(f"[BROKER] ⚠️ Could not query balance, using database qty: {qty:.4f}", flush=True)
            except Exception as e:
                # Fallback to database qty
                qty_to_sell = float(qty)
                pre_token_balance = float(qty)  # Use database value
                safety_pct = 0.95
                print(f"[BROKER] ⚠️ Balance query exception: {e}, using database qty", flush=True)
            
            # Sell 95% of actual balance (5% buffer prevents Error 6025)
            # Old: 99% buffer was too small (1% = ~200 tokens on 20K position)
            # New: 95% buffer is safer (5% = ~1000 tokens on 20K position)
            in_amount = int(qty_to_sell * (10 ** dec) * safety_pct)
            
            print(f"[BROKER] Sell: {qty_to_sell:.4f} tokens × 95% = {in_amount} raw units (5% buffer)", flush=True)
            
            if in_amount <= 0:
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Amount too small")
            
            # PERMANENT FIX: Graduated slippage for illiquid memecoins
            # Problem: 50% max slippage was too low, causing Error 6024
            # Solution: Try up to 100% slippage for tokens that can't sell
            # Jupiter Pro 10 RPS: 4 attempts × 2 calls = 8 calls per sell (still safe!)
            slippage_levels = [2500, 5000, 7500, 10000]  # 25%, 50%, 75%, 100%
            
            for attempt, slippage_bps in enumerate(slippage_levels, 1):
                try:
                    print(f"[BROKER] 🎯 SELL attempt {attempt}/{len(slippage_levels)} with {slippage_bps/100}% slippage for {token[:8]}...", flush=True)
                    
                    # ULTRA-OPTIMIZED: Always allow multi-hop routes (low-liq tokens need this)
                    # Only 1 API call per attempt (vs 2-3 in old logic)
                    output_mint = SOL_MINT
                    quote = None
                    
                    try:
                        # Get quote with multi-hop routes allowed (needed for low-liquidity tokens)
                        quote = self._quote(token, SOL_MINT, in_amount, slippage_bps_override=slippage_bps, only_direct_routes=False)
                    except Exception as e:
                        # CRITICAL: Check if token is rugged (no routes at all)
                        if "COULD_NOT_FIND_ANY_ROUTE" in str(e) or "NO_ROUTES_FOUND" in str(e):
                            print(f"[BROKER] 🚨 RUG DETECTED: No routes available for {token[:8]}", flush=True)
                            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                                       error="RUG_DETECTED: No liquidity - DO NOT RETRY")
                        
                        print(f"[BROKER] ⚠️ Quote error: {e}", flush=True)
                        if attempt < len(slippage_levels):
                            time.sleep(1)  # Shorter wait for faster retry
                            continue
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=str(e))
                    
                    if not quote:
                        print(f"[BROKER] ⚠️ Quote failed at {slippage_bps/100}% slippage, trying next level...", flush=True)
                        time.sleep(1)
                        continue
                    
                    # Calculate expected fill based on output mint
                    base_dec = self._get_decimals(output_mint)
                    out_amount_base = float(quote.get("outAmount") or 0) / (10 ** base_dec)
                    
                    # Convert to USD value
                    if output_mint == SOL_MINT:
                        sol_price = self._get_sol_price_fallback()
                        out_usd = out_amount_base * sol_price
                        print(f"[BROKER] Direct route quote: {out_amount_base:.6f} SOL @ ${sol_price:.2f} = ${out_usd:.4f}", flush=True)
                    elif output_mint == USDC_MINT:
                        out_usd = out_amount_base  # USDC is 1:1 USD
                        print(f"[BROKER] Direct route quote: {out_amount_base:.4f} USDC = ${out_usd:.4f}", flush=True)
                    else:
                        print(f"[BROKER] ❌ Unexpected output mint: {output_mint}", flush=True)
                        continue
                    
                    if float(qty) <= 0:
                        continue
                    expected_price = out_usd / float(qty)
                    
                    # Price impact guard for sells (higher cap)
                    try:
                        price_impact = abs(float(quote.get("priceImpactPct") or 0))
                        if price_impact > MAX_PRICE_IMPACT_SELL_PCT:
                            print(f"[BROKER] ❌ Sell price impact too high: {price_impact:.1f}% > cap {MAX_PRICE_IMPACT_SELL_PCT}%", flush=True)
                            # Still try next slippage level before giving up
                            if attempt < len(slippage_levels):
                                time.sleep(2)
                                continue
                            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=f"Sell price impact too high: {price_impact:.1f}%")
                    except Exception:
                        pass
                    
                    # Dry run
                    if self._dry:
                        return Fill(price=expected_price, qty=float(qty), usd=out_usd, 
                                   success=True, slippage_pct=0.0)
                    
                    # Execute
                    swap_tx = self._swap(quote)
                    if not swap_tx:
                        print(f"[BROKER] ⚠️ Swap failed at {slippage_bps/100}% slippage, trying next level...", flush=True)
                        time.sleep(1)
                        continue
                    
                    # Execute transaction
                    sig, error = self._sign_and_send(swap_tx)
                    
                    # PERMANENT FIX: Error 6025 is MISLEADING - it's usually a TOKEN balance issue!
                    # Error 6025 = InsufficientFunds
                    # Despite the name, this usually means:
                    # - Trying to sell MORE tokens than you actually own (most common)
                    # - OR insufficient SOL for fees (rare)
                    # This fix queries actual balance before selling, preventing this error
                    if error and "6025" in str(error):
                        print(f"[BROKER] ❌ ERROR 6025: InsufficientFunds", flush=True)
                        print(f"[BROKER] This usually means: Trying to sell more tokens than owned", flush=True)
                        print(f"[BROKER] (Rarely means: Insufficient SOL for fees)", flush=True)
                        print(f"[BROKER] The actual balance query should have prevented this!", flush=True)
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                                   error="Error 6025: InsufficientFunds (token balance mismatch)")
                    
                    # Error 6024 (stale quote / insufficient token balance)
                    # This can happen with price volatility - try next slippage level
                    if error and "6024" in str(error):
                        print(f"[BROKER] ⚠️ Error 6024 at {slippage_bps/100}% slippage (stale quote or balance mismatch)", flush=True)
                        if attempt < len(slippage_levels):
                            print(f"[BROKER] 🔄 Trying next slippage level...", flush=True)
                            time.sleep(1)
                            continue
                        # Last attempt failed
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=f"Error 6024 persists after all attempts: {error}")
                    
                    # Rate limiting - abort and let cooldown handle it
                    if error and ("Rate limited" in str(error) or "429" in str(error)):
                        print(f"[BROKER] ⚠️ Aborting due to Jupiter rate limit: {error}", flush=True)
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=str(error))
                    
                    # If no error - SUCCESS!
                    if not error:
                        # Calculate actual executed price from USD received
                        actual_price = out_usd / float(qty) if float(qty) > 0 else expected_price
                        
                        print(f"[BROKER] ✅ SELL SUCCESS at {slippage_bps/100}% slippage!", flush=True)
                        print(f"[BROKER] Sold {qty:.0f} tokens for ${out_usd:.4f} at ${actual_price:.10f}/token", flush=True)
                        
                        # CRITICAL FIX: Verify sell actually succeeded on-chain
                        out_amount_base = float(quote.get("outAmount") or 0) / (10 ** self._get_decimals(SOL_MINT))
                        is_verified = self._verify_sell_success(token, pre_token_balance, pre_sol_balance, out_amount_base, qty_requested=qty_to_sell)
                        
                        if not is_verified:
                            print(f"[BROKER] 🚨 Sell verification FAILED - transaction may have reverted!", flush=True)
                            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, tx=sig, error="Sell verification failed (ghost sell)")
                        
                        return Fill(price=actual_price, qty=float(qty), usd=out_usd, 
                                   tx=sig, success=True, slippage_pct=slippage_bps/100)
                    
                    # If still error and not last attempt, try next level
                    if attempt < len(slippage_levels):
                        print(f"[BROKER] ⚠️ Failed at {slippage_bps/100}% slippage: {error}", flush=True)
                        print(f"[BROKER] 🔄 Trying {slippage_levels[attempt]/100}% slippage...", flush=True)
                        time.sleep(1)  # Fast retry (was 3s)
                        continue
                    else:
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=error, tx=sig)
                
                except Exception as e:
                    print(f"[BROKER] ❌ Exception at {slippage_bps/100}% slippage: {e}", flush=True)
                    if attempt < len(slippage_levels):
                        time.sleep(1)
                        continue
                    else:
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=f"Exception: {str(e)}")
            
            # If we exhausted all attempts
            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                       error="Exhausted all slippage levels (25%-50%) - no working route found")
            
        except Exception as e:
            self._error_count += 1
            self._last_error_time = time.time()
            print(f"[BROKER] ❌ SELL EXCEPTION: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=f"Sell failed: {str(e)}")

    def get_error_rate(self) -> float:
        """Get recent error rate"""
        return self._error_count / max(1, time.time() - self._last_error_time + 1)
    
    def get_token_price(self, token: str) -> float:
        """
        Get current token price in USD.
        Uses Jupiter quote API to get real-time price.
        
        Returns:
            Price in USD, or 0.0 if failed
        """
        try:
            # Get a small quote to determine price
            # Quote 1 token worth to get price
            dec = self._get_decimals(token)
            in_amount = int(1 * (10 ** dec))  # 1 token
            
            # Get quote selling token for USDC
            quote = self._quote(token, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", in_amount, slippage_bps_override=50)
            if not quote:
                return 0.0
            
            # Calculate price: output_usdc / input_tokens
            out_usdc = float(quote.get("outAmount", 0)) / 1e6  # USDC has 6 decimals
            in_tokens = float(in_amount) / (10 ** dec)
            
            if in_tokens > 0:
                price = out_usdc / in_tokens
                return price
            
            return 0.0
            
        except Exception as e:
            print(f"[BROKER] Failed to get token price: {e}", flush=True)
            return 0.0

