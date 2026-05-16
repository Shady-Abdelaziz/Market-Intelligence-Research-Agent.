# Monitor page — usage guide

The **Monitors** view (`/monitor` in the web UI) lets you put MIRA on standing
watch for one or more tickers. On every tick, MIRA recomputes 30-day baselines,
checks three trigger conditions, and — if any of them fire — kicks off a full
`PROACTIVE_ALERT`-tagged analysis. Triggered reports show up on the row and link
through to the live job view.

This page is the UI in front of these endpoints:

| UI action | Endpoint |
|---|---|
| List monitors | `GET /monitor` |
| Add a watch | `POST /monitor_start` |
| Stop a watch | `DELETE /monitor/{ticker}` |
| History per ticker | `GET /monitor/{ticker}/history` |

Source: `frontend/app/(chrome)/monitor/page.tsx`, `backend/app/api/monitor.py`.

---

## Opening the page

1. Start the stack: `docker compose up --build`.
2. Open <http://localhost:3000/monitor>.

If no monitors are running, the list area shows the **"no active monitors"**
empty state with a hint to add one via the form at the bottom.

---

## Page layout

### 1. Header strip

Three rolled-up counters across the top:

| Stat | Meaning |
|---|---|
| **Under watch** | Total active monitors. |
| **Tripped today** | Monitors whose most-recent run (within 24h) had at least one trigger fired. |
| **Alerts · 30 d** | Sum of trigger-firing runs in the last 30 days across all monitors. |

### 2. Filter row

Filters the list below by status:

| Filter | A monitor matches when… |
|---|---|
| **All** | always. |
| **Alert** | its history shows at least one run with a fired trigger. |
| **Watching** | baselines have been computed and no alert has fired. |
| **Quiet** | baselines haven't been computed yet (the first tick hasn't run, or `compute_baselines` raised — e.g., unknown ticker, yfinance outage). |

Each filter chip shows a live count.

### 3. Monitor list (rows)

Each row corresponds to one active `MonitoringTarget`. Five columns:

**Ticker** — symbol and company name (pulled from the latest report).

**Status / price** — a coloured badge (`Alert today` / `Watching` / `Quiet`)
plus the latest close and daily % change. If no tick has produced a report yet,
shows `awaiting first tick`.

**Triggers** — three pills, each highlighted when that trigger fired on the
most recent run:
- **Articles** — `≥5` when ≥ 5 new article URLs have been seen since the last
  tick (`trigger_new_articles`).
- **Price σ** — current σ-distance from the 30-day mean. Fires when
  `|close − mean| > 2 × std` (`trigger_price_2sigma`).
- **Volume** — current ratio of today's volume to the 30-day average. Fires
  when `> 2 ×` (`trigger_volume_2x`).

**Meta** — configured peers, cadence (formatted in hours, gated by NYSE
trading-day calendar), and last-run timestamp.

**Alerts / actions** — count of historical trigger-firing runs, a `view` link
to the most recent job's live page, and a red `stop` button that calls
`DELETE /monitor/{ticker}`.

### 4. Trigger rules legend

Static reference card spelling out the three conditions and their thresholds.
Any one of them, evaluated per tick, is enough to fire a proactive analysis.

### 5. Add-a-watch form

POSTs to `/monitor_start`. Four inputs plus a submit button:

| Field | Purpose | Notes |
|---|---|---|
| **Ticker** | The symbol to watch. | Uppercased on input; required. |
| **Peers** | Comma-separated peer tickers. | Used by the analysis (correlations, peer news) when an alert fires. Optional. |
| **Cadence** | How often the cron tick runs. | `1h`, `4h`, `24h · trading days` (default), `weekly`. |
| **Calendar** | Trading-day calendar that gates the tick. | `NYSE` (default), `NASDAQ`, or `24/7`. Server-side this is the global `MONITOR_TRADING_CALENDAR` setting; the field is a placeholder until per-monitor calendars are exposed. |

Successful submit clears the ticker/peers fields, refreshes the list, and
your new monitor appears in `Quiet` until the first baseline computes.

---

## How a monitor actually runs

1. **`POST /monitor_start`** upserts a `MonitoringTarget` row, immediately
   computes 30-day baselines (mean, std, volume avg) from yfinance, and
   enqueues the first `monitor_tick` deferred by `cadence_seconds`
   (`backend/app/api/monitor.py:25`).
2. The worker picks up `monitor_tick`. If `is_trading_day(...)` is false
   for the configured calendar, the tick re-enqueues itself for the next
   cadence and does nothing else.
3. On a trading day, the tick fetches today's articles, close, and volume
   and evaluates the three triggers (`backend/app/monitoring/triggers.py`).
4. If any trigger fires, it enqueues an `analyze_ticker` job with
   `alert_tag=PROACTIVE_ALERT` and `monitor_trigger=<trigger_name>`. The
   synthesizer surfaces both on the final `AnalysisReport`.
5. Either way, the tick re-enqueues itself for the next cadence and updates
   `last_run_at` and `last_seen_article_urls` on the target row.

Baselines are recomputed in-process per tick. State persists across worker
restarts via Postgres (`monitoring_targets` table).

---

## CLI equivalents

```bash
# Start watching AAPL on a 24h trading-day cadence
curl -X POST http://localhost:8000/monitor_start \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","cadence_seconds":86400,"peers":["MSFT","GOOGL"]}'

# List active monitors
curl http://localhost:8000/monitor

# Pull history for one ticker
curl http://localhost:8000/monitor/AAPL/history

# Stop a watch
curl -X DELETE http://localhost:8000/monitor/AAPL
```

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Monitor sits in `Quiet` forever, no price shown. | `compute_baselines` failed on add (logged as `baseline_compute_failed`). Common causes: unknown/delisted ticker, yfinance rate-limit, transient network. Delete and re-add, or wait for the next manual ticker check. |
| `Last run` never updates. | Worker isn't running (`arq_pool` is `None` if `docker compose up` didn't start the `worker` service), or the trading-day gate is suppressing ticks (e.g., weekend on `NYSE`). |
| Alerts fire constantly. | Baselines are too tight — verify the 30-day window has variance. Triggers are deliberately simple; tune `REFLECTION_*` and trigger thresholds in `backend/app/config.py` if needed. |
| `stop` button 404s. | Ticker already deactivated, or never registered. The list will refresh after the call regardless. |

See also: the **§3B** row in the [README](../README.md) compliance matrix
for the brief-mapping, and `backend/tests/test_monitoring_triggers.py` for
the exact trigger contracts.
