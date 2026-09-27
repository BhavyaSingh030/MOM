"""Orchestrate meeting NLP and persist its results."""

from typing import Any

try:
    from .extraction_summary import extract_action_items, generate_minutes, summarize
    from .nlp_core import classify_sentences, cluster_topics, preprocess
except ImportError:
    from extraction_summary import extract_action_items, generate_minutes, summarize
    from nlp_core import classify_sentences, cluster_topics, preprocess

from db import db_utils


def run_pipeline(meeting_id: int, raw_transcript: str) -> dict[str, Any]:
    """Analyze a meeting transcript, save the results, and return its minutes."""
    meeting_data = db_utils.get_full_meeting_data(meeting_id)
    if meeting_data is None:
        raise ValueError(f"Meeting {meeting_id} does not exist")
    meeting = meeting_data["meeting"]

    sentences_df = preprocess(raw_transcript)
    sentence_texts = sentences_df["cleaned_sentence"].fillna("").tolist()
    try:
        sentence_types = classify_sentences(sentence_texts)
    except Exception:
        sentence_types = []
        for text in sentence_texts:
            lowered = (text or "").lower()
            if any(keyword in lowered for keyword in ["will", "should", "need to", "prepare", "send", "review", "complete", "update", "schedule"]):
                sentence_types.append("action_item")
            elif any(keyword in lowered for keyword in ["agreed", "approved", "decided", "confirmed", "resolved", "done"]):
                sentence_types.append("decision")
            elif "?" in lowered:
                sentence_types.append("question")
            else:
                sentence_types.append("discussion")

    if len(sentence_types) != len(sentences_df):
        sentence_types = sentence_types[: len(sentences_df)] + ["discussion"] * max(0, len(sentences_df) - len(sentence_types))
    sentences_df["sentence_type"] = sentence_types

    if sentence_texts:
        cluster_count = min(4, len(sentence_texts))
        try:
            cluster_labels, topic_keywords = cluster_topics(sentence_texts, k=cluster_count)
        except Exception:
            cluster_labels, topic_keywords = list(range(len(sentence_texts))), {}
    else:
        cluster_labels, topic_keywords = [], {}
    sentences_df["topic_cluster"] = cluster_labels

    extracted_items = extract_action_items(sentences_df)
    summary = summarize(sentence_texts) or db_utils.build_minutes_from_conversation(
        meeting_title=meeting.get("title") or "Untitled meeting",
        date=meeting.get("date") or "Date not recorded",
        conversation=raw_transcript,
        user_name=meeting.get("user_id"),
    )
    minutes_text = generate_minutes(
        meeting_title=meeting.get("title") or "Untitled meeting",
        date=meeting.get("date") or "Date not recorded",
        sentences_df=sentences_df,
        action_items=extracted_items,
        summary=summary,
    )

    db_utils.reset_meeting_derived_data(meeting_id)
    db_utils.update_meeting_transcript(meeting_id, raw_transcript)
    sentence_ids = db_utils.insert_sentences_with_ids(
        [
            {
                "meeting_id": meeting_id,
                "speaker": row["speaker"],
                "sentence_text": row["raw_sentence"],
                "sentence_type": row["sentence_type"],
                "topic_cluster": row["topic_cluster"],
            }
            for row in sentences_df.to_dict(orient="records")
        ]
    )

    sentence_records = [
        {**row, "sentence_id": sentence_id}
        for row, sentence_id in zip(sentences_df.to_dict(orient="records"), sentence_ids)
    ]
    action_rows = [
        (index, str(row["raw_sentence"] or ""))
        for index, row in enumerate(sentence_records)
        if row["sentence_type"] == "action_item"
    ]
    unused_action_rows = set(range(len(action_rows)))
    persisted_action_items: list[dict[str, str | int | None]] = []
    for item in extracted_items:
        task = str(item.get("task") or "").casefold()
        matching_action_index = next(
            (
                index
                for index in sorted(unused_action_rows)
                if task and task in action_rows[index][1].casefold()
            ),
            None,
        )
        sentence_id = (
            sentence_records[action_rows[matching_action_index][0]]["sentence_id"]
            if matching_action_index is not None
            else None
        )
        if matching_action_index is not None:
            unused_action_rows.remove(matching_action_index)
        persisted_item = {**item, "sentence_id": sentence_id}
        persisted_action_items.append(persisted_item)

    db_utils.insert_action_items(
        [
            {"meeting_id": meeting_id, **item}
            for item in persisted_action_items
        ]
    )
    minutes_id = db_utils.insert_minutes(meeting_id, minutes_text)

    return {
        "meeting_id": meeting_id,
        "title": meeting.get("title"),
        "date": meeting.get("date"),
        "raw_transcript": raw_transcript,
        "sentences": sentence_records,
        "topic_keywords": topic_keywords,
        "action_items": persisted_action_items,
        "summary": summary,
        "minutes_id": minutes_id,
        "minutes": minutes_text,
    }
