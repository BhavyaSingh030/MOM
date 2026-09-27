# meeting-minutes-ai

A Python project scaffold for meeting transcription, analysis, and minutes generation. The SQLite schema and helper functions are in `db/`; `data/`, `src/`, and `app/` are ready for datasets, processing code, and the application UI.

## Setup

Use Python 3.10 or newer, then install dependencies:

```bash
python -m pip install -r requirements.txt
```

Initialize the database by importing and calling `init_db()` from `db/db_utils.py`:

```python
from db.db_utils import init_db

init_db()
```

The database is created at `db/meetings.db`.

## Database helpers

- `create_meeting(title, date)` returns `(meeting_id, meeting_code)`; codes are generated with `secrets.token_urlsafe(6)`.
- `get_meeting_by_code(code)` returns a meeting dictionary or `None`.
- `insert_sentences(bulk)` and `insert_action_items(bulk)` accept iterables of dictionaries and return inserted-row counts.
- `insert_minutes(meeting_id, summary_text)` returns the new minutes ID.
- `end_meeting(meeting_id)` marks the meeting as `ended` and returns whether a row was updated.
- `get_full_meeting_data(meeting_id)` returns the meeting and its related records, or `None` if it does not exist.
