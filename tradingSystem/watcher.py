import re
import time
from typing import Iterator, Dict
from .config import BOT_STDOUT_LOG


_FINAL_RE = re.compile(r"Token\s+([A-Za-z0-9]{20,64})\s+FINAL:\s+(\d+)/(\d+)\s+\(prelim:\s*(\d+),\s*velocity:\s*\+(\d+)\)")
_PASS_RE = re.compile(r"PASSED \(Strict \+ Smart Money\):\s+([A-Za-z0-9]{20,64})")
_REJECT_RE = re.compile(r"REJECTED \(Junior Strict\):\s+([A-Za-z0-9]{20,64})")

_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{20,64}$")


def _valid_ca(ca: str) -> bool:
	# Basic base58/length filter (Solana typically 32-44, but allow 20-64 for safety)
	return bool(_BASE58_RE.match(ca))


def follow_decisions(start_at_end: bool = True) -> Iterator[Dict[str, str]]:
	"""Yield normalized events from stdout.log in near-real-time.

	Events:
	- {type: 'final', ca, final:int, prelim:int, vel:int}
	- {type: 'pass_strict_smart', ca}
	- {type: 'reject_junior', ca}
	"""
	path = BOT_STDOUT_LOG
	with open(path, "r", errors="ignore") as f:
		if start_at_end:
			f.seek(0, 2)
		while True:
			line = f.readline()
			if not line:
				time.sleep(0.2)
				continue
			m = _FINAL_RE.search(line)
			if m:
				ca = m.group(1)
				if not _valid_ca(ca):
					continue
				yield {
					"type": "final",
					"ca": ca,
					"final": m.group(2),
					"prelim": m.group(4),
					"vel": m.group(5),
				}
				continue
			m = _PASS_RE.search(line)
			if m:
				ca = m.group(1)
				if not _valid_ca(ca):
					continue
				yield {"type": "pass_strict_smart", "ca": ca}
				continue
			m = _REJECT_RE.search(line)
			if m:
				ca = m.group(1)
				if not _valid_ca(ca):
					continue
				yield {"type": "reject_junior", "ca": ca}


