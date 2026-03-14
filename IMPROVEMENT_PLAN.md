# GlitchyGopher — Improvement Plan & Paper Trading Investigation

## Part 1: Code-Level Issues & Fixes

### 1. Duplicate Line in `__init__`

```python
# skill.py line 21-22
self.last_post_time = 0
self.last_post_time = 0  # ← duplicate, remove this
```

### 2. `aiohttp.ClientSession` Created Per Request

Every API call in `_fetch_data`, `_send_post`, `_check_feed_and_engage`, and `_reply_to_post` creates a new `aiohttp.ClientSession`. This is wasteful — sessions manage connection pools, and the docs explicitly recommend reusing them.

**Fix:** Create one session in `__init__` (or on first use), close it on shutdown.

```python
class UsdJpySkill:
    def __init__(self, config: Config):
        ...
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
```

### 3. `google.generativeai` Imported Inside Methods

`import google.generativeai as genai` appears inside `_post_to_moltbook` and `_reply_to_post`. It also calls `genai.configure()` on every invocation, which is unnecessary after the first call.

**Fix:** Import at module level, configure once in `__init__`.

### 4. No Retry / Backoff Logic

All HTTP calls use bare try/except with no retries. AlphaVantage rate-limits at 5 calls/minute on the free tier, and Moltbook could return transient 5xx errors.

**Fix:** Add exponential backoff with a decorator or use `aiohttp_retry`.

### 5. Hardcoded Magic Numbers

Thresholds (4.2% yield, 148 USD/JPY, 31-minute cooldown, 60-minute fetch interval, 20-second comment rate limit) are all scattered through the code.

**Fix:** Move to `Config` as environment-variable-backed settings with defaults.

```python
@dataclass
class Config:
    ...
    yield_threshold: float = 4.2
    rate_threshold: float = 148.0
    post_cooldown_minutes: int = 31
    fetch_interval_minutes: int = 60
    comment_rate_limit_seconds: int = 20
```

### 6. Stale Data Fallback Is Dangerous

Line 94-96 in `skill.py`: if the US10Y API call fails, it silently sets `self.current_yield = 4.25` as a "mock for demo." This means the bot could post analysis based on fake data with no indication to readers.

**Fix:** Remove the mock fallback entirely. If data is unavailable, skip posting (which it already does for `None`). If you need demo mode, make it explicit via a `DEMO_MODE` env var.

### 7. Gann Box Levels Are Hardcoded in Prompts

Support/resistance levels (152.00, 150.80, 155.50, 158.20) and the yield curve threshold (4.3%) are baked into the Gemini prompt string. These become stale as markets move.

**Fix:** Either compute them dynamically from historical data, or store them in a config file that can be updated without code changes.

### 8. `replied_posts` Is Unbounded In-Memory Set

The set of replied post IDs grows forever. In a long-running container, this is a slow memory leak.

**Fix:** Use an LRU cache or trim to the last N entries periodically.

### 9. Heartbeat Log Message Is Wrong

`main.py` line 25 says "15 minutes" but the actual sleep is 60 seconds. Minor, but misleading when reading logs.

### 10. No Health Check Endpoint

The Kubernetes deployment has no liveness or readiness probes. If the event loop deadlocks or the process hangs, K8s won't know to restart it.

**Fix:** Add a simple HTTP health endpoint (aiohttp server on a secondary port) and configure probes in `deployment.yaml`.

---

## Part 2: Architecture Improvements

### A. Persistent State

Currently all state (last fetch time, replied posts, posted values) is in memory. A pod restart loses everything, causing duplicate startup posts and re-replies. Options:

- **Lightweight:** Write state to a JSON file on an ephemeral volume (survives container restarts, not pod evictions)
- **Durable:** Use a small Redis instance or Cloud Firestore

### B. Structured Logging

Replace f-string log messages with structured logging (JSON format). This makes it much easier to query in Cloud Logging / Stackdriver.

### C. Graceful Shutdown

`main.py` catches `KeyboardInterrupt` but `asyncio.run()` may not propagate `SIGTERM` (what K8s sends). Add a signal handler.

### D. Testing

The project has zero tests. Priority test targets:

1. `_analyze()` — Pure logic, easy to unit test. Parameterize across yield/rate combos.
2. `_fetch_data()` — Mock aiohttp responses, test parsing and error paths.
3. `_check_feed_and_engage()` — Mock feed responses, verify keyword filtering and self-reply avoidance.
4. Rate limiting — Verify cooldown timers work correctly.

### E. CI/CD Pipeline

Add a GitHub Actions workflow:

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt pytest pytest-asyncio aioresponses
      - run: pytest tests/ -v
  build:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: google-github-actions/auth@v2
        with: { credentials_json: '${{ secrets.GCP_SA_KEY }}' }
      - run: gcloud builds submit --tag gcr.io/glitchygopher/glitchygopher:latest .
```

### F. Complete the BoJ Intervention Feature

The `GLITCH_PANIC` signal is documented in the README but stubbed with an empty string. Two paths:

1. **Scan Moltbook feed** — You're already fetching posts in `_check_feed_and_engage`. Add "intervention" keyword detection there and set sentiment accordingly.
2. **News API** — Use a news/RSS feed (e.g., Reuters, Bloomberg RSS) to detect BoJ statements. More reliable than social posts.

---

## Part 3: Paper Trading via TradingView — Investigation

### The Core Problem

**TradingView does not expose a public API for its paper trading engine.** There is no way for an external Python script to place, modify, or cancel paper trades inside TradingView's simulated account. Pine Script is the only way to automate actions within TradingView itself, and Pine Script cannot receive external commands.

### Viable Approaches

#### Option A: TradingView Alerts → Webhook → Broker Paper Account (Recommended)

This is the most practical architecture for GlitchyGopher:

```
GlitchyGopher detects signal
  → Posts to Moltbook (existing)
  → ALSO sends order to broker paper account (new)

TradingView (optional):
  Pine Script strategy → Alert → Webhook → Your Flask/FastAPI endpoint
  → Validates signal → Sends to broker paper account
```

**Best broker for USD/JPY paper trading: OANDA**

- OANDA has a free Practice (demo) account with full API access
- Native USD/JPY support (it's a forex-first broker)
- Python SDK: `pip install v20` (official OANDA v20 bindings)
- REST API at `https://api-fxpractice.oanda.com` for paper trading
- No minimum deposit for demo

**Integration sketch:**

```python
# New file: skills/paper_trader/skill.py
import v20

class PaperTrader:
    def __init__(self, config):
        self.api = v20.Context(
            'api-fxpractice.oanda.com',
            token=config.oanda_api_key
        )
        self.account_id = config.oanda_account_id

    async def place_trade(self, sentiment: str, rate: float):
        """Place a paper trade based on GlitchyGopher's signal."""
        if sentiment == "BULLISH_SQUEEZE":
            # Long USD/JPY — expecting rate to rise
            units = 1000  # micro lot
        elif sentiment == "GLITCH_PANIC":
            # Short USD/JPY — expecting intervention to push rate down
            units = -1000
        else:
            return  # No trade on NEUTRAL

        response = self.api.order.market(
            self.account_id,
            instrument="USD_JPY",
            units=units,
        )
        return response
```

#### Option B: Self-Contained Python Paper Trading Engine

Build the simulation entirely within GlitchyGopher — no external broker needed.

**Pros:** No new API keys, no broker dependency, full control
**Cons:** No order book realism, no slippage simulation, you build everything

This would involve tracking a virtual portfolio (balance, open positions, P&L), recording entry/exit prices against real AlphaVantage data, and posting trade results to Moltbook.

#### Option C: Alpaca (Stocks/Crypto Only)

Alpaca has an excellent Python SDK and free paper trading, but **does not support forex pairs** like USD/JPY. Only relevant if GlitchyGopher expands to equities.

### Recommendation

**Go with Option A (OANDA)** for real paper trading with USD/JPY, and **add Option B as a lightweight fallback** so the bot can still track hypothetical trades when OANDA is unavailable.

For TradingView specifically: use it as a charting/visualization layer. You can display GlitchyGopher's trades on TradingView charts using the `lightweight-charts` Python library or by pushing data to TradingView via Pine Script indicators, but the actual trade execution should go through OANDA's API.

### New Dependencies

```
# additions to requirements.txt
v20>=3.0.0              # OANDA v20 API
aiohttp-retry>=2.8.0    # Retry logic for HTTP calls
```

### New Environment Variables

```
OANDA_API_KEY=your_practice_api_token
OANDA_ACCOUNT_ID=your_practice_account_id
OANDA_ENVIRONMENT=practice   # "practice" or "live"
```

---

## Summary: Priority Order

| Priority | Item | Effort |
|----------|------|--------|
| 1 | Fix bugs (duplicate line, wrong log message, mock data fallback) | 10 min |
| 2 | Reuse aiohttp session | 30 min |
| 3 | Move magic numbers to Config | 30 min |
| 4 | Add unit tests for `_analyze()` and data parsing | 2 hrs |
| 5 | OANDA paper trading integration | 4 hrs |
| 6 | In-memory paper trading fallback | 2 hrs |
| 7 | Add health check endpoint + K8s probes | 1 hr |
| 8 | Implement BoJ intervention detection from feed | 1 hr |
| 9 | CI/CD pipeline | 1 hr |
| 10 | Structured logging + graceful shutdown | 1 hr |

---

## Sources

- [OANDA v20 Developer Portal](https://developer.oanda.com/)
- [OANDA REST API Introduction](https://developer.oanda.com/rest-live-v20/introduction/)
- [TradingView Webhook Alerts](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/)
- [TradingView Webhook Guide (Pineify)](https://pineify.app/resources/blog/tradingview-webhook-the-complete-guide-to-automating-alerts-and-trade-execution/)
- [Alpaca Python SDK](https://alpaca.markets/sdks/python/)
- [tradingview-ta PyPI](https://pypi.org/project/tradingview-ta/)
- [Can You Paper Trade on TradingView Using Python?](https://trading-strategies.academy/archives/390)
