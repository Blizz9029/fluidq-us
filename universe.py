"""Fetch S&P 500 + Nasdaq-100 constituents from Wikipedia, with a cached fallback."""
from __future__ import annotations

import io
import json
import os

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "universe_cache.json")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) fluidq-us-screener/1.0"}

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NDX_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"


def _yahooify(sym: str) -> str:
    """BRK.B -> BRK-B (Yahoo's convention for share classes)."""
    return str(sym).strip().upper().replace(".", "-")


def _tables(url: str) -> list[pd.DataFrame]:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return pd.read_html(io.StringIO(r.text))


def _pick(df: pd.DataFrame, *names: str) -> str | None:
    cols = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n in cols:
            return cols[n]
    return None


def _sp500() -> dict[str, dict]:
    for df in _tables(SP500_URL):
        s = _pick(df, "symbol", "ticker")
        n = _pick(df, "security", "company")
        g = _pick(df, "gics sector")
        if s and n and g:
            return {
                _yahooify(r[s]): {
                    "name": str(r[n]).strip(),
                    "sector": str(r[g]).strip(),
                }
                for _, r in df.iterrows()
            }
    raise RuntimeError("S&P 500 constituents table not found")


def _ndx() -> dict[str, dict]:
    for df in _tables(NDX_URL):
        s = _pick(df, "ticker", "symbol")
        n = _pick(df, "company", "security")
        if s and n and len(df) > 90:
            g = _pick(df, "gics sector", "sector", "icb industry[1]", "icb industry")
            return {
                _yahooify(r[s]): {
                    "name": str(r[n]).strip(),
                    "sector": str(r[g]).strip() if g else "",
                }
                for _, r in df.iterrows()
            }
    raise RuntimeError("Nasdaq-100 constituents table not found")


def get_universe() -> dict[str, dict]:
    """Returns {symbol: {name, sector, indices: [...]}}. Falls back to cache on failure."""
    try:
        sp, nd = _sp500(), _ndx()
        if len(sp) < 450 or len(nd) < 90:
            raise RuntimeError(f"suspicious counts: sp500={len(sp)} ndx={len(nd)}")
        uni: dict[str, dict] = {}
        for sym, meta in sp.items():
            uni[sym] = {**meta, "indices": ["SP500"]}
        for sym, meta in nd.items():
            if sym in uni:
                uni[sym]["indices"].append("NDX")
            else:
                uni[sym] = {**meta, "indices": ["NDX"]}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(uni, f, indent=1)
        print(f"[universe] live: {len(sp)} S&P 500, {len(nd)} Nasdaq-100, {len(uni)} unique")
        return uni
    except Exception as e:  # noqa: BLE001
        if os.path.exists(CACHE):
            with open(CACHE, encoding="utf-8") as f:
                uni = json.load(f)
            print(f"[universe] WIKIPEDIA FAILED ({e}); using cache of {len(uni)} symbols")
            return uni
        raise


if __name__ == "__main__":
    u = get_universe()
    both = [s for s, v in u.items() if len(v["indices"]) == 2]
    print(f"in both indices: {len(both)}")
    print(list(u.items())[:3])
