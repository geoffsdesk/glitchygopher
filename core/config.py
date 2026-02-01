import os
import logging
from dataclasses import dataclass

@dataclass
class Config:
    gemini_api_key: str
    alpha_vantage_key: str
    moltbook_api_key: str

    @classmethod
    def load(cls) -> "Config":
        """Loads configuration from environment variables."""
        gemini_key = os.getenv("GEMINI_API_KEY")
        alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY")
        moltbook_api_key = os.getenv("MOLTBOOK_API_KEY")

        if not gemini_key:
            logging.warning("GEMINI_API_KEY is not set.")
        if not alpha_vantage_key:
            logging.warning("ALPHA_VANTAGE_KEY is not set.")
        if not moltbook_api_key:
            logging.warning("MOLTBOOK_API_KEY is not set.")

        return cls(
            gemini_api_key=gemini_key or "",
            alpha_vantage_key=alpha_vantage_key or "",
            moltbook_api_key=moltbook_api_key or ""
        )
