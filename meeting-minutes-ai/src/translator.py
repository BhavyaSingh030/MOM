"""Translate transcript and minutes text with a small in-memory cache."""

from deep_translator import GoogleTranslator


_TRANSLATION_CACHE: dict[tuple[str, str], str] = {}


def translate_text(text: str, target_lang_code: str) -> str:
    """Translate text into a target language, reusing cached translations."""
    cache_key = (text, target_lang_code)
    if cache_key not in _TRANSLATION_CACHE:
        _TRANSLATION_CACHE[cache_key] = GoogleTranslator(
            source="auto", target=target_lang_code
        ).translate(text)
    return _TRANSLATION_CACHE[cache_key]


def translate_transcript(sentences_list: list[str], target_lang: str) -> list[str]:
    """Translate each transcript sentence while preserving its order."""
    return [translate_text(sentence, target_lang) for sentence in sentences_list]


def translate_minutes(mom_text: str, target_lang: str) -> str:
    """Translate a formatted minutes-of-meeting document."""
    return translate_text(mom_text, target_lang)
