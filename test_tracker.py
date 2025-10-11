import sys
sys.path.insert(0, '.')
from app.storage import get_alerted_tokens_for_tracking

tokens = get_alerted_tokens_for_tracking()
print(f'Tokens found: {len(tokens)}')
if tokens:
    print(f'Sample tokens: {tokens[:5]}')
