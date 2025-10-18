#!/usr/bin/env python3
"""
Simple tool to extract pair addresses from DexScreener
Just copy-paste the visible pair addresses from the page
"""

def create_pair_list_from_visible():
    """
    Based on your screenshot, I can see these tokens on the trending page.
    Let me create a script that helps you quickly add them.
    """
    
    print("="*60)
    print("DEXSCREENER PAIR EXTRACTOR")
    print("="*60)
    print("\nHow to use:")
    print("1. Go to: https://dexscreener.com/solana?rankBy=trendingScoreH24&order=desc")
    print("2. Click on each token you want")
    print("3. Copy the pair address from the URL")
    print("4. Paste below when prompted")
    print("\nOr I can extract from the visible tokens in your screenshot...")
    print("="*60)
    
    # From your screenshot, I can see these tokens are visible:
    # Let me create a template based on what's visible
    
    visible_tokens = [
        # Format: (symbol, approx_24h_change, notes)
        ("goldcoin", 343, "Top gainer"),
        ("PIBS", 1949, "Huge gainer"),
        ("pDEM", -1399, "Negative, skip"),
        ("Fapcoin", 169, "Good gain"),
        ("", -2908, "Negative, skip"),
        ("UGIMIED", 594, "Good gain"),
        ("LONG", -331, "Negative, skip"),
        ("Fangol", 1293, "Huge gainer"),
        ("Darkbet", 1163, "Huge gainer"),
        ("BOT", 8242, "Massive gainer"),
        ("XALI", -4425, "Negative, skip"),
        ("MEEFAI", 157, "Good gain"),
        ("电影", 2041, "Huge gainer"),
        ("USDT", 514, "Good gain"),
        ("ALOH", -541, "Negative, skip"),
        ("SLERF", 1618, "Huge gainer"),
        ("西手", 666, "Good gain"),
    ]
    
    print("\nFrom your screenshot, I can see tokens with these gains:")
    print("\nPositive gainers (good for ML training):")
    
    good_tokens = [(s, g, n) for s, g, n in visible_tokens if g > 0]
    for symbol, gain, notes in good_tokens:
        if symbol:
            print(f"  {symbol}: +{gain}% - {notes}")
    
    print(f"\nTotal good candidates: {len(good_tokens)}")
    print("\n" + "="*60)
    print("MANUAL EXTRACTION NEEDED")
    print("="*60)
    print("\nSince the API is limited, here's the fastest way:")
    print("\n1. Open DexScreener trending page")
    print("2. For each token with good gains:")
    print("   a. Click on it")
    print("   b. URL will be: https://dexscreener.com/solana/PAIR_ADDRESS")
    print("   c. Copy the PAIR_ADDRESS part")
    print("   d. Add to pair_list.txt")
    print("\n3. Focus on tokens with:")
    print("   - 100%+ gains (2x+) = PRIORITY")
    print("   - 50-100% gains = GOOD")
    print("   - 10-50% gains = OPTIONAL")
    print("\n4. From your screenshot, prioritize:")
    print("   - BOT (+8242%!) - MUST HAVE")
    print("   - 电影 (+2041%) - MUST HAVE")
    print("   - PIBS (+1949%) - MUST HAVE")
    print("   - SLERF (+1618%) - MUST HAVE")
    print("   - Fangol (+1293%) - MUST HAVE")
    print("   - Darkbet (+1163%) - MUST HAVE")
    print("   - UGIMIED (+594%) - GOOD")
    print("   - USDT (+514%) - GOOD")
    print("\nAim for 50-100 pairs total for best ML results!")


def interactive_pair_collector():
    """
    Interactive tool to collect pair addresses
    """
    print("\n" + "="*60)
    print("INTERACTIVE PAIR COLLECTOR")
    print("="*60)
    print("\nPaste pair addresses one by one (or 'done' to finish):")
    print("Example: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU")
    print()
    
    pairs = []
    
    while True:
        try:
            pair = input(f"Pair {len(pairs)+1}: ").strip()
            
            if pair.lower() == 'done':
                break
            
            if not pair:
                continue
            
            # Basic validation (Solana addresses are base58, ~44 chars)
            if len(pair) < 32:
                print("  Warning: Address seems too short, but adding anyway...")
            
            pairs.append(pair)
            print(f"  Added! ({len(pairs)} total)")
            
        except KeyboardInterrupt:
            print("\n\nStopped by user")
            break
    
    if pairs:
        print(f"\n\nCollected {len(pairs)} pair addresses")
        print("Saving to pair_list.txt...")
        
        with open("pair_list.txt", 'w') as f:
            f.write("# Manually collected pair addresses\n")
            f.write(f"# Total: {len(pairs)}\n\n")
            for pair in pairs:
                f.write(f"{pair}\n")
        
        print("Saved!")
        print("\nNext step:")
        print("  python scripts/ml/scrape_dexscreener_trending.py")
    else:
        print("\nNo pairs collected")


def main():
    create_pair_list_from_visible()
    
    print("\n" + "="*60)
    print("\nWould you like to:")
    print("1. Manually collect pairs interactively")
    print("2. Exit and collect pairs yourself")
    print()
    
    choice = input("Choice (1 or 2): ").strip()
    
    if choice == "1":
        interactive_pair_collector()
    else:
        print("\nOK! Collect pairs and add to pair_list.txt")
        print("Then run: python scripts/ml/scrape_dexscreener_trending.py")


if __name__ == "__main__":
    main()


