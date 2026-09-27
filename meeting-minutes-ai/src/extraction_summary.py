"""Action-item extraction, extractive summaries, and meeting minutes."""

from functools import lru_cache
import re
from typing import Any, Sequence

import pandas as pd
import spacy
from nltk.tokenize import PunktSentenceTokenizer, TreebankWordTokenizer
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.text_rank import TextRankSummarizer


TASK_PREFIX_PATTERN = re.compile(
    r"^\s*(?:please\s+)?(?:i(?:'|’)ll|we(?:'|’)ll|you(?:'|’)ll|"
    r"(?:i|we|you|he|she|they|[A-Z][\w'-]*)\s+"
    r"(?:will|shall|should|must|can|could|would|need(?:s)?\s+to|"
    r"have\s+to|has\s+to|am\s+going\s+to|is\s+going\s+to|"
    r"are\s+going\s+to)\s+)",
    flags=re.IGNORECASE,
)


class _LocalTokenizer:
    def __init__(self) -> None:
        self._sentences = PunktSentenceTokenizer()
        self._words = TreebankWordTokenizer()

    def to_sentences(self, text: str) -> tuple[str, ...]:
        return tuple(sentence.strip() for sentence in self._sentences.tokenize(text))

    def to_words(self, text: str) -> tuple[str, ...]:
        return tuple(word for word in self._words.tokenize(text) if Tokenizer._is_word(word))


@lru_cache(maxsize=1)
def _get_nlp() -> Any:
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        return spacy.blank("en")


def _sentence_text(row: pd.Series) -> str:
    raw_sentence = row.get("raw_sentence")
    if isinstance(raw_sentence, str) and raw_sentence.strip():
        return raw_sentence.strip()
    cleaned_sentence = row.get("cleaned_sentence")
    if isinstance(cleaned_sentence, str):
        return cleaned_sentence.strip()
    return ""


def _task_span(text: str, doc: Any) -> tuple[str, int]:
    speaker_match = re.match(r"^\s*[\w .'-]{1,40}:\s*", text)
    body_start = speaker_match.end() if speaker_match else 0
    body = text[body_start:]

    prefix_match = TASK_PREFIX_PATTERN.match(body)
    if prefix_match:
        task_start = body_start + prefix_match.end()
    else:
        task_start = next(
            (
                body_start + token.idx
                for token in doc
                if token.idx >= body_start and token.pos_ == "VERB"
            ),
            body_start,
        )

    task = text[task_start:].strip(" \t\r\n.,;:")
    return task, task_start


def _remove_deadline(task: str, deadline: str | None) -> str:
    if not deadline:
        return task
    task = re.sub(re.escape(deadline), "", task, flags=re.IGNORECASE)
    task = re.sub(r"\b(?:by|before|on|after|due)\s*$", "", task, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", task).strip(" \t\r\n.,;:")


def extract_action_items(sentences_df: pd.DataFrame) -> list[dict[str, str | None]]:
    """Extract task, nearest PERSON owner, and DATE deadline from action rows."""
    if "sentence_type" not in sentences_df.columns:
        raise ValueError("sentences_df must contain a sentence_type column")

    nlp = _get_nlp()
    action_rows = sentences_df.loc[sentences_df["sentence_type"] == "action_item"]
    action_items: list[dict[str, str | None]] = []
    for _, row in action_rows.iterrows():
        sentence = _sentence_text(row)
        doc = nlp(sentence)
        task, task_start = _task_span(sentence, doc)

        person_entities = [entity for entity in doc.ents if entity.label_ == "PERSON"]
        owner = (
            min(person_entities, key=lambda entity: abs(entity.start_char - task_start)).text
            if person_entities
            else None
        )
        date_entities = [entity for entity in doc.ents if entity.label_ == "DATE"]
        deadline = date_entities[0].text if date_entities else None
        task = _remove_deadline(task, deadline)

        if task:
            action_items.append({"task": task, "owner": owner, "deadline": deadline})
    return action_items


def summarize(sentences_list: Sequence[str], num_sentences: int = 5) -> str:
    """Return a TextRank extractive summary of the supplied sentences."""
    if num_sentences < 1:
        raise ValueError("num_sentences must be at least 1")
    text = " ".join(sentence.strip() for sentence in sentences_list if sentence.strip())
    if not text:
        return ""

    try:
        tokenizer = Tokenizer("english")
    except LookupError:
        tokenizer = _LocalTokenizer()
    parser = PlaintextParser.from_string(text, tokenizer)
    summary = TextRankSummarizer()(parser.document, num_sentences)
    return " ".join(str(sentence) for sentence in summary)


def generate_minutes(
    meeting_title: str,
    date: str,
    sentences_df: pd.DataFrame,
    action_items: Sequence[dict[str, str | None]],
    summary: str,
) -> str:
    """Format meeting details, decisions, discussion summary, and action items."""
    attendees: list[str] = []
    if "speaker" in sentences_df.columns:
        for speaker in sentences_df["speaker"].dropna().astype(str):
            speaker = speaker.strip()
            if speaker and speaker not in attendees:
                attendees.append(speaker)

    decisions: list[str] = []
    if "sentence_type" in sentences_df.columns:
        decision_rows = sentences_df.loc[sentences_df["sentence_type"] == "decision"]
        decisions = [
            _sentence_text(row)
            for _, row in decision_rows.iterrows()
            if _sentence_text(row)
        ]

    lines = [
        f"# Minutes of Meeting: {meeting_title}",
        f"Date: {date}",
        "",
        "## Attendees",
        ", ".join(attendees) if attendees else "Not recorded",
        "",
        "## Key Decisions",
    ]
    lines.extend(f"- {decision}" for decision in decisions)
    if not decisions:
        lines.append("- None recorded")
    lines.extend(["", "## Discussion Summary", summary.strip() or "No summary available.", ""])
    lines.extend(
        [
            "## Action Items",
            "| Task | Owner | Deadline |",
            "| --- | --- | --- |",
        ]
    )
    if action_items:
        for item in action_items:
            task = str(item.get("task") or "").replace("|", "\\|")
            owner = str(item.get("owner") or "Unassigned").replace("|", "\\|")
            deadline = str(item.get("deadline") or "Not specified").replace("|", "\\|")
            lines.append(f"| {task} | {owner} | {deadline} |")
    else:
        lines.append("| No action items | - | - |")
    return "\n".join(lines)


def _extract_conversation_facts(conversation: str) -> list[str]:
    rows: list[str] = []
    for line in str(conversation or "").splitlines():
        text = line.strip()
        if text:
            rows.append(text)
    return rows


def build_minutes_from_conversation(
    meeting_title: str,
    date: str,
    conversation: str,
    user_name: str | None = None,
) -> str:
    """Create a meeting summary from the raw conversation while preserving decision/action detail."""
    lines = [
        f"# Minutes of Meeting: {meeting_title}",
        f"Date: {date}",
        "",
        "## Participants",
        user_name.strip() if user_name and user_name.strip() else "Host",
        "",
        "## Meeting Discussion",
    ]
    facts = _extract_conversation_facts(conversation)
    if not facts:
        lines.append("No discussion was captured for this meeting.")
        return "\n".join(lines)

    for fact in facts:
        lines.append(f"- {fact}")

    lines.extend(["", "## Summary", "The conversation covered the agreed commitments, follow-ups, and timeline items discussed during the meeting."])
    return "\n".join(lines)


if __name__ == "__main__":
    from nlp_core import preprocess

    sample_transcript = (
        "Maya: We approved the revised launch date. "
        "Leo: I'll send the updated timeline to Jordan by Friday. "
        "Maya: Does everyone agree with the support schedule? "
        "Jordan: The support team has finished its training materials. "
        "Leo: We should review customer feedback next week. "
        "Maya: Priya will share the final budget on October 2."
    )
    sample_sentences = preprocess(sample_transcript)
    sample_sentences["sentence_type"] = [
        "decision",
        "action_item",
        "question",
        "discussion",
        "action_item",
        "action_item",
    ]

    extracted_items = extract_action_items(sample_sentences)
    discussion_summary = summarize(sample_sentences["raw_sentence"].tolist())
    minutes = generate_minutes(
        "Product Launch Planning",
        "2026-09-26",
        sample_sentences,
        extracted_items,
        discussion_summary,
    )
    print("Extracted action items:")
    for item in extracted_items:
        print(item)
    print("\nGenerated minutes:\n")
    print(minutes)
