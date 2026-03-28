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
    "af": "Afrikaans",
    "sq": "Albanian (Shqip)",
    "ar": "Arabic (العربية)",
    "az": "Azerbaijani (Azərbaycanca)",
    "be": "Belarusian (Беларуская)",
    "fr": "French (Français)",
    "es": "Spanish (Español)",
    "de": "German (Deutsch)",
    "it": "Italian (Italiano)",
    "pt": "Portuguese (Português)",
    "ru": "Russian (Русский)",
    "tr": "Turkish (Türkçe)",
    "hy": "Armenian (Հայերեն)",
    "ka": "Georgian (ქართული)",
    "nl": "Dutch (Nederlands)",
    "sv": "Swedish (Svenska)",
    "pl": "Polish (Polski)",
    "hi": "Hindi (हिन्दी)",
    "bn": "Bengali (বাংলা)",
    "ne": "Nepali (नेपाली)",
    "si": "Sinhala (සිංහල)",
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
    "mk": "Macedonian (Македонски)",
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
    "km": "Khmer (ខ្មែរ)",
    "lo": "Lao (ລາວ)",
    "mn": "Mongolian (Монгол)",
    "id": "Indonesian (Bahasa Indonesia)",
    "ms": "Malay (Bahasa Melayu)",
    "tl": "Filipino (Tagalog)",
    "ps": "Pashto (پښتو)",
    "sw": "Swahili (Kiswahili)",
}

ALL_LANGUAGES: Dict[str, str] = {
    "auto": "Auto Detect",
    **ETHIOPIAN_LANGUAGES,
    **WORLD_LANGUAGES,
}

LANGUAGE_FLAGS: Dict[str, str] = {
    "auto": "🌍",
    "am": "🇪🇹",
    "om": "🇪🇹",
    "ti": "🇪🇷",
    "tig": "🇪🇷",
    "so": "🇸🇴",
    "aa": "🇪🇹",
    "ss": "🇪🇹",
    "wal": "🇪🇹",
    "sid": "🇪🇹",
    "gez": "📜",
    "har": "🇪🇹",
    "gur": "🇪🇹",
    "gam": "🇪🇹",
    "ktb": "🇪🇹",
    "dwr": "🇪🇹",
    "anu": "🇪🇹",
    "nrb": "🇪🇷",
    "kun": "🇪🇷",
    "byn": "🇪🇷",
    "aho": "🇪🇹",
    "en": "🇬🇧",
    "af": "🇿🇦",
    "sq": "🇦🇱",
    "ar": "🇸🇦",
    "az": "🇦🇿",
    "be": "🇧🇾",
    "fr": "🇫🇷",
    "es": "🇪🇸",
    "de": "🇩🇪",
    "it": "🇮🇹",
    "pt": "🇵🇹",
    "ru": "🇷🇺",
    "tr": "🇹🇷",
    "hy": "🇦🇲",
    "ka": "🇬🇪",
    "nl": "🇳🇱",
    "sv": "🇸🇪",
    "pl": "🇵🇱",
    "hi": "🇮🇳",
    "bn": "🇧🇩",
    "ne": "🇳🇵",
    "si": "🇱🇰",
    "ta": "🇮🇳",
    "te": "🇮🇳",
    "ml": "🇮🇳",
    "kn": "🇮🇳",
    "mr": "🇮🇳",
    "gu": "🇮🇳",
    "pa": "🇮🇳",
    "ur": "🇵🇰",
    "fa": "🇮🇷",
    "he": "🇮🇱",
    "el": "🇬🇷",
    "uk": "🇺🇦",
    "cs": "🇨🇿",
    "ro": "🇷🇴",
    "hu": "🇭🇺",
    "mk": "🇲🇰",
    "bg": "🇧🇬",
    "sr": "🇷🇸",
    "hr": "🇭🇷",
    "sk": "🇸🇰",
    "sl": "🇸🇮",
    "lt": "🇱🇹",
    "lv": "🇱🇻",
    "et": "🇪🇪",
    "da": "🇩🇰",
    "no": "🇳🇴",
    "fi": "🇫🇮",
    "zh-CN": "🇨🇳",
    "zh-TW": "🇹🇼",
    "ja": "🇯🇵",
    "ko": "🇰🇷",
    "th": "🇹🇭",
    "vi": "🇻🇳",
    "km": "🇰🇭",
    "lo": "🇱🇦",
    "mn": "🇲🇳",
    "id": "🇮🇩",
    "ms": "🇲🇾",
    "tl": "🇵🇭",
    "ps": "🇦🇫",
    "sw": "🇰🇪",
}

# Aliases used to improve interoperability with translation APIs.
# The bot keeps user-facing codes intact and only maps internally when needed.
TRANSLATOR_CODE_ALIASES: Dict[str, List[str]] = {
    "auto": ["auto"],
    "zh": ["zh-CN", "zh", "zh-cn"],
    "zh-CN": ["zh-CN", "zh", "zh-cn"],
    "zh-TW": ["zh-TW", "zh-tw", "zh"],
    "om": ["om"],
    "wal": ["wal"],
    "sid": ["sid"],
    "ss": ["ss"],
    "tl": ["tl", "fil"],
    "no": ["no", "nb"],
}


def language_flag(code: str) -> str:
    return LANGUAGE_FLAGS.get(code, "🌐")


def display_language_name(code: str) -> str:
    name = ALL_LANGUAGES.get(code, code)
    return f"{language_flag(code)} {name}"


def compact_language_name(code: str) -> str:
    name = ALL_LANGUAGES.get(code, code)
    primary_name = name
    native_name = ""

    if " (" in name and name.endswith(")"):
        primary_name, native_name = name[:-1].split(" (", 1)

    if native_name:
        return f"{language_flag(code)} {primary_name} {native_name}"
    return f"{language_flag(code)} {primary_name}"


def button_language_name(code: str) -> str:
    name = ALL_LANGUAGES.get(code, code)
    if " (" in name and name.endswith(")"):
        name = name[:-1].split(" (", 1)[0]
    return f"{language_flag(code)} {name}"


def button_language_chip(code: str) -> str:
    short_code = code.replace("auto", "AUTO").split("-", 1)[0].upper()
    return f"{language_flag(code)} {short_code}"
