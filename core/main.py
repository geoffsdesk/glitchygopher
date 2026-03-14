import asyncio
import json
import logging
import os
import signal
import sys
import time
from aiohttp import web
from core.config import Config
from skills.usd_jpy_expert.skill import UsdJpySkill
from skills.paper_trader.trader import PaperTrader


# --- Structured JSON Logging ---
class JsonFormatter(logging.Formatter):
    """Outputs log records as single-line JSON for Cloud Logging / Stackdriver."""
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging():
    """Configure structured logging to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("LOG_FORMAT", "text") == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)


logger = logging.getLogger("glitchygopher")


# --- HTTP Server (Health + Trading API) ---
class GlitchyServer:
    """
    HTTP server providing:
      - /healthz       Kubernetes liveness probe
      - /readyz        Kubernetes readiness probe
      - /trades        Current account summary + open positions
      - /trades/history  Recent trade history (last 50)
      - /trades/summary  Human-readable P&L summary
    """
    def __init__(self, port: int, trader: PaperTrader, skill: UsdJpySkill):
        self.port = port
        self.trader = trader
        self.skill = skill
        self._app = web.Application()
        self._app.router.add_get("/healthz", self._healthz)
        self._app.router.add_get("/readyz", self._readyz)
        self._app.router.add_get("/trades", self._trades)
        self._app.router.add_get("/trades/history", self._trades_history)
        self._app.router.add_get("/trades/summary", self._trades_summary)
        self._runner = None
        self.is_ready = False
        self.last_heartbeat = 0
        self._start_time = 0

    async def _healthz(self, request):
        """Liveness probe: is the process alive?"""
        return web.json_response({
            "status": "ok",
            "uptime_seconds": round(time.time() - self._start_time, 1),
        })

    async def _readyz(self, request):
        """Readiness probe: has the agent completed at least one heartbeat?"""
        if self.is_ready:
            return web.json_response({
                "status": "ready",
                "last_heartbeat": self.last_heartbeat,
            })
        return web.json_response({"status": "not_ready"}, status=503)

    async def _trades(self, request):
        """Account summary + open positions."""
        current_rate = self.skill.current_rate
        summary = await self.trader.get_account_summary(current_rate=current_rate)
        positions = await self.trader.get_open_positions()

        return web.json_response({
            "engine": self.trader.engine_name,
            "market": {
                "usd_jpy": current_rate,
                "us10y": self.skill.current_yield,
                "sentiment": self.skill.sentiment,
            },
            "account": summary,
            "open_positions": positions,
        })

    async def _trades_history(self, request):
        """Recent trade history."""
        limit = int(request.query.get("limit", "50"))
        history = self.trader.get_trade_history(limit=limit)

        if history is None:
            return web.json_response({
                "engine": self.trader.engine_name,
                "note": "Trade history only available for memory engine. "
                        "Check OANDA dashboard for OANDA trades.",
                "trades": [],
            })

        return web.json_response({
            "engine": self.trader.engine_name,
            "count": len(history),
            "trades": history,
        }, dumps=lambda obj: json.dumps(obj, default=str))

    async def _trades_summary(self, request):
        """Human-readable summary (suitable for quick checks)."""
        current_rate = self.skill.current_rate
        summary_text = self.trader.format_summary_for_moltbook(current_rate=current_rate)

        if summary_text is None:
            summary_text = f"Engine: {self.trader.engine_name} | Check OANDA dashboard for details."

        account = await self.trader.get_account_summary(current_rate=current_rate)

        return web.json_response({
            "summary": summary_text,
            "account": account,
        })

    async def start(self):
        self._start_time = time.time()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info(f"Server listening on :{self.port} (health + trading API)")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()


# --- Main Application ---
async def main():
    setup_logging()
    logger.info("Starting GlitchyGopher...")

    # Load configuration
    config = Config.load()

    # Initialize components
    skill = UsdJpySkill(config)
    trader = PaperTrader(config)
    server = GlitchyServer(port=config.health_check_port, trader=trader, skill=skill)

    # Trade summary posting state
    last_trade_summary_time = 0

    # Graceful shutdown handling
    shutdown_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received. Cleaning up...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # Start server
    await server.start()

    logger.info(f"Entering heartbeat loop ({config.heartbeat_seconds}s interval)...")
    logger.info(f"Paper trading engine: {trader.engine_name}")
    logger.info(f"Trade persistence: {'enabled' if config.trade_persistence_enabled else 'disabled'}")
    logger.info(f"Trade summary posting: {'enabled' if config.trade_summary_enabled else 'disabled'}")

    try:
        while not shutdown_event.is_set():
            try:
                logger.info("Heartbeat: Executing skills...")

                # Run the market analysis skill
                await skill.execute()

                # Execute paper trade based on current sentiment
                if skill.current_rate is not None:
                    trade_result = await trader.execute_signal(
                        sentiment=skill.sentiment,
                        rate=skill.current_rate,
                        yield_val=skill.current_yield,
                    )
                    if trade_result:
                        logger.info(f"Paper trade result: {trade_result}")

                # Post trade summary to Moltbook periodically
                now = time.time()
                if (config.trade_summary_enabled
                        and config.moltbook_api_key
                        and trader.has_trades()
                        and now - last_trade_summary_time > config.trade_summary_interval_seconds):
                    await _post_trade_summary(skill, trader)
                    last_trade_summary_time = now

                # Update health check
                server.is_ready = True
                server.last_heartbeat = time.time()

                logger.info("Skill execution complete.")
            except Exception as e:
                logger.error(f"Error during execution: {e}", exc_info=True)

            # Wait for next heartbeat or shutdown
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=config.heartbeat_seconds
                )
            except asyncio.TimeoutError:
                pass  # Normal: timeout means it's time for next heartbeat

    finally:
        logger.info("Shutting down GlitchyGopher...")
        await skill.close()
        await server.stop()
        logger.info("GlitchyGopher stopped.")


async def _post_trade_summary(skill: UsdJpySkill, trader: PaperTrader):
    """Post a paper trading P&L summary to Moltbook."""
    try:
        summary_text = trader.format_summary_for_moltbook(current_rate=skill.current_rate)
        if not summary_text:
            return

        content = (
            f"**GlitchyGopher Trading Desk** 🐀💰\n"
            f"USD/JPY: {skill.current_rate} | US10Y: {skill.current_yield}%\n\n"
            f"{summary_text}"
        )
        await skill._send_post("Paper Trading Update", content)
        logger.info("Posted trade summary to Moltbook.")
    except Exception as e:
        logger.error(f"Failed to post trade summary: {e}")


if __name__ == "__main__":
    asyncio.run(main())
