import requests

wallet = "7xAw4kDpsW8kXjfCgmUEqsmvqw2SU6vAcmgEhjjC92Gk"
bonk_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getTokenAccountsByOwner",
    "params": [
        wallet,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"}
    ]
}

resp = requests.post("https://api.mainnet-beta.solana.com", json=payload)
data = resp.json()

print(f"Wallet: {wallet}")
print(f"\nToken Accounts:")
for account in data["result"]["value"]:
    info = account["account"]["data"]["parsed"]["info"]
    mint = info["mint"]
    amount = float(info["tokenAmount"]["uiAmount"] or 0)
    if amount > 0:
        token_name = "BONK" if mint == bonk_mint else mint[:8]
        print(f"  {token_name}: {amount:,.2f}")

# Check specifically for BONK
bonk_accounts = [a for a in data["result"]["value"] 
                 if a["account"]["data"]["parsed"]["info"]["mint"] == bonk_mint]
if bonk_accounts:
    bonk_amount = float(bonk_accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"])
    print(f"\n✅ BONK Found: {bonk_amount:,.2f} BONK")
else:
    print(f"\n❌ No BONK found in this wallet")


