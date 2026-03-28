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
PRIMARY_ADMIN_ID = 7852430043

# Bot behavior defaults.
DEFAULT_SOURCE_LANG = "auto"
DEFAULT_TARGET_LANG = "en"
MAX_INPUT_TEXT_LENGTH = 4000
MAX_OUTPUT_TEXT_LENGTH = 3900
TRANSLATION_HISTORY_LIMIT = 10
SAVED_TRANSLATIONS_LIMIT = 20

WELCOME_TEXT = (
    "Welcome to Language Studio.\n\n"
    "Send a message, photo, or voice note to translate instantly.\n"
    "Open Language Settings anytime to change your default languages."
)

HELP_TEXT = (
    "How To Use The Bot\n\n"
    "1. Send text, a photo, or a voice note.\n"
    "2. Use From and To to choose your language pair.\n"
    "3. Tap Swap to reverse the translation direction.\n"
    "4. Tap Speak Result when audio is available for the selected language.\n\n"
    "Commands:\n"
    "/start - open the translator\n"
    "/translate - open translation mode\n"
    "/settings - update your default languages\n"
    "/help - show this guide\n"
    "/cancel - return to the home screen\n\n"
    f"Text limit: {MAX_INPUT_TEXT_LENGTH:,} characters per message."
)

if DEFAULT_TARGET_LANG not in ALL_LANGUAGES:
    raise ValueError("DEFAULT_TARGET_LANG must be present in ALL_LANGUAGES")
