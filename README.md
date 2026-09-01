# Fluid Q — US

**Live: https://blizz9029.github.io/fluidq-us/**

Your NSE **FLUID Q – 50EMA** screen, ported to the S&P 500 + Nasdaq 100 with live data.
Every calculation is unchanged; only the currency-denominated thresholds were restated in dollars.

Rebuilds itself every day at 23:00 UTC (04:30 IST) via GitHub Actions — about three hours
after the US close, so each run uses a fully settled session. Nothing runs on your machine.
A build that comes back stale or thin fails `verify.py` and is never deployed, so the site
keeps serving the last good data rather than wrong data.

## Run it locally

Optional — the hosted site is the source of truth. Useful for poking at the raw numbers.

```powershell
python build.py        # pull fresh data + rebuild the site  (~3 min)
python render.py       # rebuild the site from cached data   (instant)
python verify.py       # run the same freshness checks CI runs
start dist\index.html  # open it
```

To force the hosted site to rebuild right now, without waiting for the cron:

```powershell
gh workflow run "Refresh screener" --repo Blizz9029/fluidq-us
```

### Local scheduled task (not needed if you use the hosted site)

```powershell
powershell -ExecutionPolicy Bypass -File .\install-daily-task.ps1
```

Registers a Windows task at 07:00 IST that refreshes your local copy only. Remove it with:

```powershell
Unregister-ScheduledTask -TaskName "FluidQ US Daily Refresh" -Confirm:$false
```

## Files

| File | What it does |
|---|---|
| `universe.py` | S&P 500 + Nasdaq 100 constituents from Wikipedia, cached as a fallback |
| `build.py` | Downloads 2y daily OHLCV, quotes and all-time highs; computes every metric |
| `render.py` | Inlines `data/screen.json` into `template.html` → `dist/index.html` |
| `verify.py` | Build gate: fails CI if the data is stale, thin or malformed, so bad data is never deployed |
| `template.html` | The site. All filtering happens in the browser, so toggles are instant |
| `data/screen.json` | Raw metrics, one record per stock |
| `data/screen.csv` | Same thing as a spreadsheet |
| `dist/index.html` | Self-contained site — no server, no network. Email it, open it anywhere |

## What each number means

| Metric | Definition |
|---|---|
| Absolute return, N months | Last close ÷ last close on or before (today − N months) − 1. Calendar lookback, matching FluidQ |
| **Average absolute return 12 & 6 months** | Plain mean of the 12-month and 6-month absolute returns — the default ranking factor |
| Median daily volume 1Y | Median of `close × volume` over the last 252 sessions, in USD |
| Moving averages | 20/50/100/200-day, both SMA and EMA, on split-adjusted closes |
| Distance below ATH | All-time high from full-history monthly bars; 0% means sitting at the high |
| Distance below 1Y high | Highest daily high of the last 252 sessions |
| Positive days % | Share of sessions in the window with a positive close-to-close move |
| Beta | 1 year of daily returns against SPY |
| Volatility | Stdev of daily returns × √252 |
| P/E | Trailing, from the live quote |

Prices are **split-adjusted, dividend-unadjusted**, so returns are price returns — NSE convention.

## India → US translations

Formulas are identical. Only these thresholds changed units:

| Filter | Your NSE screen | US default | Why |
|---|---|---|---|
| Median daily volume | ₹1 crore (≈ $115K) | $1,000,000 | ₹1cr is inert against US large caps |
| Market cap floor | ₹5,000 cr (≈ $570M) | $500M | Nearest round dollar equivalent |
| Price (CMP) range | ₹30 – ₹2,000 | $5 – $10,000 | ₹30–₹2,000 is $0.34–$22.70; it would have cut the index |
| Series EQ / BE | EQ only | *dropped* | NSE-only concept, no US counterpart |

Change any of these in the UI — the site never hard-codes them.

## Two judgement calls worth knowing

1. **EMA vs SMA.** Your screen is named *50EMA* but the FluidQ toggle reads "Above 50-day MA".
   Both are computed; the UI defaults to **EMA** to match the screen name. Flip it in the
   Moving Average card. On today's data it's the difference between 139 and 134 matches.
2. **"Ignore top beta / volatility stocks."** FluidQ doesn't state the cut-off, so it's exposed
   as *drop the top N%*, defaulting to 10%. The explicit **beta ceiling** (1.25) is exact.

Not ported: *Historical Ranks* (needs point-in-time snapshots — the data would have to be
accumulated day by day from here) and *Custom Filters* (undefined slots in FluidQ).

---

For research and screening only. Not investment advice.
