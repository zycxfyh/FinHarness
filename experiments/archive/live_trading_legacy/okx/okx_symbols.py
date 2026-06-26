"""OKX symbol normalization helpers."""

from __future__ import annotations


def normalize_usdt_symbol(symbol: str) -> str:
    """Normalize compact OKX app-style symbols such as BTCUSDT into BTC-USDT."""
    clean = symbol.strip().upper()
    if "-" in clean:
        return clean
    if clean.endswith("USDT") and len(clean) > 4:
        return f"{clean[:-4]}-USDT"
    return clean


def candidate_inst_ids(symbol: str) -> list[str]:
    """Return likely OKX instrument IDs for app-style symbols."""
    normalized = normalize_usdt_symbol(symbol)
    candidates = [normalized]
    if normalized.endswith("-USDT") and not normalized.endswith("-USDT-SWAP"):
        candidates.append(f"{normalized}-SWAP")
    return candidates
