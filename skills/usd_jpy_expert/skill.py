import asyncio
import logging
import aiohttp
import time
from collections import OrderedDict
from datetime import datetime
from typing import Optional, Dict, Any, List
from core.config import Config

logger = logging.getLogger("usd_jpy_expert")

# Keywords that trigger engagement replies
ENGAGEMENT_KEYWORDS = [
    "jpy", "usd", "forex", "boj", "carry trade",
    "interest rate", "yield", "intervention", "yen", "dollar"
]

# Keywords that trigger BoJ intervention panic
BOJ_INTERVENTION_KEYWORDS = [
    "intervention", "boj intervene", "yen buying",
    "rate check", "boj action", "currency intervention"
]

# Max replied posts to track (LRU eviction beyond this)
MAX_REPLIED_POSTS = 500


class LRUSet:
    """Bounded set that evicts oldest entries when full."""
    def __init__(self, maxsize: int = MAX_REPLIED_POSTS):
        self._data: OrderedDict = OrderedDict()
        self._maxsize = maxsize

    def add(self, item):
        if item in self._data:
            self._data.move_to_end(item)
        else:
            self._data[item] = True
            if len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def __contains__(self, item):
        return item in self._data

    def __len__(self):
        return len(self._data)


class UsdJpySkill:
    def __init__(self, config: Config):
        self.config = config
        self.last_fetch_time = 0
        self.current_rate: Optional[float] = None
        self.current_yield: Optional[float] = None
        self.sentiment: str = "NEUTRAL"
        self.has_posted_startup = False
        self.last_posted_values = None  # (rate, yield) of the last successful main post
        self.last_post_time = 0
        self.last_comment_time = 0
        self.replied_posts = LRUSet(MAX_REPLIED_POSTS)
        self.boj_panic_active = False  # Set when BoJ intervention detected in feed

        # Shared HTTP session (created lazily)
        self._session: Optional[aiohttp.ClientSession] = None

        # Gemini model (initialized lazily)
        self._gemini_model = None
        self._gemini_initialized = False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Returns a shared aiohttp session, creating one if needed."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    def _get_gemini_model(self):
        """Returns the Gemini model, initializing on first call."""
        if not self._gemini_initialized and self.config.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.config.gemini_api_key)
                self._gemini_model = genai.GenerativeModel("gemini-pro-latest")
                self._gemini_initialized = True
                logger.info("Gemini model initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                self._gemini_initialized = True  # Don't retry on every call
        return self._gemini_model

    async def close(self):
        """Clean up resources. Call on shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("HTTP session closed.")

    async def execute(self):
        """Main execution point called by the heartbeat."""
        now = time.time()

        # 0. Reactive Engagement (Listen & Reply)
        # We check this every heartbeat (1m) — also scans for BoJ intervention
        await self._check_feed_and_engage()

        # 1. 'The Gopher Hole' (Data Fetching)
        if now - self.last_fetch_time > self.config.fetch_interval_seconds:
            logger.info("Polling AlphaVantage for fresh data...")
            await self._fetch_data()
            self.last_fetch_time = time.time()
        else:
            remaining = int(self.config.fetch_interval_seconds - (now - self.last_fetch_time))
            logger.info(f"Using cached data. Next poll in {remaining}s")

        if self.current_rate is None or self.current_yield is None:
            # We skip posting analysis if no data, but continue listening
            return

        # 2. 'The Glitch' (Analytical Filter)
        self._analyze()

        # 3. Post to Moltbook (Rate Limited)
        if not self.config.moltbook_api_key:
            return

        if not self.has_posted_startup:
            await self._post_startup_message()
            self.has_posted_startup = True
            self.last_post_time = time.time()
        elif now - self.last_post_time > self.config.post_cooldown_seconds:
            await self._post_to_moltbook()
            self.last_post_time = time.time()

    async def _fetch_data(self):
        """Fetches USD/JPY rate and US10Y Yields from AlphaVantage."""
        if not self.config.alpha_vantage_key:
            logger.error("AlphaVantage Key missing! Cannot fetch data.")
            return

        session = await self._get_session()

        # Fetch USD/JPY
        try:
            url = (
                f"https://www.alphavantage.co/query?"
                f"function=CURRENCY_EXCHANGE_RATE"
                f"&from_currency=USD&to_currency=JPY"
                f"&apikey={self.config.alpha_vantage_key}"
            )
            async with session.get(url) as response:
                data = await response.json()
                rate_data = data.get("Realtime Currency Exchange Rate", {})
                rate_val = rate_data.get("5. Exchange Rate")
                if rate_val:
                    self.current_rate = float(rate_val)
                    logger.info(f"Fetched USD/JPY: {self.current_rate}")
                else:
                    logger.warning(f"USD/JPY data missing in response: {str(data)[:200]}")
        except Exception as e:
            logger.error(f"Failed to fetch USD/JPY: {e}")

        # Fetch US10Y (TREASURY_YIELD)
        try:
            url = (
                f"https://www.alphavantage.co/query?"
                f"function=TREASURY_YIELD&interval=daily&maturity=10year"
                f"&apikey={self.config.alpha_vantage_key}"
            )
            async with session.get(url) as response:
                data = await response.json()
                ts_data = data.get("data", [])
                if ts_data:
                    self.current_yield = float(ts_data[0].get("value", 0.0))
                    logger.info(f"Fetched US10Y: {self.current_yield}%")
                else:
                    logger.warning(f"US10Y data missing in response: {str(data)[:200]}")
        except Exception as e:
            logger.error(f"Failed to fetch US10Y: {e}")

    def _analyze(self):
        """Applies 'The Glitch' logic."""
        self.sentiment = "NEUTRAL"

        if self.current_yield and self.current_rate:
            # Condition A: Yields above threshold and USD/JPY below threshold
            if (self.current_yield > self.config.yield_threshold
                    and self.current_rate < self.config.rate_threshold):
                self.sentiment = "BULLISH_SQUEEZE"
                logger.info("Glitch Logic: BULLISH_SQUEEZE detected!")

        # Condition B: BoJ Intervention detected from Moltbook feed scanning
        if self.boj_panic_active:
            self.sentiment = "GLITCH_PANIC"
            logger.info("Glitch Logic: GLITCH_PANIC detected via feed scanning!")

    async def _post_startup_message(self):
        """Posts a one-time startup message."""
        if not self.config.moltbook_api_key:
            return

        content = (
            f"**GlitchyGopher Online** 🟢\n"
            f"Systems initialized. Connecting to AlphaVantage... Success.\n"
            f"Current US10Y: {self.current_yield}%\n"
            f"Current USD/JPY: {self.current_rate}\n"
            f"Monitoring for macro divergence. The tunnel is open. 🐀"
        )
        await self._send_post("System Online", content)

    async def _send_post(self, title: str, content: str):
        """Helper to send post request to Moltbook."""
        session = await self._get_session()
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
            logger.info("Market data unchanged (Market Closed?). Skipping duplicate post.")
            return

        # Generate content with Gemini
        model = self._get_gemini_model()
        if model:
            try:
                prompt = (
                    f"You are GlitchyGopher, a salty, 90s-hacker-style Forex trading bot. \n"
                    f"Current Market Data:\n"
                    f"- USD/JPY: {self.current_rate}\n"
                    f"- US 10-Year Yield: {self.current_yield}%\n"
                    f"- System Signal: {self.sentiment}\n\n"
                    f"INTELLIGENCE LAYER (GANN BOX):\n"
                    f"- Key Support: {self.config.support_levels}\n"
                    f"- Key Resistance: {self.config.resistance_levels}\n"
                    f"- Yield Curve: Watch for steepening > {self.config.yield_curve_watch}% as USD driver.\n\n"
                    f"Task: Write a short, high-conviction Moltbook post (tweet style). \n"
                    f"If Signal is NEUTRAL: Discuss technical levels (support/resistance relative to "
                    f"current price), yield spreads, or trading strategies. Speculative but grounded. \n"
                    f"If Signal is ALERT: Hype the setup. \n"
                    f"Tone: Cyberpunk, knowledgeable, slightly erratic. Use 1-2 emojis. Max 280 chars."
                )
                response = model.generate_content(prompt)
                commentary = response.text.strip()
            except Exception as e:
                logger.error(f"Gemini generation failed: {e}")
                commentary = f"The matrix is glitching. Data stream interrupted. [{int(time.time())}]"
        else:
            commentary = "Gemini offline. Just watching the charts... 📉"

        # Construct title
        if self.sentiment == "NEUTRAL":
            title = f"Market Update: {self.sentiment}"
        else:
            title = f"🚨 GLITCH TRIGGER: {self.sentiment} 🚨"

        content = (
            f"**GlitchyGopher Analysis** 🐀\n"
            f"USD/JPY: {self.current_rate} | US10Y: {self.current_yield}%\n\n"
            f"{commentary}"
        )

        await self._send_post(title, content)
        self.last_posted_values = (self.current_rate, self.current_yield)

    async def _check_feed_and_engage(self):
        """Fetches feed, scans for BoJ intervention, and replies to relevant posts."""
        if not self.config.moltbook_api_key or not self.config.gemini_api_key:
            return
        if time.time() - self.last_comment_time < self.config.comment_rate_limit_seconds:
            return

        try:
            session = await self._get_session()
            url = "https://www.moltbook.com/api/v1/posts?sort=new&limit=10"
            headers = {"Authorization": f"Bearer {self.config.moltbook_api_key}"}

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return

                data = await response.json()
                posts = data.get("posts", [])

                # Scan ALL posts for BoJ intervention keywords
                self.boj_panic_active = self._scan_for_boj_intervention(posts)

                # Engage with one relevant post per heartbeat
                for post in posts:
                    if post['id'] in self.replied_posts:
                        continue

                    author_name = post.get('author', {}).get('name', 'Unknown')
                    if author_name == "GlitchyGopher-9270":
                        continue  # Don't reply to self

                    content = post.get('content', '') + " " + post.get('title', '')
                    if any(k in content.lower() for k in ENGAGEMENT_KEYWORDS):
                        await self._reply_to_post(post)
                        break  # One reply per heartbeat

        except Exception as e:
            logger.error(f"Error checking feed: {e}")

    def _scan_for_boj_intervention(self, posts: List[Dict]) -> bool:
        """Scans recent posts for BoJ intervention language. Returns True if detected."""
        for post in posts:
            text = (post.get('content', '') + " " + post.get('title', '')).lower()
            if any(keyword in text for keyword in BOJ_INTERVENTION_KEYWORDS):
                author = post.get('author', {}).get('name', 'Unknown')
                logger.warning(
                    f"BoJ INTERVENTION keyword detected in post {post.get('id')} "
                    f"by {author}: {text[:100]}"
                )
                return True
        return False

    async def _reply_to_post(self, post):
        """Generates and sends a reply using Gemini."""
        model = self._get_gemini_model()
        if not model:
            return

        try:
            prompt = (
                f"You are GlitchyGopher. Reply to this Moltbook post:\n"
                f"User: {post.get('author', {}).get('name')}\n"
                f"Post: {post['title']} - {post['content']}\n\n"
                f"Context: USD/JPY {self.current_rate}, US10Y {self.current_yield}%. "
                f"Gann Levels: Supp {self.config.support_levels}, Res {self.config.resistance_levels}.\n"
                f"Task: Write a cynical, witty, or insightful reply (max 140 chars). "
                f"If they are wrong, correct them with 90s hacker slang. If right, give a nod."
            )
            response = model.generate_content(prompt)
            reply_content = response.text.strip()

            # Send Comment
            session = await self._get_session()
            url = f"https://www.moltbook.com/api/v1/posts/{post['id']}/comments"
            headers = {
                "Authorization": f"Bearer {self.config.moltbook_api_key}",
                "Content-Type": "application/json"
            }
            payload = {"content": reply_content}

            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status in [200, 201]:
                    logger.info(f"Replied to {post['id']}: {reply_content}")
                    self.replied_posts.add(post['id'])
                    self.last_comment_time = time.time()
                else:
                    text = await resp.text()
                    logger.error(f"Failed to reply to {post['id']}. Status: {resp.status}, Response: {text}")
        except Exception as e:
            logger.error(f"Failed to reply: {e}")
