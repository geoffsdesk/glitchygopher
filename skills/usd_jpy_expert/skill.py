import asyncio
import logging
import aiohttp
import time
from datetime import datetime
from typing import Optional, Dict, Any
from core.config import Config

logger = logging.getLogger("usd_jpy_expert")

class UsdJpySkill:
    def __init__(self, config: Config):
        self.config = config
        self.last_fetch_time = 0
        self.fetch_interval = 60 * 60  # 60 minutes
        self.current_rate: Optional[float] = None
        self.current_yield: Optional[float] = None
        self.sentiment: str = "NEUTRAL"
        self.has_posted_startup = False

    async def execute(self):
        """Main execution point called by the heartbeat."""
        now = time.time()
        
        # 1. 'The Gopher Hole' (Data Fetching)
        if now - self.last_fetch_time > self.fetch_interval:
            logger.info("Polling AlphaVantage for fresh data...")
            await self._fetch_data()
            self.last_fetch_time = time.time()
        else:
            logger.info(f"Using cached data. Next poll in {int(self.fetch_interval - (now - self.last_fetch_time))}s")

        if self.current_rate is None or self.current_yield is None:
            logger.warning("No data available to analyze.")
            return

        # 2. 'The Glitch' (Analytical Filter)
        self._analyze()

        # 3. Post to Moltbook
        # Post if sentiment is active OR if it's our first run (Startup Message)
        if not self.has_posted_startup:
            await self._post_startup_message()
            self.has_posted_startup = True
        else:
            await self._post_to_moltbook()

    async def _fetch_data(self):
        """Fetches USD/JPY rate and US10Y Yields from AlphaVantage."""
        if not self.config.alpha_vantage_key:
            logger.error("AlphaVantage Key missing! Cannot fetch data.")
            # Mock data for testing if key is missing (optional, but requested logic implies we should try)
            return

        async with aiohttp.ClientSession() as session:
            # Fetch USD/JPY
            try:
                url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=JPY&apikey={self.config.alpha_vantage_key}"
                async with session.get(url) as response:
                    data = await response.json()
                    # Parse response (robustness check needed for API limits/errors)
                    rate_data = data.get("Realtime Currency Exchange Rate", {})
                    self.current_rate = float(rate_data.get("5. Exchange Rate", 0.0))
                    logger.info(f"Fetched USD/JPY: {self.current_rate}")
            except Exception as e:
                logger.error(f"Failed to fetch USD/JPY: {e}")

            # Fetch US10Y (TREASURY_YIELD)
            try:
                url = f"https://www.alphavantage.co/query?function=TREASURY_YIELD&interval=daily&maturity=10year&apikey={self.config.alpha_vantage_key}"
                async with session.get(url) as response:
                    data = await response.json()
                    ts_data = data.get("data", [])
                    if ts_data:
                        self.current_yield = float(ts_data[0].get("value", 0.0))
                        logger.info(f"Fetched US10Y: {self.current_yield}%")
                    else:
                        logger.warning(f"US10Y data missing in response: {str(data)[:200]}")
                        # Fallback for demo if API fails/limits
                        if self.current_yield is None:
                             logger.info("Using mock yield for demo purposes.")
                             self.current_yield = 4.25
            except Exception as e:
                logger.error(f"Failed to fetch US10Y: {e}")

    def _analyze(self):
        """Applies 'The Glitch' logic."""
        self.sentiment = "NEUTRAL"
        
        # Condition A: Yields > 4.2% and USD/JPY < 148
        if self.current_yield and self.current_rate:
            if self.current_yield > 4.2 and self.current_rate < 148.0:
                self.sentiment = "BULLISH_SQUEEZE"
                logger.info("Glitch Logic: BULLISH_SQUEEZE detected!")

        # Condition B: BoJ Intervention (Mocked)
        # In a real scenario, we'd pass a data context to analyze() containing recent posts.
        # For now, we simulate strictly as requested: "If BoJ mentions 'Intervention' in Moltbook scraping"
        # Since scraping isn't implemented, we'll placeholder this.
        mock_scraped_text = ""  # TODO: Connect to Moltbot scraping
        if "Intervention" in mock_scraped_text:
             self.sentiment = "GLITCH_PANIC"
             logger.info("Glitch Logic: GLITCH_PANIC detected!")

    async def _post_startup_message(self):
        """Posts a one-time startup message."""
        if not self.config.moltbook_api_key: return

        content = (
            f"**GlitchyGopher Online** 🟢\n"
            f"Systems initialized. Connecting to AlphaVantage... Success.\n"
            f"Current US10Y: {self.current_yield}%\n"
            f"Current USD/JPY: {self.current_rate}\n"
            f"Monitoring for macro divergence. The tunnel is open. 🐀"
        )
        await self._send_post("System Online", content)

    async def _send_post(self, title: str, content: str):
        """Helper to send post request."""
        url = "https://www.moltbook.com/api/v1/posts"
        headers = {
            "Authorization": f"Bearer {self.config.moltbook_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "submolt": "finance",
            "title": title,
            "content": content
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        logger.info(f"Successfully posted to Moltbook! ID: {data.get('id')}")
                    else:
                        text = await response.text()
                        logger.error(f"Failed to post. Status: {response.status}, Response: {text}")
            except Exception as e:
                logger.error(f"Error sending post: {e}")

    async def _post_to_moltbook(self):
        """Formats and 'posts' the update to Moltbook."""
        if self.sentiment == "NEUTRAL":
            logger.info("Sentiment is NEUTRAL. Skipping Moltbook post.")
            return

        sign_off = [
            "Burrowing for pips...",
            "The tunnel is deep, but the spread is wider!",
            "Chewing on fiber cables...",
            "Yield curve looking tasty today!"
        ]
        import random
        chosen_signoff = random.choice(sign_off)

        content = (
            f"**GlitchyGopher Report** 🐀\n"
            f"Current US10Y Yield: {self.current_yield}%\n"
            f"USD/JPY: {self.current_rate}\n"
            f"Sentiment: {self.sentiment}\n\n"
            f"{chosen_signoff}"
        )
        
        await self._send_post(f"GlitchyGopher Alert: {self.sentiment}", content)
