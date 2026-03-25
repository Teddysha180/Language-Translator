"""SQLite database access layer for the Telegram translator bot."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class Database:
    """Simple SQLite wrapper for users, history, and saved translations."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = str(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    preferred_source_lang TEXT DEFAULT 'auto',
                    preferred_target_lang TEXT DEFAULT 'en',
                    onboarding_completed INTEGER DEFAULT 0,
                    joined_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS translation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_translations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    saved_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )
            cursor.execute("PRAGMA table_info(users)")
            user_columns = {row["name"] for row in cursor.fetchall()}
            if "onboarding_completed" not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0")
            conn.commit()

    def upsert_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name
                """,
                (user_id, username, first_name, last_name),
            )
            conn.commit()

    def get_user_preferences(self, user_id: int) -> Dict[str, str]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT preferred_source_lang, preferred_target_lang, onboarding_completed
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {
                    "preferred_source_lang": "auto",
                    "preferred_target_lang": "en",
                    "onboarding_completed": 0,
                }
            return {
                "preferred_source_lang": row["preferred_source_lang"],
                "preferred_target_lang": row["preferred_target_lang"],
                "onboarding_completed": row["onboarding_completed"],
            }

    def update_user_preferences(
        self, user_id: int, source_lang: Optional[str] = None, target_lang: Optional[str] = None
    ) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            if source_lang is not None:
                cursor.execute(
                    "UPDATE users SET preferred_source_lang = ? WHERE user_id = ?",
                    (source_lang, user_id),
                )
            if target_lang is not None:
                cursor.execute(
                    "UPDATE users SET preferred_target_lang = ? WHERE user_id = ?",
                    (target_lang, user_id),
                )
            conn.commit()

    def is_onboarding_completed(self, user_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT onboarding_completed FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return bool(row["onboarding_completed"]) if row else False

    def set_onboarding_completed(self, user_id: int, completed: bool = True) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET onboarding_completed = ? WHERE user_id = ?",
                (1 if completed else 0, user_id),
            )
            conn.commit()

    def add_translation_history(
        self,
        user_id: int,
        source_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO translation_history
                (user_id, source_text, translated_text, source_lang, target_lang)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, source_text, translated_text, source_lang, target_lang),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_translation_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, source_text, translated_text, source_lang, target_lang, timestamp
                FROM translation_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def save_translation(
        self,
        user_id: int,
        source_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO saved_translations
                (user_id, source_text, translated_text, source_lang, target_lang)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, source_text, translated_text, source_lang, target_lang),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_saved_translations(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, source_text, translated_text, source_lang, target_lang, saved_date
                FROM saved_translations
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
