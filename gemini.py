# gemini.py
from dotenv import load_dotenv
import os
import logging
from datetime import date
from google import genai

load_dotenv()
logger = logging.getLogger("gemini")
# ---------- Config ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# Ordered by preference
MODELS = [
    {
        "name": "models/gemini-2.5-flash",
        "daily_limit": 20,
    },
    {
        "name": "models/gemini-3-flash",
        "daily_limit": 20,
    },
    {
        "name": "models/gemini-2.5-flash-lite",
        "daily_limit": 10,
    },
]

SAFETY_MARGIN = 1  # stop before hard limit

# ---------- State (in-memory) ----------
_today = date.today()
_usage = {m["name"]: 0 for m in MODELS}


# ---------- Helpers ----------
def _reset_if_needed():
    global _today, _usage
    today = date.today()
    if today != _today:
        _today = today
        _usage = {m["name"]: 0 for m in MODELS}
        logger.info("🔄 Gemini daily quota reset")


def _can_use(model_name: str, limit: int) -> bool:
    return _usage.get(model_name, 0) < (limit - SAFETY_MARGIN)


def _record_use(model_name: str):
    _usage[model_name] += 1


# ---------- Public API ----------
def best_available_model() -> str | None:
    """
    Returns the next model name that still has quota,
    or None if all exhausted.
    """
    _reset_if_needed()
    for m in MODELS:
        if _can_use(m["name"], m["daily_limit"]):
            return m["name"]
    return None


def remaining_total_quota() -> int:
    """
    Total remaining quota across all models.
    """
    _reset_if_needed()
    total = 0
    for m in MODELS:
        used = _usage[m["name"]]
        limit = m["daily_limit"]
        remaining = max(limit - SAFETY_MARGIN - used, 0)
        total += remaining
    return total


def has_any_quota() -> bool:
    """
    Whether any model still has usable quota.
    """
    return remaining_total_quota() > 0


def quota_status() -> dict:
    """
    Returns per-model quota status
    """
    _reset_if_needed()
    return {
        m["name"]: {
            "used": _usage[m["name"]],
            "limit": m["daily_limit"],
            "remaining": max(m["daily_limit"] - _usage[m["name"]], 0),
        }
        for m in MODELS
    }


def ask(text: str) -> str:
    """
    Ask Gemini sequentially:
    Try model A, then B, then C.
    """
    _reset_if_needed()

    last_error = None

    for m in MODELS:
        model_name = m["name"]
        model_limit = m["daily_limit"]

        if not _can_use(model_name, model_limit):
            logger.warning("⛔ Model exhausted: %s", model_name)
            continue

        logger.info("🧠 Using Gemini model: %s", model_name)

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=text,
                config={
                    "temperature": 0.6,
                    "maxOutputTokens": 2048,
                },
            )
            _record_use(model_name)
            return response.text.strip()

        except Exception as e:
            logger.exception("❌ Gemini error on model %s", model_name)
            last_error = e
            # Try next model

    # All models exhausted or failed
    raise RuntimeError("All Gemini models quota exhausted for today") from last_error
