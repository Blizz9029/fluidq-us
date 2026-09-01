"""
FLUID Q - US  |  daily data build

Ports the FLUID Q screen (NSE) to the US market, 1:1 on every calculation.
Pulls live daily OHLCV + quotes for the S&P 500 + Nasdaq-100, computes every
metric the screen filters on, and emits a self-contained website.

Run:  python build.py
Out:  dist/index.html          (self-contained site, data inlined)
      data/screen.json         (raw metrics, for your own use)
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import yfinance as yf
from yfinance.data import YfData

from universe import get_universe

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DIST = os.path.join(HERE, "dist")

BENCHMARK = "SPY"          # beta reference
TRADING_DAYS_1Y = 252

# Calendar-day lookbacks for "absolute return over N months" (FluidQ convention:
# last close vs the last close on or before the lookback date).
LOOKBACKS = {"1M": 30, "3M": 91, "6M": 183, "9M": 274, "12M": 365}
MA_PERIODS = (20, 50, 100, 200)


# --------------------------------------------------------------------------- io

def fetch_prices(symbols: list[str]) -> pd.DataFrame:
    """2y daily OHLCV. auto_adjust=False -> split-adjusted, dividend-unadjusted,
    i.e. exactly the 'absolute price return' FluidQ ranks on."""
    print(f"[prices] downloading 2y daily for {len(symbols)} symbols...")
    df = yf.download(
        symbols, period="2y", interval="1d", auto_adjust=False,
        progress=False, threads=True, group_by="column",
    )
    print(f"[prices] got {df.shape[0]} sessions, last = {df.index[-1].date()}")
    return df


def fetch_ath(symbols: list[str], chunk: int = 60) -> dict[str, float]:
    """All-time high from full-history monthly bars (cheap: ~600 rows/ticker)."""
    out: dict[str, float] = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        try:
            d = yf.download(
                part, period="max", interval="1mo", auto_adjust=False,
                progress=False, threads=True, group_by="column",
            )
            high = d["High"] if isinstance(d.columns, pd.MultiIndex) else d[["High"]]
            if isinstance(high, pd.Series):
                high = high.to_frame(part[0])
            for s in part:
                if s in high.columns:
                    v = high[s].max()
                    if pd.notna(v) and v > 0:
                        out[s] = float(v)
        except Exception as e:  # noqa: BLE001
            print(f"[ath] chunk {i} failed: {e}")
        print(f"[ath] {min(i + chunk, len(symbols))}/{len(symbols)}", end="\r")
    print(f"\n[ath] resolved {len(out)}/{len(symbols)}")
    return out


def fetch_quotes(symbols: list[str], chunk: int = 100) -> dict[str, dict]:
    """Batch Yahoo quote: market cap, shares, trailing P/E, 52w high, exchange."""
    yfd = YfData()
    fields = ",".join([
        "symbol", "marketCap", "sharesOutstanding", "trailingPE", "forwardPE",
        "regularMarketPrice", "fiftyTwoWeekHigh", "fullExchangeName", "quoteType",
        "longName", "shortName",
    ])
    out: dict[str, dict] = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        try:
            r = yfd.get_raw_json(
                "https://query2.finance.yahoo.com/v7/finance/quote",
                params={"symbols": ",".join(part), "fields": fields},
            )
            for q in r.get("quoteResponse", {}).get("result", []):
                out[q["symbol"]] = q
        except Exception as e:  # noqa: BLE001
            print(f"[quotes] chunk {i} failed: {e}")
        print(f"[quotes] {min(i + chunk, len(symbols))}/{len(symbols)}", end="\r")
    print(f"\n[quotes] resolved {len(out)}/{len(symbols)}")
    return out


# ---------------------------------------------------------------------- metrics

def _f(x) -> float | None:
    """Round-trip a numpy/pandas scalar to a JSON-safe float (or None)."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(v) or math.isinf(v)) else v


def tv_exchange(name: str | None) -> str | None:
    """Yahoo's exchange name -> the prefix TradingView expects (NASDAQ:AAPL).
    Returns None when unrecognised, so the symbol is emitted bare and
    TradingView resolves it itself."""
    n = (name or "").lower()
    if "nasdaq" in n:
        return "NASDAQ"
    if "american" in n or "amex" in n or "arca" in n:
        return "AMEX"
    if "nyse" in n:
        return "NYSE"
    if "bats" in n or "bzx" in n:
        return "BATS"
    # "Cboe US" and anything else unrecognised: emit the ticker bare and let
    # TradingView resolve it to the primary listing (CBOE -> CBOE:CBOE).
    return None


def _r(x, nd: int = 2) -> float | None:
    v = _f(x)
    return None if v is None else round(v, nd)


def absolute_return(close: pd.Series, days: int) -> float | None:
    """(last / last close on-or-before (last_date - days) - 1) * 100"""
    if close.empty:
        return None
    last_date = close.index[-1]
    cutoff = last_date - pd.Timedelta(days=days)
    base = close.loc[:cutoff]
    if base.empty:
        return None
    b, l = base.iloc[-1], close.iloc[-1]
    if not (b > 0):
        return None
    return (l / b - 1.0) * 100.0


def positive_days_pct(close: pd.Series, days: int) -> float | None:
    """% of trading sessions in the window with a positive close-to-close return."""
    if close.empty:
        return None
    cutoff = close.index[-1] - pd.Timedelta(days=days)
    win = close.loc[close.index > cutoff]
    if len(win) < 2:
        return None
    rets = win.pct_change(fill_method=None).dropna()
    if rets.empty:
        return None
    return float((rets > 0).sum()) / float(len(rets)) * 100.0


def compute(uni: dict[str, dict], px: pd.DataFrame, ath: dict[str, float],
            quotes: dict[str, dict]) -> list[dict]:
    close_all = px["Close"]
    high_all = px["High"]
    vol_all = px["Volume"]

    # benchmark daily returns for beta
    bench = close_all[BENCHMARK].dropna() if BENCHMARK in close_all.columns else pd.Series(dtype=float)
    bench_ret = bench.pct_change(fill_method=None).dropna().tail(TRADING_DAYS_1Y)

    rows: list[dict] = []
    skipped: list[str] = []

    for sym, meta in uni.items():
        if sym not in close_all.columns:
            skipped.append(sym)
            continue
        close = close_all[sym].dropna()
        if len(close) < 60:
            skipped.append(sym)
            continue

        high = high_all[sym].reindex(close.index)
        vol = vol_all[sym].reindex(close.index)
        q = quotes.get(sym, {})
        price = _f(close.iloc[-1])
        if not price:
            skipped.append(sym)
            continue

        rec: dict = {
            "s": sym,
            "n": q.get("longName") or q.get("shortName") or meta.get("name") or sym,
            "sec": meta.get("sector") or "",
            "ix": meta.get("indices", []),
            "px": _r(price),
        }

        # --- absolute returns -------------------------------------------------
        for label, days in LOOKBACKS.items():
            rec[f"r{label}"] = _r(absolute_return(close, days))
        # Sort factor: "Average absolute return 12 & 6 months"
        r12, r6 = rec.get("r12M"), rec.get("r6M")
        rec["rAvg126"] = _r((r12 + r6) / 2.0) if (r12 is not None and r6 is not None) else None

        # --- median daily traded value, 1Y (USD; FluidQ's "median daily volume in Rs")
        dv = (close * vol).dropna().tail(TRADING_DAYS_1Y)
        rec["mdv"] = _r(dv.median(), 0) if len(dv) else None

        # --- moving averages, SMA and EMA ------------------------------------
        for p in MA_PERIODS:
            if len(close) >= p:
                rec[f"sma{p}"] = _r(close.rolling(p).mean().iloc[-1])
                rec[f"ema{p}"] = _r(close.ewm(span=p, adjust=False).mean().iloc[-1])
            else:
                rec[f"sma{p}"] = rec[f"ema{p}"] = None

        # --- distance below highs (0% = sitting at the high) ------------------
        a = ath.get(sym)
        if a is None or not (a > 0):
            a = _f(close.max())
        rec["ath"] = _r(a)
        rec["dATH"] = _r(max(0.0, (a - price) / a * 100.0)) if a else None

        h52 = high.tail(TRADING_DAYS_1Y).max()
        h52 = _f(h52) or _f(q.get("fiftyTwoWeekHigh"))
        rec["h52"] = _r(h52)
        rec["d52"] = _r(max(0.0, (h52 - price) / h52 * 100.0)) if h52 else None

        # --- % positive days --------------------------------------------------
        for label, days in LOOKBACKS.items():
            rec[f"p{label}"] = _r(positive_days_pct(close, days), 1)

        # --- beta vs SPY + annualised volatility, 1Y daily --------------------
        ret = close.pct_change(fill_method=None).dropna().tail(TRADING_DAYS_1Y)
        rec["vol"] = _r(ret.std() * math.sqrt(TRADING_DAYS_1Y) * 100.0) if len(ret) > 30 else None
        if len(bench_ret) > 30 and len(ret) > 30:
            j = pd.concat([ret, bench_ret], axis=1, join="inner").dropna()
            if len(j) > 30:
                bv = j.iloc[:, 1].var()
                rec["beta"] = _r(j.iloc[:, 0].cov(j.iloc[:, 1]) / bv, 3) if bv else None
            else:
                rec["beta"] = None
        else:
            rec["beta"] = None

        # --- fundamentals from the live quote ---------------------------------
        rec["mcap"] = _r(q.get("marketCap"), 0)
        rec["pe"] = _r(q.get("trailingPE"))
        rec["x"] = tv_exchange(q.get("fullExchangeName"))

        rows.append(rec)

    if skipped:
        print(f"[compute] skipped {len(skipped)} (no/thin data): {', '.join(skipped[:15])}"
              f"{' ...' if len(skipped) > 15 else ''}")
    return rows


# ------------------------------------------------------------------------ build

def main() -> int:
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    uni = get_universe()
    symbols = sorted(uni)
    px = fetch_prices(symbols + [BENCHMARK])
    quotes = fetch_quotes(symbols)
    ath = fetch_ath(symbols)

    rows = compute(uni, px, ath, quotes)
    rows.sort(key=lambda r: (r.get("rAvg126") is None, -(r.get("rAvg126") or 0)))

    asof = str(px.index[-1].date())
    payload = {
        "asof": asof,
        "built": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "counts": {
            "total": len(rows),
            "SP500": sum(1 for r in rows if "SP500" in r["ix"]),
            "NDX": sum(1 for r in rows if "NDX" in r["ix"]),
        },
        "rows": rows,
    }

    with open(os.path.join(DATA, "screen.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))

    try:
        import render
        render.render()
    except Exception as e:  # noqa: BLE001
        print(f"[render] skipped: {e}")

    print(f"[build] OK  asof={asof}  {len(rows)} stocks "
          f"(S&P500 {payload['counts']['SP500']}, NDX {payload['counts']['NDX']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
