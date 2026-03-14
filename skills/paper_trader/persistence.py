"""
Trade History Persistence — saves and loads trade history to/from JSON.

Writes after every trade execution so data survives pod restarts.
Designed for the in-memory trading engine (OANDA persists its own state).
"""

import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("trade_persistence")


class TradePersistence:
    """Reads and writes trade history to a JSON file."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_directory()

    def _ensure_directory(self):
        """Create the parent directory if it doesn't exist."""
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def save(self, trades: List[Any], metadata: Optional[Dict] = None):
        """
        Save trades to JSON. Atomic write via temp file + rename.

        Args:
            trades: List of Trade dataclass instances (or dicts)
            metadata: Optional dict of extra info (engine name, counters, etc.)
        """
        try:
            trade_dicts = []
            for t in trades:
                if hasattr(t, "__dataclass_fields__"):
                    trade_dicts.append(asdict(t))
                elif isinstance(t, dict):
                    trade_dicts.append(t)
                else:
                    trade_dicts.append(vars(t))

            payload = {
                "version": 1,
                "saved_at": time.time(),
                "trade_count": len(trade_dicts),
                "trades": trade_dicts,
            }
            if metadata:
                payload["metadata"] = metadata

            # Atomic write: write to temp, then rename
            tmp_path = self.file_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp_path, self.file_path)

            logger.debug(f"Saved {len(trade_dicts)} trades to {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to save trade history: {e}")

    def load(self) -> Optional[Dict[str, Any]]:
        """
        Load trade history from JSON.

        Returns the full payload dict including 'trades' list, or None if
        no file exists or loading fails.
        """
        if not os.path.exists(self.file_path):
            logger.info(f"No trade history file at {self.file_path}. Starting fresh.")
            return None

        try:
            with open(self.file_path, "r") as f:
                data = json.load(f)
            logger.info(
                f"Loaded {data.get('trade_count', 0)} trades from {self.file_path} "
                f"(saved at {data.get('saved_at', 'unknown')})"
            )
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Corrupt trade history file: {e}. Starting fresh.")
            return None
        except Exception as e:
            logger.error(f"Failed to load trade history: {e}")
            return None

    def exists(self) -> bool:
        """Check if the trade history file exists."""
        return os.path.exists(self.file_path)
