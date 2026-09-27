"""Streamlit host and participant interface for meeting-minutes-ai."""

from datetime import date
import html
import io
from pathlib import Path
import sys
import threading
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db import db_utils

LANGUAGE_OPTIONS = ["English", "Hindi", "Spanish", "French"]
LANGUAGE_CODES = {"English": "en", "Hindi": "hi", "Spanish": "es", "French": "fr"}
SPEECH_LOCALES = {
    "English": "en-US",
    "Hindi": "hi-IN",
    "Spanish": "es-ES",
    "French": "fr-FR",
}
_live_speech = components.declare_component(
    "live_speech",
    path=str(Path(__file__).resolve().parent / "live_speech"),
)


st.set_page_config(
    page_title="Meeting Room | Minutes Console",
    page_icon="M",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
    :root {
        --bg: #0d1110;
        --bg-soft: #141b19;
        --panel: #171f1d;
        --panel-2: #1d2825;
        --sidebar: #101715;
        --line: #2a3835;
        --text: #edf4ef;
        --muted: #a7b1aa;
        --accent: #b8f46d;
        --accent-strong: #9de34a;
        --accent-2: #7bd9c2;
        --orange: #f7925b;
        --danger: #ff8d7a;
        --shadow: rgba(0, 0, 0, 0.22);
    }
    html, body, [class*="css"] {
        font-family: 'Manrope', sans-serif;
        background: var(--bg);
        color: var(--text);
    }
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%);
    }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] {
        background: var(--sidebar);
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] > div:first-child { padding-top: 1.25rem; }
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 3rem;
        max-width: 1320px;
    }
    .brand-mark {
        display: flex; align-items: center; gap: 11px; margin: 0 0 1.4rem;
        font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase;
        color: var(--text);
    }
    .brand-square {
        width: 30px; height: 30px; display: grid; place-items: center;
        background: var(--accent); color: #101510; font: 500 15px 'DM Mono', monospace;
        border-radius: 6px;
    }
    .eyebrow { color: var(--accent-2); font: 500 11px 'DM Mono', monospace; text-transform: uppercase; }
    .page-title { margin: 0.15rem 0 0.2rem; font-size: 30px; line-height: 1.18; font-weight: 800; color: var(--text); }
    .page-subtitle { margin: 0 0 1.35rem; color: var(--muted); font-size: 13px; }
    .section-label {
        margin: 0 0 0.6rem; color: var(--muted); font: 500 11px 'DM Mono', monospace;
        text-transform: uppercase;
    }
    .code-panel {
        padding: 1rem 1.1rem; background: var(--panel-2); color: var(--accent);
        border: 1px solid var(--line); border-radius: 12px;
        font: 500 24px 'DM Mono', monospace; letter-spacing: 0.03em;
    }
    .live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
        background: var(--orange); margin-right: 7px; }
    div[data-testid="stMetric"] {
        background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--accent-2);
        padding: 0.7rem 0.9rem; box-shadow: 0 8px 18px var(--shadow);
    }
    div[data-testid="stMetricLabel"] { color: var(--muted); font-size: 11px; }
    div[data-testid="stMetricValue"] { font-family: 'DM Mono', monospace; font-size: 24px; color: var(--text); }
    div.stButton > button[kind="primary"] {
        background: var(--accent); color: #111611; border: 1px solid var(--accent);
        font-weight: 800; min-height: 42px; box-shadow: 0 10px 18px rgba(184, 244, 109, 0.18);
    }
    div.stButton > button[kind="primary"]:hover { background: var(--accent-strong); border-color: var(--accent-strong); }
    div.stButton > button {
        border-radius: 8px; background: var(--panel); color: var(--text); border: 1px solid var(--line);
    }
    [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; }
    [data-testid="stFileUploader"] section { border-radius: 10px; }
    .mono-caption { color: var(--muted); font: 400 11px 'DM Mono', monospace; }
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div,
    .stNumberInput > div > div > input {
        background: var(--panel);
        color: var(--text);
        border: 1px solid var(--line);
        border-radius: 10px;
    }
    .stTabs [role="tablist"] { background: transparent; }
    .stTabs [role="tab"] { color: var(--muted); }
    .stTabs [role="tab"][aria-selected="true"] { color: var(--text); }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state() -> None:
    defaults = {
        "user": None,
        "auth_mode": "signin",
        "host_meeting_id": None,
        "host_meeting_code": None,
        "host_audio_thread": None,
        "host_audio_status": None,
        "host_minutes": None,
        "join_meeting": None,
        "pending_speaker_profiles": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _sign_out() -> None:
    for key in (
        "user",
        "host_meeting_id",
        "host_meeting_code",
        "host_minutes",
        "join_meeting",
        "pending_speaker_profiles",
    ):
        st.session_state[key] = None
    st.rerun()


def _render_auth_card() -> None:
    if st.session_state.get("user"):
        user = st.session_state["user"]
        st.sidebar.markdown("### Workspace")
        st.sidebar.caption(f"Signed in as {user['name']}")
        if st.sidebar.button("Sign out"):
            _sign_out()
        return

    st.sidebar.markdown("### Workspace")
    auth_mode = st.sidebar.radio("Account", ["Sign in", "Create account"], horizontal=True)
    st.session_state["auth_mode"] = "signin" if auth_mode == "Sign in" else "signup"

    if st.session_state["auth_mode"] == "signup":
        with st.sidebar.form("signup_form"):
            name = st.text_input("Your name", key="signup_name")
            email = st.text_input("Work email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            submit = st.form_submit_button("Create account", type="primary")
        if submit:
            try:
                user = db_utils.create_user(name, email, password)
                st.session_state["user"] = user
                st.sidebar.success("Account created successfully.")
                st.rerun()
            except ValueError as error:
                st.sidebar.error(str(error))
    else:
        with st.sidebar.form("signin_form"):
            email = st.text_input("Email", key="signin_email")
            password = st.text_input("Password", type="password", key="signin_password")
            submit = st.form_submit_button("Sign in", type="primary")
        if submit:
            user = db_utils.authenticate_user(email, password)
            if user is None:
                st.sidebar.error("Invalid email or password.")
            else:
                st.session_state["user"] = user
                st.rerun()


@st.cache_resource(show_spinner=False)
def _classifier_evaluation_state() -> dict[str, Any]:
    return {"finished": True, "skipped": True}


def _audio_thread(audio_path: str, meeting_id: int, status: dict[str, Any]) -> None:
    try:
        from src.live_transcribe import simulate_live_meeting

        status["transcript"] = simulate_live_meeting(audio_path, meeting_id)
    except Exception as error:
        status["error"] = str(error)
    finally:
        status["finished"] = True


def _save_live_utterance(meeting_id: int, speaker: str, text: str) -> None:
    text = text.strip()
    if not text:
        return
    db_utils.insert_sentences(
        [
            {
                "meeting_id": meeting_id,
                "speaker": speaker,
                "sentence_text": text,
                "sentence_type": None,
                "topic_cluster": None,
            }
        ]
    )
    meeting_data = db_utils.get_full_meeting_data(meeting_id)
    if meeting_data is None:
        return
    transcript_lines = []
    for row in meeting_data["sentences"]:
        utterance = (row.get("sentence_text") or "").strip()
        speaker_name = (row.get("speaker") or "").strip()
        if utterance:
            transcript_lines.append(
                f"{speaker_name}: {utterance}" if speaker_name else utterance
            )
    db_utils.update_meeting_transcript(meeting_id, "\n".join(transcript_lines))


def _speaker_error_message(error: Exception) -> str:
    if isinstance(error, ModuleNotFoundError) and error.name == "speechbrain":
        return (
            "SpeechBrain is missing from the Python environment running Streamlit. "
            "Install requirements with that same Python, then restart Streamlit."
        )
    return str(error)


@st.fragment(run_every=1)
def _show_classifier_report() -> None:
    st.sidebar.markdown("### Classifier report")
    result = _classifier_evaluation_state()
    if not result["finished"]:
        st.sidebar.caption("Evaluating labeled examples…")
        return
    if "error" in result:
        st.sidebar.warning("Evaluation unavailable")
        st.sidebar.caption(result["error"])
        return
    best_name = result["best_model"]
    report = result["reports"][best_name]
    st.sidebar.caption(best_name)
    metric_cols = st.sidebar.columns(2)
    metric_cols[0].metric("Accuracy", f"{report['accuracy']:.0%}")
    metric_cols[1].metric("Macro F1", f"{report['macro avg']['f1-score']:.0%}")
    st.sidebar.caption(f"Weighted F1  {report['weighted avg']['f1-score']:.0%}")


def _render_host_mode() -> bool:
    user = st.session_state.get("user")
    if user is None:
        st.warning("Please sign in to host or view your meetings.")
        return False

    meeting_id = st.session_state.host_meeting_id
    if meeting_id is None:
        st.markdown('<p class="eyebrow">01 / Host a room</p>', unsafe_allow_html=True)
        st.markdown('<h1 class="page-title">Prepare a meeting</h1>', unsafe_allow_html=True)
        st.markdown(
            '<p class="page-subtitle">Record each participant’s voice sample before starting. The samples will identify speakers in the transcript.</p>',
            unsafe_allow_html=True,
        )
        setup_left, setup_right = st.columns([1, 1.1], gap="large")
        pending_key = "pending_speaker_profiles"
        pending_profiles = st.session_state.setdefault(pending_key, [])

        with setup_left:
            st.markdown("#### Speaker samples")
            st.caption(
                "Allow microphone access, record one complete sentence for each participant, then press Stop and save sample. Voice recordings and profiles are saved with the meeting."
            )
            setup_event = _live_speech(
                active=True,
                enrollmentOnly=True,
                speakerCount=len(pending_profiles),
                key="premeeting_speaker_setup",
                default=None,
            )
            setup_event_key = "premeeting_last_enrollment_id"
            notice_key = "premeeting_enrollment_notice"
            if st.session_state.get(notice_key):
                st.success(st.session_state.pop(notice_key))
            if (
                isinstance(setup_event, dict)
                and setup_event.get("enroll")
                and setup_event.get("id") != st.session_state.get(setup_event_key)
            ):
                try:
                    from src.speaker_id import decode_wav_base64, embedding_from_wav_base64

                    audio_base64 = str(setup_event.get("audio") or "")
                    if not audio_base64:
                        raise ValueError("No voice sample was captured. Try recording again.")
                    embedding = embedding_from_wav_base64(audio_base64)
                    speaker_name = f"Speaker {len(pending_profiles) + 1}"
                    pending_profiles.append(
                        {
                            "name": speaker_name,
                            "embedding": embedding.tolist(),
                            "samples": 1,
                            "sample_audio": decode_wav_base64(audio_base64),
                        }
                    )
                    st.session_state[pending_key] = pending_profiles
                    st.session_state[notice_key] = f"Voice sample saved as {speaker_name}."
                except Exception as error:
                    st.session_state[notice_key] = (
                        f"Could not save that voice sample: {_speaker_error_message(error)}"
                    )
                st.session_state[setup_event_key] = setup_event.get("id")
                st.rerun()

            if pending_profiles:
                st.markdown("**Recorded speakers**")
                for profile in pending_profiles:
                    st.write(f"• {profile['name']}")
            else:
                st.info("Add a sample for each person who will speak.")

        with setup_right:
            st.markdown("#### Meeting details")
            with st.form("start_meeting_form", clear_on_submit=False):
                title = st.text_input(
                    "Meeting title",
                    placeholder="Quarterly product review",
                    key="new_meeting_title",
                )
                start_meeting = st.form_submit_button(
                    "Start Meeting",
                    type="primary",
                    disabled=not pending_profiles,
                )
            if not pending_profiles:
                st.caption("Record at least one speaker sample to enable the meeting.")

            if start_meeting:
                if not title.strip():
                    st.error("Add a meeting title to continue.")
                    return False

                db_utils.init_db()
                new_meeting_id, meeting_code = db_utils.create_meeting(
                    title.strip(), date.today().isoformat(), user["user_id"]
                )
                for profile in pending_profiles:
                    db_utils.upsert_speaker_profile(
                        new_meeting_id,
                        str(profile["name"]),
                        profile["embedding"],
                        int(profile["samples"]),
                        profile["sample_audio"],
                    )
                st.session_state[f"speaker_profiles_{new_meeting_id}"] = [
                    {key: value for key, value in profile.items() if key != "sample_audio"}
                    for profile in pending_profiles
                ]
                st.session_state[pending_key] = []
                st.session_state.host_meeting_id = new_meeting_id
                st.session_state.host_meeting_code = meeting_code
                st.session_state.host_minutes = None
                st.rerun()

        recent_meetings = db_utils.get_recent_meetings(limit=8, user_id=user["user_id"])
        if recent_meetings:
            st.divider()
            st.markdown("#### My meetings")
            recent_by_id = {row["meeting_id"]: row for row in recent_meetings}

            def recent_meeting_label(recent_id: int) -> str:
                row = recent_by_id[recent_id]
                title_text = row.get("title") or "Untitled meeting"
                status_text = "MoM saved" if row["has_minutes"] else row["status"].title()
                return f"{title_text} · {row['date']} · {status_text}"

            selected_meeting_id = st.selectbox(
                "Recent meetings",
                options=list(recent_by_id),
                format_func=recent_meeting_label,
            )
            if st.button("Open meeting", key="open_recent_meeting"):
                st.session_state[pending_key] = []
                selected_meeting = recent_by_id[selected_meeting_id]
                st.session_state.host_meeting_id = selected_meeting_id
                st.session_state.host_meeting_code = selected_meeting["meeting_code"]
                st.session_state.host_minutes = None
                st.rerun()

        return False

    meeting_data = db_utils.get_full_meeting_data(meeting_id)
    if meeting_data is None:
        st.error("This meeting is no longer available in the database.")
        st.session_state.host_meeting_id = None
        return False

    meeting = meeting_data["meeting"]
    is_ended = meeting.get("status") == "ended"
    profile_key = f"speaker_profiles_{meeting_id}"
    if profile_key not in st.session_state:
        st.session_state[profile_key] = db_utils.get_speaker_profiles(meeting_id)

    header_left, header_right = st.columns([4, 1])
    with header_left:
        st.markdown('<p class="eyebrow">01 / Host room</p>', unsafe_allow_html=True)
        title = html.escape(str(meeting.get("title") or "Untitled meeting"))
        st.markdown(f'<h1 class="page-title">{title}</h1>', unsafe_allow_html=True)
        state_label = "ENDED" if is_ended else "LIVE"
        dot = "" if is_ended else '<span class="live-dot"></span>'
        st.markdown(
            f'<div class="mono-caption">{dot}{state_label} &nbsp; / &nbsp; {meeting["date"]}</div>',
            unsafe_allow_html=True,
        )
    with header_right:
        if st.button("New meeting", key="new_host_meeting"):
            for key in (
                "host_meeting_id",
                "host_meeting_code",
                "host_minutes",
            ):
                st.session_state[key] = None
            st.rerun()

    st.markdown('<p class="section-label">Share this room code</p>', unsafe_allow_html=True)
    room_code = html.escape(str(st.session_state.host_meeting_code or ""))
    st.markdown(
        f'<div class="code-panel">{room_code}</div>',
        unsafe_allow_html=True,
    )

    selected_language = st.selectbox(
        "Transcript language",
        LANGUAGE_OPTIONS,
        key=f"host_language_{meeting_id}",
        disabled=is_ended,
    )
    if not is_ended:
        speech_event = _live_speech(
            active=True,
            lang=SPEECH_LOCALES[selected_language],
            speakerCount=len(st.session_state[profile_key]),
            key=f"live_speech_{meeting_id}",
            default=None,
        )
        enrollment_notice_key = f"speaker_enrollment_notice_{meeting_id}"
        if st.session_state.get(enrollment_notice_key):
            st.success(st.session_state.pop(enrollment_notice_key))
        if isinstance(speech_event, dict) and (
            speech_event.get("text") or speech_event.get("utterances") or speech_event.get("enroll")
        ):
            event_key = f"host_last_speech_id_{meeting_id}"
            if speech_event.get("id") != st.session_state.get(event_key):
                enrollment_saved = False
                if speech_event.get("enroll"):
                    audio = speech_event.get("audio")
                    try:
                        from src.speaker_id import embedding_from_wav_base64

                        if not audio:
                            raise ValueError("No voice sample was captured. Try recording again.")
                        profiles = st.session_state[profile_key]
                        voice_embedding = embedding_from_wav_base64(str(audio))
                        speaker = f"Speaker {len(profiles) + 1}"
                        profiles.append(
                            {
                                "name": speaker,
                                "embedding": voice_embedding.tolist(),
                                "samples": 1,
                            }
                        )
                        st.session_state[profile_key] = profiles
                        st.success(f"Voice sample saved as {speaker}.")
                        enrollment_saved = True
                    except Exception as error:
                        st.warning(
                            f"Could not save the voice sample: {_speaker_error_message(error)}"
                        )
                else:
                    from src.speaker_id import embedding_from_wav_base64, match_speaker

                    utterances = speech_event.get("utterances") or [
                        {"text": speech_event.get("text"), "audio": speech_event.get("audio")}
                    ]
                    for utterance in utterances:
                        text = str(utterance.get("text") or "").strip()
                        if not text:
                            continue
                        speaker = "Speaker ?"
                        audio = utterance.get("audio")
                        if audio:
                            try:
                                profiles = st.session_state[profile_key]
                                voice_embedding = embedding_from_wav_base64(str(audio))
                                speaker, profiles = match_speaker(voice_embedding, profiles)
                            except Exception as error:
                                st.warning(
                                    f"Could not identify a speaker: {_speaker_error_message(error)}"
                                )
                        else:
                            speaker = "Speaker ?"
                        _save_live_utterance(meeting_id, speaker, text)
                st.session_state[event_key] = speech_event.get("id")
                if enrollment_saved:
                    st.session_state[enrollment_notice_key] = f"Voice sample saved as {speaker}."
                    st.rerun()

    meeting_data = db_utils.get_full_meeting_data(meeting_id)
    meeting = meeting_data["meeting"]
    transcript = meeting.get("raw_transcript") or ""
    transcript_col, actions_col = st.columns([1.55, 1], gap="large")
    with transcript_col:
        st.markdown("#### Transcript")
        if not is_ended:
            st.caption(
                "Enrollment voice profiles are saved with this meeting. Speak for at least one second per turn for reliable matching; live voice clips are not saved."
            )
        if not transcript:
            st.info("Waiting for speech. Allow microphone access if your browser asks.")
        st.text_area(
            "Meeting transcript",
            value=transcript,
            height=350,
            disabled=True,
            label_visibility="collapsed",
            key=f"host_transcript_{meeting_id}_{len(transcript)}",
        )
    with actions_col:
        st.markdown("#### Meeting controls")
        if not is_ended:
            if st.button(
                "End Meeting & Generate MoM",
                type="primary",
                disabled=not transcript,
                use_container_width=True,
            ):
                try:
                    from src.pipeline import run_pipeline

                    with st.spinner("Classifying the transcript and preparing the minutes..."):
                        result = run_pipeline(meeting_id, transcript)
                        db_utils.end_meeting(meeting_id)
                    st.session_state.host_minutes = result["minutes"]
                    st.rerun()
                except Exception as error:
                    st.error(f"Minutes generation failed: {error}")
        else:
            st.success("Meeting ended. Minutes are saved.")
            if st.button("Regenerate MoM", key=f"regenerate_minutes_{meeting_id}"):
                try:
                    from src.pipeline import run_pipeline

                    with st.spinner("Rebuilding minutes from the saved transcript..."):
                        result = run_pipeline(meeting_id, transcript)
                    st.session_state.host_minutes = result["minutes"]
                    st.rerun()
                except Exception as error:
                    st.error(f"Minutes regeneration failed: {error}")

    if is_ended:
        stored_minutes = meeting_data["minutes"][-1]["summary_text"] if meeting_data["minutes"] else ""
        minutes_text = st.session_state.host_minutes or stored_minutes
        st.divider()
        minutes_heading, download_column = st.columns([4, 1], vertical_alignment="center")
        minutes_heading.markdown("### Minutes of Meeting")
        if minutes_text:
            download_column.download_button(
                "Download MoM",
                data=minutes_text,
                file_name=f"meeting_{meeting_id}_minutes.md",
                mime="text/markdown",
                use_container_width=True,
            )
        st.markdown(minutes_text or "No minutes were saved for this meeting.")

    return not is_ended


@st.fragment(run_every=1)
def _render_join_mode() -> bool:
    user = st.session_state.get("user")
    if user is None:
        st.warning("Please sign in to access your meetings.")
        return False

    st.markdown('<p class="eyebrow">02 / Join a room</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="page-title">Meeting room</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="page-subtitle">Enter the host code to follow the transcript and minutes.</p>',
        unsafe_allow_html=True,
    )

    with st.form("join_meeting_form"):
        code = st.text_input("Meeting code", placeholder="Paste the host code")
        fetch = st.form_submit_button("Join meeting", type="primary")
    if fetch:
        meeting = db_utils.get_meeting_by_code(code.strip(), user_id=user["user_id"]) if code.strip() else None
        if meeting is None:
            st.session_state.join_meeting = None
            st.error("No meeting found for that code on your account.")
        else:
            st.session_state.join_meeting = meeting

    meeting_ref = st.session_state.join_meeting
    if not meeting_ref:
        return False

    meeting_data = db_utils.get_full_meeting_data(meeting_ref["meeting_id"])
    if meeting_data is None:
        st.error("This meeting is no longer available.")
        return False
    meeting = meeting_data["meeting"]
    is_ended = meeting.get("status") == "ended"

    title_col, lang_col = st.columns([3, 1])
    with title_col:
        status_text = "Ended" if is_ended else "In progress"
        st.subheader(meeting.get("title") or "Untitled meeting")
        st.caption(f"{meeting.get('date') or 'Date not recorded'}  /  {status_text}")
    with lang_col:
        language = st.selectbox(
            "Display language",
            ["English", "Hindi", "Spanish", "French"],
            key="join_language",
        )
    language_codes = {"English": "en", "Hindi": "hi", "Spanish": "es", "French": "fr"}
    target_lang = language_codes[language]

    transcript_sentences = [
        row["sentence_text"]
        for row in meeting_data["sentences"]
        if row.get("sentence_text")
    ]
    raw_transcript = meeting.get("raw_transcript") or ""
    if not transcript_sentences and raw_transcript:
        transcript_sentences = [line for line in raw_transcript.splitlines() if line.strip()]

    minutes_rows = meeting_data["minutes"]
    minutes_text = minutes_rows[-1]["summary_text"] if minutes_rows else ""
    left_col, right_col = st.columns(2, gap="large")
    with left_col:
        st.markdown("#### Transcript")
        if transcript_sentences:
            try:
                from src.translator import translate_transcript

                shown_sentences = translate_transcript(transcript_sentences, target_lang)
            except Exception as error:
                st.warning(f"Translation unavailable; showing the original text. {error}")
                shown_sentences = transcript_sentences
            st.text_area(
                "Meeting transcript",
                value="\n".join(shown_sentences),
                height=420,
                disabled=True,
                label_visibility="collapsed",
                key=f"join_transcript_{meeting['meeting_id']}_{language}_{len(transcript_sentences)}",
            )
        else:
            st.info("No transcript lines have arrived yet.")
    with right_col:
        st.markdown("#### Minutes of Meeting")
        if is_ended:
            if minutes_text:
                try:
                    from src.translator import translate_minutes

                    shown_minutes = translate_minutes(minutes_text, target_lang)
                except Exception as error:
                    st.warning(f"Translation unavailable; showing the original text. {error}")
                    shown_minutes = minutes_text
                st.markdown(shown_minutes)
            else:
                st.info("No minutes have been saved for this meeting.")
        else:
            st.info("Meeting in progress...")

    return not is_ended


_init_state()
db_utils.init_db()

st.sidebar.markdown(
    '<div class="brand-mark"><span class="brand-square">M</span> Minutes Console</div>',
    unsafe_allow_html=True,
)
_render_auth_card()

if st.session_state.get("user") is None:
    st.markdown(
        """
        <div style='max-width:1150px; margin: 40px auto; padding: 20px 0 0 0;'>
            <div style='display:flex; align-items:center; gap: 12px; color:#3b4d43; letter-spacing:0.18em; text-transform:uppercase; font-size:12px; font-weight:700;'>
                <span style='width:34px; height:1px; background:#3b4d43; display:inline-block;'></span>
                A clearer record of every room
            </div>
            <h1 style='font-size: clamp(4rem, 7vw, 8rem); line-height: 0.94; margin: 30px 0; font-weight: 800; letter-spacing: -0.07em; color:#1d2320;'>Good meetings<br>leave a <span style='color:#2a9d8f;'>trace.</span></h1>
            <p style='font-size: clamp(1.2rem, 2vw, 2rem); color:#4f5e57; max-width:900px; margin-bottom: 42px;'>Live transcription, useful patterns, and minutes you can actually follow up on.</p>
            <div style='display:flex; align-items:center; gap: 12px; color:#5b675f; font-size:0.9rem;'><span style='width:8px; height:8px; border-radius:50%; background:#d96d4d; display:inline-block;'></span> Your voice stays yours. Original words stay original.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.sidebar.divider()
    mode = st.sidebar.radio("Mode", ["Host", "Join"], horizontal=True)
    if mode == "Host":
        _render_host_mode()
    else:
        _render_join_mode()
