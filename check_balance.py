import requests

wallet = "7xAw4kDpsW8kXjfCgmUEqsmvqw2SU6vAcmgEhjjC92Gk"

# Check SOL balance
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getBalance",
    "params": [wallet]
}

resp = requests.post("https://api.mainnet-beta.solana.com", json=payload)
data = resp.json()
sol_balance = data["result"]["value"] / 1e9

print(f"Wallet: {wallet}")
print(f"SOL Balance: {sol_balance:.4f} SOL")
print(f"USD Value (@ $180/SOL): ${sol_balance * 180:.2f}")


