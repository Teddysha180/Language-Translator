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
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import requests
from deep_translator import GoogleTranslator
from deep_translator.exceptions import NotValidLength, RequestError, TooManyRequests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
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
    PRIMARY_ADMIN_ID,
    REQUIRED_CHANNEL_URL,
    REQUIRED_CHANNEL_USERNAME,
    WELCOME_TEXT,
)
from database import Database
from keyboards import (
    CB_ADMIN_ADD_ADMIN,
    CB_ADMIN_ADMINS,
    CB_ADMIN_BROADCAST,
    CB_ADMIN_BROADCAST_CANCEL,
    CB_ADMIN_BROADCAST_POST,
    CB_ADMIN_BROADCAST_SEND,
    CB_ADMIN_BROADCAST_SKIP_BUTTON,
    CB_ADMIN_BROADCAST_START,
    CB_ADMIN_DASHBOARD,
    CB_ADMIN_REMOVE_ADMIN,
    CB_ADMIN_STATUS,
    CB_JOIN_CHECK,
    CB_ONBOARD_SETTINGS,
    CB_ONBOARD_START,
    CB_TRANSLATE_TTS,
    LANGUAGE_MENU_BACK,
    MENU_HELP,
    MENU_SETTINGS,
    MENU_TRANSLATE,
    SET_BACK_MENU,
    SET_PICK_SOURCE,
    SET_PICK_TARGET,
    TR_AGAIN,
    TR_BACK_MENU,
    TR_PICK_SOURCE,
    TR_PICK_TARGET,
    TR_SWAP,
    admin_broadcast_builder_keyboard,
    admin_panel_keyboard,
    join_required_keyboard,
    language_menu_keyboard,
    language_menu_label,
    main_menu_keyboard,
    onboarding_keyboard,
    settings_keyboard,
    translation_panel_keyboard,
    translation_result_inline_keyboard,
)
from languages import ALL_LANGUAGES, TRANSLATOR_CODE_ALIASES, display_language_name

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
BOT_STARTED_AT = time.time()

TRANSLATE_STATE = 1
SETTINGS_STATE = 2

db = Database(DB_PATH)
db.ensure_admin(PRIMARY_ADMIN_ID, PRIMARY_ADMIN_ID)

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

OCR_SPACE_LANGUAGE_HINTS = {
    "auto": "auto",
    "ar": "ara",
    "bg": "bul",
    "zh-CN": "chs",
    "zh-TW": "cht",
    "hr": "hrv",
    "cs": "cze",
    "da": "dan",
    "nl": "dut",
    "en": "eng",
    "fi": "fin",
    "fr": "fre",
    "de": "ger",
    "el": "gre",
    "hu": "hun",
    "ko": "kor",
    "it": "ita",
    "ja": "jpn",
    "pl": "pol",
    "pt": "por",
    "ru": "rus",
    "sl": "slv",
    "es": "spa",
    "sv": "swe",
    "th": "tha",
    "tr": "tur",
    "uk": "ukr",
    "vi": "vnm",
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


def resolve_ocr_space_language(code: str) -> str:
    aliases = [code, *TRANSLATOR_CODE_ALIASES.get(code, [])]
    for candidate in aliases:
        if candidate in OCR_SPACE_LANGUAGE_HINTS:
            return OCR_SPACE_LANGUAGE_HINTS[candidate]
    return "auto"


def is_admin_user(user_id: Optional[int]) -> bool:
    return bool(user_id) and db.is_admin(int(user_id))


async def is_required_channel_member(context: ContextTypes.DEFAULT_TYPE, user_id: Optional[int]) -> bool:
    if not user_id or is_admin_user(user_id):
        return True
    try:
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL_USERNAME, int(user_id))
    except Exception as exc:  # pragma: no cover
        logger.warning("Channel membership check failed for %s: %s", user_id, exc)
        return False

    if member.status in {"member", "administrator", "creator"}:
        return True
    if member.status == "restricted" and getattr(member, "is_member", False):
        return True
    return False


async def enforce_required_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id if update.effective_user else None
    if await is_required_channel_member(context, user_id):
        return True
    if update.effective_message:
        await update.effective_message.reply_text(
            (
                "*Join Required*\n\n"
                "Please join our channel first to use this bot.\n"
                "After joining, tap *I Joined* to continue."
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=join_required_keyboard(REQUIRED_CHANNEL_URL),
        )
    return False


async def deny_admin_access(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("This command is available to bot admins only.")


def format_uptime() -> str:
    total_seconds = max(0, int(time.time() - BOT_STARTED_AT))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def build_admin_stats_text() -> str:
    return (
        "*Admin Dashboard*\n\n"
        f"*Users:* {db.get_user_count():,}\n"
        f"*New users today:* {db.get_new_user_count(1):,}\n"
        f"*New users this week:* {db.get_new_user_count(7):,}\n"
        f"*Translations:* {db.get_translation_count():,}\n"
        f"*Translations today:* {db.get_recent_translation_count(1):,}\n"
        f"*Translations this week:* {db.get_recent_translation_count(7):,}\n"
        f"*Admins:* {len(db.list_admin_ids()):,}\n"
        f"*Uptime:* {format_uptime()}\n"
        f"*Health:* `/health` active"
    )


def clear_admin_broadcast_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("admin_broadcast_draft", None)
    context.user_data.pop("admin_broadcast_step", None)


def get_admin_broadcast_draft(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Optional[str]]:
    return context.user_data.setdefault("admin_broadcast_draft", {})


def get_public_health_url() -> str:
    for key in ("PUBLIC_WEB_URL", "RENDER_EXTERNAL_URL", "APP_BASE_URL"):
        value = os.getenv(key, "").strip().rstrip("/")
        if value:
            return f"{value}/health"
    return ""


def admin_panel_text(view: str) -> str:
    if view == "status":
        return (
            "*Bot Status*\n\n"
            f"*Uptime:* {format_uptime()}\n"
            f"*Users:* {db.get_user_count():,}\n"
            f"*Translations:* {db.get_translation_count():,}\n"
            f"*Today:* {db.get_recent_translation_count(1):,} translations\n"
            f"*This week:* {db.get_recent_translation_count(7):,} translations\n"
            "*Health endpoint:* `/health`"
        )
    if view == "admins":
        admins = db.list_admin_ids()
        lines = ["*Admin List*", ""]
        for admin_id in admins:
            suffix = " (main admin)" if admin_id == PRIMARY_ADMIN_ID else ""
            lines.append(f"- `{admin_id}`{suffix}")
        return "\n".join(lines)
    if view == "broadcast":
        return (
            "*Broadcast Tools*\n\n"
            "Use the guided flow below.\n\n"
            "1. Tap *Start Broadcast*\n"
            "2. Send the post first\n"
            "3. Add an inline button or skip it\n"
            "4. Send the campaign to all users"
        )
    if view == "broadcast_post":
        return (
            "*Post Broadcast Guide*\n\n"
            "Supported post formats:\n"
            "- text\n"
            "- photo with caption\n"
            "- video with caption\n"
            "- document with caption\n\n"
            "After you send the post, the bot will ask for an optional inline button."
        )
    if view == "add_admin":
        return (
            "*Add Admin*\n\n"
            "Main admin only.\n"
            "Use:\n"
            "`/addadmin 123456789`"
        )
    if view == "remove_admin":
        return (
            "*Remove Admin*\n\n"
            "Main admin only.\n"
            "Use:\n"
            "`/removeadmin 123456789`"
        )
    return (
        f"{build_admin_stats_text()}\n\n"
        "*Quick Actions*\n"
        "Use the buttons below to view status, admins, or broadcast tools."
    )


def parse_broadcast_button_spec(raw: str) -> Tuple[Optional[str], Optional[str]]:
    text = (raw or "").strip()
    if not text:
        return None, None
    if "|" not in text:
        return None, None
    label, url = [part.strip() for part in text.split("|", 1)]
    if not label or not url or not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return None, None
    return label[:64], url


def build_broadcast_markup(button_label: Optional[str], button_url: Optional[str]) -> Optional[InlineKeyboardMarkup]:
    if not button_label or not button_url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(button_label, url=button_url)]])


async def broadcast_message_to_users(
    context: ContextTypes.DEFAULT_TYPE,
    user_ids: list[int],
    text: Optional[str] = None,
    parse_mode: Optional[str] = None,
    photo_file_id: Optional[str] = None,
    video_file_id: Optional[str] = None,
    document_file_id: Optional[str] = None,
    caption: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> Tuple[int, int]:
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            if photo_file_id:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo_file_id,
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
            elif video_file_id:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=video_file_id,
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
            elif document_file_id:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=document_file_id,
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text or "",
                    parse_mode=parse_mode,
                    disable_web_page_preview=False,
                    reply_markup=reply_markup,
                )
            sent += 1
        except Exception as exc:  # pragma: no cover
            failed += 1
            logger.warning("Broadcast failed for user %s: %s", user_id, exc)
    return sent, failed


async def send_admin_broadcast_draft_prompt(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            (
                "*Broadcast Builder*\n\n"
                "Step 1 of 2\n"
                "Send the post you want to broadcast.\n\n"
                "Supported formats:\n"
                "- text\n"
                "- photo with caption\n"
                "- video with caption\n"
                "- document with caption"
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_broadcast_builder_keyboard("await_post"),
        )


async def send_admin_broadcast_button_prompt(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            (
                "*Broadcast Builder*\n\n"
                "Step 2 of 2\n"
                "Send the button in this format:\n"
                "`Button Text | https://example.com`\n\n"
                "Or tap *Skip Button* to send the post without a button."
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_broadcast_builder_keyboard("await_button"),
        )


async def send_admin_broadcast_draft_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    draft = context.user_data.get("admin_broadcast_draft") or {}
    if not draft:
        if update.effective_message:
            await update.effective_message.reply_text("There is no broadcast draft ready to send.")
        return

    sent, failed = await broadcast_message_to_users(
        context,
        db.get_all_user_ids(),
        text=draft.get("text"),
        parse_mode=draft.get("parse_mode"),
        photo_file_id=draft.get("photo_file_id"),
        video_file_id=draft.get("video_file_id"),
        document_file_id=draft.get("document_file_id"),
        caption=draft.get("caption"),
        reply_markup=build_broadcast_markup(draft.get("button_label"), draft.get("button_url")),
    )
    clear_admin_broadcast_draft(context)
    if update.effective_message:
        await update.effective_message.reply_text(f"Broadcast finished. Sent: {sent}, Failed: {failed}.")


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
                "Welcome to Language Studio.\n\n"
                "1. Send text, a photo, or a voice note.\n"
                "2. Choose your From and To languages anytime.\n"
                "3. Use Speak Result when audio is available."
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
            "*Language Studio*\n\n"
            f"*From:* {src_name}\n"
            f"*To:* {tgt_name}\n\n"
            "Send text, a photo, or a voice note to get started."
        ),
        reply_markup=translation_panel_keyboard(source, target),
    )
    return TRANSLATE_STATE


async def show_settings_overview(update: Update, user_id: int) -> int:
    source, target = get_user_langs(user_id)
    await send_markdown(
        update,
        (
            "*Language Settings*\n\n"
            f"*Default source:* {escape_markdown(ui_lang_name(source), version=1)}\n"
            f"*Default target:* {escape_markdown(ui_lang_name(target), version=1)}"
        ),
        settings_keyboard(source, target),
    )
    return SETTINGS_STATE


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    if not await enforce_required_membership(update, context):
        return ConversationHandler.END
    context.user_data.pop("lang_menu_mode", None)
    await animate_start_intro(update)
    await show_onboarding_if_needed(update, update.effective_user.id)
    return await show_translate_prompt(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    if not await enforce_required_membership(update, context):
        return
    await send_markdown(update, HELP_TEXT, main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)


async def admin_dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin_user(user_id):
        await deny_admin_access(update)
        return
    await send_markdown(
        update,
        admin_panel_text("dashboard"),
        reply_markup=admin_panel_keyboard(get_public_health_url()),
        parse_mode=ParseMode.MARKDOWN,
    )


async def bot_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin_user(user_id):
        await deny_admin_access(update)
        return
    await send_markdown(
        update,
        admin_panel_text("status"),
        reply_markup=admin_panel_keyboard(get_public_health_url()),
        parse_mode=ParseMode.MARKDOWN,
    )


async def list_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin_user(user_id):
        await deny_admin_access(update)
        return
    await send_markdown(
        update,
        admin_panel_text("admins"),
        reply_markup=admin_panel_keyboard(get_public_health_url()),
        parse_mode=ParseMode.MARKDOWN,
    )


async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    caller_id = update.effective_user.id if update.effective_user else None
    if caller_id != PRIMARY_ADMIN_ID:
        await deny_admin_access(update)
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("Admin user_id must be a number.")
        return
    db.ensure_admin(new_admin_id, int(caller_id))
    await update.effective_message.reply_text(f"Admin access granted to {new_admin_id}.")


async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    caller_id = update.effective_user.id if update.effective_user else None
    if caller_id != PRIMARY_ADMIN_ID:
        await deny_admin_access(update)
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        admin_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("Admin user_id must be a number.")
        return
    if admin_id == PRIMARY_ADMIN_ID:
        await update.effective_message.reply_text("The main admin cannot be removed.")
        return
    db.remove_admin(admin_id)
    await update.effective_message.reply_text(f"Admin access removed from {admin_id}.")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    caller_id = update.effective_user.id if update.effective_user else None
    if not is_admin_user(caller_id):
        await deny_admin_access(update)
        return
    clear_admin_broadcast_draft(context)
    context.user_data["admin_broadcast_step"] = "await_post"
    await send_admin_broadcast_draft_prompt(update)


async def broadcast_button_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update)
    caller_id = update.effective_user.id if update.effective_user else None
    if not is_admin_user(caller_id):
        await deny_admin_access(update)
        return

    draft = context.user_data.get("admin_broadcast_draft")
    if not draft:
        await update.effective_message.reply_text("Start with /broadcast or the Broadcast button in /admin.")
        return

    button_label, button_url = parse_broadcast_button_spec(" ".join(context.args))
    if not button_label:
        await update.effective_message.reply_text("Button format: /broadcast_button Button Text | https://example.com")
        return

    draft["button_label"] = button_label
    draft["button_url"] = button_url
    await send_admin_broadcast_draft_now(update, context)


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await register_user(update)
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin_user(user_id):
        await query.answer("Admins only.", show_alert=True)
        return

    if query.data == CB_ADMIN_BROADCAST_START:
        clear_admin_broadcast_draft(context)
        context.user_data["admin_broadcast_step"] = "await_post"
        await query.answer()
        await query.message.reply_text(
            (
                "*Broadcast Builder*\n\n"
                "Step 1 of 2\n"
                "Send the post you want to broadcast."
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_broadcast_builder_keyboard("await_post"),
        )
        return

    if query.data == CB_ADMIN_BROADCAST:
        await query.answer()
        await query.message.reply_text(
            (
                "*Broadcast Builder*\n\n"
                "This tool will guide you step by step.\n\n"
                "Step 1: send the post you want to broadcast.\n"
                "Step 2: add an inline button or skip it.\n"
                "Step 3: send the campaign to all users."
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_broadcast_builder_keyboard("await_post"),
        )
        return

    if query.data == CB_ADMIN_BROADCAST_POST:
        await query.answer()
        await query.message.reply_text(
            (
                "*Broadcast Formats*\n\n"
                "You can send:\n"
                "- text\n"
                "- photo with caption\n"
                "- video with caption\n"
                "- document with caption\n\n"
                "After that, the bot will ask for the inline button."
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_broadcast_builder_keyboard("await_post"),
        )
        return

    if query.data == CB_ADMIN_BROADCAST_SKIP_BUTTON:
        draft = context.user_data.get("admin_broadcast_draft") or {}
        draft["button_label"] = None
        draft["button_url"] = None
        context.user_data["admin_broadcast_draft"] = draft
        await query.answer("Button skipped.")
        await query.message.reply_text("Sending the broadcast now...")
        await send_admin_broadcast_draft_now(update, context)
        return

    if query.data == CB_ADMIN_BROADCAST_SEND:
        await query.answer()
        await query.message.reply_text("Sending the broadcast now...")
        await send_admin_broadcast_draft_now(update, context)
        return

    if query.data == CB_ADMIN_BROADCAST_CANCEL:
        clear_admin_broadcast_draft(context)
        await query.answer("Broadcast cancelled.")
        await query.message.reply_text("Broadcast draft cancelled.")
        return

    view_map = {
        CB_ADMIN_DASHBOARD: "dashboard",
        CB_ADMIN_STATUS: "status",
        CB_ADMIN_ADMINS: "admins",
        CB_ADMIN_ADD_ADMIN: "add_admin",
        CB_ADMIN_REMOVE_ADMIN: "remove_admin",
    }
    view = view_map.get(query.data, "dashboard")
    await query.answer()
    await query.message.edit_text(
        text=admin_panel_text(view),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_panel_keyboard(get_public_health_url()),
        disable_web_page_preview=True,
    )


async def handle_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await register_user(update)
    await query.answer()
    if await is_required_channel_member(context, update.effective_user.id if update.effective_user else None):
        await query.message.reply_text("Access granted. You can use the bot now.")
        await show_translate_prompt(update, context)
        return
    await query.message.reply_text(
        (
            "*Join Required*\n\n"
            "We still could not verify your channel membership.\n"
            "Please join the channel first, then tap *I Joined* again."
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=join_required_keyboard(REQUIRED_CHANNEL_URL),
    )


async def admin_broadcast_draft_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin_user(user_id):
        return False

    step = context.user_data.get("admin_broadcast_step")
    message = update.effective_message
    if not step or not message:
        return False

    if step == "await_post":
        draft = get_admin_broadcast_draft(context)
        draft.clear()
        draft["parse_mode"] = ParseMode.HTML

        if message.photo:
            draft["photo_file_id"] = message.photo[-1].file_id
            draft["caption"] = message.caption_html or message.caption or ""
        elif message.video:
            draft["video_file_id"] = message.video.file_id
            draft["caption"] = message.caption_html or message.caption or ""
        elif message.document:
            draft["document_file_id"] = message.document.file_id
            draft["caption"] = message.caption_html or message.caption or ""
        elif message.text and not message.text.startswith("/"):
            draft["text"] = message.text_html or message.text
        else:
            await message.reply_text("Send a text, photo, video, or document to create the broadcast post.")
            return True

        context.user_data["admin_broadcast_step"] = "await_button"
        await send_admin_broadcast_button_prompt(update)
        return True

    if step == "await_button":
        if message.text and not message.text.startswith("/"):
            button_label, button_url = parse_broadcast_button_spec(message.text)
            if not button_label:
                await message.reply_text(
                    "Button format: Button Text | https://example.com\nOr tap Skip Button."
                )
                return True
            draft = get_admin_broadcast_draft(context)
            draft["button_label"] = button_label
            draft["button_url"] = button_url
            await send_admin_broadcast_draft_now(update, context)
            return True
        await message.reply_text("Send the button as: Button Text | https://example.com")
        return True

    return False


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    context.user_data.pop("lang_menu_mode", None)
    await send_markdown(update, WELCOME_TEXT, main_menu_keyboard())
    return ConversationHandler.END


async def main_menu_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    await register_user(update)
    if not await enforce_required_membership(update, context):
        return None
    if await admin_broadcast_draft_handler(update, context):
        return None
    text = (update.effective_message.text or "").strip()
    if text == MENU_TRANSLATE:
        return await translate_entry(update, context)
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
    if not await enforce_required_membership(update, context):
        return ConversationHandler.END
    context.user_data.pop("lang_menu_mode", None)
    return await show_translate_prompt(update, context)


async def settings_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    if not await enforce_required_membership(update, context):
        return ConversationHandler.END
    context.user_data.pop("lang_menu_mode", None)
    user_id = update.effective_user.id
    source, target = ensure_user_data_langs(context, user_id)
    db.update_user_preferences(user_id, source_lang=source, target_lang=target)
    return await show_settings_overview(update, user_id)


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


async def extract_text_from_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    message = update.effective_message
    if not message:
        raise RuntimeError("No image was found.")

    telegram_file = None
    if message.photo:
        telegram_file = await context.bot.get_file(message.photo[-1].file_id)
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        telegram_file = await context.bot.get_file(message.document.file_id)
    else:
        raise RuntimeError("Please send a photo or image file.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as image_file:
        image_path = image_file.name

    source_lang, _ = ensure_user_data_langs(context, update.effective_user.id)
    ocr_space_api_key = os.getenv("OCR_SPACE_API_KEY", "").strip()

    try:
        await telegram_file.download_to_drive(custom_path=image_path)

        def _ocr_with_tesseract() -> str:
            import pytesseract
            from PIL import Image

            with Image.open(image_path) as image:
                cleaned = image.convert("L")
                return pytesseract.image_to_string(cleaned).strip()

        def _ocr_with_ocr_space() -> str:
            with open(image_path, "rb") as image_file:
                response = requests.post(
                    "https://api.ocr.space/parse/image",
                    headers={"apikey": ocr_space_api_key},
                    files={"file": image_file},
                    data={
                        "language": resolve_ocr_space_language(source_lang),
                        "isOverlayRequired": "false",
                        "OCREngine": "2",
                    },
                    timeout=45,
                )
            response.raise_for_status()
            payload = response.json()
            if payload.get("IsErroredOnProcessing"):
                message_text = payload.get("ErrorMessage") or ["OCR processing failed."]
                raise RuntimeError(", ".join(message_text))
            parsed = payload.get("ParsedResults") or []
            extracted = "\n".join((item.get("ParsedText") or "").strip() for item in parsed).strip()
            return extracted

        try:
            extracted_text = await asyncio.to_thread(_ocr_with_tesseract)
        except ImportError:
            extracted_text = ""
        except Exception as exc:
            logger.warning("Local OCR failed: %s", exc)
            extracted_text = ""

        if not extracted_text and ocr_space_api_key:
            extracted_text = await asyncio.to_thread(_ocr_with_ocr_space)
    finally:
        try:
            os.remove(image_path)
        except OSError:
            pass

    if not extracted_text:
        if ocr_space_api_key:
            raise RuntimeError("I could not detect readable text in that image.")
        raise RuntimeError(
            "Image translation needs Tesseract OCR on the server or an OCR_SPACE_API_KEY in Render."
        )

    return extracted_text


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
        "<b>Translation Result</b>\n\n"
        f"{detected_line}"
        f"<b>From:</b> {html.escape(ui_lang_name(source_lang))}\n"
        f"<b>To:</b> {html.escape(ui_lang_name(target_lang))}\n\n"
        "<b>Original</b>\n"
        f"<code>{html.escape(text[:700])}</code>\n\n"
        "<b>Translation</b>\n"
        f"<code>{html.escape(translated[:700])}</code>"
    )
    result_actions = translation_result_inline_keyboard(include_tts=resolve_tts_code(target_lang) is not None)
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
        await send_markdown(update, f"Language issue: {escape_markdown(str(exc), version=1)}")
        return TRANSLATE_STATE
    except (NotValidLength, TooManyRequests, RequestError):
        await send_markdown(update, "The translation service is busy right now. Please try again in a moment.")
        return TRANSLATE_STATE
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected translation failure: %s", exc)
        await send_markdown(update, "Something went wrong while translating. Please try again.")
        return TRANSLATE_STATE

    translated = translated or ""
    if is_effectively_empty_text(translated):
        await send_markdown(update, "No translation result came back for that language pair. Try another target language.")
        return TRANSLATE_STATE

    return await send_translation_result(update, context, text, translated, source_lang, target_lang, detected_lang)


async def translate_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    if not await enforce_required_membership(update, context):
        return TRANSLATE_STATE
    if await admin_broadcast_draft_handler(update, context):
        return TRANSLATE_STATE
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
                "Please choose a language from the list below.",
                language_menu_keyboard(choices, include_auto=(menu_mode == "tr_src")),
            )
            return TRANSLATE_STATE
        if menu_mode == "tr_src":
            context.user_data["source_lang"] = picked_code
        else:
            context.user_data["target_lang"] = picked_code
        context.user_data.pop("lang_menu_mode", None)
        return await show_translate_prompt(update, context)

    if text.startswith(f"{TR_PICK_SOURCE} "):
        context.user_data["lang_menu_mode"] = "tr_src"
        await send_markdown(
            update,
            "Choose the source language:",
            language_menu_keyboard(selectable_languages(include_auto=True), include_auto=True),
        )
        return TRANSLATE_STATE

    if text.startswith(f"{TR_PICK_TARGET} "):
        context.user_data["lang_menu_mode"] = "tr_tgt"
        await send_markdown(
            update,
            "Choose the target language:",
            language_menu_keyboard(selectable_languages(include_auto=False, for_target=True), include_auto=False),
        )
        return TRANSLATE_STATE

    if text == TR_SWAP:
        if source_lang == "auto":
            await send_markdown(update, "Choose a specific source language before using Swap.")
            return TRANSLATE_STATE
        context.user_data["source_lang"], context.user_data["target_lang"] = target_lang, source_lang
        return await show_translate_prompt(update, context)

    if text == TR_AGAIN:
        return await show_translate_prompt(update, context)

    if text == TR_BACK_MENU:
        context.user_data.pop("lang_menu_mode", None)
        await send_markdown(update, WELCOME_TEXT, main_menu_keyboard())
        return ConversationHandler.END

    return await run_translation_flow(update, context, text)


async def voice_translation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    if not await enforce_required_membership(update, context):
        return TRANSLATE_STATE
    if await admin_broadcast_draft_handler(update, context):
        return TRANSLATE_STATE
    source_lang, _ = ensure_user_data_langs(context, update.effective_user.id)
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        transcribed_text = await transcribe_voice_message(update, context, source_lang)
    except RuntimeError as exc:
        await update.effective_message.reply_text(str(exc))
        return TRANSLATE_STATE
    except Exception as exc:  # pragma: no cover
        logger.exception("Voice translation failed: %s", exc)
        await update.effective_message.reply_text("I could not process that voice note. Please try another one.")
        return TRANSLATE_STATE

    await update.effective_message.reply_text(f"Heard:\n{transcribed_text}")
    return await run_translation_flow(update, context, transcribed_text)


async def image_translation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_user(update)
    if not await enforce_required_membership(update, context):
        return TRANSLATE_STATE
    if await admin_broadcast_draft_handler(update, context):
        return TRANSLATE_STATE
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        extracted_text = await extract_text_from_image(update, context)
    except RuntimeError as exc:
        await update.effective_message.reply_text(str(exc))
        return TRANSLATE_STATE
    except Exception as exc:  # pragma: no cover
        logger.exception("Image translation failed: %s", exc)
        await update.effective_message.reply_text("I could not read that image clearly. Please try a sharper one.")
        return TRANSLATE_STATE

    return await run_translation_flow(update, context, extracted_text)


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
            await query.message.reply_text("Translate something first, then I can read it aloud.")
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
    if not await enforce_required_membership(update, context):
        return SETTINGS_STATE
    if await admin_broadcast_draft_handler(update, context):
        return SETTINGS_STATE
    user_id = update.effective_user.id
    text = (update.effective_message.text or "").strip()
    menu_mode = context.user_data.get("lang_menu_mode")

    if menu_mode not in {"set_src", "set_tgt"}:
        if text.startswith(f"{SET_PICK_SOURCE} "):
            context.user_data["lang_menu_mode"] = "set_src"
            await send_markdown(
                update,
                "Choose your default source language:",
                language_menu_keyboard(selectable_languages(include_auto=True), include_auto=True),
            )
            return SETTINGS_STATE
        if text.startswith(f"{SET_PICK_TARGET} "):
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
            "Please choose a language from the list below.",
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
            "*Settings Updated*\n\n"
            f"*Default source:* {escape_markdown(ui_lang_name(source), version=1)}\n"
            f"*Default target:* {escape_markdown(ui_lang_name(target), version=1)}"
        ),
        settings_keyboard(source, target),
    )
    return SETTINGS_STATE


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("An unexpected error occurred. Please try again.")


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
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, image_translation_handler),
                MessageHandler(filters.VOICE, voice_translation_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, translate_text_handler),
            ],
            SETTINGS_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_text_handler)],
        },
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

    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(handle_join_callback, pattern=r"^join:"))
    app.add_handler(CommandHandler("admin", admin_dashboard_command))
    app.add_handler(CommandHandler("botstatus", bot_status_command))
    app.add_handler(CommandHandler("admins", list_admins_command))
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("removeadmin", remove_admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("broadcast_button", broadcast_button_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(translate_conv)
    app.add_handler(settings_conv)
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, image_translation_handler))
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
