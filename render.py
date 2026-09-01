"""Merge data/screen.json into template.html -> dist/index.html (self-contained)."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(HERE, "data", "screen.json")
TPL_PATH = os.path.join(HERE, "template.html")
OUT_PATH = os.path.join(HERE, "dist", "index.html")
CSV_PATH = os.path.join(HERE, "data", "screen.csv")

TOKEN = "/*__DATA__*/null"


def render() -> str:
    with open(JSON_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    with open(TPL_PATH, encoding="utf-8") as f:
        html = f.read()
    if TOKEN not in html:
        raise RuntimeError(f"template.html is missing the {TOKEN} placeholder")

    # </script> inside a JSON string would close the host <script> block early.
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace(TOKEN, blob)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    write_csv(payload)
    print(f"[render] {OUT_PATH} ({os.path.getsize(OUT_PATH)/1024:.0f} KB, "
          f"{len(payload['rows'])} stocks, asof {payload['asof']})")
    return OUT_PATH


def write_csv(payload: dict) -> None:
    import csv

    cols = ["s", "n", "sec", "px", "mcap", "r1M", "r3M", "r6M", "r9M", "r12M", "rAvg126",
            "mdv", "sma20", "sma50", "sma100", "sma200", "ema20", "ema50", "ema100", "ema200",
            "ath", "dATH", "h52", "d52", "p1M", "p3M", "p6M", "p9M", "p12M", "beta", "vol", "pe"]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "name", "sector", "indices"] + cols[3:])
        for r in payload["rows"]:
            w.writerow([r["s"], r["n"], r["sec"], "|".join(r.get("ix", []))]
                       + [r.get(c) for c in cols[3:]])


if __name__ == "__main__":
    render()
    sys.exit(0)
