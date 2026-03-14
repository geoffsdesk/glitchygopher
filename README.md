# GlitchyGopher

![Glitchy Gopher Logic](assets/avatar.png)

**The Moltbook Agent specialized in High-Conviction USD/JPY Macro Analysis & Paper Trading.**

GlitchyGopher (specifically **GlitchyGopher-9270**) is a proactive autonomous agent built on the OpenClaw framework (custom Python implementation). It monitors the 10-Year US Treasury Yield and the USD/JPY exchange rate to identify market "Glitches" — moments of extreme divergence or squeeze potential — and executes paper trades based on its signals.

## Persona & Logic

- **Vibe**: Goofy, slightly erratic, uses 90s tech slang.
- **Specialization**: USD/JPY Forex pair & US Bond Yields.
- **"The Glitch"**:
  - IF `US10Y Yields > 4.2%` AND `USD/JPY < 148` → **BULLISH SQUEEZE**
  - IF BoJ mentions "Intervention" in Moltbook feed → **GLITCH PANIC**

**Live Profile**: [https://www.moltbook.com/u/GlitchyGopher-9270](https://www.moltbook.com/u/GlitchyGopher-9270)

## Architecture & Tech Stack

- **Runtime**: Python 3.11+
- **LLM**: Google Gemini (via `google-generativeai` SDK)
- **Data Source**: AlphaVantage API (polled every 60 mins)
- **Paper Trading**: OANDA v20 Practice API (with in-memory fallback)
- **Platform**: Google Kubernetes Engine (GKE) Autopilot
- **Security**: GKE Sandbox (gVisor), non-root execution, Kubernetes Secrets
- **Observability**: JSON structured logging, trading API, health probes
- **CI/CD**: GitHub Actions (lint, test, build, push)

## Features

- **Market Analysis**: Fetches USD/JPY and US10Y data, applies signal logic, posts to Moltbook
- **Social Engagement**: Monitors Moltbook feed, replies to relevant posts with AI-generated commentary
- **BoJ Intervention Detection**: Scans feed posts for intervention keywords, triggers GLITCH_PANIC
- **Paper Trading**: Executes virtual trades via OANDA Practice account (or in-memory engine as fallback)
- **Trading API**: HTTP endpoints to monitor positions, P&L, and trade history in real time
- **Trade Summary Posts**: Periodically posts paper trading P&L updates to Moltbook
- **Persistent Trade History**: Trades saved to JSON with atomic writes, survives pod restarts
- **Configurable Thresholds**: All magic numbers (yield/rate thresholds, cooldowns, Gann levels) are environment-variable-backed

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (or use .env)
export GEMINI_API_KEY='your-key'
export ALPHA_VANTAGE_KEY='your-key'
export MOLTBOOK_API_KEY='your-key'

# Optional: OANDA paper trading
export OANDA_API_KEY='your-practice-token'
export OANDA_ACCOUNT_ID='your-practice-account-id'

# Run
python -m core.main
```

### Run Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Monitoring Paper Trades

GlitchyGopher provides three ways to track paper trading activity:

### 1. Trading API (HTTP)

The built-in HTTP server exposes trading data alongside health probes on port 8080.

```bash
# Port-forward if running in K8s
kubectl port-forward deployment/glitchygopher 8080:8080

# Account summary + open positions + current market data
curl localhost:8080/trades

# Recent trade history (default last 50 trades)
curl localhost:8080/trades/history
curl localhost:8080/trades/history?limit=10

# Quick human-readable P&L summary
curl localhost:8080/trades/summary
```

**Example `/trades` response:**

```json
{
  "engine": "memory",
  "market": {
    "usd_jpy": 152.5,
    "us10y": 4.3,
    "sentiment": "BULLISH_SQUEEZE"
  },
  "account": {
    "starting_balance": 100000,
    "realized_pnl": 1500.0,
    "unrealized_pnl": 250.0,
    "total_pnl": 1750.0,
    "open_trade_count": 1,
    "total_trades": 5,
    "win_rate": 66.7
  },
  "open_positions": [
    {
      "trade_id": "mem-0005",
      "direction": "long",
      "units": 1000,
      "entry_price": 151.8,
      "sentiment": "BULLISH_SQUEEZE"
    }
  ]
}
```

### 2. Moltbook Trade Summary Posts

Every 2 hours (configurable), GlitchyGopher posts a "Trading Desk" update to Moltbook showing open positions, total P&L, and win rate — alongside its regular market commentary. Disable with `TRADE_SUMMARY_ENABLED=false`.

### 3. Persistent Trade History (JSON)

Trades are saved to `/app/data/trade_history.json` after every trade event using atomic writes (temp file + rename). On pod restart, the in-memory engine restores all trades, counters, and the last signal state. For Kubernetes, mount a PersistentVolumeClaim at `/app/data/`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Liveness probe (uptime) |
| `/readyz` | GET | Readiness probe (has completed one heartbeat) |
| `/trades` | GET | Account summary, open positions, current market data |
| `/trades/history` | GET | Recent trade history (`?limit=N`, default 50) |
| `/trades/summary` | GET | Human-readable P&L one-liner |

## Deployment (GKE)

### 1. Build Container
```bash
gcloud builds submit --tag gcr.io/glitchygopher/glitchygopher:latest .
```

### 2. Configure Secrets
```bash
kubectl create secret generic glitchygopher-secrets \
  --from-literal=GEMINI_API_KEY='YOUR_KEY' \
  --from-literal=ALPHA_VANTAGE_KEY='YOUR_KEY' \
  --from-literal=MOLTBOOK_API_KEY='YOUR_KEY' \
  --from-literal=OANDA_API_KEY='YOUR_KEY' \
  --from-literal=OANDA_ACCOUNT_ID='YOUR_ACCOUNT_ID'
```

### 3. Deploy
```bash
kubectl apply -f deployment.yaml
```

The deployment manifest includes liveness/readiness probes, a PersistentVolumeClaim for trade history, and optional OANDA secrets.

## Configuration

All settings are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | (required) | Google Gemini API key |
| `ALPHA_VANTAGE_KEY` | (required) | AlphaVantage API key |
| `MOLTBOOK_API_KEY` | (required) | Moltbook API key |
| `OANDA_API_KEY` | (optional) | OANDA Practice API token |
| `OANDA_ACCOUNT_ID` | (optional) | OANDA Practice account ID |
| `OANDA_ENVIRONMENT` | `practice` | `practice` or `live` |
| `PAPER_TRADING_ENABLED` | auto | Auto-enabled if OANDA key is set |
| `PAPER_TRADE_UNITS` | `1000` | Trade size (micro lot) |
| `YIELD_THRESHOLD` | `4.2` | US10Y yield threshold for BULLISH_SQUEEZE |
| `RATE_THRESHOLD` | `148.0` | USD/JPY rate threshold for BULLISH_SQUEEZE |
| `SUPPORT_LEVELS` | `152.00, 150.80` | Gann box support levels |
| `RESISTANCE_LEVELS` | `155.50, 158.20` | Gann box resistance levels |
| `FETCH_INTERVAL_SECONDS` | `3600` | AlphaVantage polling interval |
| `POST_COOLDOWN_SECONDS` | `1860` | Moltbook posting cooldown |
| `HEARTBEAT_SECONDS` | `60` | Main loop interval |
| `HEALTH_CHECK_PORT` | `8080` | Port for all HTTP endpoints |
| `LOG_FORMAT` | `text` | `text` or `json` (JSON for Cloud Logging) |
| `TRADE_SUMMARY_ENABLED` | `true` | Post P&L summaries to Moltbook |
| `TRADE_SUMMARY_INTERVAL_SECONDS` | `7200` | How often to post trade summaries (2h) |
| `TRADE_PERSISTENCE_ENABLED` | `true` | Save trade history to disk |
| `TRADE_HISTORY_PATH` | `/app/data/trade_history.json` | Path for trade history file |

## Project Structure

```
glitchygopher/
├── core/
│   ├── config.py              # Configuration (env-var backed)
│   └── main.py                # Heartbeat loop, HTTP server, graceful shutdown
├── skills/
│   ├── usd_jpy_expert/
│   │   └── skill.py           # Market analysis, Moltbook posting, BoJ detection
│   └── paper_trader/
│       ├── trader.py           # Unified facade (OANDA or memory)
│       ├── oanda_trader.py     # OANDA v20 Practice integration
│       ├── memory_trader.py    # In-memory paper trading engine
│       └── persistence.py      # JSON trade history read/write
├── tests/                      # pytest test suite (58 tests)
├── .github/workflows/ci.yml   # GitHub Actions CI/CD
├── Dockerfile                  # Container (Python 3.11-slim, non-root)
├── deployment.yaml             # GKE Autopilot + gVisor + health probes + PVC
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Test/lint dependencies
└── pyproject.toml              # pytest + ruff config
```
