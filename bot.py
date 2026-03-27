"""Telegram translator bot with guided onboarding, inline actions, and audio features."""

from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import os
import re
import tempfile
import threading
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from deep_translator import GoogleTranslator
from deep_translator.exceptions import NotValidLength, RequestError, TooManyRequests
from telegram import InputFile, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

from config import (
    BOT_TOKEN,
    DB_PATH,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    HELP_TEXT,
    LOG_LEVEL,
    MAX_INPUT_TEXT_LENGTH,
    WELCOME_TEXT,
)
from database import Database
from keyboards import (
    CB_ONBOARD_SETTINGS,
    CB_ONBOARD_START,
    CB_TRANSLATE_TTS,
    LANGUAGE_MENU_BACK,
    MENU_HELP,
    MENU_SETTINGS,
    MENU_TRANSLATE,
    MENU_TRAVEL,
    SET_BACK_MENU,
    SET_PICK_SOURCE,
    SET_PICK_TARGET,
    TR_AGAIN,
    TR_BACK_MENU,
    TR_HELP,
    TR_PICK_SOURCE,
    TR_PICK_TARGET,
    TR_SWAP,
    TR_TRAVEL,
    TRAVEL_BACK,
    language_menu_keyboard,
    language_menu_label,
    main_menu_keyboard,
    onboarding_keyboard,
    settings_keyboard,
    travel_categories_keyboard,
    translation_panel_keyboard,
    translation_result_inline_keyboard,
)
from languages import ALL_LANGUAGES, TRANSLATOR_CODE_ALIASES, display_language_name
from travel_phrases import TRAVEL_CATEGORIES, TRAVEL_PHRASES

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

TRANSLATE_STATE = 1
SETTINGS_STATE = 2
TRAVEL_STATE = 3

db = Database(DB_PATH)

FORCED_UNSUPPORTED_TARGET_LANGS = {"aa", "ss", "wal", "sid", "gez", "har", "gur", "kun", "byn", "aho"}
ALWAYS_ALLOW_TARGET_LANGS = {"ti"}
INVISIBLE_TEXT_RE = re.compile(r"[\s\u200b\u200c\u200d\u200e\u200f\u2060\ufeff]+")

SPEECH_LANGUAGE_HINTS = {
    "en": "en-US",
    "fr": "fr-FR",
    "es": "es-ES",
    "de": "de-DE",
    "it": "it-IT",
    "pt": "pt-PT",
    "ru": "ru-RU",
    "ar": "ar-SA",
    "hi": "hi-IN",
    "tr": "tr-TR",
    "sw": "sw-KE",
    "am": "am-ET",
}

TTS_FALLBACK_CODES = {
    "am",
    "ar",
    "de",
    "en",
    "es",
    "fr",
    "hi",
    "it",
    "pt",
    "ru",
    "so",
    "sw",
    "tr",
    "zh-CN",
    "zh-TW",
}


class HealthHandler(BaseHTTPRequestHandler):
    """Tiny health endpoint for Render/UptimeRobot."""

    def _write_status(self, code: int, body: bytes, include_body: bool = True) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _is_health_path(self) -> bool:
        return self.path in {"/", "/health", "/health/"}

    def do_GET(self) -> None:  # noqa: N802
        if self._is_health_path():
            self._write_status(200, b"ok")
            return

        self._write_status(404, b"not found")

    def do_HEAD(self) -> None:  # noqa: N802
        if self._is_health_path():
            self._write_status(200, b"ok", include_body=False)
            return
        self._write_status(404, b"not found", include_body=False)

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("Health server: " + format, *args)


@lru_cache(maxsize=1)
def get_translator_supported_codes() -> set[str]:
    """Fetch language codes supported by deep-translator at runtime."""
    try:
        supported = GoogleTranslator().get_supported_languages(as_dict=True)
        return set(supported.values())
    except Exception as exc:  # pragma: no cover - network variability
        logger.warning("Could not fetch supported codes: %s", exc)
        return set()


def resolve_translator_code(code: str) -> Optional[str]:
    """Map app language codes to translator backend codes."""
    if code == "auto":
        return "auto"
    aliases = TRANSLATOR_CODE_ALIASES.get(code, [code])
    supported = get_translator_supported_codes()
    if not supported:
        return aliases[0]
    for candidate in aliases:
        if candidate in supported:
            return candidate
    return None


def lang_name(code: str) -> str:
    return ALL_LANGUAGES.get(code, code)


def ui_lang_name(code: str) -> str:
    return display_language_name(code)


def is_effectively_empty_text(text: str) -> bool:
    if text is None:
        return True
    return INVISIBLE_TEXT_RE.sub("", text) == ""


def is_supported_source_lang(code: str) -> bool:
    return code == "auto" or resolve_translator_code(code) is not None


def is_supported_target_lang(code: str) -> bool:
    if code in FORCED_UNSUPPORTED_TARGET_LANGS:
        return False
    if code in ALWAYS_ALLOW_TARGET_LANGS:
        return True
    return code != "auto" and resolve_translator_code(code) is not None


def selectable_languages(include_auto: bool, for_target: bool = False) -> Dict[str, str]:
    filtered: Dict[str, str] = {}
    for code, name in ALL_LANGUAGES.items():
        if code == "auto":
            if include_auto and not for_target:
                filtered[code] = name
            continue
        if for_target:
            if is_supported_target_lang(code):
                filtered[code] = name
        else:
            if is_supported_source_lang(code):
                filtered[code] = name
    return filtered


def parse_language_menu_choice(choice: str, include_auto: bool) -> Optional[str]:
    raw = (choice or "").strip()
    if not raw:
        return None
    lowered = raw.casefold()
    for code, name in ALL_LANGUAGES.items():
        if code == "auto" and not include_auto:
            continue
        if lowered in {code.casefold(), name.casefold(), language_menu_label(code, name).casefold()}:
            return code
    return None


def get_user_langs(user_id: int) -> Tuple[str, str]:
    prefs = db.get_user_preferences(user_id)
    source = prefs.get("preferred_source_lang") or DEFAULT_SOURCE_LANG
    target = prefs.get("preferred_target_lang") or DEFAULT_TARGET_LANG
    if source not in ALL_LANGUAGES or not is_supported_source_lang(source):
        source = DEFAULT_SOURCE_LANG
    if target not in ALL_LANGUAGES or not is_supported_target_lang(target):
        target = DEFAULT_TARGET_LANG
    return source, target


def ensure_user_data_langs(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Tuple[str, str]:
    source, target = get_user_langs(user_id)
    context.user_data.setdefault("source_lang", source)
    context.user_data.setdefault("target_lang", target)
    if not is_supported_source_lang(context.user_data["source_lang"]):
        context.user_data["source_lang"] = DEFAULT_SOURCE_LANG
    if not is_supported_target_lang(context.user_data["target_lang"]):
        context.user_data["target_lang"] = DEFAULT_TARGET_LANG
    return context.user_data["source_lang"], context.user_data["target_lang"]


def detect_language_code(text: str) -> Optional[str]:
    """Detect the language code using Google's lightweight endpoint."""
    params = urlencode({"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text})
    with urlopen(f"https://translate.googleapis.com/translate_a/single?{params}", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if len(payload) < 3:
        return None
    detected = payload[2]
    return detected if detected in ALL_LANGUAGES else None


def speech_hint_for_language(source_lang: str) -> str:
    if source_lang == "auto":
        return "en-US"
    aliases = TRANSLATOR_CODE_ALIASES.get(source_lang, [source_lang])
    for alias in [source_lang, *aliases]:
        if alias in SPEECH_LANGUAGE_HINTS:
            return SPEECH_LANGUAGE_HINTS[alias]
    return "en-US"


@lru_cache(maxsize=1)
def get_tts_supported_codes() -> set[str]:
    try:
        from gtts.lang import tts_langs
    except ImportError:
        return set(TTS_FALLBACK_CODES)
    return set(tts_langs().keys()) | set(TTS_FALLBACK_CODES)


def resolve_tts_code(code: str) -> Optional[str]:
    if code == "auto":
        return None
    aliases = [code, *TRANSLATOR_CODE_ALIASES.get(code, [])]
    supported = get_tts_supported_codes()
    if not supported:
        return None
    for candidate in aliases:
        if candidate in supported:
            return candidate
    return None


async def register_user(update: Update) -> None:
    user = update.effective_user
    if not user:
        return
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)


async def send_markdown(
    update: Update,
    text: str,
    reply_markup: Optional[object] = None,
    parse_mode: str = ParseMode.MARKDOWN,
) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )


async def animate_start_intro(update: Update) -> None:
    message = update.effective_message
    if not message:
        return
    frames = [
        "Starting your translator",
        "Starting your translator.",
        "Starting your translator..",
        "Starting your translator...",
        "*Translator ready*",
    ]
    sent = await message.reply_text(frames[0], parse_mode=ParseMode.MARKDOWN)
    for frame in frames[1:]:
        await asyncio.sleep(0.35)
        try:
            await sent.edit_text(frame, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            break


async def show_onboarding_if_needed(update: Update, user_id: int) -> None:
    if db.is_onboarding_completed(user_id):
        return
    if update.effective_message:
        await update.effective_message.reply_text(
            (
                "Welcome to your translation workspace.\n\n"
                "1. Send text or a voice note at any time.\n"
                "2. Change From or To whenever you need a new language pair.\n"
                "3. Use Speak Result when voice playback is supported."
            ),
            reply_markup=onboarding_keyboard(),
        )
    db.set_onboarding_completed(user_id, True)


async def show_translate_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    source, target = ensure_user_data_langs(context, user_id)
    src_name = escape_markdown(ui_lang_name(source), version=1)
    tgt_name = escape_markdown(ui_lang_name(target), version=1)
    await send_markdown(
        update,
        (
            "*Translation Studio*\n\n"
            f"*From:* {src_name}\n"
            f"*To:* {tgt_name}\n\n"
            "Send any text now and the bot will translate it immediately."
        ),
        reply_markup=translation_panel_keyboard(source, target),
    )
    return TRANSLATE_STATE


async def show_settings_overview(update: Update, user_id: int) -> int:
    source, target = get_user_langs(user_id)
    await send_markdown(
        update,
        (
            "*Preferences*\n\n"
            f"*Default from:* {escape_markdown(ui_lang_name(source), version=1)}\n"
            f"*Default to:* {escape_markdown(ui_lang_name(target), version=1)}"
        ),
        settings_keyboard(source, target),
    )
    return SETTINGS_STATE


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    context.user_data.pop("lang_menu_mode", None)
    await animate_start_intro(update)
    await show_onboarding_if_needed(update, update.effective_user.id)
    return await show_translate_prompt(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    await send_markdown(update, HELP_TEXT, main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    context.user_data.pop("lang_menu_mode", None)
    await send_markdown(update, WELCOME_TEXT, main_menu_keyboard())
    return ConversationHandler.END


async def main_menu_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    await register_user(update)
    text = (update.effective_message.text or "").strip()
    if text == MENU_TRANSLATE:
        return await translate_entry(update, context)
    if text == MENU_TRAVEL:
        return await travel_entry(update, context)
    if text == MENU_SETTINGS:
        return await settings_entry(update, context)
    if text == MENU_HELP:
        await help_command(update, context)
        return None
    if text:
        await run_translation_flow(update, context, text)
    return None


async def translate_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    context.user_data.pop("lang_menu_mode", None)
    return await show_translate_prompt(update, context)


async def settings_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    context.user_data.pop("lang_menu_mode", None)
    user_id = update.effective_user.id
    source, target = ensure_user_data_langs(context, user_id)
    db.update_user_preferences(user_id, source_lang=source, target_lang=target)
    return await show_settings_overview(update, user_id)


async def show_travel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    _, target = ensure_user_data_langs(context, user_id)
    await send_markdown(
        update,
        (
            "*Travel Mode*\n\n"
            f"*Target language:* {escape_markdown(ui_lang_name(target), version=1)}\n\n"
            "Choose a category and the bot will send a ready-to-use phrase pack."
        ),
        travel_categories_keyboard(TRAVEL_CATEGORIES),
    )
    return TRAVEL_STATE


async def travel_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    context.user_data.pop("lang_menu_mode", None)
    return await show_travel_prompt(update, context)


async def translate_travel_phrases(target_lang: str, category_key: str) -> list[tuple[str, str]]:
    phrases = TRAVEL_PHRASES[category_key]
    translated_rows: list[tuple[str, str]] = []
    for phrase in phrases:
        if target_lang == "en":
            translated_rows.append((phrase, phrase))
            continue
        translated, _ = await perform_translation(phrase, "en", target_lang)
        translated_rows.append((phrase, translated or phrase))
    return translated_rows


async def travel_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    text = (update.effective_message.text or "").strip()
    if text == TRAVEL_BACK:
        await send_markdown(update, WELCOME_TEXT, main_menu_keyboard())
        return ConversationHandler.END

    selected_key = None
    for key, label in TRAVEL_CATEGORIES.items():
        if text == label:
            selected_key = key
            break

    if not selected_key:
        await send_markdown(
            update,
            "Choose one of the travel categories from the menu.",
            travel_categories_keyboard(TRAVEL_CATEGORIES),
        )
        return TRAVEL_STATE

    _, target_lang = ensure_user_data_langs(context, update.effective_user.id)
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        rows = await translate_travel_phrases(target_lang, selected_key)
    except Exception as exc:  # pragma: no cover
        logger.exception("Travel mode translation failed: %s", exc)
        await send_markdown(update, "Travel phrases are unavailable right now. Please try again.")
        return TRAVEL_STATE

    lines = [
        "*Travel Phrases*",
        "",
        f"*Category:* {escape_markdown(TRAVEL_CATEGORIES[selected_key], version=1)}",
        f"*Language:* {escape_markdown(ui_lang_name(target_lang), version=1)}",
        "",
    ]
    for index, (source_phrase, translated_phrase) in enumerate(rows, start=1):
        lines.append(f"*{index}. {escape_markdown(source_phrase, version=1)}*")
        lines.append(escape_markdown(translated_phrase, version=1))
        lines.append("")

    await send_markdown(update, "\n".join(lines).strip(), travel_categories_keyboard(TRAVEL_CATEGORIES))
    return TRAVEL_STATE


async def perform_translation(text: str, source_lang: str, target_lang: str) -> Tuple[str, Optional[str]]:
    detected_code: Optional[str] = None
    if source_lang == "auto":
        try:
            detected_code = await asyncio.to_thread(detect_language_code, text)
        except Exception as exc:  # pragma: no cover - network variability
            logger.warning("Language detection failed: %s", exc)
    src = resolve_translator_code(source_lang)
    tgt = resolve_translator_code(target_lang)
    if not src:
        raise ValueError(f"Source language '{source_lang}' is not supported.")
    if not tgt:
        raise ValueError(f"Target language '{target_lang}' is not supported.")
    translated = await asyncio.to_thread(GoogleTranslator(source=src, target=tgt).translate, text)
    return translated, detected_code


async def build_tts_audio_bytes(text: str, target_lang: str) -> io.BytesIO:
    speech_lang = resolve_tts_code(target_lang)
    if not speech_lang:
        raise RuntimeError(f"Speak Result is not available for {lang_name(target_lang)} yet.")

    def _synthesize() -> io.BytesIO:
        params = urlencode(
            {
                "ie": "UTF-8",
                "client": "tw-ob",
                "tl": speech_lang,
                "q": text[:800],
            }
        )
        request = Request(
            f"https://translate.google.com/translate_tts?{params}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urlopen(request, timeout=20) as response:
            audio_content = response.read()
        buffer = io.BytesIO(audio_content)
        buffer.seek(0)
        return buffer

    return await asyncio.to_thread(_synthesize)


async def transcribe_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE, source_lang: str) -> str:
    voice = update.effective_message.voice
    if not voice:
        raise RuntimeError("No voice message found.")

    try:
        import speech_recognition as sr
        from pydub import AudioSegment
    except ImportError as exc:
        raise RuntimeError("Voice translation packages are not installed.") from exc

    telegram_file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as ogg_file:
        ogg_path = ogg_file.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wav_file:
        wav_path = wav_file.name

    try:
        await telegram_file.download_to_drive(custom_path=ogg_path)

        def _convert_and_transcribe() -> str:
            AudioSegment.from_file(ogg_path).export(wav_path, format="wav")
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as audio_file:
                audio_data = recognizer.record(audio_file)
            return recognizer.recognize_google(audio_data, language=speech_hint_for_language(source_lang))

        return await asyncio.to_thread(_convert_and_transcribe)
    except FileNotFoundError as exc:
        raise RuntimeError("Voice translation needs ffmpeg installed on the server.") from exc
    finally:
        for path in (ogg_path, wav_path):
            try:
                os.remove(path)
            except OSError:
                pass


def store_last_translation(
    context: ContextTypes.DEFAULT_TYPE,
    source_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str,
    detected_lang: Optional[str],
) -> None:
    context.user_data["last_translation"] = {
        "source_text": source_text,
        "translated_text": translated_text,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "detected_lang": detected_lang,
    }


async def send_translation_result(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    translated: str,
    source_lang: str,
    target_lang: str,
    detected_lang: Optional[str],
) -> int:
    store_last_translation(context, text, translated, source_lang, target_lang, detected_lang)
    db.add_translation_history(update.effective_user.id, text, translated, source_lang, target_lang)

    detected_line = ""
    if source_lang == "auto" and detected_lang:
        detected_line = f"<b>Detected:</b> {html.escape(ui_lang_name(detected_lang))}\n"

    result_text = (
        "<b>Translation Ready</b>\n\n"
        f"{detected_line}"
        f"<b>From:</b> {html.escape(ui_lang_name(source_lang))}\n"
        f"<b>To:</b> {html.escape(ui_lang_name(target_lang))}\n\n"
        "<b>Original text</b>\n"
        f"<code>{html.escape(text[:700])}</code>\n\n"
        "<b>Translated text</b>\n"
        f"<code>{html.escape(translated[:700])}</code>"
    )
    result_actions = translation_result_inline_keyboard()
    try:
        await send_markdown(update, result_text, result_actions, parse_mode=ParseMode.HTML)
    except BadRequest:
        await update.effective_message.reply_text(
            f"From: {lang_name(source_lang)}\nTo: {lang_name(target_lang)}\n\nOriginal:\n{text}\n\nTranslated:\n{translated}",
            reply_markup=result_actions,
        )
    return TRANSLATE_STATE


async def run_translation_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    source_lang, target_lang = ensure_user_data_langs(context, update.effective_user.id)

    if not text:
        await send_markdown(update, "Send some text and I will translate it.")
        return TRANSLATE_STATE
    if len(text) > MAX_INPUT_TEXT_LENGTH:
        await send_markdown(update, f"That message is too long. Keep it under {MAX_INPUT_TEXT_LENGTH:,} characters.")
        return TRANSLATE_STATE

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        translated, detected_lang = await perform_translation(text, source_lang, target_lang)
    except ValueError as exc:
        await send_markdown(update, f"Language error: {escape_markdown(str(exc), version=1)}")
        return TRANSLATE_STATE
    except (NotValidLength, TooManyRequests, RequestError):
        await send_markdown(update, "Translation service is busy. Please try again in a moment.")
        return TRANSLATE_STATE
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected translation failure: %s", exc)
        await send_markdown(update, "Something went wrong. Please try again.")
        return TRANSLATE_STATE

    translated = translated or ""
    if is_effectively_empty_text(translated):
        await send_markdown(update, "No result came back for that language pair. Try another target language.")
        return TRANSLATE_STATE

    return await send_translation_result(update, context, text, translated, source_lang, target_lang, detected_lang)


async def translate_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    user_id = update.effective_user.id
    text = (update.effective_message.text or "").strip()
    menu_mode = context.user_data.get("lang_menu_mode")
    source_lang, target_lang = ensure_user_data_langs(context, user_id)

    if menu_mode in {"tr_src", "tr_tgt"}:
        if text == LANGUAGE_MENU_BACK:
            context.user_data.pop("lang_menu_mode", None)
            return await show_translate_prompt(update, context)

        choices = selectable_languages(
            include_auto=(menu_mode == "tr_src"),
            for_target=(menu_mode == "tr_tgt"),
        )
        picked_code = parse_language_menu_choice(text, include_auto=(menu_mode == "tr_src"))
        if picked_code and picked_code not in choices:
            picked_code = None
        if not picked_code:
            await send_markdown(
                update,
                "Please choose a language from the menu.",
                language_menu_keyboard(choices, include_auto=(menu_mode == "tr_src")),
            )
            return TRANSLATE_STATE
        if menu_mode == "tr_src":
            context.user_data["source_lang"] = picked_code
        else:
            context.user_data["target_lang"] = picked_code
        context.user_data.pop("lang_menu_mode", None)
        return await show_translate_prompt(update, context)

    if text == TR_PICK_SOURCE:
        context.user_data["lang_menu_mode"] = "tr_src"
        await send_markdown(
            update,
            "Choose the language you are translating from:",
            language_menu_keyboard(selectable_languages(include_auto=True), include_auto=True),
        )
        return TRANSLATE_STATE

    if text == TR_PICK_TARGET:
        context.user_data["lang_menu_mode"] = "tr_tgt"
        await send_markdown(
            update,
            "Choose the language you are translating to:",
            language_menu_keyboard(selectable_languages(include_auto=False, for_target=True), include_auto=False),
        )
        return TRANSLATE_STATE

    if text == TR_TRAVEL:
        return await travel_entry(update, context)

    if text == TR_SWAP:
        if source_lang == "auto":
            await send_markdown(update, "Choose a specific source language before using Swap.")
            return TRANSLATE_STATE
        context.user_data["source_lang"], context.user_data["target_lang"] = target_lang, source_lang
        return await show_translate_prompt(update, context)

    if text == TR_AGAIN:
        return await show_translate_prompt(update, context)

    if text == TR_HELP:
        await send_markdown(
            update,
            (
                "*Tips*\n\n"
                "Send text directly and translation starts right away.\n"
                "Voice notes also work when speech tools are installed.\n"
                "Use Speak Result when audio is available for the target language."
            ),
            translation_panel_keyboard(source_lang, target_lang),
        )
        return TRANSLATE_STATE

    if text == TR_BACK_MENU:
        context.user_data.pop("lang_menu_mode", None)
        await send_markdown(update, WELCOME_TEXT, main_menu_keyboard())
        return ConversationHandler.END

    return await run_translation_flow(update, context, text)


async def voice_translation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    source_lang, _ = ensure_user_data_langs(context, update.effective_user.id)
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        transcribed_text = await transcribe_voice_message(update, context, source_lang)
    except RuntimeError as exc:
        await update.effective_message.reply_text(str(exc))
        return TRANSLATE_STATE
    except Exception as exc:  # pragma: no cover
        logger.exception("Voice translation failed: %s", exc)
        await update.effective_message.reply_text("I could not process that voice note. Please try a shorter one.")
        return TRANSLATE_STATE

    await update.effective_message.reply_text(f"Heard:\n{transcribed_text}")
    return await run_translation_flow(update, context, transcribed_text)


async def handle_translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return TRANSLATE_STATE

    await register_user(update)
    await query.answer()
    user_id = update.effective_user.id
    if query.data == CB_TRANSLATE_TTS:
        last = context.user_data.get("last_translation")
        if not last:
            await query.message.reply_text("Translate something first so I can speak it.")
            return TRANSLATE_STATE
        try:
            audio_bytes = await build_tts_audio_bytes(last["translated_text"], last["target_lang"])
        except RuntimeError as exc:
            await query.message.reply_text(str(exc))
            return TRANSLATE_STATE
        except Exception as exc:  # pragma: no cover
            logger.exception("TTS failed: %s", exc)
            await query.message.reply_text("I could not create audio for that translation.")
            return TRANSLATE_STATE
        audio_bytes.name = "translation.mp3"
        await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=InputFile(audio_bytes, filename="translation.mp3"),
            title="Translation speech",
            performer="Translator Bot",
        )
        return TRANSLATE_STATE

    if query.data == CB_ONBOARD_START:
        return await show_translate_prompt(update, context)

    if query.data == CB_ONBOARD_SETTINGS:
        return await settings_entry(update, context)

    return TRANSLATE_STATE


async def settings_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    user_id = update.effective_user.id
    text = (update.effective_message.text or "").strip()
    menu_mode = context.user_data.get("lang_menu_mode")

    if menu_mode not in {"set_src", "set_tgt"}:
        if text == SET_PICK_SOURCE:
            context.user_data["lang_menu_mode"] = "set_src"
            await send_markdown(
                update,
                "Choose your default source language:",
                language_menu_keyboard(selectable_languages(include_auto=True), include_auto=True),
            )
            return SETTINGS_STATE
        if text == SET_PICK_TARGET:
            context.user_data["lang_menu_mode"] = "set_tgt"
            await send_markdown(
                update,
                "Choose your default target language:",
                language_menu_keyboard(selectable_languages(include_auto=False, for_target=True), include_auto=False),
            )
            return SETTINGS_STATE
        if text == SET_BACK_MENU:
            await send_markdown(update, WELCOME_TEXT, main_menu_keyboard())
            return ConversationHandler.END
        return SETTINGS_STATE

    if text == LANGUAGE_MENU_BACK:
        context.user_data.pop("lang_menu_mode", None)
        return await show_settings_overview(update, user_id)

    choices = selectable_languages(include_auto=(menu_mode == "set_src"), for_target=(menu_mode == "set_tgt"))
    picked_code = parse_language_menu_choice(text, include_auto=(menu_mode == "set_src"))
    if picked_code and picked_code not in choices:
        picked_code = None
    if not picked_code:
        await send_markdown(
            update,
            "Please choose a language from the menu.",
            language_menu_keyboard(choices, include_auto=(menu_mode == "set_src")),
        )
        return SETTINGS_STATE

    if menu_mode == "set_src":
        db.update_user_preferences(user_id, source_lang=picked_code)
    else:
        db.update_user_preferences(user_id, target_lang=picked_code)

    context.user_data.pop("lang_menu_mode", None)
    source, target = get_user_langs(user_id)
    context.user_data["source_lang"] = source
    context.user_data["target_lang"] = target
    await send_markdown(
        update,
        (
            "*Preferences Updated*\n\n"
            f"*Default from:* {escape_markdown(ui_lang_name(source), version=1)}\n"
            f"*Default to:* {escape_markdown(ui_lang_name(target), version=1)}"
        ),
        settings_keyboard(source, target),
    )
    return SETTINGS_STATE


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("An unexpected error happened. Please try again.")


def start_health_server() -> None:
    port_value = os.getenv("PORT")
    if not port_value:
        logger.info("PORT is not set. Health server not started.")
        return

    try:
        port = int(port_value)
    except ValueError:
        logger.warning("Invalid PORT value: %s", port_value)
        return

    def _serve() -> None:
        try:
            server = HTTPServer(("0.0.0.0", port), HealthHandler)
            logger.info("Health server listening on port %s", port)
            server.serve_forever()
        except Exception as exc:  # pragma: no cover
            logger.exception("Health server failed: %s", exc)

    threading.Thread(target=_serve, daemon=True).start()


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Add it in environment variables.")

    app = Application.builder().token(BOT_TOKEN).build()

    translate_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CommandHandler("translate", translate_entry),
            MessageHandler(filters.Regex(f"^{re.escape(MENU_TRANSLATE)}$"), translate_entry),
        ],
        states={
            TRANSLATE_STATE: [
                CallbackQueryHandler(handle_translate_callback, pattern=r"^(tr:tts|ob:)"),
                MessageHandler(filters.VOICE, voice_translation_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, translate_text_handler),
            ],
            SETTINGS_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_text_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
    )

    travel_conv = ConversationHandler(
        entry_points=[
            CommandHandler("travel", travel_entry),
            MessageHandler(filters.Regex(f"^{re.escape(MENU_TRAVEL)}$"), travel_entry),
            MessageHandler(filters.Regex(f"^{re.escape(TR_TRAVEL)}$"), travel_entry),
        ],
        states={TRAVEL_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, travel_text_handler)]},
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
    )

    settings_conv = ConversationHandler(
        entry_points=[
            CommandHandler("settings", settings_entry),
            MessageHandler(filters.Regex(f"^{re.escape(MENU_SETTINGS)}$"), settings_entry),
        ],
        states={SETTINGS_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_text_handler)]},
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(translate_conv)
    app.add_handler(travel_conv)
    app.add_handler(settings_conv)
    app.add_handler(MessageHandler(filters.VOICE, voice_translation_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_text_handler))
    app.add_error_handler(global_error_handler)
    return app


def main() -> None:
    start_health_server()
    app = build_application()
    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
