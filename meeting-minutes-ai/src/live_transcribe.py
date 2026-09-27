"""Chunked Whisper transcription for live-meeting demonstrations."""

from functools import lru_cache
from pathlib import Path
import tempfile
import time
from typing import Any

import whisper
from pydub import AudioSegment

try:
    from .nlp_core import preprocess
except ImportError:
    from nlp_core import preprocess

from db import db_utils


CHUNK_LENGTH_MS = 10_000
CHUNK_DELAY_SECONDS = 0.25


@lru_cache(maxsize=1)
def _get_model() -> Any:
    return whisper.load_model("base")


def transcribe_chunk(audio_chunk_path: str | Path) -> str:
    """Transcribe one audio chunk using the cached Whisper base model."""
    result = _get_model().transcribe(str(audio_chunk_path))
    return str(result.get("text", "")).strip()


def simulate_live_meeting(full_audio_path: str | Path, meeting_id: int) -> str:
    """Transcribe audio in ten-second chunks and persist each chunk immediately."""
    meeting_data = db_utils.get_full_meeting_data(meeting_id)
    if meeting_data is None:
        raise ValueError(f"Meeting {meeting_id} does not exist")

    audio = AudioSegment.from_file(full_audio_path)
    transcript_parts: list[str] = []
    existing_transcript = meeting_data["meeting"].get("raw_transcript") or ""
    current_transcript = str(existing_transcript)

    for start_ms in range(0, len(audio), CHUNK_LENGTH_MS):
        chunk = audio[start_ms : start_ms + CHUNK_LENGTH_MS]
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            chunk_path = Path(temp_file.name)
        try:
            chunk.export(chunk_path, format="wav")
            chunk_text = transcribe_chunk(chunk_path)
        finally:
            chunk_path.unlink(missing_ok=True)

        if chunk_text:
            transcript_parts.append(chunk_text)
            chunk_sentences = preprocess(chunk_text)
            db_utils.insert_sentences(
                [
                    {
                        "meeting_id": meeting_id,
                        "speaker": row["speaker"],
                        "sentence_text": row["raw_sentence"],
                        "sentence_type": None,
                        "topic_cluster": None,
                    }
                    for row in chunk_sentences.to_dict(orient="records")
                ]
            )
            addition = " ".join(
                row.strip()
                for row in chunk_sentences["raw_sentence"].tolist()
                if row.strip()
            )
            current_transcript = " ".join(
                part for part in (current_transcript.strip(), addition) if part
            )
            db_utils.update_meeting_transcript(meeting_id, current_transcript)

        time.sleep(CHUNK_DELAY_SECONDS)

    return " ".join(transcript_parts)
