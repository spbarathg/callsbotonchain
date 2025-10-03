from dataclasses import dataclass
import base64
import json
from typing import Dict, Optional

import requests
from solana.rpc.api import Client as SolanaClient
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.signature import Signature
import base58 as b58

from .config import (
	DRY_RUN,
	RPC_URL,
	WALLET_SECRET,
	SLIPPAGE_BPS,
	PRIORITY_FEE_MICROLAMPORTS,
	BASE_MINT,
)


@dataclass
class Fill:
	price: float
	qty: float
	usd: float
	tx: Optional[str] = None


class Broker:
	"""Jupiter v6 execution broker. Falls back to dry-run when TS_DRY_RUN=true or wallet missing."""

	def __init__(self) -> None:
		self._dry = bool(DRY_RUN or not WALLET_SECRET)
		self._rpc = SolanaClient(RPC_URL)
		self._kp = self._load_keypair(WALLET_SECRET) if not self._dry else None
		self._pubkey = str(self._kp.pubkey()) if self._kp else None
		self._token_meta: Dict[str, int] = {}  # mint -> decimals cache

	def _load_keypair(self, secret: str) -> Keypair:
		sec = secret.strip()
		try:
			# JSON array of bytes
			if sec.startswith("["):
				arr = json.loads(sec)
				return Keypair.from_bytes(bytes(arr))
			# base58 string
			return Keypair.from_bytes(b58.b58decode(sec))
		except Exception as e:
			raise RuntimeError(f"Invalid TS_WALLET_SECRET: {e}")

	def _get_decimals(self, mint: str) -> int:
		if mint in self._token_meta:
			return self._token_meta[mint]
		try:
			# Free token list (cached by CDN)
			resp = requests.get("https://token.jup.ag/all", timeout=10)
			resp.raise_for_status()
			for item in resp.json():
				if item.get("address") == mint:
					dec = int(item.get("decimals") or 6)
					self._token_meta[mint] = dec
					return dec
		except Exception:
			pass
		# Fallback to 6
		self._token_meta[mint] = 6
		return 6

	def _sign_and_send(self, swap_tx_b64: str) -> str:
		raw = base64.b64decode(swap_tx_b64)
		tx = VersionedTransaction.from_bytes(raw)
		tx = VersionedTransaction(tx.message, [self._kp])  # type: ignore[arg-type]
		sig: Signature = self._rpc.send_raw_transaction(bytes(tx), opts=TxOpts(skip_preflight=True, max_retries=3))
		return str(sig)

	def _quote(self, in_mint: str, out_mint: str, in_amount: int) -> Dict:
		params = {
			"inputMint": in_mint,
			"outputMint": out_mint,
			"amount": str(in_amount),
			"slippageBps": str(int(SLIPPAGE_BPS)),
		}
		resp = requests.get("https://quote-api.jup.ag/v6/quote", params=params, timeout=10)
		resp.raise_for_status()
		return resp.json()

	def _swap(self, quote: Dict) -> str:
		payload = {
			"quoteResponse": quote,
			"userPublicKey": self._pubkey,
			"wrapAndUnwrapSol": True,
			"computeUnitPriceMicroLamports": int(PRIORITY_FEE_MICROLAMPORTS or 0),
			"dynamicComputeUnitLimit": True,
		}
		resp = requests.post("https://quote-api.jup.ag/v6/swap", json=payload, timeout=15)
		resp.raise_for_status()
		data = resp.json()
		return data.get("swapTransaction")

	def market_buy(self, token: str, usd_size: float) -> Fill:
		# token is output mint; base is USDC (BASE_MINT)
		base_dec = self._get_decimals(BASE_MINT)
		in_amount = int(round(float(usd_size) * (10 ** base_dec)))
		if self._dry:
			# Use quote for a better estimate even in dry-run
			q = self._quote(BASE_MINT, token, in_amount)
			out_amt = float(q.get("outAmount") or 0) / (10 ** self._get_decimals(token))
			qty = out_amt
			price = (usd_size / max(qty, 1e-9))
			return Fill(price=price, qty=qty, usd=float(usd_size), tx=None)
		q = self._quote(BASE_MINT, token, in_amount)
		swap_tx = self._swap(q)
		sig = self._sign_and_send(swap_tx)
		out_amt = float(q.get("outAmount") or 0) / (10 ** self._get_decimals(token))
		qty = out_amt
		price = (usd_size / max(qty, 1e-9))
		return Fill(price=price, qty=qty, usd=float(usd_size), tx=sig)

	def market_sell(self, token: str, qty: float) -> Fill:
		# token is input mint; we sell into BASE_MINT
		dec = self._get_decimals(token)
		in_amount = int(round(float(qty) * (10 ** dec)))
		if in_amount <= 0:
			return Fill(price=0.0, qty=0.0, usd=0.0, tx=None)
		if self._dry:
			q = self._quote(token, BASE_MINT, in_amount)
			out_usd = float(q.get("outAmount") or 0) / (10 ** self._get_decimals(BASE_MINT))
			price = out_usd / max(float(qty), 1e-9)
			return Fill(price=price, qty=float(qty), usd=out_usd, tx=None)
		q = self._quote(token, BASE_MINT, in_amount)
		swap_tx = self._swap(q)
		sig = self._sign_and_send(swap_tx)
		out_usd = float(q.get("outAmount") or 0) / (10 ** self._get_decimals(BASE_MINT))
		price = out_usd / max(float(qty), 1e-9)
		return Fill(price=price, qty=float(qty), usd=out_usd, tx=sig)

