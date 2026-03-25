"""Configuration values for the Telegram translator bot."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from languages import ALL_LANGUAGES

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "translator_bot.db"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Bot behavior defaults.
DEFAULT_SOURCE_LANG = "auto"
DEFAULT_TARGET_LANG = "en"
MAX_INPUT_TEXT_LENGTH = 4000
MAX_OUTPUT_TEXT_LENGTH = 3900
TRANSLATION_HISTORY_LIMIT = 10
SAVED_TRANSLATIONS_LIMIT = 20

WELCOME_TEXT = (
    "Your translator is ready.\n\n"
    "Send any text to translate instantly.\n"
    "Use Language Setup if you want to change the default languages."
)

HELP_TEXT = (
    "Quick help\n\n"
    "1. Send a word, sentence, paragraph, or voice note.\n"
    "2. Use From Language or To Language when you want to switch languages.\n"
    "3. Tap Swap Languages to reverse the direction.\n"
    "4. Use Copy Text or Speak Result after each translation.\n\n"
    "Commands:\n"
    "/start - open the quick translator\n"
    "/translate - open translate mode\n"
    "/settings - save your default languages\n"
    "/help - show this help text\n"
    "/cancel - return home\n\n"
    f"Limit: keep text under {MAX_INPUT_TEXT_LENGTH:,} characters."
)

if DEFAULT_TARGET_LANG not in ALL_LANGUAGES:
    raise ValueError("DEFAULT_TARGET_LANG must be present in ALL_LANGUAGES")
