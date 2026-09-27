# meeting-minutes-ai

A Python project scaffold for meeting transcription, analysis, and minutes generation. The SQLite schema and helper functions are in `db/`; `data/`, `src/`, and `app/` are ready for datasets, processing code, and the application UI.

## Setup

Use Python 3.10 or newer, then install dependencies:

```bash
python -m pip install -r requirements.txt
```

Install dependencies and launch Streamlit with the same Python interpreter. In
this workspace, Streamlit runs from the parent folder's `.venv`:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

Before a meeting starts, the host records a full sentence for each participant
in the left setup panel and presses **Stop and save sample**. The original WAV samples and SpeechBrain ECAPA-TDNN voice
embeddings are stored with the meeting in SQLite. During the meeting, transient
utterance clips are sent to the Streamlit server to match against those profiles;
the live clips are not stored. Transcript text and labels such as `Speaker 1`
and `Speaker 2` are saved. The first speaker match downloads the pretrained
model from Hugging Face.

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
