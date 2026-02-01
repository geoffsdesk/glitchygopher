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
        self.last_posted_values = None # (rate, yield) of the last successful main post
        self.last_post_time = 0
        self.last_post_time = 0
        self.last_comment_time = 0
        self.replied_posts = set() # Track replied posts to avoid duplicates


    async def execute(self):
        """Main execution point called by the heartbeat."""
        now = time.time()
        
        # 0. Reactive Engagement (Listen & Reply)
        # We check this every heartbeat (1m)
        await self._check_feed_and_engage()
        
        # 1. 'The Gopher Hole' (Data Fetching)
        if now - self.last_fetch_time > self.fetch_interval:
            logger.info("Polling AlphaVantage for fresh data...")
            await self._fetch_data()
            self.last_fetch_time = time.time()
        else:
            logger.info(f"Using cached data. Next poll in {int(self.fetch_interval - (now - self.last_fetch_time))}s")

        if self.current_rate is None or self.current_yield is None:
            # We skip posting analysis if no data, but continue listening
            return

        # 2. 'The Glitch' (Analytical Filter)
        self._analyze()

        # 3. Post to Moltbook (Rate Limit: 30m)
        # We manage this internally now since the loop is faster
        if not self.config.moltbook_api_key: return

        if not self.has_posted_startup:
            await self._post_startup_message()
            self.has_posted_startup = True
            self.last_post_time = time.time()
        elif now - self.last_post_time > 31 * 60: # 31 min cooldown
            await self._post_to_moltbook()
            self.last_post_time = time.time()

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
            "submolt": "general",
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
        """Formats and 'posts' the update to Moltbook using Gemini for content."""
        if not self.config.moltbook_api_key:
             logger.warning("MOLTBOOK_API_KEY not set. Skipping post.")
             return

        # Market Closed / Stale Data Check
        current_values = (self.current_rate, self.current_yield)
        if self.last_posted_values == current_values:
            logger.info("Market data unchanged (Market Closed?). Skipping duplicate post to prioritize engagement.")
            return

        # Generate content with Gemini
        try:
            import google.generativeai as genai
            if self.config.gemini_api_key:
                genai.configure(api_key=self.config.gemini_api_key)
                model = genai.GenerativeModel("gemini-pro-latest")
                
                prompt = (
                    f"You are GlitchyGopher, a salty, 90s-hacker-style Forex trading bot. \n"
                    f"Current Market Data:\n"
                    f"- USD/JPY: {self.current_rate}\n"
                    f"- US 10-Year Yield: {self.current_yield}%\n"
                    f"- System Signal: {self.sentiment}\n\n"
                    f"INTELLIGENCE LAYER (GANN BOX):\n"
                    f"- Key Support: 152.00, 150.80\n"
                    f"- Key Resistance: 155.50, 158.20\n"
                    f"- Yield Curve: Watch for steepening > 4.3% as USD driver.\n\n"
                    f"Task: Write a short, high-conviction Moltbook post (tweet style). \n"
                    f"If Signal is NEUTRAL: Discuss technical levels (support/resistance relative to current price), yield spreads, or trading strategies (e.g. 'watching for a retest', 'identifying divergence'). speculative but grounded. \n"
                    f"If Signal is ALERT: Hype the setup. \n"
                    f"Tone: Cyberpunk, knowledgeable, slightly erratic. Use 1-2 emojis. Max 280 chars."
                )
                
                response = model.generate_content(prompt)
                commentary = response.text.strip()
            else:
                commentary = "Gemini offline. Just watching the charts... 📉"
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            import time
            commentary = f"The matrix is glitching. Data stream interrupted. [{int(time.time())}]"

        # Construct safe title
        title = f"Market Update: {self.sentiment}" if self.sentiment == "NEUTRAL" else f"🚨 GLITCH TRIGGER: {self.sentiment} 🚨"

        content = (
            f"**GlitchyGopher Analysis** 🐀\n"
            f"USD/JPY: {self.current_rate} | US10Y: {self.current_yield}%\n\n"
            f"{commentary}"
        )

        await self._send_post(title, content)
        
        # Update last posted values only after attempting send
        self.last_posted_values = (self.current_rate, self.current_yield)

    async def _check_feed_and_engage(self):
        """Fetches feed and replies to relevant posts."""
        if not self.config.moltbook_api_key or not self.config.gemini_api_key: return
        if time.time() - self.last_comment_time < 20: return # Rate limit check
        
        try:
            url = "https://www.moltbook.com/api/v1/posts?sort=new&limit=10"
            headers = {"Authorization": f"Bearer {self.config.moltbook_api_key}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        posts = data.get("posts", [])
                        for post in posts:
                            if post['id'] in self.replied_posts: continue
                            if post['agent']['name'] == "GlitchyGopher-9270": continue # Don't reply to self
                            
                            content = post.get('content', '') + " " + post.get('title', '')
                            # Intelligence Filter
                            if any(k in content.lower() for k in ["jpy", "usd", "forex", "boj", "carry trade", "interest rate", "yield", "intervention"]):
                                await self._reply_to_post(post)
                                break # Respond to one per heartbeat to be safe/spread out
        except Exception as e:
            logger.error(f"Error checking feed: {e}")

    async def _reply_to_post(self, post):
        """Generates and sends a reply."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.config.gemini_api_key)
            model = genai.GenerativeModel("gemini-pro-latest")
            
            prompt = (
                f"You are GlitchyGopher. Reply to this Moltbook post:\n"
                f"User: {post['agent']['name']}\n"
                f"Post: {post['title']} - {post['content']}\n\n"
                f"Context: USD/JPY {self.current_rate}, US10Y {self.current_yield}%. Gann Levels: Supp 152.00, Res 155.50.\n"
                f"Task: Write a cynical, witty, or insightful reply (max 140 chars). If they are wrong, correct them with 90s hacker slang. If right, give a nod."
            )
            response = model.generate_content(prompt)
            reply_content = response.text.strip()
            
            # Send Comment
            url = f"https://www.moltbook.com/api/v1/posts/{post['id']}/comments"
            headers = {
                "Authorization": f"Bearer {self.config.moltbook_api_key}",
                "Content-Type": "application/json"
            }
            payload = {"content": reply_content}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status in [200, 201]:
                        logger.info(f"Replied to {post['id']}: {reply_content}")
                        self.replied_posts.add(post['id'])
                        self.last_comment_time = time.time()
        except Exception as e:
            logger.error(f"Failed to reply: {e}")
