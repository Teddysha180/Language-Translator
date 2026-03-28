"""Keyboard builders for the translator bot."""

from __future__ import annotations

from typing import Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from languages import compact_language_name

MENU_TRANSLATE = "Open Studio"
MENU_SETTINGS = "Tune Languages"
MENU_HELP = "Quick Guide"

TR_PICK_SOURCE = "◂ Source"
TR_PICK_TARGET = "Target ▸"
TR_SWAP = "⇆ Flip Pair"
TR_BACK_MENU = "⌂ Studio"
TR_AGAIN = "New Translation"

SET_PICK_SOURCE = "◂ Default Source"
SET_PICK_TARGET = "Default Target ▸"
SET_BACK_MENU = "⌂ Studio"

LANGUAGE_MENU_BACK = "Back"

CB_TRANSLATE_TTS = "tr:tts"
CB_ONBOARD_START = "ob:start"
CB_ONBOARD_SETTINGS = "ob:settings"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(MENU_TRANSLATE)],
        [KeyboardButton(MENU_SETTINGS), KeyboardButton(MENU_HELP)],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=False)


def translation_panel_keyboard(
    source_lang: str,
    target_lang: str,
    source_name: str = "",
    target_name: str = "",
) -> ReplyKeyboardMarkup:
    _ = (source_lang, target_lang, source_name, target_name)
    keyboard = [
        [KeyboardButton(TR_PICK_SOURCE), KeyboardButton(TR_PICK_TARGET)],
        [KeyboardButton(TR_SWAP), KeyboardButton(TR_BACK_MENU)],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=False)


def translation_result_inline_keyboard(include_tts: bool = True) -> InlineKeyboardMarkup:
    keyboard = []
    if include_tts:
        keyboard.append([InlineKeyboardButton("🔊 Speak", callback_data=CB_TRANSLATE_TTS)])
    return InlineKeyboardMarkup(keyboard)


def settings_keyboard(
    source_lang: str,
    target_lang: str,
    source_name: str = "",
    target_name: str = "",
) -> ReplyKeyboardMarkup:
    _ = (source_lang, target_lang, source_name, target_name)
    keyboard = [
        [KeyboardButton(SET_PICK_SOURCE), KeyboardButton(SET_PICK_TARGET)],
        [KeyboardButton(SET_BACK_MENU)],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=False)


def onboarding_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Start Translating", callback_data=CB_ONBOARD_START)],
        [InlineKeyboardButton("Pick My Default Language", callback_data=CB_ONBOARD_SETTINGS)],
    ]
    return InlineKeyboardMarkup(keyboard)


def language_menu_label(code: str, name: str) -> str:
    _ = name
    return compact_language_name(code)


def language_menu_keyboard(
    languages: Dict[str, str],
    include_auto: bool = False,
    per_row: int = 1,
) -> ReplyKeyboardMarkup:
    items = [(code, name) for code, name in languages.items() if include_auto or code != "auto"]
    keyboard = []
    row = []
    for code, name in items:
        row.append(KeyboardButton(language_menu_label(code, name)))
        if len(row) == per_row:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([KeyboardButton(LANGUAGE_MENU_BACK)])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True,
    )
