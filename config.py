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
    "Professional translation, ready whenever you are.\n\n"
    "Send a message and the bot will translate it right away.\n"
    "Open Preferences if you want to change your default languages."
)

HELP_TEXT = (
    "How to use the translator\n\n"
    "1. Send a word, sentence, paragraph, photo, or voice note.\n"
    "2. Use From or To to change the language pair.\n"
    "3. Tap Swap to reverse the translation direction.\n"
    "4. Tap Speak Result when audio is available for the selected target language.\n\n"
    "Commands:\n"
    "/start - open the translator\n"
    "/translate - open translation mode\n"
    "/settings - update your default languages\n"
    "/help - show this guide\n"
    "/cancel - return to the main menu\n\n"
    f"Text limit: keep each message under {MAX_INPUT_TEXT_LENGTH:,} characters."
)

if DEFAULT_TARGET_LANG not in ALL_LANGUAGES:
    raise ValueError("DEFAULT_TARGET_LANG must be present in ALL_LANGUAGES")
