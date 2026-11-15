"""Settings and logging for PawPal AI."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MODEL = "openai/gpt-oss-20b"
LOG_FILE = Path(os.getenv("PAWPAL_LOG_FILE", ROOT / "logs" / "pawpal_ai.log"))


def groq_model() -> str:
    """Model id to call on Groq (override with GROQ_MODEL)."""
    return os.getenv("GROQ_MODEL", DEFAULT_MODEL)


def groq_agent_model() -> str:
    """Model for the multi-step agent (override with GROQ_AGENT_MODEL); a larger model plans more reliably."""
    return os.getenv("GROQ_AGENT_MODEL", "openai/gpt-oss-120b")


def groq_api_key() -> str | None:
    """The Groq API key from the environment or .env, if any."""
    return os.getenv("GROQ_API_KEY") or None


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Log every AI step to logs/pawpal_ai.log (idempotent)."""
    logger = logging.getLogger("pawpal_ai")
    if not logger.handlers:
        LOG_FILE.parent.mkdir(exist_ok=True)
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger
