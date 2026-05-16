# Monitoring — operator guide

M.I.R.A.'s monitor feature watches a ticker on a cadence and runs a full
`/analyze` only when something interesting changes — so you don't pay
for or wade through reports about quiet days.

## What a monitor does

Every tick, the worker recomputes a 30-day price/volume baseline for the
ticker and fires a fresh analysis when **any one** of three triggers
crosses the line:

| Trigger | Condition | Action on fire |
|---|---|---|
| `articles` | ≥ 5 new article URLs since the last tick | Enqueue `analyze_ticker` job tagged `PROACTIVE_ALERT` |
| `price_2sigma` | `|today_close − 30 d mean| > 2 × 30 d std` | same |
| `volume_2x` | `today_volume > 2 × 30 d avg volume` | same |

The resulting `AnalysisReport` carries `alert_tag = "PROACTIVE_ALERT"`
and `monitor_trigger` set to the first firing trigger. Pre-trigger
context (`new_articles` count, `price_sigma`, `volume_ratio`) is captured
in the `monitor_trigger_snapshot` field on the job row so the UI's
trigger pills show real numbers instead of "current σ" mixed with
"historical fire status."

## How a monitor actually runs

1. `POST /monitor_start` computes baselines synchronously. If yfinance
   refuses (delisted ticker, no history, rate-limited), the API returns
   `400 {"detail": {"code": "BASELINE_COMPUTE_FAILED", ...}}` and **no
   monitor row is created**. This prevents a half-broken monitor from
   sitting in the UI forever.
2. On success the monitor row is persisted, baselines are stamped on it,
   and the first `monitor_tick` is enqueued via arq with
   `_defer_by=cadence_seconds`.
3. Each `monitor_tick` runs in a `try/finally`. The `finally` clause
   **always** schedules the next tick (so weekends, baseline failures,
   and trading-day skips don't kill the schedule), unless the monitor
   has been deactivated. Concretely the chain stops in exactly two
   cases:
   - The monitor row no longer exists (deleted from DB).
   - `target.active = False` (via `DELETE /monitor/{ticker}` or manual
     intervention).
4. Trading-day gate (`pandas_market_calendars`, NYSE by default) skips
   the body on weekends and US market holidays but re-enqueues the next
   tick anyway. Set `MONITOR_TRADING_CALENDAR` to `NASDAQ`, `LSE`, etc.
   if you need a different calendar.

If the worker is **down** when a tick is due, the deferred arq job sits
in the Redis queue and runs on next worker start. Your schedule slips
by the outage duration but doesn't lose ticks.

## Add a monitor

The UI form at `/monitor` calls `POST /monitor_start`:

| Field | Required | Notes |
|---|---|---|
| Ticker | yes | Upper-cased, yfinance-resolvable. Bad tickers fail loudly at add time. |
| Peers (comma-separated) | no | Used by reflection's `peer_news` + `peer_fundamentals` when a fired alert runs analysis. |
| Cadence | yes | 1 h / 4 h / 24 h (trading days) — see floor below. |

**Trading calendar is global** (set via env var
`MONITOR_TRADING_CALENDAR`, default `NYSE`). The per-monitor calendar
dropdown was removed — it never connected to anything server-side.

## Cadence floor

Minimum cadence is **3600 seconds (1 hour)**, enforced server-side by
the `MonitorStartRequest` pydantic schema. Sub-hour ticks would hammer
yfinance + NewsAPI past their free-tier rate limits, and the brief
frames monitoring as a background cadence rather than near-realtime
streaming. Submit `cadence_seconds < 3600` and you'll get a 422.

The UI no longer offers a Weekly option. Weekly always lands on the
same day-of-week; if that day intersects an NYSE holiday chain
(Thanksgiving, holiday Fridays around July 4th, Christmas Day on a
Friday), the trading-day gate skips every re-enqueue indefinitely.
Daily / 4h / 1h are all unaffected because they always cross a weekday
within the next gap.

## Auto-refresh

The `/monitor` page polls `/monitor` and `/monitor/{ticker}/history`
every 60 seconds while the tab is visible (`document.visibilityState
=== "visible"`). Background tabs don't poll. Manual refresh is
unnecessary — fires landing within the cadence window will appear on
their own.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Add returns 400 `BASELINE_COMPUTE_FAILED` | yfinance returned no history (delisted, ticker malformed, or upstream rate-limited). Retry in a minute or try a different ticker. |
| Row stays "Quiet" — baseline shows `null` | Should be impossible after the baseline-up-front fix; if seen, the monitor was created by an older build. Stop and re-add. |
| `last_run_at` stuck on an old timestamp | Worker isn't running, or the most recent run hit a transient `compute_baselines` error (see `mira_monitor_ticks_total{status="failed_baseline_compute"}` on the metrics endpoint). |
| No fires after several days | Trading-day gate (weekend/holiday run) + the actual triggers don't trip on quiet movement. Check the metrics counter `mira_monitor_ticks_total{status="skipped_non_trading_day"}` to confirm ticks are still being scheduled. |
| Stop button does nothing | Old build with a non-idempotent `DELETE`. Refresh the page; the new client treats `404` as success and the server now returns `200 + was_active=false` regardless. |

## Metrics

Prometheus at `GET /metrics`:

- `mira_monitor_ticks_total{status=success|skipped_non_trading_day|failed_baseline_compute|target_inactive}` — one increment per tick, labeled by which branch ran.
- `mira_monitor_triggers_total{trigger=articles|price_2sigma|volume_2x}` — counts each trigger fire.
