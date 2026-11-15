"""Settings and logging for PawPal AI."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MODEL = "openai/gpt-oss-20b"
LOG_FILE = Path(os.getenv("PAWPAL_LOG_FILE", ROOT / "logs" / "pawpal_ai.log"))


def groq_model() -> str:
    """Model id to call on Groq (override with GROQ_MODEL)."""
    return _secret("GROQ_MODEL") or DEFAULT_MODEL


def groq_agent_model() -> str:
    """Model for the multi-step agent (override with GROQ_AGENT_MODEL); a larger model plans more reliably."""
    return _secret("GROQ_AGENT_MODEL") or "openai/gpt-oss-120b"


def _secret(name: str) -> str | None:
    """Read a value from the environment/.env, then Streamlit secrets (Streamlit Community Cloud)."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(name) or None
    except Exception:  # streamlit not installed, or no secrets.toml configured
        return None


def groq_api_key() -> str | None:
    """The Groq API key from the environment, .env, or Streamlit secrets."""
    key = _secret("GROQ_API_KEY")
    return key.strip() if key else None


def setup_logging(level: int | None = None) -> logging.Logger:
    """Log every AI step to a rotating logs/pawpal_ai.log and to stderr (visible in cloud logs). Idempotent."""
    logger = logging.getLogger("pawpal_ai")
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)
        except OSError:  # read-only filesystem: console logging only
            pass
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.setLevel(logging.WARNING)  # keep cloud logs to problems only
        logger.addHandler(console)
        logger.setLevel(level or getattr(logging, os.getenv("PAWPAL_LOG_LEVEL", "INFO").upper(), logging.INFO))
        logger.propagate = False
    return logger
