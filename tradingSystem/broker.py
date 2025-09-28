from dataclasses import dataclass
from typing import Tuple
from .config import DRY_RUN


@dataclass
class Fill:
	price: float
	qty: float
	usd: float


class Broker:
	"""Pluggable execution broker. Default is DryRun (no network)."""

	def __init__(self):
		self.dry = DRY_RUN

	def market_buy(self, token: str, usd_size: float) -> Fill:
		# In dry-run, synthesize a price from placeholder, assume zero fees
		price = 1.0
		qty = usd_size / max(price, 1e-9)
		return Fill(price=price, qty=qty, usd=usd_size)

	def market_sell(self, token: str, qty: float) -> Fill:
		price = 1.0
		usd = qty * price
		return Fill(price=price, qty=qty, usd=usd)


