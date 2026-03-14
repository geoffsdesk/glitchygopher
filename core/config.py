import os
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("config")


@dataclass
class Config:
    # --- API Keys ---
    gemini_api_key: str = ""
    alpha_vantage_key: str = ""
    moltbook_api_key: str = ""

    # --- OANDA Paper Trading ---
    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_environment: str = "practice"  # "practice" or "live"
    paper_trading_enabled: bool = False
    paper_trade_units: int = 1000  # micro lot

    # --- Glitch Logic Thresholds ---
    yield_threshold: float = 4.2       # US10Y yield above this = bullish signal
    rate_threshold: float = 148.0      # USD/JPY below this = bullish signal

    # --- Gann Box Levels (configurable technical levels) ---
    support_levels: str = "152.00, 150.80"
    resistance_levels: str = "155.50, 158.20"
    yield_curve_watch: float = 4.3

    # --- Timing ---
    fetch_interval_seconds: int = 3600     # 60 minutes
    post_cooldown_seconds: int = 1860      # 31 minutes
    comment_rate_limit_seconds: int = 20
    heartbeat_seconds: int = 60

    # --- Trade Summary Posting ---
    trade_summary_enabled: bool = True
    trade_summary_interval_seconds: int = 7200  # 2 hours

    # --- Trade Persistence ---
    trade_persistence_enabled: bool = True
    trade_history_path: str = "/app/data/trade_history.json"

    # --- Health Check ---
    health_check_port: int = 8080

    @classmethod
    def load(cls) -> "Config":
        """Loads configuration from environment variables with sensible defaults."""

        def _env_str(key: str, default: str = "") -> str:
            return os.getenv(key, default)

        def _env_int(key: str, default: int = 0) -> int:
            val = os.getenv(key)
            if val is None:
                return default
            try:
                return int(val)
            except ValueError:
                logger.warning(f"Invalid int for {key}: {val!r}, using default {default}")
                return default

        def _env_float(key: str, default: float = 0.0) -> float:
            val = os.getenv(key)
            if val is None:
                return default
            try:
                return float(val)
            except ValueError:
                logger.warning(f"Invalid float for {key}: {val!r}, using default {default}")
                return default

        def _env_bool(key: str, default: bool = False) -> bool:
            val = os.getenv(key, "").lower()
            if val in ("1", "true", "yes"):
                return True
            if val in ("0", "false", "no"):
                return False
            return default

        # Required API keys
        gemini_key = _env_str("GEMINI_API_KEY")
        alpha_vantage_key = _env_str("ALPHA_VANTAGE_KEY")
        moltbook_api_key = _env_str("MOLTBOOK_API_KEY")

        if not gemini_key:
            logger.warning("GEMINI_API_KEY is not set.")
        if not alpha_vantage_key:
            logger.warning("ALPHA_VANTAGE_KEY is not set.")
        if not moltbook_api_key:
            logger.warning("MOLTBOOK_API_KEY is not set.")

        # OANDA
        oanda_api_key = _env_str("OANDA_API_KEY")
        oanda_account_id = _env_str("OANDA_ACCOUNT_ID")
        oanda_environment = _env_str("OANDA_ENVIRONMENT", "practice")
        paper_trading_enabled = _env_bool("PAPER_TRADING_ENABLED", bool(oanda_api_key))

        if paper_trading_enabled and not oanda_api_key:
            logger.warning("PAPER_TRADING_ENABLED is true but OANDA_API_KEY is not set.")
            paper_trading_enabled = False

        return cls(
            gemini_api_key=gemini_key,
            alpha_vantage_key=alpha_vantage_key,
            moltbook_api_key=moltbook_api_key,
            oanda_api_key=oanda_api_key,
            oanda_account_id=oanda_account_id,
            oanda_environment=oanda_environment,
            paper_trading_enabled=paper_trading_enabled,
            paper_trade_units=_env_int("PAPER_TRADE_UNITS", 1000),
            yield_threshold=_env_float("YIELD_THRESHOLD", 4.2),
            rate_threshold=_env_float("RATE_THRESHOLD", 148.0),
            support_levels=_env_str("SUPPORT_LEVELS", "152.00, 150.80"),
            resistance_levels=_env_str("RESISTANCE_LEVELS", "155.50, 158.20"),
            yield_curve_watch=_env_float("YIELD_CURVE_WATCH", 4.3),
            fetch_interval_seconds=_env_int("FETCH_INTERVAL_SECONDS", 3600),
            post_cooldown_seconds=_env_int("POST_COOLDOWN_SECONDS", 1860),
            comment_rate_limit_seconds=_env_int("COMMENT_RATE_LIMIT_SECONDS", 20),
            heartbeat_seconds=_env_int("HEARTBEAT_SECONDS", 60),
            health_check_port=_env_int("HEALTH_CHECK_PORT", 8080),
            trade_summary_enabled=_env_bool("TRADE_SUMMARY_ENABLED", True),
            trade_summary_interval_seconds=_env_int("TRADE_SUMMARY_INTERVAL_SECONDS", 7200),
            trade_persistence_enabled=_env_bool("TRADE_PERSISTENCE_ENABLED", True),
            trade_history_path=_env_str("TRADE_HISTORY_PATH", "/app/data/trade_history.json"),
        )
