"""Language definitions and utilities for the translator bot."""

from __future__ import annotations

from typing import Dict, List

# Ethiopian and Horn of Africa language focus.
ETHIOPIAN_LANGUAGES: Dict[str, str] = {
    "am": "Amharic (አማርኛ)",
    "om": "Afan Oromo (Afaan Oromoo)",
    "ti": "Tigrinya (ትግርኛ)",
    "so": "Somali (Soomaali)",
    "aa": "Afar (Qafar)",
    "tig": "Tigre (ትግሬ)",
    "ss": "Silt'e (Silt'igna)",
    "wal": "Wolaytta (Wolayttatto)",
    "sid": "Sidama (Sidaamu Afoo)",
    "gez": "Ge'ez (ግዕዝ)",
    "har": "Harari (ሀረሪ)",
    "gur": "Gurage",
    "gam": "Gamo",
    "ktb": "Kambaata",
    "dwr": "Dawuro",
    "anu": "Anuak",
    "nrb": "Nara",
    "kun": "Kunama",
    "byn": "Bilen",
    "aho": "Hadiyya",
}

# Wider world-language set.
WORLD_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "ar": "Arabic (العربية)",
    "fr": "French (Français)",
    "es": "Spanish (Español)",
    "de": "German (Deutsch)",
    "it": "Italian (Italiano)",
    "pt": "Portuguese (Português)",
    "ru": "Russian (Русский)",
    "tr": "Turkish (Türkçe)",
    "nl": "Dutch (Nederlands)",
    "sv": "Swedish (Svenska)",
    "pl": "Polish (Polski)",
    "hi": "Hindi (हिन्दी)",
    "bn": "Bengali (বাংলা)",
    "ta": "Tamil (தமிழ்)",
    "te": "Telugu (తెలుగు)",
    "ml": "Malayalam (മലയാളം)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "mr": "Marathi (मराठी)",
    "gu": "Gujarati (ગુજરાતી)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "ur": "Urdu (اردو)",
    "fa": "Persian (فارسی)",
    "he": "Hebrew (עברית)",
    "el": "Greek (Ελληνικά)",
    "uk": "Ukrainian (Українська)",
    "cs": "Czech (Čeština)",
    "ro": "Romanian (Română)",
    "hu": "Hungarian (Magyar)",
    "bg": "Bulgarian (Български)",
    "sr": "Serbian (Српски)",
    "hr": "Croatian (Hrvatski)",
    "sk": "Slovak (Slovenčina)",
    "sl": "Slovenian (Slovenščina)",
    "lt": "Lithuanian (Lietuvių)",
    "lv": "Latvian (Latviešu)",
    "et": "Estonian (Eesti)",
    "da": "Danish (Dansk)",
    "no": "Norwegian (Norsk)",
    "fi": "Finnish (Suomi)",
    "zh-CN": "Chinese Simplified (简体中文)",
    "zh-TW": "Chinese Traditional (繁體中文)",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "th": "Thai (ไทย)",
    "vi": "Vietnamese (Tiếng Việt)",
    "id": "Indonesian (Bahasa Indonesia)",
    "ms": "Malay (Bahasa Melayu)",
    "tl": "Filipino (Tagalog)",
    "sw": "Swahili (Kiswahili)",
}

ALL_LANGUAGES: Dict[str, str] = {
    "auto": "Auto Detect",
    **ETHIOPIAN_LANGUAGES,
    **WORLD_LANGUAGES,
}

# Aliases used to improve interoperability with translation APIs.
# The bot keeps user-facing codes intact and only maps internally when needed.
TRANSLATOR_CODE_ALIASES: Dict[str, List[str]] = {
    "auto": ["auto"],
    "zh": ["zh-CN", "zh", "zh-cn"],
    "zh-CN": ["zh-CN", "zh", "zh-cn"],
    "zh-TW": ["zh-TW", "zh-tw"],
    "om": ["om"],
    "wal": ["wal"],
    "sid": ["sid"],
    "ss": ["ss"],
    "tl": ["tl", "fil"],
}
