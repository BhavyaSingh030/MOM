"""Core NLP utilities for meeting transcript preprocessing and analysis."""

from pathlib import Path
import re
from typing import Sequence

import joblib
import pandas as pd
from nltk.tokenize import PunktSentenceTokenizer, sent_tokenize
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABELED_DATA_PATH = PROJECT_ROOT / "data" / "labeled_sentences.csv"
MODEL_PATH = PROJECT_ROOT / "db" / "model.pkl"
SENTENCE_COLUMNS = ["speaker", "raw_sentence", "cleaned_sentence"]
FILLER_PATTERN = re.compile(
    r"\b(?:um+|uh+|erm+|er+|ah+|you know|i mean|sort of|kind of|basically|actually)\b",
    flags=re.IGNORECASE,
)
SPEAKER_PATTERN = re.compile(r"^([\w][\w .'-]{0,39}):\s*(.+)$", flags=re.DOTALL)
SPEAKER_BOUNDARY_PATTERN = re.compile(
    r"\s+(?=(?:Speaker\s+\d+|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}):\s)"
)


def _sentence_tokenize(text: str) -> list[str]:
    if not text.strip():
        return []
    try:
        return sent_tokenize(text)
    except LookupError:
        return PunktSentenceTokenizer().tokenize(text)


def preprocess(raw_transcript: str) -> pd.DataFrame:
    """Split a transcript into speaker, original sentence, and cleaned text."""
    rows: list[dict[str, str | None]] = []
    for line in raw_transcript.splitlines() or [raw_transcript]:
        for turn in SPEAKER_BOUNDARY_PATTERN.split(line.strip()):
            match = SPEAKER_PATTERN.match(turn.strip())
            speaker = match.group(1).strip() if match else None
            text = match.group(2) if match else turn.strip()

            for sentence in _sentence_tokenize(text):
                sentence = sentence.strip()
                if not sentence:
                    continue
                raw_sentence = f"{speaker}: {sentence}" if speaker else sentence
                cleaned_sentence = FILLER_PATTERN.sub(" ", sentence.lower())
                cleaned_sentence = re.sub(r"\s+", " ", cleaned_sentence)
                cleaned_sentence = re.sub(r"\s+([,.;!?])", r"\1", cleaned_sentence).strip()
                rows.append(
                    {
                        "speaker": speaker,
                        "raw_sentence": raw_sentence,
                        "cleaned_sentence": cleaned_sentence,
                    }
                )
    return pd.DataFrame(rows, columns=SENTENCE_COLUMNS)


def train_classifier() -> dict[str, object]:
    """Evaluate Naive Bayes and linear SVM, then save the stronger model."""
    labeled = pd.read_csv(LABELED_DATA_PATH)
    required_columns = {"sentence", "sentence_type"}
    if not required_columns.issubset(labeled.columns):
        raise ValueError("Labeled data must contain sentence and sentence_type columns")
    labeled = labeled.dropna(subset=["sentence", "sentence_type"])
    if labeled["sentence_type"].nunique() < 2:
        raise ValueError("Training data must contain at least two sentence types")

    train_text, test_text, train_labels, test_labels = train_test_split(
        labeled["sentence"].astype(str),
        labeled["sentence_type"].astype(str),
        test_size=0.25,
        random_state=42,
        stratify=labeled["sentence_type"],
    )
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    train_vectors = vectorizer.fit_transform(train_text)
    test_vectors = vectorizer.transform(test_text)
    candidates = {
        "Multinomial Naive Bayes": MultinomialNB(),
        "Linear SVM": LinearSVC(random_state=42),
    }

    reports: dict[str, dict[str, object]] = {}
    best_name = ""
    best_score = -1.0
    best_model = None
    for name, model in candidates.items():
        model.fit(train_vectors, train_labels)
        predictions = model.predict(test_vectors)
        print(f"\n{name} classification report:")
        print(classification_report(test_labels, predictions, zero_division=0))
        report = classification_report(
            test_labels, predictions, output_dict=True, zero_division=0
        )
        reports[name] = report
        macro_f1 = float(report["macro avg"]["f1-score"])
        if macro_f1 > best_score:
            best_name = name
            best_score = macro_f1
            best_model = model

    final_vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    all_vectors = final_vectorizer.fit_transform(labeled["sentence"].astype(str))
    best_model.fit(all_vectors, labeled["sentence_type"].astype(str))
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": best_model, "vectorizer": final_vectorizer}, MODEL_PATH)
    return {"best_model": best_name, "macro_f1": best_score, "reports": reports}


def classify_sentences(sentence_list: Sequence[str]) -> list[str]:
    """Classify sentences with the model saved by train_classifier()."""
    if not sentence_list:
        return []
    if not MODEL_PATH.exists():
        fallback = []
        for sentence in sentence_list:
            text = str(sentence or "").lower()
            if any(keyword in text for keyword in ["will", "should", "need to", "prepare", "send", "review", "complete", "update", "schedule"]):
                fallback.append("action_item")
            elif any(keyword in text for keyword in ["agreed", "approved", "decided", "confirmed", "resolved", "done"]):
                fallback.append("decision")
            elif "?" in text:
                fallback.append("question")
            else:
                fallback.append("discussion")
        return fallback

    saved = joblib.load(MODEL_PATH)
    vectors = saved["vectorizer"].transform(sentence_list)
    return saved["model"].predict(vectors).tolist()


def cluster_topics(
    sentence_list: Sequence[str], k: int = 4
) -> tuple[list[int], dict[int, list[str]]]:
    """Return a cluster ID per sentence and three representative terms per cluster."""
    if not sentence_list:
        return [], {}
    if k < 1 or k > len(sentence_list):
        raise ValueError("k must be between 1 and the number of sentences")

    vectorizer = TfidfVectorizer(stop_words="english")
    try:
        vectors = vectorizer.fit_transform(sentence_list)
    except ValueError as error:
        raise ValueError("Sentences must contain at least one usable word") from error

    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = model.fit_predict(vectors)
    terms = vectorizer.get_feature_names_out()
    keywords: dict[int, list[str]] = {}
    for cluster_id, center in enumerate(model.cluster_centers_):
        top_indices = center.argsort()[::-1]
        keywords[cluster_id] = [
            str(terms[index]) for index in top_indices if center[index] > 0
        ][:3]
    return labels.tolist(), keywords


if __name__ == "__main__":
    sample_transcript = (
        "Maya: Um, we approved the revised launch date. "
        "Leo: I will send the updated timeline by Friday. "
        "Maya: Does everyone agree with the new support schedule? "
        "Leo: The support team has completed the training materials. "
        "Maya: We should review the customer feedback next week."
    )
    processed = preprocess(sample_transcript)
    print("Preprocessed transcript:")
    print(processed.to_string(index=False))

    training_result = train_classifier()
    print(f"\nSelected model: {training_result['best_model']}")
    print("Predicted sentence types:")
    print(classify_sentences(processed["cleaned_sentence"].tolist()))

    cluster_labels, cluster_keywords = cluster_topics(
        processed["cleaned_sentence"].tolist(), k=4
    )
    print("\nTopic clusters:")
    print(cluster_labels)
    print(cluster_keywords)
