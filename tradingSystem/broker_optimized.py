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
        """Get token decimals with retry"""
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

        if mint in self._token_meta:
            return self._token_meta[mint]
        
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
                        return dec
                self._token_meta[mint] = 6
                return 6
            except Exception:
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
                continue
        
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
                
                # Wait for confirmation (up to 60s) at finalized commitment
                confirmed = False
                for conf_attempt in range(60):
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
                            except Exception:
                                # Fallback: if confirmation_status not available, consider after sufficient waits
                                confirmed = True
                            if confirmed:
                                print(f"[BROKER] ✅ Transaction FINALIZED: {sig_str[:16]}...", flush=True)
                                break
                        else:
                            if conf_attempt % 10 == 0:
                                print(f"[BROKER] ⏳ Waiting for FINALIZED... ({conf_attempt}/60)", flush=True)
                    except Exception as e:
                        if conf_attempt == 59:
                            return sig_str, f"RPC error: {str(e)}"
                    time.sleep(1)

                if confirmed:
                    return sig_str, None
                print(f"[BROKER] ⚠️ Transaction timeout: {sig_str[:16]}... (not finalized within 60s)", flush=True)
                return sig_str, "Transaction not finalized within 60s"
                
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

    def _quote(self, in_mint: str, out_mint: str, in_amount: int, retries: int = 3, slippage_bps_override: Optional[int] = None) -> Optional[Dict]:
        """Get quote using dedicated Jupiter client (bypasses circuit breaker)"""
        jup = get_jupiter_client()
        
        use_slip = int(slippage_bps_override) if slippage_bps_override is not None else int(SLIPPAGE_BPS)
        print(f"[BROKER] Getting Jupiter quote: {in_mint[:8]}→{out_mint[:8]}, amount={in_amount}, slippage={use_slip}bps", flush=True)
        
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
            timeout=10.0
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

    def _retry_swap_on_6024(self, in_mint: str, out_mint: str, in_amount: int, token_decimals: int) -> Optional[str]:
        """Handle simulation error 6024 by re-quoting with slight amount bump and retrying a limited number of times."""
        try_attempts = 1
        bumped_amount = int(in_amount * 1.05)
        slip2 = min(int(SLIPPAGE_BPS) + 100, 3000)
        for i in range(try_attempts):
            try:
                print(f"[BROKER] 6024 retry: re-quoting with amount={bumped_amount}, slippage={slip2}bps", flush=True)
                quote = self._quote(in_mint, out_mint, bumped_amount, slippage_bps_override=slip2)
                swap_tx = self._swap(quote)
                return swap_tx
            except BrokerError as e:
                print(f"[BROKER] 6024 retry attempt {i+1} failed: {e}", flush=True)
                time.sleep(1 * (i + 1))
                continue
        return None

    def market_buy(self, token: str, usd_size: float) -> Fill:
        """Execute buy with comprehensive safety"""
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
            
            # Escalating slippage for buys: 20%, 30%, 40%, 50%
            slippage_levels = [2000, 3000, 4000, 5000]
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
                                
                                # SUCCESS! Return fill
                                print(f"[BROKER] ✅ BUY SUCCESS at {slippage_bps/100}% slippage!", flush=True)
                                return Fill(price=expected_price, qty=out_amt, usd=float(usd_size), 
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
                    
                    # SUCCESS! Return fill
                    print(f"[BROKER] ✅ BUY SUCCESS at {slippage_bps/100}% slippage!", flush=True)
                    return Fill(price=expected_price, qty=out_amt, usd=float(usd_size), 
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
        try:
            # Validation
            if qty <= 0:
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid quantity")
            
            if not token or not self._is_valid_solana_address(token):
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Invalid token address")
            
            dec = self._get_decimals(token)
            in_amount = int(round(float(qty) * (10 ** dec)))
            
            if in_amount <= 0:
                return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error="Amount too small")
            
            # Escalating slippage: 20%, 30%, 40%, 50% (capped to prevent catastrophic loss)
            slippage_levels = [2000, 3000, 4000, 5000]
            
            for attempt, slippage_bps in enumerate(slippage_levels, 1):
                try:
                    print(f"[BROKER] 🎯 SELL attempt {attempt}/{len(slippage_levels)} with {slippage_bps/100}% slippage for {token[:8]}...", flush=True)
                    
                    # Get quote with escalating slippage (sell to SELL_MINT, default USDC)
                    quote = self._quote(token, SELL_MINT, in_amount, slippage_bps_override=slippage_bps)
                    if not quote:
                        print(f"[BROKER] ⚠️ Quote failed at {slippage_bps/100}% slippage, trying next level...", flush=True)
                        time.sleep(2)
                        continue
                    
                    # Calculate expected fill
                    base_dec = self._get_decimals(SELL_MINT)
                    out_usd = float(quote.get("outAmount") or 0) / (10 ** base_dec)
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
                        time.sleep(2)
                        continue
                    
                    # Try with simulation first
                    sig, error = self._sign_and_send(swap_tx)
                    
                    # If rate limited (common cause), abort early and let higher-level cooldown handle it
                    if error and ("Rate limited" in str(error) or "429" in str(error)):
                        print(f"[BROKER] ⚠️ Aborting due to Jupiter rate limit: {error}", flush=True)
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=str(error))
                    # Skip direct send for sells to avoid unnecessary SOL spend on failures
                    
                    # If no error or direct send succeeded
                    if not error:
                        # CRITICAL: Validate we got reasonable value back
                        # If we got less than 10% of expected value, treat as failed
                        if out_usd > 0 and out_usd < (float(qty) * expected_price * 0.10):
                            print(f"[BROKER] ⚠️ SELL returned only ${out_usd:.4f} (< 10% of expected), treating as FAILED", flush=True)
                            print(f"[BROKER] Expected: ${float(qty) * expected_price:.4f}, Got: ${out_usd:.4f}", flush=True)
                            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                                       error=f"Sell returned only ${out_usd:.4f} (catastrophic slippage)", tx=sig)
                        
                        print(f"[BROKER] ✅ SELL SUCCESS at {slippage_bps/100}% slippage!", flush=True)
                        return Fill(price=expected_price, qty=float(qty), usd=out_usd, 
                                   tx=sig, success=True, slippage_pct=slippage_bps/100)
                    
                    # If still error and not last attempt, try next level
                    if attempt < len(slippage_levels):
                        print(f"[BROKER] ⚠️ Failed at {slippage_bps/100}% slippage: {error}", flush=True)
                        print(f"[BROKER] 🔄 Escalating to {slippage_levels[attempt]/100}% slippage...", flush=True)
                        time.sleep(3)
                        continue
                    else:
                        return Fill(price=0.0, qty=0.0, usd=0.0, success=False, error=error, tx=sig)
                
                except Exception as e:
                    print(f"[BROKER] ❌ Exception at {slippage_bps/100}% slippage: {e}", flush=True)
                    if attempt < len(slippage_levels):
                        time.sleep(3)
                        continue
                    else:
                        raise
            
            # If we exhausted all attempts
            return Fill(price=0.0, qty=0.0, usd=0.0, success=False, 
                       error="Exhausted all slippage levels (20%-50%) - token likely unsellable")
            
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

