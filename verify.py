"""
Build gate. Exits non-zero if the freshly built data is stale, thin or malformed,
so a bad run fails the workflow instead of deploying wrong numbers over good ones.
(Pages keeps serving the last successful deploy when this fails.)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

MIN_STOCKS = 480          # 518 in the universe; allow for a few delistings
MAX_STALE_DAYS = 5        # covers a long weekend plus a market holiday
MIN_COVERAGE = 0.95       # share of rows that must carry the core metrics
CORE = ("px", "r12M", "r6M", "rAvg126", "mcap", "ema50", "sma50", "mdv")
BELLWETHERS = ("AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "JNJ")


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    sys.exit(1)


def main() -> int:
    path = os.path.join(HERE, "data", "screen.json")
    if not os.path.exists(path):
        fail("data/screen.json was not produced")

    with open(path, encoding="utf-8") as f:
        d = json.load(f)

    rows = d.get("rows") or []
    asof = dt.date.fromisoformat(d["asof"])
    age = (dt.date.today() - asof).days

    print(f"asof={asof}  age={age}d  rows={len(rows)}")

    if age > MAX_STALE_DAYS:
        fail(f"prices are {age} days old (limit {MAX_STALE_DAYS}) - upstream feed is likely blocked")
    if len(rows) < MIN_STOCKS:
        fail(f"only {len(rows)} stocks (expected >= {MIN_STOCKS}) - the download was partial")

    for key in CORE:
        have = sum(1 for r in rows if r.get(key) is not None)
        cov = have / len(rows)
        print(f"  {key:<9} coverage {cov:6.1%}")
        if cov < MIN_COVERAGE:
            fail(f"{key} present on only {cov:.1%} of rows (need {MIN_COVERAGE:.0%})")

    by_sym = {r["s"]: r for r in rows}
    missing = [s for s in BELLWETHERS if s not in by_sym]
    if missing:
        fail(f"bellwether tickers absent: {', '.join(missing)}")

    for r in rows:
        if not (r.get("px") or 0) > 0:
            fail(f"{r['s']} has a non-positive price: {r.get('px')}")
        if r.get("mcap") is not None and r["mcap"] <= 0:
            fail(f"{r['s']} has a non-positive market cap: {r['mcap']}")

    dist = os.path.join(HERE, "dist", "index.html")
    if not os.path.exists(dist):
        fail("dist/index.html was not rendered")
    size = os.path.getsize(dist)
    if size < 150_000:
        fail(f"dist/index.html is only {size} bytes - the data was probably not inlined")
    with open(dist, encoding="utf-8") as f:
        html = f.read()
    if "/*__DATA__*/null" in html:
        fail("dist/index.html still contains the empty data placeholder")

    print(f"OK    {len(rows)} stocks, priced {asof}, site {size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
