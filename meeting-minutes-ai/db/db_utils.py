"""SQLite helpers for meetings, transcripts, action items, and minutes."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Iterable, Iterator, Mapping


DB_PATH = Path(__file__).resolve().with_name("meetings.db")
SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create the database tables if they do not already exist."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with _connection() as connection:
        connection.executescript(schema)
        columns = connection.execute("PRAGMA table_info(meetings)").fetchall()
        has_user_id = any(column[1] == "user_id" for column in columns)
        if not has_user_id:
            connection.execute("ALTER TABLE meetings ADD COLUMN user_id INTEGER REFERENCES users(user_id)")


def create_user(name: str, email: str, password: str) -> dict[str, Any]:
    """Create a new user account and return the stored user record."""
    cleaned_name = (name or "").strip()
    cleaned_email = (email or "").strip().lower()
    if not cleaned_name or not cleaned_email or not password:
        raise ValueError("Name, email, and password are required.")
    with _connection() as connection:
        try:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (cleaned_name, cleaned_email, _hash_password(password)),
            )
            return {
                "user_id": cursor.lastrowid,
                "name": cleaned_name,
                "email": cleaned_email,
            }
        except sqlite3.IntegrityError as error:
            if "users.email" in str(error):
                raise ValueError("An account already exists for this email.") from error
            raise


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    """Return a user dictionary when the email/password pair matches."""
    cleaned_email = (email or "").strip().lower()
    if not cleaned_email or not password:
        return None
    with _connection() as connection:
        row = connection.execute(
            "SELECT user_id, name, email FROM users WHERE email = ? AND password_hash = ?",
            (cleaned_email, _hash_password(password)),
        ).fetchone()
    return dict(row) if row is not None else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT user_id, name, email FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def create_meeting(title: str, date: str, user_id: int | None = None) -> tuple[int, str]:
    """Create a live meeting and return its ID and unique access code."""
    with _connection() as connection:
        while True:
            meeting_code = secrets.token_urlsafe(6)
            try:
                cursor = connection.execute(
                    "INSERT INTO meetings (title, date, meeting_code, user_id) VALUES (?, ?, ?, ?)",
                    (title, date, meeting_code, user_id),
                )
                return cursor.lastrowid, meeting_code
            except sqlite3.IntegrityError as error:
                if "meetings.meeting_code" not in str(error):
                    raise


def get_meeting_by_code(code: str, user_id: int | None = None) -> dict[str, Any] | None:
    """Return a meeting matching its access code, optionally restricted to one user."""
    with _connection() as connection:
        if user_id is None:
            row = connection.execute(
                "SELECT * FROM meetings WHERE meeting_code = ?", (code,)
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM meetings WHERE meeting_code = ? AND user_id = ?",
                (code, user_id),
            ).fetchone()
    return dict(row) if row is not None else None


def get_recent_meetings(limit: int = 10, user_id: int | None = None) -> list[dict[str, Any]]:
    """Return recent meetings for a user, or all meetings when no user is supplied."""
    limit = max(1, min(int(limit), 100))
    with _connection() as connection:
        if user_id is None:
            rows = connection.execute(
                """SELECT meeting_id, title, date, meeting_code, status, user_id,
                          EXISTS(
                              SELECT 1 FROM minutes
                              WHERE minutes.meeting_id = meetings.meeting_id
                          ) AS has_minutes
                   FROM meetings
                   ORDER BY meeting_id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT meeting_id, title, date, meeting_code, status, user_id,
                          EXISTS(
                              SELECT 1 FROM minutes
                              WHERE minutes.meeting_id = meetings.meeting_id
                          ) AS has_minutes
                   FROM meetings
                   WHERE user_id = ?
                   ORDER BY meeting_id DESC
                   LIMIT ?""",
                (user_id, limit),
            ).fetchall()
    return [dict(row) for row in rows]


def build_minutes_from_conversation(
    meeting_title: str,
    date: str,
    conversation: str,
    user_name: str | None = None,
) -> str:
    """Create a conversational summary that is useful even without a trained classifier."""
    from src.extraction_summary import build_minutes_from_conversation as generated_minutes

    return generated_minutes(
        meeting_title=meeting_title,
        date=date,
        conversation=conversation,
        user_name=user_name,
    )


def insert_sentences(bulk: Iterable[Mapping[str, Any]]) -> int:
    """Insert sentence dictionaries and return the number of inserted rows."""
    rows = [
        (
            row.get("meeting_id"),
            row.get("speaker"),
            row.get("sentence_text"),
            row.get("sentence_type"),
            row.get("topic_cluster"),
        )
        for row in bulk
    ]
    if not rows:
        return 0
    with _connection() as connection:
        cursor = connection.executemany(
            """INSERT INTO sentences
               (meeting_id, speaker, sentence_text, sentence_type, topic_cluster)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        return cursor.rowcount


def insert_sentences_with_ids(bulk: Iterable[Mapping[str, Any]]) -> list[int]:
    """Insert sentence dictionaries and return their generated sentence IDs."""
    rows = [
        (
            row.get("meeting_id"),
            row.get("speaker"),
            row.get("sentence_text"),
            row.get("sentence_type"),
            row.get("topic_cluster"),
        )
        for row in bulk
    ]
    if not rows:
        return []

    sentence_ids: list[int] = []
    with _connection() as connection:
        for row in rows:
            cursor = connection.execute(
                """INSERT INTO sentences
                   (meeting_id, speaker, sentence_text, sentence_type, topic_cluster)
                   VALUES (?, ?, ?, ?, ?)""",
                row,
            )
            sentence_ids.append(cursor.lastrowid)
    return sentence_ids


def update_meeting_transcript(meeting_id: int, raw_transcript: str) -> bool:
    """Replace a meeting's stored raw transcript; report whether it existed."""
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE meetings SET raw_transcript = ? WHERE meeting_id = ?",
            (raw_transcript, meeting_id),
        )
        return cursor.rowcount > 0


def set_meeting_audio_path(meeting_id: int, audio_path: str) -> bool:
    """Store the uploaded audio path for a meeting."""
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE meetings SET audio_path = ? WHERE meeting_id = ?",
            (audio_path, meeting_id),
        )
        return cursor.rowcount > 0


def insert_action_items(bulk: Iterable[Mapping[str, Any]]) -> int:
    """Insert action-item dictionaries and return the number of inserted rows."""
    rows = [
        (
            row.get("meeting_id"),
            row.get("sentence_id"),
            row.get("task"),
            row.get("owner"),
            row.get("deadline"),
        )
        for row in bulk
    ]
    if not rows:
        return 0
    with _connection() as connection:
        cursor = connection.executemany(
            """INSERT INTO action_items
               (meeting_id, sentence_id, task, owner, deadline)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        return cursor.rowcount


def reset_meeting_derived_data(meeting_id: int) -> None:
    """Remove generated sentences, action items, and minutes for a meeting."""
    with _connection() as connection:
        connection.execute(
            "DELETE FROM action_items WHERE meeting_id = ?", (meeting_id,)
        )
        connection.execute("DELETE FROM minutes WHERE meeting_id = ?", (meeting_id,))
        connection.execute("DELETE FROM sentences WHERE meeting_id = ?", (meeting_id,))


def append_live_utterance(meeting_id: int, speaker: str, text: str) -> str:
    """Store one live utterance and return the updated transcript."""
    cleaned = text.strip()
    if not cleaned:
        data = get_full_meeting_data(meeting_id)
        return (data["meeting"].get("raw_transcript") if data else "") or ""

    insert_sentences(
        [
            {
                "meeting_id": meeting_id,
                "speaker": speaker,
                "sentence_text": cleaned,
                "sentence_type": None,
                "topic_cluster": None,
            }
        ]
    )
    data = get_full_meeting_data(meeting_id)
    if data is None:
        return cleaned
    lines = []
    for row in data["sentences"]:
        speaker_name = (row.get("speaker") or "").strip()
        sentence = (row.get("sentence_text") or "").strip()
        lines.append(f"{speaker_name}: {sentence}" if speaker_name else sentence)
    transcript = "\n".join(line for line in lines if line.strip())
    update_meeting_transcript(meeting_id, transcript)
    return transcript


def insert_minutes(meeting_id: int, summary_text: str) -> int:
    """Store generated minutes and return the new minutes ID."""
    with _connection() as connection:
        cursor = connection.execute(
            "INSERT INTO minutes (meeting_id, summary_text) VALUES (?, ?)",
            (meeting_id, summary_text),
        )
        return cursor.lastrowid


def end_meeting(meeting_id: int) -> bool:
    """Mark a meeting as ended; return whether a meeting was updated."""
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE meetings SET status = 'ended' WHERE meeting_id = ?",
            (meeting_id,),
        )
        return cursor.rowcount > 0


def get_full_meeting_data(meeting_id: int) -> dict[str, Any] | None:
    """Return a meeting and its sentences, action items, and minutes."""
    with _connection() as connection:
        meeting = connection.execute(
            "SELECT * FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()
        if meeting is None:
            return None

        sentences = connection.execute(
            "SELECT * FROM sentences WHERE meeting_id = ? ORDER BY sentence_id",
            (meeting_id,),
        ).fetchall()
        action_items = connection.execute(
            "SELECT * FROM action_items WHERE meeting_id = ? ORDER BY item_id",
            (meeting_id,),
        ).fetchall()
        minutes = connection.execute(
            "SELECT * FROM minutes WHERE meeting_id = ? ORDER BY minutes_id",
            (meeting_id,),
        ).fetchall()

    return {
        "meeting": dict(meeting),
        "sentences": [dict(row) for row in sentences],
        "action_items": [dict(row) for row in action_items],
        "minutes": [dict(row) for row in minutes],
    }
