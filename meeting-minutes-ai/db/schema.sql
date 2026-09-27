CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meetings (
    meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id),
    title TEXT,
    date TEXT,
    meeting_code TEXT UNIQUE,
    status TEXT DEFAULT 'live',
    raw_transcript TEXT,
    audio_path TEXT
);

CREATE TABLE IF NOT EXISTS sentences (
    sentence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER REFERENCES meetings(meeting_id),
    speaker TEXT,
    sentence_text TEXT,
    sentence_type TEXT,
    topic_cluster INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meeting_speakers (
    speaker_profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(meeting_id) ON DELETE CASCADE,
    speaker_name TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 1,
    sample_audio BLOB,
    UNIQUE (meeting_id, speaker_name)
);

CREATE TABLE IF NOT EXISTS action_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER REFERENCES meetings(meeting_id),
    sentence_id INTEGER REFERENCES sentences(sentence_id),
    task TEXT,
    owner TEXT,
    deadline TEXT
);

CREATE TABLE IF NOT EXISTS minutes (
    minutes_id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER REFERENCES meetings(meeting_id),
    summary_text TEXT,
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
