from tradingSystem.config_optimized import WALLET_SECRET
from solders.keypair import Keypair
import base58 as b58

kp = Keypair.from_bytes(b58.b58decode(WALLET_SECRET.strip()))
print(f"Wallet Address: {kp.pubkey()}")


