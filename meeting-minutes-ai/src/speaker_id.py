"""Speaker embeddings for assigning stable, anonymous labels within a meeting."""

import base64
import io
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy


def decode_wav_base64(audio_base64: str) -> bytes:
    """Decode a data URL or base64 string containing a WAV recording."""
    encoded = audio_base64.split(",", 1)[-1]
    return base64.b64decode(encoded, validate=True)


@torch.no_grad()
def embedding_from_wav_base64(audio_base64: str) -> np.ndarray:
    """Return an ECAPA speaker embedding for a mono, 16 kHz PCM WAV clip."""
    audio_bytes = decode_wav_base64(audio_base64)
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise ValueError("Speaker audio must be mono 16-bit PCM.")
        if wav_file.getframerate() != 16000:
            raise ValueError("Speaker audio must use a 16 kHz sample rate.")
        samples = np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype="<i2")

    if samples.size < 16000:
        raise ValueError("Speak for at least one second to identify the voice.")
    waveform = torch.from_numpy(samples.astype(np.float32) / 32768.0).unsqueeze(0)
    model = get_speaker_model()
    vector = model.encode_batch(waveform).squeeze().cpu().numpy().astype(np.float32)
    norm = np.linalg.norm(vector)
    if not norm:
        raise ValueError("Could not extract a voice fingerprint from this audio.")
    return vector / norm


@lru_cache(maxsize=1)
@torch.no_grad()
def get_speaker_model() -> EncoderClassifier:
    """Load the public ECAPA-TDNN voice embedding model once per process."""
    return EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(
            Path(__file__).resolve().parents[1]
            / "pretrained_models"
            / "spkrec-ecapa-voxceleb"
        ),
        local_strategy=LocalStrategy.COPY,
        run_opts={"device": "cpu"},
    )


def match_speaker(
    embedding: np.ndarray,
    speaker_profiles: list[dict[str, object]],
    threshold: float = 0.25,
) -> tuple[str, list[dict[str, object]]]:
    """Match to the closest enrolled voice without changing enrollment data."""
    best_index = -1
    best_score = -1.0
    for index, profile in enumerate(speaker_profiles):
        profile_vector = np.asarray(profile["embedding"], dtype=np.float32)
        score = float(np.dot(embedding, profile_vector))
        if score > best_score:
            best_index, best_score = index, score

    if best_index >= 0:
        profile = speaker_profiles[best_index]
        return str(profile["name"]), speaker_profiles

    name = f"Speaker {len(speaker_profiles) + 1}"
    speaker_profiles.append(
        {"name": name, "embedding": embedding.tolist(), "samples": 1}
    )
    return name, speaker_profiles
